"""
migrate_device_tokens.py — Script de migración y verificación de base de datos SQLite para FaceSentinel.

Realiza las siguientes tareas de mantenimiento:
1. Añade la columna 'token_lookup_hash' a 'iot_devices' si no existe.
2. Crea índices para 'token_lookup_hash', 'access_logs.user_id' y 'access_logs.client_id'.
3. Inspecciona dispositivos existentes e informa sobre el estado de migración de sus tokens.
"""

import os
import sys
import sqlite3

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "sql", "database.db")


def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"[INFO] Base de datos no encontrada en {DB_PATH}. Se creara automaticamente al iniciar la API.")
        return

    print(f"[*] Conectando a la base de datos: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Verificar si existe la tabla iot_devices
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='iot_devices';")
        if cursor.fetchone():
            # Obtener columnas existentes en iot_devices
            cursor.execute("PRAGMA table_info(iot_devices);")
            columns = [col[1] for col in cursor.fetchall()]

            if "token_lookup_hash" not in columns:
                print("[+] Anadiendo columna 'token_lookup_hash' a la tabla 'iot_devices'...")
                cursor.execute("ALTER TABLE iot_devices ADD COLUMN token_lookup_hash VARCHAR;")
                conn.commit()
                print("[OK] Columna 'token_lookup_hash' anadida exitosamente.")
            else:
                print("[INFO] Columna 'token_lookup_hash' ya existe en 'iot_devices'.")

            if "lbp_threshold" not in columns:
                print("[+] Anadiendo columna 'lbp_threshold' a la tabla 'iot_devices'...")
                cursor.execute("ALTER TABLE iot_devices ADD COLUMN lbp_threshold FLOAT DEFAULT 3.2;")
                conn.commit()
                print("[OK] Columna 'lbp_threshold' anadida exitosamente.")
            else:
                print("[INFO] Columna 'lbp_threshold' ya existe en 'iot_devices'.")

            # Crear índice para token_lookup_hash
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_iot_devices_token_lookup_hash ON iot_devices(token_lookup_hash);"
            )
            conn.commit()
            print("[OK] Indice 'ix_iot_devices_token_lookup_hash' asegurado.")

            # Revisar dispositivos existentes
            cursor.execute("SELECT device_id, device_name, token_lookup_hash FROM iot_devices;")
            devices = cursor.fetchall()
            if devices:
                print(f"\nDispositivos IoT registrados ({len(devices)}):")
                null_count = 0
                for dev_id, name, lookup in devices:
                    status = "OK (Migrado)" if lookup else "Pendiente (se auto-migrara en su primer acceso o re-registro)"
                    if not lookup:
                        null_count += 1
                    print(f"  - ID: {dev_id} | Nombre: {name} | Estado: {status}")

                if null_count > 0:
                    print(f"\n[NOTA] Hay {null_count} dispositivo(s) sin lookup hash.")
                    print("   FaceSentinel cuenta con migracion automatica 'lazy': tan pronto como el dispositivo")
                    print("   se autentique con su token, el sistema calculara y guardara su hash automaticamente.")
            else:
                print("[INFO] No hay dispositivos IoT registrados actualmente.")
        else:
            print("[INFO] Tabla 'iot_devices' no existe aun en la base de datos.")

        # 2. Asegurar índices en access_logs
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_logs';")
        if cursor.fetchone():
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_access_logs_user_id ON access_logs(user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_access_logs_client_id ON access_logs(client_id);")
            conn.commit()
            print("[OK] Indices en 'access_logs' (user_id, client_id) creados/asegurados.")

        print("\n[EXITO] Proceso de migracion y optimizacion de base de datos completado exitosamente.")

    except Exception as e:
        print(f"[ERROR] Error durante la migracion: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
