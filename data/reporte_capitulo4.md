# FaceSentinel — Resultados Experimentales y Evaluación Científica del Capítulo IV

**Fecha de Evaluación:** 2026-09-25 14:29:18  
**Dataset Analizado:** `metricas_tesis.csv`  
**Total de Ensayos Registrados:** 484 intentos de autenticación

---

## 1. Matriz de Confusión Global de Control de Acceso

La siguiente matriz clasifica las decisiones del sistema entre accesos legítimos autorizados frente a intentos indebidos (ataques de presentación con foto/video e impostores no registrados):

| Condición Real \ Decisión Sistema | Acceso Concedido (GRANTED) | Acceso Denegado (DENIED) | Total Real |
|:---|:---:|:---:|:---:|
| **Sujeto Autorizado (Bona Fide Live)** | **Verdaderos Positivos (VP): 140** | **Falsos Negativos (FN): 328** | 468 |
| **Intento Indebido (Ataques + Impostores)** | **Falsos Positivos (FP): 7** | **Verdaderos Negativos (VN): 9** | 16 |
| **Total Clasificado** | 147 | 337 | **484** |

### Indicadores Globales de Seguridad
- **Exactitud General (Accuracy):** `30.79%`
- **Precisión (Precision):** `95.24%`
- **Sensibilidad / Tasa de Acierto (Recall / TPR):** `29.91%`
- **Especificidad (TNR):** `56.25%`
- **F1-Score:** `45.53%`
- **Tasa Global de Falsa Aceptación (FAR):** `43.75%` *(Vulnerabilidad de acceso)*
- **Tasa Global de Falso Rechazo (FRR):** `70.09%` *(Fricción de usuario)*

---

## 2. Evaluación Específica de Detección de Ataques de Presentación (PAD / ISO/IEC 30107-3)

Evaluación del subsistema Anti-Spoofing en el borde y servidor (MediaPipe Blink EAR + Textura LBP):

| Indicador PAD (ISO/IEC 30107-3) | Valor Obtenido | Muestras Evaluadas | Interpretación Técnica |
|:---|:---:|:---:|:---|
| **APCER - Fotos Impresas/Pantalla** | `0.00%` | 5 intentos | Fotos que burlaron la detección de liveness |
| **APCER - Video Replay con Parpadeo** | `72.73%` | 11 intentos | Videos en smartphone que lograron traspasar |
| **APCER Global (Ataques no detectados)** | **`50.00%`** | 16 ataques | Tasa total de filtración de ataques de presentación |
| **BPCER (Falso rechazo a vivos genuinos)**| **`32.91%`** | 468 intentos | Usuarios vivos confundidos erróneamente con spoofing |
| **ACER (Error Medio de Clasificación)**   | **`41.45%`** | 484 muestras | Media balanceada entre APCER y BPCER |

---

## 3. Evaluación del Reconocimiento Facial Biométrico (ISO/IEC 19795-1)

Rendimiento del modelo DeepFace ArcFace (512 dimensiones) con indexación vectorial ChromaDB (HNSW):

| Métrica Biometría Facial | Valor Obtenido | Muestras | Interpretación |
|:---|:---:|:---:|:---|
| **FNMR (False Non-Match Rate)** | `36.32%` | 468 | Usuarios autorizados vivos rechazados por distancia $d > 0.75$ |
| **FMR (False Match Rate)** | `0.00%` | 0 | Impostores vivos aceptados con distancia $d \le 0.75$ |
| **Distancia Coseno (Genuine Match)** | `0.32 ± 0.27` | 147 | Distancia promedio para accesos autorizados |
| **Distancia Coseno (Impostores/Desconocidos)** | `0.83 ± 0.08` | 168 | Distancia promedio para rostros no emparejados |

---

## 4. Análisis de Robustez ante Condiciones Ambientales (Iluminación)

| Entorno Evaluado | Muestras Totales | Decisiones Correctas | Fallos | Exactitud (%) | Latencia Media E2E (ms) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Iluminación Normal (Oficina/Lab)** | 479 | 144 | 335 | 30.06% | 514.53 ms |
| **Baja Iluminación (< 50 lux)** | 0 | 0 | 0 | 0.00% | 0.0 ms |
| **Alta Luz / Contraluz (> 1000 lux)** | 5 | 5 | 0 | 100.00% | 71.0 ms |

---

## 5. Benchmarking de Latencias del Pipeline (Milisegundos)

| Componente de Arquitectura | Media (ms) | Desv. Est. (ms) | Percentil 95 (ms) | Mín (ms) | Máx (ms) | Muestras |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Borde: MediaPipe Face Mesh (EAR)** | `5.31` | `±2.72` | `7.79` | `2.42` | `22.5` | 484 |
| **Borde: Procesamiento Total Borde** | `7.32` | `±4.68` | `9.79` | `0.41` | `38.0` | 484 |
| **Red Troncal: Tránsito RTT** | `14.6` | `±0.6` | `15.2` | `14.0` | `15.2` | 10 |
| **Servidor: LBP Entropía Textura** | `12.61` | `±6.08` | `23.1` | `6.61` | `55.91` | 409 |
| **Servidor: FFT Espectro Frecuencia** | `1.04` | `±1.18` | `1.97` | `0.37` | `8.1` | 409 |
| **Servidor: ArcFace Extracción 512d** | `346.74` | `±546.69` | `383.53` | `8.68` | `4936.26` | 322 |
| **Servidor: ChromaDB Búsqueda Vectorial** | `12.09` | `±10.91` | `26.57` | `5.58` | `102.35` | 315 |
| **Servidor: SQLite Validación ACL/RBAC** | `235.27` | `±36.02` | `260.61` | `1.8` | `316.61` | 484 |
| **Servidor: Latencia Total Backend** | `502.33` | `±491.59` | `624.86` | `22.0` | `5276.98` | 484 |
| **Latencia Total End-to-End** | **`509.95`** | **`±490.95`** | **`631.46`** | **`71.0`** | **`5282.46`** | 484 |

---

## 6. Eficiencia de Auditoría Blockchain (Smart Contract en Ethereum)

- **Consumo de Gas Promedio (`logAuthentication`):** `209,890 gas` (Mín: `68,432` | Máx: `264,675`)
- **Tiempo de Sellado de Bloque (Sealing Time):** `51.21 ms` (`±15.43 ms` | P95: `83.24 ms`)
- **Total de Transacciones Notariadas en Cadena:** `484` eventos
