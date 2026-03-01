"""
image_processing.py — Utilidades de Preprocesamiento de Imagen para FaceSentinel
Funciones para normalizar, limpiar, y validar imágenes antes de pasarlas al motor de IA.
"""

import base64
import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# =========================================================================
#                 CONSTANTES DE VALIDACIÓN
# =========================================================================

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024   # 10 MB máximo
MIN_IMAGE_DIMENSION = 100                  # Mínimo 100x100 px
MAX_IMAGE_DIMENSION = 4096                 # Máximo 4096x4096 px
TARGET_SIZE = (224, 224)                   # Tamaño objetivo para el modelo


# =========================================================================
#              CONVERSIÓN Y VALIDACIÓN
# =========================================================================

def decode_base64_image(base64_string: str) -> np.ndarray:
    """
    Decodifica una imagen Base64 a formato OpenCV (numpy array).
    
    Args:
        base64_string: Imagen codificada en Base64 (puede incluir header data:image/...)
    
    Returns:
        Imagen como numpy array en formato BGR
    
    Raises:
        ValueError: Si la imagen es inválida, muy grande, o tiene dimensiones incorrectas
    """
    # Remover header de data URI si existe
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    
    # Validar tamaño del payload
    estimated_size = len(base64_string) * 3 / 4
    if estimated_size > MAX_IMAGE_SIZE_BYTES:
        raise ValueError(
            f"Imagen demasiado grande: {estimated_size / 1024 / 1024:.1f} MB "
            f"(máximo {MAX_IMAGE_SIZE_BYTES / 1024 / 1024:.0f} MB)"
        )
    
    try:
        img_data = base64.b64decode(base64_string)
    except Exception:
        raise ValueError("La imagen no tiene un formato Base64 válido")
    
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("No se pudo decodificar la imagen. Formato no soportado.")
    
    # Validar dimensiones
    h, w = img.shape[:2]
    if h < MIN_IMAGE_DIMENSION or w < MIN_IMAGE_DIMENSION:
        raise ValueError(
            f"Imagen muy pequeña: {w}x{h} px "
            f"(mínimo {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION} px)"
        )
    if h > MAX_IMAGE_DIMENSION or w > MAX_IMAGE_DIMENSION:
        raise ValueError(
            f"Imagen muy grande: {w}x{h} px "
            f"(máximo {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} px)"
        )
    
    return img


def encode_image_to_base64(img: np.ndarray, format: str = ".jpg", quality: int = 90) -> str:
    """
    Codifica una imagen OpenCV a Base64.
    
    Args:
        img: Imagen como numpy array BGR
        format: Formato de salida (.jpg, .png)
        quality: Calidad JPEG (1-100)
    
    Returns:
        String Base64 de la imagen
    """
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality] if format == ".jpg" else []
    _, buffer = cv2.imencode(format, img, encode_params)
    return base64.b64encode(buffer).decode("utf-8")


# =========================================================================
#              NORMALIZACIÓN Y MEJORA
# =========================================================================

def normalize_illumination(img: np.ndarray) -> np.ndarray:
    """
    Normaliza la iluminación usando CLAHE (Contrast Limited Adaptive Histogram Equalization).
    Mejora imágenes tomadas con mala iluminación sin sobreexplotar el contraste.
    
    Args:
        img: Imagen BGR
    
    Returns:
        Imagen BGR con iluminación normalizada
    """
    # Convertir a LAB (separar luminancia de color)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Aplicar CLAHE solo al canal de luminancia
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_normalized = clahe.apply(l)
    
    # Recombinar canales
    lab_normalized = cv2.merge([l_normalized, a, b])
    result = cv2.cvtColor(lab_normalized, cv2.COLOR_LAB2BGR)
    
    return result


def align_face(img: np.ndarray) -> np.ndarray:
    """
    Alinea el rostro basado en la posición de los ojos.
    Rota la imagen para que los ojos queden en línea horizontal,
    mejorando la precisión del reconocimiento.
    
    Args:
        img: Imagen BGR con un rostro
    
    Returns:
        Imagen BGR con el rostro alineado
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Usar detector de ojos de OpenCV
    eye_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_eye.xml'
    )
    
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0:
        return img  # No se detectó rostro, retornar original
    
    x, y, w, h = faces[0]
    roi_gray = gray[y:y+h, x:x+w]
    
    eyes = eye_cascade.detectMultiScale(roi_gray)
    if len(eyes) < 2:
        return img  # No se detectan ambos ojos, retornar original
    
    # Tomar los dos ojos más prominentes
    eyes = sorted(eyes, key=lambda e: e[2] * e[3], reverse=True)[:2]
    
    # Calcular ángulo de rotación
    eye1 = (eyes[0][0] + eyes[0][2] // 2, eyes[0][1] + eyes[0][3] // 2)
    eye2 = (eyes[1][0] + eyes[1][2] // 2, eyes[1][1] + eyes[1][3] // 2)
    
    dy = eye2[1] - eye1[1]
    dx = eye2[0] - eye1[0]
    angle = np.degrees(np.arctan2(dy, dx))
    
    # Rotar imagen
    h_img, w_img = img.shape[:2]
    center = (w_img // 2, h_img // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(img, M, (w_img, h_img))
    
    return rotated


def resize_for_model(img: np.ndarray, target_size: tuple = TARGET_SIZE) -> np.ndarray:
    """
    Redimensiona la imagen al tamaño esperado por el modelo.
    Mantiene la relación de aspecto y agrega padding si es necesario.
    
    Args:
        img: Imagen BGR
        target_size: Tupla (width, height)
    
    Returns:
        Imagen redimensionada
    """
    h, w = img.shape[:2]
    target_w, target_h = target_size
    
    # Calcular factor de escala preservando aspect ratio
    scale = min(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    # Padding con negro para alcanzar el tamaño objetivo
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    y_offset = (target_h - new_h) // 2
    x_offset = (target_w - new_w) // 2
    canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized
    
    return canvas


# =========================================================================
#             DETECCIÓN DE CALIDAD DE IMAGEN
# =========================================================================

def assess_image_quality(img: np.ndarray) -> dict:
    """
    Evalúa la calidad de una imagen facial.
    Detecta problemas comunes: blur, subexposición, sobreexposición.
    
    Args:
        img: Imagen BGR
    
    Returns:
        dict con scores de calidad y recomendaciones
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Detección de blur (Laplaciano)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    is_blurry = laplacian_var < 100  # Umbral empírico
    
    # 2. Exposición (brillo promedio)
    mean_brightness = np.mean(gray)
    is_underexposed = mean_brightness < 50
    is_overexposed = mean_brightness > 220
    
    # 3. Contraste (desviación estándar)
    contrast = np.std(gray)
    low_contrast = contrast < 30
    
    # Score general de calidad (0-1)
    quality_score = 1.0
    issues = []
    
    if is_blurry:
        quality_score -= 0.3
        issues.append("Imagen borrosa — Mantén la cámara estable")
    
    if is_underexposed:
        quality_score -= 0.3
        issues.append("Imagen muy oscura — Mejora la iluminación")
    
    if is_overexposed:
        quality_score -= 0.3
        issues.append("Imagen sobreexpuesta — Reduce la luz directa")
    
    if low_contrast:
        quality_score -= 0.2
        issues.append("Bajo contraste — Verifica la iluminación")
    
    quality_score = max(0.0, quality_score)
    
    return {
        "quality_score": round(quality_score, 4),
        "is_acceptable": quality_score >= 0.5,
        "blur_score": round(laplacian_var, 2),
        "brightness": round(mean_brightness, 2),
        "contrast": round(contrast, 2),
        "issues": issues,
    }


# =========================================================================
#              PIPELINE COMPLETO DE PREPROCESAMIENTO
# =========================================================================

def preprocess_face(img: np.ndarray) -> tuple:
    """
    Pipeline completo de preprocesamiento facial.
    Ejecuta todos los pasos de mejora y validación.
    
    Args:
        img: Imagen BGR cruda
    
    Returns:
        tuple de (imagen_procesada, quality_report)
    """
    # Paso 1: Evaluar calidad
    quality = assess_image_quality(img)
    
    # Paso 2: Normalizar iluminación
    img_normalized = normalize_illumination(img)
    
    # Paso 3: Alinear rostro
    img_aligned = align_face(img_normalized)
    
    return img_aligned, quality
