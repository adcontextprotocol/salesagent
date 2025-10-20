#!/usr/bin/env python
"""Check for database locks."""
from sqlalchemy import text

from src.core.database.database_session import get_db_session

with get_db_session() as session:
    # Check for active queries and locks
    query = text(
        """
        SELECT
            pid,
            usename,
            application_name,
            state,
            query_start,
            state_change,
            wait_event_type,
            wait_event,
            LEFT(query, 100) as query_preview
        FROM pg_stat_activity
        WHERE state != 'idle'
        AND query NOT LIKE '%pg_stat_activity%'
        ORDER BY query_start;
    """
    )

    results = session.execute(query).fetchall()

    if not results:
        print("No active queries or locks")
    else:
        print("\nActive database connections:")
        print("-" * 120)
        for row in results:
            print(f"PID: {row.pid} | User: {row.usename} | App: {row.application_name}")
            print(f"  State: {row.state} | Started: {row.query_start}")
            print(f"  Wait: {row.wait_event_type}/{row.wait_event}")
            print(f"  Query: {row.query_preview}...")
            print()
