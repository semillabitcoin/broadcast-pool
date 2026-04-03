"""NIP-44 v2 encryption for Nostr.

Encrypts data using an ephemeral keypair + recipient's npub.
The server never stores the ephemeral private key — it cannot decrypt after encryption.

Dependencies: secp256k1, pycryptodome, bech32
"""

import hashlib
import hmac
import json
import logging
import os
import struct
from base64 import b64encode

import bech32
import secp256k1
from Crypto.Cipher import ChaCha20

log = logging.getLogger(__name__)

_SALT = b"nip44-v2"


def npub_to_hex(npub: str) -> str:
    """Decode npub1... bech32 to 32-byte hex pubkey."""
    hrp, data_words = bech32.bech32_decode(npub)
    if hrp != "npub" or data_words is None:
        raise ValueError(f"Invalid npub: {npub[:20]}...")
    pub_bytes = bytes(bech32.convertbits(data_words, 5, 8, False))
    if len(pub_bytes) != 32:
        raise ValueError(f"Invalid npub length: {len(pub_bytes)} bytes")
    return pub_bytes.hex()


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract: PRK = HMAC-Hash(salt, IKM)"""
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand: output key material of given length."""
    output = b""
    t = b""
    counter = 1
    while len(output) < length:
        t = hmac.new(prk, t + info + struct.pack("B", counter), hashlib.sha256).digest()
        output += t
        counter += 1
    return output[:length]


def _get_conversation_key(priv_bytes: bytes, pub_hex: str) -> bytes:
    """ECDH secp256k1 + HKDF-extract with NIP-44 salt."""
    # Create private key
    privkey = secp256k1.PrivateKey(priv_bytes)

    # Create public key from hex (add 02 prefix for compressed format)
    pub_compressed = bytes.fromhex("02" + pub_hex)
    pubkey = secp256k1.PublicKey(pub_compressed, raw=True)

    # ECDH: multiply pubkey by privkey, get x-coordinate
    shared_point = pubkey.tweak_mul(priv_bytes)
    shared_x = shared_point.serialize()[1:33]  # x-coordinate only

    # HKDF-extract
    return _hkdf_extract(_SALT, shared_x)


def _calc_padded_len(unpadded_len: int) -> int:
    """NIP-44 padding: next power of 2, minimum 32."""
    if unpadded_len <= 32:
        return 32
    next_pow = 1
    while next_pow < unpadded_len:
        next_pow <<= 1
    chunk = max(32, next_pow // 8)
    return chunk * ((unpadded_len + chunk - 1) // chunk)


def encrypt_nip44(plaintext: str, conv_key: bytes) -> str:
    """NIP-44 v2 encrypt. Returns base64 payload."""
    # 32-byte random nonce
    nonce = os.urandom(32)

    # HKDF-expand to get chacha_key(32) + chacha_nonce(12) + hmac_key(32) = 76 bytes
    keys = _hkdf_expand(conv_key, nonce, 76)
    chacha_key = keys[0:32]
    chacha_nonce = keys[32:44]
    hmac_key = keys[44:76]

    # Pad plaintext
    plaintext_bytes = plaintext.encode("utf-8")
    unpadded_len = len(plaintext_bytes)
    padded_len = _calc_padded_len(unpadded_len)
    padded = struct.pack(">H", unpadded_len) + plaintext_bytes + b"\x00" * (padded_len - unpadded_len)

    # ChaCha20 encrypt
    cipher = ChaCha20.new(key=chacha_key, nonce=chacha_nonce)
    ciphertext = cipher.encrypt(padded)

    # HMAC-SHA256 over nonce + ciphertext
    mac = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()

    # Payload: version(1) + nonce(32) + ciphertext + mac(32)
    payload = b"\x02" + nonce + ciphertext + mac
    return b64encode(payload).decode()


def encrypt_for_npub(data: dict, npub: str) -> dict:
    """Encrypt a dict for the owner of an npub. Returns {ephem_pubkey, payload}.

    Uses ephemeral keypair — the server cannot decrypt after this function returns.
    """
    recipient_hex = npub_to_hex(npub)

    # Generate ephemeral keypair
    eph_secret = os.urandom(32)
    eph_privkey = secp256k1.PrivateKey(eph_secret)
    eph_pubkey_bytes = eph_privkey.pubkey.serialize()  # 33 bytes compressed
    eph_pubkey_hex = eph_pubkey_bytes[1:].hex()  # x-only (32 bytes)

    # Derive conversation key
    conv_key = _get_conversation_key(eph_secret, recipient_hex)

    # Encrypt
    plaintext = json.dumps(data, ensure_ascii=False)
    payload = encrypt_nip44(plaintext, conv_key)

    # DISCARD ephemeral secret — cannot decrypt after this
    del eph_secret

    log.debug("Encrypted vault entry for npub %s... (payload %d bytes)",
              npub[:20], len(payload))

    return {
        "ephem_pubkey": eph_pubkey_hex,
        "payload": payload,
    }
