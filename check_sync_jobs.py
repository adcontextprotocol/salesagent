#!/usr/bin/env python
"""Check sync jobs for a tenant."""
import sys

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import SyncJob

tenant_id = sys.argv[1] if len(sys.argv) > 1 else "accuweather"

with get_db_session() as session:
    stmt = select(SyncJob).filter_by(tenant_id=tenant_id).order_by(SyncJob.started_at.desc()).limit(10)
    jobs = session.scalars(stmt).all()

    if not jobs:
        print(f"No sync jobs found for tenant: {tenant_id}")
    else:
        print(f"Recent sync jobs for {tenant_id}:")
        print("-" * 100)
        for job in jobs:
            error_msg = job.error_message[:50] if job.error_message else "none"
            print(
                f"{job.sync_id:<30} | {job.status:<10} | {job.sync_type:<10} | {str(job.started_at):<20} | {error_msg}"
            )
