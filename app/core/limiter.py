"""
limiter.py — Instancia central de rate limiting usando slowapi.
Separado en app.core para evitar dependencias circulares entre app.main y app.api.endpoints.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
