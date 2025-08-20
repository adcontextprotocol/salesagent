#!/usr/bin/env python
"""Script to perform the actual migration of routes."""

import re
import sys
from pathlib import Path


def comment_out_route(content, route_path, func_name):
    """Comment out a route in admin_ui.py."""
    # Find the route decorator and function
    pattern = rf'(@app\.route\("{re.escape(route_path)}".*?\n(?:@.*?\n)*def {func_name}.*?(?=\n@app\.route|\n@[a-z]+_bp\.route|\ndef [a-z]|\nclass |\n# |\nif __name__|$))'

    def replacer(match):
        lines = match.group(0).split("\n")
        commented_lines = []
        for line in lines:
            if line.strip():
                commented_lines.append("# " + line if not line.startswith("#") else line)
            else:
                commented_lines.append(line)
        result = "\n".join(commented_lines)
        return f"# MIGRATED to blueprint\n{result}"

    new_content = re.sub(pattern, replacer, content, flags=re.DOTALL | re.MULTILINE)
    return new_content


def migrate_auth_routes():
    """Migrate authentication routes."""
    print("Migrating authentication routes...")

    admin_ui_path = Path("admin_ui.py")
    content = admin_ui_path.read_text()

    # Routes that should be migrated
    auth_routes = [
        ("/login", "login"),
        ("/auth/google", "google_auth"),
        ("/tenant/<tenant_id>/login", "tenant_login"),
        ("/tenant/<tenant_id>/auth/google", "tenant_google_auth"),
        ("/auth/google/callback", "google_callback"),
        ("/auth/select-tenant", "select_tenant"),
        ("/logout", "logout"),
        ("/test/auth", "test_auth"),
        ("/test/login", "test_login_form"),
    ]

    for route, func in auth_routes:
        if f'@app.route("{route}"' in content and f'# @app.route("{route}"' not in content:
            print(f"  Commenting out {route} -> {func}")
            content = comment_out_route(content, route, func)

    # Fix the blueprint registration - auth shouldn't have url_prefix
    content = content.replace(
        'app.register_blueprint(auth_bp, url_prefix="/auth")',
        "app.register_blueprint(auth_bp)  # No url_prefix - auth routes are at root",
    )

    admin_ui_path.write_text(content)
    print("  Auth routes migrated!")


def update_refactored_app():
    """Update the refactored app to match current state."""
    print("\nUpdating refactored app configuration...")

    app_path = Path("src/admin/app.py")
    content = app_path.read_text()

    # Fix auth blueprint registration
    content = content.replace(
        "app.register_blueprint(auth_bp)", "app.register_blueprint(auth_bp)  # No url_prefix - auth routes are at root"
    )

    app_path.write_text(content)
    print("  Refactored app updated!")


def update_docker_compose():
    """Update docker-compose.yml to use refactored app."""
    print("\nUpdating docker-compose.yml...")

    compose_path = Path("docker-compose.yml")
    content = compose_path.read_text()

    # Update the command to use refactored app
    old_command = "command: python admin_ui_prod.py"
    new_command = "command: python -c \"from src.admin.app import create_app; app, socketio = create_app(); socketio.run(app, host='0.0.0.0', port=8001, debug=False)\""

    if old_command in content:
        content = content.replace(old_command, new_command)
        compose_path.write_text(content)
        print("  Docker compose updated to use refactored app!")
    else:
        print("  Docker compose already updated or has different configuration")


def main():
    """Main migration function."""
    print("Starting route migration...\n")

    # Step 1: Migrate auth routes
    migrate_auth_routes()

    # Step 2: Update refactored app
    update_refactored_app()

    # Step 3: Update docker-compose
    if "--docker" in sys.argv:
        update_docker_compose()

    print("\nMigration complete!")
    print("Next steps:")
    print("  1. Test the authentication routes")
    print("  2. Run tests to ensure everything works")
    print("  3. Continue migrating other route categories")


if __name__ == "__main__":
    main()
