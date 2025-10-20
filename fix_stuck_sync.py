#!/usr/bin/env python
"""Fix stuck sync job."""
from datetime import UTC, datetime

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import SyncJob

sync_id = "sync_accuweather_1760907201"

with get_db_session() as session:
    stmt = select(SyncJob).filter_by(sync_id=sync_id)
    job = session.scalars(stmt).first()

    if not job:
        print(f"Sync job {sync_id} not found")
    else:
        print(f"Found sync job: {job.sync_id}")
        print(f"  Current status: {job.status}")
        print(f"  Started: {job.started_at}")
        print("  Updating to 'failed'...")

        job.status = "failed"
        job.completed_at = datetime.now(UTC)
        job.error_message = "Sync thread died (stuck for 19+ hours) - manually marked as failed"
        session.commit()

        print("  ✅ Updated to failed status")
