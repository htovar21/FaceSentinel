"""
logging_config.py — Configuración centralizada de logging para BioAuth-Web3
Reemplaza todos los print() por un sistema de logs profesional
con rotación de archivos y formato consistente.
"""

import os
import logging
import logging.handlers
from datetime import datetime


def setup_logging(log_level: str = "INFO"):
    """
    Configura el sistema de logging profesional.
    Debe llamarse UNA VEZ al iniciar la aplicación.
    
    Args:
        log_level: Nivel mínimo de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Crear directorio de logs
    log_dir = "./data/logs"
    os.makedirs(log_dir, exist_ok=True)

    # Formato profesional con timestamp, nivel, módulo y mensaje
    log_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Formato compacto para consola
    console_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Handler 1: Consola (siempre activo)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_format)
    console_handler.setLevel(logging.INFO)

    # Handler 2: Archivo con rotación (máximo 5 MB, guarda 5 backups)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, f"bioauth_{today}.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)

    # Handler 3: Archivo separado solo para errores
    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "errors.log"),
        maxBytes=2 * 1024 * 1024,  # 2 MB
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setFormatter(log_format)
    error_handler.setLevel(logging.ERROR)

    # Configurar el logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Limpiar handlers existentes y agregar los nuevos
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    # Silenciar loggers ruidosos de terceros
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("tensorflow").setLevel(logging.ERROR)
    logging.getLogger("mediapipe").setLevel(logging.ERROR)

    logger = logging.getLogger(__name__)
    logger.info("📋 Sistema de logging inicializado")
