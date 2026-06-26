"""Tests for at-rest encryption: AES-GCM v2 + legacy v1 backwards compatibility."""
import base64
import os

import pytest

from src.pool import crypto

SEED = "test-app-seed-0123456789"
PLAINTEXT = "0200000000010199deadbeef" * 8  # a raw-hex-shaped payload


@pytest.fixture(autouse=True)
def _reset_key_cache():
    # _get_key caches the derived key globally; reset around each test so
    # different seeds don't bleed through the cache.
    crypto._derived_key = None
    yield
    crypto._derived_key = None


def _make_v1(plaintext: str, seed: str) -> str:
    """Build a legacy v1 ciphertext (the pre-v2 HMAC-CTR scheme)."""
    crypto._derived_key = None
    key = crypto._get_key(seed)
    iv = os.urandom(crypto._IV_LEN)
    data = plaintext.encode("utf-8")
    stream = crypto._keystream(key, iv, len(data))
    ct = bytes(a ^ b for a, b in zip(data, stream))
    mac = crypto._hmac(key, iv + ct)
    crypto._derived_key = None
    return crypto._V1_PREFIX + base64.b64encode(iv + ct + mac).decode()


def test_encrypt_uses_v2_prefix():
    out = crypto.encrypt(PLAINTEXT, SEED)
    assert out.startswith("ENC:v2:")
    assert crypto.is_encrypted(out)


def test_v2_roundtrip():
    blob = crypto.encrypt(PLAINTEXT, SEED)
    assert crypto.decrypt(blob, SEED) == PLAINTEXT


def test_v2_is_randomized():
    a = crypto.encrypt(PLAINTEXT, SEED)
    b = crypto.encrypt(PLAINTEXT, SEED)
    assert a != b  # fresh nonce each time
    assert crypto.decrypt(a, SEED) == crypto.decrypt(b, SEED) == PLAINTEXT


def test_no_seed_is_passthrough():
    assert crypto.encrypt(PLAINTEXT, "") == PLAINTEXT
    assert crypto.decrypt(PLAINTEXT, "") == PLAINTEXT  # no prefix → as-is


def test_legacy_v1_still_decrypts():
    v1 = _make_v1(PLAINTEXT, SEED)
    assert v1.startswith("ENC:") and not v1.startswith("ENC:v2:")
    assert crypto.is_encrypted(v1)
    assert crypto.decrypt(v1, SEED) == PLAINTEXT


def test_v2_tamper_detected():
    blob = crypto.encrypt(PLAINTEXT, SEED)
    raw = bytearray(base64.b64decode(blob[len("ENC:v2:"):]))
    raw[-1] ^= 0x01  # flip a tag bit
    tampered = "ENC:v2:" + base64.b64encode(bytes(raw)).decode()
    assert crypto.decrypt(tampered, SEED) == "[tampered]"


def test_v2_wrong_seed_fails_closed():
    blob = crypto.encrypt(PLAINTEXT, "seed-A-aaaaaaaaaaaaaaaa")
    crypto._derived_key = None  # force re-derive with the wrong seed
    assert crypto.decrypt(blob, "seed-B-bbbbbbbbbbbbbbbb") == "[tampered]"


def test_not_encrypted_passthrough():
    assert not crypto.is_encrypted(PLAINTEXT)
    assert crypto.decrypt(PLAINTEXT, SEED) == PLAINTEXT
