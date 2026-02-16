from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.endpoints import router as api_router

# Inicializar la aplicación FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend de Autenticación Biométrica con inmutabilidad Web3",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Configurar CORS (Vital para que el Frontend en React o JS pueda comunicarse sin bloqueos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción se cambia por la URL de tu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir las rutas que creamos en endpoints.py
app.include_router(api_router, prefix=settings.API_V1_STR)

# Ruta raíz para comprobar que el servidor está vivo
@app.get("/", tags=["Salud del Sistema"])
def root():
    return {
        "message": "Bienvenido a la API de BioAuth-Web3", 
        "status": "online",
        "docs_url": "/docs"
    }