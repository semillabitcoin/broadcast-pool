"""Scheduler — monitors block height and triggers broadcasts."""

import asyncio
import hashlib
import json
import logging
import struct
from datetime import datetime, timedelta

import aiohttp

from src.pool.store import TxStore
from src.proxy.upstream import UpstreamConnection
from src import config

LOCKTIME_THRESHOLD = 500_000_000  # nLockTime >= this is a unix timestamp

log = logging.getLogger(__name__)


class Scheduler:
    """Watches for new blocks and broadcasts scheduled transactions."""

    def __init__(self, store: TxStore, notify_callback=None):
        self.store = store
        self.notify_callback = notify_callback  # async fn(set[str]) to notify sessions
        self._upstream: UpstreamConnection | None = None
        self._running = False
        self._reconnect_event = asyncio.Event()
        self._price_task: asyncio.Task | None = None
        self._current_price: float | None = None

    async def start(self) -> None:
        self._running = True
        backoff = 1
        while self._running:
            try:
                await self._run()
                backoff = 1  # Reset on clean exit
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Scheduler error: %s — reconnecting in %ds", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)  # Exponential backoff, cap 15s

    async def stop(self) -> None:
        self._running = False
        if self._price_task:
            self._price_task.cancel()
        if self._upstream:
            await self._upstream.close()

    async def reconnect(self) -> None:
        """Disconnect and reconnect to (possibly new) upstream."""
        log.info("Scheduler reconnecting to new upstream...")
        self._reconnect_event.set()
        if self._upstream:
            await self._upstream.close()
            self._upstream = None

    async def broadcast_now(self, txid: str) -> dict:
        """Immediately broadcast a retained transaction. Returns result dict."""
        tx = self.store.get_tx(txid)
        if not tx:
            return {"error": "Transaction not found"}
        if tx.status not in ("pending", "scheduled"):
            return {"error": f"Cannot broadcast tx in status '{tx.status}'"}

        # Check locktime constraints before broadcasting
        if tx.locktime >= LOCKTIME_THRESHOLD:
            mtp_raw = self.store.get_state("current_mtp")
            mtp = int(mtp_raw) if mtp_raw else 0
            if mtp and mtp <= tx.locktime:
                from datetime import datetime, timezone
                lock_dt = datetime.fromtimestamp(tx.locktime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                mtp_dt = datetime.fromtimestamp(mtp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                return {
                    "error": f"Locktime no alcanzado. La tx tiene locktime {lock_dt} pero el MTP actual es {mtp_dt}. Hay que esperar."
                }
        elif 0 < tx.locktime < LOCKTIME_THRESHOLD:
            current_height = self.store.get_current_height()
            if current_height and current_height < tx.locktime:
                return {
                    "error": f"Locktime no alcanzado. La tx requiere bloque {tx.locktime} pero estamos en {current_height}."
                }

        if not self._upstream:
            return {"error": "Not connected to upstream"}

        return await self._do_broadcast(tx)

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
            await self._on_new_block(height)

        # Set up notification handler for new blocks
        self._upstream.set_notification_callback(self._handle_notification)

        # Start price poller if configured
        if self._price_task:
            self._price_task.cancel()
        self._price_task = asyncio.create_task(self._price_poller())

        # Keep alive — break immediately on reconnect request
        self._reconnect_event.clear()
        while self._running:
            try:
                await asyncio.wait_for(self._reconnect_event.wait(), timeout=30)
                break  # Reconnect requested
            except asyncio.TimeoutError:
                pass  # Normal timeout, do ping
            try:
                await self._upstream.call("server.ping")
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
        # Calculate and store MTP
        mtp = await self._compute_mtp(height)
        if mtp:
            self.store.set_state("current_mtp", str(mtp))

        # Broadcast due transactions (by block height)
        due_txs = self.store.get_due_txs(height)
        for tx in due_txs:
            result = await self._do_broadcast(tx)
            if "error" not in result:
                log.info("Broadcast scheduled tx %s at block %d", tx.txid[:16], height)

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
                    self._current_price = price
                    self.store.set_state("current_price", str(price))
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Price poll error: %s", e)
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

    async def _do_broadcast(self, tx, _depth=0) -> dict:
        """Broadcast a single transaction to upstream. Respects dependency order."""
        if _depth > 10:
            return {"error": "Dependency chain too deep (>10 levels)"}

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

        try:
            resp = await self._upstream.call(
                "blockchain.transaction.broadcast", [raw_hex]
            )

            if "error" in resp:
                error_msg = resp["error"].get("message", str(resp["error"]))
                # Check if already in mempool or blockchain (not a real error)
                if "already" in error_msg.lower():
                    self.store.update_broadcast_time(tx.txid)
                    log.info("Tx %s already in mempool/chain", tx.txid[:16])
                    return {"txid": tx.txid}
                else:
                    # Detect if inputs are spent (abandoned) vs other errors (failed)
                    is_spent = any(k in error_msg.lower() for k in
                                   ["missing", "missingorspent", "spent", "conflict", "duplicate"])
                    status = "abandoned" if is_spent else "failed"
                    self.store.update_status(tx.txid, status, error=error_msg)
                    log.warning("Broadcast %s for %s: %s", status, tx.txid[:16], error_msg)
                    return {"error": error_msg}
            else:
                self.store.update_broadcast_time(tx.txid)
                # Notify connected wallets
                if self.notify_callback:
                    affected = self.store.get_scripthashes_for_tx(tx.txid)
                    await self.notify_callback(affected)
                return {"txid": resp.get("result", tx.txid)}

        except Exception as e:
            self.store.update_status(tx.txid, "failed", error=str(e))
            log.error("Broadcast exception for %s: %s", tx.txid[:16], e)
            return {"error": str(e)}

    async def _check_confirmations(self) -> None:
        """Check if broadcasting or failed txs have been confirmed.

        Failed txs are also checked because the broadcast might have
        succeeded despite an error response (e.g. timeout, ambiguous error).
        """
        to_check = (
            self.store.get_all_txs(status="broadcasting")
            + self.store.get_all_txs(status="failed")
        )

        for tx in to_check:
            scripthashes = self.store.get_scripthashes_for_tx(tx.txid)
            if not scripthashes:
                continue

            sh = next(iter(scripthashes))
            try:
                resp = await self._upstream.call(
                    "blockchain.scripthash.get_history", [sh]
                )
                history = resp.get("result", [])
                for h in history:
                    if h["tx_hash"] == tx.txid and h.get("height", 0) > 0:
                        self.store.set_confirmed(tx.txid, h["height"])
                        log.info("Confirmed tx %s at block %d", tx.txid[:16], h["height"])
                        if self.notify_callback:
                            await self.notify_callback(scripthashes)
                        break
            except Exception as e:
                log.debug("Failed to check confirmation for %s: %s", tx.txid[:16], e)

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
                    await self._upstream.call(
                        "blockchain.transaction.broadcast", [raw]
                    )
                    self.store.update_broadcast_time(tx.txid)
                except Exception as e:
                    log.debug("Rebroadcast failed for %s: %s", tx.txid[:16], e)

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
