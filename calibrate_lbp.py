#!/usr/bin/env python3
"""
calibrate_lbp.py — Script independiente de calibración de entropía LBP para FaceSentinel.

Replica exactamente el procesamiento de textura de app/services/liveness.py:
1. Captura video en tiempo real desde la webcam local.
2. Detecta el rostro mediante Haar Cascade.
3. Extrae la región facial en escala de grises y la escala a 128x128 px.
4. Calcula LBP uniforme con skimage (P=16, R=2, method="uniform").
5. Obtiene el histograma de 18 bins y la entropía de Shannon.
6. Muestra el valor en tiempo real en pantalla y en la consola para facilitar
   el ajuste de umbrales entre rostros reales y ataques de presentación (pantallas/fotos).
"""

import sys
import cv2
import numpy as np
from skimage.feature import local_binary_pattern

# Configuración de salida segura en consola Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    print("=" * 60)
    print("  FaceSentinel — Herramienta de Calibración de Entropía LBP")
    print("=" * 60)
    print("[*] Iniciando captura de video desde la cámara (índice 0)...")
    print("[*] Presiona 'q' en la ventana de video para salir.\n")

    # 1. Inicializar clasificador Haar Cascade para detección facial
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    # 2. Abrir webcam local
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Error: No se pudo acceder a la cámara (índice 0).")
        print("   Verifica que la cámara esté conectada y no esté en uso por otra app.")
        return

    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("⚠️ No se pudo leer el fotograma de la cámara.")
                break

            frame_count += 1
            h_frame, w_frame, _ = frame.shape
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detección de rostros con los mismos hiperparámetros de liveness.py
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

            status_text = "Buscando rostro..."
            entropy_val = None

            if len(faces) > 0:
                # Tomar la primera cara detectada
                x, y, w, h = faces[0]

                # Dibujar recuadro sobre el rostro detectado
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # Preprocesamiento idéntico a analyze_texture()
                face_roi = gray[y : y + h, x : x + w]
                face_roi = cv2.resize(face_roi, (128, 128))

                # LBP uniforme con P=16, R=2
                lbp = local_binary_pattern(face_roi, P=16, R=2, method="uniform")

                # Histograma normalizado de 18 bins (rango 0 a 18)
                n_bins = 18
                hist, _ = np.histogram(lbp.ravel(), bins=n_bins, range=(0, n_bins))
                hist = hist.astype(float)
                hist /= hist.sum() + 1e-7

                # Entropía de Shannon
                entropy_val = float(-np.sum(hist * np.log2(hist + 1e-7)))
                status_text = f"Entropia LBP: {entropy_val:.4f}"

                # Imprimir periódicamente en consola (cada 10 fotogramas)
                if frame_count % 10 == 0:
                    print(f"[{frame_count:05d}] Entropía LBP detectada: {entropy_val:.4f} (máx teórico ~4.17)")

                # Visualización adicional: mini vista previa del ROI y LBP en la esquina superior derecha
                lbp_vis = (lbp * (255.0 / (n_bins - 1))).astype(np.uint8)
                lbp_vis_color = cv2.cvtColor(lbp_vis, cv2.COLOR_GRAY2BGR)
                frame[10:138, w_frame - 138 : w_frame - 10] = lbp_vis_color
                cv2.rectangle(frame, (w_frame - 138, 10), (w_frame - 10, 138), (255, 255, 255), 1)
                cv2.putText(
                    frame,
                    "LBP (P=16)",
                    (w_frame - 135, 130),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (0, 255, 255),
                    1,
                )

            # Banner de información superpuesto
            cv2.rectangle(frame, (10, 10), (450, 70), (0, 0, 0), -1)
            cv2.putText(
                frame,
                status_text,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0) if entropy_val else (0, 165, 255),
                2,
            )
            cv2.putText(
                frame,
                "Presiona 'q' para salir | Escala max log2(18) = 4.17",
                (20, 62),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (200, 200, 200),
                1,
            )

            # Mostrar ventana interactiva
            cv2.imshow("Calibracion LBP - FaceSentinel", frame)

            # Salir con la tecla 'q'
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("\n[*] Deteniendo calibración por solicitud del usuario...")
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[*] Cámara liberada y ventanas cerradas limpiamente.")


if __name__ == "__main__":
    main()
