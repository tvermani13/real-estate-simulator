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
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS str_scenarios (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            deal_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_str_scenarios_user_id
        ON str_scenarios(user_id);
        """,
    ),
    (
        4,
        """
        CREATE TABLE str_forecast_snapshots (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_key TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            forecast_json TEXT NOT NULL,
            as_of TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            retention_until TEXT NOT NULL,
            UNIQUE(user_id, content_hash)
        );
        CREATE INDEX idx_str_forecasts_property ON str_forecast_snapshots(user_id, property_key, as_of);
        CREATE TABLE str_eligibility (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_key TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, property_key)
        );
        CREATE TABLE str_acquisition_searches (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            request_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_scanned_at TEXT
        );
        CREATE INDEX idx_str_acquisition_user ON str_acquisition_searches(user_id);
        CREATE TABLE str_acquisition_runs (
            id TEXT PRIMARY KEY,
            search_id TEXT NOT NULL REFERENCES str_acquisition_searches(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            result_json TEXT NOT NULL,
            retention_until TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_str_runs_search ON str_acquisition_runs(search_id, created_at);
        CREATE TABLE str_acquisition_leases (
            search_id TEXT PRIMARY KEY REFERENCES str_acquisition_searches(id) ON DELETE CASCADE,
            lease_token TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        """,
    ),
    (
        5,
        """
        -- rebuild-tables
        -- Platform ADR 0012, decision 1. Every private table gains a workspace
        -- and an owner subject next to the legacy user_id. Legacy rows keep
        -- their user_id and ids and get no scope; platform-native rows have a
        -- scope and no user_id. Exactly one owner kind per row (the later
        -- account link replaces that rule together with the user cascade).
        -- SQLite cannot relax NOT NULL or change keys in place, so each table
        -- is rebuilt; the runner checks foreign keys and rolls back on any
        -- violation before this commits.
        CREATE TABLE financial_profiles_v5 (
            id TEXT NOT NULL PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            profile_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id),
            UNIQUE(workspace_id, owner_sub),
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO financial_profiles_v5 (id, user_id, profile_json, updated_at)
            SELECT user_id, user_id, profile_json, updated_at FROM financial_profiles;
        DROP TABLE financial_profiles;
        ALTER TABLE financial_profiles_v5 RENAME TO financial_profiles;

        CREATE TABLE saved_searches_v5 (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            name TEXT NOT NULL,
            criteria_json TEXT NOT NULL,
            notifications_enabled INTEGER NOT NULL DEFAULT 0,
            notification_email TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_scanned_at TEXT,
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO saved_searches_v5 (id, user_id, name, criteria_json, notifications_enabled,
            notification_email, created_at, updated_at, last_scanned_at)
            SELECT id, user_id, name, criteria_json, notifications_enabled,
                notification_email, created_at, updated_at, last_scanned_at FROM saved_searches;
        DROP TABLE saved_searches;
        ALTER TABLE saved_searches_v5 RENAME TO saved_searches;
        CREATE INDEX idx_saved_searches_user_id ON saved_searches(user_id);
        CREATE INDEX idx_saved_searches_scope ON saved_searches(workspace_id, owner_sub);

        CREATE TABLE saved_simulations_v5 (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            name TEXT NOT NULL,
            inputs_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO saved_simulations_v5 (id, user_id, name, inputs_json, created_at, updated_at)
            SELECT id, user_id, name, inputs_json, created_at, updated_at FROM saved_simulations;
        DROP TABLE saved_simulations;
        ALTER TABLE saved_simulations_v5 RENAME TO saved_simulations;
        CREATE INDEX idx_saved_simulations_user_id ON saved_simulations(user_id);
        CREATE INDEX idx_saved_simulations_scope ON saved_simulations(workspace_id, owner_sub);

        CREATE TABLE str_scenarios_v5 (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            name TEXT NOT NULL,
            deal_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO str_scenarios_v5 (id, user_id, name, deal_json, created_at, updated_at)
            SELECT id, user_id, name, deal_json, created_at, updated_at FROM str_scenarios;
        DROP TABLE str_scenarios;
        ALTER TABLE str_scenarios_v5 RENAME TO str_scenarios;
        CREATE INDEX idx_str_scenarios_user_id ON str_scenarios(user_id);
        CREATE INDEX idx_str_scenarios_scope ON str_scenarios(workspace_id, owner_sub);

        CREATE TABLE str_forecast_snapshots_v5 (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            property_key TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            forecast_json TEXT NOT NULL,
            as_of TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            retention_until TEXT NOT NULL,
            UNIQUE(user_id, content_hash),
            UNIQUE(workspace_id, owner_sub, content_hash),
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO str_forecast_snapshots_v5 (id, user_id, property_key, content_hash, forecast_json,
            as_of, imported_at, retention_until)
            SELECT id, user_id, property_key, content_hash, forecast_json, as_of, imported_at,
                retention_until FROM str_forecast_snapshots;
        DROP TABLE str_forecast_snapshots;
        ALTER TABLE str_forecast_snapshots_v5 RENAME TO str_forecast_snapshots;
        CREATE INDEX idx_str_forecasts_property ON str_forecast_snapshots(user_id, property_key, as_of);
        CREATE INDEX idx_str_forecasts_scope_property
            ON str_forecast_snapshots(workspace_id, owner_sub, property_key, as_of);

        CREATE TABLE str_eligibility_v5 (
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            property_key TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, property_key),
            UNIQUE(workspace_id, owner_sub, property_key),
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO str_eligibility_v5 (user_id, property_key, evidence_json, updated_at)
            SELECT user_id, property_key, evidence_json, updated_at FROM str_eligibility;
        DROP TABLE str_eligibility;
        ALTER TABLE str_eligibility_v5 RENAME TO str_eligibility;

        CREATE TABLE str_acquisition_searches_v5 (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            name TEXT NOT NULL,
            request_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_scanned_at TEXT,
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO str_acquisition_searches_v5 (id, user_id, name, request_json, enabled, created_at,
            updated_at, last_scanned_at)
            SELECT id, user_id, name, request_json, enabled, created_at, updated_at, last_scanned_at
            FROM str_acquisition_searches;
        DROP TABLE str_acquisition_searches;
        ALTER TABLE str_acquisition_searches_v5 RENAME TO str_acquisition_searches;
        CREATE INDEX idx_str_acquisition_user ON str_acquisition_searches(user_id);
        CREATE INDEX idx_str_acquisition_scope ON str_acquisition_searches(workspace_id, owner_sub);

        CREATE TABLE str_acquisition_runs_v5 (
            id TEXT PRIMARY KEY,
            search_id TEXT NOT NULL REFERENCES str_acquisition_searches(id) ON DELETE CASCADE,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT,
            owner_sub TEXT,
            result_json TEXT NOT NULL,
            retention_until TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK ((workspace_id IS NULL) = (owner_sub IS NULL)),
            CHECK ((user_id IS NULL) <> (workspace_id IS NULL)),
            CHECK (
                workspace_id IS NULL OR (
                    workspace_id GLOB 'ws_*' AND length(workspace_id) BETWEEN 19 AND 43
                    AND substr(workspace_id, 4) NOT GLOB '*[^A-Za-z0-9]*'
                    AND owner_sub GLOB 'usr_*' AND length(owner_sub) BETWEEN 20 AND 44
                    AND substr(owner_sub, 5) NOT GLOB '*[^A-Za-z0-9]*'
                    AND length(CAST(workspace_id AS BLOB)) = length(workspace_id)
                    AND length(CAST(owner_sub AS BLOB)) = length(owner_sub)
                )
            )
        );
        INSERT INTO str_acquisition_runs_v5 (id, search_id, user_id, result_json, retention_until, created_at)
            SELECT id, search_id, user_id, result_json, retention_until, created_at
            FROM str_acquisition_runs;
        DROP TABLE str_acquisition_runs;
        ALTER TABLE str_acquisition_runs_v5 RENAME TO str_acquisition_runs;
        CREATE INDEX idx_str_runs_search ON str_acquisition_runs(search_id, created_at);

        -- A run has the same owner as the search it belongs to, in the database.
        CREATE TRIGGER str_runs_same_scope_insert BEFORE INSERT ON str_acquisition_runs
        BEGIN
            SELECT RAISE(ABORT, 'run scope differs from its search') WHERE NOT EXISTS (
                SELECT 1 FROM str_acquisition_searches s
                WHERE s.id = NEW.search_id AND s.user_id IS NEW.user_id
                    AND s.workspace_id IS NEW.workspace_id AND s.owner_sub IS NEW.owner_sub
            );
        END;
        CREATE TRIGGER str_runs_same_scope_update
        BEFORE UPDATE OF search_id, user_id, workspace_id, owner_sub ON str_acquisition_runs
        BEGIN
            SELECT RAISE(ABORT, 'run scope differs from its search') WHERE NOT EXISTS (
                SELECT 1 FROM str_acquisition_searches s
                WHERE s.id = NEW.search_id AND s.user_id IS NEW.user_id
                    AND s.workspace_id IS NEW.workspace_id AND s.owner_sub IS NEW.owner_sub
            );
        END;
        CREATE TRIGGER str_search_scope_frozen
        BEFORE UPDATE OF user_id, workspace_id, owner_sub ON str_acquisition_searches
        WHEN EXISTS (SELECT 1 FROM str_acquisition_runs r WHERE r.search_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'a search with runs cannot change owner');
        END;
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


def _statements(sql: str) -> list[str]:
    """Split a script into complete statements (triggers keep their inner semicolons)."""
    out: list[str] = []
    current = ""
    for line in sql.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            out.append(current)
            current = ""
    if current.strip():
        out.append(current)
    return out


def _owner_problems(db: sqlite3.Connection) -> list[str]:
    """Rows whose owner disagrees with their parent's. Both owner fields are compared null-safely."""
    return [
        row[0]
        for row in db.execute(
            """
            SELECT r.id FROM str_acquisition_runs r
            LEFT JOIN str_acquisition_searches s ON s.id = r.search_id
            WHERE s.id IS NULL
               OR s.user_id IS NOT r.user_id
               OR s.workspace_id IS NOT r.workspace_id
               OR s.owner_sub IS NOT r.owner_sub
            """
        )
    ]


def _apply_rebuild_migration(db: sqlite3.Connection, version: int, sql: str) -> None:
    """SQLite's documented table-rebuild procedure.

    Foreign keys are off while tables are dropped and renamed (the pragma is a
    no-op inside a transaction, so it is set first), the whole rebuild runs in
    one write transaction, and the transaction commits only when the integrity,
    foreign-key and owner checks find nothing. Any failure, including one in the
    SQL itself, rolls the whole migration back and leaves the previous schema
    untouched. The version is read again after the write lock is held, so a
    second process that started at the same time finds the work already done.
    """
    db.commit()
    db.execute("PRAGMA foreign_keys = OFF")
    previous_isolation = db.isolation_level
    db.isolation_level = None
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone():
                db.execute("ROLLBACK")
                return
            for statement in _statements(sql):
                db.execute(statement)
            violations = db.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(
                    f"migration {version} left {len(violations)} foreign-key violation(s)"
                )
            integrity = db.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise RuntimeError(f"migration {version} failed the integrity check: {integrity}")
            problems = _owner_problems(db)
            if problems:
                raise RuntimeError(
                    f"migration {version} found {len(problems)} acquisition run(s) owned differently "
                    f"from their search; fix them before upgrading (first: {problems[0]})"
                )
            db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
    finally:
        db.isolation_level = previous_isolation
        db.execute("PRAGMA foreign_keys = ON")


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
            if "-- rebuild-tables" in sql:
                _apply_rebuild_migration(db, version, sql)
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
