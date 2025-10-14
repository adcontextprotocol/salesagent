#!/usr/bin/env python3
"""Find implicit Optional patterns that need fixing.

This script identifies function signatures with implicit Optional
(e.g., `arg: Type = None`) that should be `arg: Type | None = None`.

Does NOT modify files - just reports findings for manual review.
"""

import re
from pathlib import Path


def check_file(file_path: Path) -> list[dict]:
    """Find implicit Optional in a file."""
    content = file_path.read_text()
    issues = []

    # Pattern: parameter: Type = None
    # Should be: parameter: Type | None = None
    pattern = r"(\w+): ([A-Z]\w+(?:\[.*?\])?)\s*=\s*None"

    for match in re.finditer(pattern, content):
        param_name, type_name = match.groups()

        # Skip if already has | None
        context = content[max(0, match.start() - 20) : match.end() + 20]
        if "| None" in context or "|None" in context:
            continue

        # Get line number
        line_num = content[: match.start()].count("\n") + 1

        # Get the full line for context
        lines = content.split("\n")
        if line_num <= len(lines):
            full_line = lines[line_num - 1].strip()

            issues.append(
                {
                    "file": str(file_path),
                    "line": line_num,
                    "param": param_name,
                    "type": type_name,
                    "context": full_line,
                }
            )

    return issues


def main():
    print("=" * 80)
    print("Implicit Optional Pattern Finder")
    print("=" * 80)
    print()

    all_issues = []
    for file_path in Path("src").rglob("*.py"):
        issues = check_file(file_path)
        all_issues.extend(issues)

    if not all_issues:
        print("✓ No implicit Optional patterns found!")
        return

    print(f"Found {len(all_issues)} implicit Optional patterns:\n")

    # Group by file
    by_file = {}
    for issue in all_issues:
        file = issue["file"]
        if file not in by_file:
            by_file[file] = []
        by_file[file].append(issue)

    for file_path, issues in sorted(by_file.items()):
        print(f"\n{file_path}:")
        for issue in issues:
            print(f"  Line {issue['line']}: {issue['param']}: {issue['type']} = None")
            print(f"    Fix: {issue['param']}: {issue['type']} | None = None")
            print(f"    Context: {issue['context'][:70]}...")

    print("\n" + "=" * 80)
    print(f"Total: {len(all_issues)} implicit Optional patterns")
    print("=" * 80)
    print("\nTo fix, use pattern: parameter: Type | None = None")
    print("Or run: uv add --dev no-implicit-optional")
    print("Then: no-implicit-optional src/")


if __name__ == "__main__":
    main()
