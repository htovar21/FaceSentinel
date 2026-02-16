from fastapi import APIRouter, HTTPException
from app.api.schemas import UserRegister, AuthRequest, AuthResponse

# Importamos las funciones reales de IA que creamos en el paso anterior
from app.services.face_recognition import register_face, verify_face

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
    """Recibe una foto de la cámara en vivo y busca quién es en ChromaDB."""
    result = verify_face(auth_data.image_base64)
    
    if not result["success"]:
        # Si es un desconocido o no hay rostro, devolvemos un 401 (Unauthorized)
        raise HTTPException(status_code=401, detail=result["message"])
        
    return AuthResponse(
        success=True,
        message=result["message"],
        user_name=result["name"],
        role=result.get("role"),  
        match_score=result["distance"],
        tx_hash=None 
    )