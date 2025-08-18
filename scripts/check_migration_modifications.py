#!/usr/bin/env python3
"""
Pre-commit hook to prevent modification of existing migration files.

This script checks if any existing Alembic migration files have been modified
and fails if they have, enforcing the rule that migrations are immutable once
committed.
"""

import subprocess
import sys


def get_modified_files():
    """Get list of modified files in the current commit."""
    try:
        # Get list of files that are staged for commit
        result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, check=True)
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def get_migration_files_in_history():
    """Get list of migration files that exist in git history."""
    try:
        # Get all migration files that have been committed before
        result = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD", "--name-only"], capture_output=True, text=True, check=True
        )
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        # Filter for alembic migration files
        return [f for f in files if f.startswith("alembic/versions/") and f.endswith(".py")]
    except subprocess.CalledProcessError:
        return []


def check_migration_modifications():
    """Check if any existing migration files have been modified."""
    modified_files = get_modified_files()
    existing_migrations = get_migration_files_in_history()

    # Find migrations that are both modified and already exist in history
    modified_migrations = []
    for file in modified_files:
        if file in existing_migrations:
            # Check if it's actually modified (not just added)
            try:
                result = subprocess.run(
                    ["git", "diff", "--cached", "HEAD", "--", file], capture_output=True, text=True, check=True
                )
                if result.stdout.strip():  # If there's a diff, it's modified
                    modified_migrations.append(file)
            except subprocess.CalledProcessError:
                pass

    if modified_migrations:
        print("\n" + "=" * 70)
        print("❌ ERROR: Existing migration files cannot be modified!")
        print("=" * 70)
        print("\nThe following migration files have been modified:")
        for file in modified_migrations:
            print(f"  - {file}")

        print("\n⚠️  MIGRATION MODIFICATION RULES:")
        print("1. Once a migration is committed, it becomes IMMUTABLE")
        print("2. Modifying migrations can cause database inconsistencies")
        print("3. Instead, create a NEW migration to fix any issues")
        print("\nTo fix this:")
        print("1. Revert changes to the existing migration(s):")
        for file in modified_migrations:
            print(f"   git checkout HEAD -- {file}")
        print("2. Create a new migration file to address any issues:")
        print("   Create alembic/versions/XXX_fix_description.py")
        print("\nFor more info, see CLAUDE.md section 'Database Migration Best Practices'")
        print("=" * 70 + "\n")
        return 1

    # Check for new migrations - these are OK
    new_migrations = [
        f
        for f in modified_files
        if f.startswith("alembic/versions/") and f.endswith(".py") and f not in existing_migrations
    ]

    if new_migrations:
        print("✅ New migration files detected (this is OK):")
        for file in new_migrations:
            print(f"  - {file}")

    return 0


if __name__ == "__main__":
    sys.exit(check_migration_modifications())
