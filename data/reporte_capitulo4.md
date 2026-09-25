# FaceSentinel — Resultados Experimentales y Evaluación Científica del Capítulo IV

**Fecha de Evaluación:** 2026-09-25 15:59:25  
**Dataset Analizado:** `metricas_tesis.csv`  
**Total de Ensayos Registrados:** 536 intentos de autenticación

---

## 1. Matriz de Confusión Global de Control de Acceso

La siguiente matriz clasifica las decisiones del sistema entre accesos legítimos autorizados frente a intentos indebidos (ataques de presentación con foto/video e impostores no registrados):

| Condición Real \ Decisión Sistema | Acceso Concedido (GRANTED) | Acceso Denegado (DENIED) | Total Real |
|:---|:---:|:---:|:---:|
| **Sujeto Autorizado (Bona Fide Live)** | **Verdaderos Positivos (VP): 165** | **Falsos Negativos (FN): 348** | 513 |
| **Intento Indebido (Ataques + Impostores)** | **Falsos Positivos (FP): 7** | **Verdaderos Negativos (VN): 16** | 23 |
| **Total Clasificado** | 172 | 364 | **536** |

### Indicadores Globales de Seguridad
- **Exactitud General (Accuracy):** `33.77%`
- **Precisión (Precision):** `95.93%`
- **Sensibilidad / Tasa de Acierto (Recall / TPR):** `32.16%`
- **Especificidad (TNR):** `69.57%`
- **F1-Score:** `48.18%`
- **Tasa Global de Falsa Aceptación (FAR):** `30.43%` *(Vulnerabilidad de acceso)*
- **Tasa Global de Falso Rechazo (FRR):** `67.84%` *(Fricción de usuario)*

---

## 2. Evaluación Específica de Detección de Ataques de Presentación (PAD / ISO/IEC 30107-3)

Evaluación del subsistema Anti-Spoofing en el borde y servidor (MediaPipe Blink EAR + Textura LBP):

| Indicador PAD (ISO/IEC 30107-3) | Valor Obtenido | Muestras Evaluadas | Interpretación Técnica |
|:---|:---:|:---:|:---|
| **APCER - Fotos Impresas/Pantalla** | `0.00%` | 12 intentos | Fotos que burlaron la detección de liveness |
| **APCER - Video Replay con Parpadeo** | `72.73%` | 11 intentos | Videos en smartphone que lograron traspasar |
| **APCER Global (Ataques no detectados)** | **`34.78%`** | 23 ataques | Tasa total de filtración de ataques de presentación |
| **BPCER (Falso rechazo a vivos genuinos)**| **`31.97%`** | 513 intentos | Usuarios vivos confundidos erróneamente con spoofing |
| **ACER (Error Medio de Clasificación)**   | **`33.38%`** | 536 muestras | Media balanceada entre APCER y BPCER |

---

## 3. Evaluación del Reconocimiento Facial Biométrico (ISO/IEC 19795-1)

Rendimiento del modelo DeepFace ArcFace (512 dimensiones) con indexación vectorial ChromaDB (HNSW):

| Métrica Biometría Facial | Valor Obtenido | Muestras | Interpretación |
|:---|:---:|:---:|:---|
| **FNMR (False Non-Match Rate)** | `35.09%` | 513 | Usuarios autorizados vivos rechazados por distancia $d > 0.75$ |
| **FMR (False Match Rate)** | `0.00%` | 0 | Impostores vivos aceptados con distancia $d \le 0.75$ |
| **Distancia Coseno (Genuine Match)** | `0.31 ± 0.27` | 172 | Distancia promedio para accesos autorizados |
| **Distancia Coseno (Impostores/Desconocidos)** | `0.84 ± 0.08` | 178 | Distancia promedio para rostros no emparejados |

---

## 4. Análisis de Robustez ante Condiciones Ambientales (Iluminación)

| Entorno Evaluado | Muestras Totales | Decisiones Correctas | Fallos | Exactitud (%) | Latencia Media E2E (ms) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Iluminación Normal (Oficina/Lab)** | 524 | 169 | 355 | 32.25% | 513.38 ms |
| **Baja Iluminación (< 50 lux)** | 0 | 0 | 0 | 0.00% | 0.0 ms |
| **Alta Luz / Contraluz (> 1000 lux)** | 12 | 12 | 0 | 100.00% | 121.6 ms |

---

## 5. Benchmarking de Latencias del Pipeline (Milisegundos)

| Componente de Arquitectura | Media (ms) | Desv. Est. (ms) | Percentil 95 (ms) | Mín (ms) | Máx (ms) | Muestras |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Borde: MediaPipe Face Mesh (EAR)** | `5.7` | `±3.82` | `9.25` | `2.42` | `23.4` | 536 |
| **Borde: Procesamiento Total Borde** | `8.06` | `±6.62` | `11.25` | `0.41` | `39.1` | 536 |
| **Red Troncal: Tránsito RTT** | `14.6` | `±0.6` | `15.2` | `14.0` | `15.2` | 18 |
| **Servidor: LBP Entropía Textura** | `12.34` | `±5.9` | `22.76` | `6.61` | `55.91` | 458 |
| **Servidor: FFT Espectro Frecuencia** | `1.13` | `±1.43` | `2.93` | `0.37` | `8.1` | 458 |
| **Servidor: ArcFace Extracción 512d** | `343.03` | `±540.64` | `383.53` | `8.68` | `4936.26` | 357 |
| **Servidor: ChromaDB Búsqueda Vectorial** | `11.94` | `±10.67` | `25.36` | `5.58` | `102.35` | 350 |
| **Servidor: SQLite Validación ACL/RBAC** | `231.56` | `±44.71` | `259.89` | `1.8` | `344.36` | 536 |
| **Servidor: Latencia Total Backend** | `496.06` | `±487.71` | `614.93` | `22.0` | `5276.98` | 536 |
| **Latencia Total End-to-End** | **`504.61`** | **`±486.53`** | **`621.07`** | **`71.0`** | **`5282.46`** | 536 |

---

## 6. Eficiencia de Auditoría Blockchain (Smart Contract en Ethereum)

- **Consumo de Gas Promedio (`logAuthentication`):** `208,665 gas` (Mín: `68,432` | Máx: `264,675`)
- **Tiempo de Sellado de Bloque (Sealing Time):** `52.13 ms` (`±16.71 ms` | P95: `94.52 ms`)
- **Total de Transacciones Notariadas en Cadena:** `536` eventos
