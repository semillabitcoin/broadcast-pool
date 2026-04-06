"""ElectrumSession — handles one wallet TCP connection."""

import asyncio
import json
import logging

from src.proxy.interceptor import Interceptor
from src.proxy.upstream import UpstreamConnection
from src.pool.store import TxStore
from src.pool.virtual_mempool import VirtualMempool
from src import config

log = logging.getLogger(__name__)


class ElectrumSession:
    """Manages a single wallet connection with upstream proxying."""

    def __init__(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        store: TxStore,
        on_close=None,
    ):
        self.client_reader = client_reader
        self.client_writer = client_writer
        self.store = store
        self.on_close = on_close

        self.upstream: UpstreamConnection | None = None
        self.vmempool = VirtualMempool(store)
        self.interceptor: Interceptor | None = None

        self.subscribed_scripthashes: set[str] = set()
        # Track which client request IDs need response modification
        self._pending_methods: dict[int, tuple[str, list]] = {}
        self._closed = False

        # Liana height-offset state (PoC: fake future block height)
        self._liana_offset: int = 0  # 0 = disabled
        self._real_tip_height: int | None = None
        self._real_tip_header: str | None = None
        self._fake_chain: list[bytes] = []  # cached fake headers
        self._liana_increment_task: asyncio.Task | None = None

        peer = client_writer.get_extra_info("peername")
        self.peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"

    async def run(self) -> None:
        """Main session loop: connect upstream, then proxy bidirectionally."""
        try:
            host, port, use_ssl = self.store.get_upstream()
            self.upstream = UpstreamConnection(host, port, use_ssl=use_ssl)

            backoff = 1
            while not self._closed:
                try:
                    await self.upstream.connect()
                    backoff = 1
                    break
                except (OSError, ConnectionRefusedError) as e:
                    log.warning("[%s] upstream connect failed, retry in %ds: %s",
                                self.peer_str, backoff, e)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 10)

            if self._closed:
                return

            # Set up callbacks:
            # - notification_callback: server push (subscriptions)
            # - passthrough_callback: responses to client-forwarded requests
            self.upstream.set_notification_callback(self._on_upstream_notification)
            self.upstream.set_passthrough_callback(self._on_upstream_response)
            self.interceptor = Interceptor(self.store, self.vmempool, self.upstream)

            log.info("[%s] Session started (upstream %s:%d)", self.peer_str, host, port)

            await self._client_read_loop()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("[%s] Session error: %s", self.peer_str, e, exc_info=True)
        finally:
            await self._close()

    async def send_to_client(self, msg: dict) -> None:
        """Send a JSON message to the connected wallet."""
        if self._closed:
            return
        try:
            line = json.dumps(msg) + "\n"
            self.client_writer.write(line.encode())
            await self.client_writer.drain()
        except Exception as e:
            log.warning("[%s] Failed to send to client: %s", self.peer_str, e)

    # ---- Client → Proxy ----

    async def _client_read_loop(self) -> None:
        """Read JSON-RPC messages from the wallet client."""
        while True:
            line = await self.client_reader.readline()
            if not line:
                log.info("[%s] Client disconnected (EOF)", self.peer_str)
                break

            line_str = line.decode().strip()
            if not line_str:
                continue

            if line_str.startswith("["):
                await self._handle_batch(line_str)
                continue

            try:
                msg = json.loads(line_str)
            except json.JSONDecodeError:
                log.warning("[%s] Invalid JSON from client (%d bytes)",
                            self.peer_str, len(line_str))
                continue

            await self._handle_client_message(msg)

    def _is_liana(self) -> bool:
        return bool(
            self.interceptor
            and self.interceptor.wallet_label
            and "liana" in self.interceptor.wallet_label.lower()
        )

    def _load_liana_offset(self) -> int:
        """Read offset from store. Only applies to Liana sessions."""
        if not self._is_liana():
            return 0
        raw = self.store.get_state("liana_height_offset") or "0"
        try:
            return max(0, min(70000, int(raw)))  # cap ~15 months
        except ValueError:
            return 0

    def _rebuild_fake_chain(self, real_tip_height: int, real_tip_header_hex: str) -> None:
        """Generate fake header chain from current real tip."""
        from src.proxy.header_faker import generate_fake_chain
        self._real_tip_height = real_tip_height
        self._real_tip_header = real_tip_header_hex
        self._liana_offset = self._load_liana_offset()
        if self._liana_offset > 0:
            self._fake_chain = generate_fake_chain(real_tip_header_hex, self._liana_offset)
            log.warning(
                "[%s] EXPERIMENTAL: serving fake tip %d (real %d, offset %d) to Liana",
                self.peer_str,
                real_tip_height + self._liana_offset,
                real_tip_height,
                self._liana_offset,
            )
            # Start auto-increment task if configured
            rate_raw = self.store.get_state("liana_increment_rate") or "0"
            try:
                rate = int(rate_raw)
            except ValueError:
                rate = 0
            if self._liana_increment_task:
                self._liana_increment_task.cancel()
                self._liana_increment_task = None
            if rate > 0:
                self._liana_increment_task = asyncio.create_task(self._auto_increment_loop(rate))
        else:
            self._fake_chain = []

    async def _auto_increment_loop(self, rate_seconds: int) -> None:
        """Periodically extend fake chain by 1 block and notify Liana."""
        from src.proxy.header_faker import sha256d, build_header, parse_header
        try:
            while not self._closed and self._fake_chain:
                await asyncio.sleep(rate_seconds)
                if not self._fake_chain or self._real_tip_height is None:
                    break
                # Build new fake header chaining from last
                last = self._fake_chain[-1]
                last_parsed = parse_header(last.hex())
                new_header = build_header(
                    version=4,
                    prev_hash=sha256d(last),
                    merkle_root=b"\x00" * 32,
                    time=last_parsed["time"] + 600,
                    bits=last_parsed["bits"],
                    nonce=0,
                )
                self._fake_chain.append(new_header)
                self._liana_offset += 1
                new_tip_height = self._real_tip_height + self._liana_offset
                # Push notification to Liana
                notif = {
                    "jsonrpc": "2.0",
                    "method": "blockchain.headers.subscribe",
                    "params": [{"height": new_tip_height, "hex": new_header.hex()}],
                }
                await self.send_to_client(notif)
                log.debug("[%s] Auto-advanced fake tip to %d", self.peer_str, new_tip_height)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning("[%s] Auto-increment error: %s", self.peer_str, e)

    def _fake_header_at(self, height: int) -> str | None:
        """Return fake header hex for a height in the offset range, or None."""
        if not self._fake_chain or self._real_tip_height is None:
            return None
        idx = height - self._real_tip_height - 1
        if 0 <= idx < len(self._fake_chain):
            return self._fake_chain[idx].hex()
        return None

    async def _handle_client_message(self, msg: dict, collect: bool = False):
        """Process a single client message."""
        method = msg.get("method", "")
        params = msg.get("params", [])
        msg_id = msg.get("id")

        log.debug("[%s] client >> id=%s %s(%s)",
                  self.peer_str, msg_id, method, str(params)[:60])

        # --- Capture wallet label ---
        if self.interceptor and not self.interceptor.wallet_label:
            if method == "server.version" and params:
                client_name = params[0] if params else ""
                name_lower = client_name.lower()
                if "sparrow" in name_lower:
                    self.interceptor.wallet_label = client_name
                elif "liana" in name_lower:
                    self.interceptor.wallet_label = client_name
                elif "nunchuk" in name_lower:
                    self.interceptor.wallet_label = client_name
                else:
                    self.interceptor.wallet_label = client_name
                log.info("[%s] Wallet identified: %s", self.peer_str, self.interceptor.wallet_label)

            # Liana detection: electrum-client Rust skips server.version,
            # first message is blockchain.block.header(0) for genesis check
            elif method == "blockchain.block.header" and params and params[0] == 0:
                self.interceptor.wallet_label = "Liana"
                log.info("[%s] Wallet identified by pattern: Liana", self.peer_str)

        # --- INTERCEPTED: server.banner ---
        if method == "server.banner":
            banner = "\n".join([
                "",
                "        ####    #####  #####",
                " #####  #####     #    ##",
                " ##     ##  ##    #    ##",
                " #####  #####     #    #####",
                "    ##",
                " #####",
                "",
                " Broadcast Pool v0.1.0",
                " by Semilla Bitcoin",
                "",
                " An Electrum proxy to schedule",
                " and delay transaction broadcasts.",
                "",
                " Inspired by Craig Raw's Broadcast Pool",
                " proposal (bitcoin/bitcoin#30471).",
                "",
                " https://semillabitcoin.com",
            ])
            response = {"jsonrpc": "2.0", "result": banner, "id": msg_id}
            if collect:
                return response
            await self.send_to_client(response)
            return

        # --- INTERCEPTED: server.version — inject our name ---
        if method == "server.version" and params:
            # Forward to upstream to get protocol version, then replace server name
            self._pending_methods[msg_id] = ("server.version", params)
            raw = json.dumps(msg) + "\n"
            await self.upstream.send_raw(raw.encode())
            return None if collect else None

        # --- INTERCEPTED: transaction.get for retained txs ---
        if method == "blockchain.transaction.get" and params:
            requested_txid = params[0]
            retained = self.store.get_tx(requested_txid)
            if retained and retained.status in ("pending", "scheduled", "broadcasting"):
                verbose = params[1] if len(params) > 1 else False
                if not verbose:
                    # Return raw hex directly
                    response = {"jsonrpc": "2.0", "result": self.store.get_raw_hex(retained.txid), "id": msg_id}
                    log.debug("[%s] Serving retained tx %s from pool", self.peer_str, requested_txid[:16])
                    if collect:
                        return response
                    await self.send_to_client(response)
                    return
                # verbose=true: fall through to upstream (which may not have it)

        # --- LIANA HEIGHT-OFFSET PoC: intercept block headers ---
        if self._is_liana() and self._load_liana_offset() > 0:
            # block.header(N) — serve fake from cache if N > real_tip
            if method == "blockchain.block.header" and params:
                requested_height = params[0]
                if self._real_tip_height is not None and requested_height > self._real_tip_height:
                    fake_hex = self._fake_header_at(requested_height)
                    if fake_hex:
                        response = {"jsonrpc": "2.0", "result": fake_hex, "id": msg_id}
                        if collect:
                            return response
                        await self.send_to_client(response)
                        return

            # block.headers(start, count) — serve fake range
            if method == "blockchain.block.headers" and len(params) >= 2:
                start = params[0]
                count = params[1]
                if self._real_tip_height is not None and start > self._real_tip_height:
                    headers_hex = ""
                    actual = 0
                    for i in range(count):
                        h = self._fake_header_at(start + i)
                        if h:
                            headers_hex += h
                            actual += 1
                    response = {
                        "jsonrpc": "2.0",
                        "result": {"hex": headers_hex, "count": actual, "max": 2016},
                        "id": msg_id,
                    }
                    if collect:
                        return response
                    await self.send_to_client(response)
                    return

            # headers.subscribe — track for response modification
            if method == "blockchain.headers.subscribe":
                self._pending_methods[msg_id] = ("blockchain.headers.subscribe", [])

        # --- INTERCEPTED: broadcast ---
        if method == "blockchain.transaction.broadcast":
            log.info("[%s] Intercepting broadcast (id=%s)", self.peer_str, msg_id)
            response = await self.interceptor.intercept_broadcast(params, msg_id)
            if collect:
                return response
            await self.send_to_client(response)
            affected = self.interceptor.get_affected_scripthashes(
                response.get("result", "")
            )
            await self._notify_subscriptions(affected)
            return

        # --- Track methods that need response modification ---
        if method == "blockchain.scripthash.subscribe" and params:
            self.subscribed_scripthashes.add(params[0])

        if method in (
            "blockchain.scripthash.get_history",
            "blockchain.scripthash.listunspent",
        ):
            self._pending_methods[msg_id] = (method, params)
            log.debug("[%s] Tracking id=%s for modification (%s)", self.peer_str, msg_id, method)

        # --- Forward to upstream (raw, preserving client's id) ---
        raw = json.dumps(msg) + "\n"
        await self.upstream.send_raw(raw.encode())
        return None if collect else None

    # ---- Upstream → Client ----

    async def _on_upstream_response(self, msg: dict) -> None:
        """Handle a response from upstream to a client-forwarded request."""
        msg_id = msg.get("id")

        # Check if we need to modify this response
        if msg_id is not None and msg_id in self._pending_methods:
            method, params = self._pending_methods.pop(msg_id)
            scripthash = params[0] if params else ""

            log.debug("[%s] Modifying response id=%s for %s", self.peer_str, msg_id, method)

            if method == "server.version":
                # Replace server name, keep protocol version
                result = msg.get("result", [])
                if isinstance(result, list) and len(result) >= 2:
                    msg["result"] = ["Broadcast Pool v0.1.0 (Semilla Bitcoin)", result[1]]
            elif method == "blockchain.headers.subscribe":
                # Liana height-offset: rebuild fake chain from real tip and return fake tip
                result = msg.get("result", {})
                if isinstance(result, dict) and "height" in result and "hex" in result:
                    self._rebuild_fake_chain(result["height"], result["hex"])
                    if self._fake_chain:
                        fake_tip_height = result["height"] + self._liana_offset
                        fake_tip_hex = self._fake_chain[-1].hex()
                        msg["result"] = {"height": fake_tip_height, "hex": fake_tip_hex}
            elif method == "blockchain.scripthash.get_history":
                msg = self.interceptor.modify_get_history(msg, scripthash)
            elif method == "blockchain.scripthash.listunspent":
                msg = self.interceptor.modify_listunspent(msg, scripthash)
            elif method == "blockchain.scripthash.subscribe":
                msg = await self.interceptor.modify_subscribe_response(msg, scripthash)

        await self.send_to_client(msg)

    async def _on_upstream_notification(self, msg: dict) -> None:
        """Handle a server-initiated push notification from upstream."""
        notif_method = msg.get("method", "")
        notif_params = msg.get("params", [])

        log.debug("[%s] Upstream notification: %s", self.peer_str, notif_method)

        if notif_method == "blockchain.scripthash.subscribe" and notif_params:
            notif_params = await self.interceptor.modify_subscribe_notification(notif_params)
            msg["params"] = notif_params

        # Liana height-offset: rebuild fake chain on every new real block
        if (notif_method == "blockchain.headers.subscribe"
                and notif_params
                and self._is_liana()
                and self._load_liana_offset() > 0):
            try:
                header_obj = notif_params[0]
                if isinstance(header_obj, dict) and "height" in header_obj and "hex" in header_obj:
                    self._rebuild_fake_chain(header_obj["height"], header_obj["hex"])
                    if self._fake_chain:
                        fake_tip_height = header_obj["height"] + self._liana_offset
                        fake_tip_hex = self._fake_chain[-1].hex()
                        msg["params"] = [{"height": fake_tip_height, "hex": fake_tip_hex}]
            except Exception as e:
                log.warning("[%s] Failed to fake notification: %s", self.peer_str, e)

        await self.send_to_client(msg)

    # ---- Batch requests ----

    async def _handle_batch(self, line_str: str) -> None:
        """Handle a JSON-RPC batch request."""
        try:
            batch = json.loads(line_str)
        except json.JSONDecodeError:
            return

        log.debug("[%s] Batch request: %d items", self.peer_str, len(batch))

        responses = []
        for msg in batch:
            method = msg.get("method", "")
            params = msg.get("params", [])
            msg_id = msg.get("id")

            resp = None

            if method == "blockchain.transaction.broadcast":
                resp = await self.interceptor.intercept_broadcast(params, msg_id)
            elif method == "blockchain.transaction.get" and params:
                # Check if this is a retained tx
                retained = self.store.get_tx(params[0])
                verbose = params[1] if len(params) > 1 else False
                if retained and retained.status in ("pending", "scheduled", "broadcasting") and not verbose:
                    resp = {"jsonrpc": "2.0", "result": self.store.get_raw_hex(retained.txid), "id": msg_id}
                else:
                    resp = None  # Fall through to upstream below

            if resp is None:
                try:
                    upstream_resp = await self.upstream.call(method, params)
                    upstream_resp["id"] = msg_id

                    scripthash = params[0] if params else ""
                    if method == "blockchain.scripthash.subscribe" and params:
                        self.subscribed_scripthashes.add(scripthash)
                    if method == "blockchain.scripthash.get_history":
                        upstream_resp = self.interceptor.modify_get_history(upstream_resp, scripthash)
                    elif method == "blockchain.scripthash.listunspent":
                        upstream_resp = self.interceptor.modify_listunspent(upstream_resp, scripthash)
                    elif method == "blockchain.scripthash.subscribe":
                        upstream_resp = await self.interceptor.modify_subscribe_response(upstream_resp, scripthash)

                    resp = upstream_resp
                except Exception as e:
                    log.warning("[%s] Batch item %s failed: %s", self.peer_str, method, e)
                    log.warning("[%s] Batch item %s error: %s", self.peer_str, method, e)
                    resp = {"jsonrpc": "2.0", "error": {"code": -1, "message": "Request failed"}, "id": msg_id}

            responses.append(resp)

        if responses:
            out = json.dumps(responses) + "\n"
            self.client_writer.write(out.encode())
            await self.client_writer.drain()

    # ---- Subscription notifications ----

    async def _notify_subscriptions(self, scripthashes: set[str]) -> None:
        """Send subscription notifications for affected scripthashes."""
        for sh in scripthashes:
            if sh in self.subscribed_scripthashes:
                try:
                    history_resp = await self.upstream.call(
                        "blockchain.scripthash.get_history", [sh]
                    )
                    real_history = history_resp.get("result", [])
                    new_hash = self.vmempool.compute_modified_status_hash(real_history, sh)

                    notification = {
                        "jsonrpc": "2.0",
                        "method": "blockchain.scripthash.subscribe",
                        "params": [sh, new_hash],
                    }
                    await self.send_to_client(notification)
                except Exception as e:
                    log.warning("[%s] Failed to notify subscription %s: %s",
                                self.peer_str, sh[:16], e)

    # ---- Cleanup ----

    async def _close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._liana_increment_task:
            self._liana_increment_task.cancel()

        pending_count = len(self._pending_methods)
        if pending_count:
            log.warning("[%s] Closing with %d pending tracked requests",
                        self.peer_str, pending_count)

        if self.upstream:
            await self.upstream.close()

        try:
            self.client_writer.close()
            await self.client_writer.wait_closed()
        except Exception:
            pass

        log.info("[%s] Session closed", self.peer_str)

        if self.on_close:
            self.on_close(self)
