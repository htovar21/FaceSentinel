"""
deploy.py — Script de despliegue del Smart Contract AccessRegistry
Compila el contrato Solidity y lo despliega en Ganache (o cualquier red Ethereum).
Guarda el ABI y la dirección del contrato en blockchain/artifacts/.
"""

import json
import os
import sys
import time

from solcx import compile_standard, install_solc
from web3 import Web3
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# =========================================================================
#                          CONFIGURACIÓN
# =========================================================================

# Red blockchain (Ganache por defecto)
WEB3_PROVIDER_URI = os.getenv("WEB3_PROVIDER_URI", "http://127.0.0.1:7545")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS") or "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1"
ADMIN_PRIVATE_KEY = os.getenv("ADMIN_PRIVATE_KEY") or "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
# CHAIN_ID se autodetecta del nodo conectado para evitar el error de mismatch
CHAIN_ID = None  # Se llenará en deploy_contract()

# Rutas de archivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTRACT_PATH = os.path.join(BASE_DIR, "contracts", "AccessRegistry.sol")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")

# Versión de Solidity a usar
SOLC_VERSION = "0.8.19"


def compile_contract():
    """Compila el contrato Solidity y retorna el ABI y bytecode."""
    print("📦 Instalando compilador Solidity", SOLC_VERSION, "...")
    install_solc(SOLC_VERSION)

    print("📄 Leyendo contrato desde:", CONTRACT_PATH)
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        contract_source = f.read()

    print("⚙️  Compilando AccessRegistry.sol ...")
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {
                "AccessRegistry.sol": {"content": contract_source}
            },
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                    }
                },
                "optimizer": {
                    "enabled": True,
                    "runs": 200
                }
            },
        },
        solc_version=SOLC_VERSION,
    )

    contract_data = compiled["contracts"]["AccessRegistry.sol"]["AccessRegistry"]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]

    print("✅ Compilación exitosa.")
    return abi, bytecode


def deploy_contract(abi, bytecode):
    """Despliega el contrato en la blockchain y retorna la dirección."""
    print(f"\n🔗 Conectando a la blockchain: {WEB3_PROVIDER_URI}")
    w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))

    if not w3.is_connected():
        print("❌ ERROR: No se pudo conectar a la blockchain.")
        print("   Asegúrate de que Ganache esté corriendo en", WEB3_PROVIDER_URI)
        sys.exit(1)

    print("✅ Conectado a la blockchain.")
    
    # Autodetectar el chain ID real del nodo (evita el error de mismatch)
    actual_chain_id = w3.eth.chain_id
    print(f"   Chain ID detectado: {actual_chain_id}")
    print(f"   Cuenta admin: {ADMIN_ADDRESS}")

    # Verificar balance
    balance = w3.eth.get_balance(ADMIN_ADDRESS)
    balance_eth = w3.from_wei(balance, "ether")
    print(f"   Balance: {balance_eth} ETH")

    if balance == 0:
        print("❌ ERROR: La cuenta admin no tiene fondos.")
        sys.exit(1)

    # Crear la transacción de despliegue
    print("\n🚀 Desplegando contrato AccessRegistry ...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    # Obtener el nonce actual de la cuenta
    nonce = w3.eth.get_transaction_count(ADMIN_ADDRESS)

    # Construir la transacción
    tx = contract.constructor().build_transaction({
        "chainId": actual_chain_id,  # Usar el chain ID real del nodo
        "gasPrice": w3.eth.gas_price,
        "from": ADMIN_ADDRESS,
        "nonce": nonce,
    })

    # Firmar con la llave privada
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=ADMIN_PRIVATE_KEY)

    # Enviar la transacción
    t0_deploy = time.perf_counter()
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"   TX Hash: {tx_hash.hex()}")

    # Esperar confirmación
    print("   Esperando confirmación ...")
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    deploy_time_ms = (time.perf_counter() - t0_deploy) * 1000.0

    contract_address = tx_receipt.contractAddress
    print(f"\n🎉 ¡Contrato desplegado exitosamente!")
    print(f"   Dirección del contrato: {contract_address}")
    print(f"   Gas usado: {tx_receipt.gasUsed}")
    print(f"   Bloque: {tx_receipt.blockNumber}")
    print(f"   Tiempo de despliegue: {deploy_time_ms:.1f} ms")

    deploy_metrics = {
        "tx_hash": tx_hash.hex(),
        "gas_used": tx_receipt.gasUsed,
        "block_number": tx_receipt.blockNumber,
        "deploy_time_ms": round(deploy_time_ms, 2)
    }

    return contract_address, actual_chain_id, deploy_metrics


def save_artifacts(abi, contract_address, chain_id, bytecode=None, deploy_metrics=None):
    """Guarda el ABI, el bytecode, métricas de gas y la dirección del contrato en archivos JSON."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # Guardar ABI
    abi_path = os.path.join(ARTIFACTS_DIR, "AccessRegistry_abi.json")
    with open(abi_path, "w", encoding="utf-8") as f:
        json.dump(abi, f, indent=2)
    print(f"\n💾 ABI guardado en: {abi_path}")

    # Guardar Build completo (ABI + Bytecode) si está disponible
    if bytecode:
        build_path = os.path.join(ARTIFACTS_DIR, "AccessRegistry_build.json")
        with open(build_path, "w", encoding="utf-8") as f:
            json.dump({"abi": abi, "bytecode": bytecode}, f, indent=2)
        print(f"💾 Build compilado guardado en: {build_path}")

    # Guardar información del despliegue
    deploy_info = {
        "contract_address": contract_address,
        "network": WEB3_PROVIDER_URI,
        "chain_id": chain_id,
        "admin_address": ADMIN_ADDRESS,
        "deployment_metrics": deploy_metrics or {}
    }
    info_path = os.path.join(ARTIFACTS_DIR, "deploy_info.json")
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(deploy_info, f, indent=2)
    print(f"💾 Info de despliegue guardada en: {info_path}")

    # Actualizar el .env con la dirección del contrato
    update_env_file(contract_address)


def update_env_file(contract_address):
    """Actualiza el archivo .env con la dirección del contrato desplegado."""
    env_path = os.path.join(BASE_DIR, "..", ".env")

    if not os.path.exists(env_path):
        print("⚠️  No se encontró archivo .env para actualizar.")
        return

    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Reemplazar la línea del SMART_CONTRACT_ADDRESS
    lines = content.split("\n")
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("SMART_CONTRACT_ADDRESS"):
            lines[i] = f'SMART_CONTRACT_ADDRESS="{contract_address}"'
            updated = True
            break

    if updated:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"📝 .env actualizado con SMART_CONTRACT_ADDRESS={contract_address}")
    else:
        print("⚠️  No se encontró SMART_CONTRACT_ADDRESS en .env")


# =========================================================================
#                          EJECUCIÓN PRINCIPAL
# =========================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  FaceSentinel — Despliegue de Smart Contract")
    print("=" * 60)

    # Paso 1: Compilar
    abi, bytecode = compile_contract()

    # Paso 2: Desplegar (retorna dirección, chain ID y métricas de despliegue)
    contract_address, detected_chain_id, deploy_metrics = deploy_contract(abi, bytecode)

    # Paso 3: Guardar artefactos
    save_artifacts(abi, contract_address, detected_chain_id, bytecode=bytecode, deploy_metrics=deploy_metrics)

    print("\n" + "=" * 60)
    print("  ✅ Despliegue completado exitosamente")
    print("=" * 60)
    print(f"\n  Contrato: {contract_address}")
    print(f"  Red:      {WEB3_PROVIDER_URI}")
    print(f"  Chain ID: {detected_chain_id}")
    print("\n  Próximo paso: Iniciar el servidor con 'uvicorn app.main:app --reload'")
