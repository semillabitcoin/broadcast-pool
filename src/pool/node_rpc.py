"""Minimal async JSON-RPC client for a Bitcoin node.

Works with any node exposing the standard Bitcoin JSON-RPC: Bitcoin Core,
Bitcoin Knots, Libre Relay — they share the same RPC methods, auth and error
codes, so nothing here is implementation-specific.

Used as a fallback when the upstream Electrum server (electrs/Fulcrum) is
unavailable or too slow: the scheduler can still read chain height + MTP
(``getblockchaininfo``), broadcast transactions (``sendrawtransaction``) and
verify confirmations (``getrawtransaction`` → ``getblockheader``) by talking
directly to the node's RPC interface.

Opt-in: only active when BITCOIN_RPC_HOST (+ credentials) is configured. On
Umbrel the bitcoin app injects APP_BITCOIN_NODE_IP / APP_BITCOIN_RPC_PORT /
APP_BITCOIN_RPC_USER / APP_BITCOIN_RPC_PASS, wired in docker-compose.yml.

Confirmation lookups via ``getrawtransaction`` require ``txindex=1`` on the
node (broadcasting and height/MTP do not).
"""
from __future__ import annotations

import logging

import aiohttp

from src import config

log = logging.getLogger(__name__)


class NodeRPCError(Exception):
    """A JSON-RPC ``error`` object returned by the Bitcoin node.

    ``code`` is the node's numeric RPC error code — the standard Bitcoin RPC
    codes shared by Core/Knots/Libre Relay (e.g. -27 already-in-chain,
    -25 missing inputs, -26 policy/consensus rejection); ``message`` is the
    human-readable reason. A real node decision always carries an int code.
    """

    def __init__(self, code: int | None, message: str):
        super().__init__(message if code is None else f"[{code}] {message}")
        self.code = code
        self.message = message


class NodeRPCTransportError(NodeRPCError):
    """A transport/auth/parse failure — NOT a node-side decision about the tx.

    Kept distinct (``code is None``) so callers never confuse "couldn't reach
    the node" with a real JSON-RPC rejection like -25/-26/-27.
    """

    def __init__(self, message: str):
        super().__init__(None, message)


class NodeRPC:
    """Thin async wrapper over a Bitcoin node's HTTP JSON-RPC (Core/Knots/Libre Relay)."""

    def __init__(self, host: str, port: int, user: str = "", password: str = "",
                 cookie_file: str = "", timeout: float = 20.0):
        self.host = host
        self.port = port
        self._user = user
        self._password = password
        self._cookie_file = cookie_file
        self._timeout = timeout
        self._url = f"http://{host}:{port}/"

    # ------------------------------------------------------------------ factory
    @classmethod
    def from_config(cls) -> "NodeRPC | None":
        """Build from BITCOIN_RPC_* env config, or None if not configured."""
        if not config.BITCOIN_RPC_HOST:
            return None
        if not (config.BITCOIN_RPC_USER and config.BITCOIN_RPC_PASS) and not config.BITCOIN_RPC_COOKIE_FILE:
            log.warning("BITCOIN_RPC_HOST set but no credentials (user/pass or cookie) — Bitcoin node fallback disabled")
            return None
        return cls(
            host=config.BITCOIN_RPC_HOST,
            port=config.BITCOIN_RPC_PORT,
            user=config.BITCOIN_RPC_USER,
            password=config.BITCOIN_RPC_PASS,
            cookie_file=config.BITCOIN_RPC_COOKIE_FILE,
        )

    # ------------------------------------------------------------------ auth
    def _auth(self) -> aiohttp.BasicAuth:
        if self._cookie_file:
            # Cookie rotates when bitcoind restarts — read fresh each call.
            try:
                with open(self._cookie_file, "r") as f:
                    user, _, pw = f.read().strip().partition(":")
                return aiohttp.BasicAuth(user, pw)
            except OSError as e:
                raise NodeRPCTransportError(f"cannot read RPC cookie {self._cookie_file}: {e}")
        return aiohttp.BasicAuth(self._user, self._password)

    # ------------------------------------------------------------------ json-rpc call
    async def _call(self, method: str, params: list | None = None):
        payload = {"jsonrpc": "1.0", "id": "bp", "method": method, "params": params or []}
        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._url, json=payload, auth=self._auth()) as resp:
                    # The node returns 500 with a JSON-RPC error body for rejected txs;
                    # only treat non-JSON / auth failures as transport errors.
                    if resp.status in (401, 403):
                        raise NodeRPCTransportError(f"RPC auth failed (HTTP {resp.status})")
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as e:
                        raise NodeRPCTransportError(f"non-JSON RPC response (HTTP {resp.status}): {e}")
        except aiohttp.ClientError as e:
            raise NodeRPCTransportError(f"RPC transport error: {e}")
        if data.get("error"):
            err = data["error"]
            raise NodeRPCError(int(err.get("code", -1)), str(err.get("message", err)))
        return data.get("result")

    # ------------------------------------------------------------------ methods
    async def getblockchaininfo(self) -> dict:
        return await self._call("getblockchaininfo")

    async def getblockcount(self) -> int:
        return int(await self._call("getblockcount"))

    async def sendrawtransaction(self, raw_hex: str) -> str:
        """Broadcast a raw tx; returns the txid. Raises NodeRPCError on rejection."""
        return await self._call("sendrawtransaction", [raw_hex])

    async def getrawtransaction(self, txid: str, verbose: bool = True) -> dict:
        """Verbose tx info (needs txindex=1 for non-mempool/unspent txs)."""
        return await self._call("getrawtransaction", [txid, verbose])

    async def getblockheader(self, blockhash: str) -> dict:
        return await self._call("getblockheader", [blockhash])

    async def health(self) -> dict | None:
        """Return getblockchaininfo if reachable, else None (never raises)."""
        try:
            return await self.getblockchaininfo()
        except Exception as e:
            log.debug("Node RPC health check failed: %s", e)
            return None
