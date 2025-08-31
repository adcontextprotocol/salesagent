#!/usr/bin/env python3
"""
Emergency migration fix script for production
Run this if Alembic migrations are stuck in production
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlalchemy as sa

from src.core.database.database_session import get_db_session


def fix_migration_state():
    """Reset production alembic version to correct state"""
    print("🔧 Emergency migration fix for production...")

    with get_db_session() as session:
        try:
            # Check current state
            result = session.execute(sa.text("SELECT version_num FROM alembic_version;"))
            current = result.fetchone()
            print(f"Current version: {current[0] if current else 'None'}")

            # If we're at a broken state, reset to last known good
            if current and current[0] in ["019_fix_tasks_table_schema", "020_fix_tasks_schema_properly"]:
                print("🎯 Detected problematic migration state - resetting...")
                session.execute(sa.text("DELETE FROM alembic_version;"))
                session.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('13a4e417ebb5');"))
                session.commit()
                print("✅ Reset to 13a4e417ebb5 (last known good)")

                # Try to upgrade to head
                print("🚀 Now run: alembic upgrade head")
            else:
                print("📋 Migration state appears correct")

        except Exception as e:
            print(f"❌ Error: {e}")
            return False

    return True


if __name__ == "__main__":
    success = fix_migration_state()
    sys.exit(0 if success else 1)
