import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.endpoints import router as api_router
from app.services.blockchain import init_blockchain
from app.core.security import init_security

# Inicializar logging ANTES que todo lo demás
setup_logging()
logger = logging.getLogger(__name__)


# Lifecycle: se ejecuta al iniciar y al apagar el servidor
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa servicios cuando arranca el servidor."""
    # --- STARTUP ---
    logger.info("🚀 Iniciando FaceSentinel API ...")

    # Inicializar módulo de seguridad
    init_security()
    logger.info("🔐 Módulo de seguridad inicializado.")

    # Intentar conectar con la blockchain (no bloquea si falla)
    bc_ok = init_blockchain()
    if bc_ok:
        logger.info("🔗 Blockchain conectada y lista.")
    else:
        logger.warning("⚠️  Blockchain no disponible. El sistema funciona sin ella.")

    logger.info("✅ FaceSentinel API lista y esperando conexiones.")

    yield  # La aplicación corre aquí

    # --- SHUTDOWN ---
    logger.info("👋 Apagando FaceSentinel API ...")


# Inicializar la aplicación FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend de Autenticación Biométrica con inmutabilidad Web3",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)


# =========================================================================
#                       MIDDLEWARES
# =========================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción se cambia por la URL de tu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================================
#                   EXCEPTION HANDLERS GLOBALES
# =========================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Captura errores de validación y retorna un 400 limpio."""
    logger.warning(f"Validation error en {request.url.path}: {exc}")
    return JSONResponse(
        status_code=400,
        content={"success": False, "detail": str(exc)}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Captura errores inesperados y retorna un 500 con información útil."""
    logger.error(f"Error inesperado en {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "detail": "Error interno del servidor. Consulta los logs para más información."
        }
    )


# =========================================================================
#                         RUTAS
# =========================================================================

# Incluir las rutas que creamos en endpoints.py
app.include_router(api_router, prefix=settings.API_V1_STR)

# Ruta raíz para comprobar que el servidor está vivo
@app.get("/", tags=["Salud del Sistema"])
def root():
    from app.services.blockchain import is_blockchain_available
    return {
        "message": "Bienvenido a la API de FaceSentinel",
        "status": "online",
        "blockchain": "connected" if is_blockchain_available() else "disconnected",
        "docs_url": "/docs"
    }