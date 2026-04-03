"""Broadcast Pool — Entry point.

Starts three asyncio components:
1. ElectrumProxy (TCP :50005)
2. Scheduler (block monitor + broadcast dispatcher)
3. WebAPI (HTTP :3080)
"""

import asyncio
import logging
import os
import signal

from aiohttp import web

from src import config
from src.db.schema import init_db
from src.pool.store import TxStore
from src.proxy.server import ProxyServer
from src.scheduler.scheduler import Scheduler
from src.web.api import create_app

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("broadcast-pool")


async def main():
    log.info("Starting Broadcast Pool")
    log.info("Upstream: %s:%d", config.ELECTRUM_HOST, config.ELECTRUM_PORT)
    log.info("Proxy port: %d, Web port: %d", config.PROXY_PORT, config.WEB_PORT)

    # Initialize database
    conn = init_db(config.DB_PATH)
    store = TxStore(conn)
    log.info("Database initialized at %s", config.DB_PATH)

    # Create components
    proxy = ProxyServer(store)
    scheduler = Scheduler(store, notify_callback=proxy.notify_all_sessions)
    web_app = create_app(store, proxy_server=proxy, scheduler=scheduler)

    # Start proxy
    await proxy.start()

    # Start scheduler in background
    scheduler_task = asyncio.create_task(scheduler.start())

    # Start web server
    runner = web.AppRunner(web_app)
    await runner.setup()
    bind_host = os.environ.get("WEB_BIND", "127.0.0.1")
    site = web.TCPSite(runner, bind_host, config.WEB_PORT)
    log.info("Web bind: %s", bind_host)
    await site.start()
    log.info("Web UI listening on :%d", config.WEB_PORT)

    # Wait for shutdown signal
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # Graceful shutdown — order matters
    log.info("Shutting down...")

    # 1. Stop accepting new wallet connections
    await proxy.stop_listening()
    log.info("Stopped accepting new connections")

    # 2. Stop scheduler (finish any in-flight broadcast, then close upstream)
    await scheduler.stop()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    log.info("Scheduler stopped")

    # 3. Close all active wallet sessions
    await proxy.stop()
    log.info("All sessions closed")

    # 4. Stop web server
    await runner.cleanup()

    # 5. Flush and close database
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
