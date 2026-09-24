#!/usr/bin/env python3
"""
edge_gateway.py — Edge Gateway con Liveness Híbrido para FaceSentinel
Implementa detección de parpadeo (EAR) localmente via MediaPipe Face Mesh.
Solo envía UN fotograma al servidor cuando detecta un parpadeo humano válido,
reduciendo el tráfico de red ~85-95% frente al envío de video continuo.

Flujo M2M:
  Cámara → Face Mesh → EAR → Máquina de estados de parpadeo
  → Fotograma capturado → Base64 → POST /api/v1/physical-access/authenticate
"""

import os
import math
import cv2
import mediapipe as mp
import requests
import base64
import time
import threading
from collections import deque

# =========================================================================
#                     CONFIGURACIONES DEL GATEWAY
# =========================================================================
API_URL = os.environ.get(
    "FACESENTINEL_M2M_URL",
    "http://localhost:8000/api/v1/physical-access/authenticate"
)
DEVICE_TOKEN = os.environ.get("HW_CLIENT_SECRET")
if not DEVICE_TOKEN:
    raise RuntimeError(
        "❌ Variable de entorno HW_CLIENT_SECRET no configurada. "
        "Establécela antes de ejecutar el gateway.\n"
        "Ejemplo: set HW_CLIENT_SECRET=hw_xxxxx"
    )

DEFAULT_RTSP_URL = "rtsp://admin1:cimos.1979@192.168.70.10:554/Streaming/Channels/201"
_raw_src = os.environ.get("FACESENTINEL_VIDEO_SOURCE", os.environ.get("FACESENTINEL_WEBCAM_INDEX", DEFAULT_RTSP_URL))
try:
    WEBCAM_SOURCE = int(_raw_src)
except ValueError:
    WEBCAM_SOURCE = _raw_src

FRAME_WIDTH     = 480     # Resolución reducida → <65% CPU en RPi 4
FRAME_HEIGHT    = 360
COOLDOWN_TIME   = 4.0     # Segundos de espera post-envío (anti-spam)
STATUS_DURATION = 3.5     # Cuánto tiempo se mantiene el resultado en pantalla
MARGIN_PCT      = 0.15    # Margen alrededor del rostro para el recorte final

# -- Parámetros de la máquina de estados EAR --
EAR_THRESHOLD   = float(os.environ.get("FACESENTINEL_EAR_THRESHOLD", "0.24"))  # Ratio de cierre (configurable)
CONSEC_FRAMES   = 1       # Frames bajo umbral para confirmar (ideal para streams WiFi / DroidCam)
PRE_BLINK_BUF   = 5       # Tamaño del buffer de frames anteriores al cierre
                          # El frame capturado vendrá de AQUÍ (ojos abiertos y estables)

# Landmarks MediaPipe para EAR (6 puntos por ojo)
LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# =========================================================================
#             INICIALIZACIÓN DE MEDIAPIPE FACE MESH (Edge-optimized)
# =========================================================================
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=False,   # Ahorra ~30% CPU vs True; suficiente para EAR
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    static_image_mode=False   # Modo tracking: más rápido que re-detectar cada frame
)

# =========================================================================
#                     FUNCIONES DE CÁLCULO EAR
# =========================================================================

def _euclidean(p1, p2) -> float:
    """Distancia euclidiana 2D entre dos landmarks de MediaPipe."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def compute_ear(landmarks, eye_indices: list) -> float:
    """
    Eye Aspect Ratio (Soukupová & Čech, 2016).
    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    Cae a ~0.0 cuando el ojo se cierra. Valor normal: 0.25–0.35.
    """
    p1, p2, p3, p4, p5, p6 = [landmarks.landmark[i] for i in eye_indices]
    v1 = _euclidean(p2, p6)
    v2 = _euclidean(p3, p5)
    h  = _euclidean(p1, p4)
    return (v1 + v2) / (2.0 * h + 1e-7)


def get_avg_ear(face_landmarks) -> float:
    """Promedio EAR de ambos ojos."""
    left  = compute_ear(face_landmarks, LEFT_EYE)
    right = compute_ear(face_landmarks, RIGHT_EYE)
    return (left + right) / 2.0


# =========================================================================
#           MÁQUINA DE ESTADOS: DETECCIÓN DE PARPADEO
# =========================================================================

class BlinkStateMachine:
    """
    Detecta un parpadeo humano completo (ojos abiertos → cerrados → abiertos).

    Estados:
        OPEN      → ojos abiertos (estado normal)
        CLOSING   → EAR cayó bajo umbral; contando frames cerrados
        BLINKED   → parpadeo completo detectado (estado terminal hasta reset)

    El fotograma de autenticación se extrae del buffer PRE_BLINK
    (frames con ojos bien abiertos capturados ANTES del cierre),
    evitando enviar frames de párpados a medio cerrar.
    """

    OPEN    = "OPEN"
    CLOSING = "CLOSING"
    BLINKED = "BLINKED"

    def __init__(self):
        self.state         = self.OPEN
        self.closed_count  = 0
        self.pre_blink_buf = deque(maxlen=PRE_BLINK_BUF)
        self.capture_frame = None
        self.ear_open_val  = 0.30
        self.ear_blink_val = 0.20

    def update(self, ear: float, frame_bgr, face_crop=None) -> bool:
        """
        Actualiza la FSM con el EAR del frame actual, el frame BGR y el recorte del rostro.
        Retorna True exactamente una vez: cuando se completa un parpadeo.
        """
        # Umbral adaptativo según la anatomía ocular del usuario
        effective_threshold = max(0.16, min(EAR_THRESHOLD, self.ear_open_val * 0.85))

        if self.state == self.OPEN:
            if ear >= effective_threshold:
                self.ear_open_val = 0.85 * self.ear_open_val + 0.15 * ear
                # Acumular recorte de rostro óptimo con ojos abiertos
                if face_crop is not None and getattr(face_crop, "size", 0) > 0:
                    self.pre_blink_buf.append(face_crop.copy())
                else:
                    self.pre_blink_buf.append(frame_bgr.copy())
            else:
                self.state        = self.CLOSING
                self.closed_count = 1
                self.ear_blink_val = ear

        elif self.state == self.CLOSING:
            if ear < effective_threshold:
                self.closed_count += 1
                if ear < self.ear_blink_val:
                    self.ear_blink_val = ear
            else:
                if self.closed_count >= CONSEC_FRAMES:
                    # Parpadeo confirmado — tomar recorte pre-cierre (ojos bien abiertos)
                    self.capture_frame = self.pre_blink_buf[0] if len(self.pre_blink_buf) > 0 else frame_bgr
                    self.state         = self.BLINKED
                    return True
                else:
                    # Micro-movimiento, no parpadeo real → volver a OPEN
                    self.state        = self.OPEN
                    self.closed_count = 0

        return False

    def reset(self):
        self.state         = self.OPEN
        self.closed_count  = 0
        self.capture_frame = None
        self.pre_blink_buf.clear()


# =========================================================================
#                     FUNCIÓN DE RECORTE DE ROSTRO
# =========================================================================

def crop_face_from_mesh(frame_bgr, face_landmarks) -> tuple:
    """
    Deriva una bounding box del rostro a partir de los landmarks de Face Mesh
    y recorta el rostro con un margen de seguridad.
    Retorna (face_crop_bgr, (x1, y1, x2, y2)) o (None, None) si falla.
    """
    h, w = frame_bgr.shape[:2]
    xs = [lm.x * w for lm in face_landmarks.landmark]
    ys = [lm.y * h for lm in face_landmarks.landmark]

    x_min, x_max = int(min(xs)), int(max(xs))
    y_min, y_max = int(min(ys)), int(max(ys))

    margin_x = int((x_max - x_min) * MARGIN_PCT)
    margin_y = int((y_max - y_min) * MARGIN_PCT)

    x1 = max(0, x_min - margin_x)
    y1 = max(0, y_min - margin_y)
    x2 = min(w, x_max + margin_x)
    y2 = min(h, y_max + margin_y)

    crop = frame_bgr[y1:y2, x1:x2]
    return (crop, (x1, y1, x2, y2)) if crop.size > 0 else (None, None)


# =========================================================================
#                     ENVÍO AL BACKEND (hilo secundario)
# =========================================================================

def send_auth_request(base64_img: str, telemetry: dict, callbacks: dict):
    """
    Ejecutado en hilo secundario para no bloquear el loop de captura.
    Mide la latencia de red de ida y vuelta (RTT) y muestra las métricas de tesis.
    """
    t_http_start = time.perf_counter()
    try:
        payload = {
            "image_base64": base64_img,
            "test_type": telemetry.get("test_type", "LIVE_USER"),
            "environmental_condition": telemetry.get("environmental_condition", "NORMAL"),
            "edge_ear_time_ms": telemetry.get("edge_ear_time_ms", 0.0),
            "edge_total_time_ms": telemetry.get("edge_total_time_ms", 0.0),
            "ear_open_value": telemetry.get("ear_open_value", 0.0),
            "ear_blink_value": telemetry.get("ear_blink_value", 0.0),
        }

        response = requests.post(
            API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {DEVICE_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=(3, 10),   # (connect_timeout, read_timeout)
        )
        t_http_end = time.perf_counter()
        t_http_total_ms = (t_http_end - t_http_start) * 1000.0

        data = response.json()
        server_timings = data.get("timings", {})
        t_backend_ms = server_timings.get("t_backend_total_ms", 0.0)
        t_network_rtt_ms = max(0.0, t_http_total_ms - t_backend_ms)
        t_total_end2end = telemetry.get("edge_total_time_ms", 0.0) + t_http_total_ms

        liveness_data = data.get("liveness", {})
        bio_data = data.get("biometrics", {})

        print("\n" + "=" * 65)
        print("          📊 [FACE-SENTINEL TELEMETRÍA EXPERIMENTAL]")
        print("=" * 65)
        print(f" 🧪 Prueba: {payload['test_type']} | Entorno: {payload['environmental_condition']}")
        print(f" ⏱️  Latencia Borde (MediaPipe EAR): {telemetry.get('edge_ear_time_ms', 0.0):.1f} ms | Total Borde: {telemetry.get('edge_total_time_ms', 0.0):.1f} ms")
        print(f" 🌐 Latencia Red (Transit RTT):     {t_network_rtt_ms:.1f} ms (HTTP Total: {t_http_total_ms:.1f} ms)")
        if server_timings:
            print(f" 🖥️  Latencia Backend (FastAPI):    {t_backend_ms:.1f} ms")
            print(f"     ├─ LBP Textura:   {server_timings.get('t_lbp_ms', 0.0):.1f} ms")
            print(f"     ├─ FFT Espectro:  {server_timings.get('t_fft_ms', 0.0):.1f} ms")
            print(f"     ├─ ArcFace 512d:  {server_timings.get('t_arcface_ms', 0.0):.1f} ms")
            print(f"     ├─ ChromaDB Match:{server_timings.get('t_chroma_ms', 0.0):.1f} ms")
            print(f"     └─ SQLite ACL:    {server_timings.get('t_sqlite_ms', 0.0):.1f} ms")
        print(f" ⚡ Latencia Total End-to-End:      {t_total_end2end:.1f} ms {'(Óptima <500ms ✅)' if t_total_end2end < 500 else '(⚠️ Elevada)'}")
        print(f" 👁️  EAR Ojos Abiertos: {telemetry.get('ear_open_value', 0.0):.3f} | EAR Parpadeo: {telemetry.get('ear_blink_value', 0.0):.3f}")
        if liveness_data:
            print(f" 🛡️  Liveness Score: {liveness_data.get('score', 0.0):.4f} | Entropía LBP: {liveness_data.get('entropy', 0.0):.4f} (Umbral: {liveness_data.get('lbp_threshold', 3.2):.2f})")
        if bio_data:
            print(f" 🧬 Distancia Coseno: {bio_data.get('distance', 0.0):.4f} (Umbral Match: {bio_data.get('threshold', 0.68):.2f})")

        if response.status_code == 200 and data.get("authorization") == "GRANTED":
            user  = data.get("user", {})
            name  = user.get("name", "Desconocido")
            role  = user.get("role", "Usuario")
            print(f" 🔗 Blockchain TX: {data.get('blockchain_tx')}")
            print(f" 🎯 Resultado: ACCESO CONCEDIDO -> Bienvenido/a {name} ({role})")
            print("=" * 65 + "\n")
            callbacks["on_granted"](name, role)
        else:
            detail = data.get("detail", "No autorizado")
            print(f" 🚫 Resultado: ACCESO DENEGADO -> {detail}")
            print("=" * 65 + "\n")
            callbacks["on_denied"](detail)

    except requests.exceptions.RequestException as e:
        print(f"\n⚠️ Error de red durante la autenticación: {e}\n")
        callbacks["on_error"](str(e))


# =========================================================================
#                           LOOP PRINCIPAL
# =========================================================================

def main():
    print("=========================================================================")
    print("        FaceSentinel — Edge Gateway con Liveness Híbrido (EAR)           ")
    print("=========================================================================")
    print(f"📡 Backend: {API_URL}")
    token_preview = f"{DEVICE_TOKEN[:4]}...{DEVICE_TOKEN[-4:]}" if len(DEVICE_TOKEN) > 8 else "****"
    print(f"🔑 Token: {token_preview}")
    print("\n⌨️  CONTROLES DE EXPERIMENTO:")
    print("   [1] Modo LIVE_USER (Sujeto real)")
    print("   [2] Modo SPOOF_PHOTO_PRINT (Foto impresa)")
    print("   [3] Modo SPOOF_SCREEN_VIDEO (Pantalla celular)")
    print("   [N] Luz NORMAL | [H] Contraluz/HIGH_LIGHT | [L] Baja luz/LOW_LIGHT")
    print("   [Q/ESC] Salir")
    print("=========================================================================\n")

    # Intentar abrir la fuente de video (cámara, IP cam o archivo)
    cap = None
    if isinstance(WEBCAM_SOURCE, int):
        cap = cv2.VideoCapture(WEBCAM_SOURCE, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(WEBCAM_SOURCE)
    else:
        cap = cv2.VideoCapture(WEBCAM_SOURCE)

    if not cap or not cap.isOpened():
        print(f"❌ Error: No se pudo acceder a la fuente de video: '{WEBCAM_SOURCE}'.")
        print("\n💡 Diagnóstico y Soluciones:")
        print("   1. Conecta tu cámara web USB o verifica que el cable esté firme.")
        print("   2. Revisa que ninguna otra aplicación (ej. el navegador web o Zoom) esté usando la cámara.")
        print("   3. Si tu laptop tiene tecla de privacidad (Fn+F6, Fn+F10 o switch físico), actívalo.")
        print("   4. Alternativa con Smartphone (DroidCam / Iriun Webcam):")
        print("      $env:FACESENTINEL_VIDEO_SOURCE = 'http://192.168.1.X:4747/video'")
        print("   5. Alternativa con video pregrabado (MP4):")
        print("      $env:FACESENTINEL_VIDEO_SOURCE = 'video_prueba.mp4'")
        return

    # Reducir resolución → menor CPU en dispositivo de borde
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    # Estado compartido entre hilo principal e hilo HTTP (protegido por lock)
    state = {
        "auth_status"            : None,
        "status_msg"             : "PARPADEA O PULSA [ESPACIO]",
        "user_info"              : "",
        "last_auth_time"         : 0.0,
        "test_type"              : "LIVE_USER",
        "environmental_condition": "NORMAL",
    }
    state_lock = threading.Lock()

    def on_granted(name, role):
        with state_lock:
            state["auth_status"] = "GRANTED"
            state["status_msg"]  = "ACCESO CONCEDIDO"
            state["user_info"]   = f"{name}  |  {role}"

    def on_denied(detail):
        with state_lock:
            state["auth_status"] = "DENIED"
            state["status_msg"]  = "ACCESO DENEGADO"
            state["user_info"]   = detail[:60]

    def on_error(msg):
        with state_lock:
            state["auth_status"] = "DENIED"
            state["status_msg"]  = "ERROR DE CONEXIÓN"
            state["user_info"]   = "Servidor no responde"

    blink_fsm = BlinkStateMachine()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            if isinstance(WEBCAM_SOURCE, str) and not (str(WEBCAM_SOURCE).startswith("http") or str(WEBCAM_SOURCE).startswith("rtsp")):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            print("⚠️ Frame vacío o reconectando flujo de red...")
            time.sleep(0.05)
            continue

        # Si es cámara web USB física, reflejar en modo selfie; si es cámara IP/RTSP, mantener vista real
        if isinstance(WEBCAM_SOURCE, int):
            frame = cv2.flip(frame, 1)

        # Optimizar resolución para MediaPipe y tiempo real si la cámara transmite en alta definición (ej. 1440x1280)
        h_orig, w_orig = frame.shape[:2]
        if w_orig > 640:
            scale = 640.0 / w_orig
            frame = cv2.resize(frame, (640, int(h_orig * scale)))

        h, w  = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        now   = time.time()

        # Leer estado de forma segura
        with state_lock:
            auth_status = state["auth_status"]
            status_msg  = state["status_msg"]
            user_info   = state["user_info"]
            last_auth   = state["last_auth_time"]
            curr_test_type = state["test_type"]
            curr_env_cond  = state["environmental_condition"]

        # Limpiar estado expirado
        if auth_status in ("GRANTED", "DENIED") and (now - last_auth > STATUS_DURATION):
            with state_lock:
                state["auth_status"] = None
                state["status_msg"]  = "PARPADEA O PULSA [ESPACIO]"
                state["user_info"]   = ""
            blink_fsm.reset()
            auth_status = None

        # ----------------------------------------------------------------
        # Face Mesh + cálculo EAR con medición de tiempo
        # ----------------------------------------------------------------
        t0_mesh = time.perf_counter()
        mesh_results  = face_mesh.process(rgb)
        t_ear_edge_ms = (time.perf_counter() - t0_mesh) * 1000.0

        face_in_frame = False
        ear_value     = 0.0
        box_coords    = None

        if mesh_results.multi_face_landmarks:
            face_lm       = mesh_results.multi_face_landmarks[0]
            face_in_frame = True
            ear_value     = get_avg_ear(face_lm)
            curr_crop, box_coords = crop_face_from_mesh(frame, face_lm)

            # Actualizar FSM solo cuando no estamos en cooldown ni procesando
            can_auth = (
                auth_status is None
                and (now - last_auth) > COOLDOWN_TIME
            )

            if can_auth and blink_fsm.state != BlinkStateMachine.BLINKED:
                t0_edge_total = time.perf_counter()
                blinked = blink_fsm.update(ear_value, frame, curr_crop)

                if blinked and blink_fsm.capture_frame is not None:
                    # El frame pre-parpadeo ya contiene el rostro nítido con ojos abiertos
                    face_crop = blink_fsm.capture_frame
                    if face_crop is None or getattr(face_crop, "size", 0) == 0:
                        face_crop = curr_crop if curr_crop is not None else frame

                    if face_crop.size > 0:
                        # Marcar cooldown ANTES de lanzar el hilo (evita doble envío)
                        with state_lock:
                            state["auth_status"]    = "PROCESSING"
                            state["status_msg"]     = "PROCESANDO..."
                            state["last_auth_time"] = now
                        last_auth = now

                        _, buf  = cv2.imencode(".jpg", face_crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        b64_img = base64.b64encode(buf).decode("utf-8")
                        t_edge_total_ms = (time.perf_counter() - t0_edge_total) * 1000.0

                        print(f"\n👁️  Parpadeo detectado (EAR={ear_value:.3f}). Enviando autenticación M2M...")

                        telemetry_payload = {
                            "test_type": curr_test_type,
                            "environmental_condition": curr_env_cond,
                            "edge_ear_time_ms": round(t_ear_edge_ms, 2),
                            "edge_total_time_ms": round(t_edge_total_ms, 2),
                            "ear_open_value": round(blink_fsm.ear_open_val, 4),
                            "ear_blink_value": round(blink_fsm.ear_blink_val, 4),
                        }

                        threading.Thread(
                            target=send_auth_request,
                            args=(b64_img, telemetry_payload, {
                                "on_granted": on_granted,
                                "on_denied" : on_denied,
                                "on_error"  : on_error,
                            }),
                            daemon=True
                        ).start()

        # Sin cara → resetear FSM
        if not face_in_frame:
            blink_fsm.reset()

        # ----------------------------------------------------------------
        # Interfaz en pantalla (OSD)
        # ----------------------------------------------------------------
        COLORS = {
            "GRANTED"    : (0, 200, 0),
            "DENIED"     : (0, 0, 220),
            "PROCESSING" : (0, 200, 220),
            None         : (30, 30, 30),
        }
        overlay_color = COLORS.get(auth_status, COLORS[None])
        box_color     = COLORS.get(auth_status, (200, 120, 0))

        # Franja de estado superior
        cv2.rectangle(frame, (0, 0), (w, 58), overlay_color, -1)
        cv2.putText(frame, status_msg, (16, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
        if user_info:
            cv2.putText(frame, user_info, (16, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

        # Franja de metadata experimental en la parte superior (bajo header)
        exp_tag = f"EXP: {curr_test_type} | ENV: {curr_env_cond}"
        cv2.putText(frame, exp_tag, (16, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

        # Bounding box del rostro
        if box_coords:
            x1, y1, x2, y2 = box_coords
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, f"EAR: {ear_value:.3f} ({t_ear_edge_ms:.0f}ms)", (x1, max(y1 - 8, 85)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 1, cv2.LINE_AA)

        # Barra de cooldown (parte inferior)
        cooldown_left = max(0.0, COOLDOWN_TIME - (now - last_auth))
        if cooldown_left > 0 and auth_status not in (None,):
            bar_w = int((cooldown_left / COOLDOWN_TIME) * w)
            cv2.rectangle(frame, (0, h - 8), (bar_w, h), (0, 165, 255), -1)
            cv2.putText(frame, f"Cooldown: {cooldown_left:.1f}s", (8, h - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)

        # Estado FSM (debug)
        fsm_txt = f"FSM: {blink_fsm.state}  frames={blink_fsm.closed_count}  [1,2,3/N,H,L]"
        cv2.putText(frame, fsm_txt, (8, h - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1, cv2.LINE_AA)

        cv2.imshow("FaceSentinel Edge Gateway", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            break
        elif key == 32:  # Barra espaciadora: Disparo manual inmediato
            if face_in_frame:
                t0_edge_total = time.perf_counter()
                face_crop, _ = crop_face_from_mesh(frame, face_lm)
                if face_crop is None:
                    face_crop = frame

                if face_crop.size > 0:
                    with state_lock:
                        state["auth_status"]    = "PROCESSING"
                        state["status_msg"]     = "PROCESANDO (MANUAL)..."
                        state["last_auth_time"] = now
                    last_auth = now

                    _, buf  = cv2.imencode(".jpg", face_crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    b64_img = base64.b64encode(buf).decode("utf-8")
                    t_edge_total_ms = (time.perf_counter() - t0_edge_total) * 1000.0

                    print(f"\n⚡ Disparo manual activado con [ESPACIO] (EAR={ear_value:.3f}). Enviando a FaceSentinel...")

                    telemetry_payload = {
                        "test_type": curr_test_type,
                        "environmental_condition": curr_env_cond,
                        "edge_ear_time_ms": round(t_ear_edge_ms, 2),
                        "edge_total_time_ms": round(t_edge_total_ms, 2),
                        "ear_open_value": round(ear_value, 4),
                        "ear_blink_value": round(ear_value, 4),
                    }

                    threading.Thread(
                        target=send_auth_request,
                        args=(b64_img, telemetry_payload, {
                            "on_granted": on_granted,
                            "on_denied" : on_denied,
                            "on_error"  : on_error,
                        }),
                        daemon=True
                    ).start()
            else:
                print("⚠️ [ESPACIO]: No se detecta ningún rostro en este fotograma.")
        elif key == ord("1"):
            with state_lock:
                state["test_type"] = "LIVE_USER"
            print("🧪 Modo cambiado a: LIVE_USER")
        elif key == ord("2"):
            with state_lock:
                state["test_type"] = "SPOOF_PHOTO_PRINT"
            print("🧪 Modo cambiado a: SPOOF_PHOTO_PRINT (Foto en papel)")
        elif key == ord("3"):
            with state_lock:
                state["test_type"] = "SPOOF_SCREEN_VIDEO"
            print("🧪 Modo cambiado a: SPOOF_SCREEN_VIDEO (Pantalla digital)")
        elif key in (ord("n"), ord("N")):
            with state_lock:
                state["environmental_condition"] = "NORMAL"
            print("💡 Entorno cambiado a: NORMAL")
        elif key in (ord("h"), ord("H")):
            with state_lock:
                state["environmental_condition"] = "HIGH_LIGHT"
            print("💡 Entorno cambiado a: HIGH_LIGHT (Contraluz / Alta iluminación)")
        elif key in (ord("l"), ord("L")):
            with state_lock:
                state["environmental_condition"] = "LOW_LIGHT"
            print("💡 Entorno cambiado a: LOW_LIGHT (Baja iluminación)")

    # Liberar recursos
    cap.release()
    face_mesh.close()
    cv2.destroyAllWindows()
    print("\n👋 Edge Gateway cerrado correctamente.")


if __name__ == "__main__":
    main()
