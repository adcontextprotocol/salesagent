#!/usr/bin/env python
"""Check how much inventory data we have in database."""
from sqlalchemy import func, select

from src.core.database.database_session import get_db_session
from src.core.database.models import GAMInventory

tenant_id = "accuweather"

with get_db_session() as session:
    # Count by inventory type
    stmt = (
        select(GAMInventory.inventory_type, func.count())
        .filter_by(tenant_id=tenant_id)
        .group_by(GAMInventory.inventory_type)
    )
    results = session.execute(stmt).all()

    print(f"\nInventory counts for {tenant_id}:")
    print("-" * 50)
    total = 0
    for inv_type, count in results:
        print(f"  {inv_type:<25} {count:>10,}")
        total += count
    print("-" * 50)
    print(f"  {'TOTAL':<25} {total:>10,}")
