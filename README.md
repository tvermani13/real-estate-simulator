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
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
cd frontend && npm run lint && npm run build
```

## Deployment (example: DGX Spark + Tailscale Funnel + Vercel)

This repository can be deployed with:

- **Backend** on a Linux host (e.g. Ubuntu on a DGX Spark), kept private on localhost and exposed publicly via **Tailscale Serve + Funnel**
- **Frontend** deployed on **Vercel**, configured to call the backend using an environment variable

This section intentionally uses **placeholders** (no real URLs/domains) so you can keep a public repo without leaking infrastructure details.

### Backend deployment (Ubuntu host)

#### 1) Install and authenticate Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

#### 2) Run the API locally on loopback

It is strongly recommended to bind Uvicorn to `127.0.0.1` and not expose port `8000` directly to the internet.

```bash
cd /path/to/repo/backend
source /path/to/repo/.venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

#### 3) Expose the API with Tailscale Serve + Funnel

Create a persistent serve config and enable Funnel for the same port:

```bash
sudo tailscale serve --bg --http=8000 localhost:8000
sudo tailscale funnel --bg 8000
```

You should now have a public HTTPS base URL in the form:

- `https://<device-name>.<tailnet>.ts.net`

Test it:

```bash
curl -s https://<device-name>.<tailnet>.ts.net/api/health
```

#### 4) Run the API persistently with systemd

Create a unit:

```bash
sudo nano /etc/systemd/system/sbloc-backend.service
```

Example unit (replace paths/user):

```ini
[Unit]
Description=SBLOC Backend (FastAPI)
After=network.target

[Service]
User=<linux-username>
WorkingDirectory=/path/to/repo/backend
EnvironmentFile=/path/to/repo/backend/.env
ExecStart=/path/to/repo/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sbloc-backend
sudo systemctl status sbloc-backend --no-pager
```

Logs:

```bash
sudo journalctl -u sbloc-backend -f
```

#### 5) Backend environment variables

Copy the example file and edit:

```bash
cp backend/.env.example backend/.env
```

Important:

- `CORS_ALLOW_ORIGINS`: include your frontend origin(s) (local dev + Vercel prod). Example shape:
  - `http://localhost:3000,https://<your-vercel-project>.vercel.app`
- `FRED_API_KEY` (optional): enables live macro rates; otherwise the API returns fallback values.

After editing `backend/.env`, restart the service:

```bash
sudo systemctl restart sbloc-backend
```

#### 6) Updating the backend after code changes

If you make backend changes on another machine (e.g. your laptop) and push them to GitHub, you must pull those changes onto the host and restart the service.

From the repository directory on the host:

```bash
git pull
```

Then:

- If you changed Python code under `backend/app/**`:

```bash
sudo systemctl restart sbloc-backend
```

- If you changed dependencies (`backend/requirements.txt`):

```bash
source /path/to/repo/.venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart sbloc-backend
```

### Frontend deployment (Vercel)

1. Import the repo into Vercel.
2. Set the **Root Directory** to `frontend/`.
3. Set the environment variable:

- `NEXT_PUBLIC_API_BASE_URL` = `https://<device-name>.<tailnet>.ts.net`

Redeploy.

### Security notes

- Keep Uvicorn bound to `127.0.0.1` and let Tailscale handle public exposure.
- Funnel makes your API reachable from the public internet. Consider adding:
  - rate limiting / auth at an edge layer (or in-app),
  - monitoring/logging,
  - restricting inputs and compute limits (Monte Carlo runs) to prevent abuse.
