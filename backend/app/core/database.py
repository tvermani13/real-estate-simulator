from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

        CREATE TABLE IF NOT EXISTS financial_profiles (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            profile_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS saved_searches (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            criteria_json TEXT NOT NULL,
            notifications_enabled INTEGER NOT NULL DEFAULT 0,
            notification_email TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_scanned_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_saved_searches_user_id ON saved_searches(user_id);

        CREATE TABLE IF NOT EXISTS listing_matches (
            id TEXT PRIMARY KEY,
            search_id TEXT NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
            provider_listing_id TEXT NOT NULL,
            match_json TEXT NOT NULL,
            match_score REAL NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            notified_at TEXT,
            UNIQUE(search_id, provider_listing_id)
        );
        CREATE INDEX IF NOT EXISTS idx_listing_matches_search_id ON listing_matches(search_id);

        CREATE TABLE IF NOT EXISTS saved_simulations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            inputs_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_saved_simulations_user_id ON saved_simulations(user_id);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS scan_leases (
            search_id TEXT PRIMARY KEY REFERENCES saved_searches(id) ON DELETE CASCADE,
            lease_token TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scan_leases_expires_at ON scan_leases(expires_at);
        """,
    ),
)


def database_path() -> Path:
    path = Path(settings.database_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(database_path(), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 30000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_database() -> None:
    with connection() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            int(row["version"])
            for row in db.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            db.executescript(
                f"""
                BEGIN IMMEDIATE;
                {sql}
                INSERT INTO schema_migrations (version) VALUES ({version});
                COMMIT;
                """
            )
        db.execute("PRAGMA journal_mode = WAL")


def database_readiness() -> dict[str, int | str]:
    with connection() as db:
        db.execute("SELECT 1").fetchone()
        row = db.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
    return {"status": "ok", "schema_version": int(row["version"])}


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def json_loads(value: str) -> Any:
    return json.loads(value)
