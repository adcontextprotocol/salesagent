#!/usr/bin/env python3
"""
Cancel the currently running AccuWeather sync.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import SyncJob


def cancel_sync():
    tenant_id = "accuweather"

    with get_db_session() as db:
        # Get the running sync
        stmt = (
            select(SyncJob)
            .where(SyncJob.tenant_id == tenant_id, SyncJob.status == "running")
            .order_by(SyncJob.started_at.desc())
        )
        running_sync = db.scalars(stmt).first()

        if not running_sync:
            print("✅ No sync currently running")
            return

        # Mark as failed
        running_sync.status = "failed"
        running_sync.completed_at = datetime.now(UTC)
        running_sync.error_message = (
            "Manually cancelled - sync was stuck (did not complete placements/labels/custom_targeting)"
        )

        db.commit()

        print(f"✅ Cancelled sync: {running_sync.sync_id}")
        print(f"   Started: {running_sync.started_at}")
        print(f"   Cancelled: {running_sync.completed_at}")
        print("")
        print("Next steps:")
        print("  - Ad units are already synced (48,500 items)")
        print("  - Consider using selective sync to get placements/labels separately")
        print("  - Or investigate GAM API timeout issues")


if __name__ == "__main__":
    cancel_sync()
