"""Web API — REST endpoints + static file serving."""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime

from aiohttp import web

from src import config
from src.pool.store import TxStore

log = logging.getLogger(__name__)

AUTH_TOKEN = os.environ.get("BP_AUTH_TOKEN", "")  # Only activate if explicitly set, not APP_PASSWORD (Umbrel app_proxy handles auth)


def _validate_upstream(host: str, port: int) -> str | None:
    """Validate upstream host/port. Returns error message or None."""
    import ipaddress
    import re

    if not (1 <= port <= 65535):
        return "Port must be 1-65535"

    if not re.match(r'^[a-zA-Z0-9._-]+$', host):
        return "Invalid hostname characters"

    # Block internal/dangerous IPs
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return "Cannot use loopback as upstream (use your node's Electrs IP)"
        if ip.is_link_local:
            return "Cannot use link-local address"
        if ip in ipaddress.ip_network("172.17.0.0/16"):
            return "Cannot use Docker internal network"
    except ValueError:
        pass  # It's a hostname, allow

    return None


@web.middleware
async def auth_middleware(request, handler):
    """Require Bearer token for API endpoints. Static/root are public (served by app_proxy)."""
    if AUTH_TOKEN and request.path.startswith("/api/"):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        import hmac
        if not hmac.compare_digest(token.encode(), AUTH_TOKEN.encode()):
            return web.json_response({"error": "Unauthorized"}, status=401)
    return await handler(request)


def create_app(store: TxStore, proxy_server=None, scheduler=None) -> web.Application:
    middlewares = []
    if AUTH_TOKEN:
        middlewares.append(auth_middleware)
        log.info("API auth enabled (token from APP_PASSWORD/BP_AUTH_TOKEN)")
    else:
        log.warning("API auth DISABLED — no APP_PASSWORD or BP_AUTH_TOKEN set")

    app = web.Application(middlewares=middlewares, client_max_size=2 * 1024 * 1024)  # 2MB max request body
    app["store"] = store
    app["proxy_server"] = proxy_server
    app["scheduler"] = scheduler

    app.router.add_get("/api/txs", handle_list_txs)
    app.router.add_get("/api/txs/{txid}", handle_get_tx)
    app.router.add_post("/api/txs/{txid}/schedule", handle_schedule)
    app.router.add_post("/api/txs/{txid}/broadcast-now", handle_broadcast_now)
    app.router.add_delete("/api/txs/{txid}", handle_delete)
    app.router.add_post("/api/txs/{txid}/reorder", handle_reorder)
    app.router.add_post("/api/txs/{txid}/schedule-mtp", handle_schedule_mtp)
    app.router.add_post("/api/txs/{txid}/auto-schedule-locktime", handle_auto_schedule_locktime)
    app.router.add_post("/api/txs/{txid}/unschedule", handle_unschedule)
    app.router.add_post("/api/txs/{txid}/collection", handle_set_collection)
    app.router.add_post("/api/txs/{txid}/label", handle_set_label)
    app.router.add_post("/api/collections/delete", handle_delete_collection)
    app.router.add_get("/api/diagnostics", handle_diagnostics)
    app.router.add_post("/api/txs/{txid}/retry", handle_retry)
    app.router.add_post("/api/txs/import", handle_import_tx)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/settings", handle_get_settings)
    app.router.add_post("/api/settings", handle_set_settings)
    app.router.add_post("/api/txs/scan-dependencies", handle_scan_dependencies)
    app.router.add_post("/api/txs/resolve-inputs", handle_resolve_inputs)
    app.router.add_post("/api/test-connection", handle_test_connection)
    app.router.add_get("/api/discover-upstreams", handle_discover_upstreams)
    app.router.add_post("/api/npub", handle_set_npub)
    app.router.add_post("/api/preferences", handle_set_preferences)
    app.router.add_post("/api/txs/{txid}/schedule-price", handle_schedule_price)
    app.router.add_get("/api/price", handle_get_price)
    app.router.add_get("/api/discover-price-oracle", handle_discover_price_oracle)
    app.router.add_get("/api/vault", handle_vault)
    app.router.add_post("/api/vault/clear", handle_vault_clear)
    app.router.add_get("/api/conflicts", handle_conflicts)
    app.router.add_get("/api/widget/stats", handle_widget_stats)
    app.router.add_post("/api/pool/export", handle_pool_export)
    app.router.add_post("/api/pool/import-plan", handle_pool_import_plan)
    app.router.add_post("/api/pool/import-apply", handle_pool_import_apply)

    # Static files (frontend)
    app.router.add_get("/", handle_index)
    app.router.add_static("/static", "src/web/static", name="static")

    return app


def _classify_tx(tx) -> list[str]:
    """Classify a tx by its shape. Returns list of tags (can overlap).

    Rules:
    - barrido:       1 input, 1 output
    - consolidacion: >1 input
    - pago:          >1 output (can coexist with consolidacion)
    - lotes:         >2 outputs
    """
    n_in = tx.input_count
    n_out = tx.output_count
    tags = []

    if n_in == 1 and n_out == 1:
        tags.append("barrido")
    if n_in > 1:
        tags.append("consolidacion")
    if n_out > 2:
        tags.append("lotes")
    elif n_out > 1:
        tags.append("pago")

    return tags if tags else []


from src.pool.tx_parser import LOCKTIME_TIMESTAMP_THRESHOLD


def _auto_schedule_by_locktime(store: TxStore, txid: str) -> dict:
    """Schedule a tx according to its nLockTime, if it represents a real future lock.

    Skips Sparrow-style anti-fee-sniping (locktime ~ current height). Used by both
    handle_import_tx and the pool import flow, and by the user clicking the lock icon.
    """
    tx = store.get_tx(txid)
    if not tx:
        return {"scheduled": False, "reason": "not found"}
    if tx.status != "pending":
        return {"scheduled": False, "reason": f"status is '{tx.status}', not pending"}

    locktime = tx.locktime or 0
    if locktime <= 0:
        return {"scheduled": False, "reason": "no locktime"}

    if locktime >= LOCKTIME_TIMESTAMP_THRESHOLD:
        # Timestamp locktime → scheduler's MTP loop will broadcast when MTP > locktime
        store.update_status(txid, "scheduled")
        return {"scheduled": True, "type": "timestamp", "value": locktime}

    current_height = store.get_current_height() or 0
    if locktime > max(current_height, 1) + 1:
        store.update_target_block(txid, locktime)
        return {"scheduled": True, "type": "block", "value": locktime, "target_block": locktime}

    return {"scheduled": False, "reason": "locktime not in future"}


def _classify_locktime(tx, current_height: int, current_mtp: int) -> str:
    """Bucket a tx by its nLockTime relative to the current chain tip.

    Returns one of: "zero" | "future" | "present_past".
    Threshold matches the proxy interceptor: locktime > tip is "future" (so
    tip+1 already counts as future — the user wants no anti-fee-sniping
    warning for txs scheduled one block ahead). Sparrow's anti-fee-sniping
    case (locktime == tip) lands in present_past.
    """
    lt = tx.locktime or 0
    if lt <= 0:
        return "zero"
    if lt >= LOCKTIME_TIMESTAMP_THRESHOLD:
        if current_mtp and current_mtp >= lt:
            return "present_past"
        return "future"
    # Block-height locktime
    if current_height and lt <= current_height:
        return "present_past"
    return "future"


def _tx_to_dict(tx, current_height: int = 0, store: TxStore = None, current_mtp: int = 0) -> dict:
    blocks_remaining = None
    if tx.target_block and current_height:
        blocks_remaining = max(0, tx.target_block - current_height)

    oldest_coin_age = None
    if store and current_height:
        oldest_coin_age = store.get_oldest_coin_age(tx.txid, current_height)

    tx_tags = _classify_tx(tx)

    # Dependency info
    depends_on_info = None
    if tx.depends_on:
        parent = store.get_tx(tx.depends_on) if store else None
        depends_on_info = {
            "txid": tx.depends_on,
            "txid_short": tx.depends_on[:16] + "...",
            "status": parent.status if parent else "unknown",
        }

    # Locktime info
    locktime_info = None
    if tx.locktime > 0:
        if tx.locktime >= LOCKTIME_TIMESTAMP_THRESHOLD:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(tx.locktime, tz=timezone.utc)
            locktime_info = {
                "type": "timestamp",
                "value": tx.locktime,
                "date": dt.strftime("%Y-%m-%d %H:%M UTC"),
            }
        else:
            locktime_info = {
                "type": "block",
                "value": tx.locktime,
            }

    return {
        "txid": tx.txid[:8] + "...",
        "txid_full": tx.txid,
        "tx_tags": tx_tags,
        "input_count": tx.input_count,
        "output_count": tx.output_count,
        "locktime": locktime_info,
        "locktime_category": _classify_locktime(tx, current_height, current_mtp),
        "depends_on": depends_on_info,
        "amount_sats": tx.amount_sats,
        "fee_sats": tx.fee_sats,
        "fee_rate": round(tx.fee_rate, 1),
        "fee_warning": tx.fee_rate > 1000 or (tx.amount_sats > 0 and tx.fee_sats > tx.amount_sats * 0.5),
        "vsize": tx.vsize,
        "wallet_label": tx.wallet_label,
        "collection": tx.collection,
        "status": tx.status,
        "target_block": tx.target_block,
        "target_price": tx.target_price,
        "price_direction": tx.price_direction,
        "expires_at": tx.expires_at,
        "blocks_remaining": blocks_remaining,
        "oldest_coin_age": oldest_coin_age,
        "sort_order": tx.sort_order,
        "error_message": tx.error_message,
        "confirmed_block": tx.confirmed_block,
        "created_at": tx.created_at,
        "broadcast_at": tx.broadcast_at,
    }


async def handle_list_txs(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    status_filter = request.query.get("status")
    txs = store.get_all_txs(status=status_filter)
    current_height = store.get_current_height()
    current_mtp = int(store.get_state("current_mtp") or "0")

    data = {
        "txs": [_tx_to_dict(tx, current_height, store, current_mtp) for tx in txs],
        "collections": store.get_known_collections(),
        "current_height": current_height,
        "total_pending": sum(1 for t in txs if t.status == "pending"),
        "total_scheduled": sum(1 for t in txs if t.status == "scheduled"),
        # Toggle state needed by the UI to decide whether to render the
        # anti-fee-sniping warning. When auto-broadcast is ON for a given
        # locktime category, the user has already opted into the fingerprint
        # trade-off, so the warning is suppressed.
        "auto_broadcast_present_past_locktime":
            store.get_state("auto_broadcast_present_past_locktime") == "true",
        "auto_broadcast_zero_locktime":
            store.get_state("auto_broadcast_zero_locktime") == "true",
    }
    return web.json_response(data)


async def handle_get_tx(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)

    current_height = store.get_current_height()
    current_mtp = int(store.get_state("current_mtp") or "0")
    data = _tx_to_dict(tx, current_height, store, current_mtp)
    data["raw_hex"] = tx.raw_hex
    data["inputs"] = [
        {"prev_txid": i.prev_txid, "prev_vout": i.prev_vout, "value_sats": i.value_sats}
        for i in store.get_inputs(txid)
    ]
    data["outputs"] = [
        {"vout": o.vout, "value_sats": o.value_sats}
        for o in store.get_outputs(txid)
    ]
    return web.json_response(data)


async def handle_schedule(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    body = await request.json()
    target_block = body.get("target_block")

    if not target_block or not isinstance(target_block, int):
        return web.json_response({"error": "target_block (int) required"}, status=400)

    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    if tx.status not in ("pending", "scheduled"):
        return web.json_response({"error": f"Cannot schedule tx in status '{tx.status}'"}, status=400)

    # Check nLockTime constraint: only enforce if locktime is a real future lock
    # (not Sparrow's anti-fee-sniping which sets locktime ≈ current height)
    from src.pool.tx_parser import parse_raw_tx
    try:
        parsed = parse_raw_tx(tx.raw_hex)
        current_height = store.get_current_height()
        is_real_locktime = (0 < parsed.locktime < LOCKTIME_TIMESTAMP_THRESHOLD
                           and current_height > 0
                           and parsed.locktime > current_height + 1)
        if is_real_locktime and target_block < parsed.locktime:
            return web.json_response(
                {"error": f"target_block must be >= nLockTime ({parsed.locktime})"},
                status=400,
            )
    except Exception:
        pass

    store.update_target_block(txid, target_block)

    # If target block is already reached, broadcast immediately
    current_height = store.get_current_height()
    if current_height and target_block <= current_height:
        scheduler = request.app.get("scheduler")
        if scheduler:
            result = await scheduler.broadcast_now(txid)
            return web.json_response({"ok": True, "target_block": target_block, "broadcast": result})

    return web.json_response({"ok": True, "target_block": target_block})


async def handle_schedule_mtp(request: web.Request) -> web.Response:
    """Schedule a tx to broadcast when MTP passes its locktime timestamp."""
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]

    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    if tx.status not in ("pending", "scheduled"):
        return web.json_response({"error": f"Cannot schedule tx in status '{tx.status}'"}, status=400)
    if tx.locktime < LOCKTIME_TIMESTAMP_THRESHOLD:
        return web.json_response({"error": "This tx does not have a timestamp locktime"}, status=400)

    # Mark as scheduled with target_block = None (scheduler uses locktime timestamp + MTP)
    store.update_status(txid, "scheduled")

    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(tx.locktime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return web.json_response({
        "ok": True,
        "message": f"Scheduled for MTP > {dt}",
        "locktime_date": dt,
    })


async def handle_auto_schedule_locktime(request: web.Request) -> web.Response:
    """Schedule a pending tx according to its own nLockTime. Used by the lock-icon click."""
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]

    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    if tx.status != "pending":
        return web.json_response(
            {"error": f"Cannot auto-schedule tx in status '{tx.status}'"}, status=400
        )

    result = _auto_schedule_by_locktime(store, txid)
    if not result.get("scheduled"):
        return web.json_response(
            {"error": result.get("reason", "cannot auto-schedule")}, status=400
        )
    return web.json_response({"ok": True, **result})


async def handle_set_collection(request: web.Request) -> web.Response:
    """Assign (or clear with "") the collection of a retained tx."""
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    collection = body.get("collection", "")
    if not isinstance(collection, str):
        return web.json_response({"error": "collection must be a string"}, status=400)
    collection = collection.strip()
    if len(collection) > 80:
        return web.json_response({"error": "collection too long (max 80 chars)"}, status=400)
    store.set_collection(txid, collection)
    return web.json_response({"ok": True, "collection": collection})


async def handle_delete_collection(request: web.Request) -> web.Response:
    """Delete a collection: unassign it from every tx and forget the name."""
    store: TxStore = request.app["store"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    name = body.get("name", "")
    if not isinstance(name, str) or not name.strip():
        return web.json_response({"error": "name required"}, status=400)
    unassigned = store.delete_collection(name.strip())
    return web.json_response({"ok": True, "unassigned": unassigned})


async def handle_set_label(request: web.Request) -> web.Response:
    """Edit the wallet label of a retained tx."""
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    label = body.get("label", "")
    if not isinstance(label, str):
        return web.json_response({"error": "label must be a string"}, status=400)
    label = label.strip()
    if len(label) > 120:
        return web.json_response({"error": "label too long (max 120 chars)"}, status=400)
    store.set_wallet_label(txid, label)
    return web.json_response({"ok": True, "label": label})


async def handle_unschedule(request: web.Request) -> web.Response:
    """Revert a scheduled tx back to pending."""
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    if tx.status != "scheduled":
        return web.json_response({"error": "Only scheduled txs can be unscheduled"}, status=400)

    with store._lock:
        store._conn.execute(
            "UPDATE retained_txs SET status='pending', target_block=NULL, target_price=NULL, price_direction=NULL, expires_at=NULL, updated_at=datetime('now') WHERE txid=?",
            (txid,),
        )
        store._conn.commit()
    return web.json_response({"ok": True})


async def handle_retry(request: web.Request) -> web.Response:
    """Retry a failed tx: first check blockchain, then rebroadcast if needed."""
    store: TxStore = request.app["store"]
    scheduler = request.app.get("scheduler")
    txid = request.match_info["txid"]

    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)
    if tx.status not in ("failed", "abandoned"):
        return web.json_response({"error": "Only failed/abandoned txs can be retried"}, status=400)

    if not scheduler or not scheduler._upstream:
        return web.json_response({"error": "Not connected to upstream"}, status=503)

    # Step 1: Check if the tx is already confirmed on-chain
    scripthashes = store.get_scripthashes_for_tx(txid)
    for sh in scripthashes:
        try:
            resp = await scheduler._upstream.call(
                "blockchain.scripthash.get_history", [sh]
            )
            for h in resp.get("result", []):
                if h.get("tx_hash") == txid:
                    if h.get("height", 0) > 0:
                        store.set_confirmed(txid, h["height"])
                        return web.json_response({
                            "ok": True,
                            "action": "confirmed",
                            "message": f"Tx already confirmed at block {h['height']}",
                        })
                    else:
                        # In mempool — mark as broadcasting
                        store.update_status(txid, "broadcasting")
                        store.update_broadcast_time(txid)
                        return web.json_response({
                            "ok": True,
                            "action": "in_mempool",
                            "message": "Tx found in mempool, status updated",
                        })
        except Exception:
            continue

    # Step 2: Not found on-chain — try to rebroadcast
    store.update_status(txid, "pending", error=None)
    result = await scheduler.broadcast_now(txid)

    if "error" in result:
        return web.json_response({
            "ok": False,
            "action": "rebroadcast_failed",
            "message": result["error"],
        })

    return web.json_response({
        "ok": True,
        "action": "rebroadcast",
        "message": "Tx rebroadcast successfully",
    })


async def handle_broadcast_now(request: web.Request) -> web.Response:
    scheduler = request.app["scheduler"]
    txid = request.match_info["txid"]

    if not scheduler:
        return web.json_response({"error": "Scheduler not available"}, status=503)

    result = await scheduler.broadcast_now(txid)
    if "error" in result:
        return web.json_response(result, status=400)
    return web.json_response(result)


async def handle_delete(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    deleted = store.delete_tx(txid)
    if not deleted:
        return web.json_response(
            {"error": "Not found or not deletable (only pending/scheduled)"}, status=404
        )
    return web.json_response({"ok": True})


async def handle_import_tx(request: web.Request) -> web.Response:
    """Import a signed transaction from raw hex pasted by the user."""
    store: TxStore = request.app["store"]
    body = await request.json()
    raw_hex = body.get("raw_hex", "").strip()
    wallet_label = body.get("wallet_label", "Manual import")

    if not raw_hex:
        return web.json_response({"error": "raw_hex required"}, status=400)

    # Validate size (200KB hex = ~100KB raw tx, already enormous)
    if len(raw_hex) > 200_000:
        return web.json_response({"error": "Transaction too large"}, status=413)

    # Validate hex
    try:
        bytes.fromhex(raw_hex)
    except ValueError:
        return web.json_response({"error": "Invalid hex string"}, status=400)

    # Parse the transaction
    from src.pool.tx_parser import parse_raw_tx
    try:
        parsed = parse_raw_tx(raw_hex)
    except Exception as e:
        log.warning("Failed to parse imported tx: %s", e)
        return web.json_response({"error": "Invalid transaction hex"}, status=400)

    # Check if already exists
    if store.get_tx(parsed.txid):
        return web.json_response({"error": f"Transaction {parsed.txid[:16]}... already in pool"}, status=409)

    # Save first with fee=0 (will be resolved async)
    parsed.fee_sats = 0
    parsed.fee_rate = 0
    store.save_retained_tx(parsed, raw_hex, wallet_label=wallet_label)

    # Detect dependency: check if any input spends an output of another retained tx
    active_txids = {tx.txid for tx in store.get_active_txs()}
    for inp in parsed.inputs:
        if inp.prev_txid in active_txids:
            store.set_depends_on(parsed.txid, inp.prev_txid)
            break

    # Detect RBF: check if any input overlaps with inputs of an active retained tx
    from src.pool.tx_parser import parse_raw_tx as _parse
    new_outpoints = {(inp.prev_txid, inp.prev_vout) for inp in parsed.inputs}
    for atx in store.get_active_txs():
        if atx.txid == parsed.txid:
            continue
        if atx.raw_hex and len(atx.raw_hex) > 20:
            try:
                existing = _parse(atx.raw_hex)
                for ei in existing.inputs:
                    if (ei.prev_txid, ei.prev_vout) in new_outpoints:
                        store.update_status(atx.txid, "replaced",
                                            error=f"Replaced by {parsed.txid[:16]}...")
                        if atx.target_block:
                            store.update_target_block(parsed.txid, atx.target_block)
                        break
            except Exception:
                pass

    # Auto-schedule if locktime is in the future
    if store.get_state("auto_schedule_locktime") != "false":
        _auto_schedule_by_locktime(store, parsed.txid)

    # Resolve inputs async via scheduler's upstream (fee, coin age, scripthashes)
    scheduler = request.app.get("scheduler")
    if scheduler:
        asyncio.ensure_future(_resolve_imported_tx(store, scheduler, parsed.txid, raw_hex))
        # Post-arrival CPFP rescan: this tx might be the PARENT of an existing
        # retained child (e.g., random-order paste during migration).
        try:
            found = scheduler._scan_dependencies()
            if found:
                log.info("Post-import dep scan: %d new CPFP relationship(s) detected", found)
        except Exception as e:
            log.debug("Post-import dep scan failed: %s", e)

    return web.json_response({
        "ok": True,
        "txid": parsed.txid,
        "message": f"Imported {parsed.txid[:16]}... ({len(parsed.inputs)} inputs, {len(parsed.outputs)} outputs)",
    })


async def _resolve_imported_tx(store: TxStore, scheduler, txid: str, raw_hex: str):
    """Background task: resolve inputs for a manually imported tx."""
    import logging
    log = logging.getLogger(__name__)

    # Wait for scheduler to have an upstream connection
    for _ in range(30):
        if scheduler._upstream:
            break
        await asyncio.sleep(1)
    else:
        log.warning("Cannot resolve imported tx %s: no upstream", txid[:16])
        return

    from src.pool.tx_parser import parse_raw_tx, compute_scripthash
    from src.proxy.upstream import UpstreamConnection

    try:
        parsed = parse_raw_tx(raw_hex)
        upstream = scheduler._upstream

        total_input_value = 0
        for inp in parsed.inputs:
            # Get parent tx raw
            resp = await upstream.call("blockchain.transaction.get", [inp.prev_txid, False])
            parent_raw = resp.get("result", "")
            if not parent_raw or not isinstance(parent_raw, str):
                continue

            parent = parse_raw_tx(parent_raw)
            if inp.prev_vout < len(parent.outputs):
                output = parent.outputs[inp.prev_vout]
                inp.scripthash = output.scripthash
                inp.value_sats = output.value_sats
                total_input_value += output.value_sats

                # Get confirmed height from history
                try:
                    hist = await upstream.call("blockchain.scripthash.get_history", [output.scripthash])
                    for h in hist.get("result", []):
                        if h.get("tx_hash") == inp.prev_txid and h.get("height", 0) > 0:
                            inp.confirmed_height = h["height"]
                            break
                except Exception:
                    pass

        # Update fee
        output_total = sum(o.value_sats for o in parsed.outputs)
        fee = total_input_value - output_total
        fee_rate = fee / parsed.vsize if parsed.vsize > 0 and fee > 0 else 0

        # Update the DB
        with store._lock:
            store._conn.execute(
                "UPDATE retained_txs SET fee_sats=?, fee_rate=?, updated_at=datetime('now') WHERE txid=?",
                (fee, round(fee_rate, 1), txid),
            )
            for inp in parsed.inputs:
                store._conn.execute(
                    """UPDATE retained_tx_inputs
                       SET scripthash=?, value_sats=?, confirmed_height=?
                       WHERE txid=? AND prev_txid=? AND prev_vout=?""",
                    (inp.scripthash, inp.value_sats, inp.confirmed_height,
                     txid, inp.prev_txid, inp.prev_vout),
                )
            store._conn.commit()

        log.info("Resolved imported tx %s: fee=%d sats (%.1f sat/vB)", txid[:16], fee, fee_rate)

    except Exception as e:
        log.warning("Failed to resolve imported tx %s: %s", txid[:16], e)


async def handle_reorder(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    body = await request.json()
    direction = body.get("direction", "down")

    if direction not in ("up", "down"):
        return web.json_response({"error": "direction must be 'up' or 'down'"}, status=400)

    store.reorder(txid, direction)
    return web.json_response({"ok": True})


async def handle_diagnostics(request: web.Request) -> web.Response:
    """Downloadable privacy-preserving diagnostics report (plain text).

    Safe to share publicly: txids, scripthashes, addresses, hex, xpubs,
    nostr keys, IPs and onions are redacted at capture time.
    """
    from src import diagnostics

    store: TxStore = request.app["store"]
    proxy = request.app.get("proxy_server")
    host, port, use_ssl = store.get_upstream()

    txs = store.get_all_txs()
    by_status: dict[str, int] = {}
    for tx in txs:
        by_status[tx.status] = by_status.get(tx.status, 0) + 1

    extra = {
        "network": store.get_detected_network() or store.network,
        "current_height": store.get_current_height(),
        "wallet_connections": proxy.connection_count if proxy else 0,
        "upstream_ssl": use_ssl,
        "upstream_port": port,  # port reveals server type (50001/50002/...), not identity
        "encryption_at_rest": bool(config.APP_SEED),
        "tx_counts_by_status": by_status or "(empty pool)",
    }

    report = diagnostics.build_report(extra)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return web.Response(
        body=report.encode("utf-8"),
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Disposition": f'attachment; filename="bp-diagnostics-{today}.txt"',
        },
    )


async def handle_status(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    proxy = request.app.get("proxy_server")
    scheduler = request.app.get("scheduler")
    host, port, use_ssl = store.get_upstream()

    mtp_raw = store.get_state("current_mtp")
    mtp_ts = int(mtp_raw) if mtp_raw else None

    data = {
        "current_height": store.get_current_height(),
        "current_mtp": mtp_ts,
        "connections": proxy.connection_count if proxy else 0,
        "network": store.get_detected_network(),
        # Real connectivity signal — "network" always carries a fallback value
        # and must not be used to infer connection state
        "upstream_connected": bool(scheduler and scheduler.upstream_connected),
        "upstream_host": host,
        "upstream_port": port,
        "upstream_ssl": use_ssl,
        "npub": store.get_state("npub") or "",
        "total_txs": len(store.get_all_txs()),
        "pending": len(store.get_all_txs(status="pending")),
        "scheduled": len(store.get_all_txs(status="scheduled")),
        "broadcasting": len(store.get_all_txs(status="broadcasting")),
        "confirmed": len(store.get_all_txs(status="confirmed")),
        "failed": len(store.get_all_txs(status="failed")),
        "proxy_port": config.PROXY_PORT,
        "current_price": float(store.get_state("current_price") or 0) or None,
        "price_source": store.get_state("price_source") or "",
        "liana_height_offset": int(store.get_state("liana_height_offset") or "0"),
        "liana_disable_at_height": int(store.get_state("liana_disable_at_height") or "0"),
    }
    return web.json_response(data)


async def handle_get_settings(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    host, port, use_ssl = store.get_upstream()
    return web.json_response({
        "upstream_host": host,
        "upstream_port": port,
        "upstream_ssl": use_ssl,
        "network": store.get_detected_network(),
        "npub": store.get_state("npub") or "",
        "auto_schedule_locktime": store.get_state("auto_schedule_locktime") != "false",
        "auto_broadcast_present_past_locktime": store.get_state("auto_broadcast_present_past_locktime") == "true",
        "auto_broadcast_zero_locktime": store.get_state("auto_broadcast_zero_locktime") == "true",
        "price_source": store.get_state("price_source") or "",
        "price_enabled": bool(store.get_state("price_source")),
        "liana_height_offset": int(store.get_state("liana_height_offset") or "0"),
        "liana_increment_blocks_per_tx": int(store.get_state("liana_increment_blocks_per_tx") or "1000"),
        "liana_disable_at_height": int(store.get_state("liana_disable_at_height") or "0"),
    })


async def handle_set_settings(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    scheduler = request.app.get("scheduler")
    body = await request.json()

    host = body.get("upstream_host", "").strip()
    port = body.get("upstream_port")
    use_ssl = body.get("upstream_ssl", False)

    if not host or not port:
        return web.json_response({"error": "upstream_host and upstream_port required"}, status=400)

    try:
        port = int(port)
    except (ValueError, TypeError):
        return web.json_response({"error": "upstream_port must be a number"}, status=400)

    # Validate upstream
    err = _validate_upstream(host, port)
    if err:
        return web.json_response({"error": err}, status=400)

    store.set_upstream(host, port, use_ssl=bool(use_ssl))
    log.info("Upstream saved: %s:%d ssl=%s", host, port, use_ssl)

    # Reconnect scheduler to new upstream (detects network automatically)
    if scheduler:
        await scheduler.reconnect()

    return web.json_response({
        "ok": True,
        "upstream_host": host,
        "upstream_port": port,
        "message": "Upstream changed. Scheduler reconnecting. Wallet sessions will use new upstream on next connection.",
    })


async def handle_scan_dependencies(request: web.Request) -> web.Response:
    """Re-scan all active txs for CPFP dependencies (debug endpoint).

    The interceptor already calls scheduler._scan_dependencies() after every tx
    is retained, so this endpoint is rarely needed in normal operation — kept
    for manual troubleshooting via curl.
    """
    scheduler = request.app.get("scheduler")
    if not scheduler:
        return web.json_response({"error": "Scheduler unavailable"}, status=503)
    found = scheduler._scan_dependencies()
    return web.json_response({
        "ok": True,
        "found": found,
        "message": f"{found} dependencies detected" if found else "No new dependencies found",
    })


async def handle_resolve_inputs(request: web.Request) -> web.Response:
    """Force resolve all unresolved inputs (fee rates, coin ages)."""
    scheduler = request.app.get("scheduler")
    if not scheduler or not scheduler._upstream:
        return web.json_response({"error": "Not connected to upstream"}, status=503)

    await scheduler._resolve_pending_inputs()
    return web.json_response({"ok": True})


async def handle_test_connection(request: web.Request) -> web.Response:
    """Test connection to a specific host:port (not the current upstream)."""
    body = await request.json()
    host = body.get("host", "").strip()
    port = body.get("port")
    use_ssl = body.get("ssl", False)

    if not host or not port:
        return web.json_response({"ok": False, "error": "host and port required"}, status=400)

    try:
        port = int(port)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "invalid port"}, status=400)

    import asyncio as aio
    import json as jsonlib
    import ssl as sslmod

    try:
        ssl_ctx = None
        if use_ssl:
            ssl_ctx = sslmod.create_default_context()
            from src import config
            if config.ELECTRUM_SSL_NOVERIFY:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = sslmod.CERT_NONE

        reader, writer = await aio.wait_for(
            aio.open_connection(host, port, ssl=ssl_ctx, limit=65536),
            timeout=5.0,
        )

        # Handshake
        req = jsonlib.dumps({"jsonrpc": "2.0", "method": "server.version", "params": ["bp-test", "1.4"], "id": 1}) + "\n"
        writer.write(req.encode())
        await writer.drain()
        line = await aio.wait_for(reader.readline(), timeout=5.0)
        resp = jsonlib.loads(line)

        if "result" not in resp:
            writer.close()
            return web.json_response({"ok": False, "error": str(resp.get("error", "Unknown"))})

        server_name = resp["result"][0] if isinstance(resp["result"], list) else str(resp["result"])

        # Detect network via genesis block header
        import hashlib
        req2 = jsonlib.dumps({"jsonrpc": "2.0", "method": "blockchain.block.header", "params": [0], "id": 2}) + "\n"
        writer.write(req2.encode())
        await writer.drain()
        line2 = await aio.wait_for(reader.readline(), timeout=5.0)
        writer.close()

        network = "unknown"
        try:
            resp2 = jsonlib.loads(line2)
            header_hex = resp2.get("result", "")
            if header_hex:
                header_bytes = bytes.fromhex(header_hex)
                block_hash = hashlib.sha256(hashlib.sha256(header_bytes).digest()).digest()[::-1].hex()
                from src import config
                network = config.GENESIS_HASHES.get(block_hash, "unknown")
        except Exception:
            pass

        return web.json_response({"ok": True, "server": server_name, "network": network})

    except aio.TimeoutError:
        return web.json_response({"ok": False, "error": "Timeout (5s)"})
    except ConnectionRefusedError:
        return web.json_response({"ok": False, "error": "Connection refused"})
    except OSError as e:
        return web.json_response({"ok": False, "error": str(e)})
    except Exception as e:
        return web.json_response({"ok": False, "error": "Connection failed"})


async def handle_discover_upstreams(request: web.Request) -> web.Response:
    """Probe known Umbrel Electrum servers and return which are reachable."""
    import asyncio as aio

    KNOWN_SERVERS = [
        {"name": "Electrs", "host": "10.21.21.10", "port": 50001, "ssl": False},
        {"name": "Fulcrum", "host": "10.21.21.200", "port": 50002, "ssl": False},
        {"name": "ElectrumX", "host": "10.21.21.199", "port": 50001, "ssl": False},
    ]

    async def probe(server):
        try:
            import json as jsonlib
            import hashlib
            reader, writer = await aio.wait_for(
                aio.open_connection(server["host"], server["port"]),
                timeout=2.0,
            )
            # Handshake
            req = jsonlib.dumps({"jsonrpc": "2.0", "method": "server.version", "params": ["bp-probe", "1.4"], "id": 1}) + "\n"
            writer.write(req.encode())
            await writer.drain()
            line = await aio.wait_for(reader.readline(), timeout=2.0)
            resp = jsonlib.loads(line)
            server_name = resp.get("result", [server["name"]])[0] if "result" in resp else server["name"]

            # Detect network via genesis block
            network = "unknown"
            req2 = jsonlib.dumps({"jsonrpc": "2.0", "method": "blockchain.block.header", "params": [0], "id": 2}) + "\n"
            writer.write(req2.encode())
            await writer.drain()
            line2 = await aio.wait_for(reader.readline(), timeout=2.0)
            try:
                resp2 = jsonlib.loads(line2)
                header_hex = resp2.get("result", "")
                if header_hex:
                    header_bytes = bytes.fromhex(header_hex)
                    block_hash = hashlib.sha256(hashlib.sha256(header_bytes).digest()).digest()[::-1].hex()
                    from src import config
                    network = config.GENESIS_HASHES.get(block_hash, "unknown")
            except Exception:
                pass

            writer.close()
            return {**server, "online": True, "server_version": server_name, "network": network}
        except Exception:
            return {**server, "online": False, "server_version": None, "network": None}

    results = await aio.gather(*[probe(s) for s in KNOWN_SERVERS])
    online = [r for r in results if r["online"]]
    return web.json_response({"servers": results, "online": len(online)})


async def handle_set_npub(request: web.Request) -> web.Response:
    """Save npub independently from upstream settings."""
    store: TxStore = request.app["store"]
    body = await request.json()
    npub = body.get("npub", "").strip()
    clear_vault = body.get("clear_vault", False)

    if npub and (not npub.startswith("npub1") or len(npub) < 58):
        return web.json_response({"error": "Invalid npub format"}, status=400)

    store.set_state("npub", npub)

    if clear_vault:
        with store._lock:
            store._conn.execute("DELETE FROM vault_entries")
            store._conn.commit()
        log.info("Vault cleared (npub changed)")

    return web.json_response({"ok": True, "npub": npub})


async def handle_set_preferences(request: web.Request) -> web.Response:
    """Save UI preferences (auto_schedule_locktime, etc.)."""
    store: TxStore = request.app["store"]
    body = await request.json()

    if "auto_schedule_locktime" in body:
        val = "true" if body["auto_schedule_locktime"] else "false"
        store.set_state("auto_schedule_locktime", val)

    if "auto_broadcast_present_past_locktime" in body:
        val = "true" if body["auto_broadcast_present_past_locktime"] else "false"
        store.set_state("auto_broadcast_present_past_locktime", val)

    if "auto_broadcast_zero_locktime" in body:
        val = "true" if body["auto_broadcast_zero_locktime"] else "false"
        store.set_state("auto_broadcast_zero_locktime", val)

    if "price_source" in body:
        source = body["price_source"].strip()
        if source and source != "coingecko":
            from urllib.parse import urlparse
            parsed_url = urlparse(source)
            if parsed_url.scheme not in ("http", "https"):
                return web.json_response({"error": "Only http/https URLs allowed"}, status=400)
        store.set_state("price_source", source)
        if not source:
            store.set_state("current_price", "")

    # Hard cap: the faker can only run for LIANA_FAKER_MAX_BLOCKS real blocks total.
    # Use case is signing future-locktime cycling txs (<2h). Not editable by the user.
    LIANA_FAKER_MAX_BLOCKS = 12

    if "liana_height_offset" in body:
        try:
            offset = int(body["liana_height_offset"])
            if offset < 0 or offset > 70000:
                return web.json_response(
                    {"error": "liana_height_offset must be 0-70000 (~15 months)"},
                    status=400,
                )
            store.set_state("liana_height_offset", str(offset))
            if offset > 0:
                # Set the 12-block cutoff on first activation; preserve existing countdown
                # if the user is just tweaking the offset value mid-run.
                existing_cutoff = int(store.get_state("liana_disable_at_height") or "0")
                if existing_cutoff <= 0:
                    current = store.get_current_height() or 0
                    if current > 0:
                        store.set_state(
                            "liana_disable_at_height", str(current + LIANA_FAKER_MAX_BLOCKS)
                        )
            else:
                # Offset cleared → clear the cutoff too (next activation starts fresh)
                store.set_state("liana_disable_at_height", "0")
        except (ValueError, TypeError):
            return web.json_response({"error": "liana_height_offset must be an integer"}, status=400)

    if "liana_increment_blocks_per_tx" in body:
        try:
            bump = int(body["liana_increment_blocks_per_tx"])
            if bump < 1 or bump > 10000:
                return web.json_response(
                    {"error": "liana_increment_blocks_per_tx must be 1-10000"},
                    status=400,
                )
            store.set_state("liana_increment_blocks_per_tx", str(bump))
        except (ValueError, TypeError):
            return web.json_response(
                {"error": "liana_increment_blocks_per_tx must be an integer"}, status=400
            )

    return web.json_response({"ok": True})


async def handle_schedule_price(request: web.Request) -> web.Response:
    """Schedule a tx to broadcast when price crosses a threshold."""
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    body = await request.json()

    price = body.get("target_price")
    direction = body.get("direction", "below")
    expires_at = body.get("expires_at")
    if expires_at:
        try:
            from datetime import datetime as dt
            dt.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return web.json_response({"error": "expires_at must be ISO format"}, status=400)

    if not price or not isinstance(price, (int, float)) or price <= 0:
        return web.json_response({"error": "target_price (positive number) required"}, status=400)

    if direction not in ("below", "above"):
        return web.json_response({"error": "direction must be 'below' or 'above'"}, status=400)

    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Transaction not found"}, status=404)

    store.update_target_price(txid, float(price), direction, expires_at=expires_at)
    log.info("Price-scheduled tx %s: %s $%.0f expires=%s", txid[:16], direction, price, expires_at or "never")

    return web.json_response({"ok": True, "target_price": price, "direction": direction, "expires_at": expires_at})


async def handle_get_price(request: web.Request) -> web.Response:
    """Return current BTC/USD price and source config."""
    store: TxStore = request.app["store"]
    price_raw = store.get_state("current_price")
    return web.json_response({
        "price_usd": float(price_raw) if price_raw else None,
        "source": store.get_state("price_source") or "",
    })


async def handle_discover_price_oracle(request: web.Request) -> web.Response:
    """Probe known local addresses for El Oráculo (bitcoin-price-oracle).

    On Umbrel, BP and the oracle live on separate per-app Docker networks, so
    the oracle's Docker DNS name doesn't resolve and ``127.0.0.1`` points at BP
    itself. ``host.docker.internal`` (declared via ``extra_hosts: host-gateway``
    in docker-compose.yml) reaches the Umbrel host, where the oracle publishes
    its port — this is the path that actually works in production.
    """
    import aiohttp as aio

    # The oracle moved from 3200 to 7777 starting with its next release. We
    # probe 7777 first (forward-looking) and keep 3200 as a fallback for users
    # still on the old version.
    hosts = ("host.docker.internal", "bitcoin-price-oracle", "127.0.0.1")
    ports = (7777, 3200)
    candidates = [
        {"host": h, "port": p, "name": "Price oracle"}
        for p in ports for h in hosts
    ]

    results = []
    timeout = aio.ClientTimeout(total=3)
    async with aio.ClientSession(timeout=timeout) as session:
        for c in candidates:
            url = f"http://{c['host']}:{c['port']}"
            try:
                async with session.get(f"{url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("synced_height"):
                            # Get current price
                            price = None
                            try:
                                async with session.get(f"{url}/api/price/latest") as pr:
                                    pd = await pr.json()
                                    price = pd.get("price_usd")
                            except Exception:
                                pass
                            results.append({
                                "url": url,
                                "name": c["name"],
                                "synced_height": data["synced_height"],
                                "price_usd": price,
                                "online": True,
                            })
            except Exception:
                pass

    return web.json_response({"oracles": results})


async def handle_vault(request: web.Request) -> web.Response:
    """Return encrypted vault entries (opaque blobs)."""
    store: TxStore = request.app["store"]
    # For now return empty list — vault entries will be populated when NIP-44 is implemented
    try:
        rows = store._conn.execute(
            "SELECT id, ephem_pubkey, payload, network, created_at FROM vault_entries WHERE network = ? ORDER BY id DESC",
            (store.network,),
        ).fetchall()
        entries = [dict(r) for r in rows]
    except Exception:
        entries = []
    return web.json_response({"entries": entries, "count": len(entries)})


async def handle_vault_clear(request: web.Request) -> web.Response:
    """Delete all vault entries (used when npub changes)."""
    store: TxStore = request.app["store"]
    with store._lock:
        store._conn.execute("DELETE FROM vault_entries")
        store._conn.commit()
    log.info("Vault cleared (npub changed)")
    return web.json_response({"ok": True})


async def handle_conflicts(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    failed = store.get_all_txs(status="failed")
    conflicts = [
        {"txid": tx.txid, "error": tx.error_message}
        for tx in failed
        if tx.error_message and "conflict" in tx.error_message.lower()
    ]
    return web.json_response({"conflicts": conflicts, "count": len(conflicts)})


async def handle_widget_stats(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    proxy = request.app.get("proxy_server")

    height = store.get_current_height()
    pending = len(store.get_all_txs(status="pending"))
    scheduled = len(store.get_all_txs(status="scheduled"))
    connections = proxy.connection_count if proxy else 0

    return web.json_response({
        "type": "four-stats",
        "items": [
            {"title": "Retenidas", "text": str(pending + scheduled), "subtext": "transacciones"},
            {"title": "Programadas", "text": str(scheduled), "subtext": "con bloque"},
            {"title": "Altura", "text": f"{height:,}", "subtext": "actual"},
            {"title": "Conexiones", "text": str(connections), "subtext": "wallets"},
        ],
    })


# --- Pool export / import (Phase 1: no conflict wizard) ---

async def handle_pool_export(request: web.Request) -> web.Response:
    """Export active retained txs (pending + scheduled) as an encrypted .bp file.

    Body: { method: "passphrase" | "nip44" | "none", passphrase?, npub?,
            collections?: ["lending", ...] }  — when present and non-empty,
            only txs belonging to those collections are exported (e.g. to hand
            a single collection to another BP node).
    Returns: application/octet-stream with the .bp/.jsonl file content.
    """
    from src.pool import export as pool_export

    store: TxStore = request.app["store"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    method = body.get("method", "")
    if method not in ("passphrase", "nip44", "none"):
        return web.json_response(
            {"error": "method must be 'passphrase', 'nip44' or 'none'"}, status=400
        )

    collections = body.get("collections")
    if collections is not None and (
        not isinstance(collections, list)
        or not all(isinstance(c, str) and c.strip() for c in collections)
    ):
        return web.json_response(
            {"error": "collections must be a list of non-empty strings"}, status=400
        )

    txs = [
        *store.get_all_txs(status="pending"),
        *store.get_all_txs(status="scheduled"),
    ]
    if collections:
        wanted = {c.strip() for c in collections}
        txs = [tx for tx in txs if tx.collection in wanted]
        if not txs:
            return web.json_response(
                {"error": "no active txs in the selected collections"}, status=400
            )
    txs_data: list[dict] = []
    for tx in txs:
        raw = store.get_raw_hex(tx.txid)
        if not raw or raw.startswith("["):
            log.warning("Skipping tx %s from export: cannot decrypt raw_hex", tx.txid[:16])
            continue
        # Collect inputs (precomputed in DB) so the import side can detect conflicts
        # without re-parsing — server will still verify by re-parsing on import-plan.
        inputs = [
            {"prev_txid": inp.prev_txid, "prev_vout": inp.prev_vout}
            for inp in store.get_inputs(tx.txid)
        ]
        txs_data.append({
            "txid": tx.txid,
            "raw_hex": raw,
            "target_block": tx.target_block,
            "target_price": tx.target_price,
            "price_direction": tx.price_direction,
            "expires_at": tx.expires_at,
            "depends_on": tx.depends_on,
            "wallet_label": tx.wallet_label,
            "collection": tx.collection,
            "locktime": tx.locktime,
            "created_at": tx.created_at,
            "inputs": inputs,
        })

    # v2: the cleartext document is BIP-329 dialect JSONL (see pool/export.py)
    jsonl_text = pool_export.build_jsonl(txs_data, store.network)

    # Filename scope suffix: full pool vs selected collections
    if collections:
        wanted_sorted = sorted({c.strip() for c in collections})
        if len(wanted_sorted) == 1:
            slug = re.sub(r"[^a-z0-9]+", "-", wanted_sorted[0].lower()).strip("-") or "coleccion"
            scope = f"-{slug}"
        else:
            scope = f"-{len(wanted_sorted)}colecciones"
    else:
        scope = ""

    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        if method == "passphrase":
            passphrase = body.get("passphrase", "")
            if not isinstance(passphrase, str) or len(passphrase) < 8:
                return web.json_response(
                    {"error": "passphrase must be at least 8 characters "
                              "(use method='none' for unencrypted export)"},
                    status=400,
                )
            enc_block = pool_export.encrypt_passphrase(jsonl_text, passphrase)
        elif method == "nip44":
            npub = (body.get("npub") or store.get_state("npub") or "").strip()
            if not npub:
                return web.json_response(
                    {"error": "npub required for NIP-44 export (set one in Settings)"},
                    status=400,
                )
            enc_block = pool_export.encrypt_nip44(jsonl_text, npub)
        else:  # method == "none" — the file IS the BIP-329 dialect JSONL, no wrapper
            log.warning("Pool exported UNENCRYPTED — %d txs", len(txs_data))
            filename = f"broadcast-pool-export{scope}-{store.network}-{today}.jsonl"
            return web.Response(
                body=jsonl_text.encode("utf-8"),
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Tx-Count": str(len(txs_data)),
                },
            )
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        log.error("Export encryption failed: %s", e, exc_info=True)
        return web.json_response({"error": "Encryption failed"}, status=500)

    file_obj = pool_export.wrap_file(store.network, enc_block)
    body_bytes = json.dumps(file_obj, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"broadcast-pool-export{scope}-{store.network}-{today}.bp"
    return web.Response(
        body=body_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Tx-Count": str(len(txs_data)),
        },
    )


def _validate_import_payload(payload: dict, store: TxStore) -> tuple[list[dict], str | None]:
    """Validate the cleartext payload. Returns (txs_list, error)."""
    if not isinstance(payload, dict):
        return [], "payload must be a JSON object"
    if payload.get("version") not in (1, 2):
        return [], f"unsupported export version: {payload.get('version')}"
    if payload.get("network") and payload["network"] != store.network:
        return [], (
            f"network mismatch: export is for '{payload.get('network')}' "
            f"but this instance is on '{store.network}'"
        )
    txs = payload.get("txs")
    if not isinstance(txs, list):
        return [], "payload.txs must be a list"
    return txs, None


async def _decrypt_request(body: dict) -> tuple[dict | None, web.Response | None]:
    """Resolve the body into a cleartext payload dict.

    Body shapes:
    - { decrypted_payload: {...} | "jsonl…" }            — used by NIP-44 (browser decrypted;
                                                           v1 sends the dict, v2 the JSONL text)
    - { file: {...}, method: "passphrase", passphrase }  — server decrypts AES-GCM
    - { file: "jsonl…" }                                 — unencrypted v2 (.jsonl) or pasted v1 JSON
    """
    from src.pool import export as pool_export

    if "decrypted_payload" in body:
        decrypted = body["decrypted_payload"]
        if isinstance(decrypted, str):
            try:
                return pool_export.parse_cleartext(decrypted), None
            except ValueError as e:
                return None, web.json_response({"error": str(e)}, status=400)
        return decrypted, None

    file_obj = body.get("file")
    if isinstance(file_obj, str):
        try:
            return pool_export.parse_cleartext(file_obj), None
        except ValueError as e:
            return None, web.json_response({"error": str(e)}, status=400)
    if not isinstance(file_obj, dict):
        return None, web.json_response(
            {"error": "Provide either 'decrypted_payload' or 'file'+'passphrase'"},
            status=400,
        )
    method = file_obj.get("encryption", "")
    if method == "passphrase":
        passphrase = body.get("passphrase", "")
        if not isinstance(passphrase, str) or not passphrase:
            return None, web.json_response({"error": "passphrase required"}, status=400)
        try:
            return pool_export.decrypt_passphrase(file_obj, passphrase), None
        except ValueError as e:
            return None, web.json_response({"error": str(e)}, status=400)
    if method == "nip44":
        return None, web.json_response(
            {"error": "NIP-44 files must be decrypted in the browser; send 'decrypted_payload'"},
            status=400,
        )
    if method == "none":
        try:
            return pool_export.decrypt_unencrypted(file_obj), None
        except ValueError as e:
            return None, web.json_response({"error": str(e)}, status=400)
    return None, web.json_response({"error": f"Unknown encryption: {method}"}, status=400)


async def handle_pool_import_plan(request: web.Request) -> web.Response:
    """Analyze an import file: classify each tx as add / duplicate / utxo-conflict.

    Body shapes (see _decrypt_request).
    Returns: { to_add: [...], duplicates: [txid...], conflicts: [...], errors: [...] }
    """
    from src.pool.tx_parser import parse_raw_tx

    store: TxStore = request.app["store"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    payload, err_resp = await _decrypt_request(body)
    if err_resp is not None:
        return err_resp

    txs, err = _validate_import_payload(payload, store)
    if err:
        return web.json_response({"error": err}, status=400)

    to_add: list[dict] = []
    duplicates: list[str] = []
    conflicts: list[dict] = []
    errors: list[dict] = []

    for entry in txs:
        txid_hint = entry.get("txid", "")
        raw_hex = entry.get("raw_hex", "")
        if not raw_hex:
            errors.append({"txid": txid_hint, "error": "missing raw_hex"})
            continue
        # Optional integrity check: SHA-256 of raw_hex. Newer exports include it,
        # older ones don't — only validate when the field is present.
        checksum = entry.get("raw_hex_checksum")
        if checksum:
            actual = hashlib.sha256(raw_hex.encode("ascii")).hexdigest()
            if actual != checksum:
                errors.append({"txid": txid_hint, "error": "raw_hex checksum mismatch (file corrupted?)"})
                continue
        try:
            parsed = parse_raw_tx(raw_hex)
        except Exception as e:
            errors.append({"txid": txid_hint, "error": f"parse failed: {e}"})
            continue
        if txid_hint and txid_hint != parsed.txid:
            errors.append({"txid": txid_hint, "error": "txid mismatch (hex tampered?)"})
            continue

        if store.get_tx(parsed.txid):
            duplicates.append(parsed.txid)
            continue

        # UTXO conflict detection: any input already being spent by an active tx?
        conflicting_pool_txids: set[str] = set()
        shared_utxos: list[str] = []
        for inp in parsed.inputs:
            poolers = store.find_active_txs_spending_utxo(inp.prev_txid, inp.prev_vout)
            if poolers:
                conflicting_pool_txids.update(poolers)
                shared_utxos.append(f"{inp.prev_txid}:{inp.prev_vout}")

        if conflicting_pool_txids:
            conflicts.append({
                "imported_txid": parsed.txid,
                "imported_target_block": entry.get("target_block"),
                "existing_txids": sorted(conflicting_pool_txids),
                "shared_utxos": shared_utxos,
            })
        else:
            to_add.append({
                "txid": parsed.txid,
                "target_block": entry.get("target_block"),
                "target_price": entry.get("target_price"),
                "wallet_label": entry.get("wallet_label", ""),
                "collection": entry.get("collection") or "",
                "amount_sats": sum(o.value_sats for o in parsed.outputs),
            })

    return web.json_response({
        "network": store.network,
        "to_add": to_add,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "errors": errors,
    })


async def handle_pool_import_apply(request: web.Request) -> web.Response:
    """Apply an import. Phase 1 refuses to proceed if any UTXO conflicts remain.

    Body: same shape as import-plan, plus:
      - resolutions: { <imported_txid>: "skip" | "add" | "replace" }
        (Phase 2 will use this; Phase 1 only honors "skip" — conflicts force a 409 otherwise.)

    All imported txs are written with status='pending' regardless of their original status.
    """
    from src.pool.tx_parser import parse_raw_tx

    store: TxStore = request.app["store"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    payload, err_resp = await _decrypt_request(body)
    if err_resp is not None:
        return err_resp

    txs, err = _validate_import_payload(payload, store)
    if err:
        return web.json_response({"error": err}, status=400)

    resolutions = body.get("resolutions") or {}
    if not isinstance(resolutions, dict):
        return web.json_response({"error": "resolutions must be an object"}, status=400)

    # First pass: re-build the plan to validate conflicts haven't drifted since import-plan
    parsed_cache: dict[str, tuple] = {}
    blocking_conflicts: list[dict] = []
    for entry in txs:
        raw_hex = entry.get("raw_hex", "")
        if not raw_hex:
            continue
        # Same checksum check as import-plan — apply must not write a corrupted tx
        # if a caller skips the plan step.
        checksum = entry.get("raw_hex_checksum")
        if checksum and hashlib.sha256(raw_hex.encode("ascii")).hexdigest() != checksum:
            continue
        try:
            parsed = parse_raw_tx(raw_hex)
        except Exception:
            continue
        if store.get_tx(parsed.txid):
            continue  # duplicate → skipped silently
        conflicting: list[str] = []
        for inp in parsed.inputs:
            poolers = store.find_active_txs_spending_utxo(inp.prev_txid, inp.prev_vout)
            conflicting.extend(poolers)
        if conflicting and resolutions.get(parsed.txid) != "skip":
            blocking_conflicts.append({
                "imported_txid": parsed.txid,
                "existing_txids": sorted(set(conflicting)),
            })
        parsed_cache[parsed.txid] = (parsed, entry, bool(conflicting))

    if blocking_conflicts:
        return web.json_response(
            {
                "error": "utxo_conflicts",
                "message": (
                    "Some imported txs share UTXOs with active pool txs. "
                    "Phase 1 cannot resolve these automatically — resolve manually or skip them."
                ),
                "conflicts": blocking_conflicts,
            },
            status=409,
        )

    # Apply: write txs with status='pending', re-derive metadata, then re-attach schedule.
    added = 0
    skipped = 0
    errors: list[dict] = []
    for txid, (parsed, entry, had_conflict) in parsed_cache.items():
        if had_conflict and resolutions.get(txid) == "skip":
            skipped += 1
            continue
        try:
            parsed.fee_sats = 0
            parsed.fee_rate = 0
            store.save_retained_tx(
                parsed,
                entry["raw_hex"],
                wallet_label=entry.get("wallet_label") or "Pool import",
            )
            if entry.get("collection"):
                store.set_collection(parsed.txid, str(entry["collection"]))
            # depends_on: only set if the parent is also being imported or already in pool
            dep = entry.get("depends_on")
            if dep and store.get_tx(dep):
                store.set_depends_on(parsed.txid, dep)
            # Auto-schedule by nLockTime if user has the pref on (consistent with
            # the single-tx import path). Falls through to 'pending' if locktime
            # isn't in the future.
            auto_scheduled = False
            if store.get_state("auto_schedule_locktime") != "false":
                res = _auto_schedule_by_locktime(store, parsed.txid)
                auto_scheduled = bool(res.get("scheduled"))
            # If nLockTime didn't schedule, fall back to the target_block recorded
            # in the export (user explicitly scheduled it at a different height).
            if not auto_scheduled:
                target_block = entry.get("target_block")
                if target_block:
                    store.update_target_block(parsed.txid, int(target_block), keep_status=True)
            added += 1
        except Exception as e:
            log.error("Failed to import tx %s: %s", txid[:16], e, exc_info=True)
            errors.append({"txid": txid, "error": str(e)})

    # After a batch import, do one full CPFP rescan instead of N per-tx. Catches
    # parent-after-child relationships within the batch and against existing pool.
    if added > 0:
        scheduler = request.app.get("scheduler")
        if scheduler:
            try:
                found = scheduler._scan_dependencies()
                if found:
                    log.info("Post-pool-import dep scan: %d new CPFP relationship(s) detected", found)
            except Exception as e:
                log.debug("Post-pool-import dep scan failed: %s", e)

    return web.json_response({
        "added": added,
        "skipped": skipped,
        "duplicates": sum(1 for entry in txs if store.get_tx(entry.get("txid", "")) and entry.get("txid") not in parsed_cache),
        "errors": errors,
    })


async def handle_index(request: web.Request) -> web.Response:
    return web.FileResponse("src/web/static/index.html")
