#!/usr/bin/env python3
"""
Reset database migrations on Fly.io to fix migration conflicts.
This script will:
1. Connect to the Fly.io PostgreSQL database
2. Drop the alembic_version table (migration history)
3. Re-run all migrations from scratch
"""

import os
import sys
from urllib.parse import urlparse

import psycopg2


def get_fly_database_url():
    """Get the Fly.io database URL from environment or secrets."""
    # Try to get from environment
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        # Try to fetch from Fly secrets
        import subprocess

        try:
            result = subprocess.run(["fly", "secrets", "list"], capture_output=True, text=True, check=True)
            if "DATABASE_URL" in result.stdout:
                # Get the actual secret value
                result = subprocess.run(
                    ["fly", "ssh", "console", "-C", "printenv DATABASE_URL"], capture_output=True, text=True, check=True
                )
                db_url = result.stdout.strip()
        except:
            pass

    if not db_url:
        print("❌ Could not find DATABASE_URL")
        print("\nTo get your Fly.io database URL, run:")
        print("  fly ssh console -C 'printenv DATABASE_URL'")
        print("\nThen set it as an environment variable:")
        print("  export DATABASE_URL='<your-database-url>'")
        sys.exit(1)

    return db_url


def reset_migrations(db_url):
    """Reset the alembic migrations table."""

    # Parse the database URL
    parsed = urlparse(db_url)

    print(f"🔄 Connecting to database at {parsed.hostname}...")

    try:
        # Connect to the database
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        # Check if alembic_version table exists
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'alembic_version'
            );
        """
        )
        exists = cursor.fetchone()[0]

        if exists:
            print("📦 Found alembic_version table")

            # Show current migration state
            cursor.execute("SELECT version_num FROM alembic_version;")
            versions = cursor.fetchall()
            if versions:
                print(f"  Current migration: {versions[0][0]}")

            # Drop the alembic_version table
            print("🗑️  Dropping alembic_version table...")
            cursor.execute("DROP TABLE alembic_version;")
            conn.commit()
            print("✅ Migration history cleared")
        else:
            print("ℹ️  No alembic_version table found (fresh database)")

        # Also check for any orphaned migration references
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'alembic%';
        """
        )
        orphaned = cursor.fetchall()

        if orphaned:
            print(f"⚠️  Found orphaned migration tables: {orphaned}")
            for table in orphaned:
                cursor.execute(f"DROP TABLE {table[0]};")
            conn.commit()
            print("✅ Cleaned up orphaned migration tables")

        # Close the connection
        cursor.close()
        conn.close()

        print("\n✅ Migration reset complete!")
        print("\nNext steps:")
        print("1. Deploy your app to run fresh migrations:")
        print("   fly deploy --remote-only")
        print("\n2. Or manually run migrations:")
        print("   fly ssh console -C 'python migrate.py'")

    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("Fly.io Migration Reset Tool")
    print("=" * 60)

    # Get the database URL
    db_url = get_fly_database_url()

    # Confirm before proceeding
    print("\n⚠️  WARNING: This will reset all migration history!")
    print("   Your data will NOT be deleted, but migrations will be re-run.")
    response = input("\nContinue? (yes/no): ")

    if response.lower() != "yes":
        print("❌ Aborted")
        sys.exit(0)

    # Reset the migrations
    reset_migrations(db_url)


if __name__ == "__main__":
    main()
