"""Scheduler — monitors block height and triggers broadcasts."""

import asyncio
import hashlib
import json
import logging
import struct
from datetime import datetime, timedelta, timezone

import aiohttp

from src.pool.store import TxStore
from src.pool.node_rpc import NodeRPC, NodeRPCError, NodeRPCTransportError
from src.proxy.upstream import UpstreamConnection
from src import config

from src.pool.tx_parser import LOCKTIME_TIMESTAMP_THRESHOLD as LOCKTIME_THRESHOLD

log = logging.getLogger(__name__)


class Scheduler:
    """Watches for new blocks and broadcasts scheduled transactions."""

    def __init__(self, store: TxStore, notify_callback=None, proxy_server=None):
        self.store = store
        self.notify_callback = notify_callback  # async fn(set[str]) to notify sessions
        # ProxyServer reference: kept for future fan-out needs (not used here anymore;
        # the faker is now event-driven via Interceptor → Session → ProxyServer).
        self.proxy_server = proxy_server
        self._upstream: UpstreamConnection | None = None
        self._running = False
        self._reconnect_event = asyncio.Event()
        self._price_task: asyncio.Task | None = None
        self._node_task: asyncio.Task | None = None
        self._current_price: float | None = None
        # True only between a successful sync and the next disconnect/error.
        # Surfaced via /api/status as the UI's source of truth for the
        # connect-banner (the "network" field always carries a fallback value
        # and can NOT signal connectivity).
        self.upstream_connected = False
        # Optional Bitcoin node RPC fallback (None unless BITCOIN_RPC_* configured).
        # Used to read height/MTP, broadcast, and verify confirmations when the
        # Electrum upstream is unavailable. See src/pool/node_rpc.py.
        self._node: NodeRPC | None = NodeRPC.from_config()
        # True while the last chain read came from the Bitcoin node (electrs down). Surfaced
        # via /api/status so the fallback is visible, not silent.
        self.node_fallback_active = False
        # Warn once if the node lacks txindex=1 (confirmation checks via the node
        # fallback need it; broadcasting and scheduling do not).
        self._txindex_warned = False
        if self._node:
            log.info("Bitcoin node RPC fallback enabled (%s:%d)", self._node.host, self._node.port)

    async def start(self) -> None:
        self._running = True
        # Price poller runs independently of upstream connection
        self._price_task = asyncio.create_task(self._price_poller())
        # Node-RPC fallback poller: keeps height/MTP + due broadcasts alive when
        # electrs is down. No-op unless Bitcoin node RPC is configured.
        if self._node:
            self._node_task = asyncio.create_task(self._node_fallback_poller())
        backoff = 1
        while self._running:
            try:
                await self._run()
                backoff = 1  # Reset on clean exit
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.upstream_connected = False
                log.error("Scheduler error: %s — reconnecting in %ds", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)  # Exponential backoff, cap 15s
            else:
                self.upstream_connected = False

    async def stop(self) -> None:
        self._running = False
        if self._price_task:
            self._price_task.cancel()
        if self._node_task:
            self._node_task.cancel()
        if self._upstream:
            await self._upstream.close()

    async def reconnect(self) -> None:
        """Disconnect and reconnect to (possibly new) upstream."""
        log.info("Scheduler reconnecting to new upstream...")
        self.upstream_connected = False
        self._reconnect_event.set()
        if self._upstream:
            await self._upstream.close()
            self._upstream = None

    async def broadcast_now(self, txid: str) -> dict:
        """Immediately broadcast a retained transaction. Returns result dict."""
        tx = self.store.get_tx(txid)
        if not tx:
            return {"error": "Transaction not found"}
        # Shared pre-broadcast gate (expiry + locktime), fail-closed.
        err = self._check_broadcast_policy(tx)
        if err:
            return {"error": err}
        if tx.status not in ("pending", "scheduled"):
            return {"error": f"Cannot broadcast tx in status '{tx.status}'"}

        if self._upstream is None and self._node is None:
            return {"error": "Not connected to upstream"}

        return await self._do_broadcast(tx)

    def _check_broadcast_policy(self, tx) -> str | None:
        """Shared gate enforced by every broadcast path (manual AND automatic).

        Returns an error string if the tx must NOT be broadcast, else None.
        Fail-closed: marks the tx 'expired' when expiry is detected or its
        expires_at is unparseable. Centralizing this here means the automatic
        paths (by-block, by-timestamp, by-price, node-fallback) can no longer
        emit an expired or not-yet-unlocked tx by going straight to _do_broadcast.
        """
        if tx.status == "expired":
            return "Transaction expired — cannot broadcast"
        # Expiry (fail-closed) — check even if status hasn't been updated yet.
        if tx.expires_at:
            try:
                exp = datetime.fromisoformat(tx.expires_at.replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    now = datetime.utcnow()
                else:
                    now = datetime.now(timezone.utc)
                if now >= exp:
                    self.store.update_status(tx.txid, "expired")
                    return "Transaction expired — cannot broadcast"
            except Exception as e:
                log.error("Cannot parse expires_at for %s: %s", tx.txid[:16], e)
                return "Cannot verify expiration — refusing to broadcast"
        # Locktime constraints.
        if tx.locktime >= LOCKTIME_THRESHOLD:
            mtp_raw = self.store.get_state("current_mtp")
            mtp = int(mtp_raw) if mtp_raw else 0
            if mtp and mtp <= tx.locktime:
                lock_dt = datetime.fromtimestamp(tx.locktime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                mtp_dt = datetime.fromtimestamp(mtp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                return (f"Locktime no alcanzado. La tx tiene locktime {lock_dt} "
                        f"pero el MTP actual es {mtp_dt}. Hay que esperar.")
        elif 0 < tx.locktime < LOCKTIME_THRESHOLD:
            current_height = self.store.get_current_height()
            if current_height and current_height < tx.locktime:
                return (f"Locktime no alcanzado. La tx requiere bloque {tx.locktime} "
                        f"pero estamos en {current_height}.")
        return None

    async def _run(self) -> None:
        """Main scheduler loop."""
        host, port, use_ssl = self.store.get_upstream()
        self._upstream = UpstreamConnection(host, port, use_ssl=use_ssl)
        await self._upstream.connect()

        # Handshake
        await self._upstream.call("server.version", [config.CLIENT_NAME, config.PROTOCOL_VERSION])

        # Detect network via genesis_hash
        await self._detect_network()

        # Subscribe to new blocks
        resp = await self._upstream.call("blockchain.headers.subscribe", [])
        if "result" in resp:
            height = resp["result"]["height"]
            self.store.set_state("current_height", str(height))
            log.info("Scheduler synced at block %d", height)
            self.upstream_connected = True
            await self._on_new_block(height)

        # Set up notification handler for new blocks
        self._upstream.set_notification_callback(self._handle_notification)

        # Keep alive — break immediately on reconnect request
        self._reconnect_event.clear()
        while self._running:
            try:
                await asyncio.wait_for(self._reconnect_event.wait(), timeout=30)
                break  # Reconnect requested
            except asyncio.TimeoutError:
                pass  # Normal timeout, do ping
            # reconnect() may have nulled the upstream between the event wait
            # and this ping (race seen in the field as "'NoneType' object has
            # no attribute 'call'") — grab a local ref and bail out cleanly.
            upstream = self._upstream
            if upstream is None:
                break
            try:
                await upstream.call("server.ping")
            except Exception:
                break

    async def _handle_notification(self, msg: dict) -> None:
        method = msg.get("method", "")
        params = msg.get("params", [])

        if method == "blockchain.headers.subscribe" and params:
            header = params[0]
            height = header["height"]
            self.store.set_state("current_height", str(height))
            log.info("New block: %d", height)
            await self._on_new_block(height)

    async def _on_new_block(self, height: int) -> None:
        """Handle a new block: broadcast due txs, check confirmations, detect conflicts."""
        # Block arrived via electrs → it's the live transport, not the node fallback.
        self.node_fallback_active = False
        # Calculate and store MTP
        mtp = await self._compute_mtp(height)
        if mtp:
            self.store.set_state("current_mtp", str(mtp))

        # Auto-disable Liana faking if real chain reached the configured cutoff.
        # Clears offset, rate, and the cutoff itself (one-shot).
        try:
            disable_at = int(self.store.get_state("liana_disable_at_height") or "0")
        except ValueError:
            disable_at = 0
        if disable_at > 0 and height >= disable_at:
            self.store.set_state("liana_height_offset", "0")
            self.store.set_state("liana_increment_rate", "0")
            self.store.set_state("liana_disable_at_height", "0")
            log.info("Liana faking auto-disabled: real height %d reached cutoff %d", height, disable_at)

        # Broadcast due transactions (by block height)
        await self._broadcast_due_by_block(height)

        # Broadcast txs with timestamp locktime that MTP has passed
        if mtp:
            await self._broadcast_due_by_timestamp(mtp)

        # Check confirmations for broadcasting txs
        await self._check_confirmations()

        # Rebroadcast stuck txs
        await self._rebroadcast_stuck()

        # Detect UTXO conflicts
        await self._detect_conflicts()

        # Check price-triggered txs
        await self._check_price_triggers()

        # Purge expired price-scheduled txs
        self._purge_expired_txs()

        # Resolve unresolved inputs (retry for txs missing confirmed_height)
        await self._resolve_pending_inputs()

        # Purge confirmed txs (after N blocks)
        if config.PURGE_AFTER_BLOCKS > 0:
            purged = self.store.purge_confirmed(height, config.PURGE_AFTER_BLOCKS)
            if purged:
                log.info("Purged %d confirmed tx(s) at depth %d+", purged, config.PURGE_AFTER_BLOCKS)

    async def _price_poller(self) -> None:
        """Poll price source every 30s and store current price."""
        while self._running:
            try:
                source = self.store.get_state("price_source") or ""
                if not source:
                    await asyncio.sleep(30)
                    continue

                price = await self._fetch_price(source)
                if price and price > 0:
                    if self._current_price and abs(price - self._current_price) / self._current_price > 0.15:
                        log.warning("Price spike rejected: $%.0f -> $%.0f (%.1f%%)",
                                    self._current_price, price,
                                    abs(price - self._current_price) / self._current_price * 100)
                    else:
                        self._current_price = price
                        self.store.set_state("current_price", str(price))
                # Check expiry on every poll cycle (independent of blocks)
                self._purge_expired_txs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Price poll error: %s", e)
            # Also check expiry even without price source
            self._purge_expired_txs()
            await asyncio.sleep(30)

    async def _fetch_price(self, source: str) -> float | None:
        """Fetch BTC/USD price from configured source."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                if source == "coingecko":
                    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        return float(data["bitcoin"]["usd"])
                else:
                    # Local oracle or custom URL — expects {price_usd: N} or {bitcoin: {usd: N}}
                    url = source.rstrip("/") + "/api/price/latest"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        return float(data.get("price_usd", 0))
        except Exception as e:
            log.debug("Price fetch failed from %s: %s", source, e)
            return None

    async def _broadcast_due_by_block(self, height: int) -> None:
        """Broadcast txs whose target block height has been reached."""
        for tx in self.store.get_due_txs(height):
            result = await self._do_broadcast(tx)
            if "error" not in result:
                log.info("Broadcast scheduled tx %s at block %d", tx.txid[:16], height)

    async def _node_fallback_poller(self) -> None:
        """When electrs is down, drive height/MTP + due broadcasts from Bitcoin node.

        No-op while the Electrum upstream is connected (electrs is authoritative).
        Only runs when BITCOIN_RPC_* is configured (self._node is not None).
        """
        while self._running:
            try:
                if not self.upstream_connected and self._node is not None:
                    await self._node_fallback_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Node fallback tick error: %s", e)
            await asyncio.sleep(30)

    async def _node_fallback_tick(self) -> None:
        """One fallback cycle: refresh height/MTP from the Bitcoin node and process due txs."""
        info = await self._node.health()
        if not info:
            return
        height = info.get("blocks")
        mtp = info.get("mediantime")  # the node's mediantime IS the tip's MTP (BIP-113)
        if not height:
            return

        prev = self.store.get_current_height() or 0
        self.store.set_state("current_height", str(height))
        if mtp:
            self.store.set_state("current_mtp", str(mtp))
        self.node_fallback_active = True
        if height != prev:
            log.info("Node fallback: height=%d mtp=%s (electrs unavailable)", height, mtp)

        # Drive the same due-broadcast logic the electrs block handler would.
        await self._broadcast_due_by_block(height)
        if mtp:
            await self._broadcast_due_by_timestamp(mtp)
        await self._check_price_triggers()
        self._purge_expired_txs()
        await self._check_confirmations()

    async def _check_price_triggers(self) -> None:
        """Broadcast txs whose price trigger has been hit."""
        if not self._current_price:
            return

        price_txs = self.store.get_price_scheduled_txs()
        if not price_txs:
            return

        for tx in price_txs:
            if not tx.target_price:
                continue

            triggered = False
            if tx.price_direction == "below" and self._current_price <= tx.target_price:
                triggered = True
            elif tx.price_direction == "above" and self._current_price >= tx.target_price:
                triggered = True

            if triggered:
                log.info(
                    "Price trigger: BTC $%.0f %s $%.0f — broadcasting %s",
                    self._current_price, tx.price_direction, tx.target_price, tx.txid[:16],
                )
                result = await self._do_broadcast(tx)
                if "error" not in result:
                    log.info("Price-triggered broadcast of %s", tx.txid[:16])

    def _purge_expired_txs(self) -> None:
        """Mark price-scheduled txs as expired when their expiry has passed."""
        now = datetime.utcnow()
        with self.store._lock:
            rows = self.store._conn.execute(
                """SELECT txid, expires_at FROM retained_txs
                   WHERE status = 'scheduled' AND expires_at IS NOT NULL
                   AND network = ?""",
                (self.store.network,),
            ).fetchall()
            updated = 0
            for r in rows:
                try:
                    exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
                    if exp.tzinfo is not None:
                        exp = exp.replace(tzinfo=None)
                except Exception:
                    continue
                if now >= exp:
                    self.store._conn.execute(
                        """UPDATE retained_txs
                           SET status = 'expired', updated_at = datetime('now')
                           WHERE txid = ?""",
                        (r["txid"],),
                    )
                    log.info("Tx %s expired (past %s)", r["txid"][:16], r["expires_at"])
                    updated += 1
            if updated:
                self.store._conn.commit()

    async def _do_broadcast(self, tx, _depth=0) -> dict:
        """Broadcast a single transaction to upstream. Respects dependency order."""
        if _depth > 10:
            return {"error": "Dependency chain too deep (>10 levels)"}

        # Safety net: every automatic path (by-block, by-timestamp, by-price,
        # node-fallback) funnels through here, so re-assert the broadcast policy
        # to never emit an expired or not-yet-unlocked tx (covers purge races).
        err = self._check_broadcast_policy(tx)
        if err:
            log.info("Skipping broadcast of %s: %s", tx.txid[:16], err)
            return {"error": err}

        # Check if this tx depends on a parent that hasn't been broadcast yet
        if tx.depends_on:
            parent = self.store.get_tx(tx.depends_on)
            if parent and parent.status in ("pending", "scheduled"):
                # Parent not yet broadcast — broadcast parent first
                log.info("Broadcasting parent %s first (dependency of %s)",
                         parent.txid[:16], tx.txid[:16])
                parent_result = await self._do_broadcast(parent, _depth + 1)
                if "error" in parent_result:
                    self.store.update_status(tx.txid, "failed",
                                             error=f"Parent {parent.txid[:16]} failed: {parent_result['error']}")
                    return {"error": f"Parent tx failed: {parent_result['error']}"}

        self.store.update_status(tx.txid, "broadcasting")

        # Record broadcast block: only update target if it was a manual/early broadcast
        current = self.store.get_current_height()
        if current and (not tx.target_block or tx.target_block > current):
            self.store.update_target_block(tx.txid, current, keep_status=True)

        # Decrypt raw_hex if encrypted
        raw_hex = self.store.get_raw_hex(tx.txid)
        if not raw_hex or raw_hex.startswith("["):
            self.store.update_status(tx.txid, "failed", error="Cannot decrypt transaction")
            return {"error": "Cannot decrypt transaction"}

        # Relay via electrs, falling back to Bitcoin node RPC if configured.
        outcome = await self._relay_raw(raw_hex)
        kind = outcome["kind"]

        if kind in ("success", "already"):
            self.store.update_broadcast_time(tx.txid)
            if kind == "already":
                log.info("Tx %s already in mempool/chain", tx.txid[:16])
            # Notify connected wallets
            if self.notify_callback:
                affected = self.store.get_scripthashes_for_tx(tx.txid)
                await self.notify_callback(affected)
            return {"txid": outcome.get("txid") or tx.txid, "via": outcome.get("via")}

        if kind == "reject":
            # Definitive node-side refusal: inputs spent → abandoned, else failed.
            status = "abandoned" if outcome.get("spent") else "failed"
            self.store.update_status(tx.txid, status, error=outcome["error"])
            log.warning("Broadcast %s for %s: %s", status, tx.txid[:16], outcome["error"])
            return {"error": outcome["error"]}

        # kind == "unreachable": no transport reached the network — the tx may have
        # landed anyway. Keep 'broadcasting' so _check_confirmations verifies it.
        self.store.update_broadcast_time(tx.txid)
        log.warning("Broadcast unreachable for %s (will verify): %s", tx.txid[:16], outcome["error"])
        return {"txid": tx.txid, "warning": outcome["error"]}

    async def _relay_raw(self, raw_hex: str) -> dict:
        """Send a raw tx to the network: electrs first, Bitcoin node RPC as fallback.

        Returns a normalized outcome dict with "kind" one of:
          - "success"     reached the network ("txid", "via")
          - "already"     already in mempool/chain ("via")
          - "reject"      node refused it ("error", "spent": bool, "via")
          - "unreachable" no transport reached the network ("error")
        """
        electrum_err = None

        # 1) Electrum upstream (primary path)
        if self._upstream is not None:
            try:
                resp = await self._upstream.call(
                    "blockchain.transaction.broadcast", [raw_hex]
                )
                if "error" in resp:
                    msg = resp["error"].get("message", str(resp["error"]))
                    return self._classify_electrum_send_error(msg)
                return {"kind": "success", "txid": resp.get("result"), "via": "electrs"}
            except Exception as e:
                electrum_err = e
                log.warning("electrs broadcast failed (%s)%s", e,
                            " — trying Bitcoin node" if self._node else "")

        # 2) Bitcoin node RPC (fallback)
        if self._node is not None:
            try:
                txid = await self._node.sendrawtransaction(raw_hex)
                log.info("Broadcast via Bitcoin node RPC%s",
                         " (electrs unavailable)" if electrum_err else "")
                return {"kind": "success", "txid": txid, "via": "node"}
            except NodeRPCError as e:
                outcome = self._classify_node_send_error(e)
                if outcome["kind"] != "unreachable":
                    return outcome
                electrum_err = electrum_err or e
            except Exception as e:
                electrum_err = electrum_err or e

        return {"kind": "unreachable", "error": str(electrum_err or "no broadcast transport")}

    @staticmethod
    def _classify_electrum_send_error(msg: str) -> dict:
        low = msg.lower()
        if "already" in low:
            return {"kind": "already", "via": "electrs"}
        spent = any(k in low for k in
                    ["missing", "missingorspent", "spent", "conflict", "duplicate"])
        return {"kind": "reject", "error": msg, "spent": spent, "via": "electrs"}

    @staticmethod
    def _classify_node_send_error(e: NodeRPCError) -> dict:
        # A transport/auth failure is not a node decision about the tx.
        if isinstance(e, NodeRPCTransportError) or e.code is None:
            return {"kind": "unreachable", "error": e.message}
        low = e.message.lower()
        if e.code == -27 or "already" in low:  # already in chain/mempool
            return {"kind": "already", "via": "node"}
        spent = e.code == -25 or any(k in low for k in
                                     ["missing", "missingorspent", "spent", "conflict", "txn-mempool-conflict"])
        return {"kind": "reject", "error": e.message, "spent": spent, "via": "node"}

    async def _check_confirmations(self) -> None:
        """Check if broadcasting or failed txs have been confirmed.

        Failed txs are also checked because the broadcast might have
        succeeded despite an error response (e.g. timeout, ambiguous error).
        """
        to_check = (
            self.store.get_all_txs(status="broadcasting")
            + self.store.get_all_txs(status="failed")
        )

        # Watchdog: txs stuck in broadcasting > 60 min without confirmation → mark failed
        now = datetime.utcnow()
        for tx in to_check:
            if tx.status == "broadcasting" and tx.broadcast_at:
                try:
                    bcast = datetime.fromisoformat(tx.broadcast_at.replace("Z", "+00:00"))
                    if bcast.tzinfo is not None:
                        bcast = bcast.replace(tzinfo=None)
                    if (now - bcast).total_seconds() > 3600:
                        self.store.update_status(
                            tx.txid, "failed",
                            error="Broadcast unverified after 60 minutes"
                        )
                        log.warning("Tx %s timed out in broadcasting state", tx.txid[:16])
                        continue
                except Exception:
                    pass

            confirmed_height = await self._confirmation_height(tx)
            if confirmed_height and confirmed_height > 0:
                self.store.set_confirmed(tx.txid, confirmed_height)
                log.info("Confirmed tx %s at block %d", tx.txid[:16], confirmed_height)
                if self.notify_callback:
                    scripthashes = self.store.get_scripthashes_for_tx(tx.txid)
                    if scripthashes:
                        await self.notify_callback(scripthashes)

    async def _confirmation_height(self, tx) -> int | None:
        """Block height a tx confirmed at, or None if unconfirmed/unknown.

        electrs (scripthash history) is authoritative when reachable; on failure
        it falls back to Bitcoin node (getrawtransaction → getblockheader, which
        needs txindex=1 on the node).
        """
        # 1) electrs via scripthash history
        if self._upstream is not None:
            sh = next(iter(self.store.get_scripthashes_for_tx(tx.txid)), None)
            if sh:
                try:
                    resp = await self._upstream.call(
                        "blockchain.scripthash.get_history", [sh]
                    )
                    for h in resp.get("result", []):
                        if h["tx_hash"] == tx.txid and h.get("height", 0) > 0:
                            return h["height"]
                    return None  # electrs answered: seen-but-unconfirmed or absent
                except Exception as e:
                    log.debug("electrs confirmation check failed for %s: %s", tx.txid[:16], e)

        # 2) Bitcoin node fallback (getrawtransaction needs txindex=1)
        if self._node is not None:
            try:
                info = await self._node.getrawtransaction(tx.txid, True)
                blockhash = info.get("blockhash")
                if blockhash:
                    hdr = await self._node.getblockheader(blockhash)
                    return hdr.get("height")
            except NodeRPCError as e:
                if self._is_txindex_missing(e):
                    if not self._txindex_warned:
                        self._txindex_warned = True
                        log.warning(
                            "Bitcoin node has no txindex=1 — confirmation checks via the "
                            "node fallback are unavailable (broadcasting and scheduling are "
                            "unaffected). Enable txindex=1 for full fallback coverage."
                        )
                else:
                    log.debug("Bitcoin node confirmation check failed for %s: %s", tx.txid[:16], e)
            except Exception as e:
                log.debug("Bitcoin node confirmation check failed for %s: %s", tx.txid[:16], e)
        return None

    @staticmethod
    def _is_txindex_missing(e: NodeRPCError) -> bool:
        """True when a getrawtransaction error is the 'enable -txindex' hint."""
        return "txindex" in (getattr(e, "message", "") or "").lower()

    async def _rebroadcast_stuck(self) -> None:
        """Rebroadcast txs that fell out of mempool."""
        broadcasting = self.store.get_all_txs(status="broadcasting")
        now = datetime.utcnow()

        for tx in broadcasting:
            if not tx.broadcast_at:
                continue
            try:
                broadcast_time = datetime.fromisoformat(tx.broadcast_at)
            except ValueError:
                continue

            if now - broadcast_time > timedelta(minutes=config.REBROADCAST_AFTER_MINUTES):
                log.info("Rebroadcasting stuck tx %s", tx.txid[:16])
                try:
                    raw = self.store.get_raw_hex(tx.txid)
                    if not raw or raw.startswith("["):
                        continue
                    outcome = await self._relay_raw(raw)
                    if outcome["kind"] in ("success", "already"):
                        self.store.update_broadcast_time(tx.txid)
                except Exception as e:
                    log.debug("Rebroadcast failed for %s: %s", tx.txid[:16], e)

    def _scan_dependencies(self) -> int:
        """Detect CPFP relationships between active retained txs.

        For each active tx without depends_on set, check if any input spends an
        output of another active tx → mark depends_on. Returns the number of new
        dependencies recorded. Idempotent — txs that already have depends_on are skipped.

        Called by the interceptor after each tx is saved (catches the case where the
        parent arrives AFTER the child) and by the /api/txs/scan-dependencies endpoint.
        """
        from src.pool.tx_parser import parse_raw_tx
        active = self.store.get_all_txs()
        active_txids = {tx.txid for tx in active}
        found = 0
        for tx in active:
            if tx.depends_on:
                continue
            raw = self.store.get_raw_hex(tx.txid)
            if not raw or raw.startswith("[") or len(raw) < 20:
                continue
            try:
                parsed = parse_raw_tx(raw)
            except Exception:
                continue
            for inp in parsed.inputs:
                if inp.prev_txid in active_txids and inp.prev_txid != tx.txid:
                    self.store.set_depends_on(tx.txid, inp.prev_txid)
                    found += 1
                    break
        return found

    async def _compute_mtp(self, height: int) -> int | None:
        """Compute Median Time Past from the last 11 block headers."""
        try:
            start = max(0, height - 10)
            count = height - start + 1
            resp = await self._upstream.call(
                "blockchain.block.headers", [start, count]
            )
            raw_hex = resp.get("result", {}).get("hex", "")
            if not raw_hex:
                return None

            timestamps = []
            for i in range(count):
                header_hex = raw_hex[i * 160:(i + 1) * 160]
                if len(header_hex) < 160:
                    break
                header_bytes = bytes.fromhex(header_hex)
                ts = struct.unpack_from("<I", header_bytes, 68)[0]
                timestamps.append(ts)

            if len(timestamps) < 1:
                return None

            timestamps.sort()
            mtp = timestamps[len(timestamps) // 2]
            return mtp
        except Exception as e:
            log.debug("Failed to compute MTP: %s", e)
            return None

    async def _broadcast_due_by_timestamp(self, mtp: int) -> None:
        """Broadcast active txs whose nLockTime is a unix timestamp that MTP has passed."""
        from src.pool.tx_parser import parse_raw_tx

        scheduled = self.store.get_all_txs(status="scheduled")
        for tx in scheduled:
            try:
                raw = self.store.get_raw_hex(tx.txid)
                if not raw or raw.startswith("["):
                    continue
                parsed = parse_raw_tx(raw)
                if parsed.locktime >= LOCKTIME_THRESHOLD and mtp > parsed.locktime:
                    result = await self._do_broadcast(tx)
                    if "error" not in result:
                        log.info(
                            "Broadcast timestamp-locked tx %s (locktime=%d, mtp=%d)",
                            tx.txid[:16], parsed.locktime, mtp,
                        )
            except Exception:
                pass

    async def _resolve_pending_inputs(self) -> None:
        """Retry resolving inputs that have no confirmed_height or value."""
        from src.pool.tx_parser import parse_raw_tx, compute_scripthash

        active = self.store.get_active_txs()
        for tx in active:
            inputs = self.store.get_inputs(tx.txid)
            unresolved = [i for i in inputs if not i.scripthash or i.value_sats is None or i.value_sats == 0]
            if not unresolved:
                continue

            try:
                raw = self.store.get_raw_hex(tx.txid)
                if not raw or raw.startswith("["):
                    continue
                parsed = parse_raw_tx(raw)
            except Exception:
                continue

            updated = False
            for inp in parsed.inputs:
                # Check if this input needs resolving
                db_input = next((i for i in inputs if i.prev_txid == inp.prev_txid and i.prev_vout == inp.prev_vout), None)
                if db_input and db_input.scripthash and db_input.value_sats and db_input.value_sats > 0 and db_input.confirmed_height is not None:
                    continue

                try:
                    # Check if parent is in our pool first
                    retained_parent = self.store.get_tx(inp.prev_txid)
                    if retained_parent and retained_parent.raw_hex and len(retained_parent.raw_hex) > 20:
                        parent_raw = retained_parent.raw_hex
                    else:
                        resp = await self._upstream.call("blockchain.transaction.get", [inp.prev_txid, False])
                        parent_raw = resp.get("result", "")
                    if not parent_raw or not isinstance(parent_raw, str):
                        continue

                    parent = parse_raw_tx(parent_raw)
                    if inp.prev_vout >= len(parent.outputs):
                        continue

                    output = parent.outputs[inp.prev_vout]
                    scripthash = output.scripthash
                    value = output.value_sats

                    # Get confirmed height
                    conf_height = 0
                    if retained_parent:
                        conf_height = 0  # Parent is retained, not on-chain yet
                    elif scripthash:
                        try:
                            hist = await self._upstream.call("blockchain.scripthash.get_history", [scripthash])
                            for h in hist.get("result", []):
                                if h.get("tx_hash") == inp.prev_txid:
                                    conf_height = h.get("height", 0)
                                    break
                        except Exception:
                            pass

                    self.store.update_input(tx.txid, inp.prev_txid, inp.prev_vout,
                                           scripthash, value, conf_height)
                    updated = True
                except Exception:
                    continue

            if updated:
                inputs_resolved = self.store.get_inputs(tx.txid)
                total_in = sum(i.value_sats or 0 for i in inputs_resolved)
                total_out = sum(o.value_sats for o in self.store.get_outputs(tx.txid))
                if total_in > 0:
                    fee = total_in - total_out
                    fee_rate = fee / tx.vsize if tx.vsize > 0 else 0
                    self.store.update_fee(tx.txid, fee, fee_rate)
                    log.info("Resolved inputs for %s: fee=%d (%.1f sat/vB)", tx.txid[:16], fee, fee_rate)

    async def _detect_network(self) -> None:
        """Detect the Bitcoin network by matching the genesis block hash."""
        genesis = ""

        # Try server.features first (standard Electrum servers)
        try:
            resp = await self._upstream.call("server.features", [])
            features = resp.get("result", {})
            if isinstance(features, dict):
                genesis = features.get("genesis_hash", "")
        except Exception:
            pass

        # Fallback: compute genesis hash from block header 0
        if not genesis:
            try:
                resp = await self._upstream.call("blockchain.block.header", [0])
                header_hex = resp.get("result", "")
                if header_hex:
                    header_bytes = bytes.fromhex(header_hex)
                    block_hash = hashlib.sha256(hashlib.sha256(header_bytes).digest()).digest()[::-1].hex()
                    genesis = block_hash
            except Exception:
                pass

        if genesis:
            network = config.GENESIS_HASHES.get(genesis, "unknown")
            self.store.set_detected_network(network)
            log.info("Detected network: %s (genesis: %s...)", network, genesis[:16])
        else:
            log.warning("Could not detect network")

    async def _detect_conflicts(self) -> None:
        """Check if inputs of active retained txs have been spent elsewhere.
        Skip inputs that spend outputs of other retained txs (CPFP chains)."""
        active = self.store.get_active_txs()
        active_txids = {tx.txid for tx in active}

        for tx in active:
            inputs = self.store.get_inputs(tx.txid)
            for inp in inputs:
                # Skip if input spends an output of another retained tx (not on-chain yet)
                if inp.prev_txid in active_txids:
                    continue
                if not inp.scripthash:
                    continue
                try:
                    resp = await self._upstream.call(
                        "blockchain.scripthash.listunspent", [inp.scripthash]
                    )
                    utxos = resp.get("result", [])
                    still_available = any(
                        u["tx_hash"] == inp.prev_txid and u["tx_pos"] == inp.prev_vout
                        for u in utxos
                    )
                    if not still_available:
                        self.store.update_status(
                            tx.txid, "abandoned",
                            error=f"UTXO {inp.prev_txid[:16]}:{inp.prev_vout} spent by another tx",
                        )
                        log.warning("Abandoned tx %s: input %s:%d spent elsewhere",
                                    tx.txid[:16], inp.prev_txid[:16], inp.prev_vout)
                        if self.notify_callback:
                            affected = self.store.get_scripthashes_for_tx(tx.txid)
                            await self.notify_callback(affected)
                        break
                except Exception as e:
                    log.debug("Conflict check failed for %s: %s", tx.txid[:16], e)
