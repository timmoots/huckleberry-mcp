"""FastMCP server entry point for Huckleberry.

Two transports, selected by MCP_TRANSPORT:
    - stdio             — local dev (default)
    - streamable-http   — production (remote Claude clients)

In streamable-http mode we enable FastMCP's native OAuth 2.1 Authorization
Server (with DCR) and gate /mcp on a valid bearer. The user completes the
consent form once per week.
"""

from __future__ import annotations

import os
import sys

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from huckleberry_mcp.auth import is_authenticated
from huckleberry_mcp.resources.daily_summary import register_daily_summary
from huckleberry_mcp.tools.children import register_children_tools
from huckleberry_mcp.tools.diaper import register_diaper_tools
from huckleberry_mcp.tools.feeding import register_feeding_tools
from huckleberry_mcp.tools.growth import register_growth_tools
from huckleberry_mcp.tools.pumping import register_pumping_tools
from huckleberry_mcp.tools.sleep import register_sleep_tools

VERSION = os.getenv("HUCKLEBERRY_MCP_VERSION", "dev")


def _build_mcp() -> FastMCP:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    auth = None
    if transport == "streamable-http":
        # Import only when needed so stdio dev doesn't require OAUTH_ADMIN_PASSWORD
        from huckleberry_mcp.oauth import HuckleberryOAuthProvider

        base_url = os.getenv("OAUTH_ISSUER") or os.getenv("FLY_APP_URL", "http://localhost:8080")
        auth = HuckleberryOAuthProvider(base_url=base_url)

    mcp = FastMCP("huckleberry-mcp", auth=auth)

    register_children_tools(mcp)
    register_sleep_tools(mcp)
    register_feeding_tools(mcp)
    register_diaper_tools(mcp)
    register_growth_tools(mcp)
    register_pumping_tools(mcp)
    register_daily_summary(mcp)

    _register_health(mcp)
    if transport == "streamable-http":
        _register_consent(mcp, auth)

    return mcp


def _register_health(mcp: FastMCP) -> None:
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        body = {
            "status": "ok",
            "firebase_auth": "authenticated" if is_authenticated() else "not_yet",
            "version": VERSION,
            "transport": os.getenv("MCP_TRANSPORT", "stdio"),
        }
        return JSONResponse(body)


def _register_consent(mcp: FastMCP, provider) -> None:
    from huckleberry_mcp.oauth import build_consent_routes

    get_consent, post_consent = build_consent_routes(provider)
    mcp.custom_route("/consent", methods=["GET"])(get_consent)
    mcp.custom_route("/consent", methods=["POST"])(post_consent)


def run() -> None:
    mcp = _build_mcp()
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    print(
        f"Huckleberry MCP starting (transport={transport}, version={VERSION})",
        file=sys.stderr,
    )
    if transport == "streamable-http":
        port = int(os.getenv("PORT", "8080"))
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    run()
