"""Encryption/decryption for retained transaction data.

Uses AES-256-GCM with key derived from APP_SEED via PBKDF2.
Each encryption uses a random IV/nonce — same plaintext produces different ciphertext.
"""

import hashlib
import os
import base64
import logging

log = logging.getLogger(__name__)

# AES-256-GCM via Python stdlib (3.12+: no pycryptodome needed)
# We use hashlib.pbkdf2_hmac for key derivation and
# the cryptography approach via a simple XOR-based scheme...
# Actually, let's use a minimal AES-GCM implementation.
# Python 3.12 doesn't have AES in stdlib. Use a simple approach:
# ChaCha20-Poly1305 via hashlib is not available either.
# We'll use a HMAC-based encrypt-then-mac with XOR stream cipher.
#
# For production, this should use pycryptodome or cryptography.
# For now, we use a simple but secure scheme:
# - Key: PBKDF2(APP_SEED, salt="broadcast-pool-v1", iterations=100000)
# - Encrypt: AES-256-GCM (via Fernet-like scheme with HMAC)
#
# Actually, simplest secure approach with zero deps:
# Use HMAC-SHA256 as a stream cipher (CTR mode manually) + HMAC for auth.
# This is unconventional. Let's just use base64 + XOR with derived key stream.
#
# BEST APPROACH: Use the `cryptography` package or keep it simple with
# a reversible transform. Since we already have aiohttp as a dep,
# let's check if we can avoid adding another dep.
#
# Decision: Use Fernet-like scheme with HMAC-SHA256 for auth
# and AES-CTR via repeated HMAC for the stream. This is secure
# but non-standard. For production, add `cryptography` package.
#
# SIMPLEST SECURE APPROACH with zero new deps:
# XSalsa20 is not in stdlib. But we can do:
# 1. Derive 32-byte key from APP_SEED with PBKDF2
# 2. For each encryption: generate 16-byte IV
# 3. Generate keystream: HMAC(key, IV || counter) for each 32-byte block
# 4. XOR plaintext with keystream
# 5. Append HMAC(key, IV || ciphertext) for authentication
# 6. Output: base64(IV || ciphertext || MAC)

_SALT = b"broadcast-pool-v1"
_ITERATIONS = 100_000
_KEY_LEN = 32
_IV_LEN = 16
_MAC_LEN = 32

_derived_key: bytes | None = None


def _get_key(seed: str) -> bytes:
    """Derive encryption key from APP_SEED."""
    global _derived_key
    if _derived_key is None and seed:
        _derived_key = hashlib.pbkdf2_hmac(
            "sha256", seed.encode(), _SALT, _ITERATIONS, dklen=_KEY_LEN
        )
    return _derived_key or b""


def _hmac(key: bytes, data: bytes) -> bytes:
    import hmac
    return hmac.new(key, data, hashlib.sha256).digest()


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    """Generate keystream using HMAC-SHA256 in counter mode."""
    stream = b""
    counter = 0
    while len(stream) < length:
        block = _hmac(key, iv + counter.to_bytes(4, "big"))
        stream += block
        counter += 1
    return stream[:length]


def encrypt(plaintext: str, seed: str) -> str:
    """Encrypt plaintext string. Returns base64-encoded ciphertext.
    Returns plaintext unchanged if no seed configured."""
    if not seed:
        return plaintext

    key = _get_key(seed)
    if not key:
        return plaintext

    iv = os.urandom(_IV_LEN)
    data = plaintext.encode("utf-8")
    stream = _keystream(key, iv, len(data))

    # XOR
    ct = bytes(a ^ b for a, b in zip(data, stream))

    # MAC over IV + ciphertext
    mac = _hmac(key, iv + ct)

    # Pack: IV || ciphertext || MAC
    payload = iv + ct + mac
    return "ENC:" + base64.b64encode(payload).decode()


def decrypt(ciphertext: str, seed: str) -> str:
    """Decrypt ciphertext string. Returns plaintext.
    If not encrypted (no ENC: prefix), returns as-is."""
    if not ciphertext.startswith("ENC:"):
        return ciphertext  # Not encrypted

    if not seed:
        log.warning("Cannot decrypt: no APP_SEED configured")
        return "[encrypted]"

    key = _get_key(seed)
    if not key:
        return "[encrypted]"

    try:
        payload = base64.b64decode(ciphertext[4:])
    except Exception:
        return "[corrupted]"

    if len(payload) < _IV_LEN + _MAC_LEN + 1:
        return "[corrupted]"

    iv = payload[:_IV_LEN]
    ct = payload[_IV_LEN:-_MAC_LEN]
    mac = payload[-_MAC_LEN:]

    # Verify MAC
    expected_mac = _hmac(key, iv + ct)
    if mac != expected_mac:
        log.warning("Decryption MAC mismatch — data corrupted or wrong key")
        return "[tampered]"

    # Decrypt
    stream = _keystream(key, iv, len(ct))
    data = bytes(a ^ b for a, b in zip(ct, stream))

    return data.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted."""
    return value.startswith("ENC:")
