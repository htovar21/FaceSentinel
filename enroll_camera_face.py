#!/usr/bin/env python3
"""
enroll_camera_face.py — Enrolamiento Facial Directo desde Cámara Periférica
FaceSentinel — Tesis de Grado

Captura el rostro del usuario directamente desde la lente periférica (ej. Pasillo RTSP o DroidCam)
para evitar la discrepancia geométrica entre selfies frontales y cámaras cenitales de seguridad.

Uso:
    .\\venv\\Scripts\\python.exe enroll_camera_face.py --user_id 30335783 --device PASILLO62
"""

import os
import sys
import time
import json
import argparse
import numpy as np
import cv2
import requests
import mediapipe as mp

# Reconfigurar stdout para Windows PowerShell
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def parse_args():
    parser = argparse.ArgumentParser(description="Enrolamiento biométrico directo desde cámara periférica")
    parser.add_argument("--user_id", type=str, default="30335783", help="ID del usuario a enrolar (ej. 30335783)")
    parser.add_argument("--device", type=str, default="PASILLO62", help="Device ID de la cámara (ej. PASILLO62)")
    parser.add_argument("--source", type=str, default=None, help="URL RTSP/HTTP manual (opcional)")
    return parser.parse_args()

def get_device_config(device_id: str, manual_source: str = None) -> tuple:
    if manual_source:
        return manual_source, f"Dispositivo Manual ({device_id})"
    
    # Buscar en cameras.json
    for path in ["data/cameras.json", "cameras.json"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    devices = json.load(f)
                    for d in devices:
                        if d.get("device_id") == device_id:
                            return d.get("source"), d.get("name", device_id)
            except Exception:
                pass
                
    # Fallback predeterminado para PASILLO62
    if device_id == "PASILLO62":
        return "rtsp://admin1:cimos.1979@192.168.70.10:554/Streaming/Channels/201", "Pasillo 6-2 (Patio B)"
    elif device_id == "TLFHECTOR":
        return "http://192.168.80.89:4747/video", "Smart 20 Hector"
        
    return 0, device_id

def crop_face_hd(frame_bgr, face_landmarks, margin_pct: float = 0.35):
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

def main():
    args = parse_args()
    source, dev_name = get_device_config(args.device, args.source)

    print("=" * 65)
    print("      FaceSentinel — Enrolamiento Óptico Multi-Ángulo")
    print("=" * 65)
    print(f"👤 Usuario ID:    {args.user_id}")
    print(f"📹 Dispositivo:   [{args.device}] {dev_name}")
    print(f"📡 Flujo Video:   {source}")
    print("-" * 65)

    if isinstance(source, str) and source.lower().startswith("rtsp://"):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"

    raw_src = int(source) if str(source).isdigit() else source
    cap = cv2.VideoCapture(raw_src)
    if not cap or not cap.isOpened():
        print(f"❌ Error: No se pudo conectar a la cámara: {source}")
        return

    mp_mesh = mp.solutions.face_mesh
    face_mesh = mp_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.35,
        min_tracking_confidence=0.35
    )

    print("👀 Conectado. Por favor, mira fijamente a la cámara.")
    print("⌨️  Presiona [ESPACIO] para capturar tu rostro | [Q] para cancelar.\n")

    captured_crops = []
    window_title = f"FaceSentinel - Enrolamiento [{args.device}]"

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.03)
            continue

        h_orig, w_orig = frame.shape[:2]
        # Redimensionar solo para preview fluido en pantalla
        preview = frame.copy()
        if preview.shape[1] > 800:
            scale = 800.0 / preview.shape[1]
            preview = cv2.resize(preview, (800, int(preview.shape[0] * scale)))

        hp, wp = preview.shape[:2]
        rgb_p = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        res = face_mesh.process(rgb_p)

        face_found = False
        box_coords = None

        if res.multi_face_landmarks:
            face_found = True
            lm = res.multi_face_landmarks[0]
            # Extraer recorte HD del fotograma original completo
            crop_hd, _ = crop_face_hd(frame, lm, margin_pct=0.35)
            # Box en preview para dibujar
            _, box_coords = crop_face_hd(preview, lm, margin_pct=0.35)

        # Dibujar UI
        display = preview.copy()
        banner_color = (0, 160, 0) if face_found else (0, 0, 180)
        cv2.rectangle(display, (0, 0), (wp, 60), (20, 20, 20), -1)
        cv2.putText(display, f"ENROLANDO: {args.user_id} en [{args.device}]", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        status_txt = "Rostro detectado -> Pulsa [ESPACIO] para guardar" if face_found else "Buscando rostro... Mira a la camara"
        cv2.putText(display, status_txt, (15, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0) if face_found else (0, 165, 255), 1)

        if box_coords and face_found:
            x1, y1, x2, y2 = box_coords
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

        cv2.imshow(window_title, display)
        key = cv2.waitKey(1) & 0xFF

        if key in [ord('q'), ord('Q'), 27]:
            print("👋 Operación cancelada por el usuario.")
            break
        elif key == 32: # Espacio
            if face_found and crop_hd is not None:
                print("📸 Capturando y extrayendo embedding biométrico...")
                captured_crops.append(crop_hd)
                if len(captured_crops) >= 3:
                    break
            else:
                print("⚠️  No hay ningún rostro centrado en este momento.")

    cap.release()
    cv2.destroyAllWindows()

    if len(captured_crops) < 1:
        print("❌ No se capturó ninguna imagen válida.")
        return

    # Guardar la mejor captura temporal
    best_crop = captured_crops[-1]
    temp_path = "data/temp_images/enrolled_cctv.jpg"
    cv2.imwrite(temp_path, best_crop)
    print(f"💾 Fotograma guardado en {temp_path} ({best_crop.shape[1]}x{best_crop.shape[0]} px)")

    # Enviar al backend vía contenedor o script interno
    print("\n⚙️  Registrando vector en ChromaDB...")
    try:
        import base64
        _, buf = cv2.imencode(".jpg", best_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
        b64_img = base64.b64encode(buf).decode("utf-8")

        # Llamar a la API para registrar
        token = "hw_zaEy9rg43tK6QZa0e9O_oDE_spala6yRm71hA74ayV8"
        # Usar Docker exec para insertar el embedding directamente en ChromaDB
        import subprocess
        cmd = [
            "docker", "exec", "facesentinel-backend", "python", "-c",
            f"""
import cv2
import numpy as np
from app.services.face_recognition import get_embedding
from app.services.storage import face_collection, get_user_by_id

img = cv2.imread('/app/data/temp_images/enrolled_cctv.jpg')
emb, t_ms = get_embedding(img)
if not emb:
    print('ERROR: DeepFace no pudo extraer embedding del recorte.')
    exit(1)

user_info = get_user_by_id('{args.user_id}')
name = user_info['name'] if user_info else 'Usuario'
role = user_info['role'] if user_info else 'User'

# Guardar con ID multi-plantilla
multi_id = '{args.user_id}_{args.device}'
face_collection.upsert(
    embeddings=[emb],
    ids=[multi_id],
    metadatas=[{{"name": name, "role": role, "user_id": '{args.user_id}', "device": '{args.device}'}}]
)

# También actualizar la plantilla principal para asegurar compatibilidad total
face_collection.upsert(
    embeddings=[emb],
    ids=['{args.user_id}'],
    metadatas=[{{"name": name, "role": role, "device": '{args.device}'}}]
)
print('SUCCESS')
"""
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if "SUCCESS" in res.stdout:
            print(f"🎉 ¡ÉXITO! Plantilla biométrica de {args.user_id} enrolada directamente desde {args.device}.")
            print("🚀 Ahora puedes pasar frente a la cámara y el acceso será CONCEDIDO inmediatamente.")
        else:
            print(f"⚠️  Respuesta del servidor:\n{res.stdout}\n{res.stderr}")
    except Exception as e:
        print(f"❌ Error durante el enrolamiento: {e}")

if __name__ == "__main__":
    main()
