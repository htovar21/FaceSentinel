# Base Image: Python 3.10 slim
FROM python:3.10-slim

# Variables de entorno de Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema requeridas por OpenCV y TensorFlow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar pesos del modelo de IA (ArcFace) para asegurar funcionamiento offline e instantáneo
RUN python -c "from deepface import DeepFace; DeepFace.build_model('ArcFace')" || true

# Copiar el código de la aplicación
COPY . .

# Asegurar directorios de persistencia
RUN mkdir -p /app/data/sql /app/data/chromadb /app/data/temp_images /app/data/logs /root/.deepface

EXPOSE 8000

# Comprobación de salud (Healthcheck)
HEALTHCHECK --interval=30s --timeout=10s --start-period=35s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Comando de inicio del servidor ASGI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
