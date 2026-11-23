"""Migration 5 (platform ADR 0012): existing records survive unchanged and the database enforces the new keys."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.core.database import MIGRATIONS, connection, init_database

WS_A = "ws_aaaaaaaaaaaaaaaaaaaa"
WS_B = "ws_bbbbbbbbbbbbbbbbbbbb"
SUB_1 = "usr_1111111111111111111111"
SUB_2 = "usr_2222222222222222222222"

PRIVATE_TABLES = (
    "financial_profiles",
    "saved_searches",
    "saved_simulations",
    "str_scenarios",
    "str_forecast_snapshots",
    "str_eligibility",
    "str_acquisition_searches",
    "str_acquisition_runs",
)
LEGACY_COLUMNS = {
    "financial_profiles": "user_id, profile_json, updated_at",
    "saved_searches": "id, user_id, name, criteria_json, notifications_enabled, notification_email, created_at, updated_at, last_scanned_at",
    "saved_simulations": "id, user_id, name, inputs_json, created_at, updated_at",
    "str_scenarios": "id, user_id, name, deal_json, created_at, updated_at",
    "str_forecast_snapshots": "id, user_id, property_key, content_hash, forecast_json, as_of, imported_at, retention_until",
    "str_eligibility": "user_id, property_key, evidence_json, updated_at",
    "str_acquisition_searches": "id, user_id, name, request_json, enabled, created_at, updated_at, last_scanned_at",
    "str_acquisition_runs": "id, search_id, user_id, result_json, retention_until, created_at",
}


def seed_v4(db: sqlite3.Connection) -> None:
    """Two legacy accounts with a row in every private table, plus children of searches."""
    db.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    for version, sql in MIGRATIONS[:4]:
        db.executescript(sql)
        db.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))
    for user in ("u1", "u2"):
        db.execute("INSERT INTO users VALUES(?,?,?,?,?)", (user, f"Name {user}", f"{user}@example.test", "hash", "t"))
        db.execute("INSERT INTO financial_profiles VALUES(?,?,?)", (user, f'{{"liquid_cash":{len(user)}}}', "t"))
        db.execute("INSERT INTO saved_searches(id,user_id,name,criteria_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                   (f"search-{user}", user, "Search", "{}", "t", "t"))
        db.execute("INSERT INTO listing_matches VALUES(?,?,?,?,?,?,?,?)", (f"match-{user}", f"search-{user}", "p1", "{}", 0.5, "t", "t", None))
        db.execute("INSERT INTO scan_leases VALUES(?,?,?,?)", (f"search-{user}", "lease", "t", "t"))
        db.execute("INSERT INTO saved_simulations VALUES(?,?,?,?,?,?)", (f"sim-{user}", user, "Sim", "{}", "t", "t"))
        db.execute("INSERT INTO str_scenarios VALUES(?,?,?,?,?,?)", (f"scn-{user}", user, "Scn", "{}", "t", "t"))
        db.execute("INSERT INTO str_forecast_snapshots VALUES(?,?,?,?,?,?,?,?)", (f"fc-{user}", user, "key", "hash", "{}", "t", "t", "t"))
        db.execute("INSERT INTO str_eligibility VALUES(?,?,?,?)", (user, "key", "{}", "t"))
        db.execute("INSERT INTO str_acquisition_searches VALUES(?,?,?,?,?,?,?,?)", (f"acq-{user}", user, "Acq", "{}", 1, "t", "t", None))
        db.execute("INSERT INTO str_acquisition_runs VALUES(?,?,?,?,?,?)", (f"run-{user}", f"acq-{user}", user, "{}", "t", "t"))
        db.execute("INSERT INTO str_acquisition_leases VALUES(?,?,?)", (f"acq-{user}", "lease", "t"))


def checksums(db: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    out = {}
    for table, columns in LEGACY_COLUMNS.items():
        rows = db.execute(f"SELECT {columns} FROM {table} ORDER BY 1, 2").fetchall()
        digest = hashlib.sha256(repr([tuple(row) for row in rows]).encode()).hexdigest()
        out[table] = (len(rows), digest)
    for table in ("listing_matches", "scan_leases", "str_acquisition_leases", "users", "sessions"):
        rows = db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        out[table] = (len(rows), hashlib.sha256(repr([tuple(row) for row in rows]).encode()).hexdigest())
    return out


class PlatformMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original = settings.database_path
        settings.database_path = str(Path(self.temporary_directory.name) / "upgrade.db")

    def tearDown(self) -> None:
        settings.database_path = self.original
        self.temporary_directory.cleanup()

    def upgraded(self) -> dict[str, tuple[int, str]]:
        with connection() as db:
            seed_v4(db)
            before = checksums(db)
        init_database()
        return before

    def test_every_existing_record_survives_with_the_same_ids_and_content(self) -> None:
        before = self.upgraded()
        with connection() as db:
            after = checksums(db)
            self.assertEqual(before, after)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            for table in PRIVATE_TABLES:
                counts = db.execute(f"SELECT count(*), count(workspace_id), count(owner_sub) FROM {table}").fetchone()
                self.assertEqual(tuple(counts)[1:], (0, 0), f"{table}: no row is assigned an owner by the migration")
            # The profile's new key is the account id, so the id is stable.
            self.assertEqual({r[0] for r in db.execute("SELECT id FROM financial_profiles")}, {"u1", "u2"})

    def test_parent_child_links_and_cascades_still_work(self) -> None:
        self.upgraded()
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM listing_matches WHERE search_id='search-u1'").fetchone()[0], 1)
            db.execute("DELETE FROM saved_searches WHERE id='search-u1'")
            self.assertEqual(db.execute("SELECT count(*) FROM listing_matches").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM scan_leases").fetchone()[0], 1)
            db.execute("DELETE FROM users WHERE id='u2'")
            for table in PRIVATE_TABLES:
                self.assertEqual(db.execute(f"SELECT count(*) FROM {table} WHERE user_id='u2'").fetchone()[0], 0, table)
            self.assertEqual(db.execute("SELECT count(*) FROM str_acquisition_runs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM str_acquisition_leases").fetchone()[0], 1)

    def test_a_failed_rebuild_changes_nothing(self) -> None:
        with connection() as db:
            seed_v4(db)
            # An orphan the old schema tolerated only because foreign keys were off.
            db.commit()
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("INSERT INTO saved_simulations VALUES('orphan','missing-user','Sim','{}','t','t')")
        with self.assertRaises(RuntimeError):
            init_database()
        with connection() as db:
            self.assertEqual(db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0], 4)
            columns = [r[1] for r in db.execute("PRAGMA table_info(saved_simulations)")]
            self.assertNotIn("workspace_id", columns)
            self.assertEqual(db.execute("SELECT count(*) FROM saved_simulations").fetchone()[0], 3)

    def test_the_database_enforces_the_owner_rules(self) -> None:
        self.upgraded()
        with connection() as db:
            def insert(table_columns: str, values: tuple) -> None:
                marks = ",".join("?" * len(values))
                db.execute(f"INSERT INTO saved_simulations({table_columns}) VALUES({marks})", values)

            columns = "id,user_id,workspace_id,owner_sub,name,inputs_json,created_at,updated_at"
            insert(columns, ("native-1", None, WS_A, SUB_1, "Sim", "{}", "t", "t"))
            for bad in (
                ("both", "u1", WS_A, SUB_1, "Sim", "{}", "t", "t"),        # two owner kinds
                ("none", None, None, None, "Sim", "{}", "t", "t"),         # no owner
                ("half", None, WS_A, None, "Sim", "{}", "t", "t"),         # scope pair split
                ("short", None, "ws_short", SUB_1, "Sim", "{}", "t", "t"),  # identifier shape
                ("email", None, WS_A, "someone@example.test", "Sim", "{}", "t", "t"),
                ("quote", None, "ws_aaaaaaaaaaaaaaaaaaa'", SUB_1, "Sim", "{}", "t", "t"),
            ):
                with self.assertRaises(sqlite3.IntegrityError, msg=bad[0]):
                    insert(columns, bad)
            # One profile per scope, and per legacy account; two scopes and two subjects coexist.
            for scope in ((WS_A, SUB_1), (WS_B, SUB_1), (WS_A, SUB_2)):
                db.execute("INSERT INTO financial_profiles(id,workspace_id,owner_sub,profile_json,updated_at) VALUES(?,?,?,?,?)",
                           (f"{scope[0]}{scope[1]}", scope[0], scope[1], "{}", "t"))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO financial_profiles(id,workspace_id,owner_sub,profile_json,updated_at) VALUES('dup',?,?,?,?)",
                           (WS_A, SUB_1, "{}", "t"))
            # Forecast and eligibility keys include the scope: the same hash and property key in two scopes is fine.
            for scope in ((WS_A, SUB_1), (WS_B, SUB_1)):
                db.execute("INSERT INTO str_forecast_snapshots(id,workspace_id,owner_sub,property_key,content_hash,forecast_json,as_of,imported_at,retention_until) VALUES(?,?,?,?,?,?,?,?,?)",
                           (f"fc{scope[0]}", scope[0], scope[1], "key", "hash", "{}", "t", "t", "t"))
                db.execute("INSERT INTO str_eligibility(workspace_id,owner_sub,property_key,evidence_json,updated_at) VALUES(?,?,?,?,?)",
                           (scope[0], scope[1], "key", "{}", "t"))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO str_eligibility(workspace_id,owner_sub,property_key,evidence_json,updated_at) VALUES(?,?,?,?,?)",
                           (WS_A, SUB_1, "key", "{}", "t"))

    def test_a_run_and_its_search_always_share_an_owner(self) -> None:
        self.upgraded()
        with connection() as db:
            db.execute("INSERT INTO str_acquisition_searches(id,workspace_id,owner_sub,name,request_json,created_at,updated_at) VALUES('native-search',?,?,'n','{}','t','t')", (WS_A, SUB_1))
            db.execute("INSERT INTO str_acquisition_runs(id,search_id,workspace_id,owner_sub,result_json,retention_until,created_at) VALUES('ok','native-search',?,?,'{}','t','t')", (WS_A, SUB_1))
            for user_id, workspace, sub in ((None, WS_B, SUB_1), (None, WS_A, SUB_2), ("u1", None, None)):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO str_acquisition_runs(id,search_id,user_id,workspace_id,owner_sub,result_json,retention_until,created_at) VALUES('bad','native-search',?,?,?,'{}','t','t')",
                               (user_id, workspace, sub))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE str_acquisition_runs SET search_id='acq-u1' WHERE id='ok'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE str_acquisition_searches SET workspace_id=?, owner_sub=? WHERE id='native-search'", (WS_B, SUB_1))

    def test_a_run_owned_by_another_account_than_its_search_aborts_the_upgrade(self) -> None:
        with connection() as db:
            seed_v4(db)
            # u1's search carries a run that says it belongs to u2.
            db.execute("UPDATE str_acquisition_runs SET user_id='u2' WHERE id='run-u1'")
            before = checksums(db)
        with self.assertRaisesRegex(RuntimeError, "owned differently"):
            init_database()
        with connection() as db:
            self.assertEqual(db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0], 4)
            self.assertEqual(before, checksums(db))
            self.assertNotIn("workspace_id", [r[1] for r in db.execute("PRAGMA table_info(str_acquisition_runs)")])

    def test_a_sql_failure_during_the_copy_rolls_everything_back(self) -> None:
        from unittest.mock import patch
        from app.core import database
        with connection() as db:
            seed_v4(db)
            before = checksums(db)
        broken = [(v, sql.replace("DROP TABLE str_scenarios;", "SELECT * FROM table_that_does_not_exist;")
                   if v == 5 else sql) for v, sql in MIGRATIONS]
        with patch.object(database, "MIGRATIONS", tuple(broken)):
            with self.assertRaises(sqlite3.OperationalError):
                init_database()
        with connection() as db:
            self.assertEqual(db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0], 4)
            self.assertEqual(before, checksums(db))
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        init_database()  # the real migration still applies afterwards
        with connection() as db:
            self.assertEqual(db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0], 5)

    def test_two_initializers_starting_together_apply_the_migration_once(self) -> None:
        import threading
        with connection() as db:
            seed_v4(db)
            before = checksums(db)
        results: dict[str, str] = {}

        def start(name: str) -> None:
            try:
                init_database()
                results[name] = "ok"
            except Exception as error:  # pragma: no cover - failure detail goes into the assertion
                results[name] = f"{type(error).__name__}: {error}"

        threads = [threading.Thread(target=start, args=(name,)) for name in ("a", "b", "c")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(results, {"a": "ok", "b": "ok", "c": "ok"})
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM schema_migrations WHERE version=5").fetchone()[0], 1)
            self.assertEqual(before, checksums(db))

    def test_identifiers_with_embedded_nul_or_a_null_profile_id_are_refused(self) -> None:
        self.upgraded()
        with connection() as db:
            for workspace, sub in ((WS_A + "\x00", SUB_1), (WS_A, SUB_1 + "\x00x")):
                with self.assertRaises(sqlite3.IntegrityError, msg=repr((workspace, sub))):
                    db.execute("INSERT INTO saved_simulations(id,workspace_id,owner_sub,name,inputs_json,created_at,updated_at) VALUES('nul',?,?,'n','{}','t','t')",
                               (workspace, sub))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO financial_profiles(user_id,profile_json,updated_at) VALUES('u9','{}','t')")

    def test_upgrade_twice_is_a_no_op(self) -> None:
        before = self.upgraded()
        init_database()
        with connection() as db:
            self.assertEqual(before, checksums(db))
            self.assertEqual(db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()
