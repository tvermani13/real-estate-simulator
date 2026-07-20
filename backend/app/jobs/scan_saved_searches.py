from __future__ import annotations

import asyncio

from app.core.database import connection, init_database
from app.routes.product import scan_search


async def run() -> int:
    init_database()
    with connection() as db:
        rows = db.execute(
            """
            SELECT saved_searches.id AS search_id, users.id, users.name, users.email, users.created_at
            FROM saved_searches
            JOIN users ON users.id = saved_searches.user_id
            WHERE saved_searches.notifications_enabled = 1
            ORDER BY saved_searches.updated_at
            """
        ).fetchall()

    failures = 0
    for row in rows:
        user = {key: row[key] for key in ("id", "name", "email", "created_at")}
        try:
            result = await scan_search(row["search_id"], user)
            print(
                f"{result.search.name}: {result.total_scanned} scanned, "
                f"{result.new_match_count} new matches — {result.notification_status}"
            )
        except Exception as exc:
            failures += 1
            print(f"{row['search_id']}: scan failed — {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
