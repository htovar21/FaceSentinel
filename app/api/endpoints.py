from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends, status, Request, BackgroundTasks
import os
import json
import logging
import asyncio
import time
import threading
from app.core.config import settings
from app.services.liveness import comprehensive_liveness_check, calibrate_camera_stream
from app.services.metrics_collector import log_experiment_metric
from app.api.schemas import (
    UserRegister,
    AuthRequest,
    AuthResponse,
    BlockchainInfoResponse,
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    PasswordAuthRequest,
    PasswordChangeRequest,
    BiometricsEnrollRequest,
    M2MAuthRequest,
    IoTDeviceCreate,
    IoTDeviceUpdate,
    ACLRuleCreate,
)
import secrets
from app.services.storage import (
    save_oauth_client,
    get_oauth_client,
    update_oauth_client,
    get_all_oauth_clients,
    get_user_auth_info_by_username,
    get_user_auth_info_by_id,
    update_user_password,
    get_user_by_id,
    save_user_data,
    get_device_by_token,
    verify_device_access,
    get_all_users,
    save_iot_device,
    update_iot_device,
    get_iot_device,
    delete_iot_device,
    get_device_acl_rules,
    save_acl_rule,
    delete_acl_rule,
    get_all_devices,
)

logger = logging.getLogger(__name__)
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
from app.core.limiter import limiter

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
    
    policy = client_data.liveness_policy or "active"
    success = save_oauth_client(
        client_id=client_id,
        client_secret_hash=secret_hash,
        redirect_uris=client_data.redirect_uris,
        app_name=client_data.app_name,
        developer_user_id=client_data.developer_user_id,
        developer_username=client_data.developer_username,
        developer_password_hash=dev_password_hash,
        liveness_policy=policy
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
        redirect_uris=client_data.redirect_uris,
        liveness_policy=policy
    )


@router.patch("/clients/{client_id}", tags=["IdP OAuth / SSO"])
@router.put("/clients/{client_id}", tags=["IdP OAuth / SSO"])
def update_client(
    client_id: str,
    update_data: ClientUpdate,
    current_user: dict = Depends(require_admin)
):
    """Actualiza la configuración o política de liveness de una aplicación cliente."""
    success = update_oauth_client(
        client_id=client_id,
        app_name=update_data.app_name,
        redirect_uris=update_data.redirect_uris,
        liveness_policy=update_data.liveness_policy
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente '{client_id}' no encontrado o no se pudo actualizar."
        )
    return {"success": True, "message": f"Cliente '{client_id}' actualizado correctamente."}


@router.get("/clients", tags=["IdP OAuth / SSO"])
def list_oauth_clients(current_user: dict = Depends(require_admin)):
    """
    Lista todos los clientes OAuth registrados en el IdP.
    (Sólo disponible para Administradores).
    """
    return get_all_oauth_clients()


@router.get("/users", tags=["Autenticación y Registro"])
def list_users(current_user: dict = Depends(require_admin)):
    """
    Lista todos los usuarios registrados en el IdP.
    (Sólo disponible para Administradores).
    """
    return get_all_users()


@router.post("/auth/password", tags=["Autenticación y Registro"])
@limiter.limit("10/minute")
def authenticate_by_password(auth_data: PasswordAuthRequest, request: Request):
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


@router.put("/users/{user_id}/biometrics", tags=["Autenticación y Registro"])
def admin_enroll_user_biometrics(
    user_id: str,
    bio_data: BiometricsEnrollRequest,
    current_user: dict = Depends(require_admin)
):
    """
    Permite al Administrador actualizar o enrolar nuevamente la biometría facial de cualquier usuario en ChromaDB y SQLite.
    """
    user_info = get_user_by_id(user_id)
    if not user_info:
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

    return {"success": True, "message": f"Biometría facial de {user_info['name']} actualizada con éxito."}


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
def register_user(user_data: UserRegister, current_user: dict = Depends(require_admin)):
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
def delete_user_account(user_id: str, current_user: dict = Depends(require_admin)):
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
import random
from app.services.liveness import (
    BlinkTracker, 
    analyze_blink, 
    analyze_texture, 
    analyze_frequency, 
    comprehensive_liveness_check,
    estimate_head_pose
)

@router.websocket("/ws/liveness")
async def websocket_liveness(websocket: WebSocket, client_id: str = Query(None), action: str = Query("authentication")):
    """
    Endpoint interactivo que recibe frames de video en tiempo real,
    rastrea los ojos del usuario y detecta un parpadeo genuino.
    Además, verifica la textura y frecuencia espectral para bloquear
    ataques con videos grabados en pantallas o mascaras impresas.
    """
    await websocket.accept()
    
    # REGLA DE SEGURIDAD (Anti-Downgrade):
    # Si no se envía client_id o el client_id no existe, aplica por defecto "active".
    liveness_policy = "active"
    if client_id:
        client_info = get_oauth_client(client_id)
        if client_info:
            liveness_policy = client_info.get("liveness_policy", "active") or "active"

    logger.info(f"🌐 WebSocket Liveness conectado. Client ID: '{client_id}' | Política activa: '{liveness_policy}'")
    
    # Tolerancia: ear_threshold=0.16 para asegurar que el usuario cerró intencionalmente 
    # los ojos, y no un falso positivo por párpados naturalmente caídos o inicialización.
    tracker = BlinkTracker(ear_threshold=0.16, consecutive_frames=1)
    
    # Máquina de estados para Liveness Blindado (Challenge-Response Secuencial):
    # Fase 1: "blink" (Detección de parpadeo frontal + validación LBP >= 3.20 + captura frontal_frame)
    # Fase 2 & 3: "challenge" (Secuencia de 2 retos aleatorios distintos: "left", "right", "mouth")
    # Regla Crítica: Penalización por gesto opuesto/incorrecto para anular ataques de repetición
    phase = "blink"
    challenges = []  # Lista de 2 retos distintos, ej: ["left", "mouth"]
    challenge_step = 0  # 0 para Reto 1/2, 1 para Reto 2/2
    challenge_start_time = None
    frontal_frame = None
    saved_texture_res = None
    saved_freq_res = None
    saved_ear = 0.0
    
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

                effective_client_id = client_id or "LOCAL_AUTH"

                # -------------------------------------------------------------
                # POLÍTICA 1: "none" (1-Shot Instantáneo sin anti-spoofing)
                # -------------------------------------------------------------
                if liveness_policy == "none":
                    print("⚡ Política 'none' (1-Shot Instantáneo): Ejecutando ArcFace en primer frame con rostro...")
                    auth_res = verify_face(img_bgr, custom_threshold=0.70)
                    metrics_payload = {
                        "blink": {"value": round(ear, 3), "threshold": "N/A (1-Shot)", "weight": "Deshabilitado", "passed": True},
                        "texture": {"value": 0.0, "threshold": "N/A (1-Shot)", "weight": "Deshabilitado", "passed": True},
                        "pose": {"value": "N/A", "threshold": "N/A (1-Shot)", "weight": "Deshabilitado", "passed": True},
                        "frequency": {"value": 0.0, "threshold": "N/A", "weight": "Deshabilitado"}
                    }
                    if auth_res.get("success"):
                        user_id = auth_res["user_id"]
                        user_name = auth_res["name"]
                        role = auth_res["role"]
                        distance = auth_res["distance"]
                        token = generate_idp_token(
                            user_id=user_id,
                            client_id=effective_client_id,
                            role=role,
                            action=action,
                            name=user_name
                        )
                        loop = asyncio.get_event_loop()
                        log_res = await loop.run_in_executor(
                            None,
                            lambda: log_authentication(
                                user_id=user_id,
                                client_id=effective_client_id,
                                embedding=None,
                                access_granted=True,
                                match_score=distance
                            )
                        )
                        tx_hash = log_res.get("tx_hash")
                        await websocket.send_json({
                            "status": "passed",
                            "message": f"¡Identidad verificada (1-Shot)! Bienvenido, {user_name}",
                            "user_id": user_id,
                            "user_name": user_name,
                            "role": role,
                            "token": token,
                            "match_score": distance,
                            "tx_hash": tx_hash,
                            "metrics": metrics_payload
                        })
                    else:
                        distance = auth_res.get("distance", 0.0)
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: log_authentication(
                                user_id="UNKNOWN",
                                client_id=effective_client_id,
                                embedding=None,
                                access_granted=False,
                                match_score=distance
                            )
                        )
                        await websocket.send_json({
                            "status": "failed",
                            "message": auth_res.get("message", "Acceso denegado. Rostro desconocido."),
                            "match_score": distance,
                            "metrics": metrics_payload
                        })
                    break
                
                if phase == "blink":
                    # Actualizar el rastreador de parpadeo con el EAR actual
                    is_blinking = tracker.update(ear)
                    
                    if is_blinking:
                        # ¡Parpadeo detectado! Verificación LBP con umbral base SSO en 3.20
                        sso_lbp_threshold = 3.20
                        texture_res = analyze_texture(img_bgr, custom_lbp_threshold=sso_lbp_threshold, adaptive_threshold=False)
                        freq_res = analyze_frequency(img_bgr)
                        
                        print(f"🔬 Fase 1 (Parpadeo) -> LBP: {texture_res.get('entropy')} | Umbral: {texture_res.get('lbp_threshold')}")
                        
                        if not texture_res.get("is_real"):
                            if texture_res.get("is_corrupted") or texture_res.get("entropy", 0.0) <= 0.05:
                                print(f"⚠️ Fotograma corrupto recibido en websocket (entropía ~0.0). Descartando sin registrar spoofing.")
                                tracker.reset()
                                await websocket.send_json({
                                    "status": "tracking",
                                    "message": "Fotograma borroso o con interferencia. Mantén el rostro visible y parpadea nuevamente."
                                })
                                continue

                            print(f"🚨 Spoofing detectado en blink (Foto/Impresión). Texture: {texture_res.get('texture_score')}")
                            tracker.reset()
                            await websocket.send_json({
                                "status": "spoof_detected",
                                "message": "Ataque detectado (Pantalla/Foto). Usa un rostro real.",
                                "metrics": {
                                    "blink": {"value": round(ear, 3), "threshold": "< 0.16", "weight": "Filtro Base (Obligatorio)", "passed": True},
                                    "texture": {"value": texture_res.get("entropy"), "threshold": f">= {sso_lbp_threshold:.2f}", "weight": "Determinante (Alto)", "passed": False},
                                    "frequency": {"value": freq_res.get("freq_ratio"), "threshold": "N/A", "weight": "Bypass (OLED)"}
                                }
                            })
                            continue
                        
                        # -------------------------------------------------------------
                        # POLÍTICA 2: "passive" (Parpadeo + LBP sin desafíos de pose)
                        # -------------------------------------------------------------
                        if liveness_policy == "passive":
                            print("⚡ Política 'passive' (Parpadeo + LBP): Ejecutando ArcFace tras validación de vida pasiva...")
                            metrics_payload = {
                                "blink": {
                                    "value": round(ear, 3),
                                    "threshold": "< 0.16",
                                    "weight": "Filtro Base (Obligatorio)",
                                    "passed": True
                                },
                                "texture": {
                                    "value": texture_res.get("entropy"),
                                    "threshold": f">= {sso_lbp_threshold:.2f}",
                                    "weight": "Determinante (Alto)",
                                    "passed": True
                                },
                                "pose": {
                                    "value": "N/A",
                                    "threshold": "N/A (Modo Pasivo)",
                                    "weight": "Deshabilitado",
                                    "passed": True
                                },
                                "frequency": {
                                    "value": freq_res.get("freq_ratio"),
                                    "threshold": "N/A",
                                    "weight": "Bypass (OLED)"
                                }
                            }
                            auth_res = verify_face(img_bgr, custom_threshold=0.70)
                            if auth_res.get("success"):
                                user_id = auth_res["user_id"]
                                user_name = auth_res["name"]
                                role = auth_res["role"]
                                distance = auth_res["distance"]
                                token = generate_idp_token(
                                    user_id=user_id,
                                    client_id=effective_client_id,
                                    role=role,
                                    action=action,
                                    name=user_name
                                )
                                loop = asyncio.get_event_loop()
                                log_res = await loop.run_in_executor(
                                    None,
                                    lambda: log_authentication(
                                        user_id=user_id,
                                        client_id=effective_client_id,
                                        embedding=None,
                                        access_granted=True,
                                        match_score=distance
                                    )
                                )
                                tx_hash = log_res.get("tx_hash")
                                await websocket.send_json({
                                    "status": "passed",
                                    "message": f"¡Identidad verificada (Pasivo)! Bienvenido, {user_name}",
                                    "user_id": user_id,
                                    "user_name": user_name,
                                    "role": role,
                                    "token": token,
                                    "match_score": distance,
                                    "tx_hash": tx_hash,
                                    "metrics": metrics_payload
                                })
                            else:
                                distance = auth_res.get("distance", 0.0)
                                loop = asyncio.get_event_loop()
                                await loop.run_in_executor(
                                    None,
                                    lambda: log_authentication(
                                        user_id="UNKNOWN",
                                        client_id=effective_client_id,
                                        embedding=None,
                                        access_granted=False,
                                        match_score=distance
                                    )
                                )
                                await websocket.send_json({
                                    "status": "failed",
                                    "message": auth_res.get("message", "Acceso denegado. Rostro desconocido."),
                                    "match_score": distance,
                                    "metrics": metrics_payload
                                })
                            break

                        # -------------------------------------------------------------
                        # POLÍTICA 3: "active" (Parpadeo + LBP + Desafío Activo de Pose)
                        # -------------------------------------------------------------
                        # ¡Fase 1 superada! Guardamos el fotograma FRONTAL limpio para ArcFace
                        frontal_frame = img_bgr.copy()
                        saved_texture_res = texture_res
                        saved_freq_res = freq_res
                        saved_ear = ear
                        
                        # Iniciar Secuencia de 2 Retos Dinámicos DISTINTOS aleatorios:
                        challenges = random.sample(["left", "right", "mouth"], 2)
                        challenge_step = 0
                        phase = "challenge"
                        challenge_start_time = time.time()
                        
                        curr_c = challenges[0]
                        if curr_c == "left":
                            c_text = "Gira hacia tu hombro IZQUIERDO"
                        elif curr_c == "right":
                            c_text = "Gira hacia tu hombro DERECHO"
                        else:
                            c_text = "Abre ligeramente la boca 😮"
                            
                        print(f"🎯 Secuencia de retos asignada: {challenges}. Iniciando Reto 1/2: {curr_c.upper()}")
                        
                        await websocket.send_json({
                            "status": "tracking",
                            "challenge": curr_c,
                            "step": 1,
                            "message": f"¡Parpadeo detectado! Reto 1/2: {c_text}",
                            "ear": round(ear, 3),
                            "metrics": {
                                "blink": {"value": round(ear, 3), "threshold": "< 0.16", "weight": "Filtro Base", "passed": True},
                                "texture": {"value": texture_res.get("entropy"), "threshold": f">= {sso_lbp_threshold:.2f}", "weight": "Determinante", "passed": True},
                                "pose": {"value": 0.0, "threshold": f"Reto 1/2: {curr_c.upper()}", "weight": "Anti-Replay Dinámico", "passed": False},
                                "frequency": {"value": freq_res.get("freq_ratio"), "threshold": "N/A", "weight": "Bypass (OLED)"}
                            }
                        })
                    else:
                        await websocket.send_json({
                            "status": "tracking", 
                            "ear": round(ear, 3),
                            "message": "Mirando a la cámara... Por favor, parpadea."
                        })
                
                elif phase == "challenge":
                    # Límite de tiempo para el reto actual (7.0 segundos por paso)
                    elapsed_step = time.time() - challenge_start_time
                    if elapsed_step > 7.0:
                        print(f"⏱️ Tiempo agotado para el reto {challenge_step + 1}/2. Reiniciando a parpadeo.")
                        phase = "blink"
                        tracker.reset()
                        frontal_frame = None
                        challenges = []
                        challenge_step = 0
                        await websocket.send_json({
                            "status": "tracking",
                            "message": "Tiempo agotado. Mira al frente y parpadea para reintentar."
                        })
                        continue
                    
                    # Estimar pose de cabeza y apertura de boca
                    pose = estimate_head_pose(img_rgb)
                    if not pose.get("detected"):
                        await websocket.send_json({
                            "status": "no_face",
                            "message": "Rostro no detectado. Mira de frente a la cámara."
                        })
                        continue
                        
                    yaw = pose.get("yaw", 0.0)
                    mar = pose.get("mar", 0.0)
                    curr_c = challenges[challenge_step]
                    
                    # REGLA CRÍTICA ANTI-VIDEO (Penalización por gesto opuesto / incorrecto):
                    # Se concede un margen de 0.8s al iniciar el paso para permitir la transición física del rostro.
                    # Si tras 0.8s el usuario/video ejecuta el giro opuesto (>= 6.0°), se reinicia el flujo
                    # a la Fase 1 (parpadeo) para bloquear videos en bucle sin tumbar la cámara ni el WebSocket.
                    wrong_gesture = False
                    if elapsed_step > 0.8:
                        if curr_c == "left" and yaw <= -6.0:
                            wrong_gesture = True
                        elif curr_c == "right" and yaw >= 6.0:
                            wrong_gesture = True
                        elif curr_c == "mouth" and abs(yaw) >= 6.5:
                            wrong_gesture = True
                            
                    if wrong_gesture:
                        print(f"⚠️ Gesto opuesto detectado mientras se esperaba {curr_c.upper()} (Yaw: {yaw}, MAR: {mar}). Reiniciando reto de liveness.")
                        phase = "blink"
                        tracker.reset()
                        frontal_frame = None
                        challenges = []
                        challenge_step = 0
                        await websocket.send_json({
                            "status": "tracking",
                            "message": "Gesto en dirección contraria. Vuelve a mirar al frente y parpadea."
                        })
                        continue
                    
                    # Evaluar si el reto actual fue superado:
                    # 1. "left": yaw >= +5.5°
                    # 2. "right": yaw <= -5.5°
                    # 3. "mouth": mar >= 0.25
                    is_step_met = False
                    if curr_c == "left" and yaw >= 5.5:
                        is_step_met = True
                    elif curr_c == "right" and yaw <= -5.5:
                        is_step_met = True
                    elif curr_c == "mouth" and mar >= 0.25:
                        is_step_met = True
                        
                    if not is_step_met:
                        # Enviar retroalimentación en tiempo real
                        if curr_c == "left":
                            desc = f"Reto {challenge_step + 1}/2: Gira hacia tu hombro IZQUIERDO (Giro: {max(0.0, yaw):.1f}° / 5.5°)"
                            val_display = round(yaw, 1)
                        elif curr_c == "right":
                            desc = f"Reto {challenge_step + 1}/2: Gira hacia tu hombro DERECHO (Giro: {max(0.0, -yaw):.1f}° / 5.5°)"
                            val_display = round(yaw, 1)
                        else:
                            desc = f"Reto {challenge_step + 1}/2: Abre ligeramente la boca 😮 (Apertura: {mar:.2f} / 0.25)"
                            val_display = round(mar, 2)
                            
                        await websocket.send_json({
                            "status": "tracking",
                            "challenge": curr_c,
                            "step": challenge_step + 1,
                            "yaw": round(yaw, 1),
                            "mar": round(mar, 2),
                            "message": desc,
                            "metrics": {
                                "blink": {"value": round(saved_ear, 3), "threshold": "< 0.16", "weight": "Filtro Base", "passed": True},
                                "texture": {"value": saved_texture_res.get("entropy"), "threshold": f">= {sso_lbp_threshold:.2f}", "weight": "Determinante", "passed": True},
                                "pose": {"value": val_display, "threshold": f"Reto {challenge_step+1}/2: {curr_c.upper()}", "weight": "Anti-Replay Dinámico", "passed": False},
                                "frequency": {"value": saved_freq_res.get("freq_ratio"), "threshold": "N/A", "weight": "Bypass (OLED)"}
                            }
                        })
                        continue
                        
                    # ¡Paso completado!
                    if challenge_step == 0:
                        challenge_step = 1
                        challenge_start_time = time.time()
                        next_c = challenges[1]
                        print(f"✅ Reto 1/2 superado ({curr_c.upper()}). Iniciando Reto 2/2: {next_c.upper()}")
                        
                        if next_c == "left":
                            next_desc = "¡Reto 1 superado! Reto 2/2: Ahora gira hacia tu hombro IZQUIERDO"
                        elif next_c == "right":
                            next_desc = "¡Reto 1 superado! Reto 2/2: Ahora gira hacia tu hombro DERECHO"
                        else:
                            next_desc = "¡Reto 1 superado! Reto 2/2: Ahora abre ligeramente la boca 😮"
                            
                        await websocket.send_json({
                            "status": "tracking",
                            "challenge": next_c,
                            "step": 2,
                            "message": next_desc,
                            "metrics": {
                                "blink": {"value": round(saved_ear, 3), "threshold": "< 0.16", "weight": "Filtro Base", "passed": True},
                                "texture": {"value": saved_texture_res.get("entropy"), "threshold": f">= {sso_lbp_threshold:.2f}", "weight": "Determinante", "passed": True},
                                "pose": {"value": 0.0, "threshold": f"Reto 2/2: {next_c.upper()}", "weight": "Anti-Replay Dinámico", "passed": False},
                                "frequency": {"value": saved_freq_res.get("freq_ratio"), "threshold": "N/A", "weight": "Bypass (OLED)"}
                            }
                        })
                        continue
                        
                    # ¡AMBOS RETOS SUPERADOS!
                    print(f"🎉 ¡Desafío Activo Completo Superado! Secuencia: {[c.upper() for c in challenges]}")
                    
                    sso_lbp_threshold = 3.20
                    metrics_payload = {
                        "blink": {
                            "value": round(saved_ear, 3),
                            "threshold": "< 0.16",
                            "weight": "Filtro Base (Obligatorio)",
                            "passed": True
                        },
                        "texture": {
                            "value": saved_texture_res.get("entropy"),
                            "threshold": f">= {sso_lbp_threshold:.2f}",
                            "weight": "Determinante (Alto)",
                            "passed": True
                        },
                        "pose": {
                            "value": f"{challenges[0].upper()} + {challenges[1].upper()}",
                            "threshold": "Secuencia 2/2 OK",
                            "weight": "Anti-Replay Dinámico",
                            "passed": True
                        },
                        "frequency": {
                            "value": saved_freq_res.get("freq_ratio"),
                            "threshold": "N/A",
                            "weight": "Bypass (Deshabilitado para OLED)"
                        }
                    }
                    
                    # Ejecutar ArcFace usando el frontal_frame limpio guardado en Fase 1
                    print("🧠 Ejecutando ArcFace con el fotograma FRONTAL limpio guardado en Fase 1...")
                    auth_res = verify_face(frontal_frame, custom_threshold=0.70)
                    
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
                        
                        # Registrar en blockchain de forma no bloqueante
                        loop = asyncio.get_event_loop()
                        log_res = await loop.run_in_executor(
                            None,
                            lambda: log_authentication(
                                user_id=user_id,
                                client_id=effective_client_id,
                                embedding=None,
                                access_granted=True,
                                match_score=distance
                            )
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
                        
                        # Registrar fallo en blockchain de forma no bloqueante
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: log_authentication(
                                user_id="UNKNOWN",
                                client_id=effective_client_id,
                                embedding=None,
                                access_granted=False,
                                match_score=distance
                            )
                        )
                        
                        await websocket.send_json({
                            "status": "failed",
                            "message": auth_res.get("message", "Acceso denegado. Rostro desconocido."),
                            "match_score": distance,
                            "metrics": metrics_payload
                        })
                    # Romper el ciclo ya que el flujo termina (éxito o fallo biométrico)
                    break
                    
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

def _record_m2m_metrics_and_blockchain(
    user_id: str,
    client_id: str,
    embedding: list,
    access_granted: bool,
    device_id: str,
    match_score: float,
    metrics_payload: dict
):
    """
    Tarea en segundo plano que ejecuta el logging en Blockchain/SQLite
    y complementa el dataset experimental con los datos del bloque y gas.
    """
    try:
        bc_result = log_authentication(
            user_id=user_id,
            client_id=client_id,
            embedding=embedding,
            access_granted=access_granted,
            device_id=device_id,
            match_score=match_score
        )
        if isinstance(bc_result, dict):
            metrics_payload["bc_tx_hash"] = bc_result.get("tx_hash", "") or ""
            metrics_payload["bc_gas_used"] = bc_result.get("gas_used", 0) or 0
            metrics_payload["bc_block_number"] = bc_result.get("block_number", 0) or 0
            metrics_payload["bc_seal_time_ms"] = bc_result.get("seal_time_ms", 0.0) or 0.0
    except Exception as e:
        logger.error(f"Error registrando blockchain en background: {e}")

    try:
        log_experiment_metric(metrics_payload)
    except Exception as e:
        logger.error(f"Error guardando métricas experimentales: {e}")


def _dispatch_background_log(
    user_id: str,
    client_id: str,
    embedding: list,
    access_granted: bool,
    device_id: str,
    match_score: float,
    metrics_payload: dict
):
    """Lanza la grabación de métricas y blockchain en hilo daemon para garantizar ejecución incluso ante HTTPException."""
    threading.Thread(
        target=_record_m2m_metrics_and_blockchain,
        args=(user_id, client_id, embedding, access_granted, device_id, match_score, metrics_payload),
        daemon=True
    ).start()


@router.post("/physical-access/authenticate", tags=["Acceso Físico"])
@limiter.limit("20/minute")
def physical_access_authenticate(
    payload: M2MAuthRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint dedicado a dispositivos físicos M2M con telemetría para Tesis.
    Valida token, realiza control de vida (liveness),
    extrae embedding y realiza verificación facial contra ChromaDB y SQLite,
    verifica los permisos del dispositivo (ACL/RBAC),
    y registra el evento en la blockchain de manera inmutable y en el dataset CSV.
    """
    t0_backend = time.perf_counter()
    t_sqlite_accum = 0.0

    # 1. Autenticación M2M vía cabecera Authorization: Bearer <device_secret>
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabecera Authorization Bearer faltante o mal formada."
        )
    
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabecera Authorization Bearer mal formada."
        )
        
    device_secret = parts[1]
    
    # Buscar dispositivo por token/secreto en SQLite
    t0_sql = time.perf_counter()
    device = get_device_by_token(device_secret)
    t_sqlite_accum += (time.perf_counter() - t0_sql) * 1000.0

    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de dispositivo incorrecto o no autorizado."
        )

    device_lbp_threshold = device.get("lbp_threshold", 3.2) if isinstance(device, dict) else getattr(device, "lbp_threshold", 3.2)
    device_id = device.get("device_id", "API-SERVER-01") if isinstance(device, dict) else getattr(device, "device_id", "API-SERVER-01")
    antispoofing_enabled = device.get("antispoofing_enabled", True) if isinstance(device, dict) else getattr(device, "antispoofing_enabled", True)
    if antispoofing_enabled is None:
        antispoofing_enabled = True

    # 2. Decodificar imagen base64
    try:
        img_bgr = base64_to_image(payload.image_base64)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error decodificando imagen: {str(e)}"
        )

    # 3. Validación de Liveness (Anti-Spoofing) según política del dispositivo
    if not antispoofing_enabled:
        # Modo Bypass Ultra-Rápido (< 200 ms): omite validación LBP y ejecuta directamente ArcFace
        logger.info(f"⚡ Bypass anti-spoofing activado para dispositivo '{device_id}' (antispoofing_enabled=False). Match directo.")
        liveness_res = {
            "is_live": True,
            "t_lbp_ms": 0.0,
            "t_fft_ms": 0.0,
            "entropy": 0.0,
            "lbp_threshold": device_lbp_threshold,
            "lbp_variance": 0.0,
            "liveness_score": 1.0,
        }
    else:
        try:
            liveness_res = comprehensive_liveness_check(img_bgr, custom_lbp_threshold=device_lbp_threshold)
            if not liveness_res.get("is_live"):
                # Si el fotograma viene corrupto por red o micro-glitches HEVC (entropía o nitidez ~0.0),
                # descartar el frame y solicitar reintento inmediato en lugar de registrarlo como ataque de spoofing.
                if liveness_res.get("is_corrupted") or liveness_res.get("entropy", 0.0) <= 0.05:
                    logger.warning(
                        f"⚠️ [{device_id}] Fotograma corrupto o dañado por red descartado "
                        f"(Entropía: {liveness_res.get('entropy')}, Razón: {liveness_res.get('reason')}). "
                        f"Solicitando reintento de captura sin penalizar como spoofing."
                    )
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Fotograma corrupto o dañado por red, reintentando..."
                    )

                t_backend_total_ms = (time.perf_counter() - t0_backend) * 1000.0
                metrics_payload = {
                    "test_type": payload.test_type or "SPOOF_ATTACK",
                    "environmental_condition": payload.environmental_condition or "NORMAL",
                    "user_id": "UNKNOWN",
                    "granted": False,
                    "rejection_reason": "SPOOFING_DETECTED",
                    "t_ear_edge_ms": payload.edge_ear_time_ms or 0.0,
                    "t_edge_total_ms": payload.edge_total_time_ms or 0.0,
                    "t_network_rtt_ms": 0.0,
                    "t_lbp_ms": liveness_res.get("t_lbp_ms", 0.0),
                    "t_fft_ms": liveness_res.get("t_fft_ms", 0.0),
                    "t_arcface_ms": 0.0,
                    "t_chroma_ms": 0.0,
                    "t_sqlite_ms": round(t_sqlite_accum, 2),
                    "t_backend_total_ms": round(t_backend_total_ms, 2),
                    "t_total_end2end_ms": round((payload.edge_total_time_ms or 0.0) + t_backend_total_ms, 2),
                    "ear_open": payload.ear_open_value or 0.0,
                    "ear_blink": payload.ear_blink_value or 0.0,
                    "lbp_entropy": liveness_res.get("entropy", 0.0),
                    "lbp_threshold": liveness_res.get("lbp_threshold", device_lbp_threshold),
                    "lbp_variance": liveness_res.get("lbp_variance", 0.0),
                    "liveness_score": liveness_res.get("liveness_score", 0.0),
                    "cosine_distance": 0.0,
                    "match_threshold": settings.FACE_MATCH_THRESHOLD,
                }

                _dispatch_background_log(
                    user_id="UNKNOWN",
                    client_id="PHYSICAL_ACCESS",
                    embedding=None,
                    access_granted=False,
                    device_id=device_id,
                    match_score=0.0,
                    metrics_payload=metrics_payload
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Spoofing detectado"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error en validación liveness: {e}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Error durante la validación de Liveness."
            )

    # 4. Extraer embedding y buscar en ChromaDB
    try:
        auth_res = verify_face(img_bgr)
    except Exception as e:
        logger.error(f"Error en verificación facial: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error en el motor de reconocimiento facial."
        )

    if not auth_res.get("success"):
        t_backend_total_ms = (time.perf_counter() - t0_backend) * 1000.0
        metrics_payload = {
            "test_type": payload.test_type or "LIVE_USER",
            "environmental_condition": payload.environmental_condition or "NORMAL",
            "user_id": auth_res.get("user_id") or "UNKNOWN",
            "granted": False,
            "rejection_reason": "UNKNOWN_FACE_OR_NO_MATCH",
            "t_ear_edge_ms": payload.edge_ear_time_ms or 0.0,
            "t_edge_total_ms": payload.edge_total_time_ms or 0.0,
            "t_network_rtt_ms": 0.0,
            "t_lbp_ms": liveness_res.get("t_lbp_ms", 0.0),
            "t_fft_ms": liveness_res.get("t_fft_ms", 0.0),
            "t_arcface_ms": auth_res.get("t_arcface_ms", 0.0),
            "t_chroma_ms": auth_res.get("t_chroma_ms", 0.0),
            "t_sqlite_ms": round(t_sqlite_accum, 2),
            "t_backend_total_ms": round(t_backend_total_ms, 2),
            "t_total_end2end_ms": round((payload.edge_total_time_ms or 0.0) + t_backend_total_ms, 2),
            "ear_open": payload.ear_open_value or 0.0,
            "ear_blink": payload.ear_blink_value or 0.0,
            "lbp_entropy": liveness_res.get("entropy", 0.0),
            "lbp_threshold": liveness_res.get("lbp_threshold", device_lbp_threshold),
            "lbp_variance": liveness_res.get("lbp_variance", 0.0),
            "liveness_score": liveness_res.get("liveness_score", 0.0),
            "cosine_distance": auth_res.get("distance", 0.0),
            "match_threshold": settings.FACE_MATCH_THRESHOLD,
        }

        _dispatch_background_log(
            user_id=auth_res.get("user_id") or "UNKNOWN",
            client_id="PHYSICAL_ACCESS",
            embedding=None,
            access_granted=False,
            device_id=device_id,
            match_score=auth_res.get("distance", 0.0),
            metrics_payload=metrics_payload
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_res.get("message", "Acceso denegado. Rostro desconocido.")
        )

    user_id = auth_res["user_id"]
    distance = auth_res["distance"]

    # 5. Control de Acceso (RBAC/ACL)
    t0_sql2 = time.perf_counter()
    user = get_user_by_id(user_id)
    t_sqlite_accum += (time.perf_counter() - t0_sql2) * 1000.0

    if not user:
        t_backend_total_ms = (time.perf_counter() - t0_backend) * 1000.0
        metrics_payload = {
            "test_type": payload.test_type or "LIVE_USER",
            "environmental_condition": payload.environmental_condition or "NORMAL",
            "user_id": user_id,
            "granted": False,
            "rejection_reason": "USER_NOT_IN_SQLITE",
            "t_ear_edge_ms": payload.edge_ear_time_ms or 0.0,
            "t_edge_total_ms": payload.edge_total_time_ms or 0.0,
            "t_network_rtt_ms": 0.0,
            "t_lbp_ms": liveness_res.get("t_lbp_ms", 0.0),
            "t_fft_ms": liveness_res.get("t_fft_ms", 0.0),
            "t_arcface_ms": auth_res.get("t_arcface_ms", 0.0),
            "t_chroma_ms": auth_res.get("t_chroma_ms", 0.0),
            "t_sqlite_ms": round(t_sqlite_accum, 2),
            "t_backend_total_ms": round(t_backend_total_ms, 2),
            "t_total_end2end_ms": round((payload.edge_total_time_ms or 0.0) + t_backend_total_ms, 2),
            "ear_open": payload.ear_open_value or 0.0,
            "ear_blink": payload.ear_blink_value or 0.0,
            "lbp_entropy": liveness_res.get("entropy", 0.0),
            "lbp_threshold": liveness_res.get("lbp_threshold", device_lbp_threshold),
            "lbp_variance": liveness_res.get("lbp_variance", 0.0),
            "liveness_score": liveness_res.get("liveness_score", 0.0),
            "cosine_distance": distance,
            "match_threshold": settings.FACE_MATCH_THRESHOLD,
        }

        _dispatch_background_log(
            user_id=user_id,
            client_id="PHYSICAL_ACCESS",
            embedding=None,
            access_granted=False,
            device_id=device_id,
            match_score=distance,
            metrics_payload=metrics_payload
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado en la base de datos relacional."
        )

    t0_sql3 = time.perf_counter()
    has_access = verify_device_access(
        device_id=device["device_id"],
        user_id=user_id,
        user_role=user["role"]
    )
    t_sqlite_accum += (time.perf_counter() - t0_sql3) * 1000.0

    if not has_access:
        t_backend_total_ms = (time.perf_counter() - t0_backend) * 1000.0
        metrics_payload = {
            "test_type": payload.test_type or "LIVE_USER",
            "environmental_condition": payload.environmental_condition or "NORMAL",
            "user_id": user_id,
            "granted": False,
            "rejection_reason": "ACL_FORBIDDEN",
            "t_ear_edge_ms": payload.edge_ear_time_ms or 0.0,
            "t_edge_total_ms": payload.edge_total_time_ms or 0.0,
            "t_network_rtt_ms": 0.0,
            "t_lbp_ms": liveness_res.get("t_lbp_ms", 0.0),
            "t_fft_ms": liveness_res.get("t_fft_ms", 0.0),
            "t_arcface_ms": auth_res.get("t_arcface_ms", 0.0),
            "t_chroma_ms": auth_res.get("t_chroma_ms", 0.0),
            "t_sqlite_ms": round(t_sqlite_accum, 2),
            "t_backend_total_ms": round(t_backend_total_ms, 2),
            "t_total_end2end_ms": round((payload.edge_total_time_ms or 0.0) + t_backend_total_ms, 2),
            "ear_open": payload.ear_open_value or 0.0,
            "ear_blink": payload.ear_blink_value or 0.0,
            "lbp_entropy": liveness_res.get("entropy", 0.0),
            "lbp_threshold": liveness_res.get("lbp_threshold", device_lbp_threshold),
            "lbp_variance": liveness_res.get("lbp_variance", 0.0),
            "liveness_score": liveness_res.get("liveness_score", 0.0),
            "cosine_distance": distance,
            "match_threshold": settings.FACE_MATCH_THRESHOLD,
        }

        _dispatch_background_log(
            user_id=user_id,
            client_id="PHYSICAL_ACCESS",
            embedding=None,
            access_granted=False,
            device_id=device_id,
            match_score=distance,
            metrics_payload=metrics_payload
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado a esta zona"
        )

    # 6. Generar log inmutable de Éxito en Blockchain y SQLite en segundo plano (asíncrono)
    t_backend_total_ms = (time.perf_counter() - t0_backend) * 1000.0
    metrics_payload = {
        "test_type": payload.test_type or "LIVE_USER",
        "environmental_condition": payload.environmental_condition or "NORMAL",
        "user_id": user_id,
        "granted": True,
        "rejection_reason": "NONE_GRANTED",
        "t_ear_edge_ms": payload.edge_ear_time_ms or 0.0,
        "t_edge_total_ms": payload.edge_total_time_ms or 0.0,
        "t_network_rtt_ms": 0.0,
        "t_lbp_ms": liveness_res.get("t_lbp_ms", 0.0),
        "t_fft_ms": liveness_res.get("t_fft_ms", 0.0),
        "t_arcface_ms": auth_res.get("t_arcface_ms", 0.0),
        "t_chroma_ms": auth_res.get("t_chroma_ms", 0.0),
        "t_sqlite_ms": round(t_sqlite_accum, 2),
        "t_backend_total_ms": round(t_backend_total_ms, 2),
        "t_total_end2end_ms": round((payload.edge_total_time_ms or 0.0) + t_backend_total_ms, 2),
        "ear_open": payload.ear_open_value or 0.0,
        "ear_blink": payload.ear_blink_value or 0.0,
        "lbp_entropy": liveness_res.get("entropy", 0.0),
        "lbp_threshold": liveness_res.get("lbp_threshold", device_lbp_threshold),
        "lbp_variance": liveness_res.get("lbp_variance", 0.0),
        "liveness_score": liveness_res.get("liveness_score", 0.0),
        "cosine_distance": distance,
        "match_threshold": settings.FACE_MATCH_THRESHOLD,
    }

    background_tasks.add_task(
        _record_m2m_metrics_and_blockchain,
        user_id=user_id,
        client_id="PHYSICAL_ACCESS",
        embedding=auth_res.get("embedding"),
        access_granted=True,
        device_id=device_id,
        match_score=distance,
        metrics_payload=metrics_payload
    )

    # 7. Respuesta exitosa con telemetría de backend para cálculo de RTT en el Edge
    return {
        "status": "success",
        "authorization": "GRANTED",
        "user": {
            "id": user_id,
            "name": user["name"],
            "role": user["role"]
        },
        "blockchain_tx": "PENDING_COMMIT",
        "timings": {
            "t_backend_total_ms": round(t_backend_total_ms, 2),
            "t_lbp_ms": liveness_res.get("t_lbp_ms", 0.0),
            "t_fft_ms": liveness_res.get("t_fft_ms", 0.0),
            "t_arcface_ms": auth_res.get("t_arcface_ms", 0.0),
            "t_chroma_ms": auth_res.get("t_chroma_ms", 0.0),
            "t_sqlite_ms": round(t_sqlite_accum, 2)
        },
        "liveness": {
            "score": liveness_res.get("liveness_score", 0.0),
            "entropy": liveness_res.get("entropy", 0.0),
            "lbp_threshold": liveness_res.get("lbp_threshold", device_lbp_threshold)
        },
        "biometrics": {
            "distance": round(distance, 4),
            "threshold": settings.FACE_MATCH_THRESHOLD
        }
    }


# =========================================================================
#            GESTIÓN DE DISPOSITIVOS IOT Y ACLS (ADMINISTRADOR)
# =========================================================================

@router.get("/devices", tags=["Acceso Físico"])
def get_devices(current_user: dict = Depends(require_admin)):
    """Lista todos los dispositivos IoT registrados (Solo Administrador)"""
    return get_all_devices()


@router.post("/devices", tags=["Acceso Físico"])
def register_device(device_data: IoTDeviceCreate, current_user: dict = Depends(require_admin)):
    """
    Registra un nuevo dispositivo físico en SQLite.
    Genera y retorna un token de hardware único en texto plano.
    """
    # Generar token de hardware único y aleatorio
    client_secret = f"hw_{secrets.token_urlsafe(32)}"
    
    # Hashear el token para almacenamiento en base de datos
    secret_hash = hash_client_secret(client_secret)
    
    success = save_iot_device(
        device_id=device_data.device_id,
        device_name=device_data.device_name,
        device_type=device_data.device_type,
        location=device_data.location,
        client_secret_hash=secret_hash,
        token_plain=client_secret,
        lbp_threshold=device_data.lbp_threshold,
        stream_url=device_data.stream_url,
        antispoofing_enabled=device_data.antispoofing_enabled,
        is_active=True
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo registrar el dispositivo en la base de datos."
        )
        
    return {
        "device_id": device_data.device_id,
        "device_name": device_data.device_name,
        "device_type": device_data.device_type,
        "location": device_data.location,
        "stream_url": device_data.stream_url,
        "lbp_threshold": device_data.lbp_threshold,
        "antispoofing_enabled": device_data.antispoofing_enabled,
        "client_secret": client_secret  # Se retorna una sola vez en texto plano
    }


@router.get("/devices/sync", tags=["Acceso Físico"])
def sync_devices_for_gateway():
    """
    Endpoint de aprovisionamiento Zero-Config para dispositivos de borde (Edge Gateways / Raspberry Pi).
    Permite que cualquier hardware de borde consulte la configuración activa sin requerir edición manual de archivos.
    """
    devices = get_all_devices()
    KNOWN_TOKENS = {
        "PASILLO62": "hw_zaEy9rg43tK6QZa0e9O_oDE_spala6yRm71hA74ayV8",
        "TLFHECTOR": "hw_tlfhector_secret_key_8832a74ayV8",
        "IPHONE6": "hw_iphone6_token"
    }

    existing_tokens = {}
    for path in ["data/cameras.json", "cameras.json", "/app/data/cameras.json"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                for c in configs:
                    if "device_id" in c and "token" in c:
                        existing_tokens[c["device_id"].upper()] = c["token"]
            except Exception:
                pass

    result = []
    for d in devices:
        dev_id = d["device_id"].upper()
        token = existing_tokens.get(dev_id) or KNOWN_TOKENS.get(dev_id) or f"hw_{dev_id.lower()}_token"
        result.append({
            "device_id": d["device_id"],
            "name": d["device_name"],
            "token": token,
            "source": d["stream_url"] if d.get("stream_url") else "0",
            "location": d.get("location") or "Punto de Acceso",
            "enabled": bool(d.get("is_active", True) and d.get("stream_url")),
            "antispoofing_enabled": d.get("antispoofing_enabled", True),
            "lbp_threshold": d.get("lbp_threshold", 3.670)
        })

    # Guardar automáticamente en disco para sincronización física instantánea
    for path in ["/app/data/cameras.json", "data/cameras.json"]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4)
        except Exception as e:
            logger.warning(f"No se pudo guardar automáticamente {path}: {e}")

    return result


@router.get("/devices/{device_id}", tags=["Acceso Físico"])
def get_single_device(device_id: str, current_user: dict = Depends(require_admin)):
    """Obtiene los detalles de configuración y calibración de un dispositivo."""
    dev = get_iot_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return dev


@router.patch("/devices/{device_id}", tags=["Acceso Físico"])
def update_device(
    device_id: str,
    update_data: IoTDeviceUpdate,
    current_user: dict = Depends(require_admin)
):
    """Actualiza la calibración LBP, URL de streaming RTSP, nombre o ubicación de un dispositivo."""
    success = update_iot_device(
        device_id=device_id,
        device_name=update_data.device_name,
        location=update_data.location,
        stream_url=update_data.stream_url,
        lbp_threshold=update_data.lbp_threshold,
        antispoofing_enabled=update_data.antispoofing_enabled,
        is_active=update_data.is_active
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispositivo '{device_id}' no encontrado o no se pudo actualizar."
        )

    # Sincronizar data/cameras.json y cameras.json si existen
    for path in ["data/cameras.json", "cameras.json", "/app/data/cameras.json"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                matched = False
                for c in configs:
                    if c.get("device_id", "").upper() == device_id.upper():
                        matched = True
                        if update_data.is_active is not None:
                            c["enabled"] = update_data.is_active
                        if update_data.stream_url is not None:
                            c["source"] = update_data.stream_url
                        if update_data.lbp_threshold is not None:
                            c["lbp_threshold"] = update_data.lbp_threshold
                        if update_data.device_name is not None:
                            c["name"] = update_data.device_name
                        if update_data.location is not None:
                            c["location"] = update_data.location
                        if update_data.antispoofing_enabled is not None:
                            c["antispoofing_enabled"] = update_data.antispoofing_enabled
                if not matched and update_data.stream_url:
                    configs.append({
                        "device_id": device_id,
                        "name": update_data.device_name or device_id,
                        "token": f"hw_{device_id.lower()}_token_aqui",
                        "source": update_data.stream_url or "0",
                        "location": update_data.location or "Punto de Acceso",
                        "enabled": bool(update_data.is_active) if update_data.is_active is not None else True,
                        "antispoofing_enabled": update_data.antispoofing_enabled if update_data.antispoofing_enabled is not None else True,
                        "lbp_threshold": update_data.lbp_threshold or 3.670
                    })
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(configs, f, indent=4)
            except Exception:
                pass
                pass

    return {"success": True, "message": f"Dispositivo '{device_id}' actualizado correctamente."}


@router.post("/devices/{device_id}/auto-calibrate", tags=["Acceso Físico"])
def auto_calibrate_device(
    device_id: str,
    target_samples: int = 25,
    current_user: dict = Depends(require_admin)
):
    """
    Calibra empíricamente una cámara en vivo conectándose a su stream_url.
    Captura muestras faciales reales, calcula el umbral LBP óptimo,
    lo actualiza en la base de datos y retorna el informe estadístico.
    """
    dev = get_iot_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Dispositivo '{device_id}' no encontrado.")

    stream_url = dev.get("stream_url")
    if not stream_url or stream_url.strip() in ["", "0"]:
        raise HTTPException(
            status_code=400,
            detail=f"El dispositivo '{device_id}' no tiene una URL de stream válida configurada (RTSP o HTTP)."
        )

    try:
        calib_result = calibrate_camera_stream(stream_url.strip(), target_samples=target_samples)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante la calibración: {str(e)}")

    new_threshold = calib_result["optimal_threshold"]
    update_iot_device(device_id=device_id, lbp_threshold=new_threshold)

    # Actualizar data/cameras.json si existe
    for path in ["data/cameras.json", "/app/data/cameras.json"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                for c in configs:
                    if c.get("device_id", "").upper() == device_id.upper():
                        c["lbp_threshold"] = new_threshold
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(configs, f, indent=4)
            except Exception:
                pass

    return {
        "success": True,
        "device_id": device_id,
        "device_name": dev.get("device_name", device_id),
        "calibration": calib_result,
        "message": f"Calibración exitosa: nuevo umbral óptimo θ={new_threshold} guardado para '{device_id}'."
    }


@router.delete("/devices/{device_id}", tags=["Acceso Físico"])
def remove_device(device_id: str, current_user: dict = Depends(require_admin)):
    """Elimina un dispositivo IoT registrado (Solo Administrador)"""
    success = delete_iot_device(device_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispositivo no encontrado o no se pudo eliminar."
        )
    return {"success": True, "message": f"Dispositivo '{device_id}' eliminado con éxito."}


@router.get("/devices/{device_id}/acl", tags=["Acceso Físico"])
def get_device_acl(device_id: str, current_user: dict = Depends(require_admin)):
    """Lista las reglas de acceso (ACL/RBAC) configuradas para un dispositivo (Solo Administrador)"""
    return get_device_acl_rules(device_id)


@router.post("/devices/{device_id}/acl", tags=["Acceso Físico"])
def add_device_acl(device_id: str, acl_data: ACLRuleCreate, current_user: dict = Depends(require_admin)):
    """Asocia una nueva regla de acceso (ACL/RBAC) a un dispositivo (Solo Administrador)"""
    if not acl_data.user_id and not acl_data.allowed_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar al menos un user_id (ACL) o allowed_role (RBAC)."
        )
        
    success = save_acl_rule(
        device_id=device_id,
        user_id=acl_data.user_id,
        allowed_role=acl_data.allowed_role,
        schedule_rule=None
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo registrar la regla de acceso en la base de datos."
        )
        
    return {"success": True, "message": "Regla de acceso registrada con éxito."}


@router.delete("/devices/acl/{rule_id}", tags=["Acceso Físico"])
def remove_device_acl(rule_id: int, current_user: dict = Depends(require_admin)):
    """Elimina una regla de acceso ACL/RBAC por su ID (Solo Administrador)"""
    success = delete_acl_rule(rule_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regla de acceso no encontrada o no se pudo eliminar."
        )
    return {"success": True, "message": "Regla de acceso eliminada con éxito."}


@router.get("/health", tags=["Salud del Sistema"])
def health_check():
    """Endpoint de salud del backend y estado de la red Blockchain."""
    from app.services.blockchain import is_blockchain_available
    return {
        "message": "Bienvenido a la API de FaceSentinel",
        "status": "online",
        "blockchain": "connected" if is_blockchain_available() else "disconnected",
        "docs_url": "/docs"
    }


@router.get("/blockchain/info", tags=["Blockchain"])
def blockchain_contract_info():
    """Retorna información en tiempo real del Smart Contract y de la red Ethereum (Ganache)."""
    from app.services.blockchain import get_contract_info
    return get_contract_info()
