"""
face_recognition.py — Motor de Reconocimiento Facial BioAuth-Web3
Usa DeepFace con ArcFace para extraer embeddings y buscar coincidencias en ChromaDB.
"""

import logging
import cv2
import numpy as np
import base64
from deepface import DeepFace
from app.core.config import settings
from app.services.storage import face_collection, save_user_data, get_user_by_id

logger = logging.getLogger(__name__)


# =========================================================================
#              UTILIDADES DE CONVERSIÓN
# =========================================================================

def base64_to_image(base64_string: str):
    """Convierte la imagen en texto (Base64) que envía el Frontend a un formato de matriz NumPy para OpenCV."""
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]

    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("No se pudo decodificar la imagen Base64")

    return img


# =========================================================================
#              MOTOR DE IA: EXTRACCIÓN DE CARACTERÍSTICAS
# =========================================================================

def get_embedding(img_array):
    """Usa DeepFace (ArcFace) para extraer el vector matemático del rostro."""
    try:
        representations = DeepFace.represent(
            img_path=img_array,
            model_name=settings.AI_MODEL_NAME,
            enforce_detection=True
        )
        embedding = representations[0]["embedding"]
        logger.debug(f"Embedding extraído: vector de {len(embedding)} dimensiones")
        return embedding
    except ValueError:
        logger.warning("No se detectó ningún rostro en la imagen")
        return None
    except Exception as e:
        logger.error(f"Error en DeepFace.represent: {e}")
        return None


# =========================================================================
#              FLUJO DE REGISTRO (ENROLLMENT)
# =========================================================================

def register_face(user_id: str, name: str, role: str, base64_image: str):
    """Procesa una foto nueva y guarda el usuario en SQLite y ChromaDB."""
    logger.info(f"📝 Iniciando registro para '{name}' (ID: {user_id})...")

    img = base64_to_image(base64_image)
    embedding = get_embedding(img)

    if not embedding:
        logger.warning(f"Registro fallido para '{name}': sin rostro detectado")
        return False, "❌ No se detectó ningún rostro válido en la imagen. Intenta con mejor iluminación."

    save_user_data(user_id, name, role, embedding)
    logger.info(f"✅ Usuario '{name}' registrado exitosamente con biometría")
    return True, f"✅ Usuario {name} registrado exitosamente con biometría."


# =========================================================================
#              FLUJO DE AUTENTICACIÓN (MATCHING)
# =========================================================================

def verify_face(base64_image: str):
    """Convierte la foto de la cámara en vector y busca el más parecido en la DB."""
    logger.info("🔍 Iniciando verificación facial...")

    img = base64_to_image(base64_image)
    embedding = get_embedding(img)

    if not embedding:
        logger.warning("Verificación fallida: sin rostro detectado")
        return {"success": False, "message": "No se detectó ningún rostro frente a la cámara."}

    # Buscar en ChromaDB (n_results=1 trae al candidato matemáticamente más cercano)
    results = face_collection.query(
        query_embeddings=[embedding],
        n_results=1
    )

    if not results['ids'][0]:
        logger.warning("Verificación fallida: base de datos biométrica vacía")
        return {"success": False, "message": "Base de datos biométrica vacía."}

    # Extraer los datos de la búsqueda
    distance = results['distances'][0][0]
    matched_id = results['ids'][0][0]

    logger.info(f"Candidato encontrado: {matched_id} | Distancia: {distance:.4f} | Umbral: {settings.FACE_MATCH_THRESHOLD}")

    # Evaluación de Umbral (Threshold)
    # En distancia Coseno, MÁS BAJO significa MÁS PARECIDO
    if distance < settings.FACE_MATCH_THRESHOLD:
        user_info = get_user_by_id(matched_id)
        if user_info:
            logger.info(f"✅ Identidad confirmada: {user_info['name']} (distancia: {distance:.4f})")
            return {
                "success": True,
                "message": "Identidad confirmada.",
                "user_id": matched_id,
                "name": user_info["name"],
                "role": user_info["role"],
                "distance": round(distance, 4)
            }
        else:
            logger.error(f"Error: ID {matched_id} encontrado en ChromaDB pero no en SQLite")
            return {"success": False, "message": "Error de sincronización de datos."}
    else:
        logger.warning(f"🚫 Acceso denegado: distancia {distance:.4f} > umbral {settings.FACE_MATCH_THRESHOLD}")
        return {
            "success": False,
            "message": f"Acceso denegado. Rostro desconocido (Distancia: {distance:.2f})"
        }