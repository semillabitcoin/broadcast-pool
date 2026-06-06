"""Privacy-preserving diagnostics: in-memory event log + Electrum method stats.

Everything stored here is meant to be downloadable and SHAREABLE in public
(support requests, GitHub issues), so records are sanitized aggressively:
no txids, scripthashes, addresses, raw tx hex, xpubs, npubs or IPs survive.
Method names, latencies, counts and error shapes do — which is what's needed
to debug connectivity/indexing problems.
"""

import logging
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone

# Order matters: longest/most specific patterns first.
_SANITIZERS = [
    (re.compile(r"\b[0-9a-fA-F]{64}\b"), "<hash64>"),          # txid / scripthash / header hash
    (re.compile(r"\b[0-9a-fA-F]{20,}\b"), "<hex>"),            # raw tx fragments, pubkeys
    (re.compile(r"\b(?:bc1|tb1|bcrt1)[ac-hj-np-z02-9]{6,}\b", re.I), "<address>"),
    (re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b"), "<address>"),   # legacy base58
    (re.compile(r"\b[xyztuv]p(?:ub|rv)[1-9A-HJ-NP-Za-km-z]{20,}\b"), "<xpub>"),
    (re.compile(r"\bn(?:pub|sec|profile|event)1[ac-hj-np-z02-9]{6,}\b", re.I), "<nostr>"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<ip>"),
    (re.compile(r"[a-z2-7]{16,56}\.onion\b", re.I), "<onion>"),
]

_MAX_EVENTS = 1500
# The report only includes events from this window back. Debugging flow is
# "reproduce the issue, then download" — older history adds nothing and the
# less it carries, the safer it is to share.
EVENT_WINDOW_S = 600  # 10 minutes


def sanitize(text: str) -> str:
    """Strip anything privacy-sensitive from a log line."""
    for pattern, repl in _SANITIZERS:
        text = pattern.sub(repl, text)
    return text


class _MethodStats:
    """Aggregated latency/error stats per Electrum method (no payloads)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stats: dict[str, dict] = {}

    def record(self, method: str, ms: float, ok: bool) -> None:
        with self._lock:
            s = self._stats.setdefault(method, {
                "count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0,
            })
            s["count"] += 1
            s["total_ms"] += ms
            s["max_ms"] = max(s["max_ms"], ms)
            if not ok:
                s["errors"] += 1

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                m: {
                    "count": s["count"],
                    "errors": s["errors"],
                    "avg_ms": round(s["total_ms"] / s["count"], 1) if s["count"] else 0,
                    "max_ms": round(s["max_ms"], 1),
                }
                for m, s in sorted(self._stats.items())
            }


class RingLogHandler(logging.Handler):
    """Keeps the last N log records, sanitized, for the diagnostics report."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        # (monotonic_ts, sanitized_line) — monotonic so the window filter
        # survives wall-clock jumps
        self.events: deque[tuple[float, str]] = deque(maxlen=_MAX_EVENTS)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            line = f"{ts} [{record.name}] {record.levelname}: {record.getMessage()}"
            self.events.append((time.monotonic(), sanitize(line)))
        except Exception:
            pass  # diagnostics must never break the app

    def recent(self, window_s: float = EVENT_WINDOW_S) -> list[str]:
        cutoff = time.monotonic() - window_s
        return [line for t, line in self.events if t >= cutoff]


# Module-level singletons, wired into logging by main.py
ring_handler = RingLogHandler()
upstream_stats = _MethodStats()
_started_at = time.monotonic()


def record_upstream_call(method: str, ms: float, ok: bool) -> None:
    upstream_stats.record(method, ms, ok)


def event(message: str) -> None:
    """Record a structured diagnostics event outside the logging system."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ring_handler.events.append(
        (time.monotonic(), sanitize(f"{ts} [diagnostics] EVENT: {message}"))
    )


def uptime_seconds() -> int:
    return int(time.monotonic() - _started_at)


def build_report(extra_info: dict | None = None) -> str:
    """Assemble the downloadable plain-text report."""
    lines = [
        "# Broadcast Pool — diagnostics report",
        f"# generated_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"# uptime_s: {uptime_seconds()}",
        "# privacy: txids, scripthashes, addresses, hex, xpubs, nostr keys,",
        "#          IPs and onions are redacted at capture time.",
        "",
    ]
    for key, value in (extra_info or {}).items():
        lines.append(f"{key}: {value}")

    lines.append("")
    lines.append("## upstream method stats (count / errors / avg ms / max ms)")
    stats = upstream_stats.snapshot()
    if not stats:
        lines.append("(no upstream calls recorded)")
    for method, s in stats.items():
        lines.append(
            f"{method:45s} {s['count']:6d} {s['errors']:5d} {s['avg_ms']:9.1f} {s['max_ms']:9.1f}"
        )

    recent = ring_handler.recent()
    lines.append("")
    lines.append(f"## events from the last {EVENT_WINDOW_S // 60} minutes (sanitized)")
    if not recent:
        lines.append("(no events in window — reproduce the issue, then download again)")
    lines.extend(recent)
    lines.append("")
    return "\n".join(lines)
