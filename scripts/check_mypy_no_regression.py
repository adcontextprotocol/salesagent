#!/usr/bin/env python3
"""
Check that mypy error count doesn't increase (no regression).

This is much faster than checking individual files (~3 seconds vs 2+ minutes).
Approach: Run mypy on entire codebase, ensure error count <= baseline.

Usage:
    python scripts/check_mypy_no_regression.py
    python scripts/check_mypy_no_regression.py --update-baseline
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

BASELINE_FILE = Path(".mypy_baseline")
BASELINE_ERRORS = 0  # ENFORCED: 100% mypy compliance (as of 2025-10-28)


def get_current_error_count() -> tuple[int, str]:
    """Run mypy on entire codebase and return error count."""
    try:
        result = subprocess.run(
            ["uv", "run", "mypy", "src/", "--config-file=mypy.ini"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Parse "Found X errors in Y files"
        output = result.stdout + result.stderr
        match = re.search(r"Found (\d+) errors? in \d+ files?", output)

        if match:
            return int(match.group(1)), output

        # No errors found
        if "Success: no issues found" in output:
            return 0, output

        # Couldn't parse
        print("⚠️  Warning: Could not parse mypy output")
        return -1, output

    except subprocess.TimeoutExpired:
        print("❌ mypy timed out after 30 seconds")
        return -1, ""
    except Exception as e:
        print(f"❌ Error running mypy: {e}")
        return -1, ""


def get_baseline() -> int:
    """Get baseline error count from file or default."""
    if BASELINE_FILE.exists():
        try:
            return int(BASELINE_FILE.read_text().strip())
        except ValueError:
            pass
    return BASELINE_ERRORS


def update_baseline(count: int) -> None:
    """Update baseline file with new error count."""
    BASELINE_FILE.write_text(f"{count}\n")
    print(f"✅ Updated baseline to {count} errors")


def main():
    parser = argparse.ArgumentParser(description="Check that mypy error count doesn't increase")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Update baseline with current error count",
    )
    args = parser.parse_args()

    print("🔍 Checking mypy error count (no regression)...\n")

    current_count, output = get_current_error_count()

    if current_count == -1:
        print("❌ Failed to run mypy")
        return 1

    baseline = get_baseline()

    print(f"Current errors: {current_count}")
    print(f"Baseline:       {baseline}")
    print()

    if args.update_baseline:
        update_baseline(current_count)
        return 0

    if current_count > baseline:
        print(f"❌ mypy error count INCREASED by {current_count - baseline}")
        print("\nYou introduced new mypy errors. Please fix them or update existing code.")
        print("\nTo see errors: uv run mypy src/ --config-file=mypy.ini")
        return 1
    elif current_count < baseline:
        improvement = baseline - current_count
        print(f"✅ mypy error count DECREASED by {improvement}! 🎉")
        print("\nConsider updating baseline: python scripts/check_mypy_no_regression.py --update-baseline")
        return 0
    else:
        print("✅ mypy error count unchanged (no regression)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
