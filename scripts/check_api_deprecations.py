#!/usr/bin/env python3
"""
Check for usage of deprecated external API methods.
"""
import ast
import os
import sys

# Deprecated API methods and their replacements
DEPRECATED_APIS = {
    "new_filter_statement": {
        "replacement": "StatementBuilder",
        "module": "googleads.ad_manager",
        "example": 'statement_builder = ad_manager.StatementBuilder(version="v202411")',
        "deprecated_in": "googleads v24.0.0",
    },
    "GetDataDownloader": {
        "note": "Deprecated but still works in googleads==46.0.0",
        "check_context": True,
        "allow_with_comment": True,  # Allow if there's a TODO comment
    },
    # Add more deprecated APIs as they're discovered
}


def find_deprecated_calls(tree: ast.AST, filename: str) -> list[tuple[str, int, str]]:
    """Find calls to deprecated API methods."""
    issues = []

    for node in ast.walk(tree):
        # Check attribute access (e.g., client.new_filter_statement())
        if isinstance(node, ast.Attribute):
            if node.attr in DEPRECATED_APIS:
                line_no = getattr(node, "lineno", 0)
                issues.append((node.attr, line_no, "attribute"))

        # Check method calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                if method_name in DEPRECATED_APIS:
                    line_no = getattr(node, "lineno", 0)
                    issues.append((method_name, line_no, "call"))

    return issues


def check_file(filepath: str) -> list[str]:
    """Check a single file for deprecated API usage."""
    issues = []

    try:
        with open(filepath) as f:
            content = f.read()

        # Quick check if file might contain deprecated APIs
        has_potential_issues = any(api in content for api in DEPRECATED_APIS.keys())
        if not has_potential_issues:
            return []

        lines = content.split("\n")
        tree = ast.parse(content)
        deprecated_calls = find_deprecated_calls(tree, filepath)

        for api_name, line_no, usage_type in deprecated_calls:
            api_info = DEPRECATED_APIS[api_name]

            # Check if there's a TODO comment near this usage
            if api_info.get("allow_with_comment", False) and line_no > 0:
                # Check previous 3 lines for TODO comment
                has_todo = False
                for i in range(max(0, line_no - 4), min(line_no, len(lines))):
                    if "TODO" in lines[i]:
                        has_todo = True
                        break
                if has_todo:
                    continue  # Skip this issue if there's a TODO

            issue_msg = f"{filepath}:{line_no}: Deprecated API '{api_name}'"

            if "replacement" in api_info:
                issue_msg += f"\n    Replace with: {api_info['replacement']}"
            if "example" in api_info:
                issue_msg += f"\n    Example: {api_info['example']}"
            if "deprecated_in" in api_info:
                issue_msg += f"\n    Deprecated in: {api_info['deprecated_in']}"
            if "note" in api_info:
                issue_msg += f"\n    Note: {api_info['note']}"

            issues.append(issue_msg)

    except Exception:
        # Skip files that can't be parsed
        pass

    return issues


def check_requirements():
    """Check requirements.txt for version pinning."""
    issues = []
    requirements_files = ["requirements.txt", "pyproject.toml"]

    for req_file in requirements_files:
        if os.path.exists(req_file):
            with open(req_file) as f:
                content = f.read()

            # Check for unpinned dependencies that have deprecated APIs
            if "googleads" in content and "==" not in content.split("googleads")[1].split("\n")[0]:
                issues.append(
                    f"{req_file}: 'googleads' library should be version pinned to avoid "
                    f"unexpected API deprecations\n    Example: googleads==24.1.0"
                )

    return issues


def main():
    """Check for deprecated API usage."""
    all_issues = []

    # Check Python files in adapters directory
    for root, dirs, files in os.walk("adapters"):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                issues = check_file(filepath)
                all_issues.extend(issues)

    # Check other relevant directories
    other_dirs = ["services", "."]
    for dir_name in other_dirs:
        if os.path.exists(dir_name):
            for file in os.listdir(dir_name):
                if file.endswith(".py") and file not in ["check_api_deprecations.py"]:
                    filepath = os.path.join(dir_name, file)
                    if os.path.isfile(filepath):
                        issues = check_file(filepath)
                        all_issues.extend(issues)

    # Check requirements
    req_issues = check_requirements()
    all_issues.extend(req_issues)

    if all_issues:
        print("Found usage of deprecated APIs:")
        for issue in all_issues:
            print(f"\n{issue}")
        print(f"\n\nTotal issues: {len(all_issues)}")
        print("\nPlease update to use the recommended replacements.")
        sys.exit(1)
    else:
        print("✓ No deprecated API usage found")
        sys.exit(0)


if __name__ == "__main__":
    main()
