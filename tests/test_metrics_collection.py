"""
test_metrics_collection.py — Pruebas del Sistema de Telemetría y Matriz de Confusión
Verifica:
1. Creación e integridad de las 28 columnas en metricas_tesis.csv
2. Resiliencia y fallback a JSONL cuando el archivo está bloqueado (simulación de Excel)
3. Sincronización automática (flush) al liberarse el archivo
4. Generación de reportes Markdown y LaTeX desde export_confusion_matrix.py
"""

import os
import csv
import json
import pytest
import tempfile
from unittest.mock import patch

from app.services.metrics_collector import (
    log_experiment_metric,
    flush_backup_to_csv,
    CSV_HEADERS,
    CSV_METRICS_PATH,
    BACKUP_JSONL_PATH,
)
from export_confusion_matrix import generate_reports, calc_stats, parse_bool, parse_float


def test_csv_headers_completeness():
    assert len(CSV_HEADERS) == 28
    assert "t_network_rtt_ms" in CSV_HEADERS
    assert "environmental_condition" in CSV_HEADERS
    assert "test_type" in CSV_HEADERS
    assert "bc_seal_time_ms" in CSV_HEADERS


def test_log_experiment_metric_live():
    # Registrar evento de prueba
    sample_metric = {
        "test_type": "LIVE_USER",
        "environmental_condition": "NORMAL",
        "user_id": "TEST_USER_01",
        "granted": True,
        "rejection_reason": "NONE_GRANTED",
        "t_ear_edge_ms": 22.5,
        "t_edge_total_ms": 38.0,
        "t_network_rtt_ms": 15.2,
        "t_lbp_ms": 12.4,
        "t_fft_ms": 8.1,
        "t_arcface_ms": 245.0,
        "t_chroma_ms": 11.2,
        "t_sqlite_ms": 2.1,
        "t_backend_total_ms": 285.0,
        "t_total_end2end_ms": 338.2,
        "ear_open": 0.285,
        "ear_blink": 0.142,
        "lbp_entropy": 4.25,
        "lbp_threshold": 3.2,
        "lbp_variance": 0.0045,
        "liveness_score": 0.92,
        "cosine_distance": 0.2310,
        "match_threshold": 0.68,
        "bc_tx_hash": "0xabc123456789",
        "bc_gas_used": 68432,
        "bc_block_number": 42,
        "bc_seal_time_ms": 115.4,
    }

    ok = log_experiment_metric(sample_metric)
    assert ok is True
    assert os.path.exists(CSV_METRICS_PATH)

    # Verificar que se escribió con 28 columnas
    with open(CSV_METRICS_PATH, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) >= 2  # Header + at least 1 row
        assert len(reader[0]) == 28


def test_excel_file_lock_fallback_resilience():
    """Simula que Excel tiene abierto y bloqueado el CSV para verificar el fallback JSONL."""
    sample_locked_metric = {
        "test_type": "SPOOF_PHOTO_PRINT",
        "environmental_condition": "HIGH_LIGHT",
        "user_id": "UNKNOWN",
        "granted": False,
        "rejection_reason": "SPOOFING_DETECTED",
        "t_ear_edge_ms": 21.0,
        "t_edge_total_ms": 35.0,
        "t_network_rtt_ms": 14.0,
        "t_lbp_ms": 11.0,
        "t_fft_ms": 7.5,
        "t_arcface_ms": 0.0,
        "t_chroma_ms": 0.0,
        "t_sqlite_ms": 1.8,
        "t_backend_total_ms": 22.0,
        "t_total_end2end_ms": 71.0,
        "ear_open": 0.28,
        "ear_blink": 0.13,
        "lbp_entropy": 2.95,
        "lbp_threshold": 3.2,
        "lbp_variance": 0.0012,
        "liveness_score": 0.35,
        "cosine_distance": 0.0,
        "match_threshold": 0.68,
        "bc_tx_hash": "0xdeadbeef",
        "bc_gas_used": 68432,
        "bc_block_number": 43,
        "bc_seal_time_ms": 110.0,
    }

    # Simular PermissionError en _write_row_to_csv
    with patch("app.services.metrics_collector._write_row_to_csv", side_effect=PermissionError("File locked by Excel")):
        ok = log_experiment_metric(sample_locked_metric)
        assert ok is True  # No falla ni lanza 500
        assert os.path.exists(BACKUP_JSONL_PATH)

    # Verificar que el backup contiene el registro
    with open(BACKUP_JSONL_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data["test_type"] == "SPOOF_PHOTO_PRINT"
        assert data["granted"] is False

    # Sincronizar backup al CSV
    synced = flush_backup_to_csv()
    assert synced >= 1


def test_export_confusion_matrix_and_latex():
    """Verifica que el script export_confusion_matrix procese los datos y genere los archivos."""
    generate_reports()

    from export_confusion_matrix import MD_REPORT_PATH, TEX_REPORT_PATH
    assert os.path.exists(MD_REPORT_PATH)
    assert os.path.exists(TEX_REPORT_PATH)

    # Verificar contenido de LaTeX
    with open(TEX_REPORT_PATH, "r", encoding="utf-8") as f:
        tex = f.read()
        assert "\\begin{table}" in tex
        assert "\\label{tab:matriz_confusion}" in tex
        assert "\\label{tab:metricas_biometricas}" in tex
        assert "\\label{tab:latencias_pipeline}" in tex
        assert "\\label{tab:blockchain_metrics}" in tex
