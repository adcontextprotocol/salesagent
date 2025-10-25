#!/usr/bin/env python3
"""
Refresh AdCP Schemas from Official Source

This script:
1. Deletes ALL cached schemas (clean slate)
2. Downloads fresh schemas from https://adcontextprotocol.org
3. Verifies no outdated references (like budget.json) remain
4. Reports what was downloaded

Usage:
    python scripts/refresh_adcp_schemas.py [--version v1]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.e2e.adcp_schema_validator import preload_schemas


async def refresh_schemas(adcp_version: str = "v1", dry_run: bool = False):
    """
    Refresh AdCP schemas by cleaning cache and downloading fresh versions.

    Args:
        adcp_version: AdCP version to download (e.g., "v1")
        dry_run: If True, show what would be deleted without actually deleting
    """
    # Determine cache directory (schemas moved to project root in #614)
    project_root = Path(__file__).parent.parent
    cache_dir = project_root / "schemas" / adcp_version

    print("🔍 AdCP Schema Refresh Tool")
    print(f"Version: {adcp_version}")
    print(f"Cache directory: {cache_dir}")
    print()

    # Step 1: Clean up existing cache (both .json and .meta files)
    if cache_dir.exists():
        cached_files = list(cache_dir.glob("*.json"))
        meta_files = list(cache_dir.glob("*.meta"))
        total_files = len(cached_files) + len(meta_files)

        print(f"📂 Found {len(cached_files)} cached schema files and {len(meta_files)} metadata files")

        if cached_files or meta_files:
            print(f"\n{'🔍 Would delete' if dry_run else '🗑️  Deleting'} old files:")

            # Delete schema files
            for schema_file in sorted(cached_files):
                print(f"  - {schema_file.name}")
                if not dry_run:
                    schema_file.unlink()

            # Delete metadata files
            for meta_file in sorted(meta_files):
                print(f"  - {meta_file.name} (metadata)")
                if not dry_run:
                    meta_file.unlink()

            if not dry_run:
                print(
                    f"\n✅ Deleted {total_files} old files ({len(cached_files)} schemas + {len(meta_files)} metadata)"
                )
        else:
            print("✨ No cached files found (clean slate)")
    else:
        print("✨ Cache directory doesn't exist yet (clean slate)")
        if not dry_run:
            cache_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print("\n🔍 DRY RUN - no changes made")
        print("Run without --dry-run to actually refresh schemas")
        return

    # Step 2: Download fresh schemas
    print("\n📥 Downloading fresh schemas from https://adcontextprotocol.org...")
    print()

    try:
        await preload_schemas(load_all=True, adcp_version=adcp_version)
    except Exception as e:
        print(f"\n❌ Error downloading schemas: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 3: Verify results
    print("\n🔍 Verifying downloaded schemas...")
    new_cached_files = list(cache_dir.glob("*.json"))
    print(f"✅ Successfully cached {len(new_cached_files)} schemas")

    # Check for problematic files
    print("\n🔍 Checking for outdated schema references...")
    budget_json_files = [f for f in new_cached_files if "budget_json" in f.name]

    if budget_json_files:
        print(f"⚠️  WARNING: Found {len(budget_json_files)} budget.json references:")
        for f in budget_json_files:
            print(f"  - {f.name}")
        print("\n💡 These files should NOT exist per AdCP spec (budgets are plain numbers)")
        print("   The official spec may have changed or there's a bug in the schema download")
    else:
        print("✅ No budget.json references found (correct per AdCP spec)")

    # Show summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Cache directory: {cache_dir}")
    print(f"Total schemas: {len(new_cached_files)}")
    print(f"Schema version: {adcp_version}")
    print()
    print("✅ Schema refresh completed successfully!")
    print()
    print("Next steps:")
    print("1. Run tests to verify schemas work correctly")
    print("2. Commit updated schema cache to git")
    print("3. Update any code that assumed budget object format")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Refresh AdCP schemas from official source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be deleted
  python scripts/refresh_adcp_schemas.py --dry-run

  # Actually refresh schemas (default v1)
  python scripts/refresh_adcp_schemas.py

  # Refresh specific version
  python scripts/refresh_adcp_schemas.py --version v2
        """,
    )

    parser.add_argument("--version", default="v1", help="AdCP version to download (default: v1)")

    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")

    args = parser.parse_args()

    # Run async refresh
    asyncio.run(refresh_schemas(adcp_version=args.version, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
