#!/usr/bin/env python3
"""
Script to remove Scope3 dependencies from the codebase.

This script replaces hardcoded scope3.com domains with domain configuration
utility functions or environment variables, making the codebase vendor-neutral.
"""

import re
from pathlib import Path


def update_file_with_domain_config(filepath: Path) -> tuple[bool, list[str]]:
    """
    Update a single file to use domain_config utilities instead of hardcoded domains.

    Returns:
        (changed, changes_made): Whether file was modified and list of changes
    """
    try:
        content = filepath.read_text()
        original_content = content
        changes = []

        # Skip if file already imports domain_config
        has_domain_config_import = "from src.core.domain_config import" in content

        # Pattern 1: Simple string replacements (URLs, comments, etc.)
        replacements = {
            "sales-agent.scope3.com": "${SALES_AGENT_DOMAIN}",
            "admin.sales-agent.scope3.com": "${ADMIN_DOMAIN}",
            ".sales-agent.scope3.com": ".{get_sales_agent_domain()}",
            "https://scope3.com": "https://example.com",  # Generic docs reference
            "scope3.com": "${SUPER_ADMIN_DOMAIN}",  # For email domain checks
        }

        # Track which patterns we replaced
        for old, new in replacements.items():
            if old in content:
                # Special handling for different contexts
                if ".sales-agent.scope3.com" in content and filepath.suffix == ".py":
                    # Python files: Use domain_config functions
                    if not has_domain_config_import:
                        # Add import if needed
                        if "from src.core" in content:
                            # Find a good place to insert import
                            import_pattern = r"(from src\.core\.[\w\.]+ import [^\n]+\n)"
                            last_import = None
                            for match in re.finditer(import_pattern, content):
                                last_import = match

                            if last_import:
                                insert_pos = last_import.end()
                                domain_import = "from src.core.domain_config import get_sales_agent_domain, extract_subdomain_from_host, is_sales_agent_domain\n"
                                content = content[:insert_pos] + domain_import + content[insert_pos:]
                                changes.append("Added domain_config import")
                                has_domain_config_import = True

                # For Python files with domain checks
                if filepath.suffix == ".py" and has_domain_config_import:
                    # Replace domain checking patterns
                    content = re.sub(
                        r'\.endswith\(["\']\.sales-agent\.scope3\.com["\']\)',
                        '.endswith(f".{get_sales_agent_domain()}")',
                        content,
                    )
                    content = re.sub(
                        r'\.split\(["\']\.sales-agent\.scope3\.com["\']\)',
                        '.split(f".{get_sales_agent_domain()}")',
                        content,
                    )
                    content = re.sub(
                        r'["\']\ssales-agent\.scope3\.com["\']\sin\s', ' f".{get_sales_agent_domain()}" in ', content
                    )
                elif old in content:
                    count = content.count(old)
                    content = content.replace(old, new)
                    changes.append(f"Replaced {count} occurrence(s) of {old}")

        # Pattern 2: Super admin domain checks
        if "scope3.com" in content and filepath.suffix == ".py":
            # Update scope3.com email checks
            content = re.sub(
                r'email_domain\s*==\s*["\']scope3\.com["\']', "email_domain == get_super_admin_domain()", content
            )
            content = re.sub(
                r'["\']scope3\.com["\']\s*==\s*email_domain', "get_super_admin_domain() == email_domain", content
            )

        # Write back if changed
        if content != original_content:
            filepath.write_text(content)
            return True, changes

        return False, []

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False, []


def main():
    """Main script execution."""
    # Get the project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    print("Removing Scope3 dependencies from codebase...")
    print(f"Project root: {project_root}\n")

    # Directories to process
    dirs_to_process = [
        project_root / "src",
        project_root / "tests",
        project_root / "templates",
        project_root / "static",
    ]

    # File extensions to process
    extensions = {".py", ".js", ".html", ".md", ".toml", ".conf", ".sh"}

    total_files = 0
    changed_files = 0

    for directory in dirs_to_process:
        if not directory.exists():
            continue

        print(f"Processing {directory}...")

        for filepath in directory.rglob("*"):
            if filepath.suffix not in extensions:
                continue

            if filepath.is_file():
                total_files += 1
                changed, changes = update_file_with_domain_config(filepath)

                if changed:
                    changed_files += 1
                    print(f"  ✓ {filepath.relative_to(project_root)}")
                    for change in changes:
                        print(f"    - {change}")

    print("\nSummary:")
    print(f"  Total files scanned: {total_files}")
    print(f"  Files modified: {changed_files}")
    print("\nNext steps:")
    print("  1. Review the changes: git diff")
    print("  2. Update environment variables in .env.secrets")
    print("  3. Run tests: ./run_all_tests.sh quick")
    print("  4. Commit changes: git commit -m 'Remove Scope3 dependencies'")


if __name__ == "__main__":
    main()
