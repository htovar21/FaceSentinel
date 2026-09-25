#!/usr/bin/env python3
"""
export_confusion_matrix.py — Procesador Científico y Generador de Reportes del Capítulo IV
FaceSentinel — Tesis de Grado en Ingeniería

Funcionalidades:
1. Matriz de Confusión Global (VP, VN, FP, FN) y métricas de seguridad de acceso (Accuracy, Precision, Recall, F1, FAR, FRR).
2. Evaluación Específica de Detección de Ataques de Presentación (PAD / Anti-Spoofing según ISO/IEC 30107-3):
   - APCER (Attack Presentation Classification Error Rate) desglosado en Foto y Video Replay.
   - BPCER (Bona Fide Presentation Classification Error Rate) para usuarios vivos genuinos.
   - ACER (Average Classification Error Rate).
3. Evaluación Específica de Reconocimiento Facial (Biometría según ISO/IEC 19795-1):
   - FNMR (False Non-Match Rate) y FMR (False Match Rate).
   - Distribución de distancias coseno (Matches autorizados vs Impostores/Desconocidos).
4. Análisis de Robustez Ambiental (NORMAL, LOW_LIGHT, HIGH_LIGHT).
5. Desglose Estadístico de Latencias del Pipeline (Media, Desv. Est., Percentil 95, Mín, Máx).
6. Telemetría de Transacciones Blockchain en Ethereum (Consumo de gas, tiempos de sellado).
7. Exportación automática a Markdown (data/reporte_capitulo4.md) y código LaTeX (data/tablas_tesis.tex).
8. Soporte CLI para respaldar y reiniciar el dataset (--backup) o analizar archivos históricos (--file).
"""

import os
import sys
import csv
import math
import json
import shutil
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# Asegurar codificación UTF-8 en consola de Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_CSV_PATH = os.path.join(DATA_DIR, "metricas_tesis.csv")
BACKUP_JSONL_PATH = os.path.join(DATA_DIR, "metricas_tesis_backup.jsonl")
MD_REPORT_PATH = os.path.join(DATA_DIR, "reporte_capitulo4.md")
TEX_REPORT_PATH = os.path.join(DATA_DIR, "tablas_tesis.tex")


def load_dataset(csv_path: str = DEFAULT_CSV_PATH) -> List[Dict[str, Any]]:
    """Carga los registros del CSV y consolida con backup JSONL si existe."""
    records = []

    # 1. Sincronizar backups pendientes si el módulo está disponible
    try:
        from app.services.metrics_collector import flush_backup_to_csv
        flush_backup_to_csv()
    except Exception:
        pass

    # 2. Leer CSV principal
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)

    # 3. Si aún hay líneas en backup JSONL, incluirlas si leemos el CSV por defecto
    if csv_path == DEFAULT_CSV_PATH and os.path.exists(BACKUP_JSONL_PATH):
        try:
            with open(BACKUP_JSONL_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line.strip()))
        except Exception:
            pass

    return records


def parse_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def parse_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "granted", "yes", "t")
    return bool(val)


def calc_stats(numbers: List[float]) -> Dict[str, float]:
    """Calcula promedio, mínimo, máximo, desviación estándar y percentil 95."""
    if not numbers:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0, "count": 0}
    n = len(numbers)
    mean = sum(numbers) / n
    variance = sum((x - mean) ** 2 for x in numbers) / n if n > 1 else 0.0
    std = math.sqrt(variance)
    sorted_nums = sorted(numbers)
    p95_idx = int(math.ceil(0.95 * n)) - 1
    p95 = sorted_nums[max(0, min(p95_idx, n - 1))]
    return {
        "mean": round(mean, 2),
        "std": round(std, 2),
        "min": round(min(numbers), 2),
        "max": round(max(numbers), 2),
        "p95": round(p95, 2),
        "count": n
    }


def backup_and_reset_csv(csv_path: str = DEFAULT_CSV_PATH):
    """Crea una copia de respaldo con timestamp y limpia el CSV activo."""
    if not os.path.exists(csv_path):
        print(f"⚠️ El archivo '{csv_path}' no existe. Nada que respaldar.")
        return

    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(DATA_DIR, f"metricas_tesis_backup_{ts_str}.csv")
    shutil.copy2(csv_path, backup_file)

    try:
        from app.services.metrics_collector import CSV_HEADERS
    except Exception:
        CSV_HEADERS = [
            "timestamp", "test_type", "environmental_condition", "user_id", "granted",
            "rejection_reason", "t_ear_edge_ms", "t_edge_total_ms", "t_network_rtt_ms",
            "t_lbp_ms", "t_fft_ms", "t_arcface_ms", "t_chroma_ms", "t_sqlite_ms",
            "t_backend_total_ms", "t_total_end2end_ms", "ear_open", "ear_blink",
            "lbp_entropy", "lbp_threshold", "lbp_variance", "liveness_score",
            "cosine_distance", "match_threshold", "bc_tx_hash", "bc_gas_used",
            "bc_block_number", "bc_seal_time_ms"
        ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)

    print(f"\n📦 [RESPALDO EXITOSO] Archivo guardado en:\n   {backup_file}")
    print(f"✨ '{csv_path}' reiniciado con cabeceras limpias.")
    print("   ¡Puedes iniciar tus nuevas corridas de pruebas oficiales para la tesis!\n")


def generate_reports(csv_path: str = DEFAULT_CSV_PATH):
    records = load_dataset(csv_path)
    if not records:
        print(f"⚠️ No se encontraron registros en '{csv_path}'.")
        print("   Ejecuta primero pruebas con edge_gateway_multi.py.")
        return

    total_records = len(records)
    print(f"📂 Procesando {total_records} registros experimentales desde:\n   {csv_path}...")

    # -------------------------------------------------------------
    # 1. CLASIFICACIÓN DE CASOS (MATRIZ DE CONFUSIÓN Y PAD)
    # -------------------------------------------------------------
    # Clases Reales:
    #   - LIVE_USER: Usuario legítimo vivo autorizado (Hector). Debe ser GRANTED.
    #   - IMPOSTOR_LIVE: Persona viva no registrada. Debe ser DENIED.
    #   - SPOOF_PHOTO / SPOOF_PHOTO_PRINT: Ataque con foto. Debe ser DENIED.
    #   - SPOOF_SCREEN_VIDEO / SPOOF_VIDEO: Ataque video replay. Debe ser DENIED.

    vp = 0  # LIVE_USER y GRANTED
    fn = 0  # LIVE_USER y DENIED
    fp = 0  # (SPOOF_* o IMPOSTOR_LIVE) y GRANTED (Falla grave de seguridad)
    vn = 0  # (SPOOF_* o IMPOSTOR_LIVE) y DENIED (Bloqueo exitoso)

    # Métricas PAD (ISO/IEC 30107-3)
    bona_fide_count = 0
    bpcer_errors = 0  # Vivos rechazados por liveness falso
    fnmr_errors = 0   # Vivos rechazados por distancia facial > umbral

    photo_attack_count = 0
    photo_leaked_count = 0  # Fotos que superaron liveness

    video_attack_count = 0
    video_leaked_count = 0  # Videos que superaron liveness

    impostor_count = 0
    impostor_accepted_count = 0  # Impostores vivos que hicieron match erróneo (FMR)

    # Análisis por Condición Ambiental
    env_stats = {
        "NORMAL": {"total": 0, "correct": 0, "error": 0, "e2e": []},
        "LOW_LIGHT": {"total": 0, "correct": 0, "error": 0, "e2e": []},
        "HIGH_LIGHT": {"total": 0, "correct": 0, "error": 0, "e2e": []},
    }

    # Colecciones de telemetría y latencias
    t_ear_list = []
    t_edge_list = []
    t_net_list = []
    t_lbp_list = []
    t_fft_list = []
    t_arcface_list = []
    t_chroma_list = []
    t_sqlite_list = []
    t_backend_list = []
    t_end2end_list = []

    entropy_live = []
    entropy_photo = []
    entropy_screen = []
    cosine_matches = []
    cosine_unknowns = []

    gas_used_list = []
    seal_time_list = []

    for r in records:
        test_type = str(r.get("test_type", "LIVE_USER")).strip().upper()
        env_cond = str(r.get("environmental_condition", "NORMAL")).strip().upper()
        if env_cond not in env_stats:
            env_cond = "NORMAL"

        granted = parse_bool(r.get("granted", False))
        rej_reason = str(r.get("rejection_reason", "")).strip().upper()
        t_e2e = parse_float(r.get("t_total_end2end_ms"))

        env_stats[env_cond]["total"] += 1
        if t_e2e > 0:
            env_stats[env_cond]["e2e"].append(t_e2e)

        is_genuine = (test_type == "LIVE_USER")

        if is_genuine:
            bona_fide_count += 1
            if granted:
                vp += 1
                env_stats[env_cond]["correct"] += 1
            else:
                fn += 1
                env_stats[env_cond]["error"] += 1
                if "SPOOF" in rej_reason:
                    bpcer_errors += 1
                elif "UNKNOWN" in rej_reason or "NO_MATCH" in rej_reason:
                    fnmr_errors += 1
        else:
            # Es un intento no autorizado (Ataque o Impostor)
            if "PHOTO" in test_type:
                photo_attack_count += 1
                if rej_reason != "SPOOFING_DETECTED":
                    photo_leaked_count += 1
            elif "VIDEO" in test_type or "SCREEN" in test_type:
                video_attack_count += 1
                if rej_reason != "SPOOFING_DETECTED":
                    video_leaked_count += 1
            elif "IMPOSTOR" in test_type:
                impostor_count += 1
                if granted:
                    impostor_accepted_count += 1

            if granted:
                fp += 1
                env_stats[env_cond]["error"] += 1
            else:
                vn += 1
                env_stats[env_cond]["correct"] += 1

        # Latencias
        t_ear = parse_float(r.get("t_ear_edge_ms"))
        t_edge = parse_float(r.get("t_edge_total_ms"))
        t_net = parse_float(r.get("t_network_rtt_ms"))
        t_lbp = parse_float(r.get("t_lbp_ms"))
        t_fft = parse_float(r.get("t_fft_ms"))
        t_arc = parse_float(r.get("t_arcface_ms"))
        t_chr = parse_float(r.get("t_chroma_ms"))
        t_sql = parse_float(r.get("t_sqlite_ms"))
        t_back = parse_float(r.get("t_backend_total_ms"))

        if t_ear > 0: t_ear_list.append(t_ear)
        if t_edge > 0: t_edge_list.append(t_edge)
        if t_net > 0: t_net_list.append(t_net)
        if t_lbp > 0: t_lbp_list.append(t_lbp)
        if t_fft > 0: t_fft_list.append(t_fft)
        if t_arc > 0: t_arcface_list.append(t_arc)
        if t_chr > 0: t_chroma_list.append(t_chr)
        if t_sql > 0: t_sqlite_list.append(t_sql)
        if t_back > 0: t_backend_list.append(t_back)
        if t_e2e > 0: t_end2end_list.append(t_e2e)

        # LBP Entropía
        entropy = parse_float(r.get("lbp_entropy"))
        if entropy > 0:
            if test_type == "LIVE_USER":
                entropy_live.append(entropy)
            elif "PHOTO" in test_type:
                entropy_photo.append(entropy)
            elif "SCREEN" in test_type or "VIDEO" in test_type:
                entropy_screen.append(entropy)

        # Distancia Coseno
        dist = parse_float(r.get("cosine_distance"))
        if dist > 0:
            if granted:
                cosine_matches.append(dist)
            else:
                cosine_unknowns.append(dist)

        # Blockchain
        gas = parse_float(r.get("bc_gas_used"))
        seal = parse_float(r.get("bc_seal_time_ms"))
        if gas > 0: gas_used_list.append(gas)
        if seal > 0: seal_time_list.append(seal)

    # -------------------------------------------------------------
    # 2. CÁLCULO DE MÉTRICAS MATEMÁTICAS Y ESTADÍSTICAS
    # -------------------------------------------------------------
    total_samples = vp + vn + fp + fn
    accuracy = ((vp + vn) / total_samples * 100.0) if total_samples > 0 else 0.0
    precision = (vp / (vp + fp) * 100.0) if (vp + fp) > 0 else 0.0
    recall = (vp / (vp + fn) * 100.0) if (vp + fn) > 0 else 0.0
    specificity = (vn / (vn + fp) * 100.0) if (vn + fp) > 0 else 0.0
    global_far = (fp / (fp + vn) * 100.0) if (fp + vn) > 0 else 0.0
    global_frr = (fn / (fn + vp) * 100.0) if (fn + vp) > 0 else 0.0
    f1_score = (2 * (precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0

    # PAD ISO/IEC 30107-3
    bpcer = (bpcer_errors / bona_fide_count * 100.0) if bona_fide_count > 0 else 0.0
    total_attacks = photo_attack_count + video_attack_count
    total_attacks_leaked = photo_leaked_count + video_leaked_count
    apcer_photo = (photo_leaked_count / photo_attack_count * 100.0) if photo_attack_count > 0 else 0.0
    apcer_video = (video_leaked_count / video_attack_count * 100.0) if video_attack_count > 0 else 0.0
    apcer_global = (total_attacks_leaked / total_attacks * 100.0) if total_attacks > 0 else 0.0
    acer = (apcer_global + bpcer) / 2.0

    # Reconocimiento Facial ISO/IEC 19795-1
    fnmr = (fnmr_errors / bona_fide_count * 100.0) if bona_fide_count > 0 else 0.0
    fmr = (impostor_accepted_count / impostor_count * 100.0) if impostor_count > 0 else 0.0

    # Estadísticas de latencias (con Percentil 95)
    stats_ear = calc_stats(t_ear_list)
    stats_edge = calc_stats(t_edge_list)
    stats_net = calc_stats(t_net_list)
    stats_lbp = calc_stats(t_lbp_list)
    stats_fft = calc_stats(t_fft_list)
    stats_arc = calc_stats(t_arcface_list)
    stats_chr = calc_stats(t_chroma_list)
    stats_sql = calc_stats(t_sqlite_list)
    stats_back = calc_stats(t_backend_list)
    stats_e2e = calc_stats(t_end2end_list)

    stats_ent_live = calc_stats(entropy_live)
    stats_ent_photo = calc_stats(entropy_photo)
    stats_ent_screen = calc_stats(entropy_screen)
    stats_cos_match = calc_stats(cosine_matches)
    stats_cos_unk = calc_stats(cosine_unknowns)

    stats_gas = calc_stats(gas_used_list)
    stats_seal = calc_stats(seal_time_list)

    # -------------------------------------------------------------
    # 3. GENERAR REPORTE CIENTÍFICO EN MARKDOWN (Capítulo IV)
    # -------------------------------------------------------------
    md_content = f"""# FaceSentinel — Resultados Experimentales y Evaluación Científica del Capítulo IV

**Fecha de Evaluación:** {records[-1].get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}  
**Dataset Analizado:** `{os.path.basename(csv_path)}`  
**Total de Ensayos Registrados:** {total_samples} intentos de autenticación

---

## 1. Matriz de Confusión Global de Control de Acceso

La siguiente matriz clasifica las decisiones del sistema entre accesos legítimos autorizados frente a intentos indebidos (ataques de presentación con foto/video e impostores no registrados):

| Condición Real \\ Decisión Sistema | Acceso Concedido (GRANTED) | Acceso Denegado (DENIED) | Total Real |
|:---|:---:|:---:|:---:|
| **Sujeto Autorizado (Bona Fide Live)** | **Verdaderos Positivos (VP): {vp}** | **Falsos Negativos (FN): {fn}** | {bona_fide_count} |
| **Intento Indebido (Ataques + Impostores)** | **Falsos Positivos (FP): {fp}** | **Verdaderos Negativos (VN): {vn}** | {vn + fp} |
| **Total Clasificado** | {vp + fp} | {fn + vn} | **{total_samples}** |

### Indicadores Globales de Seguridad
- **Exactitud General (Accuracy):** `{accuracy:.2f}%`
- **Precisión (Precision):** `{precision:.2f}%`
- **Sensibilidad / Tasa de Acierto (Recall / TPR):** `{recall:.2f}%`
- **Especificidad (TNR):** `{specificity:.2f}%`
- **F1-Score:** `{f1_score:.2f}%`
- **Tasa Global de Falsa Aceptación (FAR):** `{global_far:.2f}%` *(Vulnerabilidad de acceso)*
- **Tasa Global de Falso Rechazo (FRR):** `{global_frr:.2f}%` *(Fricción de usuario)*

---

## 2. Evaluación Específica de Detección de Ataques de Presentación (PAD / ISO/IEC 30107-3)

Evaluación del subsistema Anti-Spoofing en el borde y servidor (MediaPipe Blink EAR + Textura LBP):

| Indicador PAD (ISO/IEC 30107-3) | Valor Obtenido | Muestras Evaluadas | Interpretación Técnica |
|:---|:---:|:---:|:---|
| **APCER - Fotos Impresas/Pantalla** | `{apcer_photo:.2f}%` | {photo_attack_count} intentos | Fotos que burlaron la detección de liveness |
| **APCER - Video Replay con Parpadeo** | `{apcer_video:.2f}%` | {video_attack_count} intentos | Videos en smartphone que lograron traspasar |
| **APCER Global (Ataques no detectados)** | **`{apcer_global:.2f}%`** | {total_attacks} ataques | Tasa total de filtración de ataques de presentación |
| **BPCER (Falso rechazo a vivos genuinos)**| **`{bpcer:.2f}%`** | {bona_fide_count} intentos | Usuarios vivos confundidos erróneamente con spoofing |
| **ACER (Error Medio de Clasificación)**   | **`{acer:.2f}%`** | {bona_fide_count + total_attacks} muestras | Media balanceada entre APCER y BPCER |

---

## 3. Evaluación del Reconocimiento Facial Biométrico (ISO/IEC 19795-1)

Rendimiento del modelo DeepFace ArcFace (512 dimensiones) con indexación vectorial ChromaDB (HNSW):

| Métrica Biometría Facial | Valor Obtenido | Muestras | Interpretación |
|:---|:---:|:---:|:---|
| **FNMR (False Non-Match Rate)** | `{fnmr:.2f}%` | {bona_fide_count} | Usuarios autorizados vivos rechazados por distancia $d > 0.75$ |
| **FMR (False Match Rate)** | `{fmr:.2f}%` | {impostor_count} | Impostores vivos aceptados con distancia $d \\le 0.75$ |
| **Distancia Coseno (Genuine Match)** | `{stats_cos_match['mean']} ± {stats_cos_match['std']}` | {stats_cos_match['count']} | Distancia promedio para accesos autorizados |
| **Distancia Coseno (Impostores/Desconocidos)** | `{stats_cos_unk['mean']} ± {stats_cos_unk['std']}` | {stats_cos_unk['count']} | Distancia promedio para rostros no emparejados |

---

## 4. Análisis de Robustez ante Condiciones Ambientales (Iluminación)

| Entorno Evaluado | Muestras Totales | Decisiones Correctas | Fallos | Exactitud (%) | Latencia Media E2E (ms) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Iluminación Normal (Oficina/Lab)** | {env_stats['NORMAL']['total']} | {env_stats['NORMAL']['correct']} | {env_stats['NORMAL']['error']} | {((env_stats['NORMAL']['correct']/env_stats['NORMAL']['total'])*100 if env_stats['NORMAL']['total']>0 else 0):.2f}% | {calc_stats(env_stats['NORMAL']['e2e'])['mean']} ms |
| **Baja Iluminación (< 50 lux)** | {env_stats['LOW_LIGHT']['total']} | {env_stats['LOW_LIGHT']['correct']} | {env_stats['LOW_LIGHT']['error']} | {((env_stats['LOW_LIGHT']['correct']/env_stats['LOW_LIGHT']['total'])*100 if env_stats['LOW_LIGHT']['total']>0 else 0):.2f}% | {calc_stats(env_stats['LOW_LIGHT']['e2e'])['mean']} ms |
| **Alta Luz / Contraluz (> 1000 lux)** | {env_stats['HIGH_LIGHT']['total']} | {env_stats['HIGH_LIGHT']['correct']} | {env_stats['HIGH_LIGHT']['error']} | {((env_stats['HIGH_LIGHT']['correct']/env_stats['HIGH_LIGHT']['total'])*100 if env_stats['HIGH_LIGHT']['total']>0 else 0):.2f}% | {calc_stats(env_stats['HIGH_LIGHT']['e2e'])['mean']} ms |

---

## 5. Benchmarking de Latencias del Pipeline (Milisegundos)

| Componente de Arquitectura | Media (ms) | Desv. Est. (ms) | Percentil 95 (ms) | Mín (ms) | Máx (ms) | Muestras |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Borde: MediaPipe Face Mesh (EAR)** | `{stats_ear['mean']}` | `±{stats_ear['std']}` | `{stats_ear['p95']}` | `{stats_ear['min']}` | `{stats_ear['max']}` | {stats_ear['count']} |
| **Borde: Procesamiento Total Borde** | `{stats_edge['mean']}` | `±{stats_edge['std']}` | `{stats_edge['p95']}` | `{stats_edge['min']}` | `{stats_edge['max']}` | {stats_edge['count']} |
| **Red Troncal: Tránsito RTT** | `{stats_net['mean']}` | `±{stats_net['std']}` | `{stats_net['p95']}` | `{stats_net['min']}` | `{stats_net['max']}` | {stats_net['count']} |
| **Servidor: LBP Entropía Textura** | `{stats_lbp['mean']}` | `±{stats_lbp['std']}` | `{stats_lbp['p95']}` | `{stats_lbp['min']}` | `{stats_lbp['max']}` | {stats_lbp['count']} |
| **Servidor: FFT Espectro Frecuencia** | `{stats_fft['mean']}` | `±{stats_fft['std']}` | `{stats_fft['p95']}` | `{stats_fft['min']}` | `{stats_fft['max']}` | {stats_fft['count']} |
| **Servidor: ArcFace Extracción 512d** | `{stats_arc['mean']}` | `±{stats_arc['std']}` | `{stats_arc['p95']}` | `{stats_arc['min']}` | `{stats_arc['max']}` | {stats_arc['count']} |
| **Servidor: ChromaDB Búsqueda Vectorial** | `{stats_chr['mean']}` | `±{stats_chr['std']}` | `{stats_chr['p95']}` | `{stats_chr['min']}` | `{stats_chr['max']}` | {stats_chr['count']} |
| **Servidor: SQLite Validación ACL/RBAC** | `{stats_sql['mean']}` | `±{stats_sql['std']}` | `{stats_sql['p95']}` | `{stats_sql['min']}` | `{stats_sql['max']}` | {stats_sql['count']} |
| **Servidor: Latencia Total Backend** | `{stats_back['mean']}` | `±{stats_back['std']}` | `{stats_back['p95']}` | `{stats_back['min']}` | `{stats_back['max']}` | {stats_back['count']} |
| **Latencia Total End-to-End** | **`{stats_e2e['mean']}`** | **`±{stats_e2e['std']}`** | **`{stats_e2e['p95']}`** | **`{stats_e2e['min']}`** | **`{stats_e2e['max']}`** | {stats_e2e['count']} |

---

## 6. Eficiencia de Auditoría Blockchain (Smart Contract en Ethereum)

- **Consumo de Gas Promedio (`logAuthentication`):** `{stats_gas['mean']:,.0f} gas` (Mín: `{stats_gas['min']:,.0f}` | Máx: `{stats_gas['max']:,.0f}`)
- **Tiempo de Sellado de Bloque (Sealing Time):** `{stats_seal['mean']} ms` (`±{stats_seal['std']} ms` | P95: `{stats_seal['p95']} ms`)
- **Total de Transacciones Notariadas en Cadena:** `{stats_gas['count']}` eventos
"""

    with open(MD_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)

    # -------------------------------------------------------------
    # 4. GENERAR CÓDIGO LATEX PROFESIONAL (tablas_tesis.tex)
    # -------------------------------------------------------------
    tex_content = f"""% =========================================================================
% Tablas y Resultados Experimentales para el Capítulo IV — FaceSentinel
% Generado automáticamente desde metricas_tesis.csv
% Compatible con Overleaf y compiladores PDFLaTeX / XeLaTeX
% =========================================================================

% --- TABLA 1: MATRIZ DE CONFUSIÓN GLOBAL ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Matriz de Confusión Global de Control de Acceso}}
\\label{{tab:matriz_confusion}}
\\begin{{tabular}}{{l|c|c|c}}
\\hline
\\textbf{{Condición Real \\textbackslash{{}} Decisión}} & \\textbf{{Acceso Concedido}} & \\textbf{{Acceso Denegado}} & \\textbf{{Total}} \\\\ \\hline
\\textbf{{Sujeto Autorizado (Bona Fide)}} & \\textbf{{{vp}}} (VP) & \\textbf{{{fn}}} (FN) & {bona_fide_count} \\\\ \\hline
\\textbf{{Intento Indebido (Ataques/Impostores)}} & \\textbf{{{fp}}} (FP) & \\textbf{{{vn}}} (VN) & {vn + fp} \\\\ \\hline
\\textbf{{Total Evaluado}} & {vp + fp} & {fn + vn} & \\textbf{{{total_samples}}} \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 2: MÉTRICAS DE RENDIMIENTO BIOMÉTRICO Y PAD ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Indicadores de Rendimiento Biométrico y Anti-Spoofing (ISO/IEC 30107-3 / ISO/IEC 19795-1)}}
\\label{{tab:metricas_biometricas}}
\\begin{{tabular}}{{l|c|l}}
\\hline
\\textbf{{Métrica Evaluada}} & \\textbf{{Valor Obtenido}} & \\textbf{{Definición / Norma}} \\\\ \\hline
Exactitud Global (Accuracy) & {accuracy:.2f}\\% & Tasa de clasificación global correcta \\\\
Precisión (Precision) & {precision:.2f}\\% & Fiabilidad de accesos autorizados concedidos \\\\
Sensibilidad / Recall (TPR) & {recall:.2f}\\% & Capacidad de autenticación de usuarios legítimos \\\\
Especificidad (TNR) & {specificity:.2f}\\% & Tasa de bloqueo ante ataques e impostores \\\\
F1-Score & {f1_score:.2f}\\% & Media armónica de precisión y sensibilidad \\\\
APCER Global (Presentation Attacks) & {apcer_global:.2f}\\% & Tasa de ataques que eludieron liveness (ISO 30107-3) \\\\
BPCER (Bona Fide Rejection) & {bpcer:.2f}\\% & Usuarios vivos denegados por falso spoofing \\\\
ACER (Average Error Rate) & {acer:.2f}\\% & Media balanceada (APCER + BPCER) / 2 \\\\
Tasa Global de Falsa Aceptación (FAR) & {global_far:.2f}\\% & Intentos no autorizados aceptados \\\\
Tasa Global de Falso Rechazo (FRR) & {global_frr:.2f}\\% & Usuarios legítimos rechazados indebidamente \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 3: ANÁLISIS DE ROBUSTEZ AMBIENTAL ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Rendimiento del Sistema según Condiciones de Iluminación}}
\\label{{tab:robustez_ambiental}}
\\begin{{tabular}}{{l|c|c|c|c}}
\\hline
\\textbf{{Condición de Iluminación}} & \\textbf{{Muestras}} & \\textbf{{Aciertos}} & \\textbf{{Exactitud (\\%)}} & \\textbf{{Latencia E2E (ms)}} \\\\ \\hline
Normal (Oficina/Laboratorio) & {env_stats['NORMAL']['total']} & {env_stats['NORMAL']['correct']} & {((env_stats['NORMAL']['correct']/env_stats['NORMAL']['total'])*100 if env_stats['NORMAL']['total']>0 else 0):.2f}\\% & {calc_stats(env_stats['NORMAL']['e2e'])['mean']} \\\\
Baja Iluminación ($< 50$ lux) & {env_stats['LOW_LIGHT']['total']} & {env_stats['LOW_LIGHT']['correct']} & {((env_stats['LOW_LIGHT']['correct']/env_stats['LOW_LIGHT']['total'])*100 if env_stats['LOW_LIGHT']['total']>0 else 0):.2f}\\% & {calc_stats(env_stats['LOW_LIGHT']['e2e'])['mean']} \\\\
Alta Luz / Contraluz ($> 1000$ lux) & {env_stats['HIGH_LIGHT']['total']} & {env_stats['HIGH_LIGHT']['correct']} & {((env_stats['HIGH_LIGHT']['correct']/env_stats['HIGH_LIGHT']['total'])*100 if env_stats['HIGH_LIGHT']['total']>0 else 0):.2f}\\% & {calc_stats(env_stats['HIGH_LIGHT']['e2e'])['mean']} \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 4: DESGLOSE DE LATENCIAS EXPERIMENTALES ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Desglose Estadístico de Latencias de Procesamiento (Milisegundos)}}
\\label{{tab:latencias_pipeline}}
\\begin{{tabular}}{{l|c|c|c|c|c}}
\\hline
\\textbf{{Componente del Pipeline}} & \\textbf{{Media}} & \\textbf{{Desv. Est.}} & \\textbf{{P95}} & \\textbf{{Mín}} & \\textbf{{Máx}} \\\\ \\hline
Borde: MediaPipe Face Mesh EAR & {stats_ear['mean']} & $\\pm {stats_ear['std']}$ & {stats_ear['p95']} & {stats_ear['min']} & {stats_ear['max']} \\\\
Borde: Procesamiento Total Borde & {stats_edge['mean']} & $\\pm {stats_edge['std']}$ & {stats_edge['p95']} & {stats_edge['min']} & {stats_edge['max']} \\\\
Red Troncal: Tránsito RTT & {stats_net['mean']} & $\\pm {stats_net['std']}$ & {stats_net['p95']} & {stats_net['min']} & {stats_net['max']} \\\\
Backend: LBP Entropía de Textura & {stats_lbp['mean']} & $\\pm {stats_lbp['std']}$ & {stats_lbp['p95']} & {stats_lbp['min']} & {stats_lbp['max']} \\\\
Backend: FFT Espectro Frecuencia & {stats_fft['mean']} & $\\pm {stats_fft['std']}$ & {stats_fft['p95']} & {stats_fft['min']} & {stats_fft['max']} \\\\
Backend: ArcFace Extracción 512d & {stats_arc['mean']} & $\\pm {stats_arc['std']}$ & {stats_arc['p95']} & {stats_arc['min']} & {stats_arc['max']} \\\\
Backend: ChromaDB Match Vectorial & {stats_chr['mean']} & $\\pm {stats_chr['std']}$ & {stats_chr['p95']} & {stats_chr['min']} & {stats_chr['max']} \\\\
Backend: SQLite Validación ACL & {stats_sql['mean']} & $\\pm {stats_sql['std']}$ & {stats_sql['p95']} & {stats_sql['min']} & {stats_sql['max']} \\\\ \\hline
\\textbf{{Backend: Tiempo Total Servidor}} & \\textbf{{{stats_back['mean']}}} & $\\pm {stats_back['std']}$ & \\textbf{{{stats_back['p95']}}} & {stats_back['min']} & {stats_back['max']} \\\\ \\hline
\\textbf{{Latencia Total End-to-End}} & \\textbf{{{stats_e2e['mean']}}} & $\\pm {stats_e2e['std']}$ & \\textbf{{{stats_e2e['p95']}}} & {stats_e2e['min']} & {stats_e2e['max']} \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 5: RENDIMIENTO DE AUDITORÍA BLOCKCHAIN ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Métricas de Auditoría Inmutable en Red Blockchain Ethereum}}
\\label{{tab:blockchain_metrics}}
\\begin{{tabular}}{{l|c|l}}
\\hline
\\textbf{{Parámetro Evaluado}} & \\textbf{{Valor Promedio}} & \\textbf{{Observaciones Técnicas}} \\\\ \\hline
Consumo de Gas (\\texttt{{logAuthentication}}) & {stats_gas['mean']:,.0f} gas & Costo de ejecución en Ethereum Virtual Machine \\\\
Tiempo de Sellado de Bloque & {stats_seal['mean']} ms & Tiempo de inclusión asíncrona en bloque \\\\
Eventos Inmutables Notariados & {stats_gas['count']} & Transacciones confirmadas en ledger distribuido \\\\ \\hline
\\end{{tabular}}
\\end{{table}}
"""

    with open(TEX_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(tex_content)

    print(f"\n🎉 Reporte científico generado con éxito:")
    print(f"   📄 Markdown: {MD_REPORT_PATH}")
    print(f"   📝 LaTeX:    {TEX_REPORT_PATH}")
    print(f"\nResumen Ejecutivo:")
    print(f"   • Ensayos Procesados: {total_samples} (Vivos: {bona_fide_count}, Ataques/Impostores: {vn + fp})")
    print(f"   • Exactitud Global: {accuracy:.2f}% | F1-Score: {f1_score:.2f}%")
    print(f"   • PAD (ISO 30107-3): APCER: {apcer_global:.2f}% | BPCER: {bpcer:.2f}% | ACER: {acer:.2f}%")
    print(f"   • Latencia End-to-End: Media {stats_e2e['mean']} ms | P95 {stats_e2e['p95']} ms\n")


def main():
    parser = argparse.ArgumentParser(description="FaceSentinel — Procesador Científico de Métricas de Tesis")
    parser.add_argument("--file", type=str, default=DEFAULT_CSV_PATH, help="Ruta al archivo CSV de métricas")
    parser.add_argument("--backup", action="store_true", help="Crea copia de respaldo del CSV actual y lo reinicia limpio")
    args = parser.parse_args()

    if args.backup:
        backup_and_reset_csv(args.file)
    else:
        generate_reports(args.file)


if __name__ == "__main__":
    main()
