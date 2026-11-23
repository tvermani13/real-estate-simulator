# Platform data model and scope seam (H1a)

Status: the data model and the request seam are in place. **Platform sign-in is not wired yet** (H1b) and no behavior changed for existing accounts. This document records what was built, how it is proven, and what must be true before the native path is turned on.

Decisions come from platform ADR 0008, 0012 and its addendum. Review record: `docs/consultant-reviews/`.

## Two separate worlds

| | Legacy account | Platform person |
| --- | --- | --- |
| Identity | Hearthline session cookie | Verified platform context (H1b) |
| Owner columns | `user_id` | `workspace_id` + `owner_sub` |
| Sees | its own `user_id` rows with no platform scope | its own workspace and subject rows only |
| Alerts, scheduled scans | yes | no (409) until platform worker authorization (P5) and a verified destination |

A row has exactly one owner: the database refuses a row with both a `user_id` and a workspace, with neither, with a half scope, or with a malformed `ws_` / `usr_` value. A record that belongs to another scope answers 404, the same as one that does not exist.

## What changed in the database (migration 5)

Rebuilt in one transaction (foreign keys off, `foreign_key_check` and `integrity_check` before commit, rollback on any failure): `financial_profiles`, `saved_searches`, `saved_simulations`, `str_scenarios`, `str_forecast_snapshots`, `str_eligibility`, `str_acquisition_searches`, `str_acquisition_runs`.

- Existing ids, content hashes and timestamps are preserved. `financial_profiles` gains a surrogate `id` equal to the old `user_id`.
- Legacy keys are unchanged. Native keys are added per scope, for example `(workspace_id, owner_sub, content_hash)`.
- An acquisition run must have the same owner as its search (triggers), and a search that has runs cannot change owner.

## Request seam

`app/core/scope.py` defines `Scope`. Every private query builds its WHERE clause, INSERT columns and ON CONFLICT target from a `Scope` and never from a request field. `CurrentPrincipal` (`app/core/auth.py`) returns the scope and, for a legacy account, its profile. In H1a the principal is the legacy account unless a test overrides the dependency; H1b replaces that with the verified platform context.

The background jobs build a legacy scope explicitly and select only rows that join to `users`, so native rows are never scanned.

## Proof

- `backend/tests/test_engine_golden.py`: engine outputs (scenario A and B, risk, STR underwriting, affordability) match the outputs captured before the change (exact structure, floats to one part in 1e9 because libm differs between platforms; the same inputs give identical bytes twice in one environment).
- `backend/tests/test_platform_migration.py`: ids and checksums preserved, cascades kept, a failing rebuild rolls back, owner rules enforced, same-scope triggers, idempotence.
- `backend/tests/test_platform_scope.py`: for every private record kind, the same subject in another workspace, another subject in the same workspace, a legacy account and guessed ids all see nothing and cannot change anything; legacy and platform worlds are disjoint both ways; platform scopes cannot enable alerts or scheduled scans; jobs skip native rows; a backup restored into an empty database keeps every row and scope.

## Cutover and rollback criteria

The native path stays off until all of these hold (H1b adds the flag and the checks):

1. The upgrade drill on a copy of the live database: migration 5 reports the expected row counts per table before and after, `PRAGMA foreign_key_check` and `integrity_check` are clean, and the golden outputs match.
2. A backup taken before the upgrade is kept until the first backup after the upgrade restores cleanly (the restore drill above, run on the DGX).
3. Staging acceptance for the native path (operator-run): two workspaces, two subjects, a legacy account, and the guessed-id checks.

A release that does not know migration 5 must not write to a v5 database: its profile insert omits the new `id` column and the database refuses it (`NOT NULL`). Roll back by restoring the pre-upgrade backup, never by running the old release on the upgraded file.

Rollback before any native row exists: restore the pre-upgrade backup (the previous release ignores nothing it needs; the legacy columns are unchanged and still hold every legacy row). After native rows exist, rolling back the release does not delete them: the previous release does not read them, and the pre-upgrade backup must not be restored over them without an export of the native rows first.

## Requirements recorded by the consultant review

For the linking change (later PR): keep one owner per row; move each legacy account's rows in place in one transaction, setting all three owner columns together and keeping ids and references; define collision handling for profiles, eligibility keys and forecast hashes first; stage and re-insert acquisition runs around the search move (the run triggers block either order); drain in-flight scans and clear alert destinations and schedule flags while P5 is pending.

For H1b acceptance: a release rehearsal on a representative v4 copy (verified pre-upgrade backup taken without running the migration; upgrade and restore with the app and jobs stopped; counts and content digests for every retained table; foreign-key and owner-consistency checks before restore replaces the target; the native path disabled while post-upgrade writes are kept); and, with the real adapter and ingress, flag on and off, platform principal wins when both credentials are present, an invalid platform credential fails closed, legacy sessions still work on the legacy path, active membership and canonical ids are verified before a scope is built, and the isolation tests repeated with real credentials for two subjects, two workspaces and a legacy account.

## Not in H1a

The verified platform principal, the vendored adapter wheel, the `/api/auth/me` shape and frontend handling for platform people (H1b); linking a legacy account into the personal workspace, unlink and quarantine; jobs for platform people (P5).
