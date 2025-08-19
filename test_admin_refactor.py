#!/usr/bin/env python3
"""Test script to verify the refactored admin UI structure."""

import sys
import traceback


def test_imports():
    """Test that all modules can be imported."""
    print("Testing module imports...")

    modules_to_test = [
        ("admin.utils", "Utilities module"),
        ("admin.blueprints.auth", "Authentication blueprint"),
        ("admin.blueprints.tenants", "Tenants blueprint"),
        ("admin.blueprints.products", "Products blueprint"),
        ("admin.app", "Application factory"),
    ]

    failed = []

    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ {description} ({module_name})")
        except ImportError as e:
            print(f"❌ {description} ({module_name}): {e}")
            failed.append((module_name, e))
        except Exception as e:
            print(f"❌ {description} ({module_name}): Unexpected error - {e}")
            failed.append((module_name, e))

    return len(failed) == 0, failed


def test_app_creation():
    """Test that the Flask app can be created."""
    print("\nTesting app creation...")

    try:
        from admin.app import create_app

        app, socketio = create_app()

        # Check that app was created
        if app:
            print("✅ Flask app created successfully")
        else:
            print("❌ Flask app creation failed")
            return False

        # Check that blueprints are registered
        blueprints = list(app.blueprints.keys())
        print(f"✅ Registered blueprints: {blueprints}")

        # Check key routes exist
        rules = [str(rule) for rule in app.url_map.iter_rules()]
        key_routes = ["/login", "/logout", "/health", "/"]

        for route in key_routes:
            if any(route in rule for rule in rules):
                print(f"✅ Route {route} is registered")
            else:
                print(f"⚠️  Route {route} not found")

        return True

    except Exception as e:
        print(f"❌ App creation failed: {e}")
        traceback.print_exc()
        return False


def test_blueprint_routes():
    """Test that blueprint routes are properly registered."""
    print("\nTesting blueprint routes...")

    try:
        from admin.app import create_app

        app, _ = create_app()

        # Group routes by blueprint
        blueprint_routes = {}
        for rule in app.url_map.iter_rules():
            endpoint = rule.endpoint
            if "." in endpoint:
                blueprint = endpoint.split(".")[0]
                if blueprint not in blueprint_routes:
                    blueprint_routes[blueprint] = []
                blueprint_routes[blueprint].append(str(rule))

        # Display routes by blueprint
        for blueprint, routes in blueprint_routes.items():
            print(f"\n{blueprint} blueprint:")
            for route in routes[:5]:  # Show first 5 routes
                print(f"  - {route}")
            if len(routes) > 5:
                print(f"  ... and {len(routes) - 5} more routes")

        return True

    except Exception as e:
        print(f"❌ Blueprint route testing failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Admin UI Refactoring Test Suite")
    print("=" * 60)

    all_passed = True

    # Test imports
    passed, failed_imports = test_imports()
    all_passed = all_passed and passed

    if not passed:
        print("\n⚠️  Some imports failed. Details:")
        for module, error in failed_imports:
            print(f"  - {module}: {error}")

    # Test app creation
    if all_passed:  # Only test if imports passed
        passed = test_app_creation()
        all_passed = all_passed and passed

    # Test blueprint routes
    if all_passed:  # Only test if app creation passed
        passed = test_blueprint_routes()
        all_passed = all_passed and passed

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed! The refactored structure is working.")
        return 0
    else:
        print("❌ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
