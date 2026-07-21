#!/usr/bin/env python
import os
import sys
import sqlite3
import chromadb

# Ajustar sys.path para poder importar configuraciones
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def clear_biometrics():
    print("==================================================")
    print("  ELIMINANDO TODAS LAS BIOMETRÍAS FACIALES         ")
    print("==================================================")
    
    # 1. Conectar y limpiar ChromaDB
    chroma_path = settings.CHROMA_DB_PATH
    if os.path.exists(chroma_path):
        try:
            chroma_client = chromadb.PersistentClient(path=chroma_path)
            # Intentar obtener la colección
            try:
                col = chroma_client.get_collection("faces_collection")
                results = col.get()
                ids = results.get('ids', [])
                if ids:
                    print(f"[*] Encontrados {len(ids)} registros biométricos en ChromaDB: {ids}")
                    col.delete(ids=ids)
                    print("[OK] Registros biométricos eliminados de ChromaDB.")
                else:
                    print("[INFO] No se encontraron registros biométricos en ChromaDB.")
            except Exception as col_err:
                print(f"[INFO] No se pudo acceder a 'faces_collection' en ChromaDB: {col_err}")
                ids = []
        except Exception as e:
            print(f"[ERROR] Al acceder a ChromaDB: {e}")
            ids = []
    else:
        print(f"[INFO] ChromaDB no existe en: {chroma_path}")
        ids = []

    # 2. Conectar y limpiar SQLite (usuarios correspondientes que solo son biométricos)
    sqlite_path = settings.SQLITE_DB_PATH
    if os.path.exists(sqlite_path):
        try:
            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Buscar usuarios que se van a eliminar
            # Queremos eliminar los que están en la lista de IDs biométricos,
            # y también cualquier usuario final que no tenga contraseña hasheada (role no Admin/Developer).
            cursor.execute("SELECT user_id, name, role FROM users WHERE password_hash IS NULL")
            biometric_users = cursor.fetchall()
            
            users_to_delete = set(ids)
            for u in biometric_users:
                users_to_delete.add(u['user_id'])
                
            if users_to_delete:
                print(f"[*] Eliminando {len(users_to_delete)} usuarios biométricos de SQLite...")
                placeholders = ', '.join('?' for _ in users_to_delete)
                cursor.execute(f"DELETE FROM users WHERE user_id IN ({placeholders})", list(users_to_delete))
                deleted_count = cursor.rowcount
                conn.commit()
                print(f"[OK] {deleted_count} usuarios biométricos eliminados de SQLite.")
            else:
                print("[INFO] No hay usuarios biométricos para eliminar de SQLite.")
                
            conn.close()
        except Exception as e:
            print(f"[ERROR] Al limpiar usuarios en SQLite: {e}")
    else:
        print(f"[INFO] SQLite no existe en: {sqlite_path}")

    print("\nProceso de borrado de biometrías completado.")

if __name__ == "__main__":
    clear_biometrics()
