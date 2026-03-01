"""
storage.py — Capa de almacenamiento dual (SQLite + ChromaDB)
Gestiona la persistencia de datos biométricos y metadatos de usuarios.
"""

import sqlite3
import logging
import chromadb
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
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabla de logs de acceso (respaldo local de lo que va a la blockchain)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            access_granted BOOLEAN NOT NULL,
            match_score REAL,
            device_id TEXT,
            tx_hash TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("✅ Tablas SQLite creadas/verificadas.")


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
    cursor.execute('SELECT name, role FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return {"name": result["name"], "role": result["role"]}
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
                    device_id: str = None, tx_hash: str = None):
    """Guarda un registro de acceso local (respaldo de la blockchain)."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO access_logs (user_id, access_granted, match_score, device_id, tx_hash) '
        'VALUES (?, ?, ?, ?, ?)',
        (user_id, access_granted, match_score, device_id, tx_hash)
    )
    conn.commit()
    conn.close()
    logger.debug(f"📝 Log de acceso guardado para {user_id}")


def get_user_count() -> int:
    """Retorna el número total de usuarios registrados."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM users')
    result = cursor.fetchone()
    conn.close()
    return result["count"]


# Ejecutar la creación de tablas al importar este módulo
init_sqlite()
logger.info("✅ Bases de datos listas y conectadas.")