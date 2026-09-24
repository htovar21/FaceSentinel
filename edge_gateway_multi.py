#!/usr/bin/env python3
"""
edge_gateway_multi.py — Edge Gateway Multi-Cámara Concurrente
FaceSentinel — Tesis de Grado

Capacidad:
    Permite que un único dispositivo de borde (PC, Servidor de Borde, Raspberry Pi 4/5 o Jetson)
    gestione simultáneamente MÚLTIPLES puntos de acceso y flujos de video (RTSP IP, HTTP DroidCam, USB Webcams).
    
    Cada cámara corre en un Worker aislado (hilo independiente con buffer desacoplado),
    ejecuta análisis MediaPipe FaceMesh/EAR en paralelo y envía autenticaciones independientes
    con el hardware token correspondiente de cada punto de acceso.

Configuración:
    Carga las cámaras desde el archivo 'cameras.json' (se crea automáticamente si no existe).

Uso:
    .\venv\Scripts\python.exe edge_gateway_multi.py              # Modo Mosaico Visual NVR
    .\venv\Scripts\python.exe edge_gateway_multi.py --headless   # Modo Servicio en Segundo Plano (Raspberry Pi)
"""

import os
import sys
import time
import json
import base64
import argparse
import threading
from collections import deque
from datetime import datetime
import numpy as np
import cv2
import requests
import mediapipe as mp

# UTF-8 para consola de Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_CONFIG_PATH = os.path.join(BASE_DIR, "data", "cameras.json")
ROOT_CONFIG_PATH = os.path.join(BASE_DIR, "cameras.json")
CONFIG_PATH = DATA_CONFIG_PATH if os.path.exists(DATA_CONFIG_PATH) and os.path.getsize(DATA_CONFIG_PATH) > 0 else ROOT_CONFIG_PATH
DEFAULT_API_URL = os.getenv("FACESENTINEL_BACKEND_URL", "http://localhost:8000/api/v1/physical-access/authenticate")

# Landmarks MediaPipe Face Mesh para EAR
LEFT_EYE_IDX  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]

def eye_aspect_ratio(landmarks, eye_indices, img_w, img_h) -> float:
    pts = [
        np.array([landmarks[i].x * img_w, landmarks[i].y * img_h])
        for i in eye_indices
    ]
    A = np.linalg.norm(pts[1] - pts[5])
    B = np.linalg.norm(pts[2] - pts[4])
    C = np.linalg.norm(pts[0] - pts[3])
    return float((A + B) / (2.0 * C)) if C > 0 else 0.0

def crop_face(frame_bgr, face_landmarks, margin_pct: float = 0.35):
    h, w = frame_bgr.shape[:2]
    xs = [lm.x * w for lm in face_landmarks.landmark]
    ys = [lm.y * h for lm in face_landmarks.landmark]
    x_min, x_max = int(min(xs)), int(max(xs))
    y_min, y_max = int(min(ys)), int(max(ys))

    margin_x = int((x_max - x_min) * margin_pct)
    margin_y = int((y_max - y_min) * margin_pct)

    x1 = max(0, x_min - margin_x)
    y1 = max(0, y_min - margin_y)
    x2 = min(w, x_max + margin_x)
    y2 = min(h, y_max + margin_y)

    crop = frame_bgr[y1:y2, x1:x2]
    return crop if crop.size > 0 else None, (x1, y1, x2, y2)


# =========================================================================
#            CAPTURA DESACOPLADA DE VIDEO (Evita lag en RTSP)
# =========================================================================

class RTSPCaptureThread(threading.Thread):
    """
    Hilo de lectura continua que vacía constantemente el buffer de OpenCV.
    Garantiza que el procesamiento de IA siempre obtenga el fotograma MÁS RECIENTE,
    eliminando el retardo acumulado típico de RTSP sobre TCP/UDP.
    """
    def __init__(self, source):
        super().__init__(daemon=True)
        self.source = int(source) if str(source).isdigit() else str(source)
        self.cap = None
        self.running = True
        self.latest_frame = None
        self.lock = threading.Lock()
        self.connected = False

    def run(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                if isinstance(self.source, int):
                    self.cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        self.cap = cv2.VideoCapture(self.source)
                else:
                    self.cap = cv2.VideoCapture(self.source)

                if not self.cap or not self.cap.isOpened():
                    self.connected = False
                    time.sleep(2.0)
                    continue

                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.connected = True

            try:
                ret, frame = self.cap.read()
            except Exception:
                ret, frame = False, None

            if not ret or frame is None:
                self.connected = False
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                self.cap = None
                time.sleep(1.0)
                continue

            self.connected = True
            with self.lock:
                self.latest_frame = frame

    def read(self):
        with self.lock:
            return self.connected, None if self.latest_frame is None else self.latest_frame.copy()

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()


# =========================================================================
#               WORKER POR CÁMARA (Procesamiento Concurrente)
# =========================================================================

class CameraWorker(threading.Thread):
    """Worker independiente para un punto de acceso específico."""
    def __init__(self, config: dict, api_url: str):
        super().__init__(daemon=True)
        self.device_id   = config.get("device_id", "CAM_UNKNOWN")
        self.name        = config.get("name", self.device_id)
        self.source      = config.get("source", 0)
        self.token       = config.get("token", "")
        self.location    = config.get("location", "Borde")
        self.api_url     = api_url

        self.reader      = RTSPCaptureThread(self.source)
        self.running     = True

        # Estado del canal
        self.ear_open_val = 0.32
        self.ear_blink_val = 0.20
        self.pre_blink_buf = deque(maxlen=4)
        self.last_auth_time = 0.0
        self.cooldown = 4.0

        self.status = "MONITORING"  # MONITORING, PROCESSING, GRANTED, DENIED
        self.status_msg = "EN ESPERA"
        self.user_name = ""
        self.user_role = ""
        self.display_frame = None
        self.lock = threading.Lock()

    def run(self):
        self.reader.start()
        
        mp_mesh = mp.solutions.face_mesh
        face_mesh = mp_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.35,
            min_tracking_confidence=0.35
        )

        fsm_state = "OPEN"
        closed_count = 0

        while self.running:
            connected, frame = self.reader.read()
            if not connected or frame is None:
                # Generar imagen de sin señal
                h, w = 360, 480
                no_sig = np.zeros((h, w, 3), dtype=np.uint8)
                cv2.putText(no_sig, f"CONECTANDO: {self.name}", (20, h//2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
                cv2.putText(no_sig, f"[{self.device_id}] {self.source}", (20, h//2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 120), 1)
                with self.lock:
                    self.display_frame = no_sig
                time.sleep(0.1)
                continue

            orig_frame = frame.copy()
            # Reducir resolución para mantener FPS alto en el procesamiento MediaPipe
            if frame.shape[1] > 640:
                frame = cv2.resize(frame, (640, int(frame.shape[0] * 640 / frame.shape[1])))

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            t0_mesh = time.perf_counter()
            results = face_mesh.process(rgb)
            t_ear_ms = (time.perf_counter() - t0_mesh) * 1000.0

            ear_val = 0.0
            face_detected = False
            box = None

            if results.multi_face_landmarks:
                face_detected = True
                lm = results.multi_face_landmarks[0]
                ear_l = eye_aspect_ratio(lm.landmark, LEFT_EYE_IDX, w, h)
                ear_r = eye_aspect_ratio(lm.landmark, RIGHT_EYE_IDX, w, h)
                ear_val = (ear_l + ear_r) / 2.0
                _, box = crop_face(frame, lm, margin_pct=0.20)

                # Máquina de estados de parpadeo adaptativa (guardar fotograma en alta resolución)
                self.pre_blink_buf.append(orig_frame)
                eff_threshold = max(0.16, min(0.24, self.ear_open_val * 0.85))

                now = time.time()
                can_auth = (self.status != "PROCESSING" and (now - self.last_auth_time) > self.cooldown)

                if fsm_state == "OPEN":
                    if ear_val >= eff_threshold:
                        self.ear_open_val = 0.85 * self.ear_open_val + 0.15 * ear_val
                    elif can_auth:
                        fsm_state = "CLOSING"
                        closed_count = 1
                        self.ear_blink_val = ear_val

                elif fsm_state == "CLOSING":
                    if ear_val < eff_threshold:
                        closed_count += 1
                        if ear_val < self.ear_blink_val:
                            self.ear_blink_val = ear_val
                    else:
                        if closed_count >= 1 and can_auth:
                            # Parpadeo completado -> Disparar autenticación con recorte HD
                            auth_frame = self.pre_blink_buf[0] if len(self.pre_blink_buf) > 0 else orig_frame
                            face_crop_img, _ = crop_face(auth_frame, lm, margin_pct=0.35)
                            if face_crop_img is None:
                                face_crop_img = auth_frame

                            self.trigger_auth(face_crop_img, t_ear_ms)
                        fsm_state = "OPEN"
                        closed_count = 0

            # Limpiar estado si expiró el banner de concedido/denegado
            if self.status in ["GRANTED", "DENIED"] and (time.time() - self.last_auth_time) > self.cooldown:
                self.status = "MONITORING"
                self.status_msg = "MONITOREANDO"

            # Renderizar anotaciones en el frame
            display = frame.copy()
            if box and face_detected:
                x1, y1, x2, y2 = box
                color = (0, 255, 0) if self.status == "GRANTED" else ((0, 0, 255) if self.status == "DENIED" else (255, 200, 0))
                cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

            # Barra superior de la cámara
            banner_bg = (20, 20, 20)
            if self.status == "GRANTED":
                banner_bg = (0, 140, 0)
            elif self.status == "DENIED":
                banner_bg = (0, 0, 160)
            elif self.status == "PROCESSING":
                banner_bg = (0, 120, 180)

            cv2.rectangle(display, (0, 0), (w, 55), banner_bg, -1)
            cv2.putText(display, f"[{self.device_id}] {self.name}", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            
            sub_text = f"EAR: {ear_val:.3f} | {self.status_msg}"
            if self.status == "GRANTED":
                sub_text = f"✅ ACCESO: {self.user_name} ({self.user_role})"
            elif self.status == "DENIED":
                sub_text = f"🚫 DENEGADO: {self.status_msg}"

            cv2.putText(display, sub_text, (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

            with self.lock:
                self.display_frame = display

            time.sleep(0.015)

    def trigger_auth(self, face_img, t_ear_ms):
        """Lanza la autenticación M2M al Backend de FastAPI en segundo plano."""
        self.last_auth_time = time.time()
        self.status = "PROCESSING"
        self.status_msg = "AUTENTICANDO..."

        threading.Thread(target=self._send_request, args=(face_img, t_ear_ms), daemon=True).start()

    def _send_request(self, face_img, t_ear_ms):
        try:
            _, buf = cv2.imencode(".jpg", face_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            b64_img = base64.b64encode(buf).decode("utf-8")

            payload = {
                "image_base64": b64_img,
                "test_type": "LIVE_USER",
                "environmental_condition": "NORMAL",
                "edge_ear_time_ms": round(t_ear_ms, 2),
                "edge_total_time_ms": round(t_ear_ms + 2.0, 2),
                "ear_open_value": round(self.ear_open_val, 4),
                "ear_blink_value": round(self.ear_blink_val, 4),
            }

            resp = requests.post(
                self.api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5.0
            )

            if resp.status_code == 200:
                data = resp.json()
                user = data.get("user", {})
                self.user_name = user.get("name", "Usuario")
                self.user_role = user.get("role", "Autorizado")
                self.status = "GRANTED"
                self.status_msg = f"{self.user_name}"
                print(f"🎯 [{self.device_id}] ACCESO CONCEDIDO -> {self.user_name} ({self.user_role})")
            else:
                detail = resp.json().get("detail", "Denegado")
                self.status = "DENIED"
                self.status_msg = detail
                print(f"🚫 [{self.device_id}] ACCESO DENEGADO -> {detail}")

        except Exception as e:
            self.status = "DENIED"
            self.status_msg = "Error Red"
            print(f"⚠️ [{self.device_id}] Error de conexión: {e}")

    def stop(self):
        self.running = False
        self.reader.stop()


# =========================================================================
#            CREACIÓN DE PLANTILLA Y CARGA DE CONFIGURACIÓN
# =========================================================================

def load_or_create_config() -> list:
    paths_to_check = [p for p in [DATA_CONFIG_PATH, ROOT_CONFIG_PATH] if os.path.exists(p) and os.path.getsize(p) > 0]
    
    for path in paths_to_check:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            continue

    # Si ninguno existe o ambos están vacíos/corruptos, regenerar en ambos paths
    sample = [
        {
            "device_id": "PASILLO62",
            "name": "Pasillo 6-2 (Patio B)",
            "token": "hw_zaEy9rg43tK6QZa0e9O_oDE_spala6yRm71hA74ayV8",
            "source": "rtsp://admin1:cimos.1979@192.168.70.10:554/Streaming/Channels/201",
            "location": "Patio B, Pasillo 6-2",
            "enabled": True
        },
        {
            "device_id": "TLFHECTOR",
            "name": "Smart 20 Hector (DroidCam)",
            "token": "hw_tlfhector_secret_key_8832a74ayV8",
            "source": "http://192.168.80.127:4747/video",
            "location": "Punto de Acceso Móvil",
            "enabled": True
        }
    ]
    for p in [DATA_CONFIG_PATH, ROOT_CONFIG_PATH]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(sample, f, indent=4)
        except Exception:
            pass
    print(f"📝 Archivo de configuración generado con 2 cámaras: {ROOT_CONFIG_PATH}")
    return sample


# =========================================================================
#                          LOOP PRINCIPAL (NVR)
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="FaceSentinel Edge Gateway Multi-Cámara")
    parser.add_argument("--headless", action="store_true", help="Ejecutar como demonio sin ventana gráfica (Raspberry Pi/Servidor)")
    args = parser.parse_args()

    print("=" * 70)
    print("    FaceSentinel — Edge Gateway Multi-Cámara Concurrente (NVR)")
    print("=" * 70)
    print(f"📡 Backend FastAPI: {DEFAULT_API_URL}")
    print(f"📁 Configuración:   {CONFIG_PATH}")

    configs = load_or_create_config()
    active_configs = [c for c in configs if c.get("enabled", True)]

    if not active_configs:
        print("❌ No hay cámaras habilitadas en 'cameras.json'.")
        return

    print(f"🚀 Iniciando {len(active_configs)} Workers concurrentes de cámara...")
    workers = []
    for cfg in active_configs:
        worker = CameraWorker(cfg, DEFAULT_API_URL)
        worker.start()
        workers.append(worker)
        print(f"   [+] Worker iniciado para [{cfg.get('device_id')}]: {cfg.get('name')} ({cfg.get('source')})")

    print("\n⌨️  CONTROLES:")
    print("   [ESPACIO] Forzar escaneo en todas las cámaras")
    print("   [Q/ESC]   Detener Gateway y salir")
    print("=" * 70 + "\n")

    if args.headless:
        print("🤖 Modo Headless activo (sin GUI). Presiona Ctrl+C para salir.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
    else:
        cv2.namedWindow("FaceSentinel — Multi-Camera NVR Grid", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("FaceSentinel — Multi-Camera NVR Grid", 1280, 720)

        while True:
            # Ensamblar frames de todas las cámaras activas
            frames = []
            for w in workers:
                with w.lock:
                    if w.display_frame is not None:
                        frames.append(cv2.resize(w.display_frame, (640, 480)))
                    else:
                        blank = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(blank, f"Iniciando {w.name}...", (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
                        frames.append(blank)

            # Crear mosaico visual
            if len(frames) == 1:
                mosaic = frames[0]
            elif len(frames) == 2:
                mosaic = np.hstack((frames[0], frames[1]))
            elif len(frames) <= 4:
                while len(frames) < 4:
                    frames.append(np.zeros((480, 640, 3), dtype=np.uint8))
                row1 = np.hstack((frames[0], frames[1]))
                row2 = np.hstack((frames[2], frames[3]))
                mosaic = np.vstack((row1, row2))
            else:
                # Cuadrícula genérica
                row1 = np.hstack(frames[:len(frames)//2])
                row2 = np.hstack(frames[len(frames)//2:])
                mosaic = np.vstack((row1, row2))

            cv2.imshow("FaceSentinel — Multi-Camera NVR Grid", mosaic)
            key = cv2.waitKey(20) & 0xFF

            if key in [ord('q'), ord('Q'), 27]:
                break
            elif key == 32:  # Barra espaciadora: forzar escaneo
                print("▶️  [ESPACIO] Forzando escaneo en todas las cámaras activas...")
                for w in workers:
                    with w.lock:
                        if w.display_frame is not None:
                            w.trigger_auth(w.display_frame, 2.5)

    print("\n🛑 Deteniendo Workers de cámaras...")
    for w in workers:
        w.stop()
    cv2.destroyAllWindows()
    print("👋 Edge Gateway Multi-Cámara cerrado correctamente.\n")

if __name__ == "__main__":
    main()
