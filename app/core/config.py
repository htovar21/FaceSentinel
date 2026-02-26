import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API
    PROJECT_NAME: str = "BioAuth-Web3"
    API_V1_STR: str = "/api/v1"
    
    # Rutas
    SQLITE_DB_PATH: str = "./data/sql/database.db"
    CHROMA_DB_PATH: str = "./data/chromadb"
    TEMP_IMAGES_PATH: str = "./data/temp_images"
    
    # IA
    AI_MODEL_NAME: str = "ArcFace"
    FACE_MATCH_THRESHOLD: float = 0.68
    
    # Web3
    BLOCKCHAIN_RPC_URL: str = "http://127.0.0.1:7545"
    CHAIN_ID: int = 5777
    SMART_CONTRACT_ADDRESS: str = ""
    DEVICE_PRIVATE_KEY: str = ""

    # Seguridad — JWT
    JWT_SECRET_KEY: str = "bioauth-web3-super-secret-key-change-in-production"
    JWT_EXPIRATION_MINUTES: int = 60

    # Seguridad — Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 30

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        # Ignorar variables del .env que no estén definidas en esta clase
        # (ej: WEB3_PROVIDER_URI, ADMIN_ADDRESS, ADMIN_PRIVATE_KEY son leídas por otros módulos con os.getenv)
        "extra": "ignore",
    }

# Creamos una instancia global para usarla en todo el proyecto
settings = Settings()

# Crear los directorios de datos automáticamente si no existen
os.makedirs(settings.TEMP_IMAGES_PATH, exist_ok=True)
os.makedirs(os.path.dirname(settings.SQLITE_DB_PATH), exist_ok=True)
os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)