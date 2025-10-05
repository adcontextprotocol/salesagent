#!/usr/bin/env python3
"""
Smart over-mocking detection for tests.

Distinguishes between:
- GOOD: Mocking external I/O (auth, database, API calls, adapters)
- BAD: Mocking internal implementation (_impl functions, handlers)

Exit codes:
- 0: All tests follow proper mocking patterns
- 1: Found over-mocking violations
"""

import re
import sys
from pathlib import Path

# Patterns for ALLOWED external mocks (infrastructure/I/O)
ALLOWED_PATTERNS = [
    r"get_principal_from_token",  # Auth lookup
    r"get_current_tenant",  # Tenant resolution
    r"get_adapter",  # Adapter factory
    r"get_audit_logger",  # Logging
    r"get_db_session",  # Database session
    r"@patch.*\.adapter",  # Any adapter mock
    r"@patch.*requests\.",  # HTTP calls
    r"@patch.*boto3\.",  # AWS calls
    r"@patch.*Session",  # DB sessions
]

# Patterns for DISALLOWED internal mocks (implementation details)
DISALLOWED_PATTERNS = [
    r"_impl\b",  # Shared implementation functions
    r"_handle_\w+_skill",  # A2A skill handlers
    r"_handle_get_products",  # Specific handlers
    r"_handle_create_media_buy",  # Specific handlers
]


def check_file(filepath: Path) -> tuple[bool, list[str]]:
    """
    Check a test file for over-mocking violations.

    Returns:
        (is_valid, violations) tuple
    """
    content = filepath.read_text()
    violations = []

    # Check for disallowed patterns
    for pattern in DISALLOWED_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            # Get line numbers for better error messages (excluding comments)
            lines = content.split("\n")
            line_nums = []
            for i, line in enumerate(lines):
                # Skip comment lines
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # Skip inline comments after code
                code_part = line.split("#")[0]
                if re.search(pattern, code_part):
                    line_nums.append(i + 1)

            if line_nums:  # Only add violation if found in actual code
                violations.append(
                    f"  ❌ Mocking internal implementation: {pattern} " f"(lines: {', '.join(map(str, line_nums))})"
                )

    return len(violations) == 0, violations


def main():
    """Check all test files for over-mocking."""
    test_dir = Path("tests")
    if not test_dir.exists():
        print("✅ No tests directory found")
        return 0

    all_violations = []
    checked_files = 0

    # Check all test files
    for test_file in test_dir.rglob("test_*.py"):
        checked_files += 1
        is_valid, violations = check_file(test_file)

        if not is_valid:
            all_violations.append((test_file, violations))

    # Report results
    if all_violations:
        print("❌ Found over-mocking violations:\n")
        for filepath, violations in all_violations:
            print(f"📄 {filepath}:")
            for violation in violations:
                print(violation)
            print()

        print("💡 Fix by mocking only external I/O (auth, database, adapters),")
        print("   not internal implementation (_impl functions, handlers).\n")
        return 1

    print(f"✅ Checked {checked_files} test files - all follow proper mocking patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
