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

WEBCAM_INDEX    = 0       # Índice de la cámara
FRAME_WIDTH     = 480     # Resolución reducida → <65% CPU en RPi 4
FRAME_HEIGHT    = 360
COOLDOWN_TIME   = 4.0     # Segundos de espera post-envío (anti-spam)
STATUS_DURATION = 3.5     # Cuánto tiempo se mantiene el resultado en pantalla
MARGIN_PCT      = 0.15    # Margen alrededor del rostro para el recorte final

# -- Parámetros de la máquina de estados EAR --
EAR_THRESHOLD   = 0.20    # Ratio debajo del cual el ojo se considera "cerrado"
CONSEC_FRAMES   = 2       # Frames consecutivos bajo umbral para confirmar cierre
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

    def update(self, ear: float, frame_bgr) -> bool:
        """
        Actualiza la FSM con el EAR del frame actual y el frame BGR.
        Retorna True exactamente una vez: cuando se completa un parpadeo.
        """
        # Acumular frames antes del cierre (buffer circular)
        self.pre_blink_buf.append(frame_bgr.copy())

        if self.state == self.OPEN:
            if ear < EAR_THRESHOLD:
                self.state        = self.CLOSING
                self.closed_count = 1

        elif self.state == self.CLOSING:
            if ear < EAR_THRESHOLD:
                self.closed_count += 1
            else:
                if self.closed_count >= CONSEC_FRAMES:
                    # Parpadeo confirmado — tomar frame pre-cierre (ojos abiertos)
                    self.capture_frame = self.pre_blink_buf[0]
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

def send_auth_request(base64_img: str, callbacks: dict):
    """
    Ejecutado en hilo secundario para no bloquear el loop de captura.
    Llama al endpoint M2M y actualiza el estado compartido via callbacks.
    """
    try:
        response = requests.post(
            API_URL,
            json={"image_base64": base64_img},
            headers={
                "Authorization": f"Bearer {DEVICE_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=(3, 10),   # (connect_timeout, read_timeout)
        )
        data = response.json()

        if response.status_code == 200 and data.get("authorization") == "GRANTED":
            user  = data.get("user", {})
            name  = user.get("name", "Desconocido")
            role  = user.get("role", "Usuario")
            print(f"✅ [GRANTED] Bienvenido/a {name} ({role})")
            print(f"🔗 TX Blockchain: {data.get('blockchain_tx')}")
            print("🚪 >>> SIMULACIÓN: Abriendo Puerta / Activando Relé GPIO <<<")
            callbacks["on_granted"](name, role)
        else:
            detail = data.get("detail", "No autorizado")
            print(f"❌ [DENIED] {detail}")
            callbacks["on_denied"](detail)

    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error de red: {e}")
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
    print("ℹ️  Mira la cámara y parpadea para autenticarte.")
    print("ℹ️  Presiona 'q' o ESC para salir.")
    print("=========================================================================\n")

    cap = cv2.VideoCapture(WEBCAM_INDEX)
    if not cap.isOpened():
        print(f"❌ Error: No se pudo acceder a la webcam #{WEBCAM_INDEX}.")
        return

    # Reducir resolución → menor CPU en dispositivo de borde
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    # Estado compartido entre hilo principal e hilo HTTP (protegido por lock)
    state = {
        "auth_status"    : None,
        "status_msg"     : "PARPADEA PARA AUTENTICARTE",
        "user_info"      : "",
        "last_auth_time" : 0.0,
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
            print("⚠️ Frame vacío — reintentando...")
            continue

        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        now   = time.time()

        # Leer estado de forma segura
        with state_lock:
            auth_status = state["auth_status"]
            status_msg  = state["status_msg"]
            user_info   = state["user_info"]
            last_auth   = state["last_auth_time"]

        # Limpiar estado expirado
        if auth_status in ("GRANTED", "DENIED") and (now - last_auth > STATUS_DURATION):
            with state_lock:
                state["auth_status"] = None
                state["status_msg"]  = "PARPADEA PARA AUTENTICARTE"
                state["user_info"]   = ""
            blink_fsm.reset()
            auth_status = None

        # ----------------------------------------------------------------
        # Face Mesh + cálculo EAR
        # ----------------------------------------------------------------
        mesh_results  = face_mesh.process(rgb)
        face_in_frame = False
        ear_value     = 0.0
        box_coords    = None

        if mesh_results.multi_face_landmarks:
            face_lm       = mesh_results.multi_face_landmarks[0]
            face_in_frame = True
            ear_value     = get_avg_ear(face_lm)
            _, box_coords = crop_face_from_mesh(frame, face_lm)

            # Actualizar FSM solo cuando no estamos en cooldown ni procesando
            can_auth = (
                auth_status is None
                and (now - last_auth) > COOLDOWN_TIME
            )

            if can_auth and blink_fsm.state != BlinkStateMachine.BLINKED:
                blinked = blink_fsm.update(ear_value, frame)

                if blinked and blink_fsm.capture_frame is not None:
                    # Extraer rostro del frame pre-parpadeo (ojos abiertos)
                    face_crop, _ = crop_face_from_mesh(blink_fsm.capture_frame, face_lm)
                    if face_crop is None:
                        face_crop = blink_fsm.capture_frame  # Fallback: frame completo

                    if face_crop.size > 0:
                        # Marcar cooldown ANTES de lanzar el hilo (evita doble envío)
                        with state_lock:
                            state["auth_status"]    = "PROCESSING"
                            state["status_msg"]     = "PROCESANDO..."
                            state["last_auth_time"] = now
                        last_auth = now

                        _, buf  = cv2.imencode(".jpg", face_crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        b64_img = base64.b64encode(buf).decode("utf-8")

                        print(f"\n👁️  Parpadeo detectado (EAR={ear_value:.3f}). Enviando autenticación...")

                        threading.Thread(
                            target=send_auth_request,
                            args=(b64_img, {
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

        # Bounding box del rostro
        if box_coords:
            x1, y1, x2, y2 = box_coords
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, f"EAR: {ear_value:.3f}", (x1, max(y1 - 8, 66)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1, cv2.LINE_AA)

        # Barra de cooldown (parte inferior)
        cooldown_left = max(0.0, COOLDOWN_TIME - (now - last_auth))
        if cooldown_left > 0 and auth_status not in (None,):
            bar_w = int((cooldown_left / COOLDOWN_TIME) * w)
            cv2.rectangle(frame, (0, h - 8), (bar_w, h), (0, 165, 255), -1)
            cv2.putText(frame, f"Cooldown: {cooldown_left:.1f}s", (8, h - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)

        # Estado FSM (debug)
        fsm_txt = f"FSM: {blink_fsm.state}  frames={blink_fsm.closed_count}"
        cv2.putText(frame, fsm_txt, (8, h - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1, cv2.LINE_AA)

        cv2.imshow("FaceSentinel Edge Gateway", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            break

    # Liberar recursos
    cap.release()
    face_mesh.close()
    cv2.destroyAllWindows()
    print("\n👋 Edge Gateway cerrado correctamente.")


if __name__ == "__main__":
    main()
