#!/usr/bin/env python3
"""
Sync version from package.json to pyproject.toml.

This script is automatically run by the `npm run version` command
after changesets updates the version in package.json.
"""

import json
import re
import sys
from pathlib import Path


def sync_version():
    """Read version from package.json and update pyproject.toml."""
    root_dir = Path(__file__).parent.parent

    # Read version from package.json
    package_json_path = root_dir / "package.json"
    if not package_json_path.exists():
        print("❌ package.json not found")
        sys.exit(1)

    with open(package_json_path) as f:
        package_data = json.load(f)

    version = package_data.get("version")
    if not version:
        print("❌ No version found in package.json")
        sys.exit(1)

    print(f"📦 Version from package.json: {version}")

    # Update pyproject.toml
    pyproject_path = root_dir / "pyproject.toml"
    if not pyproject_path.exists():
        print("❌ pyproject.toml not found")
        sys.exit(1)

    with open(pyproject_path) as f:
        content = f.read()

    # Replace version in [project] section
    # Match: version = "x.y.z"
    pattern = r'(^\[project\].*?^version\s*=\s*")[^"]+(")'
    replacement = rf"\g<1>{version}\g<2>"

    new_content, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE | re.DOTALL)

    if count == 0:
        print("❌ Could not find version field in pyproject.toml")
        sys.exit(1)

    with open(pyproject_path, "w") as f:
        f.write(new_content)

    print(f"✅ Updated pyproject.toml to version {version}")


if __name__ == "__main__":
    sync_version()
