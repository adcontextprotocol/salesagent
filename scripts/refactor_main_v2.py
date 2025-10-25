#!/usr/bin/env python3
"""
Script to refactor main.py by removing tool implementations.
Uses AST parsing for accurate function detection.
"""

import ast
from pathlib import Path

# Functions to remove (will be imported from tool modules)
FUNCTIONS_TO_REMOVE = {
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
}

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


class FunctionRangeFinder(ast.NodeVisitor):
    """AST visitor to find line ranges of top-level functions."""

    def __init__(self):
        self.function_ranges: dict[str, tuple[int, int]] = {}
        self.current_level = 0

    def visit_FunctionDef(self, node):
        if self.current_level == 0:  # Only top-level functions
            # Store function name and line range
            # AST lines are 1-indexed, we want 0-indexed
            start_line = node.lineno - 1

            # Find decorator start if exists
            if node.decorator_list:
                start_line = node.decorator_list[0].lineno - 1

            # End line is the last line of the function
            end_line = node.end_lineno - 1 if node.end_lineno else start_line

            self.function_ranges[node.name] = (start_line, end_line)

        self.current_level += 1
        self.generic_visit(node)
        self.current_level -= 1

    def visit_AsyncFunctionDef(self, node):
        # Same as visit_FunctionDef
        self.visit_FunctionDef(node)


def find_function_ranges_ast(content: str) -> dict[str, tuple[int, int]]:
    """Use AST to find function ranges accurately."""
    try:
        tree = ast.parse(content)
        finder = FunctionRangeFinder()
        finder.visit(tree)
        return finder.function_ranges
    except SyntaxError as e:
        print(f"Error parsing file: {e}")
        return {}


def refactor_main_py(main_path: Path):
    """Refactor main.py by removing tool implementations and adding imports."""

    print(f"Reading {main_path}...")
    content = main_path.read_text()
    lines = content.split("\n")
    original_line_count = len(lines)

    print(f"Original line count: {original_line_count}")

    # Find function ranges using AST
    print("Finding function ranges using AST...")
    function_ranges = find_function_ranges_ast(content)

    # Identify lines to remove
    lines_to_remove: set[int] = set()
    functions_found = []

    for func_name in sorted(FUNCTIONS_TO_REMOVE):
        if func_name in function_ranges:
            start, end = function_ranges[func_name]
            print(f"  Marking {func_name} for removal (lines {start+1}-{end+1}, {end-start+1} lines)")
            for line_num in range(start, end + 1):
                lines_to_remove.add(line_num)
            functions_found.append(func_name)
        else:
            print(f"  Warning: {func_name} not found in file")

    # Find where to insert tool imports (after workflow_helpers import)
    insert_point = None
    for i, line in enumerate(lines):
        if "from src.core.helpers.workflow_helpers import" in line:
            # Find end of this import block (could be multi-line)
            j = i
            while j < len(lines) and (
                lines[j].strip().endswith(",")
                or lines[j].strip().endswith(")")
                or "from src.core.helpers.workflow_helpers" in lines[j]
            ):
                j += 1
            insert_point = j
            break

    if insert_point is None:
        # Fallback: insert after logger definition
        for i, line in enumerate(lines):
            if line.strip().startswith("logger = logging.getLogger"):
                insert_point = i + 1
                break

    if insert_point is None:
        print("Error: Could not find suitable import insertion point")
        return None, None

    print(f"Will insert tool imports at line {insert_point + 1}")

    # Build new file
    new_lines = []
    imports_added = False
    removed_block_active = False

    for i, line in enumerate(lines):
        # Check if we're entering a removal block
        if i in lines_to_remove:
            if not removed_block_active:
                # Add blank line before removal if previous line wasn't blank
                if new_lines and new_lines[-1].strip():
                    pass  # Don't add extra blank lines
                removed_block_active = True
            continue

        # Check if we just exited a removal block
        if removed_block_active:
            removed_block_active = False
            # Add blank line after removal if next line isn't blank
            if line.strip() and new_lines and new_lines[-1].strip():
                new_lines.append("")

        # Insert tool imports at the right place
        if i == insert_point and not imports_added:
            new_lines.append("")
            new_lines.append(TOOL_IMPORTS.strip())
            imports_added = True

        new_lines.append(line)

    # Remove trailing blank lines
    while new_lines and not new_lines[-1].strip():
        new_lines.pop()

    # Write result
    new_content = "\n".join(new_lines) + "\n"
    new_line_count = len(new_lines)
    lines_removed = original_line_count - new_line_count

    print("\nSummary:")
    print(f"  Original lines: {original_line_count}")
    print(f"  New lines: {new_line_count}")
    print(f"  Lines removed: {lines_removed}")
    print(f"  Functions removed: {len(functions_found)}")

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

    result = refactor_main_py(main_path)

    if result[0] is not None:
        print("\nNext steps:")
        print("1. Verify imports: python -c 'from src.core.main import mcp'")
        print("2. Run tests: uv run pytest tests/unit/ -x")
        print("3. Check diff: git diff src/core/main.py | head -100")
