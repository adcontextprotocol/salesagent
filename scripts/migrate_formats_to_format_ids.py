#!/usr/bin/env python3
"""Automated migration script for formats → format_ids.

This script updates code references from .formats to .format_ids across the codebase.

Usage:
    python scripts/migrate_formats_to_format_ids.py --dry-run   # Preview changes
    python scripts/migrate_formats_to_format_ids.py --apply     # Apply changes
"""

import re
import sys
from pathlib import Path


def migrate_file(file_path: Path, dry_run: bool = True) -> tuple[bool, list[str]]:
    """Migrate a single file from .formats to .format_ids.

    Returns:
        (changed, changes): Tuple of whether file was changed and list of changes made
    """
    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        return False, []

    original = content
    changes = []

    # Pattern 1: .formats → .format_ids
    pattern1 = r"\.formats(\s|$|,|\)|\]|:)"
    matches1 = re.findall(pattern1, content)
    if matches1:
        content = re.sub(pattern1, r".format_ids\1", content)
        changes.append(f"  - Replaced .formats → .format_ids ({len(matches1)} occurrences)")

    # Pattern 2: effective_formats → effective_format_ids
    pattern2 = r"\.effective_formats(\s|$|,|\)|\]|:)"
    matches2 = re.findall(pattern2, content)
    if matches2:
        content = re.sub(pattern2, r".effective_format_ids\1", content)
        changes.append(f"  - Replaced .effective_formats → .effective_format_ids ({len(matches2)} occurrences)")

    # Pattern 3: auto_approve_formats → auto_approve_format_ids
    pattern3 = r"\.auto_approve_formats(\s|$|,|\)|\]|:)"
    matches3 = re.findall(pattern3, content)
    if matches3:
        content = re.sub(pattern3, r".auto_approve_format_ids\1", content)
        changes.append(f"  - Replaced .auto_approve_formats → .auto_approve_format_ids ({len(matches3)} occurrences)")

    # Pattern 4: Remove floor_cpm references (if simple access pattern)
    pattern4 = r"product\.floor_cpm"
    matches4 = re.findall(pattern4, content)
    if matches4:
        changes.append(f"  ⚠️  Found {len(matches4)} .floor_cpm references (needs manual review)")

    # Pattern 5: Remove recommended_cpm references (if simple access pattern)
    pattern5 = r"product\.recommended_cpm"
    matches5 = re.findall(pattern5, content)
    if matches5:
        changes.append(f"  ⚠️  Found {len(matches5)} .recommended_cpm references (needs manual review)")

    if content != original:
        if not dry_run:
            file_path.write_text(content)
        return True, changes

    return False, changes


def main():
    dry_run = "--apply" not in sys.argv
    mode = "[DRY RUN]" if dry_run else "[APPLYING]"

    print(f"\n{mode} Migrating formats → format_ids\n")
    print("=" * 60)

    # Directories to process
    dirs_to_process = [
        Path("src"),
        Path("tests"),
    ]

    files_changed = 0
    total_changes = []

    for directory in dirs_to_process:
        if not directory.exists():
            continue

        for file_path in directory.rglob("*.py"):
            # Skip __pycache__ and migration files
            if "__pycache__" in str(file_path) or "alembic/versions" in str(file_path):
                continue

            changed, changes = migrate_file(file_path, dry_run=dry_run)

            if changed:
                files_changed += 1
                print(f"\n{mode} {file_path}")
                for change in changes:
                    print(change)
                total_changes.extend(changes)

    print("\n" + "=" * 60)
    print(f"{mode} Summary:")
    print(f"  - Files modified: {files_changed}")
    print(f"  - Total changes: {len(total_changes)}")

    if dry_run:
        print("\n💡 Run with --apply to make changes")
    else:
        print("\n✅ Changes applied successfully!")

    # Exit with error code if there are warnings
    warnings = [c for c in total_changes if "⚠️" in c]
    if warnings:
        print(f"\n⚠️  {len(warnings)} files need manual review for deprecated fields")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
