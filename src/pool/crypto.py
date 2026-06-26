"""Encryption/decryption for retained transaction data.

New ciphertexts use **AES-256-GCM** (pycryptodome) with a key derived from
APP_SEED via PBKDF2-HMAC-SHA256, tagged with the ``ENC:v2:`` prefix. Each
encryption uses a fresh random 12-byte nonce, so the same plaintext yields
different ciphertext, and GCM's tag authenticates it.

Legacy ``ENC:`` ciphertexts (the previous PBKDF2 + HMAC-SHA256 keystream + HMAC
scheme) remain decryptable for backwards compatibility — only decryption keeps
the v1 path; everything written from now on is v2.
"""

import base64
import hashlib
import logging
import os

from Crypto.Cipher import AES

log = logging.getLogger(__name__)

_SALT = b"broadcast-pool-v1"
_ITERATIONS = 100_000
_KEY_LEN = 32

_V2_PREFIX = "ENC:v2:"
_V1_PREFIX = "ENC:"

# AES-GCM (v2) parameters
_NONCE_LEN = 12
_TAG_LEN = 16

# Legacy (v1) parameters
_IV_LEN = 16
_MAC_LEN = 32

_derived_key: bytes | None = None


def _get_key(seed: str) -> bytes:
    """Derive the 32-byte encryption key from APP_SEED (cached)."""
    global _derived_key
    if _derived_key is None and seed:
        _derived_key = hashlib.pbkdf2_hmac(
            "sha256", seed.encode(), _SALT, _ITERATIONS, dklen=_KEY_LEN
        )
    return _derived_key or b""


def encrypt(plaintext: str, seed: str) -> str:
    """Encrypt a string with AES-256-GCM → ``ENC:v2:`` base64.

    Returns the plaintext unchanged if no seed is configured.
    """
    if not seed:
        return plaintext
    key = _get_key(seed)
    if not key:
        return plaintext

    nonce = os.urandom(_NONCE_LEN)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ct, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    # Pack: nonce || ciphertext || tag
    return _V2_PREFIX + base64.b64encode(nonce + ct + tag).decode()


def decrypt(ciphertext: str, seed: str) -> str:
    """Decrypt a value. If it has no ``ENC:`` prefix, returns it as-is.

    Dispatches by version tag — v2 (AES-GCM) is checked before v1 because
    ``ENC:v2:`` also starts with ``ENC:``.
    """
    if ciphertext.startswith(_V2_PREFIX):
        return _decrypt_v2(ciphertext, seed)
    if ciphertext.startswith(_V1_PREFIX):
        return _decrypt_v1(ciphertext, seed)
    return ciphertext  # not encrypted


def _decrypt_v2(ciphertext: str, seed: str) -> str:
    if not seed:
        log.warning("Cannot decrypt: no APP_SEED configured")
        return "[encrypted]"
    key = _get_key(seed)
    if not key:
        return "[encrypted]"
    try:
        payload = base64.b64decode(ciphertext[len(_V2_PREFIX):])
    except Exception:
        return "[corrupted]"
    if len(payload) < _NONCE_LEN + _TAG_LEN:
        return "[corrupted]"

    nonce = payload[:_NONCE_LEN]
    tag = payload[-_TAG_LEN:]
    ct = payload[_NONCE_LEN:-_TAG_LEN]
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        data = cipher.decrypt_and_verify(ct, tag)
    except (ValueError, KeyError):
        log.warning("Decryption auth failed — data tampered or wrong key")
        return "[tampered]"
    return data.decode("utf-8")


# --- Legacy v1 (HMAC-SHA256 keystream + HMAC) — decrypt-only ----------------
def _hmac(key: bytes, data: bytes) -> bytes:
    import hmac
    return hmac.new(key, data, hashlib.sha256).digest()


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    stream = b""
    counter = 0
    while len(stream) < length:
        stream += _hmac(key, iv + counter.to_bytes(4, "big"))
        counter += 1
    return stream[:length]


def _decrypt_v1(ciphertext: str, seed: str) -> str:
    if not seed:
        log.warning("Cannot decrypt: no APP_SEED configured")
        return "[encrypted]"
    key = _get_key(seed)
    if not key:
        return "[encrypted]"
    try:
        payload = base64.b64decode(ciphertext[len(_V1_PREFIX):])
    except Exception:
        return "[corrupted]"
    if len(payload) < _IV_LEN + _MAC_LEN + 1:
        return "[corrupted]"

    iv = payload[:_IV_LEN]
    ct = payload[_IV_LEN:-_MAC_LEN]
    mac = payload[-_MAC_LEN:]

    import hmac as _hmac_mod
    if not _hmac_mod.compare_digest(mac, _hmac(key, iv + ct)):
        log.warning("Decryption MAC mismatch — data corrupted or wrong key")
        return "[tampered]"

    stream = _keystream(key, iv, len(ct))
    data = bytes(a ^ b for a, b in zip(ct, stream))
    return data.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """True for both v2 (``ENC:v2:``) and legacy v1 (``ENC:``) ciphertexts."""
    return value.startswith(_V1_PREFIX)
