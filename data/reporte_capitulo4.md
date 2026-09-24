# FaceSentinel — Resultados Experimentales del Capítulo IV

**Fecha de Generación:** 2026-09-23 20:08:05  
**Total de Muestras Evaluadas:** 8 intentos (4 accesos legítimos vivos, 4 intentos de spoofing)

---

## 1. Matriz de Confusión y Métricas de Rendimiento Biométrico

| Condición Real \ Decisión Sistema | Acceso Concedido (GRANTED) | Acceso Denegado (DENIED) | Total Real |
|:---|:---:|:---:|:---:|
| **Sujeto Legítimo (LIVE)** | **Verdaderos Positivos (VP): 4** | **Falsos Negativos (FN): 0** | 4 |
| **Ataque de Presentación (SPOOF)** | **Falsos Positivos (FP): 0** | **Verdaderos Negativos (VN): 4** | 4 |
| **Total Clasificado** | 4 | 4 | **8** |

### Indicadores de Eficacia Biometría y Anti-Spoofing

- **Exactitud Global (Accuracy):** `100.00%`
- **Precisión (Precision):** `100.00%`
- **Sensibilidad / Tasa de Acierto (Recall / TPR):** `100.00%`
- **Especificidad (TNR):** `100.00%`
- **F1-Score:** `100.00%`
- **Tasa de Falsa Aceptación (FAR / FPR):** `0.00%` *(Debe tender a 0.0%)*
- **Tasa de Falso Rechazo (FRR / FNR):** `0.00%`

---

## 2. Análisis de Causa Raíz de Falsos Negativos (Condiciones Ambientales)

Distribución de los **0 Falsos Negativos** según iluminación:
- **Iluminación Normal:** 0 casos (0.0%)
- **Contraluz / Exceso de Luz (HIGH_LIGHT):** 0 casos (0.0%)
- **Baja Iluminación (LOW_LIGHT):** 0 casos (0.0%)

> **Hallazgo Académico:** El 0.0% de las denegaciones erróneas fueron inducidas por condiciones de iluminación no controladas.

---

## 3. Desglose de Latencias de Procesamiento (Milisegundos)

| Componente del Pipeline | Media (ms) | Desv. Est. (ms) | Mínimo (ms) | Máximo (ms) | Muestras |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Edge: MediaPipe Face Mesh (EAR)** | `21.75` | `±0.75` | `21.0` | `22.5` | 8 |
| **Edge: Procesamiento Total Borde** | `36.5` | `±1.5` | `35.0` | `38.0` | 8 |
| **Red Troncal (Network RTT Transit)** | `14.6` | `±0.6` | `14.0` | `15.2` | 8 |
| **Backend: LBP Entropía de Textura** | `11.7` | `±0.7` | `11.0` | `12.4` | 8 |
| **Backend: FFT Espectro Frecuencia** | `7.8` | `±0.3` | `7.5` | `8.1` | 8 |
| **Backend: ArcFace Extracción 512d** | `245.0` | `±0.0` | `245.0` | `245.0` | 4 |
| **Backend: ChromaDB Búsqueda Vectorial** | `11.2` | `±0.0` | `11.2` | `11.2` | 4 |
| **Backend: SQLite Verificación ACL/Token** | `1.95` | `±0.15` | `1.8` | `2.1` | 8 |
| **Backend: Tiempo Total Servidor** | `153.5` | `±131.5` | `22.0` | `285.0` | 8 |
| **Latencia Total End-to-End (Borde + Red + Servidor)** | **`204.6`** | **`±133.6`** | **`71.0`** | **`338.2`** | 8 |

---

## 4. Métricas de Discriminación Anti-Spoofing y Biometría

| Métrica Científica | Sujeto Vivo (Legítimo) | Foto Impresa (Spoof) | Pantalla Digital (Spoof) |
|:---|:---:|:---:|:---:|
| **Entropía de Shannon (LBP)** | `4.25 ± 0.0` | `2.95 ± 0.0` | `0.0 ± 0.0` |
| **Distancia Coseno (ArcFace)** | `0.23 ± 0.0` *(Match)* | N/A | `0.0 ± 0.0` *(No match)* |

---

## 5. Eficiencia y Rendimiento Blockchain (Smart Contract)

- **Consumo de Gas Promedio (`logAuthentication`):** `68,432 gas` (Mín: `68,432` | Máx: `68,432`)
- **Tiempo de Sellado / Inclusión en Bloque (Sealing Time):** `112.7 ms` (`±2.7 ms`)
- **Total Transacciones Notariadas en Cadena:** `8`
