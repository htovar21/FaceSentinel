#!/usr/bin/env python
import os
import sys
import json
import sqlite3

# Ajustar sys.path para poder importar módulos de la aplicación
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.core.security import hash_client_secret
from app.services.storage import face_collection

def create_test_users():
    print("==================================================")
    # 1. Definir datos del Cliente OAuth
    client_id = "fs_test_client"
    client_secret = "fss_test_secret_123456789"
    client_secret_hash = hash_client_secret(client_secret)
    redirect_uris = ["https://www.jwt.io/"]
    app_name = "Test App"

    # 2. Definir datos del Desarrollador
    dev_user_id = "dev_123"
    dev_username = "developer"
    dev_password = "developerpassword"
    dev_password_hash = hash_client_secret(dev_password)
    dev_name = f"Desarrollador {app_name}"

    # 3. Definir datos del Usuario Regular
    user_id = "user_123"
    user_username = "user"
    user_name = "Test User"
    
    # Obtener ruta de la BD
    db_path = settings.SQLITE_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Asegurar existencia de las tablas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS oauth_clients (
                client_id TEXT PRIMARY KEY,
                client_secret_hash TEXT NOT NULL,
                redirect_uris TEXT NOT NULL,
                app_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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

        # Insertar o reemplazar el cliente OAuth
        redirect_uris_json = json.dumps(redirect_uris)
        cursor.execute(
            "INSERT OR REPLACE INTO oauth_clients (client_id, client_secret_hash, redirect_uris, app_name) VALUES (?, ?, ?, ?)",
            (client_id, client_secret_hash, redirect_uris_json, app_name)
        )

        # Insertar o reemplazar el Desarrollador
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, name, role, password_hash, associated_client_id) VALUES (?, ?, ?, ?, ?, ?)",
            (dev_user_id, dev_username, dev_name, "Developer", dev_password_hash, client_id)
        )

        # Insertar o reemplazar el Usuario Regular en SQLite
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, name, role, password_hash, associated_client_id) VALUES (?, ?, ?, ?, NULL, NULL)",
            (user_id, user_username, user_name, "User")
        )

        conn.commit()
        conn.close()
        print(f"[OK] Cliente OAuth '{app_name}' registrado.")
        print(f"[OK] Usuario Desarrollador registrado:")
        print(f"   - Username: {dev_username}")
        print(f"   - Password: {dev_password}")
        print(f"   - Client ID: {client_id}")
        print(f"   - Client Secret: {client_secret}")
        print(f"[OK] Usuario Regular registrado en SQLite:")
        print(f"   - Username: {user_username}")
        print(f"   - User ID: {user_id}")

        # Insertar vector dummy en ChromaDB para el Usuario Regular
        try:
            dummy_vector = [0.0] * 512  # ArcFace usa embeddings de 512 dimensiones
            face_collection.upsert(
                embeddings=[dummy_vector],
                ids=[user_id],
                metadatas=[{"name": user_name, "role": "User"}]
            )
            print(f"[OK] Vector biometrico dummy para '{user_name}' insertado en ChromaDB.")
        except Exception as e:
            print(f"[WARN] Advertencia al insertar en ChromaDB: {e}")
            print("   Asegurese de que ChromaDB este disponible e inicializado.")

        # Imprimir URLs de prueba de redirección
        frontend_url = "http://localhost:5173"  # O el puerto que use el frontend
        redirect_param = f"?client_id={client_id}&redirect_uri=https://www.jwt.io/&app_name={app_name.replace(' ', '%20')}"
        print("\nPara probar la redireccion a jwt.io al autenticarse, abre el frontend en la siguiente URL:")
        print(f"URL: {frontend_url}/login{redirect_param}")

    except Exception as e:
        print(f"[ERROR] Error al crear los usuarios de prueba: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    create_test_users()
