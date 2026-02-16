# --- Núcleo de IA y Visión Artificial ---
deepface>=0.0.90      # Framework principal para reconocimiento facial (ArcFace, FaceNet, etc.)
opencv-python>=4.8.0  # Captura de cámara y procesamiento de imágenes (cv2)
mediapipe>=0.10.9     # Detección de malla facial y prueba de vida (Anti-spoofing)
tf-keras>=2.15.0      # Backend de Deep Learning necesario para DeepFace

# --- Bases de Datos (Vectorial y Relacional) ---
chromadb>=0.4.22      # Base de datos vectorial local para guardar los embeddings
pysqlite3-binary      # (Opcional) Parche para SQLite si tu sistema tiene una versión vieja

# --- Backend y API ---
fastapi>=0.109.0      # Framework para crear la API del sistema
uvicorn[standard]     # Servidor ASGI para ejecutar FastAPI
pydantic>=2.5.0       # Validación de datos (Schema enforcement)
pydantic-settings     # Gestión de variables de entorno (.env) en Pydantic v2
python-multipart      # Necesario para que FastAPI reciba imágenes (archivos)

# --- Blockchain y Web3 ---
web3>=6.15.0          # Conexión con Ethereum/Polygon/Ganache y Smart Contracts
eth-account>=0.11.0   # Gestión de billeteras y firma de transacciones locales

# --- Utilidades y Entorno ---
python-dotenv>=1.0.0  # Cargar claves privadas y config desde archivo .env
numpy>=1.26.0         # Manejo de arrays matemáticos (imágenes y vectores)
requests              # Para hacer peticiones HTTP si fuera necesario
pandas                # Manipulación de datos (dependencia de DeepFace, bueno tenerla explícita)