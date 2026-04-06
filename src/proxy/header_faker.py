"""Header faker for Liana height-offset PoC.

Generates fake block header chains to make Liana sign txs with future
nLockTime. Liana doesn't validate PoW (only chain continuity + genesis hash),
so a chain of headers with valid prev_hash linkage is enough.

Use case: lets BP retain txs with realistic anti-fee-sniping locktimes
that match the target broadcast block, improving on-chain privacy by
mixing with real timelock-using transactions.

EXPERIMENTAL — only for Liana sessions when explicitly enabled.
"""

import hashlib
import struct
from typing import List


def sha256d(data: bytes) -> bytes:
    """Bitcoin's double SHA256."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def parse_header(header_hex: str) -> dict:
    """Parse an 80-byte block header."""
    h = bytes.fromhex(header_hex)
    if len(h) != 80:
        raise ValueError(f"Header must be 80 bytes, got {len(h)}")
    return {
        "version": struct.unpack("<i", h[0:4])[0],
        "prev_hash": h[4:36],  # little-endian internal byte order
        "merkle_root": h[36:68],
        "time": struct.unpack("<I", h[68:72])[0],
        "bits": h[72:76],
        "nonce": struct.unpack("<I", h[76:80])[0],
        "hash": sha256d(h),  # internal byte order
    }


def build_header(
    version: int,
    prev_hash: bytes,
    merkle_root: bytes,
    time: int,
    bits: bytes,
    nonce: int,
) -> bytes:
    """Build an 80-byte block header."""
    return (
        struct.pack("<i", version)
        + prev_hash
        + merkle_root
        + struct.pack("<I", time)
        + bits
        + struct.pack("<I", nonce)
    )


def generate_fake_chain(real_tip_hex: str, count: int) -> List[bytes]:
    """Generate `count` fake headers chaining from real_tip.

    Each fake header:
    - prev_hash = sha256d of previous header (real_tip for first)
    - merkle_root = zeros (Liana doesn't verify this)
    - time = real_tip.time + 600*(i+1) (~10 min per block)
    - bits = real_tip.bits (same difficulty)
    - nonce = 0 (no PoW; Liana doesn't verify it)
    """
    parsed = parse_header(real_tip_hex)
    real_header_bytes = bytes.fromhex(real_tip_hex)

    fake_headers: List[bytes] = []
    prev_hash = sha256d(real_header_bytes)
    last_time = parsed["time"]
    bits = parsed["bits"]

    for i in range(count):
        last_time += 600  # 10 min per block
        header = build_header(
            version=4,
            prev_hash=prev_hash,
            merkle_root=b"\x00" * 32,
            time=last_time,
            bits=bits,
            nonce=0,
        )
        fake_headers.append(header)
        prev_hash = sha256d(header)

    return fake_headers
