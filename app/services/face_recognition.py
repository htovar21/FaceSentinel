"""
face_recognition.py — Motor de Reconocimiento Facial FaceSentinel
Usa DeepFace con ArcFace para extraer embeddings y buscar coincidencias en ChromaDB.
"""

import logging
import cv2
import numpy as np
import base64
import time
from deepface import DeepFace
from app.core.config import settings
from app.services.storage import face_collection, save_user_data, get_user_by_id, delete_user

logger = logging.getLogger(__name__)


# =========================================================================
#              UTILIDADES DE CONVERSIÓN
# =========================================================================

def base64_to_image(base64_string: str):
    """Convierte la imagen en texto (Base64) que envía el Frontend a un formato de matriz NumPy para OpenCV."""
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
        
    if not base64_string:
        raise ValueError("La cadena Base64 recibida está vacía")

    # Asegurar padding
    base64_string += "=" * ((4 - len(base64_string) % 4) % 4)

    try:
        img_data = base64.b64decode(base64_string)
    except Exception as e:
        raise ValueError(f"No se pudo decodificar Base64: {e}")

    nparr = np.frombuffer(img_data, np.uint8)
    if nparr.size == 0:
        raise ValueError("El buffer de imagen está vacío")
        
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("No se pudo decodificar la imagen Base64")

    return img


# =========================================================================
#              MOTOR DE IA: EXTRACCIÓN DE CARACTERÍSTICAS
# =========================================================================

def get_embedding(img_array):
    """Usa DeepFace (ArcFace) para extraer el vector matemático del rostro y mide el tiempo empleado."""
    t0 = time.perf_counter()
    try:
        representations = DeepFace.represent(
            img_path=img_array,
            model_name=settings.AI_MODEL_NAME,
            enforce_detection=True
        )
        embedding = representations[0]["embedding"]
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.debug(f"Embedding extraído ({elapsed_ms:.1f}ms): vector de {len(embedding)} dimensiones")
        return embedding, elapsed_ms
    except ValueError:
        logger.warning("No se detectó ningún rostro en la imagen")
        return None, (time.perf_counter() - t0) * 1000.0
    except Exception as e:
        logger.error(f"Error en DeepFace.represent: {e}")
        return None, (time.perf_counter() - t0) * 1000.0


# =========================================================================
#              FLUJO DE REGISTRO (ENROLLMENT)
# =========================================================================

def register_face(user_id: str, name: str, role: str, base64_image: str):
    """Procesa una foto nueva y guarda el usuario en SQLite y ChromaDB."""
    logger.info(f"📝 Iniciando registro para '{name}' (ID: {user_id})...")

    img = base64_to_image(base64_image)
    embedding, _ = get_embedding(img)

    if not embedding:
        logger.warning(f"Registro fallido para '{name}': sin rostro detectado")
        return False, "❌ No se detectó ningún rostro válido en la imagen. Intenta con mejor iluminación."

    save_user_data(user_id, name, role, embedding)
    logger.info(f"✅ Usuario '{name}' registrado exitosamente con biometría")
    return True, f"✅ Usuario {name} registrado exitosamente con biometría."


# =========================================================================
#              FLUJO DE AUTENTICACIÓN (MATCHING)
# =========================================================================

def verify_face(image_data):
    """Convierte la foto de la cámara (o usa el numpy array directamente) en vector y busca el más parecido en la DB."""
    logger.info("🔍 Iniciando verificación facial...")
    t0_verify = time.perf_counter()

    if isinstance(image_data, str):
        try:
            img = base64_to_image(image_data)
        except Exception as e:
            logger.warning(f"Error decodificando imagen base64: {e}")
            return {
                "success": False,
                "message": f"Error decodificando imagen: {e}",
                "t_arcface_ms": 0.0,
                "t_chroma_ms": 0.0,
                "distance": 0.0,
                "user_id": None
            }
    elif isinstance(image_data, np.ndarray):
        img = image_data
    else:
        logger.error(f"Formato de imagen inválido: {type(image_data)}")
        return {
            "success": False,
            "message": "Formato de imagen inválido",
            "t_arcface_ms": 0.0,
            "t_chroma_ms": 0.0,
            "distance": 0.0,
            "user_id": None
        }

    embedding, t_arcface_ms = get_embedding(img)

    if not embedding:
        logger.warning("Verificación fallida: sin rostro detectado")
        return {
            "success": False,
            "message": "No se detectó ningún rostro frente a la cámara.",
            "t_arcface_ms": round(t_arcface_ms, 2),
            "t_chroma_ms": 0.0,
            "distance": 0.0,
            "user_id": None
        }

    # Buscar en ChromaDB (n_results=1 trae al candidato matemáticamente más cercano)
    t0_chroma = time.perf_counter()
    results = face_collection.query(
        query_embeddings=[embedding],
        n_results=1
    )
    t_chroma_ms = (time.perf_counter() - t0_chroma) * 1000.0

    if not results['ids'][0]:
        logger.warning("Verificación fallida: base de datos biométrica vacía")
        return {
            "success": False,
            "message": "Base de datos biométrica vacía.",
            "t_arcface_ms": round(t_arcface_ms, 2),
            "t_chroma_ms": round(t_chroma_ms, 2),
            "distance": 0.0,
            "user_id": None
        }

    # Extraer los datos de la búsqueda
    distance = results['distances'][0][0]
    matched_id = results['ids'][0][0]

    logger.info(f"Candidato encontrado: {matched_id} | Distancia: {distance:.4f} | Umbral: {settings.FACE_MATCH_THRESHOLD}")

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
                "distance": round(distance, 4),
                "t_arcface_ms": round(t_arcface_ms, 2),
                "t_chroma_ms": round(t_chroma_ms, 2),
                "embedding": embedding
            }
        else:
            logger.error(f"Error: ID {matched_id} encontrado en ChromaDB pero no en SQLite. Limpiando inconsistencia...")
            try:
                face_collection.delete(ids=[matched_id])
                logger.info(f"🧹 Consistencia restaurada: ID {matched_id} eliminado de ChromaDB.")
            except Exception as cleanup_err:
                logger.error(f"Error al limpiar ID {matched_id} de ChromaDB: {cleanup_err}")
            return {
                "success": False,
                "message": "Error de sincronización de datos.",
                "distance": round(distance, 4),
                "t_arcface_ms": round(t_arcface_ms, 2),
                "t_chroma_ms": round(t_chroma_ms, 2),
                "user_id": matched_id
            }
    else:
        logger.warning(f"🚫 Acceso denegado: distancia {distance:.4f} > umbral {settings.FACE_MATCH_THRESHOLD}")
        return {
            "success": False,
            "message": f"Acceso denegado. Rostro desconocido (Distancia: {distance:.2f})",
            "distance": round(distance, 4),
            "t_arcface_ms": round(t_arcface_ms, 2),
            "t_chroma_ms": round(t_chroma_ms, 2),
            "user_id": matched_id
        }


def remove_face(user_id: str) -> dict:
    """Elimina toda huella biométrica y de registro de un usuario en el sistema"""
    # 1. Eliminar datos en memoria ChromaDB
    try:
        face_collection.delete(
            ids=[user_id]
        )
        logger.info(f"🗑️ Vectores biométricos eliminados para: {user_id}")
    except Exception as e:
        logger.error(f"Error al eliminar de ChromaDB: {e}")
        return {"success": False, "message": "Error al eliminar datos biométricos"}

    # 2. Eliminar del registro SQLite
    success = delete_user(user_id)
    if not success:
        return {"success": False, "message": "El usuario no existe en la base de datos."}

    return {"success": True, "message": "Usuario y modelo biométrico eliminados con éxito."}