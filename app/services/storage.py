"""
storage.py — Capa de almacenamiento dual (SQLite + ChromaDB) con SQLAlchemy 2.0
Gestiona la persistencia de datos biométricos, metadatos de usuarios,
clientes OAuth/SSO, dispositivos IoT y listas de control de acceso (ACL).
"""

import json
import logging
import chromadb
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine,
    String,
    Boolean,
    ForeignKey,
    Integer,
    DateTime,
    Text,
    Float,
    select,
    func,
    or_
)
from sqlalchemy.orm import (
    sessionmaker,
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship
)

from app.core.config import settings

logger = logging.getLogger(__name__)

logger.info("⏳ Inicializando bases de datos (SQLite y ChromaDB)...")

# =========================================================================
#           1. CHROMADB (Base de datos vectorial) - Sin cambios
# =========================================================================

# PersistentClient guarda los datos físicamente en la carpeta que definimos en .env
chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)

# Colección para los rostros. Usamos 'cosine' porque es la mejor métrica
# para comparar embeddings faciales en IA.
face_collection = chroma_client.get_or_create_collection(
    name="faces_collection",
    metadata={"hnsw:space": "cosine"}
)


# =========================================================================
#           2. SQLALCHEMY & MODELOS RELACIONALES (SQLite)
# =========================================================================

# Configuración del Engine de SQLAlchemy (SQLite)
# check_same_thread=False es necesario en FastAPI para peticiones concurrentes
DATABASE_URL = f"sqlite:///{settings.SQLITE_DB_PATH}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Clase base declarativa de SQLAlchemy 2.0"""
    pass


class User(Base):
    __tablename__ = "users"
    
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    associated_client_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación uno-a-muchos con permisos de acceso directo
    acl_rules: Mapped[List["AccessControlList"]] = relationship(
        "AccessControlList", back_populates="user", cascade="all, delete-orphan"
    )


class OAuthClient(Base):
    __tablename__ = "oauth_clients"
    
    client_id: Mapped[str] = mapped_column(String, primary_key=True)
    client_secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)  # JSON serializado
    app_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AccessLog(Base):
    __tablename__ = "access_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    access_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    client_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IoTDevice(Base):
    __tablename__ = "iot_devices"
    
    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_name: Mapped[str] = mapped_column(String, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False, default="door")  # 'door', 'camera', etc.
    location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    client_secret_hash: Mapped[str] = mapped_column(String, nullable=False)  # Client_Secret físico cifrado
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación uno-a-muchos con las reglas de acceso
    acl_rules: Mapped[List["AccessControlList"]] = relationship(
        "AccessControlList", back_populates="device", cascade="all, delete-orphan"
    )


class AccessControlList(Base):
    __tablename__ = "access_control_lists"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String, ForeignKey("iot_devices.device_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    allowed_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    schedule_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON serializado
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relaciones de clave foránea
    user: Mapped[Optional[User]] = relationship("User", back_populates="acl_rules")
    device: Mapped[IoTDevice] = relationship("IoTDevice", back_populates="acl_rules")


def init_sqlite():
    """Crea las tablas si no existen al arrancar el sistema."""
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Tablas SQLite creadas/verificadas con SQLAlchemy 2.0 ORM.")


# =========================================================================
#           3. OPERACIONES CRUD REFACTORIZADAS (SQLite)
# =========================================================================

def save_oauth_client(
    client_id: str,
    client_secret_hash: str,
    redirect_uris: list[str],
    app_name: str,
    developer_user_id: str,
    developer_username: str,
    developer_password_hash: str
) -> bool:
    """
    Guarda un nuevo cliente de OAuth en la base de datos relacional
    y crea automáticamente la cuenta del desarrollador asociado.
    """
    with SessionLocal() as session:
        try:
            # 1. Guardar cliente
            redirect_uris_json = json.dumps(redirect_uris)
            client = OAuthClient(
                client_id=client_id,
                client_secret_hash=client_secret_hash,
                redirect_uris=redirect_uris_json,
                app_name=app_name
            )
            session.add(client)
            
            # 2. Crear o reemplazar cuenta de desarrollador asociada
            user = session.get(User, developer_user_id)
            if user:
                user.username = developer_username
                user.name = f"Desarrollador {app_name}"
                user.role = "Developer"
                user.password_hash = developer_password_hash
                user.associated_client_id = client_id
                user.updated_at = datetime.utcnow()
            else:
                user = User(
                    user_id=developer_user_id,
                    username=developer_username,
                    name=f"Desarrollador {app_name}",
                    role="Developer",
                    password_hash=developer_password_hash,
                    associated_client_id=client_id
                )
                session.add(user)
            
            session.commit()
            logger.info(f"🔑 Cliente OAuth '{app_name}' (ID: {client_id}) y desarrollador '{developer_username}' guardados con éxito.")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Error al guardar el cliente OAuth y su desarrollador: {e}")
            return False


def get_oauth_client(client_id: str) -> Optional[dict]:
    """
    Busca y retorna un cliente OAuth por su ID.
    Deserializa las URIs de redirección desde formato JSON.
    """
    with SessionLocal() as session:
        client = session.get(OAuthClient, client_id)
        if client:
            try:
                uris = json.loads(client.redirect_uris)
            except (json.JSONDecodeError, TypeError):
                uris = []
            return {
                "client_id": client.client_id,
                "client_secret_hash": client.client_secret_hash,
                "redirect_uris": uris,
                "app_name": client.app_name
            }
        return None


def get_all_oauth_clients() -> list[dict]:
    """
    Retorna todas las aplicaciones de terceros registradas en el sistema.
    """
    with SessionLocal() as session:
        stmt = select(OAuthClient).order_by(OAuthClient.created_at.desc())
        clients = session.scalars(stmt).all()
        
        result = []
        for client in clients:
            try:
                uris = json.loads(client.redirect_uris)
            except (json.JSONDecodeError, TypeError):
                uris = []
            result.append({
                "client_id": client.client_id,
                "app_name": client.app_name,
                "redirect_uris": uris,
                "created_at": client.created_at
            })
        return result


def save_user_data(user_id: str, name: str, role: str, face_vector: list) -> bool:
    """Guarda al usuario en AMBAS bases de datos al mismo tiempo (SQLite + ChromaDB)."""
    # A. Guardar en SQLite
    with SessionLocal() as session:
        try:
            user = session.get(User, user_id)
            if user:
                user.name = name
                user.role = role
                user.updated_at = datetime.utcnow()
            else:
                user = User(
                    user_id=user_id,
                    name=name,
                    role=role
                )
                session.add(user)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Error al guardar datos de usuario en SQLite: {e}")
            return False

    # B. Guardar el vector matemático en ChromaDB (fuera del contexto de SQLite)
    try:
        face_collection.upsert(
            embeddings=[face_vector],
            ids=[user_id],
            metadatas=[{"name": name, "role": role}]
        )
    except Exception as e:
        logger.error(f"❌ Error al guardar embeddings en ChromaDB: {e}")
        return False

    logger.info(f"💾 Usuario '{name}' (ID: {user_id}) guardado en SQLite + ChromaDB.")
    return True


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Busca los datos de un usuario por su ID en SQLite."""
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user:
            return {
                "name": user.name,
                "role": user.role,
                "username": user.username
            }
        return None


def delete_user(user_id: str) -> bool:
    """Elimina un usuario de la base de datos local SQLite."""
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user:
            try:
                session.delete(user)
                session.commit()
                logger.info(f"🗑️ Usuario eliminado localmente: {user_id}")
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Error al eliminar usuario de SQLite: {e}")
                return False
        return False


def get_all_users() -> list[dict]:
    """Retorna todos los usuarios registrados."""
    with SessionLocal() as session:
        stmt = select(User).order_by(User.created_at.desc())
        users = session.scalars(stmt).all()
        return [
            {
                "user_id": u.user_id,
                "name": u.name,
                "role": u.role,
                "created_at": u.created_at
            }
            for u in users
        ]


def save_access_log(
    user_id: str,
    access_granted: bool,
    match_score: float = None,
    device_id: str = None,
    tx_hash: str = None,
    client_id: str = None
):
    """Guarda un registro de acceso local (respaldo de la blockchain)."""
    with SessionLocal() as session:
        try:
            log = AccessLog(
                user_id=user_id,
                access_granted=access_granted,
                match_score=match_score,
                device_id=device_id,
                tx_hash=tx_hash,
                client_id=client_id
            )
            session.add(log)
            session.commit()
            logger.debug(f"📝 Log de acceso guardado para {user_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Error al guardar log de acceso: {e}")


def get_local_client_logs(client_id: str, limit: int = 50) -> dict:
    """Obtiene los registros de acceso locales para un cliente."""
    import calendar
    import time
    
    with SessionLocal() as session:
        stmt = (
            select(AccessLog)
            .where(AccessLog.client_id == client_id)
            .order_by(AccessLog.timestamp.desc())
            .limit(limit)
        )
        logs = session.scalars(stmt).all()
        
        records = []
        for log in logs:
            ts = log.timestamp
            if isinstance(ts, datetime):
                epoch = calendar.timegm(ts.utctimetuple())
            elif isinstance(ts, str):
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                    epoch = calendar.timegm(dt.utctimetuple())
                except Exception:
                    epoch = int(time.time())
            else:
                epoch = int(time.time())

            records.append({
                "user_id": log.user_id,
                "biometric_hash": log.tx_hash if log.tx_hash else "0x0000000000000000000000000000000000000000000000000000000000000000",
                "timestamp": epoch,
                "access_granted": bool(log.access_granted),
                "device_id": log.device_id or "API-SERVER-01",
                "match_score": log.match_score or 0.0,
                "client_id": client_id
            })
        return {"success": True, "client_id": client_id, "records": records}


def get_local_user_auth_history(user_id: str, limit: int = 10) -> dict:
    """Obtiene el historial de accesos de un usuario desde la DB local."""
    import calendar
    import time

    with SessionLocal() as session:
        stmt = (
            select(AccessLog)
            .where(AccessLog.user_id == user_id)
            .order_by(AccessLog.timestamp.desc())
            .limit(limit)
        )
        logs = session.scalars(stmt).all()
        
        records = []
        for log in logs:
            ts = log.timestamp
            if isinstance(ts, datetime):
                epoch = calendar.timegm(ts.utctimetuple())
            elif isinstance(ts, str):
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                    epoch = calendar.timegm(dt.utctimetuple())
                except Exception:
                    epoch = int(time.time())
            else:
                epoch = int(time.time())

            records.append({
                "user_id": log.user_id,
                "biometric_hash": log.tx_hash if log.tx_hash else "0x0000000000000000000000000000000000000000000000000000000000000000",
                "timestamp": epoch,
                "access_granted": bool(log.access_granted),
                "device_id": log.device_id or "API-SERVER-01",
                "match_score": log.match_score or 0.0,
                "client_id": log.client_id or "LOCAL_AUTH"
            })
        return {"success": True, "user_id": user_id, "records": records}


def get_user_count() -> int:
    """Retorna el número total de usuarios registrados."""
    with SessionLocal() as session:
        stmt = select(func.count(User.user_id))
        return session.scalar(stmt) or 0


def get_user_auth_info_by_username(username: str) -> Optional[dict]:
    """Obtiene los detalles de autenticación de un usuario por su username."""
    with SessionLocal() as session:
        stmt = select(User).where(User.username == username)
        user = session.scalars(stmt).first()
        if user:
            return {
                "user_id": user.user_id,
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "password_hash": user.password_hash,
                "associated_client_id": user.associated_client_id
            }
        return None


def get_user_auth_info_by_id(user_id: str) -> Optional[dict]:
    """Obtiene los detalles de autenticación de un usuario por su ID (Cédula)."""
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user:
            return {
                "user_id": user.user_id,
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "password_hash": user.password_hash,
                "associated_client_id": user.associated_client_id
            }
        return None


def update_user_password(user_id: str, new_password_hash: str) -> bool:
    """Actualiza la contraseña hasheada de un usuario en SQLite."""
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user:
            try:
                user.password_hash = new_password_hash
                user.updated_at = datetime.utcnow()
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Error al actualizar contraseña del usuario: {e}")
                return False
        return False


# =========================================================================
#           4. OPERACIONES CRUD PARA HARDWARE IOT & ACL [NUEVO]
# =========================================================================

def save_iot_device(
    device_id: str,
    device_name: str,
    device_type: str,
    location: Optional[str],
    client_secret_hash: str,
    is_active: bool = True
) -> bool:
    """Guarda o actualiza un dispositivo IoT en la base de datos."""
    with SessionLocal() as session:
        try:
            device = session.get(IoTDevice, device_id)
            if device:
                device.device_name = device_name
                device.device_type = device_type
                device.location = location
                device.client_secret_hash = client_secret_hash
                device.is_active = is_active
                device.updated_at = datetime.utcnow()
            else:
                device = IoTDevice(
                    device_id=device_id,
                    device_name=device_name,
                    device_type=device_type,
                    location=location,
                    client_secret_hash=client_secret_hash,
                    is_active=is_active
                )
                session.add(device)
            session.commit()
            logger.info(f"⚙️ Dispositivo IoT '{device_name}' (ID: {device_id}) guardado con éxito.")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Error al guardar dispositivo IoT: {e}")
            return False


def get_iot_device(device_id: str) -> Optional[dict]:
    """Busca y retorna un dispositivo IoT por su ID."""
    with SessionLocal() as session:
        device = session.get(IoTDevice, device_id)
        if device:
            return {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "location": device.location,
                "client_secret_hash": device.client_secret_hash,
                "is_active": device.is_active,
                "created_at": device.created_at,
                "updated_at": device.updated_at
            }
        return None


def delete_iot_device(device_id: str) -> bool:
    """Elimina un dispositivo IoT del sistema."""
    with SessionLocal() as session:
        device = session.get(IoTDevice, device_id)
        if device:
            try:
                session.delete(device)
                session.commit()
                logger.info(f"🗑️ Dispositivo IoT eliminado: {device_id}")
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Error al eliminar dispositivo IoT: {e}")
                return False
        return False


def save_acl_rule(
    device_id: str,
    user_id: Optional[str] = None,
    allowed_role: Optional[str] = None,
    schedule_rule: Optional[Dict[str, Any]] = None
) -> bool:
    """Registra una regla de acceso (ACL/RBAC) para un dispositivo IoT."""
    with SessionLocal() as session:
        try:
            schedule_json = json.dumps(schedule_rule) if schedule_rule else None
            rule = AccessControlList(
                device_id=device_id,
                user_id=user_id,
                allowed_role=allowed_role,
                schedule_rule=schedule_json
            )
            session.add(rule)
            session.commit()
            logger.info(f"🔒 Regla ACL creada para el dispositivo '{device_id}' (User: {user_id}, Role: {allowed_role}).")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Error al registrar regla ACL: {e}")
            return False


def get_device_acl_rules(device_id: str) -> List[dict]:
    """Retorna todas las reglas de acceso vigentes para un dispositivo específico."""
    with SessionLocal() as session:
        stmt = select(AccessControlList).where(AccessControlList.device_id == device_id)
        rules = session.scalars(stmt).all()
        
        result = []
        for r in rules:
            try:
                schedule = json.loads(r.schedule_rule) if r.schedule_rule else None
            except (json.JSONDecodeError, TypeError):
                schedule = None
            result.append({
                "id": r.id,
                "device_id": r.device_id,
                "user_id": r.user_id,
                "allowed_role": r.allowed_role,
                "schedule_rule": schedule,
                "created_at": r.created_at
            })
        return result


def get_device_by_token(token: str) -> Optional[dict]:
    """Busca en IoTDevice donde client_secret_hash == token y is_active == True."""
    with SessionLocal() as session:
        stmt = select(IoTDevice).where(
            IoTDevice.client_secret_hash == token,
            IoTDevice.is_active == True
        )
        device = session.scalars(stmt).first()
        if device:
            return {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "location": device.location,
                "client_secret_hash": device.client_secret_hash,
                "is_active": device.is_active,
                "created_at": device.created_at,
                "updated_at": device.updated_at
            }
        return None


def verify_device_access(device_id: str, user_id: str, user_role: str) -> bool:
    """Busca en AccessControlList si existe permiso para user_id O allowed_role en el device_id dado."""
    with SessionLocal() as session:
        stmt = select(AccessControlList).where(
            AccessControlList.device_id == device_id,
            or_(
                AccessControlList.user_id == user_id,
                AccessControlList.allowed_role == user_role
            )
        )
        rule = session.scalars(stmt).first()
        return rule is not None


# Ejecutar la creación de tablas al importar este módulo
init_sqlite()
logger.info("✅ Bases de datos listas y conectadas.")