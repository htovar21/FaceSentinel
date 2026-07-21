#!/usr/bin/env python3
"""
edge_gateway.py — Standalone Client for FaceSentinel Physical Access Control
Simulates the physical edge gateway connected to the access door.
Captures webcam, detects face, crops it with MediaPipe, and calls the FastAPI M2M authentication endpoint.
"""

import os
import cv2
import mediapipe as mp
import requests
import base64
import time
import threading

# =========================================================================
#                     CONFIGURACIONES DEL GATEWAY
# =========================================================================
API_URL = os.environ.get("FACESENTINEL_M2M_URL", "http://localhost:8000/api/v1/physical-access/authenticate")
DEVICE_TOKEN = os.environ.get("HW_CLIENT_SECRET", "hw_Y1lW8PS-T1B6q1GhV4Iw5XroMtSjkv2XTpxEVf0NvtY")

WEBCAM_INDEX = 0             # Índice de la cámara
MIN_DETECTION_CONF = 0.6      # Umbral de confianza de detección de MediaPipe (evita falsos positivos como manos)
COOLDOWN_TIME = 3.0          # Segundos de espera entre intentos de autenticación
MARGIN_PERCENTAGE = 0.15      # Margen alrededor del rostro recortado (15%)

# =========================================================================
#                     INICIALIZACIÓN DE MEDIAPIPE
# =========================================================================
mp_face_detection = mp.solutions.face_detection
face_detector = mp_face_detection.FaceDetection(
    model_selection=0,        # 0 = Rostros dentro de 2 metros (control de acceso)
    min_detection_confidence=MIN_DETECTION_CONF
)

def crop_face(image, bbox):
    """
    Recorta el rostro detectado de la imagen original aplicando un margen de seguridad.
    """
    h, w, _ = image.shape
    xmin = int(bbox.xmin * w)
    ymin = int(bbox.ymin * h)
    width = int(bbox.width * w)
    height = int(bbox.height * h)

    # Añadir margen de recorte
    margin_x = int(width * MARGIN_PERCENTAGE)
    margin_y = int(height * MARGIN_PERCENTAGE)

    x1 = max(0, xmin - margin_x)
    y1 = max(0, ymin - margin_y)
    x2 = min(w, xmin + width + margin_x)
    y2 = min(h, ymin + height + margin_y)

    return image[y1:y2, x1:x2], (x1, y1, x2, y2)

def main():
    print("=========================================================================")
    print("                FaceSentinel - Edge Gateway Simulador                    ")
    print("=========================================================================")
    print(f"📡 Conectando a Backend: {API_URL}")
    print(f"🔑 Secret Token: {DEVICE_TOKEN[:4]}...{DEVICE_TOKEN[-4:] if len(DEVICE_TOKEN) > 8 else ''}")
    print("ℹ️ Presiona 'q' en la ventana de video para salir.")
    print("=========================================================================")

    # Iniciar captura de video
    cap = cv2.VideoCapture(WEBCAM_INDEX)
    if not cap.isOpened():
        print(f"❌ Error: No se pudo acceder a la webcam con índice {WEBCAM_INDEX}.")
        return

    last_auth_time = 0
    auth_status = None         # "GRANTED", "DENIED", "PROCESSING", o None
    status_msg = "ESPERANDO ROSTRO..."
    user_info = ""
    status_duration = 2.0      # Cuánto tiempo mantener el mensaje/color en pantalla

    def perform_auth(base64_img, score):
        nonlocal auth_status, status_msg, user_info, last_auth_time
        try:
            print(f"\n🔍 Rostro detectado (Confianza: {score:.2f}). Enviando solicitud de autenticación...")
            response = requests.post(API_URL, json={"image_base64": base64_img}, headers={
                "Authorization": f"Bearer {DEVICE_TOKEN}",
                "Content-Type": "application/json"
            }, timeout=5)
            
            response_data = response.json()
            last_auth_time = time.time()

            if response.status_code == 200 and response_data.get("authorization") == "GRANTED":
                auth_status = "GRANTED"
                user_data = response_data.get("user", {})
                name = user_data.get("name", "Desconocido")
                role = user_data.get("role", "Usuario")
                status_msg = "ACCESO CONCEDIDO"
                user_info = f"{name} ({role})"
                
                print(f"✅ [GRANTED] Acceso Autorizado. Bienvenido/a {name} ({role})")
                print(f"🔗 TX Blockchain: {response_data.get('blockchain_tx')}")
                print("🚪 >>> SIMULACIÓN: Abriendo Puerta / Activando Relé GPIO <<<")
            else:
                auth_status = "DENIED"
                detail = response_data.get("detail", "No autorizado")
                status_msg = "ACCESO DENEGADO"
                user_info = f"Motivo: {detail}"
                print(f"❌ [DENIED] Acceso Denegado. Detalle: {detail}")

        except requests.exceptions.RequestException as e:
            last_auth_time = time.time()
            auth_status = "DENIED"
            status_msg = "ERROR DE CONEXION"
            user_info = "Servidor no responde"
            print(f"⚠️ Error de red/conexión con el servidor: {e}")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Error: Frame vacío recibido de la webcam.")
            break

        # Espejar la imagen para que sea más natural interactuar
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        # Convertir a RGB para que MediaPipe lo procese
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detector.process(rgb_frame)

        current_time = time.time()
        face_detected_this_frame = False

        # Si el status expiró, limpiarlo a su valor por defecto
        if auth_status in ["GRANTED", "DENIED"] and (current_time - last_auth_time > status_duration):
            auth_status = None
            status_msg = "ESPERANDO ROSTRO..."
            user_info = ""

        if results.detections:
            # Procesar el primer rostro detectado
            detection = results.detections[0]
            score = detection.score[0] if detection.score else 0.0
            
            if score >= MIN_DETECTION_CONF:
                face_detected_this_frame = True
                bbox = detection.location_data.relative_bounding_box
                
                # Recortar el rostro y obtener las coordenadas absolutas de la caja de visualización
                face_img, coords = crop_face(frame, bbox)
                x1, y1, x2, y2 = coords
 
                # Definir color de la caja de acuerdo al estado
                if auth_status == "GRANTED":
                    box_color = (0, 255, 0)      # Verde
                elif auth_status == "DENIED":
                    box_color = (0, 0, 255)      # Rojo
                elif auth_status == "PROCESSING":
                    box_color = (255, 255, 0)    # Amarillo / Cyan
                else:
                    box_color = (255, 0, 0)      # Azul (Buscando/Detectando)
 
                # Dibujar la caja delimitadora en la pantalla
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                
                # Mostrar el score de confianza en la pantalla encima del recuadro
                cv2.putText(
                    frame,
                    f"Conf: {score:.2f}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    box_color,
                    1
                )
 
                # Lógica de Autenticación con Cooldown
                if auth_status not in ["GRANTED", "DENIED", "PROCESSING"] and (current_time - last_auth_time > COOLDOWN_TIME):
                    auth_status = "PROCESSING"
                    status_msg = "PROCESANDO ACCESO..."
                    
                    if face_img.size > 0:
                        # Convertir recorte a Base64
                        _, encoded_img = cv2.imencode('.jpg', face_img)
                        base64_img = base64.b64encode(encoded_img).decode('utf-8')
                        
                        # Lanzar la petición en un hilo de ejecución secundario (no bloqueante)
                        threading.Thread(target=perform_auth, args=(base64_img, score), daemon=True).start()

        # =========================================================================
        #              INTERFAZ GRÁFICA DE USUARIO EN PANTALLA
        # =========================================================================
        # Franja negra superior para status
        overlay_color = (0, 0, 0)
        if auth_status == "GRANTED":
            overlay_color = (0, 100, 0)      # Verde oscuro
        elif auth_status == "DENIED":
            overlay_color = (0, 0, 100)      # Rojo oscuro
        elif auth_status == "PROCESSING":
            overlay_color = (100, 100, 0)    # Amarillo oscuro

        cv2.rectangle(frame, (0, 0), (w, 60), overlay_color, -1)

        # Imprimir status en pantalla
        cv2.putText(
            frame, 
            status_msg, 
            (20, 40), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.8, 
            (255, 255, 255), 
            2, 
            cv2.LINE_AA
        )

        # Imprimir información extra de usuario si existe
        if user_info:
            cv2.putText(
                frame, 
                user_info, 
                (w - 300, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.6, 
                (200, 200, 200), 
                1, 
                cv2.LINE_AA
            )

        # Mostrar indicador de cooldown/espera si es necesario
        if not face_detected_this_frame and auth_status is None:
            time_since_last = current_time - last_auth_time
            if time_since_last < COOLDOWN_TIME:
                cooldown_left = max(0.0, COOLDOWN_TIME - time_since_last)
                cv2.putText(
                    frame, 
                    f"Cooldown: {cooldown_left:.1f}s", 
                    (20, h - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, 
                    (0, 165, 255), 
                    1, 
                    cv2.LINE_AA
                )

        # Mostrar el frame procesado
        cv2.imshow("FaceSentinel Edge Gateway", frame)

        # Tecla de escape o 'q' para salir
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    # Liberar recursos
    cap.release()
    cv2.destroyAllWindows()
    print("👋 Edge Gateway cerrado correctamente.")

if __name__ == "__main__":
    main()
