# BioAuth-Web3 🛡️🔗

**BioAuth-Web3** es un sistema profesional de autenticación biométrica (reconocimiento facial) que integra medidas de seguridad anti-spoofing de vanguardia y registra los eventos en una red blockchain para garantizar la inmutabilidad y la transparencia de los accesos.

Este proyecto forma parte de un Trabajo de Grado y está diseñado para asegurar que la autenticación no pueda ser vulnerada fácilmente usando fotografías fijas o pantallas (ataques de presentación).

---

## 🏗️ Arquitectura del Sistema

El proyecto está dividido en tres componentes principales:

1. **Smart Contract (Blockchain)**
   - Escrito en Solidity (`AccessRegistry.sol`).
   - Almacena eventos de autenticación con: Hash biométrico, ID de usuario, Timestamp, Resultado (éxito o fallo) y Dirección del dispositivo.
   - Despliegue automatizado con `web3.py` en una red local Ganache.

2. **Backend (Python / FastAPI)**
   - **Reconocimiento Facial:** Utiliza la librería `face_recognition` (basada en dlib y ResNet) con una precisión de estado del arte (99.38% LFW).
   - **Anti-Spoofing:** Implementa análisis de textura (LBP) para detectar pantallas y análisis de frecuencias (FFT) para descartar imágenes manipuladas.
   - **Seguridad:** Tokens JWT, API Keys, contraseñas hasheadas y Rate Limiting.
   - **Base de Datos:** SQLite en modo WAL para manejar altos volúmenes de eventos en simultáneo a las escrituras en la Blockchain.

3. **Frontend (React / Vite)**
   - Aplicación de página única (SPA) desarrollada con **React** y **TypeScript**.
   - Acceso nativo a la cámara web (`navigator.mediaDevices.getUserMedia`) para biometría.
   - UI construida con **Tailwind CSS v4** y componentes estructurales basados en la metodología de *shadcn/ui*.
   - Rutas interactivas: Registro (`/signup`), Acceso Biomético (`/`), y Panel Protegido (`/dashboard`).

---

## 📋 Requisitos Previos

Asegúrate de tener instalados los siguientes programas antes de comenzar:

- **Python 3.10+**: Para ejecutar el backend y los scripts de machine learning.
- **Node.js (18+ o 20+)**: Para ejecutar el frontend (NPM / Vite).
- **Ganache**: Para levantar una red blockchain local de pruebas. Puedes usar la versión UI (Ganache) o CLI (`npm install -g ganache-cli`).
- **Compilador de C++ / CMake**: Requerido por la librería `dlib` utilizada internamente por `face_recognition`. (En Windows, instala "Desktop development with C++" usando *Visual Studio Build Tools*).

---

## 🚀 Pasos para Ejecutar el Proyecto

Sigue este orden estricto para levantar el entorno completo.

### Paso 1: Levantar la Blockchain (Ganache)

1. Abre **Ganache** (la aplicación de escritorio).
2. Haz clic en **Quickstart** para iniciar una red local (generalmente en `http://127.0.0.1:7545` con Chain ID `1337` o `5777`).
3. El proyecto se conectará automáticamente al primer puerto de Ganache disponible.

### Paso 2: Preparar y Desplegar Backend

Abre una terminal en la raíz del proyecto (`BioAuth-Web3`):

```bash
# 1. Crear entorno virtual (solo la primera vez)
python -m venv venv

# 2. Activar entorno virtual
# En Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# En Linux/Mac:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Desplegar el Smart Contract en Ganache
# Este script compila Solidity, lo sube a la red, y guarda la dirección en tu archivo .env
python blockchain/deploy.py

# 5. Iniciar la API Backend
uvicorn app.main:app --reload
# El servidor backend correrá en http://127.0.0.1:8000
```

### Paso 3: Levantar el Frontend 

Abre **otra ventana de terminal**, y sitúate en la carpeta del frontend:

```bash
# 1. Entrar a la carpeta frontend
cd frontend

# 2. Instalar las dependencias de React
npm install

# 3. Ejecutar el servidor de desarrollo
npm run dev
```

El servidor Vite lanzará la aplicación en **[http://localhost:5173/](http://localhost:5173/)**.

---

## 📱 Uso del Sistema

* **1. Registro**: Ingresa a la interfaz y dirígete a "Registrarse". Completa tu Cédula, Nombre y Rol. El sistema activará tu cámara para extraer e codificar tus vectores faciales.
* **2. Login**: Ve al "Inicio de sesión". Tu rostro **es la única contraseña**. El sistema identificará tus marcadores biométricos, aplicará algoritmos anti-spoofing y, si eres legítimo, enviará un registro a la Blockchain.
* **3. Verificación Web3**: Al ingresar al Dashboard, podrás consultar el estatus en tiempo real que demuestra la conexión entre el sistema de autenticación centralizado y el registro inmutable en Ethereum/Ganache.

---

## 🛡️ Diagrama de Seguridad Anti-Spoofing

El backend no acepta imágenes ciegamente. Al recibir una foto en base64 desde el frontend:
1. **Verificadores de Calidad**: Confirman que el rostro esté bien iluminado usando CLAHE.
2. **Análisis Espectral FFT**: Filtra fotos impresas en papel analizando cambios en la alta frecuencia.
3. **Análisis de Textura LBP**: Extrae micro-texturas para descubrir si la foto proviene de una pantalla (moiré patterns).
4. **Verificación Biométrica**: Mapeo matemático final de 128-puntos en el rostro (Face Recognition).

---
*Desarrollado para la investigación y avance de la seguridad web descentralizada.*
