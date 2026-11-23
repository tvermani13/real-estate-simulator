"""Rehearse the upgrade on a COPY of the live database (never the live file).

    python -m app.jobs.upgrade_rehearsal --source /path/to/copy-of-live.db [--workdir DIR]

1. Takes a pre-upgrade backup of the copy with SQLite's backup API, without running any migration
   (the normal backup command runs the migrations first, so it cannot serve as the pre-upgrade backup).
2. Upgrades a second copy with the real migrations.
3. Compares, for every private table, the row count and a content digest of the columns the old schema
   had; checks foreign keys, integrity, owner consistency and that no existing row was given a platform owner.
4. Restores the pre-upgrade backup into a scratch database and compares it with the original again.

Exits non-zero on any difference. Run it with the app and the jobs stopped.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from app.core import database
from app.core.config import settings
from app.jobs import database_maintenance

PRIVATE_TABLES = (
    "users", "sessions", "financial_profiles", "saved_searches", "listing_matches", "scan_leases",
    "saved_simulations", "str_scenarios", "str_forecast_snapshots", "str_eligibility",
    "str_acquisition_searches", "str_acquisition_runs", "str_acquisition_leases",
)
OWNED = tuple(t for t in PRIVATE_TABLES if t.startswith(("financial", "saved_", "str_scenarios", "str_forecast",
                                                        "str_eligibility", "str_acquisition_searches", "str_acquisition_runs")))


def _tables(db: sqlite3.Connection) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in db.execute(f"PRAGMA table_info({table})")]


def digest(path: Path, columns_of: dict[str, list[str]]) -> dict[str, tuple[int, str]]:
    """Row count and a digest of the given columns, in a stable order, for every table that has rows to compare."""
    out: dict[str, tuple[int, str]] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        existing = _tables(db)
        for table, columns in columns_of.items():
            if table not in existing:
                continue
            present = _columns(db, table)
            if any(column not in present for column in columns):
                # A retained column that disappeared is a difference, never a silently smaller comparison.
                out[table] = (-1, "missing columns: " + ", ".join(c for c in columns if c not in present))
                continue
            order = ", ".join(str(i + 1) for i in range(len(columns)))
            rows = db.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order}").fetchall()
            out[table] = (len(rows), hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest())
    return out


def rehearse(source: Path, workdir: Path) -> list[str]:
    problems: list[str] = []
    workdir.mkdir(parents=True, exist_ok=True)
    original_path = settings.database_path
    before, upgraded, restored = workdir / "before.db", workdir / "upgraded.db", workdir / "restored.db"
    try:
        # 1. pre-upgrade backup, no migration
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(before) as dst:
            src.backup(dst)
        database_maintenance.verify_database(before)
        with sqlite3.connect(f"file:{before}?mode=ro", uri=True) as db:
            old_columns = {t: _columns(db, t) for t in PRIVATE_TABLES if t in _tables(db)}
            version = db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        baseline = digest(before, old_columns)
        print(f"Source schema version {version}; {len(baseline)} tables compared.")

        # 2. upgrade a copy
        shutil.copy2(before, upgraded)
        settings.database_path = str(upgraded)
        database.init_database()

        after = digest(upgraded, old_columns)
        for table, expected in baseline.items():
            if after.get(table) != expected:
                problems.append(f"{table}: before {expected[0]} rows, after {after.get(table, (0,))[0]}, or the content changed")
        with sqlite3.connect(upgraded) as db:
            db.execute("PRAGMA foreign_keys = ON")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign_key_check found violations after the upgrade")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                problems.append("integrity_check failed after the upgrade")
            if database._owner_problems(db):
                problems.append("an acquisition run is owned differently from its search")
            for table in OWNED:
                if "workspace_id" in _columns(db, table):
                    stray = db.execute(f"SELECT count(*) FROM {table} WHERE workspace_id IS NOT NULL OR user_id IS NULL").fetchone()[0]
                    if stray:
                        problems.append(f"{table}: {stray} existing row(s) were given a platform owner or lost their account")

        # 4. restore the pre-upgrade backup and compare again
        settings.database_path = str(restored)
        database_maintenance.restore_backup(before, confirm_replace=True)
        again = digest(restored, old_columns)
        if again != baseline:
            problems.append("restoring the pre-upgrade backup did not reproduce the original content")
    finally:
        settings.database_path = original_path
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="a COPY of the live database file")
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        print(f"No such file: {args.source}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="hearthline-rehearsal-") as scratch:
        workdir = args.workdir or Path(scratch)
        workdir.mkdir(parents=True, exist_ok=True)
        problems = rehearse(args.source, workdir)
    if problems:
        print("REHEARSAL FAILED:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Rehearsal passed: counts and content match before and after, checks are clean, and the pre-upgrade backup restores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
