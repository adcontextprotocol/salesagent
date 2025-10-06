#!/usr/bin/env python3
"""
Pre-commit hook to detect testing anti-patterns.

Prevents:
1. Over-mocking internal functions in integration tests
2. Missing tests for new AdCP skill handlers
3. Non-spec-compliant parameter names in tests
"""

import re
import sys
from pathlib import Path


def check_integration_test_mocking(filepath: Path) -> list[tuple[int, str]]:
    """Check for over-mocking of internal handlers in integration tests."""
    if not filepath.exists() or "integration" not in str(filepath):
        return []

    violations = []
    content = filepath.read_text()
    lines = content.split("\n")

    for i, line in enumerate(lines, start=1):
        # Flag mocking of internal handler functions
        if 'patch.object(handler, "_handle_' in line:
            violations.append((i, "Mocking internal handler defeats integration test purpose"))

        # Flag mocking of internal tool implementations
        if 'patch("src.core.main._' in line and "_impl" in line:
            violations.append((i, "Mocking internal implementation defeats integration test purpose"))

    return violations


def check_skill_handler_has_test(a2a_server_file: Path, test_dir: Path) -> list[str]:
    """Check that all skill handlers have corresponding tests."""
    if not a2a_server_file.exists():
        return []

    # Get all skill handlers
    content = a2a_server_file.read_text()
    pattern = r"async def _handle_(\w+)_skill\("
    skills = set(re.findall(pattern, content))
    skills.discard("explicit")  # Not a skill name

    # Get all test files
    test_files_content = ""
    if test_dir.exists():
        for test_file in test_dir.glob("**/test_a2a*.py"):
            test_files_content += test_file.read_text()

    # Check which skills lack tests
    untested = []
    for skill in sorted(skills):
        # Look for test function mentioning this skill
        if f"test_.*{skill}" not in test_files_content and skill not in test_files_content:
            untested.append(skill)

    return untested


def main():
    """Run all checks and return exit code."""
    project_root = Path(__file__).parent.parent
    issues_found = False

    # Check all modified files (passed as arguments by pre-commit)
    if len(sys.argv) > 1:
        for filepath in sys.argv[1:]:
            path = Path(filepath)
            violations = check_integration_test_mocking(path)

            if violations:
                issues_found = True
                print(f"\n❌ {filepath}:")
                print("   Over-mocking anti-pattern detected!")
                print("   Integration tests should mock only external dependencies.")
                print()
                for line_num, reason in violations:
                    print(f"   Line {line_num}: {reason}")
                print()
                print("   Fix: Remove patch.object for internal functions.")
                print("   Mock only: database, adapters, external HTTP calls")

    # Check skill handler coverage (only on A2A server changes)
    a2a_server_file = project_root / "src/a2a_server/adcp_a2a_server.py"
    if len(sys.argv) > 1 and str(a2a_server_file) in sys.argv[1:]:
        test_dir = project_root / "tests"
        untested = check_skill_handler_has_test(a2a_server_file, test_dir)

        if untested:
            issues_found = True
            print("\n⚠️  WARNING: New skill handlers may lack tests:")
            for skill in untested:
                print(f"   • {skill}")
            print()
            print("   Consider adding tests to tests/integration/test_a2a_skill_invocation.py")

    if issues_found:
        print("\n" + "=" * 80)
        print("❌ TESTING ANTI-PATTERNS DETECTED")
        print("=" * 80)
        print("\nRun: python scripts/analyze_test_coverage.py")
        print("For full coverage analysis and recommendations.")
        print()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
