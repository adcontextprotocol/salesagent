#!/usr/bin/env python3
"""
Audit E2E tests for quality issues:
1. Tests calling non-existent tools
2. Tests marked skip_ci (candidates for deletion)
3. Redundant tests
4. Tests with excessive tool calls
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

# Import the authoritative tool lists from contract validation
sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.e2e.conftest_contract_validation import ACTUAL_MCP_TOOLS, INTENTIONAL_NONEXISTENT_TOOLS

# Use the same lists as runtime contract validation
ACTUAL_TOOLS = ACTUAL_MCP_TOOLS
ALLOWED_NONEXISTENT_TOOLS = INTENTIONAL_NONEXISTENT_TOOLS


def find_non_existent_tool_calls(test_dir: Path) -> dict[str, list[tuple]]:
    """Find tests calling tools that don't exist (excluding intentionally allowed nonexistent tools)."""
    issues = defaultdict(list)

    for test_file in test_dir.glob("test_*.py"):
        with open(test_file) as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            # Find call_tool("tool_name") or call_mcp_tool("tool_name")
            match = re.search(r'call(?:_mcp)?_tool\(["\'](\w+)["\']', line)
            if match:
                tool_name = match.group(1)
                # Skip if tool exists OR is intentionally allowed for error handling tests
                if tool_name not in ACTUAL_TOOLS and tool_name not in ALLOWED_NONEXISTENT_TOOLS:
                    # Find the test function this is in
                    test_func = None
                    for j in range(i - 1, -1, -1):
                        func_match = re.match(r"\s*(?:async\s+)?def\s+(test_\w+)", lines[j])
                        if func_match:
                            test_func = func_match.group(1)
                            break

                    issues[test_file.name].append((i, tool_name, test_func))

    return issues


def find_skip_ci_tests(test_dir: Path) -> dict[str, list[tuple]]:
    """Find tests marked with skip_ci."""
    issues = defaultdict(list)

    for test_file in test_dir.glob("test_*.py"):
        with open(test_file) as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            if "@pytest.mark.skip_ci" in line:
                # Find the test function
                for j in range(i, min(i + 5, len(lines))):
                    func_match = re.match(r"\s*(?:async\s+)?def\s+(test_\w+)", lines[j])
                    if func_match:
                        test_func = func_match.group(1)
                        # Extract reason if present
                        reason = re.search(r'reason=["\']([^"\']+)["\']', line)
                        reason_text = reason.group(1) if reason else "No reason given"
                        issues[test_file.name].append((i, test_func, reason_text))
                        break

    return issues


def find_large_tests(test_dir: Path, threshold: int = 200) -> dict[str, list[tuple]]:
    """Find overly large test functions (candidates for splitting)."""
    issues = defaultdict(list)

    for test_file in test_dir.glob("test_*.py"):
        with open(test_file) as f:
            lines = f.readlines()

        in_test = False
        test_name = None
        test_start = 0
        test_lines = 0

        for i, line in enumerate(lines, 1):
            func_match = re.match(r"\s*(?:async\s+)?def\s+(test_\w+)", line)
            if func_match:
                # Save previous test if it was large
                if in_test and test_lines > threshold:
                    issues[test_file.name].append((test_start, test_name, test_lines))

                # Start new test
                in_test = True
                test_name = func_match.group(1)
                test_start = i
                test_lines = 0
            elif in_test:
                # Check if we've left the function (dedent or new function)
                if line and not line[0].isspace() and line.strip():
                    if test_lines > threshold:
                        issues[test_file.name].append((test_start, test_name, test_lines))
                    in_test = False
                else:
                    test_lines += 1

    return issues


def main():
    test_dir = Path(__file__).parent.parent / "tests" / "e2e"

    print("=" * 80)
    print("E2E TEST AUDIT")
    print("=" * 80)
    print()

    # 1. Non-existent tool calls
    print("1. TESTS CALLING NON-EXISTENT TOOLS")
    print("-" * 80)
    non_existent = find_non_existent_tool_calls(test_dir)
    if non_existent:
        print("❌ These tests call tools that don't exist:\n")
        for file, calls in sorted(non_existent.items()):
            print(f"📄 {file}:")
            for line_no, tool, test_func in calls:
                print(f"   Line {line_no}: {test_func}() calls '{tool}'")
            print()
        print("🔧 ACTION: Delete these tests or mark them @pytest.mark.skip_ci")
    else:
        print("✅ No tests calling non-existent tools")
    print()

    # 2. Skip CI tests
    print("2. TESTS MARKED skip_ci (CANDIDATES FOR DELETION)")
    print("-" * 80)
    skip_ci = find_skip_ci_tests(test_dir)
    if skip_ci:
        print("⚠️  These tests are skipped in CI:\n")
        for file, tests in sorted(skip_ci.items()):
            print(f"📄 {file}:")
            for line_no, test_func, reason in tests:
                print(f"   Line {line_no}: {test_func}()")
                print(f"              Reason: {reason}")
            print()
        print("🔧 ACTION: If features won't be implemented soon, DELETE these tests")
    else:
        print("✅ No tests marked skip_ci")
    print()

    # 3. Large tests
    print("3. OVERLY LARGE TESTS (>200 LINES)")
    print("-" * 80)
    large = find_large_tests(test_dir)
    if large:
        print("📏 These tests are very large:\n")
        for file, tests in sorted(large.items()):
            print(f"📄 {file}:")
            for line_no, test_func, size in tests:
                print(f"   Line {line_no}: {test_func}() - {size} lines")
            print()
        print("🔧 ACTION: Consider splitting into smaller, focused tests")
    else:
        print("✅ No overly large tests")
    print()

    # Summary
    total_issues = sum(len(v) for v in non_existent.values())
    total_skip = sum(len(v) for v in skip_ci.values())
    total_large = sum(len(v) for v in large.values())

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Non-existent tool calls: {total_issues}")
    print(f"Tests marked skip_ci:    {total_skip}")
    print(f"Overly large tests:      {total_large}")
    print()

    if total_issues > 0 or total_skip > 0:
        print("⚠️  ACTION REQUIRED: Clean up E2E tests")
        return 1
    else:
        print("✅ E2E tests are clean!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
