"""Electrum status_hash computation including retained transactions."""

import hashlib


def compute_status_hash(history: list[dict]) -> str | None:
    """Compute the Electrum status_hash for a given history.

    history: list of {"tx_hash": str, "height": int}
    Returns hex string or None if history is empty.
    """
    if not history:
        return None

    # Sort by (height, tx_hash) — unconfirmed (height <= 0) go last
    # Electrum protocol: height 0 = mempool, -1 = unconfirmed with unconfirmed parent
    sorted_history = sorted(history, key=lambda h: (h["height"], h["tx_hash"]))

    status = ""
    for h in sorted_history:
        status += h["tx_hash"] + ":" + str(h["height"]) + ":"

    return hashlib.sha256(status.encode("utf-8")).hexdigest()
