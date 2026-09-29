# Hearthline operator runbook

Last reviewed: 2026-09-28

Short entry point. Full procedures (release gate, backups, restore rehearsal,
scheduled scans, update and rollback) are in [`operations.md`](operations.md).
Features: [`FEATURES.md`](FEATURES.md).

## Deployments

| Target | What | Source | Status (2026-09-28) |
| --- | --- | --- | --- |
| Vercel | Public `/demo` SBLOC walkthrough | `frontend/`, commit `f5f9e41` | `https://real-estate-simulator-self.vercel.app/demo` returns 200 |
| DGX `spark-1a8f` | Full authenticated stack (Caddy + Next.js + FastAPI + SQLite volume) | `~/projects/real-estate-simulator`, an rsync'd copy byte-identical to `5e536b0` (no `.git`) | Containers `hearthline-{gateway,frontend,backend}-1` healthy, image `0.2.0`, Caddy on `127.0.0.1:8083`. **No tailnet route yet: the `:8446` Serve listener needs a one-line `sudo` command from the owner (see below).** |

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt && cp backend/.env.example backend/.env
cd backend && uvicorn app.main:app --reload --port 8000     # http://localhost:8000/docs
cd frontend && cp .env.example .env.local && npm run dev    # http://localhost:3000
make verify                                                  # full release gate
```

Container stack locally: `cp infra/.env.example infra/.env && make compose-build && make stack-up && make smoke`.

## Restore DGX tailnet access (PENDING: needs the owner, root required)

Status on 2026-09-28: **not restored.** `:8445` was reassigned to Life Orchestrator
(`127.0.0.1:8084`), and nothing routes to Hearthline's Caddy on `127.0.0.1:8083`.
`:8446` was confirmed free in `tailscale serve status`. An attempt to add the
listener as the unprivileged `tvermani13` user failed:

```text
$ tailscale serve --bg --https=8446 http://127.0.0.1:8083
sending serve config: Access denied: serve config denied
Use 'sudo tailscale serve --bg --https=8446 http://127.0.0.1:8083'.
```

Nothing was changed on the DGX: Serve still lists only 443, 8441, 8443, 8444
and 8445, and the DGX `infra/.env` still names `HEARTHLINE_ORIGIN=...:8445`.
The stack keeps running unchanged and is healthy on loopback.

`HEARTHLINE_ORIGIN` is a runtime value only. Compose passes it to the backend
container as `CORS_ALLOW_ORIGINS`; it is not a build arg, and the frontend image
is built with an empty `NEXT_PUBLIC_API_BASE_URL`. Changing it needs no image
rebuild: `up -d` recreates the backend container (Compose may also restart its
dependent gateway) and keeps the `hearthline_data` volume.

Owner steps, in order (never `tailscale serve reset`; the command is additive):

```bash
ssh tvermani13@100.72.234.104
tailscale serve status                                         # confirm :8446 is still free
sudo tailscale serve --bg --https=8446 http://127.0.0.1:8083   # the only root step
cd ~/projects/real-estate-simulator
docker compose --env-file infra/.env -f infra/docker-compose.yml --profile jobs run --rm backup
cp -p infra/.env infra/.env.bak-2026-09-28
sed -i 's#^HEARTHLINE_ORIGIN=.*#HEARTHLINE_ORIGIN=https://spark-1a8f.tailcc2643.ts.net:8446#' infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d
curl -fsS http://127.0.0.1:8083/api/ready
curl -fsS https://spark-1a8f.tailcc2643.ts.net:8446/api/ready
curl -s -o /dev/null -w '%{http_code}\n' https://spark-1a8f.tailcc2643.ts.net:8446/    # expect 200
```

Roll back if something breaks: `cp -p infra/.env.bak-2026-09-28 infra/.env`, rerun the
`up -d` line, then `sudo tailscale serve --https=8446 off`.

Optional: `sudo tailscale set --operator=$USER` (once) would let `tvermani13` manage
Serve without `sudo` in future. That is the owner's call, since it widens who can
change Tailscale config on the box.

After the route works, delete this "PENDING" wording here, in `operations.md`, and
in `FEATURES.md`. `infra/.env.dgx.example` and `deploy_dgx.sh` already point at
`:8446`, so a fresh host needs no further edits.

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
