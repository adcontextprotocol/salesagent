#!/usr/bin/env python
"""Check detailed sync status."""
import json

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import SyncJob

tenant_id = "accuweather"

with get_db_session() as session:
    stmt = select(SyncJob).filter_by(tenant_id=tenant_id, status="running").order_by(SyncJob.started_at.desc())
    running_jobs = session.scalars(stmt).all()

    if not running_jobs:
        print(f"No running sync jobs for {tenant_id}")
    else:
        for job in running_jobs:
            print(f"\nRunning Sync: {job.sync_id}")
            print(f"  Started: {job.started_at}")
            print(f"  Status: {job.status}")
            print(f"  Type: {job.sync_type}")
            if job.progress:
                progress = job.progress if isinstance(job.progress, dict) else json.loads(job.progress)
                print(f"  Progress: {progress}")
            else:
                print("  Progress: No progress data")
