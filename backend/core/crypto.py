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

# 암호화/복호화 처리 중 발생하는 예외
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
# Metadata 유틸
# =========================

# 암호화 metadata에서 복호화에 필요한 값을 검증 후 반환한다.
# metadata가 None이거나 형식이 올바르지 않은 경우에도
# TypeError/KeyError가 밖으로 새어나가지 않도록 CryptoError로 변환한다.
# decrypt_json / decrypt_file에서 공통으로 사용한다.
def _get_encryption_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    try:
        encryption = metadata["encryption"]
        encrypted_dek = encryption["encrypted_dek"]
        dek_nonce = encryption["dek_nonce"]
        data_nonce = encryption["data_nonce"]
        key_version = encryption["key_version"]
    except (KeyError, TypeError) as e:
        raise CryptoError("암호화 metadata 형식이 올바르지 않습니다.") from e

    return {
        "encrypted_dek": encrypted_dek,
        "dek_nonce": dek_nonce,
        "data_nonce": data_nonce,
        "key_version": key_version,
    }


# =========================
# Key 유틸
# =========================

# env에 넣을 DATA_ENCRYPTION_MASTER_KEY 생성용 함수
# ex. python -c "from backend.core.crypto import generate_master_key; print(generate_master_key())"
def generate_master_key() -> str:
    return _b64encode(os.urandom(AES_GCM_KEY_SIZE))

# 파일/JSON을 직접 암호화할 DEK를 생성
def generate_dek() -> bytes:
    return os.urandom(AES_GCM_KEY_SIZE)


def _get_current_key_version() -> str:
    return getattr(settings, "DATA_ENCRYPTION_KEY_VERSION", "v1")


# settings에서 버전별 Master Key 목록을 가져옴.
# 마스터 키 로테이션을 지원하기 위해 여러 버전의 키를 동시에 보관할 수 있어야 함.
#
# settings.DATA_ENCRYPTION_MASTER_KEYS는 config.py에서 이미
# {"v1": "base64...", "v2": "base64..."} 형태의 dict로 파싱되어 들어온다.
# 이 값이 비어 있을 때만 하위호환을 위해 settings.DATA_ENCRYPTION_MASTER_KEY(단일 키)를
# 현재 버전(DATA_ENCRYPTION_KEY_VERSION)의 키로 취급한다.
def _load_master_keys() -> dict[str, str]:
    keys = getattr(settings, "DATA_ENCRYPTION_MASTER_KEYS", None)
    if keys:
        return dict(keys)

    legacy_key = getattr(settings, "DATA_ENCRYPTION_MASTER_KEY", None)
    if legacy_key:
        return {_get_current_key_version(): legacy_key}

    return {}


# key_version에 해당하는 Master Key를 가져옴.
# key_version을 명시하지 않으면 현재 활성 버전(DATA_ENCRYPTION_KEY_VERSION)의 키를 반환한다.
# Master Key는 base64로 인코딩된 32 bytes 값이어야 한다.
def get_master_key(key_version: str | None = None) -> bytes:
    if key_version is None:
        key_version = _get_current_key_version()

    master_keys = _load_master_keys()

    if not master_keys:
        raise CryptoError("DATA_ENCRYPTION_MASTER_KEY(S)가 설정되어 있지 않습니다.")

    master_key = master_keys.get(key_version)
    if not master_key:
        raise CryptoError(
            f"key_version '{key_version}'에 해당하는 마스터 키를 찾을 수 없습니다. "
            "마스터 키 로테이션 이후 이전 버전 키가 삭제되지 않았는지 확인하세요."
        )

    try:
        key = _b64decode(master_key)
    except Exception as e:
        raise CryptoError(
            f"key_version '{key_version}' 마스터 키의 base64 디코딩에 실패했습니다."
        ) from e

    if len(key) != AES_GCM_KEY_SIZE:
        raise CryptoError(f"key_version '{key_version}' 마스터 키는 32 bytes여야 합니다.")

    return key


# =========================
# AES-GCM bytes 암호화/복호화
# =========================

# raw bytes 기준으로 AES-GCM 암호화를 수행하는 내부 헬퍼.
# JSON/DEK처럼 base64 문자열로 다뤄야 하는 곳은 encrypt_bytes()를,
# 파일처럼 큰 raw bytes를 그대로 다뤄야 하는 곳(encrypt_file)은 이 함수를 직접 사용해
# 불필요한 base64 인코딩/디코딩 왕복을 피한다.
def _encrypt_raw(plain_data: bytes, key: bytes) -> tuple[bytes, bytes]:
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

    return ciphertext, nonce

# raw bytes 기준으로 AES-GCM 복호화를 수행하는 내부 헬퍼. (_encrypt_raw와 대칭)
def _decrypt_raw(ciphertext: bytes, nonce: bytes, key: bytes) -> bytes:
    if len(key) != AES_GCM_KEY_SIZE:
        raise CryptoError("AES-GCM key는 32 bytes여야 합니다.")

    aesgcm = AESGCM(key)

    try:
        return aesgcm.decrypt(
            nonce=nonce,
            data=ciphertext,
            associated_data=None,
        )
    except Exception as e:
        raise CryptoError("복호화에 실패했습니다. 데이터가 변조되었거나 키가 올바르지 않습니다.") from e


# bytes 데이터를 AES-GCM으로 암호화 (ciphertext/nonce를 base64 문자열로 반환)
def encrypt_bytes(plain_data: bytes, key: bytes) -> dict[str, str]:
    ciphertext, nonce = _encrypt_raw(plain_data, key)

    return {
        "ciphertext": _b64encode(ciphertext),
        "nonce": _b64encode(nonce),
    }

# AES-GCM으로 암호화된 bytes 데이터를 복호화 (ciphertext/nonce는 base64 문자열로 입력받음)
def decrypt_bytes(ciphertext_b64: str, nonce_b64: str, key: bytes) -> bytes:
    try:
        ciphertext = _b64decode(ciphertext_b64)
        nonce = _b64decode(nonce_b64)
    except Exception as e:
        raise CryptoError("ciphertext 또는 nonce base64 디코딩에 실패했습니다.") from e

    return _decrypt_raw(ciphertext, nonce, key)


# =========================
# DEK 엔벨로프 암호화
# =========================

# DEK를 현재 활성 버전의 Master key로 암호화하고, 사용된 key_version을 함께 반환한다.
# 복호화 시 어떤 버전의 마스터 키를 써야 하는지 알 수 있어야 로테이션이 가능하다.
def encrypt_dek(dek: bytes) -> dict[str, str]:
    key_version = _get_current_key_version()
    master_key = get_master_key(key_version)
    encrypted = encrypt_bytes(dek, master_key)

    return {
        "encrypted_dek": encrypted["ciphertext"],
        "dek_nonce": encrypted["nonce"],
        "key_version": key_version,
    }

# Master Key로 암호화된 DEK를 복호화.
# key_version을 반드시 지정해 "암호화 당시" 사용된 마스터 키로 복호화한다.
# (마스터 키가 로테이션되어 현재 활성 버전이 바뀌어도 과거 데이터를 복호화할 수 있어야 하기 때문)
def decrypt_dek(encrypted_dek_b64: str, dek_nonce_b64: str, key_version: str) -> bytes:
    if not key_version:
        raise CryptoError("DEK 복호화에는 key_version이 반드시 필요합니다.")

    master_key = get_master_key(key_version)

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
                "key_version": encrypted_dek["key_version"],
            }
        },
    }

# encrypt_json()으로 암호화된 JSON 데이터를 복호화
def decrypt_json(ciphertext_b64: str, metadata: dict[str, Any]) -> dict[str, Any] | list[Any]:
    encryption = _get_encryption_metadata(metadata)

    dek = decrypt_dek(
        encrypted_dek_b64=encryption["encrypted_dek"],
        dek_nonce_b64=encryption["dek_nonce"],
        key_version=encryption["key_version"],
    )

    plain_bytes = decrypt_bytes(
        ciphertext_b64=ciphertext_b64,
        nonce_b64=encryption["data_nonce"],
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
    # 파일 raw bytes는 _encrypt_raw로 바로 암호화해서 그대로 기록한다.
    # encrypt_bytes()를 쓰면 ciphertext를 base64로 인코딩했다가 다시 디코딩해서
    # 파일에 쓰는 불필요한 왕복이 생긴다 (대용량 파일일수록 비용 증가).
    ciphertext, data_nonce = _encrypt_raw(plain_data, dek)
    encrypted_dek = encrypt_dek(dek)

    output_path.write_bytes(ciphertext)

    return {
        "file_path": str(output_path),
        "metadata": {
            "encryption": {
                "algorithm": "AES-256-GCM",
                "encrypted_dek": encrypted_dek["encrypted_dek"],
                "dek_nonce": encrypted_dek["dek_nonce"],
                "data_nonce": _b64encode(data_nonce),
                "key_version": encrypted_dek["key_version"],
            }
        },
    }

# 암호화된 파일을 복호화하여 output_path에 저장
def decrypt_file(encrypted_file_path: str | Path, output_path: str | Path, metadata: dict[str, Any]) -> str:

    encrypted_file_path = Path(encrypted_file_path)
    output_path = Path(output_path)

    if not encrypted_file_path.exists():
        raise CryptoError(f"복호화할 파일이 존재하지 않습니다: {encrypted_file_path}")

    encryption = _get_encryption_metadata(metadata)

    ciphertext = encrypted_file_path.read_bytes()

    dek = decrypt_dek(
        encrypted_dek_b64=encryption["encrypted_dek"],
        dek_nonce_b64=encryption["dek_nonce"],
        key_version=encryption["key_version"],
    )

    # 파일 raw bytes는 _decrypt_raw로 바로 복호화한다.
    # decrypt_bytes()를 쓰려면 이미 읽어들인 raw bytes를 base64 문자열로
    # 인코딩했다가 함수 내부에서 다시 디코딩하는 불필요한 왕복이 생긴다.
    try:
        data_nonce_bytes = _b64decode(encryption["data_nonce"])
    except Exception as e:
        raise CryptoError("data_nonce base64 디코딩에 실패했습니다.") from e

    plain_data = _decrypt_raw(ciphertext, data_nonce_bytes, dek)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(plain_data)

    return str(output_path)