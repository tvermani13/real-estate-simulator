# Short-term rental underwriting runbook

Short stays supports authenticated investment and owner-use hybrid scenarios,
licensed property forecast imports, and acquisition searches. Existing SBLOC,
profile, long-term rental scanning, notifications, and public demo workflows
remain separate. Keep PR #1 in draft; do not deploy or merge automatically.

## Development and release gates

1. Install the lockfiles with `make bootstrap`; start native services as in README.
2. Run `make verify`: Python unit/API tests, lint, TypeScript, production build,
   dependency consistency, and Compose validation.
3. Sign in, open **Short stays**, create/update/reload/delete a scenario. Import
   a normalized licensed export, inspect its source and comparables, attach it,
   and review written eligibility. Save an acquisition search and scan it.
4. CI also builds an isolated container stack and runs
   `scripts/smoke_stack.py --authenticated` with a disposable database.
5. Before any separately authorized deployment, follow `operations.md` for
   backup, readiness, smoke, rollback, and preservation of existing Tailscale ports.

Startup migration 3 creates per-user `str_scenarios`. Migration 4 adds immutable
forecast snapshots, property eligibility records, acquisition searches, scan
runs, and leases. Upgrade tests retain existing users, SBLOC simulations and
long-term searches; repeated migrations and backup/restore are tested.

## Financial model

Amounts are USD, before income tax. Revenue is **accommodation revenue only**:
exclude guest taxes and cleaning-fee income. Cleaning/supplies remain an expense
assumption. Do not combine a forecast net of manager/platform fees with those
fees again. Monthly gross overrides annual gross. Forecasts cover all calendar
nights **before** personal-use blocks; already owner-blocked forecasts are rejected.

For a hybrid with monthly owner nights, displaced expected earnings are
`monthly gross × blocked calendar nights / days in that month`. This includes
forecast occupancy once: at $200 ADR and 50% occupancy, an owner night displaces
$100 expected revenue, not $200. Demand is assumed uniform within a month;
weekend/holiday premiums and booking fragmentation are not modeled. Without a
monthly profile or owner-night timing, uniform annual displacement is labelled
an approximation. Dated licensed forecasts supply their actual month lengths,
including leap February; monthly inputs are mapped to January–December for
owner-use matching even when the horizon starts in another month.

Variable costs apply to revenue after owner-use displacement. Fixed costs
include property tax, insurance, utilities, services, HOA dues and the combined
maintenance/capex reserve. Reported NOI and DSCR use this **reserve-adjusted**
NOI; lender NOI excluding capex may differ. Debt service includes principal and
interest. DSCR = NOI / annual debt service, and is null for an all-cash deal.
Cap rate = NOI / purchase price. Cash-on-cash = annual cash flow / initial cash,
where cash includes down payment, closing fees, furnishings and retained
reserves. Zero initial cash gives an undefined/null return. Full owner blocking
gives no finite breakeven (null), never Infinity in JSON.

Mortgages fully amortize at the entered fixed APR. Refinancing uses the balance
**after** the specified number of payments and the original remaining term;
it does not reset a 30-year clock or refinance the original principal. Fees are
paid separately in cash. Simple fee payback is fees / annual payment savings,
undefined when savings are nonpositive. Future annual refinance cash flow is a
steady-state illustration, not a blended acquisition-year figure. Refinancing
is not guaranteed. The ±20% revenue stress scales displacement and variable
costs together; fixed costs and debt stay fixed. It is not a calibrated
probability forecast. No tax benefits, income tax, appreciation, exit costs,
inflation, flood loss or equity-return forecast is modeled.

## Licensed property forecasts: exports first

`StrForecastProvider` is the async adapter interface in
`backend/app/services/str_forecasts.py`. `LicensedExportForecastProvider` reads
private normalized snapshots. Add future adapters through
`get_str_forecast_provider()` after checking the actual licensed API contract.
No AirDNA/PriceLabs/Key Data API endpoint or license is assumed or fabricated.
RentCast sale listings and **long-term** rent comparables are never STR forecasts.

Use **Normalized forecast export (JSON)** in Short stays, or authenticated
`POST /api/str/forecasts/import`. This is Hearthline's normalized contract, not
a promise to accept each vendor's raw dashboard export. Map only fields your
license permits. Inspect the exact schema with:

```bash
PYTHONPATH=backend .venv/bin/python - <<'PY'
import json
from app.routes.str_forecast_models import LicensedForecastExport
print(json.dumps(LicensedForecastExport.model_json_schema(), indent=2))
PY
```

Required fields:

| Field | Contract |
| --- | --- |
| `forecast_kind` | `property_specific`; market averages are rejected |
| `provider`, `source_url`, `attribution`, `data_version`, `methodology` | Explicit attribution, original evidence URL, version and forecast assumptions |
| `license_reference`, `licensed_use_attested` | Contract reference and true attestation; user must actually verify licensed access |
| `permitted_use`, `retention_permitted`, `retention_until` | `internal_underwriting`, true, and a permitted retention end date |
| `property` | Full address, property type, bedrooms, bathrooms, provider subject ID |
| `as_of`, `generated_at` | Evidence date and timezone-aware generation timestamp, neither future-dated |
| `currency`, `revenue_basis` | `USD`, `accommodation_only_before_owner_use` |
| `months` | Exactly 12 consecutive first-of-month dates and nonnegative finite `gross_revenue` |
| Optional monthly `adr`, `occupancy`, `available_nights` | Supply all three together; occupancy is 0–1, nights are all calendar days, revenue equals ADR × occupancy × nights within 1% or $1 rounding |
| `comparables` | Distinct IDs and source URLs, type/beds/baths, distance, approximately 12-month observation dates, revenue, booked and owner-blocked nights, optional exclusion reason |
| Optional `annual_p10`, `annual_p90` | Provider-supplied bounds surrounding the base annual forecast; never invented confidence intervals |

For this phase, qualified comparables must share the subject property type,
be within one bedroom and bathroom, be within 25 miles, contain no owner-blocked
nights, and have an observation period ending within 90 days of `as_of`.
Explicitly excluded comps and the subject property cannot count. At least **8**
qualified comps are required. These conservative rules do not replace review of
amenities, permitted occupancy, quality, seasonality and competition. The app
validates evidence structure and consistency; it does not authenticate a vendor
export's signature, independently audit comparables, or calibrate forecast accuracy.
Actual operations are still self-reported research inputs until a separate
actuals-validation adapter exists.

Snapshots include a content hash, import timestamp and all dated normalized
assumptions. Identical imports by the same user return the same snapshot ID;
changed forecasts get a new immutable ID. Lookup matches address after only
case/spacing normalization and requires matching property type, beds and baths.
Nearby addresses, address aliases and remodeled-property assumptions do not
silently match. Evidence older than 90 days or a horizon starting before the
current month/more than two months ahead is stale. Results explicitly distinguish
`available`, `unavailable`, `stale`, `insufficient_evidence`, `property_mismatch`
and `license_expired`. No missing-data revenue is fabricated.

Authenticated scenario underwriting with `forecast_snapshot_id` resolves that
user's current evidence and overrides client-entered revenue and comp counts.
A self-selected provenance dropdown cannot clear the evidence gate. Scenario
storage retains the snapshot reference rather than duplicating licensed figures.
Expired/deleted references require a new permitted import. All endpoints require
existing session auth and user ownership; foreign IDs return 404.

### Retention and privacy

Do not commit real exports, provider keys, personal financing terms, guest data
or licensed datasets. The test fixtures are entirely synthetic and explicitly
labelled. Snapshots and derived scan results are private per user; there is no
public forecast distribution endpoint. Import only contracts permitting the
normalized evidence to be displayed to that user and retained internally.

Reads, imports and the scheduled job logically delete evidence and derived runs
after `retention_until`. Deleting a snapshot also deletes affected scan history.
Run the job daily even if no searches are enabled to ensure cleanup. SQLite
backups (including pre-restore safety copies) exclude forecast snapshots and
derived acquisition runs, compacting the backup to remove deleted pages. They
retain users, household data, scenarios/references and acquisition settings;
licensed evidence must be reimported after restore. Platform filesystem snapshots,
WAL files, historical backups and logs are outside this application's purge
boundary. The operator must reconcile those retention policies with the license
before importing real data. Do not promise physical erasure across those systems.

## Municipality and HOA/deed gates

Eligibility is stored by user and exact property identity. Each municipality
and HOA/deed decision defaults to `unknown`. To verify or block, require a
written document reference/URL, authority, review date, expiry/review-by date,
and operating conditions in notes. A zero HOA fee does **not** establish no deed
restriction. An expired permission becomes unknown; an expired prohibition
remains blocked until affirmative new review. The user reviews the proposed STR
use; the software does not infer permission from a sale listing or act as legal counsel.

`blocked` overrides all financial results. Unknown/expired permission, missing
current forecasts, and manual/market inputs are research only. Verified revenue
and both current permissions are necessary for a financial screen: DSCR ≥1.25
(or all-cash), cash-on-cash ≥8%, and annual cash flow ≥0 under −20% revenue.
Acquisition searches can impose stricter cap-rate/DSCR/cashflow/return thresholds.
A passing screen does not authorize purchase or waive parcel-level flood,
insurance, septic, tax, lender, or occupancy checks.

## Acquisition scanning and scheduling

Save a search from Short stays using the current scenario's financing/cost
assumptions. Per candidate, the job:

1. Requests live RentCast **sale** listings only and applies price/type/bed/bath/age filters.
2. Matches a dated property-specific snapshot by exact address and attributes.
3. Loads user-specific written municipality and HOA/deed evidence.
4. Uses sale price and annualized listing HOA dues, overriding template values.
5. Applies STR cashflow and downside screens. Only fully qualified candidates
   get ranks, ordered by downside cash flow. Others remain visible with reasons.
6. Saves a dated private run for review. Old run ranks describe evidence at scan
   time; rescan before relying on them. No purchases or email messages are triggered.

Missing RentCast access or an upstream failure produces an explicit unavailable
run with no demo shortlist. A missing forecast produces a visible unranked
candidate with no underwriting substituted. Forecast updates and gate changes
require a rescan. Searches default to scheduled scanning **disabled**.

Native one-shot job:

```bash
cd /workspace/real-estate-simulator
PYTHONPATH=backend .venv/bin/python -m app.jobs.scan_str_acquisitions
```

Compose one-shot job (reuses the bounded scanner container):

```bash
make scan-str
```

Schedule only after separate operator approval. For example, a daily systemd
service can use this `ExecStart` with the working directory/config appropriate to
that installation; a timer invokes it daily:

```ini
[Service]
Type=oneshot
WorkingDirectory=/path/to/real-estate-simulator
ExecStart=/usr/bin/flock -n /run/lock/hearthline-str-scan.lock /usr/bin/docker compose --env-file infra/.env.example -f infra/docker-compose.yml --profile jobs run --rm scanner python -m app.jobs.scan_str_acquisitions
```

The application also acquires per-search expiring leases and releases only its
own token. The job processes enabled searches for their owning users, logs IDs
and outcome counts without licensed payloads/credentials, and returns nonzero
when a required provider is unavailable or a scan fails. The UI toggle does not
install a timer. No schedule has been installed or deployment performed by this PR.

## Authenticated API

- `POST /api/str/underwrite`
- `GET/POST /api/str/scenarios`; `GET/PUT/DELETE /api/str/scenarios/{id}`
- `POST /api/str/forecasts/import`, `POST /api/str/forecasts/lookup`
- `GET/DELETE /api/str/forecasts/{id}` (immutable; no update endpoint)
- `PUT /api/str/eligibility`, `POST /api/str/eligibility/lookup`
- `GET/POST /api/str/acquisitions`; `PUT/DELETE /api/str/acquisitions/{id}`
- `POST /api/str/acquisitions/{id}/scan`; `GET .../{id}/runs` (latest 20)

## Outstanding production evidence

No live licensed vendor data or RentCast acquisition call has been verified in
this development instance. Synthetic provider fixtures validate contracts and
failure handling, not forecast accuracy. Provider licensing/normalization,
real property comp review, cost quotes, written eligibility, and any live API
adapter remain external evidence requirements before production decisions.

Development validation on 2026-10-09: `make verify` passed with 53 backend tests,
lint, TypeScript, production build, dependency consistency and Compose config.
An isolated Python 3.11 / Node 22 container stack passed authenticated smoke
checks. A Chromium/Playwright check exercised registration, scenario save/reload/
update, synthetic forecast import and comparable display, written eligibility,
the financial screen, unavailable RentCast access, existing workspaces and demo
without JavaScript page errors. Cloud container builds required an external
proxy/hostname/CA trust override and a readable Caddyfile; repository Dockerfiles
and TLS/checksum verification were preserved. These local checks do not assert
remote CI completion, vendor forecast accuracy or production readiness.
