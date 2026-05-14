"""Pool export/import — serialize active retained txs and encrypt for backup.

Two encryption methods supported:
- NIP-44 v2: encrypt with the user's Nostr npub (decrypt requires their nsec via NIP-07)
- passphrase: AES-256-GCM with key derived via scrypt (decrypt with the same passphrase)

The cleartext payload is JSON containing every tx needed to restore the pool
without re-signing on the wallet.
"""

import hashlib
import json
import logging
import os
from base64 import b64decode, b64encode
from datetime import datetime, timezone

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt

from src.pool.nip44 import encrypt_for_npub

log = logging.getLogger(__name__)

EXPORT_VERSION = 1
SCRYPT_N = 2 ** 17   # 131072, ~128 MB RAM; balances security and UX
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32    # 256-bit key for AES-256
SALT_LEN = 16
NONCE_LEN = 12       # AES-GCM standard


def build_payload(txs_data: list[dict], network: str) -> dict:
    """Build the cleartext payload that will be encrypted."""
    return {
        "version": EXPORT_VERSION,
        "network": network,
        "txs": txs_data,
    }


def encrypt_passphrase(payload: dict, passphrase: str) -> dict:
    """Encrypt the payload with AES-256-GCM, key from scrypt(passphrase, salt)."""
    if not passphrase:
        raise ValueError("passphrase is empty")
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = scrypt(passphrase.encode("utf-8"), salt, key_len=SCRYPT_DKLEN,
                 N=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return {
        "encryption": "passphrase",
        "encryption_meta": {
            "kdf": "scrypt",
            "kdf_params": {"N": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "dklen": SCRYPT_DKLEN},
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "tag": tag.hex(),
        },
        "ciphertext": b64encode(ciphertext).decode(),
    }


def decrypt_passphrase(file_obj: dict, passphrase: str) -> dict:
    """Decrypt a passphrase-encrypted export file. Returns the cleartext payload dict."""
    meta = file_obj.get("encryption_meta", {})
    try:
        salt = bytes.fromhex(meta["salt"])
        nonce = bytes.fromhex(meta["nonce"])
        tag = bytes.fromhex(meta["tag"])
        ciphertext = b64decode(file_obj["ciphertext"])
        params = meta.get("kdf_params", {})
        n = int(params.get("N", SCRYPT_N))
        r = int(params.get("r", SCRYPT_R))
        p = int(params.get("p", SCRYPT_P))
        dklen = int(params.get("dklen", SCRYPT_DKLEN))
    except (KeyError, ValueError) as e:
        raise ValueError(f"Malformed passphrase export header: {e}") from e

    key = scrypt(passphrase.encode("utf-8"), salt, key_len=dklen, N=n, r=r, p=p)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    try:
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    except (ValueError, KeyError) as e:
        raise ValueError("Decryption failed (wrong passphrase or corrupted file)") from e
    return json.loads(plaintext.decode("utf-8"))


def encrypt_nip44(payload: dict, npub: str) -> dict:
    """Encrypt the payload with NIP-44 v2 for the given npub."""
    enc = encrypt_for_npub(payload, npub)
    return {
        "encryption": "nip44",
        "encryption_meta": {"ephem_pubkey": enc["ephem_pubkey"]},
        "ciphertext": enc["payload"],
    }


def wrap_file(network: str, encryption_block: dict) -> dict:
    """Build the outer file object that will be downloaded by the user."""
    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network": network,
        **encryption_block,
    }


def hash_passphrase_for_fingerprint(passphrase: str) -> str:
    """Tiny fingerprint to surface "wrong passphrase" without timing leaks (UI display only)."""
    return hashlib.sha256(passphrase.encode("utf-8")).hexdigest()[:8]
