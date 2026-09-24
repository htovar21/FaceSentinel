# FaceSentinel — Resultados Experimentales del Capítulo IV

**Fecha de Generación:** 2026-09-24 18:03:43  
**Total de Muestras Evaluadas:** 40 intentos (24 accesos legítimos vivos, 16 intentos de spoofing)

---

## 1. Matriz de Confusión y Métricas de Rendimiento Biométrico

| Condición Real \ Decisión Sistema | Acceso Concedido (GRANTED) | Acceso Denegado (DENIED) | Total Real |
|:---|:---:|:---:|:---:|
| **Sujeto Legítimo (LIVE)** | **Verdaderos Positivos (VP): 19** | **Falsos Negativos (FN): 5** | 24 |
| **Ataque de Presentación (SPOOF)** | **Falsos Positivos (FP): 7** | **Verdaderos Negativos (VN): 9** | 16 |
| **Total Clasificado** | 26 | 14 | **40** |

### Indicadores de Eficacia Biometría y Anti-Spoofing

- **Exactitud Global (Accuracy):** `70.00%`
- **Precisión (Precision):** `73.08%`
- **Sensibilidad / Tasa de Acierto (Recall / TPR):** `79.17%`
- **Especificidad (TNR):** `56.25%`
- **F1-Score:** `76.00%`
- **Tasa de Falsa Aceptación (FAR / FPR):** `43.75%` *(Debe tender a 0.0%)*
- **Tasa de Falso Rechazo (FRR / FNR):** `20.83%`

---

## 2. Análisis de Causa Raíz de Falsos Negativos (Condiciones Ambientales)

Distribución de los **5 Falsos Negativos** según iluminación:
- **Iluminación Normal:** 5 casos (100.0%)
- **Contraluz / Exceso de Luz (HIGH_LIGHT):** 0 casos (0.0%)
- **Baja Iluminación (LOW_LIGHT):** 0 casos (0.0%)

> **Hallazgo Académico:** El 0.0% de las denegaciones erróneas fueron inducidas por condiciones de iluminación no controladas.

---

## 3. Desglose de Latencias de Procesamiento (Milisegundos)

| Componente del Pipeline | Media (ms) | Desv. Est. (ms) | Mínimo (ms) | Máximo (ms) | Muestras |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Edge: MediaPipe Face Mesh (EAR)** | `7.66` | `±8.16` | `2.42` | `22.5` | 40 |
| **Edge: Procesamiento Total Borde** | `9.73` | `±15.52` | `0.41` | `38.0` | 40 |
| **Red Troncal (Network RTT Transit)** | `14.6` | `±0.6` | `14.0` | `15.2` | 10 |
| **Backend: LBP Entropía de Textura** | `16.95` | `±4.35` | `11.0` | `30.62` | 38 |
| **Backend: FFT Espectro Frecuencia** | `2.44` | `±3.21` | `0.37` | `8.1` | 38 |
| **Backend: ArcFace Extracción 512d** | `374.4` | `±563.51` | `178.68` | `2427.41` | 27 |
| **Backend: ChromaDB Búsqueda Vectorial** | `13.44` | `±11.17` | `7.23` | `52.7` | 27 |
| **Backend: SQLite Verificación ACL/Token** | `173.69` | `±99.27` | `1.8` | `247.68` | 40 |
| **Backend: Tiempo Total Servidor** | `466.57` | `±533.18` | `22.0` | `2738.83` | 40 |
| **Latencia Total End-to-End (Borde + Red + Servidor)** | **`479.95`** | **`±526.23`** | **`71.0`** | **`2739.4`** | 40 |

---

## 4. Métricas de Discriminación Anti-Spoofing y Biometría

| Métrica Científica | Sujeto Vivo (Legítimo) | Foto Impresa (Spoof) | Pantalla Digital (Spoof) |
|:---|:---:|:---:|:---:|
| **Entropía de Shannon (LBP)** | `3.8 ± 0.26` | `2.95 ± 0.0` | `3.64 ± 0.04` |
| **Distancia Coseno (ArcFace)** | `0.44 ± 0.15` *(Match)* | N/A | `0.88 ± 0.0` *(No match)* |

---

## 5. Eficiencia y Rendimiento Blockchain (Smart Contract)

- **Consumo de Gas Promedio (`logAuthentication`):** `190,900 gas` (Mín: `68,432` | Máx: `259,075`)
- **Tiempo de Sellado / Inclusión en Bloque (Sealing Time):** `60.43 ms` (`±33.91 ms`)
- **Total Transacciones Notariadas en Cadena:** `40`
