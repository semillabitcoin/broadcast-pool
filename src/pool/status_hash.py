"""Electrum status_hash computation including retained transactions."""

import hashlib


def _sort_key(h: dict):
    height = h["height"]
    if height > 0:
        return (0, height, h["tx_hash"])           # confirmed: blockchain order (by height)
    # Mempool goes AFTER confirmed. Within mempool, height 0 (all inputs
    # confirmed) before -1 (has an unconfirmed parent). tx_hash breaks ties
    # deterministically so the same set always hashes the same way.
    return (1, 0 if height == 0 else 1, h["tx_hash"])


def sort_history(history: list[dict]) -> list[dict]:
    """Order a history the Electrum way: confirmed by height, then mempool.

    Used for BOTH the status_hash and the get_history response so a wallet that
    recomputes the hash from the history it receives (e.g. Electrum desktop) gets
    the same value the subscribe notification carried. Sorting mempool first —
    the old behavior — mismatched that recomputation.
    """
    return sorted(history, key=_sort_key)


def compute_status_hash(history: list[dict]) -> str | None:
    """Compute the Electrum status_hash for a given history.

    history: list of {"tx_hash": str, "height": int}
    Returns hex string or None if history is empty.
    """
    if not history:
        return None

    status = ""
    for h in sort_history(history):
        status += h["tx_hash"] + ":" + str(h["height"]) + ":"

    return hashlib.sha256(status.encode("utf-8")).hexdigest()
