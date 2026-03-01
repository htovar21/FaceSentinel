from pydantic import BaseModel
from typing import Optional, List

# =========================================================================
#                   SCHEMAS DE AUTENTICACIÓN (Biometría)
# =========================================================================

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
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    role: Optional[str] = None      
    match_score: Optional[float] = None
    tx_hash: Optional[str] = None  # El recibo de la Blockchain


# =========================================================================
#                   SCHEMAS DE BLOCKCHAIN
# =========================================================================

class BlockchainInfoResponse(BaseModel):
    """Información del estado de la conexión con la blockchain."""
    connected: bool
    message: Optional[str] = None
    contract_address: Optional[str] = None
    network: Optional[str] = None
    chain_id: Optional[int] = None
    total_records: Optional[int] = None
    admin_address: Optional[str] = None
    block_number: Optional[int] = None


class AuthRecordResponse(BaseModel):
    """Un registro individual de autenticación en la blockchain."""
    user_id: str
    biometric_hash: str
    timestamp: int
    access_granted: bool
    device_id: str
    match_score: float


class AuthHistoryResponse(BaseModel):
    """Historial de autenticaciones de un usuario."""
    success: bool
    user_id: str
    total_records: int
    records: List[AuthRecordResponse]