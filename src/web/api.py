"""Web API — REST endpoints + static file serving."""

import asyncio
import json
import logging
import os

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
        if token != AUTH_TOKEN:
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
    app.router.add_post("/api/txs/{txid}/unschedule", handle_unschedule)
    app.router.add_post("/api/txs/{txid}/retry", handle_retry)
    app.router.add_post("/api/txs/auto-assign", handle_auto_assign)
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
    app.router.add_get("/api/vault", handle_vault)
    app.router.add_post("/api/vault/clear", handle_vault_clear)
    app.router.add_get("/api/conflicts", handle_conflicts)
    app.router.add_get("/api/widget/stats", handle_widget_stats)

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


def _tx_to_dict(tx, current_height: int = 0, store: TxStore = None) -> dict:
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
        if tx.locktime >= 500_000_000:
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
        "txid": tx.txid[:16] + "...",
        "txid_full": tx.txid,
        "tx_tags": tx_tags,
        "input_count": tx.input_count,
        "output_count": tx.output_count,
        "locktime": locktime_info,
        "depends_on": depends_on_info,
        "amount_sats": tx.amount_sats,
        "fee_sats": tx.fee_sats,
        "fee_rate": round(tx.fee_rate, 1),
        "fee_warning": tx.fee_rate > 1000 or (tx.amount_sats > 0 and tx.fee_sats > tx.amount_sats * 0.5),
        "vsize": tx.vsize,
        "wallet_label": tx.wallet_label,
        "status": tx.status,
        "target_block": tx.target_block,
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

    data = {
        "txs": [_tx_to_dict(tx, current_height, store) for tx in txs],
        "current_height": current_height,
        "total_pending": sum(1 for t in txs if t.status == "pending"),
        "total_scheduled": sum(1 for t in txs if t.status == "scheduled"),
    }
    return web.json_response(data)


async def handle_get_tx(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    txid = request.match_info["txid"]
    tx = store.get_tx(txid)
    if not tx:
        return web.json_response({"error": "Not found"}, status=404)

    current_height = store.get_current_height()
    data = _tx_to_dict(tx, current_height, store)
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
        is_real_locktime = (0 < parsed.locktime < 500_000_000
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
    if tx.locktime < 500_000_000:
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
            "UPDATE retained_txs SET status='pending', target_block=NULL, updated_at=datetime('now') WHERE txid=?",
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

    # Resolve inputs async via scheduler's upstream (fee, coin age, scripthashes)
    scheduler = request.app.get("scheduler")
    if scheduler:
        asyncio.ensure_future(_resolve_imported_tx(store, scheduler, parsed.txid, raw_hex))

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


async def handle_auto_assign(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    body = await request.json()
    base_block = body.get("base_block")
    offset = body.get("offset", 1)
    txids = body.get("txids")

    if not base_block or not isinstance(base_block, int):
        return web.json_response({"error": "base_block (int) required"}, status=400)

    count = store.auto_assign(base_block, offset, txids)
    return web.json_response({"ok": True, "assigned": count})


async def handle_status(request: web.Request) -> web.Response:
    store: TxStore = request.app["store"]
    proxy = request.app.get("proxy_server")
    host, port, use_ssl = store.get_upstream()

    mtp_raw = store.get_state("current_mtp")
    mtp_ts = int(mtp_raw) if mtp_raw else None

    data = {
        "current_height": store.get_current_height(),
        "current_mtp": mtp_ts,
        "connections": proxy.connection_count if proxy else 0,
        "network": store.get_detected_network(),
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
    """Re-scan all active txs for dependencies (CPFP chains)."""
    store: TxStore = request.app["store"]
    from src.pool.tx_parser import parse_raw_tx

    active = store.get_all_txs()
    active_txids = {tx.txid for tx in active}
    found = 0

    for tx in active:
        if tx.depends_on:
            continue  # Already has dependency
        if not tx.raw_hex or len(tx.raw_hex) < 20:
            continue
        try:
            parsed = parse_raw_tx(tx.raw_hex)
            for inp in parsed.inputs:
                if inp.prev_txid in active_txids:
                    store.set_depends_on(tx.txid, inp.prev_txid)
                    found += 1
                    break
        except Exception:
            continue

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

    return web.json_response({"ok": True})


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


async def handle_index(request: web.Request) -> web.Response:
    return web.FileResponse("src/web/static/index.html")
