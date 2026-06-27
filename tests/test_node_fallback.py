"""Tests for the Bitcoin node RPC fallback (electrs down).

Covers error classification, the electrs→node relay fallback in _relay_raw,
the outcome handling in _do_broadcast, and NodeRPC.from_config gating.
"""
import asyncio
from types import SimpleNamespace

import pytest

from src.scheduler.scheduler import Scheduler
from src.pool.node_rpc import NodeRPC, NodeRPCError, NodeRPCTransportError


# --------------------------------------------------------------------- fakes
class FakeUpstream:
    def __init__(self, result=None, raises=None, error=None):
        self._result = result
        self._raises = raises
        self._error = error
        self.calls = []

    async def call(self, method, params=None):
        self.calls.append((method, params))
        if self._raises:
            raise self._raises
        if self._error is not None:
            return {"error": {"message": self._error}}
        return {"result": self._result}


class FakeNode:
    def __init__(self, send_result=None, send_raises=None, health_info=None):
        self._send_result = send_result
        self._send_raises = send_raises
        self._health_info = health_info
        self.sent = []

    async def sendrawtransaction(self, raw_hex):
        self.sent.append(raw_hex)
        if self._send_raises:
            raise self._send_raises
        return self._send_result

    async def health(self):
        return self._health_info


class FakeStore:
    def __init__(self, height=953839):
        self.status_updates = []
        self.broadcast_times = []
        self.state = {}
        self._height = height

    def update_status(self, txid, status, **kw):
        self.status_updates.append((txid, status))

    def update_broadcast_time(self, txid):
        self.broadcast_times.append(txid)

    def get_scripthashes_for_tx(self, txid):
        return set()

    def get_tx(self, txid):
        return None

    def get_current_height(self):
        return self._height

    def get_raw_hex(self, txid):
        return "deadbeef"

    def update_target_block(self, *a, **kw):
        pass

    def set_state(self, k, v):
        self.state[k] = v

    def get_state(self, k):
        return self.state.get(k)


def _sched(upstream=None, node=None, store=None):
    s = Scheduler.__new__(Scheduler)
    s._upstream = upstream
    s._node = node
    s.store = store or FakeStore()
    s.notify_callback = None
    return s


def _tx():
    return SimpleNamespace(txid="a" * 64, status="scheduled", depends_on=None,
                           target_block=None, locktime=0, expires_at=None)


# ---------------------------------------------------- error classification
def test_classify_electrum_already():
    out = Scheduler._classify_electrum_send_error("Transaction already in block chain")
    assert out["kind"] == "already"


def test_classify_electrum_spent():
    out = Scheduler._classify_electrum_send_error("bad-txns-inputs-missingorspent")
    assert out["kind"] == "reject" and out["spent"] is True


def test_classify_electrum_policy_failed():
    out = Scheduler._classify_electrum_send_error("min relay fee not met")
    assert out["kind"] == "reject" and out["spent"] is False


def test_classify_node_already_by_code():
    out = Scheduler._classify_node_send_error(NodeRPCError(-27, "already in block chain"))
    assert out["kind"] == "already"


def test_classify_node_missing_inputs_is_spent():
    out = Scheduler._classify_node_send_error(NodeRPCError(-25, "Missing inputs"))
    assert out["kind"] == "reject" and out["spent"] is True


def test_classify_node_policy_failed():
    out = Scheduler._classify_node_send_error(NodeRPCError(-26, "dust"))
    assert out["kind"] == "reject" and out["spent"] is False


def test_classify_node_transport_is_unreachable():
    out = Scheduler._classify_node_send_error(NodeRPCTransportError("RPC transport error"))
    assert out["kind"] == "unreachable"


def test_is_txindex_missing():
    # The 'enable -txindex' hint from getrawtransaction must be recognized…
    e = NodeRPCError(-5, "No such mempool transaction. Use -txindex to enable "
                         "blockchain transaction queries.")
    assert Scheduler._is_txindex_missing(e) is True
    # …but a generic not-found (txindex on, tx simply absent) must not be.
    assert Scheduler._is_txindex_missing(NodeRPCError(-5, "No such transaction")) is False


# ----------------------------------------------------------- _relay_raw
def test_relay_electrs_success():
    s = _sched(upstream=FakeUpstream(result="txid-electrs"))
    out = asyncio.run(s._relay_raw("deadbeef"))
    assert out == {"kind": "success", "txid": "txid-electrs", "via": "electrs"}


def test_relay_falls_back_to_node_when_electrs_raises():
    up = FakeUpstream(raises=ConnectionError("electrs down"))
    node = FakeNode(send_result="txid-node")
    s = _sched(upstream=up, node=node)
    out = asyncio.run(s._relay_raw("deadbeef"))
    assert out["via"] == "node" and out["kind"] == "success"
    assert node.sent == ["deadbeef"]


def test_relay_uses_node_when_no_upstream():
    node = FakeNode(send_result="txid-node")
    s = _sched(upstream=None, node=node)
    out = asyncio.run(s._relay_raw("deadbeef"))
    assert out["via"] == "node" and out["kind"] == "success"


def test_relay_node_reject_spent():
    up = FakeUpstream(raises=ConnectionError("down"))
    node = FakeNode(send_raises=NodeRPCError(-25, "Missing inputs"))
    s = _sched(upstream=up, node=node)
    out = asyncio.run(s._relay_raw("deadbeef"))
    assert out["kind"] == "reject" and out["spent"] is True


def test_relay_unreachable_when_both_fail():
    up = FakeUpstream(raises=ConnectionError("down"))
    node = FakeNode(send_raises=NodeRPCTransportError("transport"))
    s = _sched(upstream=up, node=node)
    out = asyncio.run(s._relay_raw("deadbeef"))
    assert out["kind"] == "unreachable"


def test_relay_unreachable_when_no_transport():
    s = _sched(upstream=None, node=None)
    out = asyncio.run(s._relay_raw("deadbeef"))
    assert out["kind"] == "unreachable"


# ------------------------------------------------------- _do_broadcast outcomes
def test_do_broadcast_success_marks_broadcast_time():
    store = FakeStore()
    s = _sched(upstream=FakeUpstream(result="txid-ok"), store=store)
    out = asyncio.run(s._do_broadcast(_tx()))
    assert "error" not in out
    assert store.broadcast_times == ["a" * 64]


def test_do_broadcast_reject_marks_failed():
    store = FakeStore()
    up = FakeUpstream(raises=ConnectionError("down"))
    node = FakeNode(send_raises=NodeRPCError(-26, "non-final"))
    s = _sched(upstream=up, node=node, store=store)
    out = asyncio.run(s._do_broadcast(_tx()))
    assert "error" in out
    assert ("a" * 64, "failed") in store.status_updates


def test_do_broadcast_rejects_expired_on_automatic_path():
    # The automatic paths call _do_broadcast() directly (not broadcast_now()).
    # The centralized policy gate must still refuse an expired tx and never relay it.
    store = FakeStore()
    up = FakeUpstream(result="should-not-be-sent")
    s = _sched(upstream=up, store=store)
    tx = _tx()
    tx.expires_at = "2020-01-01T00:00:00"  # long past
    out = asyncio.run(s._do_broadcast(tx))
    assert "expired" in out["error"]
    assert up.calls == []  # never reached the relay
    assert ("a" * 64, "expired") in store.status_updates


def test_do_broadcast_unreachable_keeps_broadcasting():
    store = FakeStore()
    up = FakeUpstream(raises=ConnectionError("down"))
    node = FakeNode(send_raises=NodeRPCTransportError("transport"))
    s = _sched(upstream=up, node=node, store=store)
    out = asyncio.run(s._do_broadcast(_tx()))
    # Not a definitive failure → keep 'broadcasting', report as warning.
    assert out.get("warning")
    assert ("a" * 64, "broadcasting") in store.status_updates
    assert all(st != "failed" for _, st in store.status_updates)


# ------------------------------------------------------- _node_fallback_tick
async def _noop(*a, **kw):
    return None


def test_node_fallback_tick_refreshes_chain_state_from_node():
    store = FakeStore(height=900000)
    node = FakeNode(health_info={"blocks": 953900, "mediantime": 1700000000})
    s = _sched(upstream=None, node=node, store=store)
    # Isolate from the downstream broadcast/confirmation orchestration.
    s._broadcast_due_by_block = _noop
    s._broadcast_due_by_timestamp = _noop
    s._check_price_triggers = _noop
    s._purge_expired_txs = lambda: None
    s._check_confirmations = _noop

    asyncio.run(s._node_fallback_tick())

    assert store.state["current_height"] == "953900"
    assert store.state["current_mtp"] == "1700000000"
    assert s.node_fallback_active is True
    assert s.node_reachable is True  # a successful tick proves the node is reachable


def test_node_fallback_tick_noop_when_node_unreachable():
    store = FakeStore(height=900000)
    node = FakeNode(health_info=None)  # health() returns None → unreachable
    s = _sched(upstream=None, node=node, store=store)
    s.node_fallback_active = False
    asyncio.run(s._node_fallback_tick())
    assert "current_height" not in store.state
    assert s.node_fallback_active is False
    assert s.node_reachable is False  # unreachable node is reflected for the UI badge


# ------------------------------------------------------- NodeRPC.from_config
def test_from_config_disabled_without_host(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "BITCOIN_RPC_HOST", "")
    assert NodeRPC.from_config() is None


def test_from_config_requires_credentials(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "BITCOIN_RPC_HOST", "10.0.0.1")
    monkeypatch.setattr(config, "BITCOIN_RPC_USER", "")
    monkeypatch.setattr(config, "BITCOIN_RPC_PASS", "")
    monkeypatch.setattr(config, "BITCOIN_RPC_COOKIE_FILE", "")
    assert NodeRPC.from_config() is None


def test_from_config_enabled_with_userpass(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "BITCOIN_RPC_HOST", "10.0.0.1")
    monkeypatch.setattr(config, "BITCOIN_RPC_PORT", 8332)
    monkeypatch.setattr(config, "BITCOIN_RPC_USER", "u")
    monkeypatch.setattr(config, "BITCOIN_RPC_PASS", "p")
    monkeypatch.setattr(config, "BITCOIN_RPC_COOKIE_FILE", "")
    node = NodeRPC.from_config()
    assert node is not None and node.host == "10.0.0.1" and node.port == 8332
