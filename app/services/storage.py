"""
storage.py — Capa de almacenamiento dual (SQLite + ChromaDB)
Gestiona la persistencia de datos biométricos y metadatos de usuarios.
"""

import sqlite3
import json
import logging
import chromadb
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

logger.info("⏳ Inicializando bases de datos (SQLite y ChromaDB)...")

# =========================================================================
#           1. CHROMADB (Base de datos vectorial)
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
#           2. SQLITE (Base de datos relacional)
# =========================================================================

def _get_connection():
    """Obtiene una conexión a SQLite con WAL mode para mejor concurrencia."""
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_sqlite():
    """Crea las tablas si no existen al arrancar el sistema."""
    conn = _get_connection()
    cursor = conn.cursor()

    # Tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT,
            associated_client_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migración de columnas por si la tabla ya existía
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN associated_client_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass

    # Tabla de logs de acceso (respaldo local de lo que va a la blockchain)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            access_granted BOOLEAN NOT NULL,
            match_score REAL,
            device_id TEXT,
            tx_hash TEXT,
            client_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    try:
        cursor.execute("ALTER TABLE access_logs ADD COLUMN client_id TEXT")
    except sqlite3.OperationalError:
        pass

    # Tabla de clientes OAuth/SSO registrados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id TEXT PRIMARY KEY,
            client_secret_hash TEXT NOT NULL,
            redirect_uris TEXT NOT NULL,
            app_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("✅ Tablas SQLite creadas/verificadas.")


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
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        # 1. Guardar cliente
        redirect_uris_json = json.dumps(redirect_uris)
        cursor.execute(
            'INSERT INTO oauth_clients (client_id, client_secret_hash, redirect_uris, app_name) VALUES (?, ?, ?, ?)',
            (client_id, client_secret_hash, redirect_uris_json, app_name)
        )
        
        # 2. Crear cuenta de desarrollador asociada
        cursor.execute(
            'INSERT OR REPLACE INTO users (user_id, username, name, role, password_hash, associated_client_id) VALUES (?, ?, ?, ?, ?, ?)',
            (developer_user_id, developer_username, f"Desarrollador {app_name}", "Developer", developer_password_hash, client_id)
        )
        
        conn.commit()
        logger.info(f"🔑 Cliente OAuth '{app_name}' (ID: {client_id}) y desarrollador '{developer_username}' guardados con éxito.")
        return True
    except sqlite3.IntegrityError as e:
        logger.error(f"❌ Error de integridad al guardar el cliente OAuth y su desarrollador: {e}")
        return False
    finally:
        conn.close()


def get_oauth_client(client_id: str) -> Optional[dict]:
    """
    Busca y retorna un cliente OAuth por su ID.
    Deserializa las URIs de redirección desde formato JSON.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT client_id, client_secret_hash, redirect_uris, app_name FROM oauth_clients WHERE client_id = ?',
        (client_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        try:
            uris = json.loads(row["redirect_uris"])
        except (json.JSONDecodeError, TypeError):
            uris = []
        return {
            "client_id": row["client_id"],
            "client_secret_hash": row["client_secret_hash"],
            "redirect_uris": uris,
            "app_name": row["app_name"]
        }
    return None


def get_all_oauth_clients() -> list[dict]:
    """
    Retorna todas las aplicaciones de terceros registradas en el sistema.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT client_id, redirect_uris, app_name, created_at FROM oauth_clients ORDER BY created_at DESC'
    )
    rows = cursor.fetchall()
    conn.close()

    clients = []
    for row in rows:
        try:
            uris = json.loads(row["redirect_uris"])
        except (json.JSONDecodeError, TypeError):
            uris = []
        clients.append({
            "client_id": row["client_id"],
            "app_name": row["app_name"],
            "redirect_uris": uris,
            "created_at": row["created_at"]
        })
    return clients



def save_user_data(user_id: str, name: str, role: str, face_vector: list):
    """Guarda al usuario en AMBAS bases de datos al mismo tiempo."""
    # A. Guardar texto en SQLite
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO users (user_id, name, role, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
        (user_id, name, role)
    )
    conn.commit()
    conn.close()

    # B. Guardar el vector matemático en ChromaDB
    # Usamos upsert para que se actualice si ya existe
    face_collection.upsert(
        embeddings=[face_vector],
        ids=[user_id],
        metadatas=[{"name": name, "role": role}]
    )

    logger.info(f"💾 Usuario '{name}' (ID: {user_id}) guardado en SQLite + ChromaDB.")
    return True


def get_user_by_id(user_id: str):
    """Busca los datos de un usuario por su ID en SQLite."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name, role, username FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return {"name": result["name"], "role": result["role"], "username": result["username"]}
    return None


def delete_user(user_id: str) -> bool:
    """Elimina un usuario de la base de datos local SQLite."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if deleted:
        logger.info(f"🗑️ Usuario eliminado localmente: {user_id}")
    return deleted


def get_all_users():
    """Retorna todos los usuarios registrados."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, name, role, created_at FROM users ORDER BY created_at DESC')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def save_access_log(user_id: str, access_granted: bool, match_score: float = None,
                    device_id: str = None, tx_hash: str = None, client_id: str = None):
    """Guarda un registro de acceso local (respaldo de la blockchain)."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO access_logs (user_id, access_granted, match_score, device_id, tx_hash, client_id) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, access_granted, match_score, device_id, tx_hash, client_id)
    )
    conn.commit()
    conn.close()
    logger.debug(f"📝 Log de acceso guardado para {user_id}")


def get_local_client_logs(client_id: str, limit: int = 50) -> dict:
    """Obtiene los registros de acceso locales para un cliente."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT user_id, access_granted, match_score, device_id, tx_hash, timestamp '
        'FROM access_logs WHERE client_id = ? ORDER BY timestamp DESC LIMIT ?',
        (client_id, limit)
    )
    records = []
    import calendar
    from datetime import datetime
    import time
    for row in cursor.fetchall():
        ts = row["timestamp"]
        if isinstance(ts, str):
            try:
                dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                epoch = calendar.timegm(dt.utctimetuple())
            except Exception:
                epoch = int(time.time())
        else:
            epoch = int(ts) if ts else int(time.time())

        records.append({
            "user_id": row["user_id"],
            "biometric_hash": row["tx_hash"] if row["tx_hash"] else "0x0000000000000000000000000000000000000000000000000000000000000000",
            "timestamp": epoch,
            "access_granted": bool(row["access_granted"]),
            "device_id": row["device_id"] or "API-SERVER-01",
            "match_score": row["match_score"] or 0.0,
            "client_id": client_id
        })
    conn.close()
    return {"success": True, "client_id": client_id, "records": records}


def get_local_user_auth_history(user_id: str, limit: int = 10) -> dict:
    """Obtiene el historial de accesos de un usuario desde la DB local."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT user_id, access_granted, match_score, device_id, tx_hash, timestamp, client_id '
        'FROM access_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
        (user_id, limit)
    )
    records = []
    import calendar
    from datetime import datetime
    import time
    for row in cursor.fetchall():
        ts = row["timestamp"]
        if isinstance(ts, str):
            try:
                dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                epoch = calendar.timegm(dt.utctimetuple())
            except Exception:
                epoch = int(time.time())
        else:
            epoch = int(ts) if ts else int(time.time())

        records.append({
            "user_id": row["user_id"],
            "biometric_hash": row["tx_hash"] if row["tx_hash"] else "0x0000000000000000000000000000000000000000000000000000000000000000",
            "timestamp": epoch,
            "access_granted": bool(row["access_granted"]),
            "device_id": row["device_id"] or "API-SERVER-01",
            "match_score": row["match_score"] or 0.0,
            "client_id": row["client_id"] or "LOCAL_AUTH"
        })
    conn.close()
    return {"success": True, "user_id": user_id, "records": records}


def get_user_count() -> int:
    """Retorna el número total de usuarios registrados."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM users')
    result = cursor.fetchone()
    conn.close()
    return result["count"]


def get_user_auth_info_by_username(username: str) -> Optional[dict]:
    """Obtiene los detalles de autenticación de un usuario por su username."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, name, role, password_hash, associated_client_id FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "name": row["name"],
            "role": row["role"],
            "password_hash": row["password_hash"],
            "associated_client_id": row["associated_client_id"]
        }
    return None


def get_user_auth_info_by_id(user_id: str) -> Optional[dict]:
    """Obtiene los detalles de autenticación de un usuario por su ID (Cédula)."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, name, role, password_hash, associated_client_id FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "name": row["name"],
            "role": row["role"],
            "password_hash": row["password_hash"],
            "associated_client_id": row["associated_client_id"]
        }
    return None


def update_user_password(user_id: str, new_password_hash: str) -> bool:
    """Actualiza la contraseña hasheada de un usuario en SQLite."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET password_hash = ? WHERE user_id = ?', (new_password_hash, user_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


# Ejecutar la creación de tablas al importar este módulo
init_sqlite()
logger.info("✅ Bases de datos listas y conectadas.")