# Platform sign-in (H1b)

Status: built and tested, **off by default** (`PLATFORM_CONTEXT=off`). Data model: `docs/PLATFORM_DATA_MODEL.md`. Decisions: platform ADR 0007, 0008, 0012 and its addendum; review records in `docs/consultant-reviews/`.

## What it does

A request that carries `X-Platform-Context` is a **platform request** and its result is final. The context is verified (ES256, at most 60 seconds, audience `module:hearthline`, entitlement `hearthline`) against the session edge's key set, and the scope is read from its claims: `ws.id` and the subject `sub`. Nothing else names a scope.

| Situation | Result |
| --- | --- |
| Verified user context, `PLATFORM_CONTEXT=on` | 200 with that workspace-and-subject scope; the legacy cookie and bearer are never read |
| Context refused (bad signature, expired, other app, not entitled, replayed write) | 401 or 403 with the contract code; never retried against the legacy cookie |
| Empty `X-Platform-Context` header | 401 `context_missing`; still a platform request |
| `PLATFORM_CONTEXT` not `on` | 403 `context_not_accepted` (no silent downgrade) |
| Key set URL not on loopback | 503 `context_unavailable` |
| Service context | 403 `scope_insufficient` (this app defines no service scopes) |
| Two `X-Platform-Context` fields | 401 `context_invalid` |
| Platform write without exactly one `Origin` equal to `PLATFORM_ORIGIN` (or none configured) | 403 `origin_required` |
| Any response to a platform request, including an uncaught 500 | `Cache-Control: private, no-store` |
| `/api/auth/register`, `/login`, `/logout` with a context | 403 `context_not_accepted` |
| `/api/auth/me` | `{"sign_in": "platform", "user": {"id": <subject>, "name": "Platform sign-in", "email": ""}}` |
| Alerts and scheduled scans for a platform person | 409 until worker authorization (platform P5) and a verified address exist |

Legacy accounts are unchanged: the same cookie sign-in, the same data, the same jobs.

## Operating notes

- **One process.** Replay protection for writes is the verifier's in-memory `jti` cache, enough only for one process behind private transport. The container runs `--workers 1`; a second worker needs a shared cache first.
- **Rate limits** key on the client address. Behind the edge every request arrives from the edge, so `RATE_LIMIT_TRUST_PROXY_HEADERS` must be `true` (the compose file sets it) and the edge must forward the client address.
- **Key set on loopback.** The adapter fetches the edge key set from `PLATFORM_JWKS_URL`, which must be the literal `127.0.0.1` or `[::1]` (no redirects, no proxies). A non-loopback endpoint would need an ADR change with an authenticated channel.
- **Staging network (consultant-required).** In the current Docker bridge network the edge is not on the backend container's loopback. For the Linux DGX staging pilot: run the backend on the **host network**, bind Uvicorn explicitly to `127.0.0.1` with `--workers 1` (override the image's `0.0.0.0` command), keep the key set on the host edge's loopback listener, give the edge a loopback upstream for `/api` and the UI, check actual listeners and Tailscale Serve mappings, keep a separate authorized legacy ingress during the pilot, and replace the wildcard forwarded-header trust (`--forwarded-allow-ips=*`) with the real proxy hops so the rate limiter sees a trustworthy address. None of this changes the current legacy deployment; it is the staging runbook's first step.
- **Edge requirements before staging.** The edge must require exactly one `Origin` equal to the module origin before it mints a context for a write (this app now enforces `PLATFORM_ORIGIN` too), strip client-supplied platform headers and legacy credentials on the platform route, and inject exactly one context.
- **Retention.** A platform read never deletes anything; a platform write deletes only that scope's expired licensed evidence. Schedule a database-wide purge (the scheduled STR scan job already runs one) so expired evidence does not wait for its owner's next write.
- **Browser.** `/api/auth/me` returns `workspace_id`; the page re-checks it when the tab or window regains focus or the page is restored from history and reloads if the person or workspace changed.
- **Vendored adapter.** `backend/vendor/platform-context` holds the wheel built from the platform repository at the commit in `PROVENANCE.json`, with a hash for every source file. `backend/tests/test_vendored_adapter.py` fails if the wheel, the lock or the installed copy differ. `backend/vendor/verify_vendored.py` runs before pip installs it (Dockerfile, `make bootstrap`, CI). Update it only in a dedicated PR from a reviewed platform commit. Install from `backend/` (the lock lists the wheel by relative path); `make bootstrap`, the Dockerfile and CI do.

## Proof

- `backend/tests/test_platform_context.py`: real ES256 contexts through the real routes (accepted, every refusal, flag off, key set location, replay on writes, Origin, no-store, cookie and bearer never consulted, empty header, auth routes refused, isolation across two workspaces, two subjects and a legacy account).
- `backend/tests/test_platform_scope.py` and `test_platform_migration.py`: data isolation for every record kind, migration safety (H1a).
- `backend/tests/test_vendored_adapter.py` and `backend/vendor/verify_vendored.py` (the check that runs before the wheel is installed).
- `scripts/smoke_platform.py` (`make smoke-platform`, in CI): the same behaviors against a real uvicorn server with a local key set.
- `make upgrade-rehearsal SOURCE=<copy of the live database>`: the release rehearsal the consultant required (below).

## Release rehearsal and staging acceptance (operator-run)

1. **Rehearsal on a copy of the live database** (app and jobs stopped; copy the file first, never point it at the live file): `make upgrade-rehearsal SOURCE=/path/to/copy.db`. It takes a pre-upgrade backup without running migrations, upgrades a second copy, compares counts and content digests per table, checks foreign keys, integrity and owner consistency, and restores the backup into a scratch file and compares again. It must print `Rehearsal passed`.
2. Deploy with `PLATFORM_CONTEXT=off`; confirm legacy sign-in, a saved search, and a scenario still work.
3. Turn the flag on for staging only, behind the real edge, with a platform person in two workspaces and a legacy account: repeat the isolation checks with real credentials (read, write, guessed ids), confirm a refused context is not retried against the cookie, a replayed write is refused, platform writes need an `Origin`, and responses are not cacheable through the edge.
4. Rollback: set `PLATFORM_CONTEXT=off` (platform records stay, unread). The previous release must not run against the upgraded database; restore the pre-upgrade backup only if no platform record exists, otherwise export those rows first (`PLATFORM_DATA_MODEL.md`).

## Not here

Linking a legacy account into the personal workspace, unlink and quarantine, edge legacy passthrough (P4), jobs for platform people (P5), and the step-up and audit pieces of the portal (P2, P3).
