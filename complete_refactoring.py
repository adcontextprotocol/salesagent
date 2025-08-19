#!/usr/bin/env python3
"""Script to complete the admin UI refactoring."""

import re
from pathlib import Path

# Blueprint definitions with their routes
BLUEPRINTS = {
    "operations": {
        "prefix": "/tenant/<tenant_id>",
        "routes": [
            ("targeting", "GET", 1973),
            ("inventory", "GET", 1999),
            ("orders", "GET", 2030),
            ("reporting", "GET", 2111),
            ("workflows", "GET", 2507),
            ("media-buy/<media_buy_id>/approve", "GET", 2750),
        ],
        "api_routes": [
            ("/api/tenant/<tenant_id>/sync/orders", "POST", 2057),
            ("/api/tenant/<tenant_id>/sync/status", "GET", 2151),
            ("/api/tenant/<tenant_id>/sync/trigger", "POST", 2221),
            ("/api/tenant/<tenant_id>/orders", "GET", 2276),
            ("/api/tenant/<tenant_id>/orders/<order_id>", "GET", 2402),
        ],
    },
    "creatives": {
        "prefix": "/tenant/<tenant_id>/creative-formats",
        "routes": [
            ("", "GET", 4615),
            ("add/ai", "GET", 4669),
            ("analyze", "POST", 4680),
            ("save", "POST", 4715),
            ("sync-standard", "POST", 4768),
            ("discover", "POST", 4792),
            ("save-multiple", "POST", 4842),
            ("<format_id>", "GET", 4904),
            ("<format_id>/edit", "GET", 4949),
            ("<format_id>/update", "POST", 5011),
            ("<format_id>/delete", "POST", 5059),
        ],
    },
    "policy": {
        "prefix": "/tenant/<tenant_id>/policy",
        "routes": [
            ("", "GET", 4301),
            ("update", "POST", 4412),
            ("rules", ["GET", "POST"], 4481),
            ("review/<task_id>", ["GET", "POST"], 4488),
        ],
    },
    "settings": {
        "prefix": "/tenant/<tenant_id>/settings",
        "routes": [
            ("general", "POST", 1580),
            ("adapter", "POST", 1601),
            ("slack", "POST", 1954),
        ],
        "api_routes": [
            ("/api/tenant/<tenant_id>/revenue-chart", "GET", 1528),
            ("/api/oauth/status", "GET", 1638),
        ],
    },
    "adapters": {
        "prefix": "/tenant/<tenant_id>",
        "routes": [
            ("adapter/<adapter_name>/inventory_schema", "GET", 3136),
            ("setup_adapter", "POST", 3198),
        ],
    },
    "api": {
        "prefix": "/api",
        "routes": [
            ("health", "GET", 3377),
            ("gam/test-connection", "POST", 3388),
            ("gam/get-advertisers", "POST", 3560),
        ],
        "static_routes": [
            ("/static/<path:path>", "GET", 3669),
        ],
    },
    "mcp_test": {
        "prefix": "",
        "routes": [
            ("mcp-test", "GET", 6557),
        ],
        "api_routes": [
            ("/api/mcp-test/call", "POST", 6605),
        ],
    },
}

# Templates that need url_for updates
TEMPLATES_TO_UPDATE = {
    "targeting": "operations.targeting",
    "inventory": "operations.inventory",
    "orders": "operations.orders",
    "reporting": "operations.reporting",
    "workflows": "operations.workflows",
    "creative_formats": "creatives.index",
    "add_creative_format_ai": "creatives.add_ai",
    "policy": "policy.index",
    "policy_review": "policy.review",
    "mcp_test": "mcp_test.index",
    "gam_line_item": "gam.view_line_item",
    "detect_gam_network": "gam.detect_network",
    "configure_gam": "gam.configure",
}


def create_blueprint_file(name, config):
    """Create a new blueprint file with the specified routes."""

    blueprint_path = Path(f"src/admin/blueprints/{name}.py")

    # Generate the blueprint content
    content = f'''"""{''.join(word.capitalize() for word in name.split('_'))} management blueprint."""

import json
import logging
from flask import Blueprint, jsonify, render_template, request, session, redirect, url_for
from database_session import get_db_session
from models import Tenant, MediaBuy, Task, Product, CreativeFormat, HumanTask
from src.admin.utils import require_auth, require_tenant_access

logger = logging.getLogger(__name__)

# Create blueprint
{name}_bp = Blueprint("{name}", __name__)

'''

    # Add placeholder route functions
    if "routes" in config:
        for route_info in config["routes"]:
            if isinstance(route_info, tuple) and len(route_info) >= 2:
                route_path = route_info[0]
                methods = route_info[1] if isinstance(route_info[1], list) else [route_info[1]]
                func_name = route_path.replace("<", "").replace(">", "").replace("/", "_").replace("-", "_").strip("_")
                if not func_name:
                    func_name = "index"

                # Add route decorator and function
                content += f'''
@{name}_bp.route("/{route_path}", methods={methods})
@require_tenant_access()
def {func_name}(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({{"error": "Not yet implemented"}}), 501
'''

    # Write the file
    with open(blueprint_path, "w") as f:
        f.write(content)

    print(f"Created {blueprint_path}")


def update_template_references():
    """Update url_for references in templates."""

    templates_dir = Path("templates")

    for template_file in templates_dir.glob("*.html"):
        content = template_file.read_text()
        original = content

        # Update url_for references
        for old_name, new_name in TEMPLATES_TO_UPDATE.items():
            # Handle various url_for patterns
            patterns = [
                (f"url_for\\('{old_name}'", f"url_for('{new_name}'"),
                (f'url_for("{old_name}"', f'url_for("{new_name}"'),
                (f"url_for\\( '{old_name}'", f"url_for('{new_name}'"),
                (f'url_for( "{old_name}"', f'url_for("{new_name}"'),
            ]

            for old_pattern, new_pattern in patterns:
                content = content.replace(old_pattern, new_pattern)

        # Write back if changed
        if content != original:
            template_file.write_text(content)
            print(f"Updated {template_file}")


def register_blueprints_in_app():
    """Update src/admin/app.py to register new blueprints."""

    app_file = Path("src/admin/app.py")
    content = app_file.read_text()

    # Add imports for new blueprints
    import_section = """from src.admin.blueprints.auth import auth_bp
from src.admin.blueprints.tenants import tenants_bp
from src.admin.blueprints.products import products_bp
from src.admin.blueprints.gam import gam_bp
from src.admin.blueprints.operations import operations_bp
from src.admin.blueprints.creatives import creatives_bp
from src.admin.blueprints.policy import policy_bp
from src.admin.blueprints.settings import settings_bp
from src.admin.blueprints.adapters import adapters_bp
from src.admin.blueprints.api import api_bp
from src.admin.blueprints.mcp_test import mcp_test_bp"""

    # Replace the import section
    content = re.sub(
        r"from src\.admin\.blueprints\.auth import auth_bp.*?from src\.admin\.blueprints\.products import products_bp",
        import_section,
        content,
        flags=re.DOTALL,
    )

    # Add blueprint registrations
    registration_section = """    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(tenants_bp, url_prefix="/tenant")
    app.register_blueprint(products_bp, url_prefix="/tenant/<tenant_id>/products")
    app.register_blueprint(gam_bp)
    app.register_blueprint(operations_bp)
    app.register_blueprint(creatives_bp)
    app.register_blueprint(policy_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(adapters_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(mcp_test_bp)"""

    # Replace the registration section
    content = re.sub(
        r"    # Register blueprints.*?app\.register_blueprint\(products_bp.*?\)",
        registration_section,
        content,
        flags=re.DOTALL,
    )

    app_file.write_text(content)
    print(f"Updated {app_file}")


def main():
    """Main function to complete the refactoring."""

    print("Starting admin UI refactoring completion...")

    # Create remaining blueprint files
    for name, config in BLUEPRINTS.items():
        if name not in ["gam"]:  # Skip GAM as we already created it
            create_blueprint_file(name, config)

    # Update template references
    print("\nUpdating template references...")
    update_template_references()

    # Register blueprints in app
    print("\nRegistering blueprints in app...")
    register_blueprints_in_app()

    print("\nRefactoring structure created!")
    print("\nNext steps:")
    print("1. Manually extract route implementations from admin_ui.py to blueprint files")
    print("2. Test all functionality")
    print("3. Remove extracted code from admin_ui.py")
    print("4. Switch Docker/deployment to use admin_ui_refactored.py")


if __name__ == "__main__":
    main()
