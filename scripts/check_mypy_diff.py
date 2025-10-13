#!/usr/bin/env python3
"""
Check mypy errors only on lines changed in the current branch.

Usage:
    python scripts/check_mypy_diff.py
    python scripts/check_mypy_diff.py --base main
    python scripts/check_mypy_diff.py --files src/core/schemas.py src/core/main.py
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_changed_files(base_branch: str = "main") -> list[str]:
    """Get list of Python files changed compared to base branch."""
    try:
        result = subprocess.run(
            ["git", "diff", base_branch, "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py") and Path(f).exists()]
        return files
    except subprocess.CalledProcessError:
        print("❌ Error getting changed files from git")
        return []


def get_changed_line_ranges(file: str, base_branch: str = "main") -> list[tuple[int, int]]:
    """Get ranges of lines changed in the file (start_line, end_line)."""
    try:
        result = subprocess.run(
            ["git", "diff", base_branch, file],
            capture_output=True,
            text=True,
            check=True,
        )

        ranges = []
        for line in result.stdout.split("\n"):
            if line.startswith("@@"):
                # Parse @@ -10,5 +12,8 @@ format
                # We want the +12,8 part (new file line numbers)
                try:
                    parts = line.split("+")[1].split(" ")[0].split(",")
                    start = int(parts[0])
                    count = int(parts[1]) if len(parts) > 1 else 1
                    ranges.append((start, start + count))
                except (IndexError, ValueError):
                    continue

        return ranges
    except subprocess.CalledProcessError:
        return []


def get_mypy_errors(file: str) -> dict[int, str]:
    """Run mypy on file and return errors by line number."""
    try:
        result = subprocess.run(
            ["uv", "run", "mypy", file, "--config-file=mypy.ini"],
            capture_output=True,
            text=True,
        )

        errors = {}
        for line in result.stdout.split("\n") + result.stderr.split("\n"):
            if line.startswith(f"{file}:"):
                try:
                    # Parse "file.py:123: error: message"
                    parts = line.split(":", 3)
                    line_num = int(parts[1])
                    error_msg = ":".join(parts[2:])
                    errors[line_num] = error_msg
                except (IndexError, ValueError):
                    continue

        return errors
    except subprocess.CalledProcessError:
        return {}


def is_line_in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    """Check if line number falls within any of the changed ranges."""
    for start, end in ranges:
        if start <= line < end:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Check mypy errors only on changed lines")
    parser.add_argument("--base", default="main", help="Base branch to compare against")
    parser.add_argument("--files", nargs="*", help="Specific files to check (optional)")
    args = parser.parse_args()

    print(f"🔍 Checking mypy for lines changed compared to {args.base}...\n")

    # Get files to check
    if args.files:
        files = [f for f in args.files if f.endswith(".py") and Path(f).exists()]
    else:
        files = get_changed_files(args.base)

    if not files:
        print("✅ No Python files to check")
        return 0

    total_errors = 0
    files_with_errors = []

    for file in files:
        print(f"Checking {file}...")

        # Get changed line ranges
        changed_ranges = get_changed_line_ranges(file, args.base)
        if not changed_ranges:
            print(f"  No changes detected in {file}")
            continue

        # Get mypy errors
        errors = get_mypy_errors(file)
        if not errors:
            print("  ✅ No mypy errors")
            continue

        # Filter to only errors in changed lines
        changed_errors = {line: msg for line, msg in errors.items() if is_line_in_ranges(line, changed_ranges)}

        if changed_errors:
            print(f"  ❌ Found {len(changed_errors)} error(s) in changed lines:")
            for line, msg in sorted(changed_errors.items()):
                print(f"    Line {line}: {msg}")
            total_errors += len(changed_errors)
            files_with_errors.append(file)
        else:
            print(f"  ✅ No mypy errors in changed lines (but {len(errors)} total in file)")

    print()
    if total_errors > 0:
        print(f"❌ Found {total_errors} mypy error(s) in changed lines across {len(files_with_errors)} file(s)")
        print("\nFiles with errors:")
        for f in files_with_errors:
            print(f"  - {f}")
        return 1
    else:
        print(f"✅ No mypy errors in changed lines across {len(files)} file(s)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
