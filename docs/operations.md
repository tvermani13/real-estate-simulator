# Hearthline operations

This runbook covers the Next.js, FastAPI, and Caddy container stack and its
tailnet-only DGX deployment. Caddy remains on loopback; Tailscale Serve is the
only client-facing layer. Do not enable Tailscale Funnel or a public proxy.

## Release gate

Use Python 3.11 and Node.js 22:

```bash
make bootstrap
make verify
```

`backend/requirements.lock` is the exact production Python dependency set.
`frontend/package-lock.json` is the exact frontend dependency set. CI repeats
the backend, frontend, Compose, container-start, and authenticated smoke checks.

`npm ci` runs with `--no-audit` because an online audit sends the private
project's dependency inventory to npm's advisory service. Generic install-time
advisory counts are deferred maintenance for this tailnet-only deployment, not
a release blocker. Review a full advisory report in an approved environment
before any public exposure, and never apply `npm audit fix --force` blindly.

## Stack design

`infra/docker-compose.yml` runs three persistent services:

- `gateway`: Caddy on `127.0.0.1:3080`, routing `/api/*` to FastAPI and all
  other requests to Next.js.
- `frontend`: a Next.js 16 standalone server on the private Compose network.
- `backend`: one Uvicorn worker on the private Compose network with SQLite in
  the `hearthline_data` volume.

The `jobs` profile adds one-shot `scanner` and `backup` containers. It does not
run either job continuously.

The browser always uses the same origin for pages, APIs, and session cookies.
The production frontend image therefore builds with an empty
`NEXT_PUBLIC_API_BASE_URL`; local development continues to use
`frontend/.env.local`.

## DGX deployment

Hearthline follows the existing personal-app convention on `spark-1a8f`:

```text
https://spark-1a8f.tailcc2643.ts.net:8445
  -> Tailscale Serve (tailnet only)
  -> Caddy 127.0.0.1:8083
       /api/* -> FastAPI
       /*     -> Next.js standalone
```

Smart Vault, CNBC Pro Clone, and Spark Chat keep their existing listeners on
HTTPS 443, 8443, and 8444. Never run `tailscale serve reset` while deploying or
updating Hearthline.

The initial deployment syncs the current reviewed worktree, builds the ARM64
images on the DGX, starts the stack, and verifies readiness:

```bash
scripts/deploy_dgx.sh
```

The script creates `/home/tvermani13/projects/real-estate-simulator`, preserves
remote ignored configuration and persistent Docker data, and initializes
`infra/.env` from `infra/.env.dgx.example` only when it does not already exist.
It never copies local API credentials.

On the first deployment only, add the dedicated tailnet listener without
changing the existing mappings:

```bash
sudo tailscale serve --bg --https=8445 http://127.0.0.1:8083
tailscale serve status
```

Validate both layers:

```bash
curl -fsS http://127.0.0.1:8083/api/ready
curl -fsS https://spark-1a8f.tailcc2643.ts.net:8445/api/ready
```

The DGX profile intentionally leaves FRED, RentCast, and SMTP unset. Macro data
and listings use labelled fallbacks, while email delivery stays disabled.
Registration starts enabled so the intended account can be created; set
`HEARTHLINE_REGISTRATION_ENABLED=false` in the DGX `infra/.env` and rerun the
stack after account creation.

## DGX resource boundary

The stack is ARM64-compatible and does not need CUDA.

- No service requests GPU devices or mounts NVIDIA device files.
- Every application container sets `NVIDIA_VISIBLE_DEVICES=void`.
- Persistent services are capped at a combined 4 CPUs and 3.25 GiB of memory.
- Jobs have separate bounded CPU and memory limits and run only on demand.
- Process counts are capped, root filesystems are read-only, application
  capabilities are dropped, and `no-new-privileges` is enabled. The Caddy image
  retains only `NET_BIND_SERVICE`, which its packaged binary requires.
- Only Caddy publishes a port, and it binds to loopback.

Keep these controls when the stack moves to the DGX so it cannot consume memory
or devices reserved for vLLM.

## Build and start locally

Create the non-secret Compose settings:

```bash
cp infra/.env.example infra/.env
```

Keep backend integration settings in the ignored `backend/.env`. External API
keys are optional: without them, Hearthline uses labelled demo listings,
fallback macro rates, and saved in-app matches without email delivery.

Build and start:

```bash
make compose-config
make compose-build
make stack-up
```

Verify:

```bash
curl -fsS http://127.0.0.1:3080/api/health
curl -fsS http://127.0.0.1:3080/api/ready
.venv/bin/python scripts/smoke_stack.py
```

The authenticated smoke mode creates a disposable account and should be used
only with a disposable or pre-production database:

```bash
.venv/bin/python scripts/smoke_stack.py --authenticated
```

Logs and shutdown:

```bash
make stack-logs
make stack-down
```

## Backend configuration to complete later

Before any HTTPS deployment, review these values in `backend/.env`:

```dotenv
ENVIRONMENT=production
CORS_ALLOW_ORIGINS=https://your-final-origin.example
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
REGISTRATION_ENABLED=false
PROPERTY_PROVIDER=rentcast
RENTCAST_API_KEY=
FRED_API_KEY=
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=true
```

Leave registration enabled only long enough to create intended accounts.
Because Caddy provides one origin, `SameSite=Lax` is sufficient; do not switch
to cross-site cookies unless the architecture changes.

## Database migrations

Startup applies ordered, idempotent migrations recorded in
`schema_migrations`. The readiness endpoint reports the current schema version.
The backend deliberately stays at one worker while SQLite is authoritative.

## Backups

Create a verified online SQLite backup and retain the newest 14:

```bash
make backup
```

The job writes backups under `/data/backups` in the persistent volume, runs
`PRAGMA quick_check`, and refuses to treat a database without migration metadata
as valid.

Backups in the same Docker volume protect against application mistakes but not
host or disk loss. Before a real deployment, add a second copy target outside
the DGX and test retrieval.

To inspect available backups:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml \
  --profile jobs run --rm --entrypoint sh backup \
  -c 'ls -lh /data/backups'
```

## Restore rehearsal

Restores replace the active SQLite database, so stop all readers and writers:

```bash
make stack-down
docker compose --env-file infra/.env.example -f infra/docker-compose.yml \
  --profile jobs run --rm --entrypoint python backup \
  -m app.jobs.database_maintenance restore \
  /data/backups/hearthline-YYYYMMDDTHHMMSSZ.db --confirm-replace
make stack-up
curl -fsS http://127.0.0.1:3080/api/ready
```

The restore command verifies the selected backup and creates a
`pre-restore` safety copy of the replaced database.

## Scheduled scans

Manual execution:

```bash
make scan
```

On Linux, use a systemd timer whose service runs the same one-shot Compose job.
Protect the command with `flock` so scheduler invocations cannot overlap:

```ini
[Service]
Type=oneshot
WorkingDirectory=/path/to/real-estate-simulator
ExecStart=/usr/bin/flock -n /run/lock/hearthline-scan.lock /usr/bin/docker compose --env-file infra/.env.example -f infra/docker-compose.yml --profile jobs run --rm scanner
```

The application also stores per-search leases, preventing a scheduled scan and
a manual scan from processing the same saved search concurrently.

## Updating and rollback

For an update:

1. Run `make verify` on the candidate commit.
2. Create a verified database backup.
3. Build version-tagged images by changing `HEARTHLINE_VERSION`.
4. Run `make stack-up` and the read-only smoke test.
5. Review health, readiness, container health, and logs.

For rollback:

1. Stop the stack.
2. Restore the prior `HEARTHLINE_VERSION`.
3. Restore the pre-deployment database backup only if the schema or data changed
   incompatibly.
4. Start the stack and rerun readiness and smoke checks.

Do not delete the previous images or pre-deployment backup until the new version
has completed its soak period.
