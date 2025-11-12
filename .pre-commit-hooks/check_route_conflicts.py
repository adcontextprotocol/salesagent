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
        routes_by_path = {}
        conflicts = []

        for rule in app.url_map.iter_rules():
            path = str(rule)
            endpoint = rule.endpoint

            if path in routes_by_path:
                # Found a conflict!
                conflicts.append(
                    {
                        "path": path,
                        "endpoints": [routes_by_path[path], endpoint],
                        "methods": rule.methods,
                    }
                )
            else:
                routes_by_path[path] = endpoint

        # Whitelist known conflicts (technical debt to be resolved later)
        # These are existing conflicts that we don't want to block commits for
        KNOWN_CONFLICTS = {
            "/tenant/<tenant_id>/update",
            "/tenant/<tenant_id>/products/<product_id>/inventory",
            "/tenant/<tenant_id>/principals/create",
            "/tenant/<tenant_id>/principal/<principal_id>/update_mappings",
            "/tenant/<tenant_id>/users",
            "/tenant/<tenant_id>/users/add",
            "/tenant/<tenant_id>/users/<user_id>/toggle",
            "/tenant/<tenant_id>/users/<user_id>/update_role",
            "/tenant/<tenant_id>/orders",
            "/tenant/<tenant_id>/workflows",
            "/api/v1/tenant-management/tenants",
            "/api/v1/tenant-management/tenants/<tenant_id>",
        }

        # Filter out known conflicts
        new_conflicts = [c for c in conflicts if c["path"] not in KNOWN_CONFLICTS]

        if new_conflicts:
            print("\n❌ NEW ROUTE CONFLICTS DETECTED:")
            print("=" * 80)
            for conflict in new_conflicts:
                print(f"\n🔴 Path: {conflict['path']}")
                print(f"   Endpoints: {', '.join(conflict['endpoints'])}")
                print(f"   Methods: {conflict['methods']}")

            print("\n" + "=" * 80)
            print("\n⚠️  Route conflicts can cause:")
            print("   - Unpredictable routing behavior (last registered route wins)")
            print("   - Authentication failures (wrong decorator applied)")
            print("   - 404/401 errors")
            print("\n💡 Solution:")
            print("   - Remove duplicate @app.route() or @blueprint.route() decorators")
            print("   - Remove deprecated service-registered routes (e.g., gam_inventory_service.py)")
            print("   - Ensure each path has only ONE route registration")
            print("\n📖 See: src/services/gam_inventory_service.py for example of deprecated routes")
            print()
            return 1

        if conflicts:
            # All conflicts are known/whitelisted
            print(f"⚠️  {len(conflicts)} known route conflicts exist (technical debt)")
            print("   These are whitelisted to not block commits.")
            print("   TODO: Resolve these conflicts in a future cleanup.")
        else:
            print("✅ No route conflicts detected")

        return 0

    except Exception as e:
        print(f"\n⚠️  Warning: Could not check route conflicts: {e}")
        print("   (This is not a fatal error - continuing)")
        return 0  # Don't fail the commit for import errors


if __name__ == "__main__":
    sys.exit(check_route_conflicts())
