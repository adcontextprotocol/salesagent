#!/usr/bin/env python3
"""
Script to update deprecated AdCP fields in test files.

Changes:
1. promoted_offering → brand_manifest
2. Package.products=[] → Package.product_id=""
3. video_completions → completed_views
"""

import re
from pathlib import Path


def update_file_content(content: str, filepath: str) -> tuple[str, int]:
    """Update deprecated fields in file content. Returns (new_content, num_changes)."""
    changes = 0
    original = content

    # 1. Replace promoted_offering with brand_manifest
    # Simply replace ALL occurrences - promoted_offering → brand_manifest
    if 'promoted_offering' in content:
        count = content.count('promoted_offering')
        content = content.replace('promoted_offering', 'brand_manifest')
        changes += count

    # 2. Replace Package.products=[] with Package.product_id=""
    # This is more complex - need to handle various list patterns
    # products=["prod_1", "prod_2"] → product_id="prod_1" (take first)
    # products=["prod_1"] → product_id="prod_1"
    # products=[...] → product_id="..." (extract first item)

    # Pattern 1: products=["single_item"] → product_id="single_item"
    products_pattern = r'products\s*=\s*\[\s*"([^"]+)"\s*\]'
    matches = re.findall(products_pattern, content)
    if matches:
        changes += len(matches)
        content = re.sub(products_pattern, r'product_id="\1"', content)

    # Pattern 2: products=["first", "second", ...] → product_id="first"
    products_multi_pattern = r'products\s*=\s*\[\s*"([^"]+)"\s*,\s*[^\]]+\]'
    matches = re.findall(products_multi_pattern, content)
    if matches:
        changes += len(matches)
        content = re.sub(products_multi_pattern, r'product_id="\1"', content)

    # Pattern 3: .products → .product_id (attribute access)
    attr_pattern = r'\.products\b'
    if re.search(attr_pattern, content):
        # Count occurrences in lines that look like Package access
        lines_with_products = [line for line in content.split('\n') if '.products' in line]
        # Only replace if it looks like Package access (not other uses of .products)
        for line in lines_with_products:
            if 'package' in line.lower() or 'pkg' in line.lower():
                changes += 1
        content = re.sub(attr_pattern, r'.product_id', content)

    # 3. Replace video_completions with completed_views
    video_completions_patterns = [
        (r'\bvideo_completions\b', r'completed_views'),
        (r'"video_completions"', r'"completed_views"'),
        (r"'video_completions'", r"'completed_views'"),
    ]

    for pattern, replacement in video_completions_patterns:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            changes += len(re.findall(pattern, content))
            content = new_content

    return content, changes


def update_test_files(root_dir: str = "tests"):
    """Update all test files in the given directory."""
    root_path = Path(root_dir)
    if not root_path.exists():
        root_path = Path(__file__).parent.parent / root_dir

    total_files = 0
    total_changes = 0
    updated_files = []

    # Find all Python test files
    for filepath in root_path.rglob("*.py"):
        if filepath.name.startswith("test_") or "test" in filepath.parts:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            new_content, changes = update_file_content(content, str(filepath))

            if changes > 0:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                total_files += 1
                total_changes += changes
                updated_files.append((filepath, changes))
                print(f"Updated {filepath.relative_to(root_path)}: {changes} changes")

    # Also update JSON schema files
    for filepath in root_path.rglob("*.json"):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        new_content, changes = update_file_content(content, str(filepath))

        if changes > 0:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)

            total_files += 1
            total_changes += changes
            updated_files.append((filepath, changes))
            print(f"Updated {filepath.relative_to(root_path)}: {changes} changes")

    print(f"\n{'='*80}")
    print(f"Summary: Updated {total_files} files with {total_changes} total changes")
    print(f"{'='*80}\n")

    if updated_files:
        print("Files updated:")
        for filepath, changes in sorted(updated_files, key=lambda x: -x[1]):
            print(f"  {filepath.name}: {changes} changes")

    return total_files, total_changes


if __name__ == "__main__":
    import sys

    root_dir = sys.argv[1] if len(sys.argv) > 1 else "tests"
    update_test_files(root_dir)
