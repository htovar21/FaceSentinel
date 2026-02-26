"""
test_blockchain.py — Tests para el servicio de blockchain
Verifica la conexión, el logging de autenticaciones, y las consultas.
"""

import os
import sys
import pytest

# Ajustar path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =========================================================================
#              TESTS DE CONEXIÓN
# =========================================================================

class TestBlockchainConnection:
    """Tests para la inicialización y conexión blockchain."""

    def test_is_blockchain_available_returns_bool(self):
        """Verifica que is_blockchain_available retorna un booleano."""
        from app.services.blockchain import is_blockchain_available
        result = is_blockchain_available()
        assert isinstance(result, bool)

    def test_get_contract_info_returns_dict(self):
        """Verifica que get_contract_info retorna información válida."""
        from app.services.blockchain import get_contract_info
        info = get_contract_info()
        assert isinstance(info, dict)
        assert "connected" in info

    def test_get_total_records_returns_int(self):
        """Verifica que get_total_records retorna un entero."""
        from app.services.blockchain import get_total_records
        count = get_total_records()
        assert isinstance(count, int)
        assert count >= 0


# =========================================================================
#              TESTS DE HASHING BIOMÉTRICO
# =========================================================================

class TestBiometricHashing:
    """Tests para el hashing de datos biométricos."""

    def test_compute_biometric_hash_deterministic(self):
        """Verifica que el mismo embedding siempre produce el mismo hash."""
        from app.services.blockchain import _compute_biometric_hash

        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        hash1 = _compute_biometric_hash(embedding)
        hash2 = _compute_biometric_hash(embedding)

        assert hash1 == hash2
        assert len(hash1) == 32  # SHA-256 = 32 bytes

    def test_different_embeddings_different_hashes(self):
        """Verifica que embeddings diferentes producen hashes diferentes."""
        from app.services.blockchain import _compute_biometric_hash

        hash1 = _compute_biometric_hash([0.1, 0.2, 0.3])
        hash2 = _compute_biometric_hash([0.4, 0.5, 0.6])

        assert hash1 != hash2


# =========================================================================
#              TESTS DE LOGGING (cuando blockchain no está disponible)
# =========================================================================

class TestBlockchainGracefulDegradation:
    """Tests para verificar que el sistema funciona sin blockchain."""

    def test_log_authentication_without_blockchain(self):
        """Verifica que log_authentication no falla si blockchain no está disponible."""
        from app.services.blockchain import log_authentication

        result = log_authentication(
            user_id="TEST-001",
            access_granted=True,
            device_id="TEST-DEVICE",
            match_score=0.35,
        )

        assert isinstance(result, dict)
        assert "success" in result
        # Si blockchain no está disponible, debe retornar success=False sin excepción

    def test_get_auth_history_without_blockchain(self):
        """Verifica que get_auth_history no falla si blockchain no está disponible."""
        from app.services.blockchain import get_auth_history

        result = get_auth_history("TEST-001", count=5)

        assert isinstance(result, dict)
        assert "records" in result


# =========================================================================
#                    EJECUCIÓN
# =========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
