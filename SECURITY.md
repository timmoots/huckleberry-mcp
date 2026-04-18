# Security Model

This server is single-user by design. The threat model assumes one operator
(the parent) and public access to the Fly.io URL.

## Authentication boundaries

1. **Claude.ai ↔ MCP server.** OAuth 2.1 with Dynamic Client Registration
   and PKCE. FastMCP's built-in Authorization Server issues 1-hour access
   tokens and 30-day refresh tokens after the operator enters a consent
   password.
2. **Origin (`/mcp`).** Every request is validated against the OAuth
   token store, which is pickled to a mounted Fly volume after every
   mutation. Restarts survive without the operator re-consenting.
3. **Huckleberry (Firebase).** Email/password → Firebase ID token, refreshed
   internally by `py-huckleberry-api` (~hourly). If refresh fails, the server
   re-authenticates transparently from env vars.

## Credential handling

- `HUCKLEBERRY_EMAIL`, `HUCKLEBERRY_PASSWORD`, `OAUTH_ADMIN_PASSWORD`, and
  `HUCKLEBERRY_DEFAULT_CHILD_UID` are stored **only** as Fly secrets
  (encrypted at rest). Never in git, never in image layers, never logged.
- `.env.example` ships placeholder values. `.env` is gitignored.
- Use a **Huckleberry-specific password**. Firebase auth here has no MFA.
- `OAUTH_ADMIN_PASSWORD` is an independent 32-byte random string.
  Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
  Compromising one does not imply the other.

## Consent-form hardening

- Password comparison uses `secrets.compare_digest` (no timing side-channel).
- POST `/consent` is rate-limited in-process to **10 attempts per IP per
  minute**. A long random admin password plus this ceiling makes online brute
  force impractical.
- On a wrong password, the pending OAuth session is preserved so the
  operator can retry without restarting the whole authorization flow.
- A correct password consumes the session — codes cannot be replayed.

## Dependency trust

| Layer         | Project                              | Trust signal                                                      | Pinning              |
|---------------|--------------------------------------|-------------------------------------------------------------------|----------------------|
| MCP framework | `fastmcp`                            | Active upstream; ships OAuth AS                                   | `>=2.12,<3.0`        |
| API client    | `huckleberry-api` (Woyken)           | Uses official Firebase SDK; MIT; PyPI; active                     | `>=0.4.0,<0.5.0`     |
| Fork base     | `bckenstler/py-huckleberry-mcp`      | Starting shape; tool logic has been rewritten against real API    | Git source; diffed   |
| Host          | Fly.io                               | First-party; secrets encrypted at rest                            | Managed              |

## Risk matrix

| Risk                                                           | Likelihood | Impact                                    | Mitigation                                                                      |
|----------------------------------------------------------------|------------|-------------------------------------------|---------------------------------------------------------------------------------|
| Huckleberry changes Firebase rules or schema                   | Medium     | Tools fail (no data loss)                 | Pin `huckleberry-api`; monitor upstream; `/health` surfaces auth status         |
| `huckleberry-api` v0.5.0 ships breaking changes                | Medium     | Silent tool failures                      | Upper-bound pin `<0.5.0`; review changelog before bumping                       |
| Git leak of `.env`                                             | Low        | Account compromise                        | `.gitignore` coverage; Fly secrets are primary store; unique Huckleberry password |
| Online brute force of consent password                         | Low        | Unauthorized bearer issuance              | 32-byte random; 10 req/min/IP rate limit; constant-time compare                  |
| Token exfil from memory (Fly VM compromise)                    | Very low   | Bearer valid ≤1 hour; refresh revoked     | Fly VM isolation; short TTL; revoke on rotation                                  |
| Huckleberry ToS enforcement                                    | Low        | Account suspension                        | Personal, non-commercial use; library mimics official SDK traffic                |
| Upstream fork introduces malicious code                        | Very low   | Credential exfil                          | Fork isolates; review diffs before pulling                                       |

## Reporting

Security issues: open a private GitHub security advisory. Do not file public issues
for vulnerabilities in this server or its OAuth implementation.
