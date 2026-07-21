#!/usr/bin/env python3
"""
clear_biometrics.py — Script interactivo para limpiar datos biométricos faciales.
Permite eliminar la biometría de un usuario específico o de todos, 
facilitando las pruebas con un mismo rostro en diferentes identidades.
"""

import os
import sys
import sqlite3
import chromadb

# Ajustar sys.path para poder importar configuraciones
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def load_biometric_data():
    """Carga los registros de ChromaDB y los cruza con la información de SQLite."""
    chroma_path = settings.CHROMA_DB_PATH
    sqlite_path = settings.SQLITE_DB_PATH
    
    records = []
    
    # 1. Leer de ChromaDB
    if not os.path.exists(chroma_path):
        return [], "La base de datos de ChromaDB no existe."
        
    try:
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        col = chroma_client.get_collection("faces_collection")
        results = col.get()
        ids = results.get('ids', [])
        metadatas = results.get('metadatas', [])
    except Exception as e:
        return [], f"Error al leer ChromaDB: {e}"

    if not ids:
        return [], None

    # 2. Consultar SQLite para obtener detalles adicionales si existen
    sqlite_users = {}
    if os.path.exists(sqlite_path):
        try:
            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id, name, role, password_hash FROM users")
            for row in cursor.fetchall():
                sqlite_users[row['user_id']] = {
                    "name": row['name'],
                    "role": row['role'],
                    "has_password": row['password_hash'] is not None
                }
            conn.close()
        except Exception as e:
            print(f"[WARN] No se pudo leer SQLite para cruzar datos: {e}")

    # 3. Consolidar registros
    for i, user_id in enumerate(ids):
        metadata = metadatas[i] if i < len(metadatas) else {}
        name = metadata.get('name', 'Desconocido')
        role = metadata.get('role', 'Usuario')
        has_password = False
        in_sqlite = user_id in sqlite_users
        
        if in_sqlite:
            name = sqlite_users[user_id]["name"]
            role = sqlite_users[user_id]["role"]
            has_password = sqlite_users[user_id]["has_password"]
            
        records.append({
            "user_id": user_id,
            "name": name,
            "role": role,
            "has_password": has_password,
            "in_sqlite": in_sqlite
        })
        
    return records, None

def delete_user_biometric(user_record):
    """Elimina la biometría de un usuario específico de ChromaDB y SQLite."""
    user_id = user_record["user_id"]
    name = user_record["name"]
    chroma_path = settings.CHROMA_DB_PATH
    sqlite_path = settings.SQLITE_DB_PATH
    
    # 1. Eliminar de ChromaDB
    try:
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        col = chroma_client.get_collection("faces_collection")
        col.delete(ids=[user_id])
        print(f"[OK] [ChromaDB] Biometria facial de '{name}' (ID: {user_id}) eliminada.")
    except Exception as e:
        print(f"[ERROR] [ChromaDB] Error al eliminar biometria: {e}")
        return False

    # 2. Eliminar de SQLite si es un usuario puramente biometrico (sin contrasena)
    if user_record["in_sqlite"]:
        if not user_record["has_password"]:
            try:
                conn = sqlite3.connect(sqlite_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                conn.commit()
                conn.close()
                print(f"[OK] [SQLite] Usuario '{name}' (ID: {user_id}) eliminado de la base de datos relacional.")
            except Exception as e:
                print(f"[ERROR] [SQLite] Error al eliminar usuario: {e}")
        else:
            print(f"[INFO] [SQLite] El usuario '{name}' tiene contrasena establecida. Se conservo su perfil relacional.")
    
    return True

def main():
    print("==================================================")
    print("      FaceSentinel - Control de Biometrias        ")
    print("==================================================")
    
    while True:
        records, error = load_biometric_data()
        
        if error:
            print(f"[ERROR] Error: {error}")
            break
            
        if not records:
            print("\n[INFO] No hay registros biometricos cargados en el sistema.")
            break
            
        print(f"\nSe encontraron {len(records)} rostro(s) registrado(s):")
        print("-" * 50)
        for idx, r in enumerate(records, 1):
            pwd_str = " (Con contrasena)" if r["has_password"] else " (Solo Biometrico)"
            print(f"[{idx}] {r['name']} - ID: {r['user_id']} | Rol: {r['role']}{pwd_str}")
        print("-" * 50)
        
        print("\nOpciones:")
        print(" [Numero] - Eliminar biometria de ese usuario (ej. 1)")
        print(" [all]    - Eliminar TODOS los registros biometricos")
        print(" [q]      - Salir")
        
        try:
            choice = input("\nSeleccione una opcion: ").strip().lower()
        except KeyboardInterrupt:
            print("\nSaliendo...")
            break
            
        if choice == 'q':
            print("Saliendo...")
            break
            
        elif choice == 'all':
            confirm = input("[WARN] ¿Esta seguro de eliminar TODOS los rostros registrados? (s/N): ").strip().lower()
            if confirm == 's':
                print("\nEliminando todos los registros...")
                success_count = 0
                for r in records:
                    if delete_user_biometric(r):
                        success_count += 1
                print(f"\n[OK] Se eliminaron {success_count} registros biometricos.")
                break
            else:
                print("[INFO] Operacion cancelada.")
                
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(records):
                target = records[idx]
                confirm = input(f"¿Eliminar biometria de '{target['name']}'? (s/N): ").strip().lower()
                if confirm == 's':
                    delete_user_biometric(target)
                else:
                    print("[INFO] Operacion cancelada.")
            else:
                print("[ERROR] Numero de opcion invalido.")
        else:
            print("[ERROR] Opcion no reconocida. Intente de nuevo.")

if __name__ == "__main__":
    main()
