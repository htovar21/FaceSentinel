"""
test_recognition.py — Tests unitarios para el servicio de reconocimiento facial
Verifica el flujo de registro, verificación, y almacenamiento.
"""

import os
import sys
import pytest
import numpy as np
import base64
import cv2

# Ajustar path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =========================================================================
#                       FIXTURES (Datos de prueba)
# =========================================================================

@pytest.fixture
def sample_image_base64():
    """Genera una imagen de prueba en Base64 (cuadro negro con un círculo blanco)."""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    # Dibujar un "rostro" básico para que OpenCV pueda procesarlo
    cv2.circle(img, (100, 80), 50, (200, 200, 200), -1)   # Cabeza
    cv2.circle(img, (85, 70), 8, (50, 50, 50), -1)         # Ojo izq
    cv2.circle(img, (115, 70), 8, (50, 50, 50), -1)        # Ojo der
    cv2.ellipse(img, (100, 100), (20, 10), 0, 0, 180, (100, 100, 100), 2)  # Boca
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')


@pytest.fixture
def empty_image_base64():
    """Genera una imagen vacía (negra) sin ningún rostro."""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')


@pytest.fixture
def sample_embedding():
    """Genera un embedding facial simulado (vector de 512 dimensiones)."""
    np.random.seed(42)
    return np.random.randn(512).tolist()


# =========================================================================
#                    TESTS DE CONVERSIÓN DE IMAGEN
# =========================================================================

class TestImageConversion:
    """Tests para la conversión Base64 -> OpenCV."""

    def test_base64_to_image_valid(self, sample_image_base64):
        """Verifica que una imagen Base64 válida se convierte correctamente."""
        from app.services.face_recognition import base64_to_image

        img = base64_to_image(sample_image_base64)
        assert img is not None
        assert isinstance(img, np.ndarray)
        assert len(img.shape) == 3  # Debe tener 3 dimensiones (alto, ancho, canales)

    def test_base64_to_image_with_header(self, sample_image_base64):
        """Verifica que maneja correctamente el header data:image/jpeg;base64,..."""
        from app.services.face_recognition import base64_to_image

        img_with_header = f"data:image/jpeg;base64,{sample_image_base64}"
        img = base64_to_image(img_with_header)
        assert img is not None

    def test_base64_to_image_invalid(self):
        """Verifica que una imagen inválida lanza un error."""
        from app.services.face_recognition import base64_to_image

        with pytest.raises(Exception):
            base64_to_image("esto-no-es-base64-valido!!!")


# =========================================================================
#                    TESTS DE ALMACENAMIENTO
# =========================================================================

class TestStorage:
    """Tests para el servicio de almacenamiento (SQLite + ChromaDB)."""

    def test_save_and_retrieve_user(self, sample_embedding):
        """Verifica que se puede guardar y recuperar un usuario."""
        from app.services.storage import save_user_data, get_user_by_id

        user_id = "TEST-001"
        name = "Test User"
        role = "Tester"

        # Guardar
        result = save_user_data(user_id, name, role, sample_embedding)
        assert result is True

        # Recuperar
        user = get_user_by_id(user_id)
        assert user is not None
        assert user["name"] == name
        assert user["role"] == role

    def test_get_nonexistent_user(self):
        """Verifica que buscar un usuario que no existe retorna None."""
        from app.services.storage import get_user_by_id

        user = get_user_by_id("NO-EXISTE-99999")
        assert user is None

    def test_save_user_updates_existing(self, sample_embedding):
        """Verifica que guardar un usuario con ID existente lo actualiza."""
        from app.services.storage import save_user_data, get_user_by_id

        user_id = "TEST-UPDATE"

        save_user_data(user_id, "Nombre Original", "Rol1", sample_embedding)
        save_user_data(user_id, "Nombre Actualizado", "Rol2", sample_embedding)

        user = get_user_by_id(user_id)
        assert user["name"] == "Nombre Actualizado"
        assert user["role"] == "Rol2"


# =========================================================================
#                 TESTS DE PROCESAMIENTO DE IMAGEN
# =========================================================================

class TestImageProcessing:
    """Tests para el módulo de preprocesamiento de imagen."""

    def test_normalize_illumination(self, sample_image_base64):
        """Verifica que la normalización de iluminación funciona."""
        from app.utils.image_processing import normalize_illumination
        from app.services.face_recognition import base64_to_image

        img = base64_to_image(sample_image_base64)
        normalized = normalize_illumination(img)
        assert normalized is not None
        assert normalized.shape == img.shape

    def test_assess_quality_dark_image(self):
        """Verifica que detecta una imagen oscura."""
        from app.utils.image_processing import assess_image_quality

        dark_img = np.zeros((200, 200, 3), dtype=np.uint8)
        quality = assess_image_quality(dark_img)
        assert quality["brightness"] < 50
        assert "oscura" in " ".join(quality["issues"]).lower() or len(quality["issues"]) > 0

    def test_assess_quality_bright_image(self):
        """Verifica que detecta una imagen sobreexpuesta."""
        from app.utils.image_processing import assess_image_quality

        bright_img = np.ones((200, 200, 3), dtype=np.uint8) * 250
        quality = assess_image_quality(bright_img)
        assert quality["brightness"] > 200

    def test_decode_valid_base64(self, sample_image_base64):
        """Verifica la decodificación Base64 con validaciones."""
        from app.utils.image_processing import decode_base64_image

        img = decode_base64_image(sample_image_base64)
        assert img is not None
        assert img.shape[0] >= 100
        assert img.shape[1] >= 100


# =========================================================================
#                    TESTS DE LIVENESS
# =========================================================================

class TestLiveness:
    """Tests para el motor de anti-spoofing."""

    def test_analyze_texture_returns_dict(self, sample_image_base64):
        """Verifica que el análisis de textura retorna un resultado válido."""
        from app.services.liveness import analyze_texture
        from app.services.face_recognition import base64_to_image

        img = base64_to_image(sample_image_base64)
        result = analyze_texture(img)
        assert isinstance(result, dict)
        assert "texture_score" in result

    def test_analyze_frequency_returns_dict(self, sample_image_base64):
        """Verifica que el análisis de frecuencia retorna un resultado válido."""
        from app.services.liveness import analyze_frequency
        from app.services.face_recognition import base64_to_image

        img = base64_to_image(sample_image_base64)
        result = analyze_frequency(img)
        assert isinstance(result, dict)
        assert "frequency_score" in result

    def test_comprehensive_check_no_face(self):
        """Verifica que una imagen sin rostro falla el liveness."""
        from app.services.liveness import comprehensive_liveness_check

        black_img = np.zeros((200, 200, 3), dtype=np.uint8)
        result = comprehensive_liveness_check(black_img)
        assert result["is_live"] is False


# =========================================================================
#                    EJECUCIÓN
# =========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])