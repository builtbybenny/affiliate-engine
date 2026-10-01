"""Fernet helpers: store the Meta token encrypted inside the repo for CI.

The Fernet key lives only in GitHub Actions secrets / your local .env, so the
committed data/token.enc is useless to anyone without the key.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encrypt_to_file(plaintext: str, dest: Path, key: str) -> Path:
    f = Fernet(key.encode())
    dest.write_bytes(f.encrypt(plaintext.encode()))
    return dest


def decrypt_from_file(src: Path, key: str) -> str:
    f = Fernet(key.encode())
    return f.decrypt(src.read_bytes()).decode()
