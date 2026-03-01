"""
security.py — Módulo de Seguridad para FaceSentinel
Implementa JWT, API Keys, y protección de endpoints.
"""

import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# =========================================================================
#                        CONFIGURACIÓN JWT
# =========================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", settings.JWT_SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))

# Esquemas de seguridad para FastAPI/Swagger
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# =========================================================================
#                      FUNCIONES JWT
# =========================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Genera un JSON Web Token (JWT) con los datos proporcionados.

    Args:
        data: Payload del token (ej. {"sub": "admin", "role": "admin"})
        expires_delta: Tiempo de expiración personalizado

    Returns:
        Token JWT codificado como string
    """
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=JWT_EXPIRATION_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    token = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.info(f"🔑 Token JWT generado para: {data.get('sub', 'unknown')}")
    return token


def verify_token(token: str) -> dict:
    """
    Verifica y decodifica un JWT.

    Args:
        token: El JWT a verificar

    Returns:
        Payload decodificado del token

    Raises:
        HTTPException si el token es inválido o expirado
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. Solicita uno nuevo.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )


# =========================================================================
#                      SISTEMA DE API KEYS
# =========================================================================

def generate_api_key() -> str:
    """Genera una API Key segura de 64 caracteres hex."""
    return secrets.token_hex(32)


def hash_api_key(api_key: str) -> str:
    """Hashea una API Key con SHA-256 para almacenamiento seguro."""
    return hashlib.sha256(api_key.encode()).hexdigest()


# Las API Keys autorizadas se guardan aquí (en producción usar BD)
# El hash de la key se compara con el hash almacenado
_authorized_api_keys: dict[str, dict] = {}


def register_api_key(name: str, role: str = "device") -> str:
    """
    Registra una nueva API Key para un dispositivo.

    Args:
        name: Nombre descriptivo del dispositivo
        role: Rol del dispositivo (device, admin)

    Returns:
        La API Key generada (se muestra solo una vez)
    """
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    _authorized_api_keys[key_hash] = {
        "name": name,
        "role": role,
        "created": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"🔐 API Key registrada para dispositivo: {name}")
    return raw_key


def validate_api_key(api_key: str) -> Optional[dict]:
    """
    Valida una API Key contra las keys registradas.

    Returns:
        Info del dispositivo si es válida, None si no lo es
    """
    key_hash = hash_api_key(api_key)
    return _authorized_api_keys.get(key_hash)


# =========================================================================
#               DEPENDENCIES DE FASTAPI (Proteger Endpoints)
# =========================================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    """
    Dependency de FastAPI que protege un endpoint.
    Acepta autenticación por JWT (Bearer token) O por API Key (X-API-Key header).

    Uso en un endpoint:
        @router.post("/protected")
        def my_endpoint(user: dict = Depends(get_current_user)):
            ...

    Returns:
        dict con la info del usuario/dispositivo autenticado
    """
    # Opción 1: JWT Bearer Token
    if credentials and credentials.credentials:
        payload = verify_token(credentials.credentials)
        return {
            "auth_method": "jwt",
            "sub": payload.get("sub"),
            "role": payload.get("role", "user"),
        }

    # Opción 2: API Key
    if api_key:
        device_info = validate_api_key(api_key)
        if device_info:
            return {
                "auth_method": "api_key",
                "sub": device_info["name"],
                "role": device_info["role"],
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida.",
        )

    # Ninguno proporcionado
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación requerida. Usa Bearer token o X-API-Key.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency que solo permite acceso a administradores.
    Se encadena con get_current_user.
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador.",
        )
    return user


# =========================================================================
#                INICIALIZACIÓN (crear API Key por defecto)
# =========================================================================

def init_security():
    """
    Inicializa el módulo de seguridad.
    Crea una API Key por defecto para desarrollo si no hay ninguna.
    """
    if not _authorized_api_keys:
        # En desarrollo, creamos una key por defecto
        default_key = os.getenv("DEFAULT_API_KEY", "")
        if default_key:
            key_hash = hash_api_key(default_key)
            _authorized_api_keys[key_hash] = {
                "name": "default-dev-device",
                "role": "admin",
                "created": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("🔐 API Key por defecto cargada desde .env")
        else:
            logger.info("ℹ️  No hay API Keys configuradas. Usa POST /api/v1/admin/generate-key para crear una.")
