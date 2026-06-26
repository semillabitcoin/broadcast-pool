"""Regression tests for Scheduler.broadcast_now() expiry handling.

Guards against the datetime-shadowing bug where a local `from datetime import
datetime` further down broadcast_now() turned `datetime` into a function-local,
making the earlier expiry-check reference raise UnboundLocalError. That error
was caught and surfaced as "Cannot verify expiration — refusing to broadcast",
silently blocking every manual broadcast of a price-scheduled tx (which carry a
default 7-day expiry).
"""
import asyncio
from types import SimpleNamespace

from src.scheduler.scheduler import Scheduler


class _FakeStore:
    def __init__(self, tx):
        self._tx = tx
        self.updates = []

    def get_tx(self, txid):
        return self._tx

    def update_status(self, txid, status, **kw):
        self.updates.append((txid, status))

    def get_state(self, k):
        return None

    def get_current_height(self):
        return 953839


def _make_tx(expires_at, status="scheduled"):
    return SimpleNamespace(
        txid="a" * 64, status=status, expires_at=expires_at,
        locktime=0, depends_on=None, target_price=59000, price_direction="below",
    )


def _broadcast(expires_at):
    sched = Scheduler.__new__(Scheduler)
    sched.store = _FakeStore(_make_tx(expires_at))
    sched._upstream = None  # disconnected → expect the upstream guard, not an expiry error
    sched._node = None      # no Bitcoin node fallback configured
    return asyncio.run(sched.broadcast_now("a" * 64))


def test_far_future_expiry_passes_expiry_check():
    # Must clear the expiry check and reach the upstream guard — i.e. no UnboundLocalError.
    assert _broadcast("2099-01-01T00:00:00") == {"error": "Not connected to upstream"}


def test_tz_aware_z_suffixed_expiry_parses():
    assert _broadcast("2099-01-01T00:00:00Z") == {"error": "Not connected to upstream"}


def test_past_expiry_is_flagged_expired():
    result = _broadcast("2020-01-01T00:00:00")
    assert "expired" in result["error"]


def test_no_expiry_passes_through():
    assert _broadcast(None) == {"error": "Not connected to upstream"}
