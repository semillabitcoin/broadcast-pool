"""Every path that moves a tx to 'scheduled' must encrypt raw_hex at rest.

Regression for the gap where update_target_block()/update_target_price() set
status='scheduled' via direct SQL, bypassing the encryption that only
update_status() used to do — leaving price/block-scheduled txs in cleartext.
"""
import pytest

from src.db.schema import init_db
from src.pool.store import TxStore
from src.pool.tx_parser import ParsedTx, TxInput, TxOutput
from src.pool import crypto
from src import config

RAW = "0200000000010199" + "ab" * 60 + "00000000"


def _parsed(txid):
    return ParsedTx(
        txid=txid, version=2,
        inputs=[TxInput(prev_txid="11" * 32, prev_vout=0, script_sig=b"", sequence=0xfffffffd)],
        outputs=[TxOutput(value_sats=100_000, script_pubkey=b"\x00\x14" + b"\x11" * 20,
                          script_pubkey_hex="0014" + "11" * 20)],
        locktime=0, size=100, weight=400, vsize=100, is_segwit=True, fee_sats=200, fee_rate=2.0,
    )


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(config, "APP_SEED", "store-test-seed-aaaaaaaa")
    crypto._derived_key = None
    s = TxStore(init_db(":memory:"))
    s.network = "mainnet"
    yield s
    crypto._derived_key = None


def _raw_at_rest(store, txid):
    row = store._conn.execute(
        "SELECT raw_hex FROM retained_txs WHERE txid = ?", (txid,)
    ).fetchone()
    return row["raw_hex"]


def test_saved_tx_encrypted_at_rest(store):
    # Retained txs are encrypted at rest immediately — not even 'pending' is cleartext.
    txid = "f" * 64
    store.save_retained_tx(_parsed(txid), RAW)
    assert _raw_at_rest(store, txid).startswith("ENC:v2:")
    # …but every reader sees plaintext: decrypted on load and on demand.
    assert store.get_tx(txid).raw_hex == RAW
    assert store.get_raw_hex(txid) == RAW
    assert store.get_all_txs()[0].raw_hex == RAW


def test_no_app_seed_stays_cleartext(monkeypatch):
    # Without APP_SEED, behaviour is unchanged (plaintext at rest, plaintext to readers).
    from src import config
    monkeypatch.setattr(config, "APP_SEED", "")
    crypto._derived_key = None
    s = TxStore(init_db(":memory:"))
    s.network = "mainnet"
    txid = "e" * 64
    s.save_retained_tx(_parsed(txid), RAW)
    assert _raw_at_rest(s, txid) == RAW
    assert s.get_tx(txid).raw_hex == RAW


def test_update_target_price_encrypts_at_rest(store):
    txid = "a" * 64
    store.save_retained_tx(_parsed(txid), RAW)
    store.update_target_price(txid, 59_000, "below", expires_at=None)
    assert _raw_at_rest(store, txid).startswith("ENC:v2:")  # encrypted at rest
    assert store.get_raw_hex(txid) == RAW                   # still decryptable


def test_update_target_block_encrypts_at_rest(store):
    txid = "b" * 64
    store.save_retained_tx(_parsed(txid), RAW)
    store.update_target_block(txid, 953_999)  # keep_status=False → status 'scheduled'
    assert _raw_at_rest(store, txid).startswith("ENC:v2:")
    assert store.get_raw_hex(txid) == RAW


def test_update_status_scheduled_encrypts(store):
    txid = "c" * 64
    store.save_retained_tx(_parsed(txid), RAW)
    store.update_status(txid, "scheduled")
    assert _raw_at_rest(store, txid).startswith("ENC:v2:")
    assert store.get_raw_hex(txid) == RAW


def test_encrypt_existing_at_rest_sweeps_cleartext(store):
    # Simulate older/buggy data: force two rows to cleartext on disk.
    for txid in ("a" * 64, "b" * 64):
        store.save_retained_tx(_parsed(txid), RAW)
        store._conn.execute("UPDATE retained_txs SET raw_hex=? WHERE txid=?", (RAW, txid))
    store._conn.commit()
    assert _raw_at_rest(store, "a" * 64) == RAW  # cleartext on disk

    n = store.encrypt_existing_at_rest()
    assert n == 2
    assert _raw_at_rest(store, "a" * 64).startswith("ENC:v2:")
    assert _raw_at_rest(store, "b" * 64).startswith("ENC:v2:")
    assert store.get_raw_hex("a" * 64) == RAW           # still decryptable
    assert store.encrypt_existing_at_rest() == 0        # idempotent


def test_encrypt_existing_skips_placeholder(store):
    txid = "d" * 64
    store.save_retained_tx(_parsed(txid), RAW)
    store._conn.execute("UPDATE retained_txs SET raw_hex='[unresolved]' WHERE txid=?", (txid,))
    store._conn.commit()
    assert store.encrypt_existing_at_rest() == 0        # "[...]" placeholders left alone
    assert _raw_at_rest(store, txid) == "[unresolved]"
