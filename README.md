# Hearthline Real Estate Planner

Hearthline is an authenticated property-planning product built around the original SBLOC simulator. It now supports:

- Email/password accounts with server-side sessions
- Persisted household finances, liquidity, liabilities, risk tolerance, and financing assumptions
- Separate primary-home and rental-investment buying ranges
- Saved property scans and transparent per-listing scores
- A RentCast-first listing provider with an automatic demo fallback until a key is configured
- Optional SMTP email alerts for new qualifying matches
- Named, saved versions of the original sell-stock vs. SBLOC model

## Repo layout

- `frontend/`: Next.js + Tailwind dashboard UI
- `backend/`: FastAPI quantitative engine

## Local development

### Backend (FastAPI)

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
uvicorn app.main:app --reload --port 8000
```

Then visit `http://localhost:8000/docs`.

The SQLite database is created at `backend/data/real_estate_simulator.db` and is ignored by git. For a public HTTPS deployment with a frontend and backend on different sites, configure:

```bash
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
```

### Frontend (Next.js)

In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm run dev
```

Visit `http://localhost:3000`.

Create an account, enter household finances under **Finances**, and then create a scan under **Properties**.

## Property data

RentCast is the preferred provider. Until a key is configured, the app automatically uses clearly marked illustrative listings so the whole workflow can still be tested. To enable live sale listings and local rental comps:

```bash
PROPERTY_PROVIDER=rentcast
RENTCAST_API_KEY=<your-key>
```

The integration uses RentCast's sale-listing endpoint and, for investment scans, a second rental-listing request to estimate market rent by property type and bedroom count. Fairfield County, Connecticut is the default launch market: the app runs a geographic radius query and then strictly filters the response to Fairfield County. Searches remain nationwide through city/state, ZIP code, or a street address with a configurable radius. It does not scrape Zillow or Redfin.

## Notifications and scheduled scans

Email is the initial alert channel. Set the `SMTP_*` variables in `backend/.env`, enable notifications on a saved scan, then schedule:

```bash
cd backend
PYTHONPATH=. python -m app.jobs.scan_saved_searches
```

Run that command from cron, a systemd timer, or your deployment scheduler. Only saved scans with notifications enabled are processed. New listings are stored before email delivery, so a mail outage does not lose matches.

## Verification

```bash
make verify
```

The verification gate runs backend unit and API integration tests, frontend lint,
TypeScript checks and a production build, dependency checks, and Docker Compose
validation.

## Container stack

The prepared self-hosted stack uses:

- Caddy as the only host-facing service, bound to `127.0.0.1:3080`
- Next.js standalone output for the frontend
- One FastAPI/Uvicorn worker for SQLite safety
- A persistent Docker volume for application state and verified backups
- One-shot scanner and backup jobs
- CPU, memory, process, read-only filesystem, and no-GPU controls

On the DGX, it stays on loopback behind a dedicated tailnet-only Tailscale Serve
listener. It is not publicly exposed and does not use the GPU.

```bash
cp infra/.env.example infra/.env
make compose-build
make stack-up
make smoke
make backup
```

Detailed deployment preparation, backup/restore, scheduler, rollback, API
configuration, and DGX resource-isolation guidance is in
[`docs/operations.md`](docs/operations.md).
