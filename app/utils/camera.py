"""
camera.py — Cliente de Cámara con Anti-Spoofing Avanzado
Interfaz de video en tiempo real para registro y autenticación facial
con múltiples capas de detección de vida (liveness).
"""

import cv2
import base64
import requests
import time
import logging

# Importamos el motor anti-spoofing avanzado
from app.services.liveness import (
    analyze_face_liveness,
    comprehensive_liveness_check,
    estimate_head_pose,
)

logger = logging.getLogger(__name__)

# URL de tu API local (Asegúrate de que uvicorn esté corriendo)
BASE_URL = "http://127.0.0.1:8000/api/v1"

# Umbrales científicos para el parpadeo (EAR - Eye Aspect Ratio)
EAR_CERRADO = 0.20  # Si baja de este número, el ojo se considera cerrado
EAR_ABIERTO = 0.25  # Si sube de este número, el ojo está abierto

# Colores para la interfaz
COLOR_GREEN = (0, 255, 0)
COLOR_RED = (0, 0, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_BLUE = (255, 180, 0)


def frame_to_base64(frame):
    """Convierte el frame de OpenCV (matriz) a texto Base64 para enviarlo por HTTP."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')


def draw_status_bar(frame, text, color=COLOR_WHITE, y_pos=30):
    """Dibuja un texto con fondo semi-transparente."""
    (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(frame, (5, y_pos - text_h - 5), (text_w + 15, y_pos + 5), (0, 0, 0), -1)
    cv2.putText(frame, text, (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def main():
    print("=" * 55)
    print("  FaceSentinel | Sistema de Autenticación Biométrica")
    print("=" * 55)
    print("⏳ Iniciando cliente de cámara...")

    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ Error: No se pudo conectar a la cámara.")
        return

    print("✅ Cámara lista con Anti-Spoofing Avanzado.")
    print("-" * 55)
    print("  CONTROLES EN LA VENTANA DE VIDEO:")
    print("  [R]  Registrar un nuevo usuario")
    print("  [A]  Autenticar un rostro (con liveness)")
    print("  [L]  Prueba de liveness completa")
    print("  [Q]  Salir del sistema")
    print("-" * 55)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error al leer el flujo de video.")
            break

        # Dibujar interfaz
        draw_status_bar(frame, "R:Registrar | A:Autenticar | L:Liveness | Q:Salir", COLOR_WHITE, 25)

        cv2.imshow("FaceSentinel | Punto de Acceso", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break

        # --- REGISTRO ---
        elif key == ord('r'):
            print("\n--- NUEVO REGISTRO ---")
            user_id = input("  ID (ej. V-12345): ")
            name = input("  Nombre y Apellido: ")
            role = input("  Rol (Estudiante/Profesor): ")

            print("📸 Procesando foto con IA...")
            b64_img = frame_to_base64(frame)

            payload = {
                "user_id": user_id,
                "name": name,
                "role": role,
                "image_base64": b64_img
            }

            try:
                response = requests.post(f"{BASE_URL}/register", json=payload)
                if response.status_code == 200:
                    print(f"  ✅ ÉXITO: {response.json()['message']}")
                else:
                    print(f"  ❌ ERROR: {response.json().get('detail')}")
            except Exception as e:
                print(f"  ⚠️ Error conectando al servidor: {e}")

        # --- AUTENTICACIÓN CON LIVENESS COMPLETO ---
        elif key == ord('a'):
            print("\n--- INTENTO DE ACCESO ---")
            print("🛡️ ANTI-SPOOFING: Mira a la cámara y PARPADEA...")

            ojos_cerrados_detectados = False
            parpadeo_completado = False
            frame_para_enviar = None
            liveness_score = 0

            while not parpadeo_completado:
                ret, liveness_frame = cap.read()
                if not ret:
                    break

                rgb_frame = cv2.cvtColor(liveness_frame, cv2.COLOR_BGR2RGB)
                hay_rostro, ear = analyze_face_liveness(rgb_frame)

                # Mostrar EAR
                draw_status_bar(liveness_frame, f"EAR: {ear:.3f}", COLOR_YELLOW, 60)

                if hay_rostro:
                    if ear < EAR_CERRADO:
                        ojos_cerrados_detectados = True
                        draw_status_bar(liveness_frame, "OJOS CERRADOS", COLOR_RED, 90)

                    elif ear > EAR_ABIERTO and ojos_cerrados_detectados:
                        # Parpadeo detectado — ahora hacer liveness avanzado
                        draw_status_bar(liveness_frame, "PARPADEO OK! Verificando textura...", COLOR_GREEN, 90)
                        cv2.imshow("BioAuth-Web3 | Punto de Acceso", liveness_frame)
                        cv2.waitKey(300)

                        # Verificación avanzada de liveness
                        liveness_result = comprehensive_liveness_check(liveness_frame)
                        liveness_score = liveness_result.get("liveness_score", 0)

                        if liveness_result["is_live"]:
                            parpadeo_completado = True
                            frame_para_enviar = liveness_frame.copy()
                            draw_status_bar(liveness_frame, f"LIVENESS OK (Score: {liveness_score:.2f})", COLOR_GREEN, 120)
                        else:
                            draw_status_bar(liveness_frame, f"SPOOFING DETECTADO (Score: {liveness_score:.2f})", COLOR_RED, 120)
                            print(f"  🚨 Posible ataque detectado: {liveness_result.get('reason')}")
                            ojos_cerrados_detectados = False  # Resetear

                    else:
                        draw_status_bar(liveness_frame, "ESPERANDO PARPADEO...", COLOR_BLUE, 90)
                else:
                    draw_status_bar(liveness_frame, "NO SE DETECTA ROSTRO", COLOR_RED, 90)

                cv2.imshow("FaceSentinel | Punto de Acceso", liveness_frame)

                if cv2.waitKey(1) & 0xFF == ord('c'):
                    print("  Cancelado por el usuario.")
                    break

            if parpadeo_completado:
                cv2.waitKey(500)
                print(f"  👁️ Liveness confirmado (Score: {liveness_score:.2f}). Verificando identidad...")

                b64_img = frame_to_base64(frame_para_enviar)
                payload = {"image_base64": b64_img}

                try:
                    response = requests.post(f"{BASE_URL}/authenticate", json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        tx_info = f" | TX: {data['tx_hash'][:16]}..." if data.get('tx_hash') else ""
                        print(f"  🔓 ACCESO PERMITIDO: {data['user_name']} | Rol: {data.get('role', 'N/A')} | Similitud: {data['match_score']}{tx_info}")
                    else:
                        print(f"  🚫 ACCESO DENEGADO: {response.json().get('detail')}")
                except Exception as e:
                    print(f"  ⚠️ Error conectando al servidor: {e}")

        # --- PRUEBA DE LIVENESS SOLO (DEBUG) ---
        elif key == ord('l'):
            print("\n--- PRUEBA DE LIVENESS ---")
            result = comprehensive_liveness_check(frame)
            print(f"  Score: {result['liveness_score']:.4f}")
            print(f"  Es real: {'✅ Sí' if result['is_live'] else '❌ No'}")
            print(f"  Razón: {result['reason']}")
            if result.get("details"):
                details = result["details"]
                print(f"  Textura: {details.get('texture', {}).get('texture_score', 'N/A')}")
                print(f"  Frecuencia: {details.get('frequency', {}).get('frequency_score', 'N/A')}")
                print(f"  EAR: {details.get('ear', 'N/A')}")
                pose = details.get("head_pose", {})
                if pose.get("detected"):
                    print(f"  Pose — Yaw: {pose['yaw']:.1f} | Pitch: {pose['pitch']:.1f} | Roll: {pose['roll']:.1f}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()