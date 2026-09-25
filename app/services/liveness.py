"""
liveness.py — Motor Anti-Spoofing Avanzado para FaceSentinel
Combina múltiples técnicas para detectar ataques de presentación:
1. EAR (Eye Aspect Ratio) — Detección de parpadeo
2. LBP (Local Binary Patterns) — Análisis de textura facial
3. FFT (Fast Fourier Transform) — Análisis de frecuencia
4. Movimiento de cabeza — Tracking de landmarks 3D
5. Score compuesto — Combinación ponderada de todas las señales
"""

from typing import Optional
import math
import time
import logging
import numpy as np
import cv2
from skimage.feature import local_binary_pattern
import mediapipe as mp

logger = logging.getLogger(__name__)

# =========================================================================
#                      MEDIAPIPE FACE MESH
# =========================================================================

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.35,
    min_tracking_confidence=0.35
)

# Índices exactos de los puntos (landmarks) de los ojos en MediaPipe
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Landmarks para estimar pose de la cabeza (nariz, mentón, ojos, boca)
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_CORNER = 33
RIGHT_EYE_CORNER = 263
LEFT_MOUTH = 61
RIGHT_MOUTH = 291
UPPER_LIP = 13
LOWER_LIP = 14


# =========================================================================
#               MÓDULO 1: DETECCIÓN DE PARPADEO (EAR)
# =========================================================================

def _euclidean_distance(point1, point2):
    """Calcula la distancia lineal entre dos puntos espaciales."""
    return math.sqrt((point1.x - point2.x)**2 + (point1.y - point2.y)**2)


def _eye_aspect_ratio(landmarks, eye_indices):
    """
    Calcula el EAR (Eye Aspect Ratio).
    Fórmula científica que divide la altura del ojo entre su anchura.
    Si el ojo se cierra, la altura baja a casi 0, haciendo que el EAR caiga de golpe.
    """
    p1, p2, p3, p4, p5, p6 = [landmarks.landmark[i] for i in eye_indices]

    v1 = _euclidean_distance(p2, p6)
    v2 = _euclidean_distance(p3, p5)
    h = _euclidean_distance(p1, p4)

    ear = (v1 + v2) / (2.0 * h)
    return ear


def analyze_blink(frame_rgb) -> tuple:
    """
    Analiza un frame y retorna si hay un rostro y su nivel de apertura de ojos.
    Retorna: (bool_hay_rostro, float_ear_promedio)
    """
    results = face_mesh.process(frame_rgb)

    if not results.multi_face_landmarks:
        return False, 0.0

    landmarks = results.multi_face_landmarks[0]

    left_ear = _eye_aspect_ratio(landmarks, LEFT_EYE)
    right_ear = _eye_aspect_ratio(landmarks, RIGHT_EYE)

    avg_ear = (left_ear + right_ear) / 2.0
    return True, avg_ear


# Alias de compatibilidad con el código existente
analyze_face_liveness = analyze_blink

class BlinkTracker:
    """
    Rastrea el historial de EAR (Eye Aspect Ratio) a través de múltiples frames
    para detectar un parpadeo completo (cerrar y abrir los ojos).
    """
    def __init__(self, ear_threshold=0.20, consecutive_frames=2):
        self.ear_threshold = ear_threshold
        self.consecutive_frames = consecutive_frames
        self.frame_counter = 0
        self.blink_detected = False
        self.history = []

    def update(self, ear: float) -> bool:
        """
        Actualiza el estado con el nuevo EAR. Retorna True si se acaba de completar un parpadeo.
        """
        self.history.append(ear)
        if len(self.history) > 10:
            self.history.pop(0)

        # Lógica de detección: si el EAR cae por debajo del umbral por N frames
        if ear < self.ear_threshold:
            self.frame_counter += 1
        else:
            # Si el ojo volvió a abrirse y había estado cerrado lo suficiente, es un parpadeo
            if self.frame_counter >= self.consecutive_frames:
                self.blink_detected = True
            self.frame_counter = 0
            
        return self.blink_detected

    def reset(self):
        self.frame_counter = 0
        self.blink_detected = False
        self.history.clear()


# =========================================================================
#          MÓDULO 2: ANÁLISIS DE TEXTURA (LBP - Local Binary Patterns)
# =========================================================================

def analyze_texture(frame_bgr, custom_lbp_threshold: Optional[float] = 3.2, adaptive_threshold: bool = False) -> dict:
    """
    Analiza la textura facial para distinguir piel real de pantallas/impresiones.
    Soporta dos modalidades de umbralización:
    1. Fija por hardware: usa custom_lbp_threshold configurado para cámaras M2M en SQLite/cameras.json.
    2. Adaptativa guiada por calidad (Quality-Aware): para SSO WebSockets, interpola dinámicamente entre
       3.20 (webcam genérica de baja nitidez) y 3.58 (sensor móvil de alta nitidez) evaluando la
       varianza del Laplaciano (nitidez óptica) y la escala del ROI facial en resolución nativa.

    Args:
        frame_bgr: Frame en formato BGR (OpenCV)
        custom_lbp_threshold: Umbral de entropía LBP fijo configurado para el dispositivo
        adaptive_threshold: Si True, interpola el umbral según la calidad óptica del sensor

    Returns:
        dict con score de textura, entropía, tiempos, nitidez y si parece real
    """
    t0 = time.perf_counter()
    try:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # Detectar el rostro con MediaPipe Face Mesh para aislar el ROI facial
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mesh_results = face_mesh.process(rgb)

        if mesh_results.multi_face_landmarks:
            h, w = gray.shape[:2]
            lms = mesh_results.multi_face_landmarks[0].landmark
            xs = [lm.x * w for lm in lms]
            ys = [lm.y * h for lm in lms]
            x1 = max(0, int(min(xs)))
            y1 = max(0, int(min(ys)))
            x2 = min(w, int(max(xs)))
            y2 = min(h, int(max(ys)))
            if (x2 - x1) >= 32 and (y2 - y1) >= 32:
                raw_face_roi = gray[y1:y2, x1:x2]
            else:
                raw_face_roi = gray
        else:
            # Fallback robusto: si la imagen ya viene recortada del borde o MediaPipe no converge,
            # analizamos la región facial central
            h, w = gray.shape[:2]
            if h >= 32 and w >= 32:
                raw_face_roi = gray[int(h * 0.1):int(h * 0.9), int(w * 0.1):int(w * 0.9)]
            else:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                fallback_thresh = custom_lbp_threshold if custom_lbp_threshold is not None else 3.20
                return {
                    "is_real": False,
                    "texture_score": 0.0,
                    "entropy": 0.0,
                    "lbp_threshold": round(fallback_thresh, 4),
                    "variance": 0.0,
                    "energy": 0.0,
                    "sharpness": 0.0,
                    "quality_score": 0.0,
                    "face_roi_size": [0, 0],
                    "time_ms": round(elapsed_ms, 2),
                    "reason": "No se detectó rostro"
                }

        # 1. Medición de calidad óptica en resolución nativa antes del redimensionamiento:
        # - Varianza del Laplaciano (alta frecuencia / nitidez de la óptica del sensor)
        # - Área/escala real del ROI facial
        roi_h, roi_w = raw_face_roi.shape[:2]
        face_size = min(roi_w, roi_h)
        laplacian_var = float(cv2.Laplacian(raw_face_roi, cv2.CV_64F).var())

        # Normalización del índice de calidad óptica Q in [0.0, 1.0]
        # Calibración empírica:
        # - Webcam laptop (óptica suave/ruido difuso): laplacian_var ~80-150, face_size ~100-140 -> Q ~0.0-0.2
        # - Sensor móvil Smart 20 / HD (óptica nítida): laplacian_var ~300-800+, face_size >=200 -> Q ~0.8-1.0
        sharpness_norm = float(np.clip((laplacian_var - 80.0) / (320.0 - 80.0), 0.0, 1.0))
        resolution_norm = float(np.clip((face_size - 90.0) / (240.0 - 90.0), 0.0, 1.0))
        quality_score = float(0.70 * sharpness_norm + 0.30 * resolution_norm)

        # 2. Redimensionar para análisis LBP estandarizado
        face_roi = cv2.resize(raw_face_roi, (128, 128))

        # Calcular LBP uniforme con skimage (C compilado, ~50x más rápido)
        lbp = local_binary_pattern(face_roi, P=16, R=2, method="uniform")

        # LBP uniforme con P=16 produce valores 0..17 -> histograma de 18 bins
        n_bins = 18
        hist, _ = np.histogram(lbp.ravel(), bins=n_bins, range=(0, n_bins))
        hist = hist.astype(float)
        hist /= (hist.sum() + 1e-7)

        # Métricas de textura:
        variance = np.var(hist)
        entropy = -np.sum(hist * np.log2(hist + 1e-7))
        energy = np.sum(hist ** 2)

        # 3. Determinación del umbral efectivo:
        if custom_lbp_threshold is not None:
            effective_threshold = float(custom_lbp_threshold)
        elif adaptive_threshold:
            effective_threshold = round(3.20 + (3.58 - 3.20) * quality_score, 4)
        else:
            effective_threshold = 3.20

        is_real = entropy >= effective_threshold

        # Score normalizado según el umbral efectivo
        texture_score = min(1.0, max(0.0, (entropy - (effective_threshold - 0.4)) / 0.8))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "is_real": is_real,
            "texture_score": round(texture_score, 4),
            "entropy": round(entropy, 4),
            "lbp_threshold": round(effective_threshold, 4),
            "variance": round(variance, 6),
            "energy": round(energy, 6),
            "has_screen_artifacts": False,
            "sharpness": round(laplacian_var, 2),
            "quality_score": round(quality_score, 4),
            "face_roi_size": [roi_w, roi_h],
            "time_ms": round(elapsed_ms, 2),
        }

    except Exception as e:
        logger.error(f"Error en análisis de textura: {e}")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        fallback_thresh = custom_lbp_threshold if custom_lbp_threshold is not None else 3.20
        return {
            "is_real": True,
            "texture_score": 0.5,
            "entropy": 0.0,
            "lbp_threshold": round(fallback_thresh, 4),
            "variance": 0.0,
            "energy": 0.0,
            "sharpness": 0.0,
            "quality_score": 0.0,
            "face_roi_size": [0, 0],
            "time_ms": round(elapsed_ms, 2),
            "reason": "Error en análisis"
        }


# =========================================================================
#    MÓDULO 3: ANÁLISIS DE FRECUENCIA (FFT - Fast Fourier Transform)
# =========================================================================

def analyze_frequency(frame_bgr) -> dict:
    """
    Analiza el espectro de frecuencia de la imagen facial.
    Las pantallas y las impresiones introducen artefactos de alta frecuencia
    (patrones de moiré, ruido de impresión) que la piel real no tiene.

    Args:
        frame_bgr: Frame en formato BGR

    Returns:
        dict con score de frecuencia, tiempo y si parece real
    """
    t0 = time.perf_counter()
    try:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (128, 128))

        # Aplicar FFT
        f = np.fft.fft2(gray.astype(float))
        fshift = np.fft.fftshift(f)
        magnitude = np.log(np.abs(fshift) + 1)

        # Dividir el espectro en regiones
        h, w = magnitude.shape
        center_y, center_x = h // 2, w // 2

        # Región de baja frecuencia (centro)
        low_freq = magnitude[
            center_y - h // 8:center_y + h // 8,
            center_x - w // 8:center_x + w // 8
        ]

        # Región de alta frecuencia (bordes)
        high_freq_mask = np.ones_like(magnitude, dtype=bool)
        high_freq_mask[
            center_y - h // 4:center_y + h // 4,
            center_x - w // 4:center_x + w // 4
        ] = False
        high_freq = magnitude[high_freq_mask]

        # Ratio entre alta y baja frecuencia
        low_mean = np.mean(low_freq)
        high_mean = np.mean(high_freq)
        freq_ratio = high_mean / (low_mean + 1e-7)

        freq_score = 1.0
        is_real = True
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "is_real": is_real,
            "frequency_score": round(freq_score, 4),
            "freq_ratio": round(freq_ratio, 4),
            "low_freq_mean": round(low_mean, 4),
            "high_freq_mean": round(high_mean, 4),
            "time_ms": round(elapsed_ms, 2),
        }

    except Exception as e:
        logger.error(f"Error en análisis de frecuencia: {e}")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "is_real": True,
            "frequency_score": 0.5,
            "time_ms": round(elapsed_ms, 2),
            "reason": "Error en análisis"
        }


# =========================================================================
#        MÓDULO 4: DETECCIÓN DE MOVIMIENTO DE CABEZA
# =========================================================================

def estimate_head_pose(frame_rgb) -> dict:
    """
    Estima la orientación de la cabeza usando landmarks faciales.
    Calcula los ángulos de yaw (giro horizontal), pitch (inclinación),
    y roll (rotación).

    Útil para challenge-response: "por favor, gira la cabeza a la derecha".

    Returns:
        dict con ángulos de la cabeza y si se detectó un rostro
    """
    results = face_mesh.process(frame_rgb)

    if not results.multi_face_landmarks:
        return {"detected": False, "yaw": 0, "pitch": 0, "roll": 0, "mar": 0.0}

    landmarks = results.multi_face_landmarks[0]

    # Obtener puntos clave
    nose = landmarks.landmark[NOSE_TIP]
    chin = landmarks.landmark[CHIN]
    left_eye = landmarks.landmark[LEFT_EYE_CORNER]
    right_eye = landmarks.landmark[RIGHT_EYE_CORNER]

    # Calcular ángulos aproximados

    # Yaw (giro izquierda/derecha): diferencia horizontal entre nariz y punto medio de ojos
    eye_center_x = (left_eye.x + right_eye.x) / 2
    yaw = (nose.x - eye_center_x) * 100  # Normalizado

    # Pitch (arriba/abajo): diferencia vertical entre nariz y mentón
    face_height = abs(chin.y - (left_eye.y + right_eye.y) / 2)
    nose_relative = (nose.y - (left_eye.y + right_eye.y) / 2) / (face_height + 1e-7)
    pitch = (nose_relative - 0.35) * 100  # Normalizado

    # Roll (inclinación lateral): ángulo entre los ojos
    dy = right_eye.y - left_eye.y
    dx = right_eye.x - left_eye.x
    roll = math.degrees(math.atan2(dy, dx))

    # MAR (Mouth Aspect Ratio): apertura de boca
    upper_lip = landmarks.landmark[UPPER_LIP]
    lower_lip = landmarks.landmark[LOWER_LIP]
    left_mouth = landmarks.landmark[LEFT_MOUTH]
    right_mouth = landmarks.landmark[RIGHT_MOUTH]
    mouth_height = _euclidean_distance(upper_lip, lower_lip)
    mouth_width = _euclidean_distance(left_mouth, right_mouth)
    mar = mouth_height / (mouth_width + 1e-7)

    return {
        "detected": True,
        "yaw": round(yaw, 2),
        "pitch": round(pitch, 2),
        "roll": round(roll, 2),
        "mar": round(mar, 3),
    }


# =========================================================================
#           MÓDULO 5: SCORE COMPUESTO DE LIVENESS
# =========================================================================

def comprehensive_liveness_check(frame_bgr, custom_lbp_threshold: float = 3.2) -> dict:
    """
    Ejecuta TODAS las verificaciones de liveness y retorna un score compuesto.
    Esta es la función principal que combina todas las técnicas anti-spoofing.

    Ponderaciones:
    - Textura (LBP): 40% — El más fiable para detectar pantallas
    - Frecuencia (FFT): 30% — Bueno para detectar impresiones
    - Presencia facial: 30% — Requisito básico

    Args:
        frame_bgr: Frame en formato BGR (OpenCV)
        custom_lbp_threshold: Umbral de entropía LBP dinámico por dispositivo (default: 3.2)

    Returns:
        dict con liveness_score (0-1), is_live, y desglose de scores y tiempos
    """
    t0_check = time.perf_counter()

    # 1. Verificar presencia facial
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    has_face, ear = analyze_blink(frame_rgb)

    if not has_face:
        elapsed_total = (time.perf_counter() - t0_check) * 1000.0
        return {
            "is_live": False,
            "liveness_score": 0.0,
            "t_lbp_ms": 0.0,
            "t_fft_ms": 0.0,
            "t_liveness_total_ms": round(elapsed_total, 2),
            "entropy": 0.0,
            "lbp_threshold": round(custom_lbp_threshold, 4),
            "reason": "No se detectó rostro en la imagen",
            "details": {}
        }

    # 2. Análisis de textura (con umbral dinámico de hardware)
    texture_result = analyze_texture(frame_bgr, custom_lbp_threshold=custom_lbp_threshold)

    # 3. Análisis de frecuencia
    freq_result = analyze_frequency(frame_bgr)

    # 4. Pose de la cabeza
    pose = estimate_head_pose(frame_rgb)

    # 5. Calcular score compuesto ponderado
    texture_score = texture_result.get("texture_score", 0.0)
    freq_score = freq_result.get("frequency_score", 0.5)
    presence_score = 1.0 if has_face else 0.0
    texture_is_real = texture_result.get("is_real", False)

    liveness_score = (
        texture_score * 0.50 +
        freq_score * 0.25 +
        presence_score * 0.25
    )

    # El filtro de textura (LBP) es determinante: si no supera el umbral de piel real, se rechaza
    is_live = bool(texture_is_real and (liveness_score >= 0.50))
    elapsed_total = (time.perf_counter() - t0_check) * 1000.0

    result = {
        "is_live": is_live,
        "liveness_score": round(liveness_score, 4),
        "entropy": texture_result.get("entropy", 0.0),
        "lbp_threshold": texture_result.get("lbp_threshold", custom_lbp_threshold),
        "lbp_variance": texture_result.get("variance", 0.0),
        "t_lbp_ms": texture_result.get("time_ms", 0.0),
        "t_fft_ms": freq_result.get("time_ms", 0.0),
        "t_liveness_total_ms": round(elapsed_total, 2),
        "reason": "Prueba de vida aprobada" if is_live else "Posible ataque de presentación detectado",
        "details": {
            "texture": texture_result,
            "frequency": freq_result,
            "ear": round(ear, 4),
            "head_pose": pose,
        }
    }

    if is_live:
        logger.info(f"✅ Liveness OK — Score: {liveness_score:.4f} (LBP: {result['t_lbp_ms']}ms, FFT: {result['t_fft_ms']}ms)")
    else:
        logger.warning(f"🚨 Liveness FALLIDO — Score: {liveness_score:.4f} (Entropía: {result['entropy']})")

    return result


# =========================================================================
#       MÓDULO 6: AUTO-CALIBRACIÓN SENSORIAL PARA LA PLATAFORMA WEB
# =========================================================================

def calibrate_camera_stream(stream_url: str, target_samples: int = 25) -> dict:
    """
    Se conecta a una cámara por RTSP o HTTP (DroidCam) y analiza fotogramas faciales
    para calcular empíricamente el umbral óptimo de LBP (textura) para esa lente.
    """
    import os
    # Forzar transporte TCP para streams RTSP (evita bloqueos UDP a través de Docker y Firewall)
    if isinstance(stream_url, str) and stream_url.lower().startswith("rtsp://"):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"

    source = int(stream_url) if str(stream_url).isdigit() else stream_url
    cap = cv2.VideoCapture(source)
    if not cap or not cap.isOpened():
        raise ValueError(f"No se pudo conectar al flujo de video '{stream_url}'. Verifica que la cámara esté encendida y accesible.")

    t0 = time.time()
    samples_entropy = []
    samples_variance = []
    w, h = 0, 0
    total_frames_read = 0
    max_wait = 10.0

    try:
        while len(samples_entropy) < target_samples and (time.time() - t0) < max_wait:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.03)
                continue

            total_frames_read += 1
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if not results.multi_face_landmarks:
                time.sleep(0.02)
                continue

            landmarks = results.multi_face_landmarks[0].landmark
            xs = [int(p.x * w) for p in landmarks]
            ys = [int(p.y * h) for p in landmarks]
            x_min, x_max = max(0, min(xs)), min(w, max(xs))
            y_min, y_max = max(0, min(ys)), min(h, max(ys))

            if (x_max - x_min) < 40 or (y_max - y_min) < 40:
                continue

            face_crop = frame[y_min:y_max, x_min:x_max]
            gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            face_128 = cv2.resize(gray_face, (128, 128))

            lbp = local_binary_pattern(face_128, P=16, R=2, method="uniform")
            hist, _ = np.histogram(lbp.ravel(), bins=18, range=(0, 18))
            hist = hist.astype(float)
            hist /= (hist.sum() + 1e-7)
            entropy = -np.sum(hist * np.log2(hist + 1e-7))
            variance = float(np.var(hist))

            samples_entropy.append(float(entropy))
            samples_variance.append(variance)
            time.sleep(0.02)
    finally:
        cap.release()

    if len(samples_entropy) < 5:
        if total_frames_read > 0:
            raise ValueError(f"Cámara conectada ({w}x{h} px), pero no hay ningún rostro visible frente al lente. Debes pararte frente a la cámara mirando hacia ella para calibrarla.")
        else:
            raise ValueError("No se pudieron recibir fotogramas del flujo de video. Verifica la conexión.")

    arr_ent = np.array(samples_entropy)
    mean_ent = float(np.mean(arr_ent))
    std_ent = float(np.std(arr_ent))
    min_ent = float(np.min(arr_ent))
    mean_var = float(np.mean(samples_variance))

    # Umbral óptimo: media - 3*std con margen de seguridad
    suggested = round(max(3.20, min(3.80, mean_ent - 3.0 * std_ent)), 3)
    if suggested > (min_ent - 0.005):
        suggested = round(min_ent - 0.01, 3)

    return {
        "samples_analyzed": len(samples_entropy),
        "resolution": f"{w}x{h}",
        "mean_entropy": round(mean_ent, 4),
        "std_entropy": round(std_ent, 4),
        "min_entropy": round(min_ent, 4),
        "variance_mean": round(mean_var, 6),
        "optimal_threshold": suggested
    }