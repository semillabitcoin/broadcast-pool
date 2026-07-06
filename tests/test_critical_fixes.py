"""Regression tests for the v0.3.22 critical-bug fixes.

1. Upstream read-loop deadlock: a notification callback that issues its own
   upstream.call() must not stall message routing (dispatch runs off the read
   loop). This is the wallet↔upstream data path, so it must never freeze.
2. _detect_conflicts must NOT abandon a tx when electrs returns an error
   (false positive → next purge deletes the signed raw_hex irrecoverably).
3. _broadcast_due_by_timestamp must ignore txs that carry an explicit block or
   price trigger (only pure timestamp-locktime schedules are due by MTP).
4. update_target_block/price must clear the opposite trigger so a tx can't be
   scheduled by two conflicting triggers at once.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from src.scheduler.scheduler import Scheduler
from src.proxy.upstream import UpstreamConnection
from src.db.schema import init_db
from src.pool.store import TxStore
from src.pool import crypto
from src import config


def _sched(upstream=None, node=None, store=None, notify=None):
    s = Scheduler.__new__(Scheduler)
    s._upstream = upstream
    s._node = node
    s.store = store
    s.notify_callback = notify
    return s


# ------------------------------------------------------------------ Fix #1
def test_notification_callback_can_reenter_call_without_deadlock():
    """The exact deadlock shape: an upstream server pushes a notification; the
    notification callback issues its own upstream.call() on the SAME connection.
    Before the dispatch-queue fix the read loop was suspended inside the callback
    and could never deliver that call()'s response → 120s timeout. It must now
    resolve promptly."""

    async def scenario():
        async def handle(reader, writer):
            # Push a server-initiated notification the instant the client connects…
            notif = {"jsonrpc": "2.0", "method": "blockchain.headers.subscribe",
                     "params": [{"height": 1, "hex": "00"}]}
            writer.write((json.dumps(notif) + "\n").encode())
            await writer.drain()
            # …then answer every request (the callback's re-entrant call).
            while True:
                line = await reader.readline()
                if not line:
                    break
                req = json.loads(line)
                resp = {"jsonrpc": "2.0", "id": req["id"],
                        "result": {"hex": "00" * 80, "count": 1, "max": 2016}}
                writer.write((json.dumps(resp) + "\n").encode())
                await writer.drain()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        conn = UpstreamConnection("127.0.0.1", port)
        reentered = asyncio.Event()

        async def notif_cb(msg):
            # Re-entrant call on the same connection — the deadlock trigger.
            await conn.call("blockchain.block.headers", [1, 1])
            reentered.set()

        conn.set_notification_callback(notif_cb)
        await conn.connect()
        try:
            # Generous ceiling but far below the 120s per-method timeout the
            # deadlock would otherwise hit.
            await asyncio.wait_for(reentered.wait(), timeout=5)
        finally:
            await conn.close()
            server.close()  # not wait_closed(): it hangs on lingering conns in py3.12
        assert reentered.is_set()

    asyncio.run(scenario())


def test_passthrough_responses_keep_arrival_order():
    """Passthrough responses (wallet's own requests) must reach the client in the
    order upstream sent them — the single FIFO dispatch worker guarantees it."""

    async def scenario():
        seen = []

        async def handle(reader, writer):
            while True:
                line = await reader.readline()
                if not line:
                    break
                req = json.loads(line)
                resp = {"jsonrpc": "2.0", "id": req["id"], "result": req["id"]}
                writer.write((json.dumps(resp) + "\n").encode())
                await writer.drain()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        conn = UpstreamConnection("127.0.0.1", port)
        done = asyncio.Event()

        async def passthrough_cb(msg):
            seen.append(msg["id"])
            if len(seen) == 5:
                done.set()

        conn.set_passthrough_callback(passthrough_cb)
        await conn.connect()
        try:
            # Client-forwarded requests use low IDs (passthrough range).
            for i in range(1, 6):
                await conn.send_raw((json.dumps({"id": i, "method": "x", "params": []}) + "\n").encode())
            await asyncio.wait_for(done.wait(), timeout=5)
        finally:
            await conn.close()
            server.close()  # not wait_closed(): it hangs on lingering conns in py3.12
        assert seen == [1, 2, 3, 4, 5]

    asyncio.run(scenario())


# ------------------------------------------------------------------ Fix #2
class _ConflictStore:
    def __init__(self, inputs):
        self._inputs = inputs
        self.status_updates = []

    def get_active_txs(self):
        return [SimpleNamespace(txid="a" * 64)]

    def get_inputs(self, txid):
        return self._inputs

    def update_status(self, txid, status, **kw):
        self.status_updates.append((txid, status))

    def get_scripthashes_for_tx(self, txid):
        return set()


class _ReplyUpstream:
    def __init__(self, resp):
        self._resp = resp

    async def call(self, method, params=None):
        return self._resp


def _input():
    return SimpleNamespace(prev_txid="b" * 64, prev_vout=0, scripthash="c" * 64)


def test_conflict_not_abandoned_on_electrs_error():
    # electrs returns a JSON-RPC error → status is UNKNOWN, tx must survive.
    store = _ConflictStore([_input()])
    s = _sched(upstream=_ReplyUpstream({"error": {"code": 1, "message": "history too large"}}),
               store=store)
    asyncio.run(s._detect_conflicts())
    assert store.status_updates == []  # never marked abandoned


def test_conflict_not_abandoned_on_missing_result():
    store = _ConflictStore([_input()])
    s = _sched(upstream=_ReplyUpstream({}), store=store)  # neither result nor error
    asyncio.run(s._detect_conflicts())
    assert store.status_updates == []


def test_conflict_abandoned_when_utxo_really_gone():
    # A clean empty result (UTXO genuinely spent elsewhere) still abandons.
    store = _ConflictStore([_input()])
    s = _sched(upstream=_ReplyUpstream({"result": []}), store=store)
    asyncio.run(s._detect_conflicts())
    assert ("a" * 64, "abandoned") in store.status_updates


def test_conflict_kept_when_utxo_present():
    store = _ConflictStore([_input()])
    s = _sched(upstream=_ReplyUpstream({"result": [{"tx_hash": "b" * 64, "tx_pos": 0}]}),
               store=store)
    asyncio.run(s._detect_conflicts())
    assert store.status_updates == []


# ------------------------------------------------------------------ Fix #3
class _TimestampStore:
    def __init__(self, txs):
        self._txs = txs

    def get_all_txs(self, status=None, network=None):
        return [t for t in self._txs if status is None or t.status == status]

    def get_raw_hex(self, txid):
        return "rawhex-" + txid


def _stx(txid, target_block=None, target_price=None):
    return SimpleNamespace(txid=txid, status="scheduled",
                           target_block=target_block, target_price=target_price)


def test_timestamp_broadcast_skips_block_and_price_scheduled(monkeypatch):
    # parse_raw_tx is imported inside the function; patch it on the module so a
    # timestamp locktime (>= threshold) is reported for any raw hex.
    monkeypatch.setattr("src.pool.tx_parser.parse_raw_tx",
                        lambda raw: SimpleNamespace(locktime=1_700_000_000))

    pure = _stx("a" * 64)                       # eligible (no explicit trigger)
    by_block = _stx("b" * 64, target_block=950_000)
    by_price = _stx("c" * 64, target_price=150_000.0)
    store = _TimestampStore([pure, by_block, by_price])
    s = _sched(store=store)

    broadcast = []

    async def fake_do_broadcast(tx):
        broadcast.append(tx.txid)
        return {"result": "ok"}

    s._do_broadcast = fake_do_broadcast
    # MTP well past the timestamp locktime → the pure tx is due.
    asyncio.run(s._broadcast_due_by_timestamp(1_700_000_100))

    assert broadcast == ["a" * 64]  # only the pure timestamp schedule fired


# ------------------------------------------------------------------ Fix #4
@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(config, "APP_SEED", "critical-fixes-seed-aaaa")
    crypto._derived_key = None
    s = TxStore(init_db(":memory:"))
    s.network = "mainnet"
    yield s
    crypto._derived_key = None


def _row(store, txid):
    return store._conn.execute(
        "SELECT target_block, target_price, expires_at, price_direction FROM retained_txs WHERE txid = ?",
        (txid,),
    ).fetchone()


def _insert(store, txid):
    store._conn.execute(
        "INSERT INTO retained_txs (txid, raw_hex, fee_sats, fee_rate, vsize, network, status) "
        "VALUES (?, '00', 0, 0, 100, 'mainnet', 'pending')",
        (txid,),
    )
    store._conn.commit()


def test_setting_block_trigger_clears_price_trigger(store):
    txid = "d" * 64
    _insert(store, txid)
    store.update_target_price(txid, 150_000.0, direction="below", expires_at="2030-01-01T00:00:00")
    # Re-schedule by block: the price trigger and its expiry must be gone.
    store.update_target_block(txid, 950_000)
    row = _row(store, txid)
    assert row["target_block"] == 950_000
    assert row["target_price"] is None
    assert row["expires_at"] is None


def test_setting_price_trigger_clears_block_trigger(store):
    txid = "e" * 64
    _insert(store, txid)
    store.update_target_block(txid, 950_000)
    store.update_target_price(txid, 120_000.0, direction="above")
    row = _row(store, txid)
    assert row["target_price"] == 120_000.0
    assert row["target_block"] is None


def test_keep_status_block_update_also_clears_price(store):
    # The import path uses keep_status=True; it must clear price too.
    txid = "f" * 64
    _insert(store, txid)
    store.update_target_price(txid, 150_000.0, expires_at="2030-01-01T00:00:00")
    store.update_target_block(txid, 950_000, keep_status=True)
    row = _row(store, txid)
    assert row["target_block"] == 950_000
    assert row["target_price"] is None
    assert row["expires_at"] is None
