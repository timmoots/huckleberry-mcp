"""OAuth 2.1 Authorization Server for the Huckleberry MCP.

Single-user design. Claude.ai completes Dynamic Client Registration (DCR), then
redirects the user's browser to /consent, where the user enters a single
admin password (OAUTH_ADMIN_PASSWORD env var). On success we issue a 1-hour
access token and a 7-day refresh token. Restarts wipe state — the user
re-consents once per week in the normal flow, and after any deploy.

Security notes:
- Token stores are in-memory. A VM compromise exposes tokens valid for ≤1 hour.
- The consent form is rate-limited per-IP to resist online brute force.
- The admin password is compared with `secrets.compare_digest` — no timing leak.
- Auth codes are PKCE-bound; Claude sends `code_challenge`/`code_verifier`.
"""

from __future__ import annotations

import collections
import os
import secrets
import time
from html import escape

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from fastmcp.server.auth.auth import ClientRegistrationOptions
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider

ACCESS_TOKEN_TTL_SECONDS = 60 * 60              # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60    # 7 days — matches user's weekly sign-in max
CONSENT_SESSION_TTL_SECONDS = 5 * 60            # 5 minutes to complete the consent flow
AUTH_CODE_TTL_SECONDS = 5 * 60                  # 5 minutes
CONSENT_RATE_LIMIT_WINDOW = 60                  # seconds
CONSENT_RATE_LIMIT_MAX = 10                     # POSTs per IP per window


class HuckleberryOAuthProvider(InMemoryOAuthProvider):
    """OAuth AS with a human-gated consent form.

    Overrides `authorize` to park the request and redirect to /consent
    instead of auto-issuing codes like the parent in-memory provider does.
    """

    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self.pending_consent: dict[
            str, tuple[OAuthClientInformationFull, AuthorizationParams, float]
        ] = {}
        self._post_hits: dict[str, collections.deque[float]] = collections.defaultdict(
            collections.deque
        )
        admin_password = os.getenv("OAUTH_ADMIN_PASSWORD")
        if not admin_password:
            raise RuntimeError(
                "OAUTH_ADMIN_PASSWORD must be set for remote transport"
            )
        self._admin_password = admin_password

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        expires_at = time.time() + CONSENT_SESSION_TTL_SECONDS
        self.pending_consent[session_id] = (client, params, expires_at)
        return f"/consent?session={session_id}"

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise TokenError(
                "invalid_grant", "Authorization code not found or already used."
            )
        del self.auth_codes[authorization_code.code]

        access_token_value = f"hb_at_{secrets.token_urlsafe(32)}"
        refresh_token_value = f"hb_rt_{secrets.token_urlsafe(32)}"

        self.access_tokens[access_token_value] = AccessToken(
            token=access_token_value,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
        )
        self.refresh_tokens[refresh_token_value] = RefreshToken(
            token=refresh_token_value,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time() + REFRESH_TOKEN_TTL_SECONDS),
        )
        self._access_to_refresh_map[access_token_value] = refresh_token_value
        self._refresh_to_access_map[refresh_token_value] = access_token_value

        return OAuthToken(
            access_token=access_token_value,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=refresh_token_value,
            scope=" ".join(authorization_code.scopes),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        original_scopes = set(refresh_token.scopes)
        if not set(scopes).issubset(original_scopes):
            raise TokenError(
                "invalid_scope",
                "Requested scopes exceed those authorized by the refresh token.",
            )
        self._revoke_internal(refresh_token_str=refresh_token.token)

        new_access = f"hb_at_{secrets.token_urlsafe(32)}"
        new_refresh = f"hb_rt_{secrets.token_urlsafe(32)}"

        self.access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
        )
        self.refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(time.time() + REFRESH_TOKEN_TTL_SECONDS),
        )
        self._access_to_refresh_map[new_access] = new_refresh
        self._refresh_to_access_map[new_refresh] = new_access

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=new_refresh,
            scope=" ".join(scopes),
        )

    def _rate_limit(self, ip: str) -> bool:
        now = time.time()
        window_start = now - CONSENT_RATE_LIMIT_WINDOW
        hits = self._post_hits[ip]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= CONSENT_RATE_LIMIT_MAX:
            return False
        hits.append(now)
        return True

    def _issue_code(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        auth_code_value = f"hb_code_{secrets.token_urlsafe(32)}"
        scopes_list = params.scopes if params.scopes is not None else []
        if client.scope:
            client_allowed = set(client.scope.split())
            scopes_list = [s for s in scopes_list if s in client_allowed]

        self.auth_codes[auth_code_value] = AuthorizationCode(
            code=auth_code_value,
            client_id=client.client_id,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=scopes_list,
            expires_at=time.time() + AUTH_CODE_TTL_SECONDS,
            code_challenge=params.code_challenge,
        )
        return construct_redirect_uri(
            str(params.redirect_uri),
            code=auth_code_value,
            state=params.state,
        )


def _consent_page(session_id: str, error: str | None = None) -> str:
    err_html = (
        f'<p class="err">{escape(error)}</p>' if error else ""
    )
    return f"""<!doctype html>
<html><head><title>Huckleberry MCP — Authorize</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 420px;
       margin: 10vh auto; padding: 2rem; color: #222; }}
h1 {{ font-size: 1.3rem; margin: 0 0 0.5rem 0; }}
p {{ color: #555; line-height: 1.5; }}
.err {{ color: #b00020; background: #fdecea; padding: 0.6rem 0.8rem;
        border-radius: 6px; }}
input[type=password] {{ width: 100%; padding: 0.7rem; font-size: 1rem;
                        border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }}
button {{ width: 100%; padding: 0.8rem; font-size: 1rem; background: #1e6fff;
         color: white; border: 0; border-radius: 6px; margin-top: 0.8rem; cursor: pointer; }}
button:hover {{ background: #1558cc; }}
</style></head>
<body>
<h1>Authorize Claude to log events</h1>
<p>Enter your admin password to allow this Claude client to write to your Huckleberry account for the next 7 days.</p>
{err_html}
<form method="post" action="/consent">
  <input type="hidden" name="session" value="{escape(session_id)}">
  <input type="password" name="password" autofocus autocomplete="current-password" required>
  <button type="submit">Authorize</button>
</form>
</body></html>"""


def build_consent_routes(provider: HuckleberryOAuthProvider):
    """Return Starlette route handlers for /consent GET and POST.

    Usage:
        mcp.custom_route("/consent", methods=["GET"])(get_consent)
        mcp.custom_route("/consent", methods=["POST"])(post_consent)
    """

    async def get_consent(request: Request):
        session_id = request.query_params.get("session", "")
        if not session_id or session_id not in provider.pending_consent:
            return HTMLResponse(
                "<h1>Session not found or expired</h1>"
                "<p>Return to Claude and restart the authorization flow.</p>",
                status_code=400,
            )
        return HTMLResponse(_consent_page(session_id))

    async def post_consent(request: Request):
        # Behind a reverse proxy (Fly.io), request.client.host is the edge IP
        # — same for every real client — so rate-limiting on it is effectively
        # global. Prefer Fly-Client-IP, fall back to X-Forwarded-For's leftmost
        # entry, fall back to the socket peer only for direct local dev.
        client_ip = (
            request.headers.get("fly-client-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        if not provider._rate_limit(client_ip):
            return HTMLResponse(
                "<h1>Too many attempts</h1><p>Wait a minute and try again.</p>",
                status_code=429,
            )

        form = await request.form()
        session_id = str(form.get("session", ""))
        password = str(form.get("password", ""))

        pending = provider.pending_consent.pop(session_id, None)
        if pending is None:
            return HTMLResponse(_consent_page(session_id, error="Session expired."), status_code=400)

        client, params, expires_at = pending
        if time.time() > expires_at:
            return HTMLResponse(_consent_page(session_id, error="Session expired."), status_code=400)

        if not secrets.compare_digest(password, provider._admin_password):
            # Put the pending session back so the user can retry without re-initiating
            provider.pending_consent[session_id] = (client, params, expires_at)
            return HTMLResponse(_consent_page(session_id, error="Incorrect password."), status_code=401)

        redirect = provider._issue_code(client, params)
        return RedirectResponse(redirect, status_code=302)

    return get_consent, post_consent
