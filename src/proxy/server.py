"""Electrum proxy TCP server."""

import asyncio
import logging

from src.pool.store import TxStore
from src.proxy.session import ElectrumSession
from src import config

log = logging.getLogger(__name__)


class ProxyServer:
    """TCP server that accepts wallet connections and creates sessions."""

    def __init__(self, store: TxStore):
        self.store = store
        self.sessions: list[ElectrumSession] = []
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_connection,
            host="0.0.0.0",
            port=config.PROXY_PORT,
            limit=1_048_576,  # 1MB max line — prevents DoS via oversized requests
        )
        log.info("Electrum proxy listening on :%d", config.PROXY_PORT)

    async def stop_listening(self) -> None:
        """Stop accepting new connections but keep existing sessions alive."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def stop(self) -> None:
        """Close all active sessions."""
        await self.stop_listening()
        for session in list(self.sessions):
            await session._close()

    @property
    def connection_count(self) -> int:
        return len(self.sessions)

    async def notify_all_sessions(self, scripthashes: set[str]) -> None:
        """Notify all connected wallets about changes to these scripthashes."""
        for session in list(self.sessions):
            await session._notify_subscriptions(scripthashes)

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        session = ElectrumSession(
            client_reader=reader,
            client_writer=writer,
            store=self.store,
            on_close=self._remove_session,
        )
        self.sessions.append(session)
        await session.run()

    def _remove_session(self, session: ElectrumSession) -> None:
        if session in self.sessions:
            self.sessions.remove(session)
