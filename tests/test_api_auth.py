"""The dashboard exposes raw hex + broadcast actions, so /api/ must require a
Bearer token when one is configured (BP_AUTH_TOKEN, or Umbrel's app_proxy in
front). Root/static stay public so app_proxy can serve them.
"""
import asyncio

import pytest

from src.web import api


class _Req:
    def __init__(self, path, auth=None):
        self.path = path
        self.headers = {"Authorization": auth} if auth is not None else {}


async def _handler(_req):
    return "HANDLED"


def _run(path, auth, token):
    api.AUTH_TOKEN = token
    return asyncio.run(api.auth_middleware(_Req(path, auth), _handler))


def test_api_rejects_without_token():
    resp = _run("/api/status", None, "s3cr3t")
    assert resp.status == 401


def test_api_rejects_wrong_token():
    resp = _run("/api/status", "Bearer wrong", "s3cr3t")
    assert resp.status == 401


def test_api_allows_correct_token():
    assert _run("/api/status", "Bearer s3cr3t", "s3cr3t") == "HANDLED"


def test_root_is_public():
    # Static/root served by app_proxy — never gated by the token.
    assert _run("/", None, "s3cr3t") == "HANDLED"


def test_no_token_configured_is_open():
    # When no token is set, the middleware passes everything (Umbrel app_proxy
    # is the gate in that deployment).
    assert _run("/api/status", None, "") == "HANDLED"
