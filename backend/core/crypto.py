# backend/core/crypto.py
# AES-GCM 기반 공통 암호화/복호화 유틸

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.core.config import settings


AES_GCM_KEY_SIZE = 32      # 32 bytes = AES-256
AES_GCM_NONCE_SIZE = 12    # GCM 권장 nonce size

# 암호화/복호화 처리 중 발생하는 예와
class CryptoError(Exception):
    pass


# =========================
# Base64 유틸
# =========================

def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("utf-8"))


# =========================
# Key 유틸
# =========================

# env에 넣을 DATA_ENCRYPTION_MA.STER_KEY 생성용 함수
# ex. python -c "from backend.core.crypto import generate_master_key; print(generate_master_key())"
def generate_master_key() -> str:
    return _b64encode(os.urandom(AES_GCM_KEY_SIZE))

# 파일/JSON을 직접 암호화할 DEK를 생성
def generate_dek() -> bytes:
    return os.urandom(AES_GCM_KEY_SIZE)

# settings.DATA_ENCRYPTION_MASTER_KEY에서 Master Key를 가져옴
# Master Key는 base64f로 인코딩된 32 bytes 값이어야함
def get_master_key() -> bytes:
    master_key = getattr(settings, "DATA_ENCRYPTION_MASTER_KEY", None)

    if not master_key:
        raise CryptoError("DATA_ENCRYPTION_MASTER_KEY가 설정되어 있지 않습니다.")

    try:
        key = _b64decode(master_key)
    except Exception as e:
        raise CryptoError("DATA_ENCRYPTION_MASTER_KEY base64 디코딩에 실패했습니다.") from e

    if len(key) != AES_GCM_KEY_SIZE:
        raise CryptoError("DATA_ENCRYPTION_MASTER_KEY는 32 bytes여야 합니다.")

    return key


# =========================
# AES-GCM bytes 암호화/복호화
# =========================

# bytes 데이터를 AES-GCM으로 암호화
def encrypt_bytes(plain_data: bytes, key: bytes) -> dict[str, str]:
    if not isinstance(plain_data, bytes):
        raise CryptoError("plain_data는 bytes 타입이어야 합니다.")

    if len(key) != AES_GCM_KEY_SIZE:
        raise CryptoError("AES-GCM key는 32 bytes여야 합니다.")

    nonce = os.urandom(AES_GCM_NONCE_SIZE)
    aesgcm = AESGCM(key)

    ciphertext = aesgcm.encrypt(
        nonce=nonce,
        data=plain_data,
        associated_data=None,
    )

    return {
        "ciphertext": _b64encode(ciphertext),
        "nonce": _b64encode(nonce),
    }

# AES-GCM으로 암호화된 bytes 데이터를 복호화
def decrypt_bytes(ciphertext_b64: str, nonce_b64: str, key: bytes) -> bytes:
    if len(key) != AES_GCM_KEY_SIZE:
        raise CryptoError("AES-GCM key는 32 bytes여야 합니다.")

    try:
        ciphertext = _b64decode(ciphertext_b64)
        nonce = _b64decode(nonce_b64)
    except Exception as e:
        raise CryptoError("ciphertext 또는 nonce base64 디코딩에 실패했습니다.") from e

    aesgcm = AESGCM(key)

    try:
        return aesgcm.decrypt(
            nonce=nonce,
            data=ciphertext,
            associated_data=None,
        )
    except Exception as e:
        raise CryptoError("복호화에 실패했습니다. 데이터가 변조되었거나 키가 올바르지 않습니다.") from e


# =========================
# DEK 엔벨로프 암호화
# =========================

# DEK를 Master key로 암호화
def encrypt_dek(dek: bytes) -> dict[str, str]:
    master_key = get_master_key()
    encrypted = encrypt_bytes(dek, master_key)

    return {
        "encrypted_dek": encrypted["ciphertext"],
        "dek_nonce": encrypted["nonce"],
    }

# Master Key로 암호화된 DEK를 복호화
def decrypt_dek(encrypted_dek_b64: str, dek_nonce_b64: str) -> bytes:
    master_key = get_master_key()

    return decrypt_bytes(
        ciphertext_b64=encrypted_dek_b64,
        nonce_b64=dek_nonce_b64,
        key=master_key,
    )


# =========================
# JSON 암호화/복호화
# =========================

# dict/list 형태의 JSON 데이터를 암호화
def encrypt_json(data: dict[str, Any] | list[Any]) -> dict[str, Any]:
    dek = generate_dek()

    plain_json = json.dumps(
        data,
        ensure_ascii=False,
    ).encode("utf-8")

    encrypted_data = encrypt_bytes(plain_json, dek)
    encrypted_dek = encrypt_dek(dek)

    return {
        "ciphertext": encrypted_data["ciphertext"],
        "metadata": {
            "encryption": {
                "algorithm": "AES-256-GCM",
                "encrypted_dek": encrypted_dek["encrypted_dek"],
                "dek_nonce": encrypted_dek["dek_nonce"],
                "data_nonce": encrypted_data["nonce"],
                "key_version": getattr(settings, "DATA_ENCRYPTION_KEY_VERSION", "v1"),
            }
        },
    }

# encrypt_json()으로 암호화된 JSON 데이터를 복호화
def decrypt_json(ciphertext_b64: str, metadata: dict[str, Any]) -> dict[str, Any] | list[Any]:
    try:
        encryption = metadata["encryption"]
        encrypted_dek = encryption["encrypted_dek"]
        dek_nonce = encryption["dek_nonce"]
        data_nonce = encryption["data_nonce"]
    except KeyError as e:
        raise CryptoError("암호화 metadata 형식이 올바르지 않습니다.") from e

    dek = decrypt_dek(
        encrypted_dek_b64=encrypted_dek,
        dek_nonce_b64=dek_nonce,
    )

    plain_bytes = decrypt_bytes(
        ciphertext_b64=ciphertext_b64,
        nonce_b64=data_nonce,
        key=dek,
    )

    return json.loads(plain_bytes.decode("utf-8"))

# =========================
# 파일 암호화/복호화
# =========================

# 파일을 AES-GCM으로 암호화하여 output_path에 저장
def encrypt_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise CryptoError(f"암호화할 파일이 존재하지 않습니다: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    plain_data = input_path.read_bytes()

    dek = generate_dek()
    encrypted_data = encrypt_bytes(plain_data, dek)
    encrypted_dek = encrypt_dek(dek)

    output_path.write_bytes(_b64decode(encrypted_data["ciphertext"]))

    return {
        "file_path": str(output_path),
        "metadata": {
            "encryption": {
                "algorithm": "AES-256-GCM",
                "encrypted_dek": encrypted_dek["encrypted_dek"],
                "dek_nonce": encrypted_dek["dek_nonce"],
                "data_nonce": encrypted_data["nonce"],
                "key_version": getattr(settings, "DATA_ENCRYPTION_KEY_VERSION", "v1"),
            }
        },
    }

# 암호화된 파일을 복호화하여 output_path에 저장
def decrypt_file(encrypted_file_path: str | Path, output_path: str | Path, metadata: dict[str, Any]) -> str:

    encrypted_file_path = Path(encrypted_file_path)
    output_path = Path(output_path)

    if not encrypted_file_path.exists():
        raise CryptoError(f"복호화할 파일이 존재하지 않습니다: {encrypted_file_path}")

    try:
        encryption = metadata["encryption"]
        encrypted_dek = encryption["encrypted_dek"]
        dek_nonce = encryption["dek_nonce"]
        data_nonce = encryption["data_nonce"]
    except KeyError as e:
        raise CryptoError("암호화 metadata 형식이 올바르지 않습니다.") from e

    encrypted_data = encrypted_file_path.read_bytes()

    dek = decrypt_dek(
        encrypted_dek_b64=encrypted_dek,
        dek_nonce_b64=dek_nonce,
    )

    plain_data = decrypt_bytes(
        ciphertext_b64=_b64encode(encrypted_data),
        nonce_b64=data_nonce,
        key=dek,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(plain_data)

    return str(output_path)