from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import database_path, init_database


BACKUP_PREFIX = "hearthline-"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def verify_database(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Database file does not exist: {path}")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        result = db.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError(f"Database integrity check failed: {result}")
        migrations = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if migrations is None:
            raise RuntimeError("Database does not contain the schema_migrations table")


def create_backup(output_dir: Path, retention: int = 14) -> Path:
    if retention < 1:
        raise ValueError("retention must be at least 1")
    init_database()
    source_path = database_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{BACKUP_PREFIX}{_timestamp()}.db"

    with tempfile.NamedTemporaryFile(
        prefix=".hearthline-backup-",
        suffix=".db",
        dir=output_dir,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with sqlite3.connect(source_path) as source, sqlite3.connect(temporary_path) as target:
            source.backup(target)
        verify_database(temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    backups = sorted(
        output_dir.glob(f"{BACKUP_PREFIX}*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for expired in backups[retention:]:
        expired.unlink()
    return destination


def restore_backup(backup_path: Path, *, confirm_replace: bool) -> Path:
    if not confirm_replace:
        raise ValueError("restore requires --confirm-replace")
    verify_database(backup_path)
    target = database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    safety_backup = target.with_name(f"{target.stem}.pre-restore-{_timestamp()}{target.suffix}")

    if target.exists():
        with sqlite3.connect(target) as source, sqlite3.connect(safety_backup) as safety:
            source.backup(safety)
        verify_database(safety_backup)

    with tempfile.NamedTemporaryFile(
        prefix=".hearthline-restore-",
        suffix=".db",
        dir=target.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with sqlite3.connect(backup_path) as source, sqlite3.connect(temporary_path) as restored:
            source.backup(restored)
        verify_database(temporary_path)
        os.replace(temporary_path, target)
        target.with_name(f"{target.name}-wal").unlink(missing_ok=True)
        target.with_name(f"{target.name}-shm").unlink(missing_ok=True)
    finally:
        temporary_path.unlink(missing_ok=True)
    return safety_backup


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create, verify, or restore Hearthline SQLite backups")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("--output-dir", type=Path)
    create.add_argument("--retention", type=int, default=14)

    verify = commands.add_parser("verify")
    verify.add_argument("backup", type=Path)

    restore = commands.add_parser("restore")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--confirm-replace", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "create":
        output_dir = args.output_dir or database_path().parent / "backups"
        backup = create_backup(output_dir, retention=args.retention)
        print(f"Created and verified backup: {backup}")
    elif args.command == "verify":
        verify_database(args.backup)
        print(f"Backup is valid: {args.backup}")
    else:
        safety_backup = restore_backup(
            args.backup,
            confirm_replace=args.confirm_replace,
        )
        print(f"Restore completed; previous database backup: {safety_backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
