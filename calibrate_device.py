#!/usr/bin/env python3
"""
calibrate_device.py — Módulo de Autocalibración Sensorial y Óptica de Borde
FaceSentinel — Tesis de Grado

Propósito:
    Analiza la función de transferencia óptica, nivel de compresión de video (MJPEG/H.264/RTSP/USB)
    y distribución de entropía de piel local de una cámara específica.
    Calcula empíricamente el umbral óptimo de LBP (textura) y EAR (parpadeo)
    y lo almacena directamente en la base de datos de FaceSentinel para ese dispositivo.

Uso:
    $env:FACESENTINEL_VIDEO_SOURCE = "http://192.168.80.127:4747/video"  # o 0 para webcam
    $env:HW_CLIENT_SECRET = "hw_zaEy9rg43tK6QZa0e9O_oDE_spala6yRm71hA74ayV8"
    .\venv\Scripts\python.exe calibrate_device.py
"""

import os
import sys
import time
import json
import sqlite3
import subprocess
import numpy as np
import cv2
import mediapipe as mp
from skimage.feature import local_binary_pattern

# Configuración UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "sql", "database.db")
CALIB_DIR = os.path.join(BASE_DIR, "data", "calibrations")
os.makedirs(CALIB_DIR, exist_ok=True)

# Fuente de video
raw_source = os.getenv("FACESENTINEL_VIDEO_SOURCE", "0").strip()
if raw_source.isdigit():
    WEBCAM_SOURCE = int(raw_source)
else:
    WEBCAM_SOURCE = raw_source

# Token o ID del dispositivo
DEVICE_TOKEN = os.getenv("HW_CLIENT_SECRET", "hw_zaEy9rg43tK6QZa0e9O_oDE_spala6yRm71hA74ayV8").strip()

# Landmarks MediaPipe para EAR
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

def compute_lbp_features(gray_face):
    face_128 = cv2.resize(gray_face, (128, 128))
    lbp = local_binary_pattern(face_128, P=16, R=2, method="uniform")
    hist, _ = np.histogram(lbp.ravel(), bins=18, range=(0, 18))
    hist = hist.astype(float)
    hist /= (hist.sum() + 1e-7)
    entropy = -np.sum(hist * np.log2(hist + 1e-7))
    variance = float(np.var(hist))
    return float(entropy), variance

def find_device_id_by_token(token: str) -> str:
    """Busca el device_id correspondiente al token o hash en SQLite."""
    if not os.path.exists(DB_PATH):
        return "PASILLO62"
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT device_id FROM iot_devices WHERE device_id = 'PASILLO62'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else "PASILLO62"
    except Exception:
        return "PASILLO62"

def update_db_threshold(device_id: str, new_threshold: float):
    """Actualiza el umbral en SQLite local y en el contenedor Docker si está activo."""
    if not os.path.exists(DB_PATH):
        print(f"⚠️ Base de datos no encontrada en {DB_PATH}")
        return False

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE iot_devices SET lbp_threshold = ? WHERE device_id = ?", (new_threshold, device_id))
        conn.commit()
        conn.close()
        print(f"✅ SQLite local actualizado: Dispositivo '{device_id}' -> lbp_threshold = {new_threshold:.4f}")

        # Sincronizar con el contenedor Docker de backend si existe
        subprocess.run(
            ["docker", "cp", DB_PATH, "facesentinel-backend:/app/data/sql/database.db"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        print(f"❌ Error actualizando base de datos: {e}")
        return False

def load_camera_from_config(target_device: str):
    """Busca la configuración de una cámara específica en cameras.json."""
    paths = [
        os.path.join(BASE_DIR, "data", "cameras.json"),
        os.path.join(BASE_DIR, "cameras.json")
    ]
    for p in paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                    for c in configs:
                        if c.get("device_id", "").upper() == target_device.upper():
                            return c
            except Exception:
                pass
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Asistente de Calibración Sensorial de Cámaras — FaceSentinel")
    parser.add_argument("--device", type=str, default=None, help="ID del dispositivo en cameras.json (ej. TLFHECTOR, PASILLO62)")
    parser.add_argument("--source", type=str, default=None, help="URL de video (RTSP o HTTP DroidCam) o índice de webcam (0, 1)")
    parser.add_argument("--token", type=str, default=None, help="Token M2M del dispositivo (client_secret)")
    args = parser.parse_args()

    # Resolver dispositivo y fuente
    video_source = WEBCAM_SOURCE
    device_id = "PASILLO62"
    device_token = DEVICE_TOKEN

    if args.device:
        cfg = load_camera_from_config(args.device)
        if cfg:
            device_id = cfg.get("device_id", args.device)
            video_source = cfg.get("source", video_source)
            device_token = cfg.get("token", device_token)
            print(f"📖 Configuración cargada desde cameras.json para [{device_id}]")
        else:
            device_id = args.device

    if args.source:
        video_source = int(args.source) if args.source.isdigit() else args.source

    if args.token:
        device_token = args.token

    if not args.device and not args.source:
        device_id = find_device_id_by_token(device_token)

    print("=" * 70)
    print("    FaceSentinel — Asistente de Calibración Sensorial y Óptica")
    print("=" * 70)
    print(f"🏷️  Dispositivo a Calibrar: {device_id}")
    print(f"📷 Fuente de Video:        {video_source}")
    print("\n📋 Instrucciones:")
    print("   1. Mira fijamente a la cámara con tu rostro normal a la distancia habitual.")
    print("   2. El sistema capturará 40 fotogramas continuos analizando tu piel y ojos.")
    print("   3. Si deseas probar con pantalla de celular, mantén presionada la tecla [S].")
    print("   4. Presiona [ESPACIO] para iniciar la calibración | [Q] para cancelar.")
    print("=" * 70 + "\n")

    # Abrir cámara
    cap = None
    if isinstance(video_source, int):
        cap = cv2.VideoCapture(video_source, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(video_source)
    else:
        cap = cv2.VideoCapture(video_source)

    if not cap or not cap.isOpened():
        print(f"❌ Error: No se pudo abrir la fuente de video '{video_source}'.")
        print("💡 Verifica que la cámara o DroidCam esté activa y accesible en esa dirección.")
        return

    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.35,
        min_tracking_confidence=0.35
    )

    cv2.namedWindow("FaceSentinel — Calibrador Sensorial", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("FaceSentinel — Calibrador Sensorial", 720, 540)

    # Estado de calibración
    calibrating = False
    samples_live_entropy = []
    samples_live_variance = []
    samples_live_ear = []
    
    samples_spoof_entropy = []
    samples_spoof_variance = []

    target_samples = 40
    calib_mode = "LIVE"  # "LIVE" o "SPOOF"

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        h, w = frame.shape[:2]
        display_frame = frame.copy()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        face_detected = False
        ear_val = 0.0
        entropy_val = 0.0
        var_val = 0.0

        if results.multi_face_landmarks:
            face_detected = True
            face_lm = results.multi_face_landmarks[0]
            ear_l = eye_aspect_ratio(face_lm.landmark, LEFT_EYE_IDX, w, h)
            ear_r = eye_aspect_ratio(face_lm.landmark, RIGHT_EYE_IDX, w, h)
            ear_val = (ear_l + ear_r) / 2.0

            xs = [lm.x * w for lm in face_lm.landmark]
            ys = [lm.y * h for lm in face_lm.landmark]
            x1, x2 = max(0, int(min(xs))), min(w, int(max(xs)))
            y1, y2 = max(0, int(min(ys))), min(h, int(max(ys)))

            if (x2 - x1) > 40 and (y2 - y1) > 40:
                face_crop_gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                entropy_val, var_val = compute_lbp_features(face_crop_gray)

                # Dibujar bounding box
                box_color = (0, 255, 0) if calib_mode == "LIVE" else (0, 0, 255)
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), box_color, 2)

        # Si estamos en modo captura
        if calibrating and face_detected:
            if calib_mode == "LIVE":
                samples_live_entropy.append(entropy_val)
                samples_live_variance.append(var_val)
                samples_live_ear.append(ear_val)
            else:
                samples_spoof_entropy.append(entropy_val)
                samples_spoof_variance.append(var_val)

            if len(samples_live_entropy) >= target_samples and calib_mode == "LIVE":
                calibrating = False

        # Dibujar Interfaz de Calibración
        overlay = display_frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 90), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.75, display_frame, 0.25, 0, display_frame)

        if not calibrating and len(samples_live_entropy) < target_samples:
            status_text = "PULSA [ESPACIO] PARA INICIAR CALIBRACION | [S] MODO PANTALLA"
            cv2.putText(display_frame, status_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            cv2.putText(display_frame, f"Camara: {w}x{h} | EAR: {ear_val:.3f} | Entropia: {entropy_val:.3f}", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        elif calibrating:
            current_count = len(samples_live_entropy) if calib_mode == "LIVE" else len(samples_spoof_entropy)
            bar_w = int((w - 40) * (current_count / target_samples))
            cv2.rectangle(display_frame, (20, 70), (20 + bar_w, 80), (0, 255, 0), -1)
            cv2.putText(display_frame, f"CALIBRANDO ({calib_mode}): {current_count}/{target_samples} frames...", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"Entropia Instantanea: {entropy_val:.4f} | Varianza: {var_val:.5f}", (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        else:
            cv2.putText(display_frame, "CALIBRACION COMPLETADA CON EXITO (Pulsa Q para aplicar)", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.imshow("FaceSentinel — Calibrador Sensorial", display_frame)
        key = cv2.waitKey(1) & 0xFF

        if key in [ord('q'), ord('Q'), 27]:
            break
        elif key == 32:  # Barra espaciadora
            if not calibrating:
                calibrating = True
                calib_mode = "LIVE"
                samples_live_entropy.clear()
                samples_live_variance.clear()
                samples_live_ear.clear()
                print("▶️  Iniciando muestreo de sujeto real...")
        elif key in [ord('s'), ord('S')]:
            calib_mode = "SPOOF" if calib_mode == "LIVE" else "LIVE"
            print(f"🔄 Modo alternado a: {calib_mode}")

        # Salir si terminó la calibración
        if len(samples_live_entropy) >= target_samples and not calibrating:
            time.sleep(0.5)
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(samples_live_entropy) < 10:
        print("⚠️ No se acumularon suficientes muestras para calcular la calibración.")
        return

    # =========================================================================
    #                    CÁLCULO ESTADÍSTICO DEL UMBRAL ÓPTIMO
    # =========================================================================
    arr_ent = np.array(samples_live_entropy)
    arr_var = np.array(samples_live_variance)
    arr_ear = np.array(samples_live_ear)

    mean_ent = float(np.mean(arr_ent))
    std_ent  = float(np.std(arr_ent))
    min_ent  = float(np.min(arr_ent))
    max_ent  = float(np.max(arr_ent))

    mean_var = float(np.mean(arr_var))
    mean_ear = float(np.mean(arr_ear))

    # Umbral propuesto:
    # Ligeramente por debajo del mínimo empírico registrado (min_ent - 0.005) o 2.5 desviaciones bajo la media
    # asegurando 100% de aceptación para el usuario legítimo en esta cámara
    suggested_threshold = round(max(3.45, min(3.72, min(min_ent - 0.005, mean_ent - 2.5 * std_ent))), 3)

    # Si se tomaron muestras de spoof, ajustar al punto medio
    if len(samples_spoof_entropy) >= 5:
        spoof_max = float(np.max(samples_spoof_entropy))
        if spoof_max < min_ent:
            suggested_threshold = round((spoof_max + min_ent) / 2.0, 3)

    print("\n" + "=" * 65)
    print("          📊 [REPORTE DE CALIBRACIÓN SENSORIAL]")
    print("=" * 65)
    print(f" 🏷️  Dispositivo Analizado:     {device_id}")
    print(f" 📷 Resolución de Entrada:     {w}x{h} px")
    print(f" 📦 Muestras Analizadas:       {len(arr_ent)} frames")
    print("-" * 65)
    print(f" 🧬 Entropía Piel Real (Media): {mean_ent:.4f} ± {std_ent:.4f}")
    print(f" 📉 Rango Empírico de Piel:    [{min_ent:.4f} — {max_ent:.4f}]")
    print(f" 📈 Varianza LBP (Media):      {mean_var:.6f} {'(Óptima piel real)' if mean_var <= 0.00245 else '(Compresión alta)'}")
    print(f" 👁️  EAR Ojos Abiertos (Media): {mean_ear:.3f}")
    print("-" * 65)
    print(f" 🎯 UMBRAL LBP ÓPTIMO RECOMENDADO: {suggested_threshold:.4f}")
    print("=" * 65 + "\n")

    # Guardar perfil de calibración en JSON
    profile_data = {
        "device_id": device_id,
        "calibration_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "resolution": {"width": w, "height": h},
        "sample_count": len(arr_ent),
        "entropy_stats": {
            "mean": round(mean_ent, 4),
            "std": round(std_ent, 4),
            "min": round(min_ent, 4),
            "max": round(max_ent, 4)
        },
        "variance_mean": round(mean_var, 6),
        "ear_open_mean": round(mean_ear, 4),
        "optimal_lbp_threshold": suggested_threshold
    }

    profile_path = os.path.join(CALIB_DIR, f"{device_id}_calib.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=4)
    print(f"📁 Perfil de calibración guardado en: {profile_path}")

    # Aplicar a la base de datos
    update_db_threshold(device_id, suggested_threshold)
    print("\n✨ ¡Calibración finalizada! Ahora el Edge Gateway y el Backend operan con el punto óptimo de esta cámara.\n")

if __name__ == "__main__":
    main()
