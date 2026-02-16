import math
import mediapipe as mp

# Inicializamos MediaPipe Face Mesh para obtener la malla 3D del rostro
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True, 
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Índices exactos de los puntos (landmarks) de los ojos en MediaPipe
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

def _euclidean_distance(point1, point2):
    """Calcula la distancia lineal entre dos puntos espaciales."""
    return math.sqrt((point1.x - point2.x)**2 + (point1.y - point2.y)**2)

def _eye_aspect_ratio(landmarks, eye_indices):
    """
    Calcula el EAR (Eye Aspect Ratio).
    Es una fórmula científica que divide la altura del ojo entre su anchura.
    Si el ojo se cierra, la altura baja a casi 0, haciendo que el EAR caiga de golpe.
    """
    # Extraer los 6 puntos del contorno del ojo
    p1, p2, p3, p4, p5, p6 = [landmarks.landmark[i] for i in eye_indices]
    
    # Calcular las dos distancias verticales (altura del ojo)
    v1 = _euclidean_distance(p2, p6)
    v2 = _euclidean_distance(p3, p5)
    # Calcular la distancia horizontal (anchura del ojo)
    h = _euclidean_distance(p1, p4)
    
    # Aplicar la fórmula EAR
    ear = (v1 + v2) / (2.0 * h)
    return ear

def analyze_face_liveness(frame_rgb):
    """
    Analiza un frame de video y retorna si hay un rostro y su nivel de apertura de ojos.
    Retorna: (bool_hay_rostro, float_ear_promedio)
    """
    # MediaPipe procesa la imagen buscando la geometría facial
    results = face_mesh.process(frame_rgb)
    
    if not results.multi_face_landmarks:
        return False, 0.0
        
    landmarks = results.multi_face_landmarks[0]
    
    # Calculamos el EAR de ambos ojos
    left_ear = _eye_aspect_ratio(landmarks, LEFT_EYE)
    right_ear = _eye_aspect_ratio(landmarks, RIGHT_EYE)
    
    # Sacamos el promedio de apertura de ambos ojos
    avg_ear = (left_ear + right_ear) / 2.0
    return True, avg_ear