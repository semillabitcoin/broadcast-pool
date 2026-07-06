"""Import re-applies each tx's recorded rebroadcast conditions (price/block),
with a toggle to ignore them and import as pending. BIP-329 dialect carries the
schedule on the tx line; this covers the restore side (was a v1 limitation)."""
import asyncio

import pytest

from src.web import api
from src.db.schema import init_db
from src.pool.store import TxStore
from src.pool.tx_parser import parse_raw_tx
from src.pool import crypto
from src import config


# A minimal valid non-segwit tx (coinbase-style: no real prevouts to conflict on).
RAW = (
    "01000000"
    "01"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "ffffffff"
    "07"
    "04ffff001d0104"
    "ffffffff"
    "01"
    "00f2052a01000000"
    "43"
    "4104678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb6"
    "49f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5fac"
    "00000000"
)


class _App(dict):
    def get(self, k, default=None):
        return dict.get(self, k, default)


class _Req:
    match_info = {}

    def __init__(self, app, body):
        self.app = app
        self._body = body

    async def json(self):
        return self._body


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(config, "APP_SEED", "")
    crypto._derived_key = None
    s = TxStore(init_db(":memory:"))
    s.network = "mainnet"
    yield s
    crypto._derived_key = None


def _apply(store, entry, restore_schedule):
    app = _App()
    app["store"] = store
    app["scheduler"] = None
    body = {
        "decrypted_payload": {"version": 2, "network": "mainnet", "txs": [entry]},
        "restore_schedule": restore_schedule,
    }
    asyncio.run(api.handle_pool_import_apply(_Req(app, body)))


def _price_entry():
    txid = parse_raw_tx(RAW).txid
    return {
        "txid": txid, "raw_hex": RAW, "wallet_label": "loan",
        "target_price": 95000.0, "price_direction": "below",
        "expires_at": "2030-01-01T00:00:00", "target_block": None,
    }, txid


def test_import_restores_price_schedule(store):
    entry, txid = _price_entry()
    _apply(store, entry, restore_schedule=True)
    tx = store.get_tx(txid)
    assert tx is not None
    assert tx.status == "scheduled"
    assert tx.target_price == 95000.0
    assert tx.price_direction == "below"
    assert tx.expires_at == "2030-01-01T00:00:00"
    assert tx.target_block is None


def test_import_ignores_schedule_when_toggled_off(store):
    entry, txid = _price_entry()
    _apply(store, entry, restore_schedule=False)
    tx = store.get_tx(txid)
    assert tx is not None
    assert tx.status == "pending"        # imported unscheduled
    assert tx.target_price is None       # condition NOT restored


def test_import_restores_block_schedule(store):
    txid = parse_raw_tx(RAW).txid
    entry = {"txid": txid, "raw_hex": RAW, "wallet_label": "loan",
             "target_block": 950000, "target_price": None}
    _apply(store, entry, restore_schedule=True)
    tx = store.get_tx(txid)
    assert tx.status == "scheduled"
    assert tx.target_block == 950000
    assert tx.target_price is None
