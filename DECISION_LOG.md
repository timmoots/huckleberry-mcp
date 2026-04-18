# Decision Log

Four load-bearing choices shape this repo. Each includes the options considered
and why the alternatives were rejected.

## 1. Build vs. fork vs. rewrite

**Chose: fork `bckenstler/py-huckleberry-mcp` and rewrite the tool layer.**

- `bckenstler/py-huckleberry-mcp` provided a useful scaffold (FastMCP wiring,
  separate modules per category), but its tool implementations called API
  methods that **do not exist in any published `py-huckleberry-api` release**
  (`start_feeding`, `get_children`, `get_feed_intervals`, etc.). The real
  library uses `start_nursing`, `get_user`, `list_feed_intervals`. Upstream
  tests mocked the missing methods so CI was green despite the production
  code being dead.
- Keeping the fork scaffold was still worthwhile: MCP registration pattern,
  module split, env-var flow were all reusable.
- The tool layer (diaper, sleep, feeding, growth) was rewritten from scratch
  against the real async API surface. `pumping` was added net-new.

## 2. Transport

**Chose: dual transport — `stdio` for local dev, `streamable-http` for production.**

- Claude mobile **requires** a remote HTTPS MCP with OAuth 2.1. stdio alone
  cannot reach mobile.
- Stripping stdio would make local development annoying (no hot loop without
  deploys). Dual gated by `MCP_TRANSPORT` env var keeps both cheap.

## 3. Authentication for remote access

**Chose: FastMCP's native OAuth 2.1 Authorization Server with DCR.**

Options considered:

- **Cloudflare Access.** Issues cookie/JWT after browser SSO login. Doesn't
  fit Claude's server-to-server MCP request path, which expects OAuth 2.1 +
  DCR bearer tokens on every call.
- **External IdP (WorkOS / Clerk / Stytch / Auth0).** Real OAuth 2.1 + DCR
  support. Adds an external service to configure, maintain, and pay for.
- **Static bearer token.** Rejected — claude.ai connectors run the full
  OAuth flow and don't accept a pre-shared bearer for user-added servers.
- **FastMCP native OAuth AS (this repo).** Single codebase. No third-party
  identity provider. Subclasses FastMCP's `InMemoryOAuthProvider`, overrides
  `authorize` to redirect through a minimal consent form, issues
  1-hour access / 30-day refresh tokens.

Consent form is the one UI in the whole system — one password input, 30 lines
of HTML served by the same FastMCP app. Admin password compared with
`secrets.compare_digest`, posts rate-limited 10/min/IP.

## 4. Host

**Chose: Fly.io (single VM, `min_machines_running = 1`).**

| Option                    | Why not                                                                 |
|---------------------------|-------------------------------------------------------------------------|
| Railway                   | Fine alternative; slightly worse free tier for always-on workloads     |
| Render (free)             | Sleeps after 15 min idle — cold start at 2am kills the UX               |
| Cloudflare Workers        | No Python async + persistent-session story; FastMCP model doesn't fit   |
| Self-host + Cloudflare Tunnel | Fragile if the host Mac sleeps; bad portfolio demo story             |

Fly gives: persistent stateful process, first-class secrets, HTTPS automatic,
free for this scale, Docker-native deploys.

---

## Non-decisions worth calling out

- **Integration tests.** Deferred. Requires a throwaway Huckleberry account
  and real Firestore calls. Upstream tests were unit-level mocks that
  exercised phantom API methods — removed as misleading.
- **Multi-user.** Out of scope. Everything assumes one operator. Partner
  access would mean a per-user consent form, a real token DB, and token
  revocation UI.
- **Scheduled daily digest.** The `huckleberry://today/{uid}` resource does
  the aggregation; the *scheduling* is a separate concern (Fly cron, Claude
  scheduled agent, or a shortcut).
