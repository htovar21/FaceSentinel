from pydantic import BaseModel
from typing import Optional

# Lo que el sistema espera recibir cuando registras a un usuario nuevo
class UserRegister(BaseModel):
    user_id: str
    name: str
    role: str
    image_base64: str  # La foto capturada por la cámara

# Lo que el sistema espera recibir cuando alguien intenta entrar
class AuthRequest(BaseModel):
    image_base64: str

# Lo que tu sistema le responderá al Frontend o a la puerta
class AuthResponse(BaseModel):
    success: bool
    message: str
    user_name: Optional[str] = None
    role: Optional[str] = None      
    match_score: Optional[float] = None
    tx_hash: Optional[str] = None  # El recibo de la Blockchain