#!/usr/bin/env python
import sqlite3
import argparse
import sys
import os

# Ajustar sys.path para poder importar configuraciones si es necesario
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bcrypt
from app.core.config import settings

def main():
    parser = argparse.ArgumentParser(description="Crear un usuario administrador en la base de datos de FaceSentinel.")
    parser.add_argument("--cedula", required=True, help="Cédula del administrador (user_id)")
    parser.add_argument("--username", required=True, help="Nombre de usuario del administrador (username)")
    parser.add_argument("--name", required=True, help="Nombre completo del administrador")
    parser.add_argument("--password", required=True, help="Contraseña en texto plano para el administrador")
    
    args = parser.parse_args()
    
    # 1. Hashear contraseña usando la misma configuración de la aplicación (bcrypt)
    password_hash = bcrypt.hashpw(args.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # 2. Obtener ruta de la BD desde config
    db_path = settings.SQLITE_DB_PATH
    
    # Asegurar que el directorio de la BD exista
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Asegurar existencia de la tabla users
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
        
        # Insertar o reemplazar el usuario administrador
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, name, role, password_hash, associated_client_id) VALUES (?, ?, ?, ?, ?, NULL)",
            (args.cedula, args.username, args.name, "Admin", password_hash)
        )
        conn.commit()
        conn.close()
        print(f"✅ Usuario administrador '{args.username}' ({args.name}) creado correctamente.")
    except Exception as e:
        print(f"❌ Error al crear el usuario administrador en la base de datos: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
