# Hearthline (`real-estate-simulator`) — Feature Catalog

Last reviewed: 2026-09-28

README: [`../README.md`](../README.md). Operator runbook: [`RUNBOOK.md`](RUNBOOK.md). Operations: [`operations.md`](operations.md). Original quant brief: [`../sbloc_dashboard_architecture.md`](../sbloc_dashboard_architecture.md).

## Purpose

Authenticated household property planner built on an SBLOC vs sell-stock quant engine: financial profile → affordability ranges → RentCast (or demo) property scans with transparent scores, saved simulations, optional SMTP alerts. Calculations stay deterministic. Life Orchestrator profile: `hearthline` (`forbidden_actions` includes `model_generated_calculation`).

## Frontend workspaces

| Workspace | Capabilities |
| --- | --- |
| Auth | Register / login / logout. Registration can be disabled. |
| Overview | SBLOC simulator: inputs, macro banner, scenario cards, risk charts, save named simulation. |
| Finances / Profile | Income, debts, liquidity, credit score, risk/financing guardrails; primary vs rental buying ranges. |
| Discover / Properties | Saved scans (purpose primary/investment, Fairfield County default, filters, score thresholds, DSCR/cap-rate/cashflow mins), live vs demo provider badge, match verdicts, notification toggle. |
| Instructions | Product modal. |
| Public demo (`/demo`) | Unauthenticated, self-contained SBLOC walkthrough page (added 2026-08-30). Deployed to Vercel at `https://real-estate-simulator-self.vercel.app/demo` and linked from the portfolio site. |
| Short stays | Investment/hybrid STR scenarios; licensed property export imports with dated source/comparable evidence; written municipality/HOA gates; saved acquisition scans and downside screening. See [`STR-RUNBOOK.md`](STR-RUNBOOK.md). |

## Product API (authenticated)

- `POST /api/auth/register|login|logout`, `GET /api/auth/me`
- `GET|PUT /api/profile`, `GET /api/affordability`
- `GET /api/property-provider`
- CRUD `/api/searches`, matches list, `POST .../scan`
- CRUD `/api/simulations`
- STR underwriting and per-user scenario CRUD at `/api/str/underwrite` and `/api/str/scenarios`
- Immutable private licensed snapshots at `/api/str/forecasts`, property eligibility at `/api/str/eligibility`
- Saved acquisition searches, manual scans and dated history at `/api/str/acquisitions`

## Quant API (authenticated)

| Route | Behavior |
| --- | --- |
| `GET /api/health`, `/api/ready` | Liveness / readiness. |
| `GET /api/macro` | FRED SOFR/EFFR or fallback. |
| `POST /api/scenario-a` | Tax drag + 10y opportunity cost of selling stock. |
| `POST /api/scenario-b` | SBLOC cashflow + SOFR stress rows. |
| `POST /api/risk` | Monte Carlo margin-call probability (GBM) across horizons. |

## Jobs and providers

- Scheduled scan of notification-enabled searches; email new matches.
- Backup / DB maintenance one-shots in Compose `jobs` profile.
- Scan leases (`SCAN_LEASE_MINUTES`) for concurrency safety.
- RentCast sale listings + rental comps for investment scans. Auto demo listings when key missing.
- Geographic radius then strict Fairfield County filter; also city/state/ZIP/address nationwide.
- Explicitly no Zillow/Redfin scraping.
- STR acquisition job combines live RentCast sales with validated licensed property exports; no long-term-rent or market-average STR forecasts. Only current forecasts and both written permission gates can rank.
- Scheduled STR searches are opt-in; `make scan-str` runs a one-shot job. No timer or production deployment is installed by the PR.

## Runtime and data

- Local: backend `:8000`, frontend `:3000`.
- Compose: Caddy on loopback. Local default `127.0.0.1:3080`; DGX `infra/.env` uses `127.0.0.1:8083`.
- **DGX ingress:** `https://spark-1a8f.tailcc2643.ts.net:8446` (Tailscale Serve → Caddy `127.0.0.1:8083`), restored 2026-09-30 after `:8445` moved to Life Orchestrator. `HEARTHLINE_ORIGIN` in the DGX `infra/.env` and in `infra/.env.dgx.example` both name `:8446`.
- Resource caps: backend 2 CPU/2G, frontend 1.5 CPU/1G, no GPU, read-only FS, `cap_drop ALL`.
- SQLite `backend/data/real_estate_simulator.db`: users, sessions, financial_profiles, saved_searches, listing_matches, saved_simulations, scan_leases, schema_migrations.
- Schema 3/4 add str_scenarios, str_forecast_snapshots, str_eligibility, str_acquisition_searches, str_acquisition_runs and str_acquisition_leases. Backups omit licensed forecast/derived-run data; scenario references and household data remain backed up.
- Auth: email/password, hashed, server-side session cookies, CORS allowlist, rate limiting.
- Env names: `FRED_API_KEY`, `RENTCAST_API_KEY`, `SMTP_*`, `DATABASE_PATH`, `CORS_ALLOW_ORIGINS`, `REGISTRATION_ENABLED`, `PROPERTY_PROVIDER`, `SCANNER_RESULT_LIMIT`, `RATE_LIMIT_*`, `SESSION_*`.

## Gaps

Original architecture doc still mentions AWS/RDS, forward yield curves / VIX, and a full 10y net-worth chart that are not fully shipped. DGX profile leaves FRED/RentCast/SMTP unset by default (demo/fallback). Featured from `next-portfolio` via GitHub + the Vercel `/demo` URL. The DGX copy is an rsync'd non-git directory byte-identical to `5e536b0`; the `/demo` page (`f5f9e41`) was never deployed there. `infra/.env.dgx.example` was swallowed by `.gitignore` (`.env.*`) until 2026-09-28, when it was unignored and committed.
