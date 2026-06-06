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

EXPORT_VERSION = 2
SCRYPT_N = 2 ** 17   # 131072, ~128 MB RAM; balances security and UX
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32    # 256-bit key for AES-256
SALT_LEN = 16
NONCE_LEN = 12       # AES-GCM standard


# Schedule metadata carried on each "tx" line of the BIP-329 dialect.
# Omitted from the line when null/empty to keep records lean.
_TX_LINE_OPTIONAL = (
    "collection", "target_block", "target_price", "price_direction",
    "expires_at", "depends_on", "locktime",
)

RESERVED_LABEL = "Reservado: Broadcast Pool"


def build_jsonl(txs_data: list[dict], network: str) -> str:
    """Serialize the pool as a BIP-329 dialect JSONL document (v2 format).

    One record per line:
    - header line, type "bp": file metadata (version, network, exported_at)
    - one "tx" line per retained tx: ref=txid, label, hex (mandatory in this
      dialect), checksum (sha256 of hex — txid does not commit to witness data),
      plus BP schedule metadata
    - one "output" line per committed prevout, spendable:false, so external
      BIP-329 importers freeze the coins reserved by retained txs

    External wallets ignore the "bp" line and the unknown fields; BP's own
    import requires "hex" on every "tx" line.
    """
    lines: list[dict] = [{
        "type": "bp",
        "version": EXPORT_VERSION,
        "network": network,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }]
    prevouts_seen: set[str] = set()
    for tx in txs_data:
        line: dict = {
            "type": "tx",
            "ref": tx["txid"],
            "label": tx.get("wallet_label", ""),
            "hex": tx["raw_hex"],
            "checksum": hashlib.sha256(tx["raw_hex"].encode("ascii")).hexdigest(),
        }
        if tx.get("created_at"):
            line["time"] = tx["created_at"]
        for field in _TX_LINE_OPTIONAL:
            value = tx.get(field)
            if value in (None, ""):
                continue
            # price_direction is the DB default even without a price schedule —
            # only meaningful alongside target_price
            if field == "price_direction" and not tx.get("target_price"):
                continue
            line[field] = value
        lines.append(line)
        for inp in tx.get("inputs", []):
            ref = f"{inp['prev_txid']}:{inp['prev_vout']}"
            if ref in prevouts_seen:
                continue
            prevouts_seen.add(ref)
            lines.append({
                "type": "output",
                "ref": ref,
                "label": RESERVED_LABEL,
                "spendable": False,
            })
    return "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n"


def parse_jsonl(text: str) -> dict:
    """Parse a v2 JSONL export back into the internal payload shape
    ({version, network, txs: [...]}) consumed by the import flow.

    Tolerant with unknown types/fields (BIP-329 rule), strict with what BP
    needs: every "tx" line must carry "hex"."""
    version = None
    network = None
    txs: list[dict] = []
    for n, raw_line in enumerate(text.splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            line = json.loads(raw_line)
        except ValueError as e:
            raise ValueError(f"line {n}: invalid JSON ({e})") from e
        if not isinstance(line, dict):
            raise ValueError(f"line {n}: record must be a JSON object")
        ltype = line.get("type")
        if ltype == "bp":
            version = line.get("version")
            network = line.get("network")
        elif ltype == "tx":
            if not line.get("hex"):
                raise ValueError(
                    f"line {n}: 'tx' record without 'hex' — not a Broadcast Pool export"
                )
            entry = {
                "txid": line.get("ref", ""),
                "raw_hex": line["hex"],
                "raw_hex_checksum": line.get("checksum"),
                "wallet_label": line.get("label", ""),
                "created_at": line.get("time"),
            }
            for field in _TX_LINE_OPTIONAL:
                entry[field] = line.get(field)
            txs.append(entry)
        # "output" lines (frozen prevouts) and unknown types: informative only —
        # import re-derives prevouts by parsing each tx hex.
    return {"version": version, "network": network, "txs": txs}


def parse_cleartext(text: str) -> dict:
    """Parse a cleartext export of either generation.

    v1: a single JSON object {version:1, network, txs}.
    v2: JSONL (BIP-329 dialect) — one object per line.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty export payload")
    try:
        doc = json.loads(stripped)
    except ValueError:
        # Not a single JSON document — treat as JSONL (v2)
        return parse_jsonl(stripped)
    if isinstance(doc, dict) and isinstance(doc.get("txs"), list):
        return doc  # v1 payload
    if isinstance(doc, dict) and doc.get("type") in ("bp", "tx", "output"):
        return parse_jsonl(stripped)  # single-line JSONL edge case
    raise ValueError("unrecognized export payload structure")


def encrypt_passphrase(payload: dict | str, passphrase: str) -> dict:
    """Encrypt the payload with AES-256-GCM, key from scrypt(passphrase, salt).

    v2 passes the JSONL document as str; dict kept for backward compat."""
    if not passphrase:
        raise ValueError("passphrase is empty")
    cleartext = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    plaintext = cleartext.encode("utf-8")
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
    return parse_cleartext(plaintext.decode("utf-8"))


def build_unencrypted(payload: dict) -> dict:
    """Embed the payload inline (no encryption) so the file is plain readable JSON.

    Used when the user explicitly opts out of encryption (acknowledged warning).
    Encrypted variants use {ciphertext, encryption_meta}; for "none" the payload
    sits under "payload" directly, so the file can be opened in any editor.
    """
    return {
        "encryption": "none",
        "payload": payload,
    }


def decrypt_unencrypted(file_obj: dict) -> dict:
    """Read the inline payload from an unencrypted export."""
    if "payload" not in file_obj or not isinstance(file_obj["payload"], dict):
        raise ValueError("Malformed unencrypted export: missing 'payload' object")
    return file_obj["payload"]


def encrypt_nip44(payload: dict | str, npub: str) -> dict:
    """Encrypt the payload with NIP-44 v2 for the given npub.

    v2 passes the JSONL document as str; dict kept for backward compat."""
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
