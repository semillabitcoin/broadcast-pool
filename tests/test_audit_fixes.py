"""Regression tests for the high/medium/low audit fixes (v0.3.22)."""
import asyncio
from base64 import b64encode
from types import SimpleNamespace

import pytest

from src.scheduler.scheduler import Scheduler
from src.pool.status_hash import compute_status_hash, sort_history
from src.pool.tx_parser import parse_raw_tx
from src.pool import export as exportmod
from src import diagnostics


LEGACY_TX_HEX = (
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


# ---------------------------------------------------------------- fakes
class FakeStore:
    def __init__(self, height=900000):
        self.state = {}
        self.status_updates = []
        self.broadcast_times = []
        self._height = height

    def set_state(self, k, v): self.state[k] = v
    def get_state(self, k): return self.state.get(k)
    def get_current_height(self): return self._height
    def update_status(self, txid, status, **kw): self.status_updates.append((txid, status))
    def update_broadcast_time(self, txid): self.broadcast_times.append(txid)
    def get_scripthashes_for_tx(self, txid): return set()
    def get_all_txs(self, status=None, network=None): return []


def _sched(store=None, upstream=None, node=None):
    s = Scheduler.__new__(Scheduler)
    s._upstream = upstream
    s._node = node
    s.store = store or FakeStore()
    s.notify_callback = None
    s._running = False
    s.node_fallback_active = False
    s.node_reachable = None
    return s


# ---------------------------------------------------------------- L7
def test_status_hash_orders_confirmed_before_mempool():
    h = [
        {"tx_hash": "aa", "height": 0},     # mempool
        {"tx_hash": "bb", "height": 100},   # confirmed
        {"tx_hash": "cc", "height": -1},    # mempool with unconfirmed parent
        {"tx_hash": "dd", "height": 50},    # confirmed, earlier
    ]
    order = [x["tx_hash"] for x in sort_history(h)]
    assert order == ["dd", "bb", "aa", "cc"]  # confirmed by height, then 0, then -1


def test_status_hash_stable_and_consistent_with_sorted():
    h = [{"tx_hash": "bb", "height": 100}, {"tx_hash": "aa", "height": 0}]
    # A wallet recomputing over the (sorted) get_history must land on the same hash.
    assert compute_status_hash(h) == compute_status_hash(sort_history(h))
    assert compute_status_hash([]) is None


# ---------------------------------------------------------------- L8
def test_parser_accepts_clean_tx():
    parsed = parse_raw_tx(LEGACY_TX_HEX)
    assert parsed.txid and len(parsed.txid) == 64


def test_parser_rejects_trailing_bytes():
    with pytest.raises(ValueError, match="Trailing bytes"):
        parse_raw_tx(LEGACY_TX_HEX + "00")


# ---------------------------------------------------------------- M8
def test_scrypt_params_bounded_on_import():
    file_obj = {
        "encryption_meta": {
            "salt": "00" * 16, "nonce": "00" * 12, "tag": "00" * 16,
            "kdf_params": {"N": 2 ** 24, "r": 8, "p": 1, "dklen": 32},  # N far too high
        },
        "ciphertext": b64encode(b"").decode(),
    }
    with pytest.raises(ValueError, match="out of accepted range"):
        exportmod.decrypt_passphrase(file_obj, "whatever")


def test_scrypt_params_accept_defaults():
    # Default params must pass the bounds check (then fail on the wrong passphrase).
    file_obj = {
        "encryption_meta": {
            "salt": "00" * 16, "nonce": "00" * 12, "tag": "00" * 16,
            "kdf_params": {"N": 2 ** 17, "r": 8, "p": 1, "dklen": 32},
        },
        "ciphertext": b64encode(b"x" * 16).decode(),
    }
    with pytest.raises(ValueError, match="Decryption failed"):
        exportmod.decrypt_passphrase(file_obj, "whatever")


# ---------------------------------------------------------------- M10
def test_diagnostics_redacts_8byte_txid_prefix():
    # Logs abbreviate txids with [:16] (16 hex = 8 bytes). Those must be redacted.
    line = "Broadcast scheduled tx a1b2c3d4e5f60718 at block 900000"
    out = diagnostics.sanitize(line)
    assert "a1b2c3d4e5f60718" not in out
    assert "<hex>" in out
    assert "900000" in out  # decimal height untouched


# ------------------------------------------------ node_fallback_active reset
def test_node_fallback_active_cleared_when_node_dies():
    store = FakeStore()
    node = SimpleNamespace()
    async def health(): return None
    node.health = health
    s = _sched(store=store, node=node)
    s.node_fallback_active = True  # node had been the fallback (electrs down)
    asyncio.run(s._node_fallback_tick())
    assert s.node_reachable is False
    assert s.node_fallback_active is False       # not left stale-amber
    assert "current_height" not in store.state   # chain state untouched


# ---------------------------------------------------------------- L2
def test_broadcast_now_checks_status_before_expiry():
    # A confirmed tx with a past expiry must be refused on STATUS, and NOT
    # relabeled 'expired' by the policy gate running first.
    store = FakeStore()
    tx = SimpleNamespace(txid="a" * 64, status="confirmed",
                         expires_at="2020-01-01T00:00:00", locktime=0)
    store.get_tx = lambda txid: tx
    s = _sched(store=store)
    out = asyncio.run(s.broadcast_now("a" * 64))
    assert "status 'confirmed'" in out["error"]
    assert ("a" * 64, "expired") not in store.status_updates


# ---------------------------------------------------------------- M6
def test_reconnect_nulls_upstream_before_await():
    closed = {"done": False}
    class SlowUpstream:
        async def close(self):
            # By the time close() awaits, reconnect must have already nulled the
            # scheduler's ref — else a concurrent _run() could clobber a new one.
            assert not_scheduler._upstream is None  # already detached
            closed["done"] = True
    s = _sched()
    s.upstream_connected = True
    s._reconnect_event = asyncio.Event()
    not_scheduler = s
    s._upstream = SlowUpstream()
    asyncio.run(s.reconnect())
    assert closed["done"] and s._upstream is None


# ---------------------------------------------------------------- L4
def test_confirmation_height_skips_empty_scripthash():
    store = FakeStore()
    store.get_scripthashes_for_tx = lambda txid: {"", "c" * 64}
    calls = []
    class Up:
        async def call(self, method, params=None):
            calls.append(params[0])
            return {"result": [{"tx_hash": "a" * 64, "height": 850000}]}
    s = _sched(store=store, upstream=Up())
    tx = SimpleNamespace(txid="a" * 64)
    h = asyncio.run(s._confirmation_height(tx))
    assert calls == ["c" * 64]  # used the real scripthash, not ""
    assert h == 850000


# ---------------------------------------------------------------- H1
def test_price_poller_accepts_sustained_move(monkeypatch):
    store = FakeStore()
    store.set_state("price_source", "coingecko")
    s = _sched(store=store)
    s._current_price = 100000.0
    s._running = True
    s._purge_expired_txs = lambda: None
    reads = [80000.0, 80000.0, 80000.0]  # a real -20% move, sustained
    calls = {"n": 0}
    async def fake_fetch(src):
        i = calls["n"]; calls["n"] += 1
        return reads[i] if i < len(reads) else 80000.0
    s._fetch_price = fake_fetch
    import src.scheduler.scheduler as schedmod
    async def fake_sleep(_):
        if calls["n"] >= len(reads):
            s._running = False
    monkeypatch.setattr(schedmod.asyncio, "sleep", fake_sleep)
    asyncio.run(s._price_poller())
    assert s._current_price == 80000.0  # accepted after 3 agreeing readings


def test_price_poller_holds_single_spike(monkeypatch):
    store = FakeStore()
    store.set_state("price_source", "coingecko")
    s = _sched(store=store)
    s._current_price = 100000.0
    s._running = True
    s._purge_expired_txs = lambda: None
    reads = [50000.0, 99000.0]  # one glitch, then back to normal
    calls = {"n": 0}
    async def fake_fetch(src):
        i = calls["n"]; calls["n"] += 1
        return reads[i] if i < len(reads) else 99000.0
    s._fetch_price = fake_fetch
    import src.scheduler.scheduler as schedmod
    async def fake_sleep(_):
        if calls["n"] >= len(reads):
            s._running = False
    monkeypatch.setattr(schedmod.asyncio, "sleep", fake_sleep)
    asyncio.run(s._price_poller())
    assert s._current_price == 99000.0  # glitch ignored, normal reading accepted
