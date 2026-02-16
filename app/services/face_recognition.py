import cv2
import numpy as np
import base64
from deepface import DeepFace
from app.core.config import settings
from app.services.storage import face_collection, save_user_data, get_user_by_id

# 1. Función Auxiliar: Convertir de Web a OpenCV
def base64_to_image(base64_string: str):
    """Convierte la imagen en texto (Base64) que envía el Frontend a un formato de matriz NumPy para OpenCV."""
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    
    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

# 2. El Motor de IA: Extracción de Características
def get_embedding(img_array):
    """Usa DeepFace (ArcFace) para extraer el vector matemático del rostro."""
    try:
        # enforce_detection=True asegura que haya una cara antes de procesar
        representations = DeepFace.represent(
            img_path=img_array, 
            model_name=settings.AI_MODEL_NAME, 
            enforce_detection=True
        )
        # Retornamos el vector (embedding) del primer rostro detectado
        return representations[0]["embedding"]
    except ValueError:
        # Esto salta si la IA no encuentra ningún rostro en la foto
        return None

# 3. Flujo de Registro (Enrollment)
def register_face(user_id: str, name: str, role: str, base64_image: str):
    """Procesa una foto nueva y guarda el usuario en SQLite y ChromaDB."""
    img = base64_to_image(base64_image)
    embedding = get_embedding(img)
    
    if not embedding:
        return False, "❌ No se detectó ningún rostro válido en la imagen. Intenta con mejor iluminación."
        
    save_user_data(user_id, name, role, embedding)
    return True, f"✅ Usuario {name} registrado exitosamente con biometría."

# 4. Flujo de Autenticación (Matching)
def verify_face(base64_image: str):
    """Convierte la foto de la cámara en vector y busca el más parecido en la DB."""
    img = base64_to_image(base64_image)
    embedding = get_embedding(img)
    
    if not embedding:
        return {"success": False, "message": "No se detectó ningún rostro frente a la cámara."}

    # Buscar en ChromaDB (n_results=1 trae al candidato matemáticamente más cercano)
    results = face_collection.query(
        query_embeddings=[embedding],
        n_results=1
    )

    if not results['ids'][0]:
        return {"success": False, "message": "Base de datos biométrica vacía."}

    # Extraer los datos de la búsqueda
    distance = results['distances'][0][0]
    matched_id = results['ids'][0][0]

    # Evaluación de Umbral (Threshold)
    # IMPORTANTE para la tesis: En distancia Coseno, MÁS BAJO significa MÁS PARECIDO.
    if distance < settings.FACE_MATCH_THRESHOLD:
        user_info = get_user_by_id(matched_id)
        return {
            "success": True, 
            "message": "Identidad confirmada.",
            "user_id": matched_id,
            "name": user_info["name"],
            "role": user_info["role"],
            "distance": round(distance, 4)
        }
    else:
        return {
            "success": False, 
            "message": f"Acceso denegado. Rostro desconocido (Distancia: {distance:.2f})"
        }