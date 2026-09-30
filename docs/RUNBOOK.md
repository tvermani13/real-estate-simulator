# Hearthline operator runbook

Last reviewed: 2026-09-28

Short entry point. Full procedures (release gate, backups, restore rehearsal,
scheduled scans, update and rollback) are in [`operations.md`](operations.md).
Features: [`FEATURES.md`](FEATURES.md).

## Deployments

| Target | What | Source | Status (2026-09-30) |
| --- | --- | --- | --- |
| Vercel | Public `/demo` SBLOC walkthrough | `frontend/`, commit `f5f9e41` | `https://real-estate-simulator-self.vercel.app/demo` returns 200 |
| DGX `spark-1a8f` | Full authenticated stack (Caddy + Next.js + FastAPI + SQLite volume) | `~/projects/real-estate-simulator`, an rsync'd copy byte-identical to `5e536b0` (no `.git`) | Containers `hearthline-{gateway,frontend,backend}-1` healthy, image `0.2.0`, Caddy on `127.0.0.1:8083`. Tailnet: `https://spark-1a8f.tailcc2643.ts.net:8446` (restored 2026-09-30; `/`, `/api/ready`, `/api/health` return 200). `/demo` is Vercel-only because this copy predates it. |

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt && cp backend/.env.example backend/.env
cd backend && uvicorn app.main:app --reload --port 8000     # http://localhost:8000/docs
cd frontend && cp .env.example .env.local && npm run dev    # http://localhost:3000
make verify                                                  # full release gate
```

Container stack locally: `cp infra/.env.example infra/.env && make compose-build && make stack-up && make smoke`.

## DGX tailnet access (restored 2026-09-30)

`:8445` was reassigned to Life Orchestrator, so Hearthline moved to `:8446`.
The owner ran this on `spark-1a8f` in `~/projects/real-estate-simulator`:

1. Verified app backup (`/data/backups/hearthline-20260930T043130Z.db`).
2. Backed up `infra/.env` to `infra/.env.bak-2026-09-30`.
3. Set `HEARTHLINE_ORIGIN=https://spark-1a8f.tailcc2643.ts.net:8446`.
4. `docker compose ... up -d`, which recreated the backend.
5. `sudo tailscale serve --bg --https=8446 http://127.0.0.1:8083`.

Verified from the tailnet: `/`, `/api/ready`, and `/api/health` return 200.
CORS allows the `:8446` origin with credentials and rejects the old `:8445`
origin.

`HEARTHLINE_ORIGIN` is runtime-only: Compose passes it to the backend as
`CORS_ALLOW_ORIGINS`, so changing it never needs an image rebuild.

Rollback: `cp -p infra/.env.bak-2026-09-30 infra/.env`, then rerun `up -d`,
then `sudo tailscale serve --https=8446 off`. Never run `tailscale serve reset`.

Optional: `sudo tailscale set --operator=$USER` (once) would let `tvermani13`
manage Serve without `sudo`. It is the owner's call, since it widens who can
change Tailscale config on the box.

## Deploy an update to the DGX

From the Mac, on a verified commit:

```bash
make verify
scripts/deploy_dgx.sh          # takes a backup, rsyncs (no .git), builds ARM64 images, starts, checks readiness
```

`deploy_dgx.sh` preserves the remote `infra/.env` and Docker volumes. It
doesn't record which commit it shipped, so note the commit yourself. It also
never deletes remote files; rsync runs without `--delete`.

## Health, logs, backups

```bash
docker ps --filter name=hearthline
curl -fsS http://127.0.0.1:8083/api/health && curl -fsS http://127.0.0.1:8083/api/ready
cd ~/projects/real-estate-simulator && docker compose --env-file infra/.env -f infra/docker-compose.yml logs --tail 100 backend
docker compose --env-file infra/.env -f infra/docker-compose.yml --profile jobs run --rm backup
```

The stack restarts on its own after a reboot (`restart: unless-stopped`) and uses
no GPU. Scheduled scans aren't wired to a timer on the DGX. The scan job exists
(`--profile jobs`), but nothing runs it, and SMTP/RentCast/FRED are unset there,
so the DGX runs in demo/fallback mode.

## Repository hygiene

- `infra/.env.dgx.example` holds no secrets. `.gitignore` now unignores it
  (`!infra/.env.dgx.example`, after the `.env.*` rule) and it is tracked, because
  `deploy_dgx.sh` copies it to `infra/.env` on a fresh host. It names `:8446`.
  The real `infra/.env` and `backend/.env` stay ignored and are never rsynced.
- Consider making the DGX copy a git checkout, or have `deploy_dgx.sh` write
  the deployed commit to a `RELEASE` file, so drift is visible.
