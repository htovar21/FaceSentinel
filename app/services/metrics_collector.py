"""
metrics_collector.py — Módulo de Telemetría y Recolección de Datos Experimentales
Diseñado para registrar las métricas de rendimiento del sistema FaceSentinel
para el Capítulo IV de la tesis académica.

Características:
1. Escritura thread-safe en data/metricas_tesis.csv
2. Tolerancia a fallos de bloqueo de SO (PermissionError cuando el CSV está abierto en Excel)
3. Búfer de respaldo JSONL con auto-flush al liberar el archivo
4. Captura de latencias Edge, Red (RTT), Backend y Blockchain
"""

import os
import csv
import json
import time
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Rutas de almacenamiento
BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_METRICS_PATH = os.path.join(DATA_DIR, "metricas_tesis.csv")
BACKUP_JSONL_PATH = os.path.join(DATA_DIR, "metricas_tesis_backup.jsonl")

# Cabeceras del dataset experimental (28 columnas)
CSV_HEADERS = [
    "timestamp",
    "test_type",
    "environmental_condition",
    "user_id",
    "granted",
    "rejection_reason",
    "t_ear_edge_ms",
    "t_edge_total_ms",
    "t_network_rtt_ms",
    "t_lbp_ms",
    "t_fft_ms",
    "t_arcface_ms",
    "t_chroma_ms",
    "t_sqlite_ms",
    "t_backend_total_ms",
    "t_total_end2end_ms",
    "ear_open",
    "ear_blink",
    "lbp_entropy",
    "lbp_threshold",
    "lbp_variance",
    "liveness_score",
    "cosine_distance",
    "match_threshold",
    "bc_tx_hash",
    "bc_gas_used",
    "bc_block_number",
    "bc_seal_time_ms",
]

_file_lock = threading.Lock()


def _ensure_data_dir():
    """Asegura que el directorio data/ exista."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _init_csv_if_missing():
    """Inicializa el archivo CSV con las cabeceras correspondientes si no existe."""
    _ensure_data_dir()
    if not os.path.exists(CSV_METRICS_PATH) or os.path.getsize(CSV_METRICS_PATH) == 0:
        with open(CSV_METRICS_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)


def _write_row_to_csv(row_dict: Dict[str, Any]) -> bool:
    """Intenta escribir una fila en el archivo CSV."""
    _init_csv_if_missing()
    row = [row_dict.get(h, "") for h in CSV_HEADERS]
    with open(CSV_METRICS_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)
    return True


def _append_to_backup_jsonl(row_dict: Dict[str, Any]):
    """Guarda en el archivo de respaldo si el CSV principal está bloqueado por el SO."""
    _ensure_data_dir()
    with open(BACKUP_JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row_dict, ensure_ascii=False) + "\n")


def flush_backup_to_csv() -> int:
    """
    Intenta volcar los registros acumulados en el archivo de respaldo hacia el CSV principal.
    Retorna el número de registros sincronizados.
    """
    if not os.path.exists(BACKUP_JSONL_PATH) or os.path.getsize(BACKUP_JSONL_PATH) == 0:
        return 0

    recovered_count = 0
    remaining_lines = []

    try:
        with open(BACKUP_JSONL_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return 0

        _init_csv_if_missing()
        with open(CSV_METRICS_PATH, "a", newline="", encoding="utf-8") as f_csv:
            writer = csv.writer(f_csv)
            for idx, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    row = [data.get(h, "") for h in CSV_HEADERS]
                    writer.writerow(row)
                    recovered_count += 1
                except Exception as ex:
                    logger.warning(f"Error procesando línea {idx} de backup JSONL: {ex}")
                    remaining_lines.append(line)

        # Si todo se procesó, limpiamos el archivo de backup
        if remaining_lines:
            with open(BACKUP_JSONL_PATH, "w", encoding="utf-8") as f_back:
                f_back.writelines(remaining_lines)
        else:
            try:
                os.remove(BACKUP_JSONL_PATH)
            except Exception:
                # Si no se puede borrar, vaciarlo
                with open(BACKUP_JSONL_PATH, "w", encoding="utf-8") as f_back:
                    pass

        if recovered_count > 0:
            logger.info(f"🔄 Sincronizados {recovered_count} registros pendientes desde backup JSONL al CSV.")
    except (PermissionError, IOError, OSError) as e:
        logger.warning(f"No se pudo sincronizar backup JSONL al CSV (archivo bloqueado): {e}")

    return recovered_count


def log_experiment_metric(metric_data: Dict[str, Any]) -> bool:
    """
    Punto de entrada principal para registrar un evento experimental.
    Garantiza que ningún dato se pierda ante bloqueos de archivo de Excel o concurrencia.
    """
    # Formatear timestamp si no viene
    if "timestamp" not in metric_data or not metric_data["timestamp"]:
        metric_data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    # Asegurar valores por defecto para campos numéricos
    defaults = {
        "test_type": "LIVE_USER",
        "environmental_condition": "NORMAL",
        "user_id": "UNKNOWN",
        "granted": False,
        "rejection_reason": "",
        "t_ear_edge_ms": 0.0,
        "t_edge_total_ms": 0.0,
        "t_network_rtt_ms": 0.0,
        "t_lbp_ms": 0.0,
        "t_fft_ms": 0.0,
        "t_arcface_ms": 0.0,
        "t_chroma_ms": 0.0,
        "t_sqlite_ms": 0.0,
        "t_backend_total_ms": 0.0,
        "t_total_end2end_ms": 0.0,
        "ear_open": 0.0,
        "ear_blink": 0.0,
        "lbp_entropy": 0.0,
        "lbp_threshold": 3.2,
        "lbp_variance": 0.0,
        "liveness_score": 0.0,
        "cosine_distance": 0.0,
        "match_threshold": 0.68,
        "bc_tx_hash": "",
        "bc_gas_used": 0,
        "bc_block_number": 0,
        "bc_seal_time_ms": 0.0,
    }

    final_data = {**defaults, **metric_data}

    # Redondear números flotantes para consistencia en el CSV
    for k, v in final_data.items():
        if isinstance(v, float):
            final_data[k] = round(v, 4)

    with _file_lock:
        try:
            _write_row_to_csv(final_data)
            # Intentar volcar backups previos si el CSV está libre
            flush_backup_to_csv()
            return True
        except (PermissionError, IOError, OSError) as e:
            logger.warning(
                f"⚠️ CSV de métricas bloqueado por el SO (¿abierto en Excel?): {e}. "
                f"Guardando evento en '{BACKUP_JSONL_PATH}' para no perder datos."
            )
            try:
                _append_to_backup_jsonl(final_data)
                return True
            except Exception as backup_err:
                logger.error(f"❌ Error crítico guardando métrica en backup: {backup_err}")
                return False
        except Exception as e:
            logger.error(f"❌ Error inesperado registrando métricas experimentales: {e}")
            return False
