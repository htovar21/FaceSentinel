import cv2
import base64
import requests
import time

# IMPORTANTE: Importamos nuestro motor matemático de Liveness
from app.services.liveness import analyze_face_liveness

# URL de tu API local (Asegúrate de que uvicorn esté corriendo)
BASE_URL = "http://127.0.0.1:8000/api/v1"

# Umbrales científicos para el parpadeo (EAR - Eye Aspect Ratio)
EAR_CERRADO = 0.20  # Si baja de este número, el ojo se considera cerrado
EAR_ABIERTO = 0.25  # Si sube de este número, el ojo está abierto

def frame_to_base64(frame):
    """Convierte el frame de OpenCV (matriz) a texto Base64 para enviarlo por HTTP."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')

def main():
    print("⏳ Iniciando cliente de cámara (DroidCam)...")
    # Usamos el 0 porque ya confirmamos que te funciona con DroidCam
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ Error: No se pudo conectar a la cámara.")
        return

    print("✅ Cámara lista con Anti-Spoofing (Liveness).")
    print("--------------------------------------------------")
    print("👉 CONTROLES EN LA VENTANA DE VIDEO:")
    print("   Presiona 'R' para REGISTRAR un nuevo usuario.")
    print("   Presiona 'A' para AUTENTICAR un rostro.")
    print("   Presiona 'Q' para SALIR.")
    print("--------------------------------------------------")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error al leer el flujo de video.")
            break

        # Dibujar instrucciones en la pantalla para que se vea profesional
        cv2.putText(frame, "R: Registrar | A: Autenticar | Q: Salir", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        cv2.imshow("BioAuth-Web3 | Punto de Acceso", frame)

        # Capturar qué tecla presiona el usuario
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        
        # --- LÓGICA DE REGISTRO ---
        elif key == ord('r'):
            print("\n--- NUEVO REGISTRO ---")
            # Pedimos los datos por consola para simular un formulario
            user_id = input("Ingresa un ID (ej. V-12345): ")
            name = input("Ingresa tu Nombre y Apellido: ")
            role = input("Ingresa tu Rol (Estudiante/Profesor): ")
            
            print("📸 Procesando foto con IA. Por favor, mantente quieto...")
            b64_img = frame_to_base64(frame)
            
            payload = {
                "user_id": user_id,
                "name": name,
                "role": role,
                "image_base64": b64_img
            }
            
            try:
                # Enviamos el POST a tu API
                response = requests.post(f"{BASE_URL}/register", json=payload)
                if response.status_code == 200:
                    print(f"✅ ÉXITO: {response.json()['message']}")
                else:
                    print(f"❌ ERROR: {response.json().get('detail')}")
            except Exception as e:
                print(f"⚠️ Error conectando al servidor: {e}")

        # --- LÓGICA DE AUTENTICACIÓN (AHORA CON LIVENESS) ---
        elif key == ord('a'):
            print("\n--- INTENTO DE ACCESO ---")
            print("🛡️ MODO ANTI-SPOOFING: Por favor, mira a la cámara y PARPADEA...")
            
            ojos_cerrados_detectados = False
            parpadeo_completado = False
            frame_para_enviar = None

            # Bucle de espera temporal: La cámara se queda aquí hasta que parpadees
            while not parpadeo_completado:
                ret, liveness_frame = cap.read()
                if not ret: break

                # OpenCV usa BGR, pero MediaPipe necesita colores en RGB
                rgb_frame = cv2.cvtColor(liveness_frame, cv2.COLOR_BGR2RGB)
                
                # Calcular la apertura de los ojos
                hay_rostro, ear = analyze_face_liveness(rgb_frame)

                # Imprimir el cálculo matemático en la pantalla
                cv2.putText(liveness_frame, f"EAR: {ear:.3f}", (10, 70), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                if hay_rostro:
                    if ear < EAR_CERRADO:
                        # Fase 1: El ojo se cerró
                        ojos_cerrados_detectados = True
                        cv2.putText(liveness_frame, "OJOS CERRADOS", (10, 100), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    elif ear > EAR_ABIERTO and ojos_cerrados_detectados:
                        # Fase 2: El ojo se volvió a abrir (Parpadeo exitoso)
                        parpadeo_completado = True
                        frame_para_enviar = liveness_frame.copy()
                        cv2.putText(liveness_frame, "PARPADEO DETECTADO!", (10, 100), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    else:
                        cv2.putText(liveness_frame, "ESPERANDO PARPADEO...", (10, 100), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 100), 2)
                else:
                    cv2.putText(liveness_frame, "NO SE DETECTA ROSTRO", (10, 100), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                cv2.imshow("BioAuth-Web3 | Punto de Acceso", liveness_frame)
                
                # Permitir cancelar presionando 'C'
                if cv2.waitKey(1) & 0xFF == ord('c'):
                    print("Cancelado por el usuario.")
                    break

            # Si salimos del bucle porque hubo un parpadeo, enviamos la foto a DeepFace
            if parpadeo_completado:
                cv2.waitKey(500) # Pausa de medio segundo para que veas el mensaje verde
                print("👁️ Parpadeo confirmado (Liveness OK). Analizando identidad en base de datos...")
                
                b64_img = frame_to_base64(frame_para_enviar)
                payload = {"image_base64": b64_img}
                
                try:
                    response = requests.post(f"{BASE_URL}/authenticate", json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        print(f"🔓 ACCESO PERMITIDO: Bienvenido {data['user_name']} | Rol: {data.get('role', 'N/A')} | Similitud: {data['match_score']}")
                    else:
                        print(f"🚫 ACCESO DENEGADO: {response.json().get('detail')}")
                except Exception as e:
                    print(f"⚠️ Error conectando al servidor: {e}")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()