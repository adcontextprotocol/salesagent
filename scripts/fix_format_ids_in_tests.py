#!/usr/bin/env python3
"""Script to convert string format_ids to FormatId objects in tests.

This script automatically converts test files from using:
    format_ids=["display_300x250"]
to:
    format_ids=[make_format_id("display_300x250")]
"""

import re
from pathlib import Path

DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"

# Helper function template to add to files
HELPER_FUNCTION = '''
# Default agent URL for creating FormatId objects
DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"


def make_format_id(format_id: str) -> FormatId:
    """Helper to create FormatId objects with default agent URL."""
    return FormatId(agent_url=DEFAULT_AGENT_URL, id=format_id)

'''


def needs_formatid_import(content: str) -> bool:
    """Check if file needs FormatId import."""
    return "format_ids=" in content and "FormatId" not in content


def add_formatid_import(content: str) -> str:
    """Add FormatId to imports."""
    # Find the import line for schemas
    import_pattern = r"from src\.core\.schemas import (.*?)$"
    match = re.search(import_pattern, content, re.MULTILINE)

    if match:
        imports = match.group(1)
        if "FormatId" not in imports:
            # Add FormatId to imports
            new_imports = imports.rstrip() + ", FormatId"
            content = re.sub(
                import_pattern, f"from src.core.schemas import {new_imports}", content, count=1, flags=re.MULTILINE
            )

    return content


def add_helper_function(content: str) -> str:
    """Add helper function after imports."""
    if "make_format_id" not in content:
        # Find the last import line
        import_end = 0
        for match in re.finditer(r"^(from |import )", content, re.MULTILINE):
            import_end = match.end()

        # Find the next non-empty line
        next_line_match = re.search(r"\n\n", content[import_end:])
        if next_line_match:
            insert_pos = import_end + next_line_match.end()
            content = content[:insert_pos] + HELPER_FUNCTION + content[insert_pos:]

    return content


def convert_format_ids(content: str) -> str:
    """Convert string format_ids to FormatId objects."""
    # Pattern 1: format_ids=["single"]
    content = re.sub(r'format_ids=\["([^"]+)"\]', r'format_ids=[make_format_id("\1")]', content)

    # Pattern 2: format_ids=["multi", "ple"]
    def replace_multi(match):
        ids = re.findall(r'"([^"]+)"', match.group(0))
        converted = ", ".join([f'make_format_id("{id}")' for id in ids])
        return f"format_ids=[{converted}]"

    content = re.sub(r'format_ids=\["[^"]+",\s*"[^"]+"[^\]]*\]', replace_multi, content)

    # Pattern 3: output_format_ids=["..."]
    content = re.sub(r'output_format_ids=\["([^"]+)"\]', r'output_format_ids=[make_format_id("\1")]', content)

    def replace_output_multi(match):
        ids = re.findall(r'"([^"]+)"', match.group(0))
        converted = ", ".join([f'make_format_id("{id}")' for id in ids])
        return f"output_format_ids=[{converted}]"

    content = re.sub(r'output_format_ids=\["[^"]+",\s*"[^"]+"[^\]]*\]', replace_output_multi, content)

    return content


def process_file(filepath: Path) -> bool:
    """Process a single test file. Returns True if modified."""
    content = filepath.read_text()
    original_content = content

    # Check if file needs processing
    if not needs_formatid_import(content):
        return False

    print(f"Processing: {filepath}")

    # Add FormatId import
    content = add_formatid_import(content)

    # Add helper function
    content = add_helper_function(content)

    # Convert format_ids usage
    content = convert_format_ids(content)

    if content != original_content:
        filepath.write_text(content)
        print(f"  ✓ Fixed {filepath}")
        return True

    return False


def main():
    """Process all test files."""
    test_dirs = [
        Path("tests/unit"),
        Path("tests/integration"),
        Path("tests/manual"),
    ]

    total_fixed = 0

    for test_dir in test_dirs:
        if not test_dir.exists():
            continue

        for filepath in test_dir.rglob("*.py"):
            if process_file(filepath):
                total_fixed += 1

    print(f"\n✓ Fixed {total_fixed} test files")


if __name__ == "__main__":
    main()
