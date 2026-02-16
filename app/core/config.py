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

    class Config:
        # Le dice a Pydantic que busque las variables en el archivo .env
        env_file = ".env"
        env_file_encoding = 'utf-8'

# Creamos una instancia global para usarla en todo el proyecto
settings = Settings()

# Crear los directorios de datos automáticamente si no existen
os.makedirs(settings.TEMP_IMAGES_PATH, exist_ok=True)
os.makedirs(os.path.dirname(settings.SQLITE_DB_PATH), exist_ok=True)
os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)