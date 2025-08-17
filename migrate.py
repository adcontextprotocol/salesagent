#!/usr/bin/env python3
"""Run database migrations using Alembic."""

import sys
import os
from pathlib import Path
from alembic.config import Config
from alembic import command

def run_migrations(exit_on_error=True):
    """Run all pending database migrations.
    
    Args:
        exit_on_error: If True, exit the process on error. If False, raise exception.
    """
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    
    # Path to alembic.ini
    alembic_ini_path = script_dir / "alembic.ini"
    
    # Create Alembic configuration
    alembic_cfg = Config(str(alembic_ini_path))
    
    # Run migrations
    try:
        print("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        print("✅ Database migrations completed successfully!")
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        if exit_on_error:
            sys.exit(1)
        else:
            raise

def check_migration_status():
    """Check current migration status."""
    script_dir = Path(__file__).parent
    alembic_ini_path = script_dir / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    
    try:
        print("Checking migration status...")
        command.current(alembic_cfg)
    except Exception as e:
        print(f"Error checking status: {e}")

def create_migration(message: str):
    """Create a new migration."""
    script_dir = Path(__file__).parent
    alembic_ini_path = script_dir / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    
    try:
        print(f"Creating migration: {message}")
        command.revision(alembic_cfg, message=message, autogenerate=True)
        print("✅ Migration created successfully!")
    except Exception as e:
        print(f"❌ Error creating migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            check_migration_status()
        elif sys.argv[1] == "create" and len(sys.argv) > 2:
            create_migration(" ".join(sys.argv[2:]))
        elif sys.argv[1] == "upgrade":
            run_migrations()
        else:
            print("""Usage:
    python migrate.py               # Run all pending migrations
    python migrate.py upgrade       # Run all pending migrations
    python migrate.py status        # Check current migration status
    python migrate.py create <msg>  # Create a new migration
            """)
    else:
        # Default action is to run migrations
        run_migrations()