"""Tests for the v2 (BIP-329 dialect JSONL) export/import format."""

import json

import pytest

from src.pool import export as e

TXS = [{
    "txid": "f91d0a8a78462bc59398f2c5d7a84fcff491c26ba54c4833478b202796c8aafd",
    "raw_hex": "0200000001abcd",
    "wallet_label": "préstamo 1",
    "collection": "lending",
    "target_block": None,
    "target_price": 95000.0,
    "price_direction": "below",
    "expires_at": None,
    "depends_on": None,
    "locktime": 904100,
    "created_at": "2026-05-18 08:00:00",
    "inputs": [
        {"prev_txid": "aa" * 32, "prev_vout": 0},
        {"prev_txid": "bb" * 32, "prev_vout": 3},
    ],
}, {
    "txid": "11" * 32,
    "raw_hex": "0200000002ffff",
    "wallet_label": "herederos",
    "collection": "",
    "target_block": 1010000,
    "target_price": None,
    "price_direction": "below",  # DB default — must NOT be exported without target_price
    "expires_at": None,
    "depends_on": None,
    "locktime": 0,
    "created_at": "2026-06-01 10:00:00",
    "inputs": [{"prev_txid": "aa" * 32, "prev_vout": 0}],  # dup prevout on purpose
}]


def test_build_jsonl_structure():
    jsonl = e.build_jsonl(TXS, "mainnet")
    lines = [json.loads(l) for l in jsonl.strip().split("\n")]

    assert lines[0]["type"] == "bp"
    assert lines[0]["version"] == 2
    assert lines[0]["network"] == "mainnet"

    tx_lines = [l for l in lines if l["type"] == "tx"]
    assert len(tx_lines) == 2
    t0 = tx_lines[0]
    assert t0["ref"] == TXS[0]["txid"]
    assert t0["hex"] == TXS[0]["raw_hex"]
    assert t0["collection"] == "lending"
    assert t0["target_price"] == 95000.0
    # empty collection and default price_direction are omitted
    assert "collection" not in tx_lines[1]
    assert "price_direction" not in tx_lines[1]

    # prevouts → output lines, deduped across txs, spendable is a real boolean
    out_lines = [l for l in lines if l["type"] == "output"]
    assert len(out_lines) == 2
    assert all(l["spendable"] is False for l in out_lines)
    assert {l["ref"] for l in out_lines} == {"aa" * 32 + ":0", "bb" * 32 + ":3"}
    # frozen-coin marker is a constant label, independent of the tx's label
    assert all(l["label"] == "Reservado: Broadcast Pool" for l in out_lines)


def test_jsonl_roundtrip():
    payload = e.parse_cleartext(e.build_jsonl(TXS, "mainnet"))
    assert payload["version"] == 2
    assert payload["network"] == "mainnet"
    assert len(payload["txs"]) == 2
    t0 = payload["txs"][0]
    assert t0["raw_hex"] == TXS[0]["raw_hex"]
    assert t0["wallet_label"] == "préstamo 1"
    assert t0["collection"] == "lending"
    assert payload["txs"][1]["target_block"] == 1010000


def test_parse_cleartext_v1_compat():
    v1 = {"version": 1, "network": "mainnet", "txs": [{"txid": "ab", "raw_hex": "02"}]}
    assert e.parse_cleartext(json.dumps(v1, indent=2)) == v1


def test_tx_line_without_hex_rejected():
    with pytest.raises(ValueError, match="hex"):
        e.parse_jsonl('{"type":"tx","ref":"ab","label":"x"}')


def test_unknown_types_and_blank_lines_tolerated():
    text = (
        '{"type": "bp", "version": 2, "network": "signet"}\n'
        '\n'
        '{"type": "addr", "ref": "tb1q...", "label": "ajena"}\n'
        '{"type": "tx", "ref": "ab", "hex": "02", "label": ""}\n'
    )
    payload = e.parse_jsonl(text)
    assert payload["network"] == "signet"
    assert len(payload["txs"]) == 1


def test_passphrase_roundtrip_v2():
    jsonl = e.build_jsonl(TXS, "mainnet")
    enc = e.encrypt_passphrase(jsonl, "supersecret123")
    dec = e.decrypt_passphrase(enc, "supersecret123")
    assert dec["version"] == 2
    assert dec["txs"][0]["raw_hex"] == TXS[0]["raw_hex"]


def test_wrong_passphrase_fails():
    enc = e.encrypt_passphrase(e.build_jsonl(TXS, "mainnet"), "supersecret123")
    with pytest.raises(ValueError):
        e.decrypt_passphrase(enc, "wrong-passphrase")
