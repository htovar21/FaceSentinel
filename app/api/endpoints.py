from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from app.api.schemas import UserRegister, AuthRequest, AuthResponse, BlockchainInfoResponse

# Importamos las funciones reales de IA que creamos en el paso anterior
from app.services.face_recognition import register_face, verify_face, remove_face, base64_to_image

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
        user_id=result.get("user_id"),
        user_name=result["name"],
        role=result.get("role"),
        match_score=result["distance"],
        tx_hash=bc_result.get("tx_hash"),
    )


@router.delete("/users/{user_id}", tags=["Autenticación y Registro"])
def delete_user_account(user_id: str):
    """
    Elimina un usuario del sistema, borrando sus vectores de ChromaDB
    y su perfil en la base de datos SQLite.
    (Nota: Los registros enviados a la blockchain son inmutables y no se pueden borrar).
    """
    result = remove_face(user_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
        
    return result


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


# =========================================================================
#              WEBSOCKET PARA LIVENESS EN TIEMPO REAL
# =========================================================================

import json
import cv2
from app.services.liveness import BlinkTracker, analyze_blink, analyze_texture, analyze_frequency

@router.websocket("/ws/liveness")
async def websocket_liveness(websocket: WebSocket):
    """
    Endpoint interactivo que recibe frames de video en tiempo real,
    rastrea los ojos del usuario y detecta un parpadeo genuino.
    Además, verifica la textura y frecuencia espectral para bloquear
    ataques con videos grabados en pantallas o mascaras impresas.
    """
    await websocket.accept()
    
    # Tolerancia: ear_threshold=0.16 para asegurar que el usuario cerró intencionalmente 
    # los ojos, y no un falso positivo por párpados naturalmente caídos o inicialización.
    tracker = BlinkTracker(ear_threshold=0.16, consecutive_frames=1)
    
    try:
        frame_count = 0
        while True:
            # Esperar el frame del frontend
            data = await websocket.receive_text()
            frame_count += 1
            if frame_count == 1:
                print("Primer frame de WebSocket recibido en el backend.")
                
            payload = json.loads(data)
            base64_img = payload.get("image_base64", "")
            
            if not base64_img:
                print("Frame vacío recibido.")
                continue
                
            try:
                # Usar la utilidad rápida de conversión
                if frame_count == 1: print("Decodificando base64...")
                img_bgr = base64_to_image(base64_img)
                
                if frame_count == 1: print("Convirtiendo a RGB...")
                img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                
                if frame_count == 1: print("Llamando a analyze_blink...")
                # Obtener el estado básico (Presencia y EAR de los ojos)
                has_face, ear = analyze_blink(img_rgb)
                
                if frame_count == 1: print("analyze_blink terminó correctamente.")
                
                if not has_face:
                    await websocket.send_json({
                        "status": "no_face", 
                        "message": "Enfoca bien tu rostro en la cámara..."
                    })
                    continue
                
                # Actualizar el rastreador de parpadeo con el EAR actual
                is_blinking = tracker.update(ear)
                
                if is_blinking:
                    # ¡Parpadeo detectado! Ahora verificamos si es una pantalla/impresión
                    texture_res = analyze_texture(img_bgr)
                    freq_res = analyze_frequency(img_bgr)
                    
                    if texture_res.get("is_real") and freq_res.get("is_real"):
                        print(f"✅ Blink real. Texture: {texture_res.get('texture_score')} | Freq: {freq_res.get('frequency_score')}")
                        await websocket.send_json({
                            "status": "passed", 
                            "message": "¡Prueba de vida superada! Analizando identidad..."
                        })
                        # Romper el ciclo para no enviar múltiples señales de éxito 
                        # que causen una condición de carrera en el Frontend / Blockchain
                        break
                    else:
                        print(f"🚨 Spoofing detectado en blink. Texture: {texture_res.get('texture_score')} | Freq: {freq_res.get('frequency_score')}")
                        # Detectamos pantalla o impresión (Spoofing)
                        # Reiniciamos el rastreador para que intente de nuevo
                        tracker.reset()
                        await websocket.send_json({
                            "status": "spoof_detected", 
                            "message": "Ataque detectado (Pantalla/Foto). Usa un rostro real."
                        })
                else:
                    await websocket.send_json({
                        "status": "tracking", 
                        "ear": round(ear, 3),
                        "message": "Mirando a la cámara... Por favor, parpadea."
                    })
                    
            except ValueError as e:
                print(f"Error decodificando imagen en WebSocket: {e}")
                
    except WebSocketDisconnect:
        print("Cliente de WebSocket desconectado de Liveness")
    except Exception as e:
        print(f"Excepción inesperada en WebSocket: {e}")
