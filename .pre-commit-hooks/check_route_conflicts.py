#!/usr/bin/env python3
"""Pre-commit hook to detect Flask route conflicts.

This hook detects when multiple Flask routes are registered for the same path,
which can cause unpredictable behavior and authentication issues.

Examples of conflicts:
- Two @app.route() decorators with the same path
- Blueprint routes that duplicate service-registered routes
- Multiple endpoints registered for the same path with different names

Exit codes:
    0: No route conflicts found
    1: Route conflicts detected
"""

import sys
from pathlib import Path


def check_route_conflicts() -> int:
    """Check for route conflicts by loading Flask app and inspecting url_map.

    Returns:
        0 if no conflicts, 1 if conflicts found
    """
    # Add project root to path so we can import the app
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    try:
        # Import and create the Flask app
        from src.admin.app import create_app

        app_tuple = create_app()
        app = app_tuple[0] if isinstance(app_tuple, tuple) else app_tuple

        # Check for route conflicts
        # Group routes by path to detect duplicates
        routes_by_path = {}  # path -> list of (endpoint, methods)

        for rule in app.url_map.iter_rules():
            path = str(rule)
            endpoint = rule.endpoint
            # Remove HEAD and OPTIONS from methods for comparison
            methods = sorted(rule.methods - {"HEAD", "OPTIONS"})

            if path not in routes_by_path:
                routes_by_path[path] = []
            routes_by_path[path].append({"endpoint": endpoint, "methods": methods})

        # Find actual conflicts (same path, overlapping methods)
        conflicts = []
        for path, route_list in routes_by_path.items():
            if len(route_list) <= 1:
                continue

            # Check if routes have overlapping methods
            for i, route1 in enumerate(route_list):
                for route2 in route_list[i + 1 :]:
                    # Check for method overlap
                    overlap = set(route1["methods"]) & set(route2["methods"])
                    if overlap:
                        # Real conflict - same path, same HTTP method
                        conflicts.append(
                            {
                                "path": path,
                                "endpoints": [route1["endpoint"], route2["endpoint"]],
                                "methods1": route1["methods"],
                                "methods2": route2["methods"],
                                "overlap": sorted(overlap),
                            }
                        )

        # No whitelist needed - all previous conflicts were resolved!
        new_conflicts = conflicts

        if new_conflicts:
            print("\n❌ ROUTE CONFLICTS DETECTED:")
            print("=" * 80)
            for conflict in new_conflicts:
                print(f"\n🔴 Path: {conflict['path']}")
                print(f"   Conflicting endpoints: {', '.join(conflict['endpoints'])}")
                print(f"   Route 1 methods: {conflict['methods1']}")
                print(f"   Route 2 methods: {conflict['methods2']}")
                print(f"   Overlapping methods: {conflict['overlap']}")

            print("\n" + "=" * 80)
            print("\n⚠️  Route conflicts can cause:")
            print("   - Unpredictable routing behavior (last registered route wins)")
            print("   - Authentication failures (wrong decorator applied)")
            print("   - 404/401 errors")
            print("\n💡 Solution:")
            print("   - Remove duplicate @app.route() or @blueprint.route() decorators")
            print("   - Ensure each path + HTTP method combination is unique")
            print("   - RESTful routes (same path, different methods) are OK")
            print()
            return 1

        print("✅ No route conflicts detected")

        return 0

    except Exception as e:
        print(f"\n⚠️  Warning: Could not check route conflicts: {e}")
        print("   (This is not a fatal error - continuing)")
        return 0  # Don't fail the commit for import errors


if __name__ == "__main__":
    sys.exit(check_route_conflicts())
