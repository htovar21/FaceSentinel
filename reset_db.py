#!/usr/bin/env python
import os
import sys
import shutil

# Ajustar sys.path para poder importar configuraciones
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def reset_chromadb():
    chroma_path = settings.CHROMA_DB_PATH
    if os.path.exists(chroma_path):
        print(f"[*] Eliminando ChromaDB en: {chroma_path} ...")
        try:
            shutil.rmtree(chroma_path)
            print("[OK] ChromaDB eliminada correctamente.")
        except Exception as e:
            print(f"[ERROR] Al eliminar ChromaDB: {e}")
            print("Tip: Asegurate de que no haya servidores o procesos activos accediendo a la base de datos.")
    else:
        print(f"[INFO] ChromaDB no existe en la ruta especificada: {chroma_path}")

def reset_sqlite():
    sqlite_path = settings.SQLITE_DB_PATH
    if os.path.exists(sqlite_path):
        print(f"[*] Eliminando SQLite en: {sqlite_path} ...")
        try:
            # Eliminar archivo principal
            os.remove(sqlite_path)
            # Eliminar archivos temporales de SQLite si existen (WAL mode)
            for suffix in ['-wal', '-shm']:
                temp_file = sqlite_path + suffix
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            print("[OK] SQLite eliminada correctamente.")
        except Exception as e:
            print(f"[ERROR] Al eliminar SQLite: {e}")
            print("Tip: Asegurate de que no haya servidores o procesos activos accediendo a la base de datos.")
    else:
        print(f"[INFO] SQLite no existe en la ruta especificada: {sqlite_path}")

def main():
    print("==================================================")
    print("  ADVERTENCIA: SE REINICIARAN LAS BASES DE DATOS  ")
    print("==================================================")
    print("Esto eliminara de forma permanente todos los registros y embeddings.")
    
    confirm = input("¿Estas seguro de que deseas continuar? (s/N): ").strip().lower()
    if confirm != 's':
        print("[CANCELADO] Operacion cancelada por el usuario.")
        return

    # Realizar borrado
    reset_chromadb()
    reset_sqlite()
    print("\nProceso de reinicio completado.")
    print("Nota: Al iniciar de nuevo tu servidor FastAPI, las bases de datos vacias se recrearan automaticamente.")

if __name__ == "__main__":
    main()
