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


@pytest.fixture
def admin_headers():
    """Crea token JWT con rol admin para pruebas autorizadas."""
    from app.core.security import create_access_token
    token = create_access_token(data={"sub": "admin", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


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

    def test_register_unauthenticated_returns_401(self, client):
        """Verifica que registrar sin credenciales de admin da 401."""
        response = client.post("/api/v1/register", json={})
        assert response.status_code == 401

    def test_register_without_image(self, client, admin_headers):
        """Verifica que registrar sin imagen da error 422."""
        payload = {
            "user_id": "TEST-001",
            "name": "Test User",
            "role": "Tester"
            # Falta image_base64
        }
        response = client.post("/api/v1/register", json=payload, headers=admin_headers)
        assert response.status_code == 422  # Validation Error

    def test_register_with_empty_fields(self, client, admin_headers):
        """Verifica que campos vacíos son procesados."""
        payload = {
            "user_id": "",
            "name": "",
            "role": "",
            "image_base64": "invalid"
        }
        response = client.post("/api/v1/register", json=payload, headers=admin_headers)
        # Debería fallar en el procesamiento de la imagen
        assert response.status_code in [400, 500]


# =========================================================================
#               TESTS DE AUTENTICACIÓN
# =========================================================================

class TestAuthentication:
    """Tests para los endpoints de autenticación."""

    def test_deprecated_authenticate_returns_410(self, client, sample_image_base64):
        """Verifica que el antiguo endpoint biométrico POST retorne 410 (Deprecated)."""
        payload = {"image_base64": sample_image_base64}
        response = client.post("/api/v1/authenticate", json=payload)
        assert response.status_code == 410

    def test_password_auth_missing_fields(self, client):
        """Verifica que falten campos retorne 422."""
        response = client.post("/api/v1/auth/password", json={})
        assert response.status_code == 422

    def test_password_auth_invalid_credentials(self, client):
        """Verifica que credenciales incorrectas retornen 401."""
        payload = {"username": "non_existent_developer", "password": "wrongpassword"}
        response = client.post("/api/v1/auth/password", json=payload)
        assert response.status_code == 401


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

    def test_auth_history_nonexistent_user(self, client, admin_headers):
        """Verifica consulta de historial cuando blockchain no está disponible."""
        response = client.get("/api/v1/auth-history/NO-EXISTE", headers=admin_headers)
        # 503 si blockchain no disponible, o 200 con registros vacíos
        assert response.status_code in [200, 503]


# =========================================================================
#            TESTS DE ENDPOINTS PROTEGIDOS & HARDENING
# =========================================================================

class TestSecurityHardening:
    """Tests para verificar los fixes de seguridad aplicados."""

    def test_delete_user_unauthenticated_returns_401(self, client):
        """Fix #2: DELETE /users/{id} sin autenticacion debe retornar 401."""
        response = client.delete("/api/v1/users/NON_EXISTENT_USER")
        assert response.status_code == 401

    def test_device_registration_and_lookup_hash(self, client, admin_headers):
        """Fix #6: Dispositivo registrado almacena token_lookup_hash y se busca en O(1)."""
        import secrets
        from app.services.storage import get_device_by_token

        device_id = f"test_dev_{secrets.token_hex(4)}"
        payload = {
            "device_id": device_id,
            "device_name": "Puerta de Prueba",
            "device_type": "door",
            "location": "Laboratorio"
        }
        res = client.post("/api/v1/devices", json=payload, headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        raw_secret = data["client_secret"]
        assert raw_secret.startswith("hw_")

        # Verificar que get_device_by_token encuentra el dispositivo inmediatamente
        found = get_device_by_token(raw_secret)
        assert found is not None
        assert found["device_id"] == device_id

        # Limpieza
        client.delete(f"/api/v1/devices/{device_id}", headers=admin_headers)

    def test_physical_access_corrupted_frame_returns_422(self, client, admin_headers):
        """Valida que un fotograma corrupto retorne HTTP 422 en vez de registrar falso spoofing."""
        import secrets
        import base64
        import cv2
        import numpy as np

        device_id = f"test_dev_{secrets.token_hex(4)}"
        reg_payload = {
            "device_id": device_id,
            "device_name": "Torniquete Corrupt Test",
            "device_type": "door",
            "location": "Entrada",
            "antispoofing_enabled": True
        }
        res = client.post("/api/v1/devices", json=reg_payload, headers=admin_headers)
        assert res.status_code == 200
        raw_secret = res.json()["client_secret"]

        # Crear imagen corrupta / plana (negro absoluto)
        blank = np.zeros((240, 240, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", blank)
        b64_blank = base64.b64encode(buf).decode("utf-8")

        auth_payload = {
            "image_base64": b64_blank,
            "test_type": "LIVE_USER",
            "environmental_condition": "NORMAL"
        }
        auth_res = client.post(
            "/api/v1/physical-access/authenticate",
            json=auth_payload,
            headers={"Authorization": f"Bearer {raw_secret}"}
        )
        assert auth_res.status_code == 422
        assert "corrupto" in auth_res.json()["detail"].lower()

        # Limpieza
        client.delete(f"/api/v1/devices/{device_id}", headers=admin_headers)


# =========================================================================
#                    EJECUCIÓN
# =========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
