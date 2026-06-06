"""Upstream connection to real Electrs/Fulcrum server."""

import asyncio
import json
import logging
import ssl
import time

from src import diagnostics

log = logging.getLogger(__name__)

# Internal IDs start at 1,000,000 to avoid collision with client IDs (typically 1-999)
_INTERNAL_ID_OFFSET = 1_000_000

# Per-method timeouts (seconds). Header-chunk downloads (up to 2016 headers)
# can legitimately take minutes on slow/busy servers — a colleague's electrs
# hit the old flat 30s ceiling and Sparrow's initial sync stalled.
_DEFAULT_TIMEOUT = 30.0
_METHOD_TIMEOUTS = {
    "blockchain.block.headers": 120.0,
    "blockchain.block.header": 60.0,
    "blockchain.scripthash.get_history": 60.0,
}


class UpstreamConnection:
    """Manages a single TCP connection to the upstream Electrum server."""

    def __init__(self, host: str, port: int, use_ssl: bool = False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = _INTERNAL_ID_OFFSET
        self._pending: dict[int, asyncio.Future] = {}
        self._notification_callback = None
        self._passthrough_callback = None  # For forwarding non-internal responses
        self._read_task: asyncio.Task | None = None
        # Set when the read loop dies (EOF/error): new call()s fail fast
        # instead of burning their full timeout against a dead socket.
        self._dead = False

    async def connect(self) -> None:
        ssl_ctx = None
        if self.use_ssl:
            from src import config
            ssl_ctx = ssl.create_default_context()
            if config.ELECTRUM_SSL_NOVERIFY:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                log.warning("SSL CERTIFICATE VERIFICATION DISABLED — only use for testing")

        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl_ctx, limit=2**20
        )
        self._read_task = asyncio.create_task(self._read_loop())
        proto = "SSL" if self.use_ssl else "TCP"
        log.info("Connected to upstream %s:%d (%s)", self.host, self.port, proto)

    async def close(self) -> None:
        if self._read_task:
            self._read_task.cancel()
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    def set_notification_callback(self, callback) -> None:
        """Set callback for server-initiated notifications (push from subscriptions)."""
        self._notification_callback = callback

    def set_passthrough_callback(self, callback) -> None:
        """Set callback for responses to client-originated requests (forwarded raw)."""
        self._passthrough_callback = callback

    async def call(self, method: str, params: list = None) -> dict:
        """Send an internal JSON-RPC request and wait for the response.
        Uses high ID range to avoid collision with client-forwarded requests."""
        if params is None:
            params = []
        if self._dead:
            raise ConnectionError("upstream connection is closed")

        self._next_id += 1
        msg_id = self._next_id

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": msg_id,
        }

        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        line = json.dumps(request) + "\n"
        self._writer.write(line.encode())
        await self._writer.drain()

        log.debug(">> upstream [internal id=%d] %s(params=%d)", msg_id, method, len(params))

        start = time.monotonic()
        timeout = _METHOD_TIMEOUTS.get(method, _DEFAULT_TIMEOUT)
        try:
            resp = await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            diagnostics.record_upstream_call(method, (time.monotonic() - start) * 1000, ok=False)
            raise
        diagnostics.record_upstream_call(
            method, (time.monotonic() - start) * 1000, ok="error" not in resp
        )
        return resp

    async def send_raw(self, data: bytes) -> None:
        """Send raw bytes to upstream (for forwarding client requests as-is)."""
        self._writer.write(data)
        await self._writer.drain()

        log.debug(">> upstream [raw] %d bytes", len(data))

    async def _read_loop(self) -> None:
        """Read all messages from upstream and route them."""
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    log.warning("Upstream connection closed (EOF)")
                    break

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Invalid JSON from upstream (%d bytes): %s",
                                len(line), line[:200])
                    continue

                msg_id = msg.get("id")
                msg_method = msg.get("method")

                # 1. Response to an internal call() — high ID range
                if msg_id is not None and msg_id in self._pending:
                    log.debug("<< upstream [internal id=%d] result=%s err=%s",
                              msg_id,
                              str(msg.get("result", ""))[:60],
                              str(msg.get("error", ""))[:60] if "error" in msg else "none")
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        future.set_result(msg)

                # 2. Server-initiated notification (no id, has method)
                elif msg_method is not None:
                    log.debug("<< upstream [notification] %s params=%s",
                              msg_method, str(msg.get("params", ""))[:80])
                    if self._notification_callback:
                        await self._notification_callback(msg)

                # 3. Response to a client-forwarded request (low ID range) — passthrough
                elif msg_id is not None and self._passthrough_callback:
                    log.debug("<< upstream [passthrough id=%d] result_len=%d err=%s",
                              msg_id,
                              len(str(msg.get("result", ""))),
                              str(msg.get("error", ""))[:60] if "error" in msg else "none")
                    await self._passthrough_callback(msg)

                else:
                    log.warning("<< upstream [unrouted] id=%s method=%s keys=%s",
                                msg_id, msg_method, list(msg.keys()))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._dead = True
            log.error("Upstream read loop error: %s", e, exc_info=True)
            self._fail_pending(e)
        else:
            self._dead = True
            # EOF (server closed the connection): fail in-flight calls right
            # away instead of letting each one burn its full timeout — the
            # scheduler keepalive detects the disconnect on the next ping.
            self._fail_pending(ConnectionError("upstream closed connection"))

    def _fail_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()
