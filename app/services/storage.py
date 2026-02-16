import sqlite3
import chromadb
from app.core.config import settings

print("⏳ Inicializando bases de datos (SQLite y ChromaDB)...")

# 1. Inicializar ChromaDB (Base de datos vectorial)
# PersistentClient guarda los datos físicamente en la carpeta que definimos en .env
chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)

# Creamos una "colección" (como una tabla) para los rostros. 
# Usamos 'cosine' porque es la mejor forma matemática de comparar rostros en IA.
face_collection = chroma_client.get_or_create_collection(
    name="faces_collection", 
    metadata={"hnsw:space": "cosine"}
)

# 2. Funciones de SQLite (Base de datos tradicional)
def init_sqlite():
    """Crea la tabla de usuarios si no existe al arrancar el sistema."""
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_user_data(user_id: str, name: str, role: str, face_vector: list):
    """
    Guarda al usuario en AMBAS bases de datos al mismo tiempo.
    """
    # A. Guardar texto en SQLite
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    cursor = conn.cursor()
    # Usamos REPLACE por si queremos actualizar la foto de un usuario existente
    cursor.execute('INSERT OR REPLACE INTO users (user_id, name, role) VALUES (?, ?, ?)', 
                   (user_id, name, role))
    conn.commit()
    conn.close()

    # B. Guardar el vector matemático en ChromaDB
    face_collection.add(
        embeddings=[face_vector],
        ids=[user_id],
        metadatas=[{"name": name, "role": role}] # Metadatos extra por si acaso
    )
    return True

def get_user_by_id(user_id: str):
    """Busca los datos de un usuario por su ID en SQLite."""
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT name, role FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {"name": result[0], "role": result[1]}
    return None

# Ejecutar la creación de tablas apenas Python lea este archivo
init_sqlite()
print("✅ Bases de datos listas y conectadas.")