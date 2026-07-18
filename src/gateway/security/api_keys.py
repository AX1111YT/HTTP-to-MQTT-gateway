from __future__ import annotations

import hashlib
import logging
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def compute_lookup_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def hash_api_key(raw_key: str) -> str:
    return _hasher.hash(raw_key)


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, raw_key)
    except VerifyMismatchError:
        return False
