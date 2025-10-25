#!/usr/bin/env python3
"""
Script to refactor main.py:
1. Add tool imports from new modules
2. Remove tool implementations that have been moved
3. Keep helper functions, health endpoints, and other infrastructure
"""

import re
from pathlib import Path

# Functions to remove (will be imported from tool modules)
FUNCTIONS_TO_REMOVE = [
    # Helper functions that moved to tool modules
    "_get_principal_id_from_context",
    "_verify_principal",
    "log_tool_activity",
    "_require_admin",
    "_validate_pricing_model_selection",
    "_validate_and_convert_format_ids",
    # Tool implementations
    "_get_products_impl",
    "get_products",
    "_list_creative_formats_impl",
    "list_creative_formats",
    "_sync_creatives_impl",
    "sync_creatives",
    "_list_creatives_impl",
    "list_creatives",
    "get_signals",
    "activate_signal",
    "_list_authorized_properties_impl",
    "list_authorized_properties",
    "_create_media_buy_impl",
    "create_media_buy",
    "_update_media_buy_impl",
    "update_media_buy",
    "_get_media_buy_delivery_impl",
    "get_media_buy_delivery",
    "_update_performance_index_impl",
    "update_performance_index",
]

# Tool imports to add
TOOL_IMPORTS = """
# Import MCP tools from separate modules
from src.core.tools.products import get_products
from src.core.tools.creative_formats import list_creative_formats
from src.core.tools.creatives import sync_creatives, list_creatives
from src.core.tools.signals import get_signals, activate_signal
from src.core.tools.properties import list_authorized_properties
from src.core.tools.media_buy_create import create_media_buy
from src.core.tools.media_buy_update import update_media_buy
from src.core.tools.media_buy_delivery import get_media_buy_delivery
from src.core.tools.performance import update_performance_index
"""


def find_function_ranges(content: str) -> dict[str, tuple[int, int]]:
    """Find line ranges for all functions in the file."""
    lines = content.split("\n")
    function_ranges = {}

    # Pattern to match function definitions
    func_pattern = re.compile(r"^(async\s+)?def\s+(\w+)\s*\(")

    current_func = None
    current_start = None
    indent_level = None

    for i, line in enumerate(lines):
        match = func_pattern.match(line)

        if match:
            # Save previous function if exists
            if current_func and current_start is not None:
                function_ranges[current_func] = (current_start, i - 1)

            # Start new function
            current_func = match.group(2)
            current_start = i
            indent_level = len(line) - len(line.lstrip())

        elif current_func and line.strip() and not line.strip().startswith("#"):
            # Check if we're back at the same indent level (new function/class)
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= indent_level and not line[indent_level:].startswith(" "):
                # This is a new top-level item, save previous function
                function_ranges[current_func] = (current_start, i - 1)
                current_func = None
                current_start = None

    # Save last function
    if current_func and current_start is not None:
        function_ranges[current_func] = (current_start, len(lines) - 1)

    return function_ranges


def refactor_main_py(main_path: Path):
    """Refactor main.py by removing tool implementations and adding imports."""

    print(f"Reading {main_path}...")
    content = main_path.read_text()
    original_lines = content.split("\n")
    original_line_count = len(original_lines)

    print(f"Original line count: {original_line_count}")

    # Find function ranges
    print("Finding function ranges...")
    function_ranges = find_function_ranges(content)

    # Identify lines to remove
    lines_to_remove = set()
    for func_name in FUNCTIONS_TO_REMOVE:
        if func_name in function_ranges:
            start, end = function_ranges[func_name]
            print(f"  Marking {func_name} for removal (lines {start+1}-{end+1})")
            for line_num in range(start, end + 1):
                lines_to_remove.add(line_num)
        else:
            print(f"  Warning: {func_name} not found in file")

    # Build new content
    print("Building new content...")
    new_lines = []

    # Find where to insert tool imports (after helper imports, before logger)
    insert_point = None
    for i, line in enumerate(original_lines):
        if "from src.core.helpers.workflow_helpers import" in line:
            # Find end of this import block
            j = i + 1
            while j < len(original_lines) and (
                original_lines[j].strip().endswith(",") or original_lines[j].strip().endswith(")")
            ):
                j += 1
            insert_point = j + 1
            break

    if insert_point is None:
        print("Warning: Could not find import insertion point, using line 59")
        insert_point = 59

    print(f"Will insert tool imports at line {insert_point + 1}")

    # Build new file
    imports_added = False
    for i, line in enumerate(original_lines):
        # Skip lines marked for removal
        if i in lines_to_remove:
            continue

        # Insert tool imports at the right place
        if i == insert_point and not imports_added:
            new_lines.append(TOOL_IMPORTS.strip())
            new_lines.append("")
            imports_added = True

        new_lines.append(line)

    # Write new content
    new_content = "\n".join(new_lines)
    new_line_count = len(new_lines)
    lines_removed = original_line_count - new_line_count

    print("\nSummary:")
    print(f"  Original lines: {original_line_count}")
    print(f"  New lines: {new_line_count}")
    print(f"  Lines removed: {lines_removed}")
    print(f"  Functions removed: {len([f for f in FUNCTIONS_TO_REMOVE if f in function_ranges])}")

    # Backup original
    backup_path = main_path.with_suffix(".py.backup")
    print(f"\nBacking up original to {backup_path}...")
    backup_path.write_text(content)

    # Write new content
    print(f"Writing refactored content to {main_path}...")
    main_path.write_text(new_content)

    print("\n✅ Refactoring complete!")
    return lines_removed, new_line_count


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    main_path = repo_root / "src" / "core" / "main.py"

    if not main_path.exists():
        print(f"Error: {main_path} not found!")
        exit(1)

    lines_removed, new_line_count = refactor_main_py(main_path)

    print("\nNext steps:")
    print("1. Verify imports: python -c 'from src.core.main import mcp'")
    print("2. Run tests: uv run pytest tests/unit/ -x")
    print("3. Check diff: git diff src/core/main.py")
