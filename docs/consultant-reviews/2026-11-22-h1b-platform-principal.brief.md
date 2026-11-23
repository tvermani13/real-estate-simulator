# Consultant brief: Hearthline H1b platform principal

Date: 2026-11-22. H1a (data model and scope seam) is merged and reviewed. H1b wires the real platform principal behind a flag that is off by default. It applies the decisions already reviewed for Kinscope K1 (the context is the sole credential; the legacy cookie is ignored with no 400; platform writes need an `Origin`; per-process `jti` memory is enough for CRUD under single-process private transport; JWKS over loopback only) to Hearthline's FastAPI app, with the vendored Python adapter.

## What H1b adds

- `backend/app/core/platform.py`: flag (`PLATFORM_CONTEXT=on`), loopback-only key set URL, a cached `Verifier` pinned to v1 and module `hearthline`, user contexts only, and an ASGI guard that requires `Origin` on platform writes and sets `Cache-Control: private, no-store` on every platform response.
- `current_principal`: if `X-Platform-Context` is present (even empty) the request is a platform request and its result is final, with the cookie and bearer never read; otherwise the unchanged legacy session. Register, login and logout refuse platform requests.
- Vendored wheel `platform_context` built from the platform repository at a recorded commit, with a hash per source file and a test that the wheel, the lock and the installed copy agree. It is installed by relative path from `backend/`.
- Frontend: platform people see no sign-out button and no alert or scheduled-scan controls.
- `scripts/smoke_platform.py`: real uvicorn, local key set, real signed contexts. `make upgrade-rehearsal`: the release rehearsal you required for H1a.

## Questions

1. Does this match the K1 decisions for the FastAPI case, and is anything in the principal or middleware wrong or leaky?
2. The Docker bridge network puts the backend container on a different loopback from the edge. The key set must be loopback-only. Which is right for staging: backend container on host networking bound to loopback, an edge sidecar, or something else? Is a narrow, explicit allowance for a non-loopback private address ever acceptable?
3. Is the vendoring and install-by-relative-path scheme adequate (provenance, per-file hashes, test), or do you require pip hash pinning of the wheel?
4. Is anything missing before the flag is turned on in staging?
