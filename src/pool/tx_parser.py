"""Minimal Bitcoin transaction parser.

Extracts txid, inputs (prev_txid:vout), outputs (value, scriptPubKey),
nLockTime, and vsize from raw transaction hex. No external dependencies.
"""

import hashlib
import struct
from dataclasses import dataclass, field
from io import BytesIO


@dataclass
class TxInput:
    prev_txid: str  # hex, reversed (display order)
    prev_vout: int
    script_sig: bytes
    sequence: int
    # Filled later by the proxy when resolving upstream
    scripthash: str = ""
    value_sats: int = 0
    confirmed_height: int = 0  # Block height where this UTXO was confirmed


@dataclass
class TxOutput:
    value_sats: int
    script_pubkey: bytes
    script_pubkey_hex: str = ""
    scripthash: str = ""


@dataclass
class ParsedTx:
    txid: str
    version: int
    inputs: list[TxInput]
    outputs: list[TxOutput]
    locktime: int
    size: int       # total bytes
    weight: int     # weight units
    vsize: int      # virtual size (ceil(weight/4))
    is_segwit: bool
    fee_sats: int = 0
    fee_rate: float = 0.0


def _read_varint(stream: BytesIO) -> int:
    n = struct.unpack("<B", stream.read(1))[0]
    if n < 0xFD:
        return n
    elif n == 0xFD:
        return struct.unpack("<H", stream.read(2))[0]
    elif n == 0xFE:
        return struct.unpack("<I", stream.read(4))[0]
    else:
        return struct.unpack("<Q", stream.read(8))[0]


def _read_bytes(stream: BytesIO, n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        raise ValueError(f"Unexpected end of data: expected {n} bytes, got {len(data)}")
    return data


def compute_scripthash(script_pubkey_hex: str) -> str:
    """Compute Electrum scripthash from a scriptPubKey hex string."""
    script_bytes = bytes.fromhex(script_pubkey_hex)
    h = hashlib.sha256(script_bytes).digest()
    return h[::-1].hex()


def parse_raw_tx(raw_hex: str) -> ParsedTx:
    """Parse a raw transaction hex string into a ParsedTx."""
    raw_bytes = bytes.fromhex(raw_hex)
    stream = BytesIO(raw_bytes)
    total_size = len(raw_bytes)

    # Version (4 bytes)
    version = struct.unpack("<I", _read_bytes(stream, 4))[0]

    # Check for segwit marker
    pos_after_version = stream.tell()
    marker = struct.unpack("<B", _read_bytes(stream, 1))[0]

    is_segwit = False
    if marker == 0x00:
        flag = struct.unpack("<B", _read_bytes(stream, 1))[0]
        if flag != 0x01:
            raise ValueError(f"Invalid segwit flag: {flag}")
        is_segwit = True
    else:
        # Not segwit, rewind
        stream.seek(pos_after_version)

    # Inputs
    num_inputs = _read_varint(stream)
    inputs = []
    for _ in range(num_inputs):
        prev_hash = _read_bytes(stream, 32)
        prev_txid = prev_hash[::-1].hex()
        prev_vout = struct.unpack("<I", _read_bytes(stream, 4))[0]
        script_len = _read_varint(stream)
        script_sig = _read_bytes(stream, script_len)
        sequence = struct.unpack("<I", _read_bytes(stream, 4))[0]
        inputs.append(TxInput(
            prev_txid=prev_txid,
            prev_vout=prev_vout,
            script_sig=script_sig,
            sequence=sequence,
        ))

    # Outputs
    num_outputs = _read_varint(stream)
    outputs = []
    for _ in range(num_outputs):
        value = struct.unpack("<Q", _read_bytes(stream, 8))[0]
        script_len = _read_varint(stream)
        script_pubkey = _read_bytes(stream, script_len)
        spk_hex = script_pubkey.hex()
        outputs.append(TxOutput(
            value_sats=value,
            script_pubkey=script_pubkey,
            script_pubkey_hex=spk_hex,
            scripthash=compute_scripthash(spk_hex),
        ))

    # Witness data (segwit only)
    witness_size = 0
    if is_segwit:
        witness_start = stream.tell()
        for _ in range(num_inputs):
            num_items = _read_varint(stream)
            for _ in range(num_items):
                item_len = _read_varint(stream)
                _read_bytes(stream, item_len)
        witness_size = stream.tell() - witness_start

    # Locktime (4 bytes)
    locktime = struct.unpack("<I", _read_bytes(stream, 4))[0]

    # Calculate weight and vsize
    # weight = (total_size - witness_size - 2) * 3 + total_size
    # The -2 accounts for marker+flag bytes in segwit
    if is_segwit:
        non_witness_size = total_size - witness_size - 2  # -2 for marker+flag
        weight = non_witness_size * 4 + witness_size + 2  # witness at 1x, +2 for marker+flag at 1x
        # More precisely: weight = base_size * 3 + total_size
        base_size = total_size - witness_size - 2
        weight = base_size * 3 + total_size
    else:
        weight = total_size * 4

    vsize = (weight + 3) // 4  # ceil division

    # Calculate txid (hash of non-witness serialization)
    if is_segwit:
        # Rebuild without witness: version + inputs + outputs + locktime
        txid_preimage = BytesIO()
        txid_preimage.write(raw_bytes[:4])  # version
        # Skip marker+flag (bytes 4,5), serialize from byte 6
        # We need to find where inputs+outputs end before witness
        # Easier: rebuild from parsed data
        txid_preimage.write(_serialize_varint(num_inputs))
        for inp in inputs:
            txid_preimage.write(bytes.fromhex(inp.prev_txid)[::-1])
            txid_preimage.write(struct.pack("<I", inp.prev_vout))
            txid_preimage.write(_serialize_varint(len(inp.script_sig)))
            txid_preimage.write(inp.script_sig)
            txid_preimage.write(struct.pack("<I", inp.sequence))
        txid_preimage.write(_serialize_varint(num_outputs))
        for out in outputs:
            txid_preimage.write(struct.pack("<Q", out.value_sats))
            txid_preimage.write(_serialize_varint(len(out.script_pubkey)))
            txid_preimage.write(out.script_pubkey)
        txid_preimage.write(struct.pack("<I", locktime))
        txid_data = txid_preimage.getvalue()
    else:
        txid_data = raw_bytes

    txid_hash = hashlib.sha256(hashlib.sha256(txid_data).digest()).digest()
    txid = txid_hash[::-1].hex()

    return ParsedTx(
        txid=txid,
        version=version,
        inputs=inputs,
        outputs=outputs,
        locktime=locktime,
        size=total_size,
        weight=weight,
        vsize=vsize,
        is_segwit=is_segwit,
    )


def _serialize_varint(n: int) -> bytes:
    if n < 0xFD:
        return struct.pack("<B", n)
    elif n <= 0xFFFF:
        return struct.pack("<BH", 0xFD, n)
    elif n <= 0xFFFFFFFF:
        return struct.pack("<BI", 0xFE, n)
    else:
        return struct.pack("<BQ", 0xFF, n)
