#!/usr/bin/env python
"""Script to help migrate routes from admin_ui.py to blueprints."""

import re
from pathlib import Path


def analyze_routes():
    """Analyze routes in admin_ui.py and categorize them."""
    admin_ui_path = Path("admin_ui.py")
    content = admin_ui_path.read_text()

    # Find all routes
    route_pattern = r'@app\.route\("([^"]+)".*?\)\n(.*?)\ndef (\w+)'
    routes = re.findall(route_pattern, content, re.MULTILINE | re.DOTALL)

    # Categorize routes
    categories = {
        "auth": [],
        "tenant": [],
        "products": [],
        "api": [],
        "gam": [],
        "settings": [],
        "operations": [],
        "other": [],
    }

    for route, _decorators, func_name in routes:
        if "/auth/" in route or "/login" in route or "/logout" in route:
            categories["auth"].append((route, func_name))
        elif "/products" in route:
            categories["products"].append((route, func_name))
        elif "/api/" in route:
            categories["api"].append((route, func_name))
        elif "/gam/" in route or "gam_" in func_name:
            categories["gam"].append((route, func_name))
        elif "/settings" in route:
            categories["settings"].append((route, func_name))
        elif "/tenant/" in route:
            categories["tenant"].append((route, func_name))
        elif "/operations" in route or "dashboard" in func_name:
            categories["operations"].append((route, func_name))
        else:
            categories["other"].append((route, func_name))

    return categories


def check_blueprint_implementation(blueprint_name, func_names):
    """Check if functions are implemented in blueprint."""
    blueprint_path = Path(f"src/admin/blueprints/{blueprint_name}.py")
    if not blueprint_path.exists():
        return []

    content = blueprint_path.read_text()
    implemented = []
    for func_name in func_names:
        if f"def {func_name}" in content:
            implemented.append(func_name)
    return implemented


def main():
    """Main function."""
    print("Analyzing routes in admin_ui.py...\n")
    categories = analyze_routes()

    # Check which routes are already commented out
    admin_ui_content = Path("admin_ui.py").read_text()

    for category, routes in categories.items():
        if not routes:
            continue

        print(f"\n{category.upper()} Routes ({len(routes)}):")
        print("=" * 50)

        for route, func_name in routes:
            # Check if already commented
            is_commented = f'# @app.route("{route}' in admin_ui_content

            # Check if in blueprint
            blueprint_names = {
                "auth": "auth",
                "tenant": "tenants",
                "products": "products",
                "api": "api",
                "gam": "gam",
                "settings": "settings",
                "operations": "operations",
            }

            in_blueprint = False
            if category in blueprint_names:
                implemented = check_blueprint_implementation(blueprint_names[category], [func_name])
                in_blueprint = bool(implemented)

            status = ""
            if is_commented:
                status = "✓ MIGRATED"
            elif in_blueprint:
                status = "⚠️  IN BLUEPRINT (needs commenting)"
            else:
                status = "❌ NOT MIGRATED"

            print(f"  {status:30} {route:50} -> {func_name}")

    # Summary
    print("\n" + "=" * 70)
    total = sum(len(routes) for routes in categories.values())
    commented = sum(
        1
        for cat_routes in categories.values()
        for route, _ in cat_routes
        if f'# @app.route("{route}' in admin_ui_content
    )
    print(f"Total routes: {total}")
    print(f"Migrated: {commented}")
    print(f"Remaining: {total - commented}")


if __name__ == "__main__":
    main()
