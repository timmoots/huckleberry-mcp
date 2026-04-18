# huckleberry-mcp

**A way to tell Claude about your baby's bodily functions so you don't have to poke at a glowing phone at 3 AM.**

New parents know the ritual: small human emits substance → fumble for phone → unlock → open app → navigate → tap wet/dirty/both → tap color → tap consistency → tap save → back to sleep. Dozens of times a day. Your thumbs develop their own sleep debt.

This MCP lets you skip all that. Type (or mumble) "log a wet diaper" to Claude on your phone, and it quietly writes to Huckleberry. Two seconds. Back to the crib.

---

## The ask → the thing

| What you say to Claude         | What actually happens                                      |
|--------------------------------|------------------------------------------------------------|
| "log a wet diaper"             | `log_diaper(mode="pee")` → Firestore → the app updates     |
| "she just fell asleep"         | `start_sleep()` timer                                      |
| "she's awake"                  | `complete_sleep()`                                         |
| "log 30ml bottle at 1:45a"     | `log_bottle_feeding(amount=30, units="ml", timestamp=...)` |
| "3oz pump, left side, 15 min"  | `log_pumping(left_amount=3, units="oz", duration=15)`      |
| "how many diapers today?"      | reads `huckleberry://today/{uid}` → "6 diapers today..."   |

No navigation. No taps. Just vibes and first-person narration of your infant's life.

---

## Why this exists (or: forks all the way down)

Huckleberry has no public API. They do have a reverse-engineered Python client ([`Woyken/py-huckleberry-api`](https://github.com/Woyken/py-huckleberry-api)) that talks to the same Firebase gRPC backend the mobile app uses. There was also a community MCP server ([`bckenstler/py-huckleberry-mcp`](https://github.com/bckenstler/py-huckleberry-mcp)) wrapping that client.

I forked the MCP, discovered the upstream tools were written against API methods that didn't exist in any published version of the underlying client (the unit tests mocked phantom methods; the production code would have failed on first call), rewrote the entire tool layer against the real async API, and then added the thing the fork was actually missing: a way for **Claude mobile** to reach it.

That last bit required adding a remote transport (streamable-http), an OAuth 2.1 Authorization Server with Dynamic Client Registration, a consent page, token persistence to a Fly volume, and a Dockerfile to deploy it all. For logging diapers. I'm aware of the ratio.

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
                                                │ Huckleberry's   │
                                                │ Firebase        │
                                                └─────────────────┘
```

- **Transport:** `streamable-http` in production, `stdio` for local dev — toggled by env var.
- **Auth:** FastMCP's native OAuth 2.1 + DCR. Claude.ai does the dance; you type one consent password once every 30 days on a 30-line HTML form served by the MCP itself. No Cloudflare Access, no WorkOS, no Clerk.
- **API:** `huckleberry-api>=0.4.0,<0.5.0` — official Google Cloud Firestore gRPC SDK, same path as the mobile app.
- **Host:** Fly.io. Single persistent VM. OAuth state on a mounted volume, so deploys don't evict you.

---

## Tools (tour)

- **Children** — `list_children`, `get_child_name`
- **Diaper** — `log_diaper`, `get_diaper_history`
- **Sleep** — `log_sleep`, `start_sleep`, `pause_sleep`, `resume_sleep`, `complete_sleep`, `cancel_sleep`, `get_sleep_history`
- **Feeding** — `log_bottle_feeding`, `log_breastfeeding`, `start_breastfeeding`, `pause_feeding`, `resume_feeding`, `switch_feeding_side`, `complete_feeding`, `cancel_feeding`, `get_feeding_history`
- **Pumping** — `log_pumping`, `get_pumping_history`
- **Growth** — `log_growth`, `get_latest_growth`, `get_growth_history`
- **Resource** — `huckleberry://today/{child_uid}` — today's tally, so "how many diapers today?" doesn't burn a tool call

Every tool except `list_children` takes `child_uid` as optional, falling back to `HUCKLEBERRY_DEFAULT_CHILD_UID`. One-shot prompts don't pay a round trip.

**Timezone contract:** naive datetimes are interpreted as `America/New_York` (EST/EDT). Override with `HUCKLEBERRY_TIMEZONE`. Yes, I opinionated the timezone. No, "3am" does not mean the same thing in every timezone and I refuse to pretend otherwise.

---

## Setup

You need:
- Python 3.14 (or the Docker image)
- [`uv`](https://docs.astral.sh/uv/)
- A Fly.io account + `flyctl`
- A Huckleberry account with email/password login (not SSO-only)
- A claude.ai **Pro or Max** subscription (mobile MCP Connectors are paid-plan territory)

### Local dev (stdio)

```bash
git clone https://github.com/<you>/huckleberry-mcp.git
cd huckleberry-mcp
cp .env.example .env    # fill in HUCKLEBERRY_EMAIL, HUCKLEBERRY_PASSWORD
uv sync
uv run huckleberry-mcp
```

Use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to poke at it:

```bash
npx @modelcontextprotocol/inspector uv run huckleberry-mcp
```

### Deploy (Fly.io)

```bash
flyctl launch --no-deploy
flyctl volumes create huckleberry_data --size 1 --region iad

flyctl secrets set \
  HUCKLEBERRY_EMAIL=you@example.com \
  HUCKLEBERRY_PASSWORD=... \
  HUCKLEBERRY_DEFAULT_CHILD_UID=<uid> \
  OAUTH_ADMIN_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  OAUTH_ISSUER=https://<your-app>.fly.dev

flyctl deploy
curl https://<your-app>.fly.dev/health
```

### Register with claude.ai

1. claude.ai → Settings → Connectors → Add custom connector.
2. URL: `https://<your-app>.fly.dev/mcp`
3. Claude runs OAuth, redirects you to a consent form.
4. Enter `OAUTH_ADMIN_PASSWORD`. Save it in your password manager. You'll see it again in 30 days.

---

## Security, briefly

Full trust model in [`SECURITY.md`](./SECURITY.md). Short version:

- Your Huckleberry credentials live only in Fly secrets. Never in git.
- The consent password is compared in constant time, rate-limited per real client IP.
- Access tokens are 1 hour; refresh tokens are 30 days.
- VM compromise leaks at most 1 hour of bearer validity.
- The reverse-engineered API uses the official Firestore SDK, not a custom REST shim — same traffic path as the Huckleberry mobile app itself. Huckleberry's ToS probably doesn't love this, but it doesn't love the mobile app's network traffic either, because it's the same.

---

## Credits

- Forked from [`bckenstler/py-huckleberry-mcp`](https://github.com/bckenstler/py-huckleberry-mcp) — thanks Brad for the scaffold.
- API client: [`Woyken/py-huckleberry-api`](https://github.com/Woyken/py-huckleberry-api) — thanks Woyken for reverse-engineering so the rest of us don't have to.
- Framework: [FastMCP](https://github.com/jlowin/fastmcp).

Built one weekend by a sleep-deprived parent who wanted one less reason to look at a screen at 3 AM.

## License

MIT.
