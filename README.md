# Real Estate SBLOC Simulator

Dashboard + API to evaluate funding a real estate down payment by:

- Selling equities (capital gains + opportunity cost), vs
- Borrowing via a Securities-Backed Line of Credit (SBLOC) (cashflow spread + margin call risk)

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

### Frontend (Next.js)

In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm run dev
```

Visit `http://localhost:3000`.

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

