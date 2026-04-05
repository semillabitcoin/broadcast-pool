"""Interceptor — logic for selectively modifying Electrum protocol messages."""

import logging

from src.pool.store import TxStore
from src.pool.tx_parser import ParsedTx, parse_raw_tx, compute_scripthash
from src.pool.virtual_mempool import VirtualMempool
from src.proxy.upstream import UpstreamConnection

log = logging.getLogger(__name__)


class Interceptor:
    """Intercepts specific Electrum methods while proxying the rest."""

    def __init__(self, store: TxStore, vmempool: VirtualMempool, upstream: UpstreamConnection):
        self.store = store
        self.vmempool = vmempool
        self.upstream = upstream
        self.wallet_label: str = ""  # Set by session from server.version handshake

    async def intercept_broadcast(self, params: list, msg_id: int) -> dict:
        """Intercept blockchain.transaction.broadcast — retain instead of forwarding."""
        raw_hex = params[0]

        try:
            parsed = parse_raw_tx(raw_hex)
        except Exception as e:
            log.error("Failed to parse tx: %s", e, exc_info=True)
            return {"jsonrpc": "2.0", "error": {"code": -1, "message": "Invalid transaction"}, "id": msg_id}

        # Resolve input scripthashes from upstream
        await self._resolve_inputs(parsed)

        # Calculate fee
        input_total = sum(inp.value_sats for inp in parsed.inputs)
        output_total = sum(out.value_sats for out in parsed.outputs)
        parsed.fee_sats = input_total - output_total
        parsed.fee_rate = parsed.fee_sats / parsed.vsize if parsed.vsize > 0 else 0

        # Fee sanity warnings
        if parsed.fee_rate > 1000:
            log.warning("HIGH FEE ALERT: tx %s has %.1f sat/vB (fee=%d sats)",
                        parsed.txid[:16], parsed.fee_rate, parsed.fee_sats)
        if output_total > 0 and parsed.fee_sats > output_total * 0.5:
            log.warning("FEE/AMOUNT ALERT: tx %s fee (%d sats) is >50%% of outputs (%d sats)",
                        parsed.txid[:16], parsed.fee_sats, output_total)

        # Detect RBF: check if any input overlaps with an active retained tx
        replaced_tx = self._detect_rbf(parsed)

        # Detect dependency: check if any input spends an OUTPUT of another retained tx (CPFP)
        parent_tx = self._detect_dependency(parsed)

        # Save to store
        self.store.save_retained_tx(parsed, raw_hex, wallet_label=self.wallet_label)

        # If dependency detected, record it
        if parent_tx and not replaced_tx:
            self.store.set_depends_on(parsed.txid, parent_tx.txid)
            log.info("Dependency detected: %s depends on %s (CPFP)",
                     parsed.txid[:16], parent_tx.txid[:16])

        # If RBF detected, mark old tx as replaced and inherit its schedule
        if replaced_tx:
            self.store.update_status(replaced_tx.txid, "replaced",
                                     error=f"Replaced by {parsed.txid[:16]}...")
            # Inherit schedule from replaced tx
            if replaced_tx.target_block:
                self.store.update_target_block(parsed.txid, replaced_tx.target_block)
            elif replaced_tx.status == "scheduled":
                # MTP-scheduled: keep new tx as scheduled too
                self.store.update_status(parsed.txid, "scheduled")
            log.info("RBF detected: %s replaces %s (fee %.1f → %.1f sat/vB)",
                     parsed.txid[:16], replaced_tx.txid[:16],
                     replaced_tx.fee_rate, parsed.fee_rate)

        # nLockTime handling:
        # - locktime < 500M = block height
        # - locktime >= 500M = unix timestamp (compared against MTP, not wall clock)
        # - Sparrow sets locktime ≈ current_height as anti-fee-sniping (ignore)
        current_height = self.store.get_current_height()

        auto_lock = self.store.get_state("auto_schedule_locktime") != "false"

        if parsed.locktime >= 500_000_000 and auto_lock:
            # Unix timestamp locktime — scheduler will broadcast when MTP passes it
            from datetime import datetime
            dt = datetime.utcfromtimestamp(parsed.locktime).strftime("%Y-%m-%d %H:%M UTC")
            log.info(
                "Retained tx %s with timestamp locktime=%d (%s, %.1f sat/vB) — will broadcast when MTP passes",
                parsed.txid[:16], parsed.locktime, dt, parsed.fee_rate,
            )
        elif (0 < parsed.locktime < 500_000_000
                and current_height > 0
                and parsed.locktime > current_height + 1
                and auto_lock):
            # Real future block height locktime — auto-schedule
            self.store.update_target_block(parsed.txid, parsed.locktime)
            log.info(
                "Retained tx %s with block locktime=%d (auto-scheduled, %.1f sat/vB)",
                parsed.txid[:16], parsed.locktime, parsed.fee_rate,
            )
        else:
            # Normal tx or anti-fee-sniping locktime — leave as pending
            log.info(
                "Retained tx %s (%d sats fee, %.1f sat/vB, %d inputs, %d outputs)",
                parsed.txid[:16], parsed.fee_sats, parsed.fee_rate,
                len(parsed.inputs), len(parsed.outputs),
            )

        # Return txid to wallet (Sparrow validates this matches)
        return {"jsonrpc": "2.0", "result": parsed.txid, "id": msg_id}

    def modify_get_history(self, response: dict, scripthash: str) -> dict:
        """Inject retained txs into blockchain.scripthash.get_history response."""
        if "result" not in response or response["result"] is None:
            return response

        response["result"] = self.vmempool.inject_in_history(
            response["result"], scripthash
        )
        return response

    def modify_listunspent(self, response: dict, scripthash: str) -> dict:
        """Hide spent UTXOs and add retained outputs in listunspent response."""
        if "result" not in response or response["result"] is None:
            return response

        response["result"] = self.vmempool.filter_listunspent(
            response["result"], scripthash
        )
        return response

    async def modify_subscribe_response(self, response: dict, scripthash: str) -> dict:
        """Recalculate status_hash for subscribe response if we have retained txs."""
        if not self.vmempool.has_retained_for_scripthash(scripthash):
            return response

        # Need the full history to compute correct status_hash
        try:
            history_resp = await self.upstream.call(
                "blockchain.scripthash.get_history", [scripthash]
            )
            real_history = history_resp.get("result", [])
        except Exception:
            return response

        new_hash = self.vmempool.compute_modified_status_hash(real_history, scripthash)
        response["result"] = new_hash
        return response

    async def modify_subscribe_notification(self, params: list) -> list:
        """Recalculate status_hash for a push notification."""
        if len(params) < 2:
            return params

        scripthash = params[0]
        if not self.vmempool.has_retained_for_scripthash(scripthash):
            return params

        try:
            history_resp = await self.upstream.call(
                "blockchain.scripthash.get_history", [scripthash]
            )
            real_history = history_resp.get("result", [])
        except Exception:
            return params

        new_hash = self.vmempool.compute_modified_status_hash(real_history, scripthash)
        params[1] = new_hash
        return params

    def get_affected_scripthashes(self, txid: str) -> set[str]:
        """Get all scripthashes affected by a retained tx."""
        return self.store.get_scripthashes_for_tx(txid)

    def _detect_dependency(self, parsed: ParsedTx):
        """Check if any input of the new tx spends an OUTPUT of a retained tx (CPFP).
        Returns the parent RetainedTx or None."""
        active = self.store.get_active_txs()
        active_txids = {tx.txid for tx in active}

        for inp in parsed.inputs:
            if inp.prev_txid in active_txids:
                parent = next(tx for tx in active if tx.txid == inp.prev_txid)
                return parent
        return None

    def _detect_rbf(self, parsed: ParsedTx):
        """Check if any input of the new tx overlaps with an active retained tx.
        Returns the replaced RetainedTx or None.
        Compares outpoints from both raw hex parsing and DB records."""
        new_outpoints = {(inp.prev_txid, inp.prev_vout) for inp in parsed.inputs}
        active = self.store.get_active_txs()

        for tx in active:
            if tx.txid == parsed.txid:
                continue

            # Try DB records first
            existing_inputs = self.store.get_inputs(tx.txid)
            for ei in existing_inputs:
                if (ei.prev_txid, ei.prev_vout) in new_outpoints:
                    return tx

            # Fallback: parse the raw hex of the existing tx to get outpoints
            if tx.raw_hex and len(tx.raw_hex) > 20:
                try:
                    existing_parsed = parse_raw_tx(tx.raw_hex)
                    for ei in existing_parsed.inputs:
                        if (ei.prev_txid, ei.prev_vout) in new_outpoints:
                            return tx
                except Exception:
                    pass

        return None

    async def _resolve_inputs(self, parsed: ParsedTx) -> None:
        """Resolve input scripthashes, values, and confirmation heights from upstream.

        Uses two strategies:
        1. verbose=true (standard electrs/fulcrum) — returns decoded tx with values
        2. raw tx fallback (mempool-electrs) — parse locally to extract outputs
        """
        for inp in parsed.inputs:
            try:
                await self._resolve_single_input(inp)
            except Exception as e:
                log.warning(
                    "Failed to resolve input %s:%d — %s",
                    inp.prev_txid[:16], inp.prev_vout, e,
                )

    async def _resolve_single_input(self, inp) -> None:
        """Resolve a single input's scripthash, value, and confirmation height."""
        # Try verbose first (works on standard electrs/fulcrum)
        try:
            resp = await self.upstream.call(
                "blockchain.transaction.get", [inp.prev_txid, True]
            )
            if "result" in resp and isinstance(resp["result"], dict):
                tx_data = resp["result"]
                output = tx_data["vout"][inp.prev_vout]
                spk_hex = output.get("scriptPubKey", output.get("scriptpubkey", {}))
                if isinstance(spk_hex, dict):
                    spk_hex = spk_hex.get("hex", "")
                inp.scripthash = compute_scripthash(spk_hex)
                value = output.get("value", 0)
                # Could be BTC (float) or sats (int) depending on server
                inp.value_sats = int(round(value * 1e8)) if isinstance(value, float) else int(value)
                # Confirmation height
                status = tx_data.get("status", {})
                if isinstance(status, dict):
                    inp.confirmed_height = status.get("block_height", 0) or 0
                elif tx_data.get("confirmations"):
                    height = self.store.get_current_height()
                    inp.confirmed_height = (height - tx_data["confirmations"] + 1) if height else 0
                return
        except Exception:
            pass  # Fall through to raw tx method

        # Fallback: get raw tx hex and parse locally
        resp = await self.upstream.call(
            "blockchain.transaction.get", [inp.prev_txid, False]
        )
        raw_hex = resp.get("result", "")
        if not raw_hex or not isinstance(raw_hex, str):
            return

        parent_tx = parse_raw_tx(raw_hex)
        if inp.prev_vout < len(parent_tx.outputs):
            output = parent_tx.outputs[inp.prev_vout]
            inp.scripthash = output.scripthash
            inp.value_sats = output.value_sats

        # Get confirmation height via get_merkle (try recent blocks)
        current_height = self.store.get_current_height()
        if current_height:
            # Try scripthash history to find the block
            if inp.scripthash:
                try:
                    hist_resp = await self.upstream.call(
                        "blockchain.scripthash.get_history", [inp.scripthash]
                    )
                    history = hist_resp.get("result", [])
                    for h in history:
                        if h.get("tx_hash") == inp.prev_txid and h.get("height", 0) > 0:
                            inp.confirmed_height = h["height"]
                            break
                except Exception:
                    pass
