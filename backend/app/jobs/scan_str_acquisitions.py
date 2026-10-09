"""Run explicitly enabled acquisition searches. Schedule externally; no purchases or alerts."""
from __future__ import annotations

import asyncio
import logging

from app.core.database import connection, init_database
from app.services.str_acquisitions import scan_acquisitions
from app.services.str_forecasts import purge_expired_evidence


async def run() -> int:
    init_database()
    purge_expired_evidence()
    with connection() as db:
        rows = db.execute(
            """SELECT s.id AS search_id,u.id,u.name,u.email,u.created_at FROM str_acquisition_searches s
               JOIN users u ON u.id=s.user_id WHERE s.enabled=1 ORDER BY s.updated_at"""
        ).fetchall()
    failures = 0
    for row in rows:
        user = {key: row[key] for key in ("id", "name", "email", "created_at")}
        try:
            result = await scan_acquisitions(row["search_id"], user)
            qualified = sum(c.rank is not None for c in result.candidates)
            print(f"{row['search_id']}: {result.status}, {len(result.candidates)} candidates, {qualified} qualified")
            failures += int(result.status != "completed")
        except Exception:
            # Do not log licensed payloads or upstream credentials.
            logging.error("Acquisition scan failed for search %s", row["search_id"])
            failures += 1
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
