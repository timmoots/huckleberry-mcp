"""Authentication handler for Huckleberry API (v0.4.x).

The underlying `py-huckleberry-api` is fully async and requires an
`aiohttp.ClientSession`. We hold both as module-scoped singletons so
Firebase session state persists across tool calls. Token refresh is
handled by `api.ensure_session()` which we call before every operation.
"""

import asyncio
import os
import sys
from typing import Optional

import aiohttp
from huckleberry_api import HuckleberryAPI


class HuckleberryAuthError(Exception):
    """Raised when authentication fails."""


_session: Optional[aiohttp.ClientSession] = None
_api: Optional[HuckleberryAPI] = None
_lock = asyncio.Lock()


def _load_credentials() -> tuple[str, str, str]:
    email = os.getenv("HUCKLEBERRY_EMAIL")
    password = os.getenv("HUCKLEBERRY_PASSWORD")
    timezone_name = os.getenv("HUCKLEBERRY_TIMEZONE", "America/New_York")
    if not email or not password:
        raise HuckleberryAuthError(
            "Missing credentials. Set HUCKLEBERRY_EMAIL and HUCKLEBERRY_PASSWORD."
        )
    return email, password, timezone_name


async def get_api() -> HuckleberryAPI:
    """Return an authenticated, session-refreshed HuckleberryAPI client."""
    global _session, _api
    async with _lock:
        if _api is None:
            email, password, tz = _load_credentials()
            _session = aiohttp.ClientSession()
            _api = HuckleberryAPI(
                email=email,
                password=password,
                timezone=tz,
                websession=_session,
            )
            try:
                await _api.authenticate()
            except Exception as e:
                await _close_session()
                _api = None
                raise HuckleberryAuthError(f"Failed to authenticate: {e}") from e
            print("Authenticated with Huckleberry API", file=sys.stderr)
        else:
            try:
                await _api.ensure_session()
            except Exception:
                # token unrecoverable — force full re-auth on next call
                await reset()
                return await get_api()
    return _api


async def _close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def reset() -> None:
    """Drop cached client + session. Next call re-auths from env vars."""
    global _api
    await _close_session()
    _api = None


def is_authenticated() -> bool:
    return _api is not None
