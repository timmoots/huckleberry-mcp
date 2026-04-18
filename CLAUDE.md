# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Remote MCP server that lets Claude (mobile/web/desktop) log events to the Huckleberry baby tracking app. Deployed at `https://huckleberry-mcp.fly.dev`. Upstream fork of `bckenstler/py-huckleberry-mcp`, rewritten against the real `huckleberry-api` v0.4.x and extended with a native OAuth 2.1 Authorization Server so Claude mobile can connect.

## Commands

```bash
uv sync                                          # install deps (Python 3.14 required)
uv sync --extra dev                              # include ruff, pytest
uv run huckleberry-mcp                           # run stdio (local dev, Claude Desktop)
MCP_TRANSPORT=streamable-http uv run huckleberry-mcp   # run remote HTTP server
uv run ruff check src                            # lint

fly deploy --app huckleberry-mcp --remote-only   # deploy (fly builds image remotely)
fly ssh console --app huckleberry-mcp            # shell into the VM
fly logs --app huckleberry-mcp                   # tail production logs
fly secrets list --app huckleberry-mcp           # list (names only — values encrypted)
curl https://huckleberry-mcp.fly.dev/health      # production smoke
```

There are no tests — the upstream unit tests mocked phantom API methods and were removed. Integration testing requires a real Huckleberry account and is done by hand.

## Architecture

Two transports, selected by `MCP_TRANSPORT`:
- **stdio** — local dev. No OAuth. Auth via `.env`. Firebase session lazy-initialized on first tool call.
- **streamable-http** — production. OAuth-gated. Same tool layer. Firebase session still lazy.

The toggle happens in `server.py::_build_mcp()`. In HTTP mode it constructs a `HuckleberryOAuthProvider` (subclass of FastMCP's `InMemoryOAuthProvider`) and wires a `/consent` HTML form via `mcp.custom_route`. OAuth state (clients, auth codes, access + refresh tokens) is pickled to `/data/oauth_state.pkl` on a mounted Fly volume after every mutation — **do not skip these `_save_state()` calls** when adding new token-issuing paths, or deploys will silently orphan clients.

Firebase session (`auth.py`) is a module-scoped `HuckleberryAPI` + `aiohttp.ClientSession` singleton. `get_api()` calls `ensure_session()` every request, which refreshes the Firebase ID token internally on expiry. A full re-auth (`_load_credentials` → `authenticate`) only happens after a machine restart.

## Tool layer

Every tool in `src/huckleberry_mcp/tools/*.py`:
- Accepts `child_uid: Optional[str] = None` — resolves to `HUCKLEBERRY_DEFAULT_CHILD_UID` via `utils.resolve_child_uid`.
- Parses datetimes through `utils.parse_dt` — naive strings are interpreted as `America/New_York` (override with `HUCKLEBERRY_TIMEZONE`). Never hand a raw ISO string to the API; route through `parse_dt` so timezone contract holds.
- Required post-`child_uid` params are keyword-only (signature uses `*,`) — Python won't accept a required arg after a default-valued one otherwise.

History tools (`get_*_history`) **must sort intervals descending by `.start`** before returning. The upstream `list_*_intervals` returns ascending, and any LLM consuming the result treats index 0 as "most recent." Ambient rule: most-recent-first for anything an LLM reads.

## Known gotchas

- **`huckleberry-api` method names.** v0.4.x uses `start_nursing`, `log_bottle`, `list_feed_intervals`, `get_user`, `get_latest_growth`. Do not trust upstream MCP's `start_feeding` / `get_children` / `get_feed_intervals` naming — those are phantom methods; the original fork's tests mocked them.
- **All API methods are async and require `websession: aiohttp.ClientSession`** in the constructor. Every tool in this tree must `await get_api()`.
- **Data type of `start` on interval models:** Unix seconds (`int | float`), not milliseconds. `utils.to_local_iso` handles both `datetime` and numeric input.
- **Fly deploys default to 2 machines for HA.** We force single-machine via `fly scale count 1`. Multi-machine with in-memory OAuth state breaks the OAuth flow (DCR on machine A, authorize on machine B, "client not found"). The `/data` volume mounts to one machine only — if ever scaling up, persistence would need a shared store.
- **Rate limit on `/consent` uses `Fly-Client-IP`, not `request.client.host`** (which is the edge IP behind the Fly proxy, i.e. identical for every real client).
- **The `HUCKLEBERRY_MCP_VERSION` env var** is not set in production; `/health` reports `"dev"`. If adding release tagging, set it in the Docker build.

## Deploy + consent flow

The user types a consent password once every 30 days on `/consent`. Access tokens last 1 hour, refreshed silently. A fresh `fly deploy` does not force re-consent (OAuth state survives via the volume). Deleting the connector in claude.ai and re-adding it is only necessary if the volume gets corrupted or a new client_id is needed.

## Secrets

Set via `fly secrets set --app huckleberry-mcp`:
- `HUCKLEBERRY_EMAIL` / `HUCKLEBERRY_PASSWORD` — the user's Huckleberry account creds
- `HUCKLEBERRY_DEFAULT_CHILD_UID` — default child for any omitted `child_uid` tool arg
- `OAUTH_ADMIN_PASSWORD` — what the user types on `/consent`
- `OAUTH_ISSUER` — full public URL (e.g. `https://huckleberry-mcp.fly.dev`); used as the OAuth `iss` claim

`HUCKLEBERRY_TIMEZONE`, `MCP_TRANSPORT`, `PORT`, `OAUTH_STATE_PATH` live in `fly.toml [env]` — non-secret, committed.

## Key files

- `src/huckleberry_mcp/server.py` — FastMCP wiring, transport switch, `/health`, consent route registration
- `src/huckleberry_mcp/oauth.py` — OAuth 2.1 AS + consent form + state persistence
- `src/huckleberry_mcp/auth.py` — Huckleberry singleton
- `src/huckleberry_mcp/utils.py` — `resolve_child_uid`, `parse_dt`, `to_local_iso`, `today_range`
- `src/huckleberry_mcp/tools/*.py` — one module per Huckleberry domain
- `src/huckleberry_mcp/resources/daily_summary.py` — `huckleberry://today/{uid}` aggregator
- `SECURITY.md`, `DECISION_LOG.md` — trust model + decision rationale; keep in sync with code
