from fastapi import APIRouter, HTTPException, Query
from app.api.schemas import UserRegister, AuthRequest, AuthResponse, BlockchainInfoResponse

# Importamos las funciones reales de IA que creamos en el paso anterior
from app.services.face_recognition import register_face, verify_face

# Importamos el servicio de blockchain
from app.services.blockchain import (
    log_authentication,
    get_auth_history,
    get_contract_info,
    is_blockchain_available,
)

router = APIRouter()

@router.post("/register", tags=["Autenticación y Registro"])
def register_user(user_data: UserRegister):
    """Recibe los datos y la foto, y los envía a la IA para extraer el vector."""
    success, message = register_face(
        user_id=user_data.user_id,
        name=user_data.name,
        role=user_data.role,
        base64_image=user_data.image_base64
    )
    
    if not success:
        # Si la IA no detectó un rostro, devolvemos un error 400 (Bad Request)
        raise HTTPException(status_code=400, detail=message)
        
    return {"success": True, "message": message}

@router.post("/authenticate", response_model=AuthResponse, tags=["Autenticación y Registro"])
def authenticate_user(auth_data: AuthRequest):
    """
    Recibe una foto de la cámara en vivo, busca quién es en ChromaDB,
    y registra el evento de autenticación en la blockchain.
    """
    result = verify_face(auth_data.image_base64)
    
    if not result["success"]:
        # Registrar intento fallido en blockchain (si está disponible)
        bc_result = log_authentication(
            user_id="DESCONOCIDO",
            access_granted=False,
            device_id="API-SERVER-01",
            match_score=0.0,
        )

        raise HTTPException(status_code=401, detail=result["message"])
    
    # Registrar acceso exitoso en la blockchain
    bc_result = log_authentication(
        user_id=result.get("user_id", ""),
        access_granted=True,
        device_id="API-SERVER-01",
        match_score=result.get("distance", 0.0),
    )

    return AuthResponse(
        success=True,
        message=result["message"],
        user_name=result["name"],
        role=result.get("role"),
        match_score=result["distance"],
        tx_hash=bc_result.get("tx_hash"),
    )


# =========================================================================
#              ENDPOINTS DE BLOCKCHAIN (Consultas)
# =========================================================================

@router.get("/auth-history/{user_id}", tags=["Blockchain"])
def get_user_auth_history(
    user_id: str,
    count: int = Query(default=10, ge=1, le=100, description="Cantidad de registros a retornar")
):
    """
    Consulta el historial de autenticaciones de un usuario en la blockchain.
    Retorna los registros más recientes, inmutables y verificables.
    """
    if not is_blockchain_available():
        raise HTTPException(
            status_code=503,
            detail="Blockchain no disponible. Verifica que Ganache esté corriendo."
        )
    
    history = get_auth_history(user_id, count)
    
    if not history["success"]:
        raise HTTPException(status_code=500, detail=history["message"])
    
    return history


@router.get("/blockchain/status", response_model=BlockchainInfoResponse, tags=["Blockchain"])
def blockchain_status():
    """
    Retorna el estado actual de la conexión con la blockchain
    y la información del Smart Contract.
    """
    info = get_contract_info()
    return BlockchainInfoResponse(**info)