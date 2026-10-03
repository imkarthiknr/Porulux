from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class KeyVaultError(RuntimeError):
    pass


def _fernet() -> Fernet:
    secret = os.getenv("KEY_ENCRYPTION_SECRET")
    if not secret:
        raise KeyVaultError("KEY_ENCRYPTION_SECRET is not configured")
    try:
        return Fernet(secret.encode())
    except ValueError as exc:
        raise KeyVaultError("KEY_ENCRYPTION_SECRET is not a valid Fernet key") from exc


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise KeyVaultError("Stored key cannot be decrypted (was the encryption secret rotated?)") from exc


def last4(key: str) -> str:
    return key[-4:]
