# Short-term rental underwriting runbook

Hearthline adds a Short stays workspace for Northeast short-term rental investment and hybrid owner-use research. It reuses auth, FastAPI, Next.js, and SQLite without changing the existing SBLOC or long-term rental scanner.

## Operations
1. Run migrations automatically at API startup. Migration 3 creates per-user str_scenarios.
2. Run PYTHONPATH=backend python -m unittest discover -s backend/tests, then make verify.
3. Start locally per README, sign in, open Short stays, underwrite a sample and save/reload.
4. For DGX deployment, follow docs/operations.md: backup, verify, deploy, smoke, rollback. Preserve production volumes and Tailscale ports.
5. This PR is a first slice, not production-verified. Do not deploy before tests/build and user review.

## Model definitions
Inputs are pre-income-tax and manually entered. Cash-on-cash includes down payment, closing fees, furnishings and retained reserves. NOI excludes debt service; DSCR is NOI / debt service. Monthly gross profile replaces annual gross when provided. For hybrids, monthly owner-use nights reduce estimated earnings in proportion to monthly gross / days. Otherwise loss is gross * owner nights / 365, a simplistic approximation with warning. A ±20% revenue stress scales owner-use displacement too. No modeled tax benefits, income-tax liability, equity buildup, flood loss, inflation, appreciation, or seller exit costs. Refinancing keeps original loan remaining term, incorporates separate fees for simple payback, and is never assumed guaranteed.

## Evidence and legal gate
Market averages and manual assumptions stay research only. To clear revenue gate, require dated property-level licensed forecast (with at least 8 comparable rentals) or actual operations, and a 12-month forecast. Require written municipality and HOA/deed eligibility. Blocking either stops underwriting recommendations. Financial screen: DSCR 1.25x, cash-on-cash 8% and cash flow >=0 under −20% bookings. A passing screen does not constitute purchase approval.

## Licensed forecast data roadmap
- RentCast currently provides sale listings and LONG-TERM rental comps. Never use those as short-term nightly rental forecasts.
- Verify actual API product contracts for AirDNA Rentalizer, PriceLabs or Key Data; dashboards alone do not imply licensed API access.
- Create backend StrForecastProvider abstraction with address, listing attributes, seasonality, provider metadata, as-of date and comparable rental evidence.
- Store immutable licensed forecast snapshots (provider, data version, raw assumptions, comp count, address, as-of, generated date, monthly revenue, ADR/occupancy where licensed). Honor provider retention and resale restrictions.
- Calibrate with 24 months actuals and exclude bad comps, owner-blocked nights, condos vs cabins and unusual amenities; output p10/p50/p90 forecasts.
- Geocode parcel and verify municipal rules individually, plus flood map, tax assessments, HOA, insurance, permitted occupancy, septic and vendor cost quotes. Track ordinance URLs with effective dates.
- Extend existing property scans to shortlist nearby STR listings, rank only property-specific verified results, and label stale data as unverified.
- Add operations layer for owner properties and third-party management; confirm local licensing before onboarding external owners.

## Security
This is a PUBLIC repository. Never commit credentials, detailed CIBC financing terms, personal accounts, guest identities, or licensed datasets. Provider keys should remain backend-only environment variables. Protect user scenarios under existing CurrentUser auth and SQLite user foreign keys.

## Limitations / testing
New STR endpoints are POST /api/str/underwrite, GET/POST /api/str/scenarios, PUT/DELETE /api/str/scenarios/{id}. No licensed STR data API has been integrated. No claim of decision-grade forecast until actual property and provider verification.
