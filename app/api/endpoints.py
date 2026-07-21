from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends, status, Request
from app.api.schemas import (
    UserRegister,
    AuthRequest,
    AuthResponse,
    BlockchainInfoResponse,
    ClientCreate,
    ClientResponse,
    PasswordAuthRequest,
    PasswordChangeRequest,
    BiometricsEnrollRequest,
    M2MAuthRequest,
)
import secrets
from app.services.storage import (
    save_oauth_client,
    get_oauth_client,
    get_all_oauth_clients,
    get_user_auth_info_by_username,
    get_user_auth_info_by_id,
    update_user_password,
    get_user_by_id,
    save_user_data,
)
from app.core.security import (
    hash_client_secret,
    generate_idp_token,
    create_access_token,
    require_admin,
    verify_client_secret,
    get_current_user,
)

# Importamos las funciones reales de IA que creamos en el paso anterior
from app.services.face_recognition import register_face, verify_face, remove_face, base64_to_image

# Importamos el servicio de blockchain
from app.services.blockchain import (
    log_authentication,
    get_auth_history,
    get_recent_records_by_client,
    get_contract_info,
    is_blockchain_available,
)

router = APIRouter()

@router.post("/clients/register", response_model=ClientResponse, tags=["IdP OAuth / SSO"])
def register_oauth_client(client_data: ClientCreate, current_user: dict = Depends(require_admin)):
    """
    Registra una nueva aplicación de terceros (cliente OAuth) y crea su cuenta Developer asociada.
    Genera un client_id y un client_secret aleatorios.
    """
    # Generar credenciales seguras
    client_id = f"fs_{secrets.token_urlsafe(32)}"
    client_secret = f"fss_{secrets.token_urlsafe(32)}"
    
    # Hashear el client_secret
    secret_hash = hash_client_secret(client_secret)
    
    # Hashear la contraseña del desarrollador
    dev_password_hash = hash_client_secret(client_data.developer_password)
    
    success = save_oauth_client(
        client_id=client_id,
        client_secret_hash=secret_hash,
        redirect_uris=client_data.redirect_uris,
        app_name=client_data.app_name,
        developer_user_id=client_data.developer_user_id,
        developer_username=client_data.developer_username,
        developer_password_hash=dev_password_hash
    )
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="No se pudo registrar el cliente o el desarrollador en la base de datos."
        )
        
    return ClientResponse(
        client_id=client_id,
        client_secret=client_secret,
        app_name=client_data.app_name,
        redirect_uris=client_data.redirect_uris
    )


@router.get("/clients", tags=["IdP OAuth / SSO"])
def list_oauth_clients(current_user: dict = Depends(require_admin)):
    """
    Lista todos los clientes OAuth registrados en el IdP.
    (Sólo disponible para Administradores).
    """
    return get_all_oauth_clients()


@router.post("/auth/password", tags=["Autenticación y Registro"])
def authenticate_by_password(auth_data: PasswordAuthRequest):
    """
    Verifica las credenciales tradicionales para roles Admin y Developer.
    Los usuarios finales (role User/Student/Professor) están estrictamente denegados (403).
    """
    user_info = get_user_auth_info_by_username(auth_data.username)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de acceso incorrectas."
        )
        
    # Validar que no sea un usuario final
    role_lower = user_info["role"].lower()
    if role_lower not in ["admin", "developer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Los usuarios finales deben autenticarse biométricamente."
        )
        
    # Verificar contraseña hasheada
    if not user_info["password_hash"] or not verify_client_secret(auth_data.password, user_info["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de acceso incorrectas."
        )
        
    # Generar token JWT con sub (user_id) y role
    token = create_access_token(data={"sub": user_info["user_id"], "role": user_info["role"]})
    
    return {
        "success": True,
        "token": token,
        "user_id": user_info["user_id"],
        "user_name": user_info["name"],
        "role": user_info["role"]
    }


@router.put("/users/me/password", tags=["Autenticación y Registro"])
def change_my_password(pass_data: PasswordChangeRequest, current_user: dict = Depends(get_current_user)):
    """
    Permite a un Administrador o Desarrollador logueado cambiar su contraseña.
    """
    user_id = current_user.get("sub")
    user_info = get_user_auth_info_by_id(user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        
    if not user_info["password_hash"] or not verify_client_secret(pass_data.current_password, user_info["password_hash"]):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta.")
        
    # Hashear y actualizar
    new_hash = hash_client_secret(pass_data.new_password)
    update_user_password(user_id, new_hash)
    
    return {"success": True, "message": "Contraseña actualizada correctamente."}


@router.put("/users/me/biometrics", tags=["Autenticación y Registro"])
def enroll_my_biometrics(bio_data: BiometricsEnrollRequest, current_user: dict = Depends(get_current_user)):
    """
    Permite a un Desarrollador o Administrador registrar su rostro para iniciar sesión biométricamente.
    """
    user_id = current_user.get("sub")
    # Buscar usuario en SQLite para conservar su nombre y rol
    user_info = get_user_by_id(user_id)
    if not user_info:
        # Si no se encuentra en get_user_by_id, consultar get_user_auth_info
        auth_info = get_user_auth_info_by_id(user_id)
        if not auth_info:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        user_info = {"name": auth_info["name"], "role": auth_info["role"]}
        
    success, message = register_face(
        user_id=user_id,
        name=user_info["name"],
        role=user_info["role"],
        base64_image=bio_data.image_base64
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
        
    return {"success": True, "message": "Biometría facial enrolada con éxito."}


@router.get("/clients/my", tags=["IdP OAuth / SSO"])
def get_my_client_app(current_user: dict = Depends(get_current_user)):
    """
    Retorna la configuración de la aplicación cliente asociada al Desarrollador logueado.
    """
    user_id = current_user.get("sub")
    user_info = get_user_auth_info_by_id(user_id)
    if not user_info or not user_info.get("associated_client_id"):
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. No tienes una aplicación de terceros asociada."
        )
        
    client = get_oauth_client(user_info["associated_client_id"])
    if not client:
        raise HTTPException(status_code=404, detail="Aplicación asociada no encontrada.")
        
    return client


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
    [DEPRECADO] Endpoint vulnerable a API Bypass.
    La autenticación biométrica ahora es Zero-Trust y debe realizarse exclusivamente
    a través del WebSocket interactivo en /ws/liveness.
    """
    raise HTTPException(
        status_code=410,
        detail="Endpoint deprecado. La autenticación biométrica ahora es Zero-Trust y debe realizarse exclusivamente a través de la conexión interactiva en /ws/liveness"
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
    limit: int = Query(default=10, ge=1, le=100, alias="limit", description="Cantidad de registros a retornar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Consulta el historial de autenticaciones de un usuario en la blockchain (o SQLite local).
    Retorna los registros más recientes, inmutables y verificables.
    """
    # Restricción estricta de Roles (RBAC - Solo Admin)
    user_role = current_user.get("role", "").lower()
    if user_role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Rol no autorizado para ver historiales de acceso."
        )

    if not is_blockchain_available():
        from app.services.storage import get_local_user_auth_history
        return get_local_user_auth_history(user_id, limit)
    
    history = get_auth_history(user_id, limit)
    
    if not history["success"]:
        raise HTTPException(status_code=500, detail=history["message"])
    
    return history


@router.get("/clients/{client_id}/logs", tags=["Blockchain"])
def get_client_logs(
    client_id: str,
    limit: int = Query(default=50, ge=1, le=100, description="Cantidad de registros a retornar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene los registros de autenticación asociados a un clientId específico en la blockchain (o SQLite local).
    """
    # Validar permisos (IDOR Protection & RBAC)
    user_role = current_user.get("role", "").lower()
    user_id = current_user.get("sub")
    
    if user_role == "admin":
        pass
    elif user_role == "developer":
        user_info = get_user_auth_info_by_id(user_id)
        if not user_info or user_info.get("associated_client_id") != client_id:
            raise HTTPException(
                status_code=403,
                detail="Acceso denegado. No puedes consultar los logs de otra aplicación."
            )
    else:
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Rol no autorizado para ver logs de aplicaciones."
        )

    if not is_blockchain_available():
        from app.services.storage import get_local_client_logs
        return get_local_client_logs(client_id, limit)
    
    logs = get_recent_records_by_client(client_id, limit)
    
    if not logs["success"]:
        raise HTTPException(status_code=500, detail=logs["message"])
    
    return logs


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
from app.services.liveness import BlinkTracker, analyze_blink, analyze_texture, analyze_frequency, comprehensive_liveness_check

@router.websocket("/ws/liveness")
async def websocket_liveness(websocket: WebSocket, client_id: str = Query(None), action: str = Query("authentication")):
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
                    
                    metrics_payload = {
                        "blink": {
                            "value": round(ear, 3),
                            "threshold": "< 0.16",
                            "weight": "Filtro Base (Obligatorio)"
                        },
                        "texture": {
                            "value": texture_res.get("entropy"),
                            "threshold": ">= 4.75",
                            "weight": "Determinante (Alto)"
                        },
                        "frequency": {
                            "value": freq_res.get("freq_ratio"),
                            "threshold": "N/A",
                            "weight": "Bypass (Deshabilitado para OLED)"
                        }
                    }
 
                    if texture_res.get("is_real") and freq_res.get("is_real"):
                        print(f"✅ Blink real. Texture: {texture_res.get('texture_score')} | Freq: {freq_res.get('frequency_score')}")
                        
                        # Ejecutar la verificación de identidad biométrica con ArcFace
                        auth_res = verify_face(img_bgr)
                        
                        if auth_res.get("success"):
                            user_id = auth_res["user_id"]
                            user_name = auth_res["name"]
                            role = auth_res["role"]
                            distance = auth_res["distance"]
                            
                            effective_client_id = client_id or "LOCAL_AUTH"
                            token = generate_idp_token(
                                user_id=user_id,
                                client_id=effective_client_id,
                                role=role,
                                action=action,
                                name=user_name
                            )
                            
                            # Registrar en la blockchain
                            log_res = log_authentication(
                                user_id=user_id,
                                client_id=effective_client_id,
                                embedding=None,
                                access_granted=True,
                                match_score=distance
                            )
                            tx_hash = log_res.get("tx_hash")
                            
                            await websocket.send_json({
                                "status": "passed",
                                "message": f"¡Identidad verificada! Bienvenido, {user_name}",
                                "user_id": user_id,
                                "user_name": user_name,
                                "role": role,
                                "token": token,
                                "match_score": distance,
                                "tx_hash": tx_hash,
                                "metrics": metrics_payload
                            })
                        else:
                            # Falla de autenticación: Rostro no reconocido o no coincide
                            distance = auth_res.get("distance", 0.0)
                            effective_client_id = client_id or "LOCAL_AUTH"
                            
                            # Registrar acceso denegado en la blockchain
                            log_authentication(
                                user_id="UNKNOWN",
                                client_id=effective_client_id,
                                embedding=None,
                                access_granted=False,
                                match_score=distance
                            )
                            
                            await websocket.send_json({
                                "status": "failed",
                                "message": auth_res.get("message", "Acceso denegado. Rostro desconocido."),
                                "match_score": distance,
                                "metrics": metrics_payload
                            })
                        # Romper el ciclo ya que el flujo termina (éxito o fallo biométrico)
                        break
                    else:
                        print(f"🚨 Spoofing detectado en blink. Texture: {texture_res.get('texture_score')} | Freq: {freq_res.get('frequency_score')}")
                        # Detectamos pantalla o impresión (Spoofing)
                        # Reiniciamos el rastreador para que intente de nuevo
                        tracker.reset()
                        await websocket.send_json({
                            "status": "spoof_detected", 
                            "message": "Ataque detectado (Pantalla/Foto). Usa un rostro real.",
                            "metrics": metrics_payload
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


# =========================================================================
#            M2M ENDPOINT PARA ACCESO FÍSICO (DISPOSITIVOS IOT)
# =========================================================================

from fastapi.responses import JSONResponse

@router.post("/physical-access/authenticate", tags=["Acceso Físico"])
def physical_access_authenticate(payload: M2MAuthRequest, request: Request):
    """
    Endpoint dedicado a dispositivos físicos M2M.
    Valida token, realiza control de vida (liveness),
    extrae embedding y realiza verificación facial contra ChromaDB y SQLite,
    y registra el evento en la blockchain de manera inmutable.
    """
    # 1. Autenticación M2M vía cabecera Authorization: Bearer <device_secret>
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "authorization": "DENIED",
                "detail": "Cabecera Authorization Bearer faltante o mal formada."
            }
        )
    
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "authorization": "DENIED",
                "detail": "Cabecera Authorization Bearer mal formada."
            }
        )
        
    device_secret = parts[1]
    if device_secret != settings.HW_CLIENT_SECRET:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "authorization": "DENIED",
                "detail": "Token de dispositivo incorrecto o no autorizado."
            }
        )

    # 2. Decodificar imagen base64
    try:
        img_bgr = base64_to_image(payload.image_base64)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "authorization": "DENIED",
                "detail": f"Error decodificando imagen: {str(e)}"
            }
        )

    # 3. Validación de Liveness (Anti-Spoofing) en una sola imagen (LBP + FFT)
    try:
        liveness_res = comprehensive_liveness_check(img_bgr)
        if not liveness_res.get("is_live"):
            # Registrar intento fallido por liveness en blockchain
            log_authentication(
                user_id="UNKNOWN",
                client_id="PHYSICAL_ACCESS",
                embedding=None,
                access_granted=False,
                device_id="PHYSICAL-GATEWAY",
                match_score=0.0
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "authorization": "DENIED",
                    "detail": f"Acceso denegado. Liveness fallido: {liveness_res.get('reason')}"
                }
            )
    except Exception as e:
        logger.error(f"Error en validación liveness: {e}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "authorization": "DENIED",
                "detail": "Error durante la validación de Liveness."
            }
        )

    # 4. Extraer embedding y buscar en ChromaDB
    try:
        auth_res = verify_face(img_bgr)
    except Exception as e:
        logger.error(f"Error en verificación facial: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "authorization": "DENIED",
                "detail": "Error en el motor de reconocimiento facial."
            }
        )

    if not auth_res.get("success"):
        # Registrar intento de acceso fallido
        log_authentication(
            user_id="UNKNOWN",
            client_id="PHYSICAL_ACCESS",
            embedding=None,
            access_granted=False,
            device_id="PHYSICAL-GATEWAY",
            match_score=auth_res.get("distance", 0.0)
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "authorization": "DENIED",
                "detail": auth_res.get("message", "Acceso denegado. Rostro desconocido.")
            }
        )

    # 5. Generar log inmutable en Blockchain
    try:
        user_id = auth_res["user_id"]
        user_name = auth_res["name"]
        role = auth_res["role"]
        distance = auth_res["distance"]
        
        log_res = log_authentication(
            user_id=user_id,
            client_id="PHYSICAL_ACCESS",
            embedding=None,
            access_granted=True,
            device_id="PHYSICAL-GATEWAY",
            match_score=distance
        )
        tx_hash = log_res.get("tx_hash") or "0x0000000000000000000000000000000000000000000000000000000000000000"
    except Exception as e:
        logger.error(f"Error al registrar autenticación en blockchain: {e}")
        tx_hash = "0x0000000000000000000000000000000000000000000000000000000000000000"

    # 6. Respuesta exitosa
    return {
        "status": "success",
        "authorization": "GRANTED",
        "user": {
            "id": user_id,
            "name": user_name,
            "role": role
        },
        "blockchain_tx": tx_hash
    }
