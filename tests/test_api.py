"""
test_api.py — Tests de integración para los endpoints de la API
Usa FastAPI TestClient para verificar los endpoints sin levantar un servidor.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient
import numpy as np
import base64
import cv2

# Ajustar path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app


# =========================================================================
#                       FIXTURES
# =========================================================================

@pytest.fixture
def client():
    """Crea un cliente de prueba de FastAPI."""
    return TestClient(app)


@pytest.fixture
def sample_image_base64():
    """Genera una imagen de prueba en Base64."""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(img, (100, 80), 50, (200, 200, 200), -1)
    cv2.circle(img, (85, 70), 8, (50, 50, 50), -1)
    cv2.circle(img, (115, 70), 8, (50, 50, 50), -1)
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')


# =========================================================================
#                  TESTS DE SALUD DEL SISTEMA
# =========================================================================

class TestHealth:
    """Tests para verificar que el servidor está online."""

    def test_root_endpoint(self, client):
        """Verifica que la raíz responde correctamente."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "blockchain" in data

    def test_docs_available(self, client):
        """Verifica que la documentación Swagger está disponible."""
        response = client.get("/docs")
        assert response.status_code == 200


# =========================================================================
#               TESTS DE REGISTRO
# =========================================================================

class TestRegistration:
    """Tests para el endpoint de registro de usuarios."""

    def test_register_without_image(self, client):
        """Verifica que registrar sin imagen da error 422."""
        payload = {
            "user_id": "TEST-001",
            "name": "Test User",
            "role": "Tester"
            # Falta image_base64
        }
        response = client.post("/api/v1/register", json=payload)
        assert response.status_code == 422  # Validation Error

    def test_register_with_empty_fields(self, client):
        """Verifica que campos vacíos son procesados."""
        payload = {
            "user_id": "",
            "name": "",
            "role": "",
            "image_base64": "invalid"
        }
        response = client.post("/api/v1/register", json=payload)
        # Debería fallar en el procesamiento de la imagen
        assert response.status_code in [400, 500]


# =========================================================================
#               TESTS DE AUTENTICACIÓN
# =========================================================================

class TestAuthentication:
    """Tests para el endpoint de autenticación."""

    def test_authenticate_without_image(self, client):
        """Verifica que autenticar sin imagen da error 422."""
        payload = {}
        response = client.post("/api/v1/authenticate", json=payload)
        assert response.status_code == 422

    def test_authenticate_empty_db(self, client, sample_image_base64):
        """Verifica el comportamiento con la base de datos vacía."""
        payload = {"image_base64": sample_image_base64}
        response = client.post("/api/v1/authenticate", json=payload)
        # Puede dar 401 (no encontrado) o 400 (no se detectó rostro en imagen de prueba)
        assert response.status_code in [400, 401]


# =========================================================================
#               TESTS DE BLOCKCHAIN
# =========================================================================

class TestBlockchain:
    """Tests para los endpoints de blockchain."""

    def test_blockchain_status(self, client):
        """Verifica que el endpoint de estado blockchain responde."""
        response = client.get("/api/v1/blockchain/status")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data

    def test_auth_history_nonexistent_user(self, client):
        """Verifica consulta de historial cuando blockchain no está disponible."""
        response = client.get("/api/v1/auth-history/NO-EXISTE")
        # 503 si blockchain no disponible, o 200 con registros vacíos
        assert response.status_code in [200, 503]


# =========================================================================
#                    EJECUCIÓN
# =========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
