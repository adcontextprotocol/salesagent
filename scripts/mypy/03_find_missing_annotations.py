#!/usr/bin/env python3
"""Find variables that need type annotations.

Parses mypy output to find all "Need type annotation" errors
and provides specific fix suggestions.
"""

import re
import subprocess
from collections import defaultdict


def run_mypy() -> str:
    """Run mypy and capture output."""
    result = subprocess.run(
        ["uv", "run", "mypy", "src/", "--config-file=mypy.ini"],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def parse_annotation_errors(output: str) -> list[dict]:
    """Parse 'Need type annotation' errors from mypy output."""
    errors = []

    for line in output.split("\n"):
        if "Need type annotation" in line:
            # Format: file.py:123: error: Need type annotation for "var" (hint: "var: list[<type>] = ...") [var-annotated]
            match = re.match(
                r'^(.*?):(\d+): error: Need type annotation for "(\w+)"(?:\s*\(hint: "(.*?)"\))?',
                line,
            )
            if match:
                file_path, line_num, var_name, hint = match.groups()
                errors.append(
                    {
                        "file": file_path,
                        "line": int(line_num),
                        "var": var_name,
                        "hint": hint,
                    }
                )

    return errors


def main():
    print("=" * 80)
    print("Missing Type Annotations Finder")
    print("=" * 80)
    print("\nRunning mypy...\n")

    output = run_mypy()
    errors = parse_annotation_errors(output)

    if not errors:
        print("✓ No missing type annotation errors found!")
        return

    print(f"Found {len(errors)} variables needing type annotations:\n")

    # Group by file
    by_file = defaultdict(list)
    for error in errors:
        by_file[error["file"]].append(error)

    for file_path, file_errors in sorted(by_file.items()):
        print(f"\n{file_path}:")
        for error in file_errors:
            print(f"  Line {error['line']}: {error['var']}")
            if error["hint"]:
                print(f"    Hint: {error['hint']}")
            print()

    print("=" * 80)
    print(f"Total: {len(errors)} variables need type annotations")
    print("=" * 80)
    print("\nCommon patterns:")
    print("  empty_list = []           → empty_list: list[str] = []")
    print("  result_dict = {}          → result_dict: dict[str, Any] = {}")
    print("  issues = []               → issues: list[ValidationIssue] = []")
    print("  targeting = {}            → targeting: dict[str, Any] = {}")


if __name__ == "__main__":
    main()
