from pydantic import BaseModel, Field
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
    client_id: Optional[str] = None

# Lo que tu sistema le responderá al Frontend o a la puerta
class AuthResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    role: Optional[str] = None      
    match_score: Optional[float] = None
    tx_hash: Optional[str] = None  # El recibo de la Blockchain
    token: Optional[str] = None    # Token federado o de acceso


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


# =========================================================================
#                   SCHEMAS DE CLIENTES OAUTH (IdP)
# =========================================================================

class ClientCreate(BaseModel):
    """Modelo para registrar una nueva aplicación cliente de terceros."""
    app_name: str
    redirect_uris: List[str]
    developer_user_id: str
    developer_username: str
    developer_password: str
    liveness_policy: Optional[str] = Field("active", description="Política de liveness: 'none', 'passive', 'active'")


class ClientUpdate(BaseModel):
    """Modelo para actualizar una aplicación cliente de terceros."""
    app_name: Optional[str] = None
    redirect_uris: Optional[List[str]] = None
    liveness_policy: Optional[str] = Field(None, description="Política de liveness: 'none', 'passive', 'active'")


class ClientResponse(BaseModel):
    """Modelo de respuesta para el registro de una aplicación cliente."""
    client_id: str
    client_secret: Optional[str] = None
    app_name: str
    redirect_uris: List[str]
    liveness_policy: Optional[str] = "active"


class PasswordAuthRequest(BaseModel):
    """Modelo para iniciar sesión con contraseña tradicional."""
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    """Modelo para cambiar la contraseña del usuario logueado."""
    current_password: str
    new_password: str


class BiometricsEnrollRequest(BaseModel):
    """Modelo para enrolar la biometría facial del usuario logueado."""
    image_base64: str


# =========================================================================
#                   SCHEMAS M2M (Acceso Físico)
# =========================================================================

class M2MAuthRequest(BaseModel):
    """Modelo para la petición de autenticación desde el Edge Gateway (M2M)."""
    image_base64: str = Field(..., description="Imagen del rostro recortado en formato Base64")
    test_type: Optional[str] = Field("LIVE_USER", description="Tipo de prueba experimental (LIVE_USER, SPOOF_PHOTO_PRINT, SPOOF_SCREEN_VIDEO)")
    environmental_condition: Optional[str] = Field("NORMAL", description="Condición de iluminación (NORMAL, HIGH_LIGHT, LOW_LIGHT)")
    edge_ear_time_ms: Optional[float] = Field(0.0, description="Tiempo de cálculo MediaPipe EAR en el dispositivo de borde")
    edge_total_time_ms: Optional[float] = Field(0.0, description="Tiempo total de procesamiento en borde hasta el envío")
    ear_open_value: Optional[float] = Field(0.0, description="Valor EAR en reposo (ojos abiertos)")
    ear_blink_value: Optional[float] = Field(0.0, description="Valor EAR mínimo alcanzado en el parpadeo")


class IoTDeviceCreate(BaseModel):
    """Modelo para registrar un nuevo dispositivo IoT."""
    device_id: str = Field(..., description="Identificador único del dispositivo de hardware")
    device_name: str = Field(..., description="Nombre descriptivo del punto de acceso")
    device_type: str = Field("camera", description="Tipo de hardware (door, camera, turnstile, gateway)")
    location: Optional[str] = Field(None, description="Ubicación física del dispositivo")
    stream_url: Optional[str] = Field(None, description="URL del stream de video RTSP o HTTP de la cámara")
    lbp_threshold: float = Field(3.670, description="Umbral de entropía LBP configurado para el sensor óptico del dispositivo")
    antispoofing_enabled: bool = Field(True, description="Si es False omite análisis LBP y valida directamente ArcFace (<200ms)")


class IoTDeviceUpdate(BaseModel):
    """Modelo para actualizar la configuración de un dispositivo IoT o su calibración."""
    device_name: Optional[str] = Field(None, description="Nombre descriptivo del punto de acceso")
    location: Optional[str] = Field(None, description="Ubicación física del dispositivo")
    stream_url: Optional[str] = Field(None, description="URL del stream de video RTSP o HTTP")
    lbp_threshold: Optional[float] = Field(None, description="Nuevo umbral de calibración óptica LBP")
    antispoofing_enabled: Optional[bool] = Field(None, description="Activa o desactiva la validación anti-spoofing")
    is_active: Optional[bool] = Field(None, description="Estado de activación del punto de acceso")


class ACLRuleCreate(BaseModel):
    """Modelo para asociar reglas de acceso (ACL/RBAC) a un dispositivo."""
    user_id: Optional[str] = Field(None, description="ID del usuario específico (Cédula)")
    allowed_role: Optional[str] = Field(None, description="Rol con permiso de acceso general (Student, Professor, etc.)")