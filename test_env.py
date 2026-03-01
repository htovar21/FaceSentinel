import cv2
import deepface
import chromadb
import web3
import mediapipe as mp

print("✅ ¡Todas las librerías de IA y Web3 se importaron correctamente!")
print("⏳ Iniciando la cámara...")

# Iniciar la captura de video (0 suele ser la cámara web principal)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ ERROR: No se pudo acceder a la cámara web.")
else:
    print("📸 Cámara funcionando. Presiona la tecla 'q' en la ventana de video para cerrar.")
    
    while True:
        # Leer el frame de la cámara
        ret, frame = cap.read()
        
        if not ret:
            print("No se pudo recibir el frame. Saliendo...")
            break
            
        # Mostrar el frame en una ventana
        cv2.imshow('Prueba FaceSentinel', frame)
        
        # Esperar 1 milisegundo a que se presione la tecla 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# Liberar la cámara y cerrar ventanas
cap.release()
cv2.destroyAllWindows()
print("👋 Prueba finalizada con éxito.")