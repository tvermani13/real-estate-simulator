# Consultant brief: Hearthline H1a data model and scope seam

Date: 2026-11-22. Platform ADR 0012 and its addendum are already decided (workspace_id and owner_sub columns, legacy user_id kept, no `user_id` on native rows, native path first, jobs behind P5, backup and restore safety). This brief asks for review of how H1a applies them. Nothing here is live: platform sign-in is not wired in H1a and the legacy behavior is unchanged.

## What H1a changes

- Migration 5 rebuilds financial_profiles, saved_searches, saved_simulations, str_scenarios, str_forecast_snapshots, str_eligibility, str_acquisition_searches and str_acquisition_runs. Every rebuilt table has nullable `user_id`, `workspace_id` and `owner_sub`, with CHECKs: scope halves travel together, exactly one of `user_id` / `workspace_id` is set (XOR), and `ws_` / `usr_` shapes. financial_profiles gets a surrogate `id` (equal to the old user_id for existing rows). Unique keys exist per scope: legacy keeps its keys, native adds (workspace_id, owner_sub, ...) keys. Ids and content hashes of existing rows are preserved.
- The runner for a rebuild migration turns foreign keys off, opens BEGIN IMMEDIATE, runs the SQL, checks `PRAGMA foreign_key_check` and `integrity_check`, records the version and commits; on any failure it rolls back.
- A run and its search must share an owner (triggers on insert and update), and a search that has runs cannot change owner (trigger).
- A `Scope` value (legacy user, or workspace plus owner subject) builds every private query. A `Principal` dependency returns it. Legacy behavior is unchanged: the legacy principal is built from the existing session dependency. A platform principal is injected only by a test override in H1a.
- A platform scope cannot turn on email alerts or scheduled acquisition scans (409). The alert and scan jobs run without a person, and the platform has not yet verified a destination address for this person. Jobs already select only legacy rows (they join `users`).
- Golden engine outputs were captured before the change and are byte-identical after it.

## Questions

1. Is the XOR CHECK (legacy row or native row, never both) the right invariant for H1a, given the later linking change will have to move a legacy account's rows into the personal workspace? Is moving rows (update user_id to NULL and set the scope in one transaction, per table) acceptable, or should linking copy and delete?
2. financial_profiles uses a surrogate id with UNIQUE(user_id) and UNIQUE(workspace_id, owner_sub). Is a UNIQUE index over nullable columns safe here (SQLite treats NULLs as distinct), given the XOR CHECK?
3. Is restricting a platform scope from enabling alerts and scheduled scans until P5 the right narrowing, or should H1a allow the flag and have the job skip native rows?
4. Is the restore drill (backup via the sqlite backup API, restore into an empty database, compare ids, scopes, integrity and foreign keys) enough for the data-model change, and what else would you require before H1b wires a real principal?
5. Anything in the migration or scope seam that could leak one scope's rows to another, or lose rows on upgrade?
