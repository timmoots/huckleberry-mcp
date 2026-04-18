# huckleberry-mcp

Remote MCP server that lets Claude (mobile, web, desktop) log to the
**Huckleberry** baby tracking app in natural language.

> "log a wet diaper" → diaper appears in the Huckleberry app ~2 seconds later.

This is a hardened fork of [`bckenstler/py-huckleberry-mcp`](https://github.com/bckenstler/py-huckleberry-mcp),
rewritten against the real `py-huckleberry-api` v0.4.x surface and extended with
a native OAuth 2.1 Authorization Server so Claude mobile can connect without an
external identity provider.

> **Disclaimer:** unofficial. Not sponsored, endorsed, or supported by
> Huckleberry. Uses a reverse-engineered API client that talks to the same
> Firebase backend as the mobile app.

---

## Why this exists

New parents log dozens of events per day — diapers, feeds, sleep, pumping.
Each entry in a mobile app is unlock → open → navigate → tap → tap → tap.
At 2am with a crying infant on your shoulder, that friction compounds.

This MCP turns any of those into a sentence in Claude:

| Prompt                              | Tool                 |
|-------------------------------------|----------------------|
| "log a wet diaper"                  | `log_diaper`         |
| "she just fell asleep"              | `start_sleep`        |
| "she's awake"                       | `complete_sleep`     |
| "log 30ml of breast milk at 1:45a"  | `log_bottle_feeding` |
| "log 3oz pump, left side, 15 min"   | `log_pumping`        |
| "how many diapers today?"           | `huckleberry://today/{uid}` resource |

---

## Architecture

```
┌─────────────────┐   OAuth 2.1 DCR + Bearer    ┌─────────────────┐
│ Claude mobile / │ ──────────────────────────► │ Fly.io VM       │
│ web / desktop   │                             │ FastMCP + OAuth │
│ (Connectors)    │ ◄────────────────────────── │ streamable-http │
└─────────────────┘                             └────────┬────────┘
                                                         │ async gRPC
                                                         ▼
                                                ┌─────────────────┐
                                                │ Huckleberry     │
                                                │ Firebase        │
                                                └─────────────────┘
```

- **Transport:** `streamable-http` in production, `stdio` for local dev —
  switched by `MCP_TRANSPORT`.
- **Auth:** FastMCP's native OAuth 2.1 Authorization Server with Dynamic
  Client Registration. Claude.ai handles the OAuth dance; you enter an admin
  password once every 30 days on a minimal consent form served by the MCP itself.
  No Cloudflare Access, no WorkOS, no Clerk.
- **API:** `huckleberry-api>=0.4.0,<0.5.0` — fully async, uses the official
  Google Cloud Firestore gRPC SDK (not a reverse-engineered REST shim).
- **Host:** Fly.io, single persistent VM (`min_machines_running = 1`) — no
  cold starts, so 2am messages feel instant.

---

## Setup

### Prerequisites

- Python 3.14 (or run in the Docker image)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Fly.io account + `flyctl`
- A Huckleberry account with email/password login (not SSO-only)
- A claude.ai Pro or Max account (required for mobile MCP Connectors)

### Local dev (stdio)

```bash
git clone https://github.com/<you>/huckleberry-mcp.git
cd huckleberry-mcp
cp .env.example .env
# Fill in HUCKLEBERRY_EMAIL and HUCKLEBERRY_PASSWORD in .env
uv sync
uv run huckleberry-mcp
```

Use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to
poke at it:

```bash
npx @modelcontextprotocol/inspector uv run huckleberry-mcp
```

Run `list_children` to grab your child UID, then set
`HUCKLEBERRY_DEFAULT_CHILD_UID` in `.env` so every subsequent call can omit it.

### Deploy (Fly.io)

```bash
flyctl launch --no-deploy       # accept the detected Dockerfile + fly.toml

flyctl secrets set \
  HUCKLEBERRY_EMAIL=you@example.com \
  HUCKLEBERRY_PASSWORD=... \
  HUCKLEBERRY_DEFAULT_CHILD_UID=<child-uid-from-list-children> \
  OAUTH_ADMIN_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  OAUTH_ISSUER=https://huckleberry-mcp.fly.dev

flyctl deploy
curl https://huckleberry-mcp.fly.dev/health
```

### Register with claude.ai

1. claude.ai → Settings → Connectors → Add custom connector.
2. URL: `https://huckleberry-mcp.fly.dev/mcp`
3. Claude kicks off DCR + the OAuth authorization flow.
4. You're redirected to `/consent` and enter `OAUTH_ADMIN_PASSWORD`.
5. Connector syncs to Claude mobile/desktop automatically.

Re-consent is required every 30 days. OAuth state is persisted to a Fly volume, so deploys and machine restarts don't invalidate the session.

---

## Tool inventory

**Children** — `list_children`, `get_child_name`
**Diaper** — `log_diaper`, `get_diaper_history`
**Sleep** — `log_sleep`, `start_sleep`, `pause_sleep`, `resume_sleep`, `complete_sleep`, `cancel_sleep`, `get_sleep_history`
**Feeding** — `log_bottle_feeding`, `log_breastfeeding`, `start_breastfeeding`, `pause_feeding`, `resume_feeding`, `switch_feeding_side`, `complete_feeding`, `cancel_feeding`, `get_feeding_history`
**Pumping** — `log_pumping`, `get_pumping_history`
**Growth** — `log_growth`, `get_latest_growth`, `get_growth_history`
**Resources** — `huckleberry://today/{child_uid}` (diaper / sleep / feed / pump totals)

Every tool except `list_children` accepts `child_uid` as optional — falls back
to `HUCKLEBERRY_DEFAULT_CHILD_UID` so one-shot prompts don't pay a round trip.

**Timezone contract:** naive datetimes are interpreted in
`America/New_York` (EST/EDT). Override with `HUCKLEBERRY_TIMEZONE`.

---

## Security

See [`SECURITY.md`](./SECURITY.md) for the trust model, dependency chain, and
risk matrix.

TL;DR: a VM compromise leaks bearer tokens valid for ≤1 hour. Your Huckleberry
password lives only in Fly secrets. The consent form is rate-limited and uses
constant-time comparison. The reverse-engineered API uses the official Google
Firestore SDK, not a custom REST shim — same traffic path as the Huckleberry
mobile app itself.

---

## Design choices

See [`DECISION_LOG.md`](./DECISION_LOG.md) for the build-vs-fork, transport,
auth, and hosting decisions with tradeoffs.

---

## License

MIT — same as upstream.
