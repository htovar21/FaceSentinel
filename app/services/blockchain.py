"""
blockchain.py — Servicio de integración con Smart Contract
Proporciona funciones para registrar eventos de autenticación en la blockchain
y consultar el historial de accesos.
"""

import json
import hashlib
import os
import logging

from web3 import Web3
from web3.exceptions import ContractLogicError
from app.core.config import settings

logger = logging.getLogger(__name__)

# =========================================================================
#                   ESTADO GLOBAL DEL SERVICIO
# =========================================================================

_w3 = None              # Instancia de Web3
_contract = None         # Instancia del contrato
_admin_account = None    # Dirección de la cuenta administradora
_private_key = None      # Llave privada para firmar transacciones
_initialized = False     # Flag de inicialización


# =========================================================================
#                         INICIALIZACIÓN
# =========================================================================

def init_blockchain():
    """
    Inicializa la conexión con la blockchain y carga el contrato.
    Se llama automáticamente al levantar el servidor.
    Si Ganache no está disponible, el sistema sigue funcionando sin blockchain.
    """
    global _w3, _contract, _admin_account, _private_key, _initialized

    # Verificar que tenemos la dirección del contrato
    if not settings.SMART_CONTRACT_ADDRESS:
        logger.warning(
            "⚠️  SMART_CONTRACT_ADDRESS no configurado. "
            "La blockchain está deshabilitada. "
            "Ejecuta 'python blockchain/deploy.py' primero."
        )
        return False

    try:
        # Conectar a la blockchain
        _w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL))

        if not _w3.is_connected():
            logger.warning(
                f"⚠️  No se pudo conectar a {settings.BLOCKCHAIN_RPC_URL}. "
                "Verifica que Ganache esté corriendo."
            )
            return False

        # Cargar ABI del contrato
        abi_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "blockchain", "artifacts", "AccessRegistry_abi.json"
        )
        abi_path = os.path.normpath(abi_path)

        if not os.path.exists(abi_path):
            logger.warning(
                f"⚠️  ABI no encontrado en {abi_path}. "
                "Ejecuta 'python blockchain/deploy.py' primero."
            )
            return False

        with open(abi_path, "r", encoding="utf-8") as f:
            abi = json.load(f)

        # Instanciar el contrato
        contract_address = Web3.to_checksum_address(settings.SMART_CONTRACT_ADDRESS)
        _contract = _w3.eth.contract(address=contract_address, abi=abi)

        # Configurar cuenta administradora
        _admin_account = os.getenv("ADMIN_ADDRESS", "")
        _private_key = os.getenv("ADMIN_PRIVATE_KEY", settings.DEVICE_PRIVATE_KEY)

        if not _admin_account or not _private_key:
            logger.warning(
                "⚠️  ADMIN_ADDRESS o ADMIN_PRIVATE_KEY no configurados. "
                "Las transacciones de escritura no funcionarán."
            )
            return False

        _initialized = True
        logger.info(
            f"✅ Blockchain inicializada — Contrato: {contract_address} | "
            f"Red: {settings.BLOCKCHAIN_RPC_URL}"
        )
        return True

    except Exception as e:
        logger.error(f"❌ Error inicializando blockchain: {e}")
        _initialized = False
        return False


def is_blockchain_available() -> bool:
    """Verifica si el servicio de blockchain está disponible."""
    return _initialized and _w3 is not None and _w3.is_connected()


# =========================================================================
#                   FUNCIONES DE ESCRITURA (TRANSACCIONES)
# =========================================================================

def _compute_biometric_hash(embedding: list) -> bytes:
    """
    Genera un hash SHA-256 del embedding facial.
    NUNCA se guarda el vector biométrico en la blockchain, solo su hash.
    Esto protege la privacidad del usuario.
    """
    embedding_str = ",".join(f"{v:.6f}" for v in embedding)
    return hashlib.sha256(embedding_str.encode()).digest()


def log_authentication(
    user_id: str,
    embedding: list = None,
    access_granted: bool = True,
    device_id: str = "API-SERVER-01",
    match_score: float = 0.0
) -> dict:
    """
    Registra un evento de autenticación en la blockchain.

    Args:
        user_id: Identificador del usuario autenticado
        embedding: Vector facial (se hashea antes de guardar, nunca se guarda raw)
        access_granted: Si el acceso fue concedido o denegado
        device_id: Identificador del punto de acceso
        match_score: Distancia coseno de la coincidencia (0.0 - 1.0)

    Returns:
        dict con tx_hash y record_id si fue exitoso, o error message si falló
    """
    if not is_blockchain_available():
        logger.warning("Blockchain no disponible. Evento no registrado en cadena.")
        return {"success": False, "message": "Blockchain no disponible", "tx_hash": None}

    try:
        # Generar hash del embedding (o un hash vacío si no se proporcionó)
        if embedding:
            bio_hash = _compute_biometric_hash(embedding)
        else:
            bio_hash = b'\x00' * 32

        # Convertir match_score a entero (x10000 para 4 decimales de precisión)
        score_int = int(match_score * 10000)

        # Construir la transacción con el chain ID real del nodo
        actual_chain_id = _w3.eth.chain_id
        nonce = _w3.eth.get_transaction_count(_admin_account)

        tx = _contract.functions.logAuthentication(
            user_id,
            bio_hash,
            access_granted,
            device_id,
            score_int
        ).build_transaction({
            "chainId": actual_chain_id,
            "gasPrice": _w3.eth.gas_price,
            "from": _admin_account,
            "nonce": nonce,
        })

        # Firmar y enviar
        signed_tx = _w3.eth.account.sign_transaction(tx, private_key=_private_key)
        tx_hash = _w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        # Esperar confirmación
        receipt = _w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

        # Obtener el recordId del evento emitido
        record_id = None
        if receipt.logs:
            try:
                event = _contract.events.AuthenticationLogged().process_receipt(receipt)
                if event:
                    record_id = event[0]['args']['recordId']
            except Exception:
                pass

        tx_hash_hex = tx_hash.hex()
        logger.info(
            f"🔗 Autenticación registrada en blockchain — "
            f"TX: {tx_hash_hex} | Usuario: {user_id} | "
            f"Acceso: {'✅' if access_granted else '❌'}"
        )

        return {
            "success": True,
            "tx_hash": tx_hash_hex,
            "record_id": record_id,
            "block_number": receipt.blockNumber,
            "gas_used": receipt.gasUsed,
        }

    except ContractLogicError as e:
        logger.error(f"Error de lógica del contrato: {e}")
        return {"success": False, "message": str(e), "tx_hash": None}
    except Exception as e:
        logger.error(f"Error registrando en blockchain: {e}")
        return {"success": False, "message": str(e), "tx_hash": None}


# =========================================================================
#                    FUNCIONES DE LECTURA (CONSULTAS)
# =========================================================================

def get_auth_history(user_id: str, count: int = 10) -> dict:
    """
    Consulta el historial de autenticaciones de un usuario en la blockchain.

    Args:
        user_id: Identificador del usuario
        count: Número máximo de registros recientes a retornar

    Returns:
        dict con lista de registros o mensaje de error
    """
    if not is_blockchain_available():
        return {"success": False, "message": "Blockchain no disponible", "records": []}

    try:
        # Obtener los registros más recientes del usuario
        records_raw = _contract.functions.getRecentRecordsByUser(user_id, count).call()

        records = []
        for r in records_raw:
            records.append({
                "user_id": r[0],
                "biometric_hash": "0x" + r[1].hex(),
                "timestamp": r[2],
                "access_granted": r[3],
                "device_id": r[4],
                "match_score": r[5] / 10000.0,  # Reconvertir a float
            })

        logger.info(f"📋 Historial consultado para {user_id}: {len(records)} registros")

        return {
            "success": True,
            "user_id": user_id,
            "total_records": len(records),
            "records": records,
        }

    except Exception as e:
        logger.error(f"Error consultando historial: {e}")
        return {"success": False, "message": str(e), "records": []}


def get_total_records() -> int:
    """Obtiene el número total de registros en el contrato."""
    if not is_blockchain_available():
        return 0
    try:
        return _contract.functions.totalRecords().call()
    except Exception:
        return 0


def get_contract_info() -> dict:
    """Retorna información general del contrato y la conexión."""
    if not is_blockchain_available():
        return {
            "connected": False,
            "message": "Blockchain no disponible"
        }

    try:
        return {
            "connected": True,
            "contract_address": settings.SMART_CONTRACT_ADDRESS,
            "network": settings.BLOCKCHAIN_RPC_URL,
            "chain_id": settings.CHAIN_ID,
            "total_records": _contract.functions.totalRecords().call(),
            "admin_address": _admin_account,
            "block_number": _w3.eth.block_number,
        }
    except Exception as e:
        return {
            "connected": False,
            "message": str(e)
        }
