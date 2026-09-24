#!/usr/bin/env python3
"""
export_confusion_matrix.py — Procesador y Generador de Reportes Científicos para el Capítulo IV
Lee data/metricas_tesis.csv y genera automáticamente:
1. Matriz de Confusión (VP, VN, FP, FN) y métricas biométricas (Accuracy, Precision, Recall, FAR, FRR, F1).
2. Análisis de Causa Raíz de Falsos Negativos cruzados con la Condición Ambiental (NORMAL, HIGH_LIGHT, LOW_LIGHT).
3. Estadísticas detalladas de Latencia (Borde, Red RTT, LBP, ArcFace, ChromaDB, SQLite, Blockchain).
4. Exportación a Markdown (data/reporte_capitulo4.md) y código LaTeX (data/tablas_tesis.tex).
"""

import os
import sys
import csv
import math
import json
from typing import List, Dict, Any

# Asegurar codificación UTF-8 en consola de Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_PATH = os.path.join(DATA_DIR, "metricas_tesis.csv")
BACKUP_JSONL_PATH = os.path.join(DATA_DIR, "metricas_tesis_backup.jsonl")
MD_REPORT_PATH = os.path.join(DATA_DIR, "reporte_capitulo4.md")
TEX_REPORT_PATH = os.path.join(DATA_DIR, "tablas_tesis.tex")


def load_dataset() -> List[Dict[str, Any]]:
    """Carga los registros del CSV y consolida con backup JSONL si existe."""
    records = []
    
    # 1. Intentar sincronizar backups pendientes si el módulo está disponible
    try:
        from app.services.metrics_collector import flush_backup_to_csv
        flush_backup_to_csv()
    except Exception:
        pass

    # 2. Leer CSV principal
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)

    # 3. Si aún hay líneas en backup JSONL, incluirlas también
    if os.path.exists(BACKUP_JSONL_PATH):
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
    """Calcula promedio, mínimo, máximo y desviación estándar."""
    if not numbers:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    n = len(numbers)
    mean = sum(numbers) / n
    variance = sum((x - mean) ** 2 for x in numbers) / n if n > 1 else 0.0
    std = math.sqrt(variance)
    return {
        "mean": round(mean, 2),
        "std": round(std, 2),
        "min": round(min(numbers), 2),
        "max": round(max(numbers), 2),
        "count": n
    }


def generate_reports():
    records = load_dataset()
    if not records:
        print("⚠️ No se encontraron registros en data/metricas_tesis.csv. Ejecuta primero pruebas con edge_gateway.py.")
        return

    total_records = len(records)
    print(f"📂 Procesando {total_records} registros experimentales...")

    # 1. Matriz de Confusión
    # Clases reales: LIVE (Positivo) vs SPOOF (Negativo)
    # Predicción: GRANTED (Positivo) vs DENIED (Negativo)
    vp = 0  # LIVE_USER y GRANTED
    fn = 0  # LIVE_USER y DENIED
    fp = 0  # SPOOF_* y GRANTED (Ataque exitoso no deseado)
    vn = 0  # SPOOF_* y DENIED (Ataque bloqueado correctamente)

    fn_by_env = {"NORMAL": 0, "HIGH_LIGHT": 0, "LOW_LIGHT": 0, "OTRO": 0}
    live_count = 0
    spoof_count = 0

    # Colecciones de métricas
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
        granted = parse_bool(r.get("granted", False))

        is_live_test = (test_type == "LIVE_USER")

        if is_live_test:
            live_count += 1
            if granted:
                vp += 1
            else:
                fn += 1
                fn_by_env[env_cond if env_cond in fn_by_env else "OTRO"] += 1
        else:
            spoof_count += 1
            if granted:
                fp += 1
            else:
                vn += 1

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
        t_e2e = parse_float(r.get("t_total_end2end_ms"))

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

        # Liveness & Biometría
        entropy = parse_float(r.get("lbp_entropy"))
        if entropy > 0:
            if test_type == "LIVE_USER":
                entropy_live.append(entropy)
            elif "PHOTO" in test_type:
                entropy_photo.append(entropy)
            elif "SCREEN" in test_type or "VIDEO" in test_type:
                entropy_screen.append(entropy)

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

    # Métricas de rendimiento
    total_samples = vp + vn + fp + fn
    accuracy = ((vp + vn) / total_samples * 100.0) if total_samples > 0 else 0.0
    precision = (vp / (vp + fp) * 100.0) if (vp + fp) > 0 else 0.0
    recall = (vp / (vp + fn) * 100.0) if (vp + fn) > 0 else 0.0  # Sensitivity / TPR
    specificity = (vn / (vn + fp) * 100.0) if (vn + fp) > 0 else 0.0  # TNR
    far = (fp / (fp + vn) * 100.0) if (fp + vn) > 0 else 0.0  # False Acceptance Rate
    frr = (fn / (fn + vp) * 100.0) if (fn + vp) > 0 else 0.0  # False Rejection Rate
    f1_score = (2 * (precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Estadísticas de latencias
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
    # 1. GENERAR REPORTE MARKDOWN (reporte_capitulo4.md)
    # -------------------------------------------------------------
    md_content = f"""# FaceSentinel — Resultados Experimentales del Capítulo IV

**Fecha de Generación:** {records[-1].get('timestamp', 'N/A')}  
**Total de Muestras Evaluadas:** {total_samples} intentos ({live_count} accesos legítimos vivos, {spoof_count} intentos de spoofing)

---

## 1. Matriz de Confusión y Métricas de Rendimiento Biométrico

| Condición Real \\ Decisión Sistema | Acceso Concedido (GRANTED) | Acceso Denegado (DENIED) | Total Real |
|:---|:---:|:---:|:---:|
| **Sujeto Legítimo (LIVE)** | **Verdaderos Positivos (VP): {vp}** | **Falsos Negativos (FN): {fn}** | {live_count} |
| **Ataque de Presentación (SPOOF)** | **Falsos Positivos (FP): {fp}** | **Verdaderos Negativos (VN): {vn}** | {spoof_count} |
| **Total Clasificado** | {vp + fp} | {fn + vn} | **{total_samples}** |

### Indicadores de Eficacia Biometría y Anti-Spoofing

- **Exactitud Global (Accuracy):** `{accuracy:.2f}%`
- **Precisión (Precision):** `{precision:.2f}%`
- **Sensibilidad / Tasa de Acierto (Recall / TPR):** `{recall:.2f}%`
- **Especificidad (TNR):** `{specificity:.2f}%`
- **F1-Score:** `{f1_score:.2f}%`
- **Tasa de Falsa Aceptación (FAR / FPR):** `{far:.2f}%` *(Debe tender a 0.0%)*
- **Tasa de Falso Rechazo (FRR / FNR):** `{frr:.2f}%`

---

## 2. Análisis de Causa Raíz de Falsos Negativos (Condiciones Ambientales)

Distribución de los **{fn} Falsos Negativos** según iluminación:
- **Iluminación Normal:** {fn_by_env['NORMAL']} casos ({((fn_by_env['NORMAL']/fn)*100 if fn>0 else 0):.1f}%)
- **Contraluz / Exceso de Luz (HIGH_LIGHT):** {fn_by_env['HIGH_LIGHT']} casos ({((fn_by_env['HIGH_LIGHT']/fn)*100 if fn>0 else 0):.1f}%)
- **Baja Iluminación (LOW_LIGHT):** {fn_by_env['LOW_LIGHT']} casos ({((fn_by_env['LOW_LIGHT']/fn)*100 if fn>0 else 0):.1f}%)

> **Hallazgo Académico:** El {(((fn_by_env['HIGH_LIGHT'] + fn_by_env['LOW_LIGHT'])/fn)*100 if fn>0 else 0):.1f}% de las denegaciones erróneas fueron inducidas por condiciones de iluminación no controladas.

---

## 3. Desglose de Latencias de Procesamiento (Milisegundos)

| Componente del Pipeline | Media (ms) | Desv. Est. (ms) | Mínimo (ms) | Máximo (ms) | Muestras |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Edge: MediaPipe Face Mesh (EAR)** | `{stats_ear['mean']}` | `±{stats_ear['std']}` | `{stats_ear['min']}` | `{stats_ear['max']}` | {stats_ear['count']} |
| **Edge: Procesamiento Total Borde** | `{stats_edge['mean']}` | `±{stats_edge['std']}` | `{stats_edge['min']}` | `{stats_edge['max']}` | {stats_edge['count']} |
| **Red Troncal (Network RTT Transit)** | `{stats_net['mean']}` | `±{stats_net['std']}` | `{stats_net['min']}` | `{stats_net['max']}` | {stats_net['count']} |
| **Backend: LBP Entropía de Textura** | `{stats_lbp['mean']}` | `±{stats_lbp['std']}` | `{stats_lbp['min']}` | `{stats_lbp['max']}` | {stats_lbp['count']} |
| **Backend: FFT Espectro Frecuencia** | `{stats_fft['mean']}` | `±{stats_fft['std']}` | `{stats_fft['min']}` | `{stats_fft['max']}` | {stats_fft['count']} |
| **Backend: ArcFace Extracción 512d** | `{stats_arc['mean']}` | `±{stats_arc['std']}` | `{stats_arc['min']}` | `{stats_arc['max']}` | {stats_arc['count']} |
| **Backend: ChromaDB Búsqueda Vectorial** | `{stats_chr['mean']}` | `±{stats_chr['std']}` | `{stats_chr['min']}` | `{stats_chr['max']}` | {stats_chr['count']} |
| **Backend: SQLite Verificación ACL/Token** | `{stats_sql['mean']}` | `±{stats_sql['std']}` | `{stats_sql['min']}` | `{stats_sql['max']}` | {stats_sql['count']} |
| **Backend: Tiempo Total Servidor** | `{stats_back['mean']}` | `±{stats_back['std']}` | `{stats_back['min']}` | `{stats_back['max']}` | {stats_back['count']} |
| **Latencia Total End-to-End (Borde + Red + Servidor)** | **`{stats_e2e['mean']}`** | **`±{stats_e2e['std']}`** | **`{stats_e2e['min']}`** | **`{stats_e2e['max']}`** | {stats_e2e['count']} |

---

## 4. Métricas de Discriminación Anti-Spoofing y Biometría

| Métrica Científica | Sujeto Vivo (Legítimo) | Foto Impresa (Spoof) | Pantalla Digital (Spoof) |
|:---|:---:|:---:|:---:|
| **Entropía de Shannon (LBP)** | `{stats_ent_live['mean']} ± {stats_ent_live['std']}` | `{stats_ent_photo['mean']} ± {stats_ent_photo['std']}` | `{stats_ent_screen['mean']} ± {stats_ent_screen['std']}` |
| **Distancia Coseno (ArcFace)** | `{stats_cos_match['mean']} ± {stats_cos_match['std']}` *(Match)* | N/A | `{stats_cos_unk['mean']} ± {stats_cos_unk['std']}` *(No match)* |

---

## 5. Eficiencia y Rendimiento Blockchain (Smart Contract)

- **Consumo de Gas Promedio (`logAuthentication`):** `{stats_gas['mean']:,.0f} gas` (Mín: `{stats_gas['min']:,.0f}` | Máx: `{stats_gas['max']:,.0f}`)
- **Tiempo de Sellado / Inclusión en Bloque (Sealing Time):** `{stats_seal['mean']} ms` (`±{stats_seal['std']} ms`)
- **Total Transacciones Notariadas en Cadena:** `{stats_gas['count']}`
"""

    with open(MD_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)

    # -------------------------------------------------------------
    # 2. GENERAR CÓDIGO LATEX (tablas_tesis.tex)
    # -------------------------------------------------------------
    tex_content = f"""% =========================================================================
% Tablas y Resultados Experimentales para el Capítulo IV — FaceSentinel
% Generado automáticamente desde metricas_tesis.csv
% =========================================================================

% --- TABLA 1: MATRIZ DE CONFUSIÓN ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Matriz de Confusión del Sistema FaceSentinel}}
\\label{{tab:confusion_matrix}}
\\begin{{tabular}}{{l|c|c|c}}
\\hline
\\textbf{{Condición Real \\textbackslash{{}} Decisión}} & \\textbf{{Acceso Concedido}} & \\textbf{{Acceso Denegado}} & \\textbf{{Total}} \\\\ \\hline
\\textbf{{Sujeto Vivo (Legítimo)}} & \\textbf{{{vp}}} (VP) & \\textbf{{{fn}}} (FN) & {live_count} \\\\ \\hline
\\textbf{{Ataque de Presentación (Spoof)}} & \\textbf{{{fp}}} (FP) & \\textbf{{{vn}}} (VN) & {spoof_count} \\\\ \\hline
\\textbf{{Total General}} & {vp + fp} & {fn + vn} & \\textbf{{{total_samples}}} \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 2: MÉTRICAS DE RENDIMIENTO BIOMÉTRICO ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Métricas de Rendimiento y Tasas de Error Biométrico}}
\\label{{tab:metricas_biometricas}}
\\begin{{tabular}}{{l|c|l}}
\\hline
\\textbf{{Métrica / Indicador}} & \\textbf{{Valor Obtenido}} & \\textbf{{Interpretación Académica}} \\\\ \\hline
Exactitud (Accuracy) & {accuracy:.2f}\\% & Capacidad global de clasificación correcta \\\\
Precisión (Precision) & {precision:.2f}\\% & Fiabilidad ante accesos concedidos \\\\
Sensibilidad / Recall (TPR) & {recall:.2f}\\% & Tasa de verificación de usuarios legítimos \\\\
Especificidad (TNR) & {specificity:.2f}\\% & Tasa de detección y bloqueo de ataques \\\\
F1-Score & {f1_score:.2f}\\% & Media armónica de precisión y recall \\\\
Tasa de Falsa Aceptación (FAR) & {far:.2f}\\% & Intentos de spoofing aceptados indebidamente \\\\
Tasa de Falso Rechazo (FRR) & {frr:.2f}\\% & Usuarios legítimos denegados erróneamente \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 3: DESGLOSE DE LATENCIAS EXPERIMENTALES ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Desglose de Latencias de Procesamiento en Milisegundos}}
\\label{{tab:latencias_pipeline}}
\\begin{{tabular}}{{l|c|c|c|c}}
\\hline
\\textbf{{Etapa del Pipeline}} & \\textbf{{Media (ms)}} & \\textbf{{Desv. Est. (ms)}} & \\textbf{{Mín (ms)}} & \\textbf{{Máx (ms)}} \\\\ \\hline
Edge: MediaPipe Face Mesh EAR & {stats_ear['mean']} & $\\pm {stats_ear['std']}$ & {stats_ear['min']} & {stats_ear['max']} \\\\
Edge: Procesamiento Total Borde & {stats_edge['mean']} & $\\pm {stats_edge['std']}$ & {stats_edge['min']} & {stats_edge['max']} \\\\
Red Troncal: Tránsito RTT & {stats_net['mean']} & $\\pm {stats_net['std']}$ & {stats_net['min']} & {stats_net['max']} \\\\
Backend: LBP Entropía de Textura & {stats_lbp['mean']} & $\\pm {stats_lbp['std']}$ & {stats_lbp['min']} & {stats_lbp['max']} \\\\
Backend: FFT Espectro Frecuencia & {stats_fft['mean']} & $\\pm {stats_fft['std']}$ & {stats_fft['min']} & {stats_fft['max']} \\\\
Backend: ArcFace Extracción 512d & {stats_arc['mean']} & $\\pm {stats_arc['std']}$ & {stats_arc['min']} & {stats_arc['max']} \\\\
Backend: ChromaDB Match Vectorial & {stats_chr['mean']} & $\\pm {stats_chr['std']}$ & {stats_chr['min']} & {stats_chr['max']} \\\\
Backend: SQLite Consulta ACL & {stats_sql['mean']} & $\\pm {stats_sql['std']}$ & {stats_sql['min']} & {stats_sql['max']} \\\\ \\hline
\\textbf{{Backend: Tiempo Total Servidor}} & \\textbf{{{stats_back['mean']}}} & $\\pm {stats_back['std']}$ & {stats_back['min']} & {stats_back['max']} \\\\ \\hline
\\textbf{{Latencia Total End-to-End}} & \\textbf{{{stats_e2e['mean']}}} & $\\pm {stats_e2e['std']}$ & {stats_e2e['min']} & {stats_e2e['max']} \\\\ \\hline
\\end{{tabular}}
\\end{{table}}

% --- TABLA 4: MÉTRICAS DE EFICIENCIA BLOCKCHAIN ---
\\begin{{table}}[htbp]
\\centering
\\caption{{Consumo de Gas y Tiempos de Sellado en Red Blockchain}}
\\label{{tab:blockchain_metrics}}
\\begin{{tabular}}{{l|c|c}}
\\hline
\\textbf{{Parámetro Evaluado}} & \\textbf{{Valor Promedio}} & \\textbf{{Observaciones}} \\\\ \\hline
Consumo de Gas (\\texttt{{logAuthentication}}) & {stats_gas['mean']:,.0f} gas & Costo computacional en EVM \\\\
Tiempo de Sellado (Block Sealing) & {stats_seal['mean']} ms & Confirmación asíncrona del bloque \\\\
Transacciones Notariadas & {stats_gas['count']} & Eventos inmutables en ledger \\\\ \\hline
\\end{{tabular}}
\\end{{table}}
"""

    with open(TEX_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(tex_content)

    print(f"\n🎉 Reporte generado con éxito:")
    print(f"   📄 Markdown: {MD_REPORT_PATH}")
    print(f"   📝 LaTeX:    {TEX_REPORT_PATH}")
    print(f"\nResumen:")
    print(f"   • Muestras: {total_samples} (Vivos: {live_count}, Spoof: {spoof_count})")
    print(f"   • Exactitud (Accuracy): {accuracy:.2f}% | Recall: {recall:.2f}% | Precision: {precision:.2f}%")
    print(f"   • FAR: {far:.2f}% | FRR: {frr:.2f}%")
    print(f"   • Latencia Media End-to-End: {stats_e2e['mean']} ms (Borde: {stats_edge['mean']} ms, Red: {stats_net['mean']} ms, Servidor: {stats_back['mean']} ms)")


if __name__ == "__main__":
    generate_reports()
