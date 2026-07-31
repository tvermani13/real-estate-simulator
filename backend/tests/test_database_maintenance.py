from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.core.database import connection, database_readiness, init_database
from app.jobs.database_maintenance import create_backup, restore_backup, verify_database


class DatabaseMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = settings.database_path
        self.database = Path(self.temporary_directory.name) / "application.db"
        settings.database_path = str(self.database)
        init_database()

    def tearDown(self) -> None:
        settings.database_path = self.original_database_path
        self.temporary_directory.cleanup()

    def test_migrations_are_idempotent(self) -> None:
        init_database()
        self.assertEqual(database_readiness()["schema_version"], 2)
        with connection() as db:
            count = db.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()
        self.assertEqual(count["count"], 2)

    def test_backup_verify_and_restore_round_trip(self) -> None:
        backups = Path(self.temporary_directory.name) / "backups"
        backup = create_backup(backups, retention=2)
        verify_database(backup)

        with connection() as db:
            db.execute(
                """
                INSERT INTO users (id, name, email, password_hash, created_at)
                VALUES ('after-backup', 'After Backup', 'after@example.com', 'hash', 'now')
                """
            )
        safety_backup = restore_backup(backup, confirm_replace=True)
        self.assertTrue(safety_backup.exists())
        with connection() as db:
            row = db.execute("SELECT id FROM users WHERE id = 'after-backup'").fetchone()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
