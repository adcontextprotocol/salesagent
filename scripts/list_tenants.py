#!/usr/bin/env python3
"""List all tenants in the database."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant

with get_db_session() as session:
    tenants = session.scalars(select(Tenant)).all()
    print(f"Found {len(tenants)} tenants:")
    for t in tenants:
        auth_method = t.adapter_config.gam_auth_method if t.adapter_config else "N/A"
        print(f"  - {t.name} (ID: {t.tenant_id}, auth: {auth_method})")
