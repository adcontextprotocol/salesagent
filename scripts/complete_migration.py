#!/usr/bin/env python
"""Complete migration of all routes to blueprints."""

import re
from pathlib import Path


def comment_out_route_function(content, func_name, blueprint_name=""):
    """Comment out a function and its decorators."""
    # Pattern to match the function and all its decorators
    pattern = rf"((?:@app\.route.*?\n|@require.*?\n|@[a-z_]+.*?\n)*)def {func_name}\(.*?\):.*?(?=\n(?:@|def |class |# MIGRATED|if __name__|$))"

    def replacer(match):
        lines = match.group(0).split("\n")
        commented = []
        for line in lines:
            if line.strip():
                commented.append("# " + line if not line.startswith("#") else line)
            else:
                commented.append(line)

        marker = f"# MIGRATED to {blueprint_name} blueprint" if blueprint_name else "# MIGRATED to blueprint"
        return f"{marker}\n" + "\n".join(commented)

    return re.sub(pattern, replacer, content, flags=re.DOTALL | re.MULTILINE)


def migrate_all_routes():
    """Migrate all routes to blueprints."""
    admin_ui_path = Path("admin_ui.py")
    content = admin_ui_path.read_text()

    # Routes to migrate (function_name, blueprint_name)
    routes_to_migrate = [
        # Main routes that need special handling
        ("health", "api"),  # Already in refactored app
        ("index", "main"),  # Already in refactored app
        ("settings", "settings"),  # Global settings
        # Tenant routes
        ("tenant_dashboard", "tenants"),
        ("tenant_settings", "settings"),
        ("update_tenant", "tenants"),
        ("update_slack", "tenants"),
        ("test_slack", "tenants"),
        ("create_tenant", "tenants"),
        # Product routes
        ("list_products", "products"),
        ("add_product", "products"),
        ("edit_product_basic", "products"),
        ("add_product_ai_form", "products"),
        ("analyze_product_ai", "products"),
        ("bulk_product_upload_form", "products"),
        ("bulk_product_upload", "products"),
        ("get_product_templates", "products"),
        ("browse_product_templates", "products"),
        ("create_from_template", "products"),
        ("product_setup_wizard", "products"),
        ("create_products_bulk", "products"),
        # User management
        ("list_users", "tenants"),
        ("add_user", "tenants"),
        ("toggle_user", "tenants"),
        ("update_user_role", "tenants"),
        ("update_principal_mappings", "tenants"),
        ("create_principal", "tenants"),
        # Policy routes
        ("policy_settings", "policy"),
        ("update_policy_settings", "policy"),
        ("manage_policy_rules", "policy"),
        ("review_policy_task", "policy"),
        # Creative format routes
        ("list_creative_formats", "creatives"),
        ("add_creative_format_ai", "creatives"),
        ("analyze_creative_format", "creatives"),
        ("save_creative_format", "creatives"),
        ("sync_standard_formats", "creatives"),
        ("discover_formats_from_url", "creatives"),
        ("save_discovered_formats", "creatives"),
        ("get_creative_format", "creatives"),
        ("edit_creative_format_page", "creatives"),
        ("update_creative_format", "creatives"),
        ("delete_creative_format", "creatives"),
        # GAM routes
        ("detect_gam_network", "gam"),
        ("configure_gam", "gam"),
        ("gam_reporting_dashboard", "gam"),
        ("view_gam_line_item", "gam"),
        ("test_gam_connection", "api"),
        ("get_gam_advertisers", "api"),
        ("get_custom_targeting_keys", "api"),
        ("get_gam_line_item", "api"),
        # Sync and order routes
        ("sync_orders_endpoint", "api"),
        ("get_tenant_sync_status", "api"),
        ("trigger_tenant_sync", "api"),
        ("get_tenant_orders_session", "api"),
        ("get_order_details_session", "api"),
        # Other routes
        ("targeting_browser", "tenants"),
        ("inventory_browser", "tenants"),
        ("orders_browser", "tenants"),
        ("workflows_dashboard", "tenants"),
        ("media_buy_approval", "tenants"),
        ("get_adapter_inventory_schema", "adapters"),
        ("setup_adapter", "adapters"),
        ("update_general_settings", "settings"),
        ("update_adapter_settings", "settings"),
        ("update_slack_settings", "settings"),
        ("check_inventory_sync", "tenants"),
        ("analyze_ad_server_inventory", "tenants"),
        ("mcp_test", "mcp_test"),
        ("mcp_test_call", "mcp_test"),
        ("update_settings", "settings"),
    ]

    migrated_count = 0
    skipped_count = 0

    for func_name, blueprint_name in routes_to_migrate:
        # Check if already migrated
        if "# MIGRATED" in content and f"def {func_name}" in content:
            # Check if the function is already commented
            func_match = re.search(rf"^def {func_name}\(", content, re.MULTILINE)
            if func_match:
                line_start = content.rfind("\n", 0, func_match.start()) + 1
                line = content[line_start : func_match.start()]
                if line.strip().startswith("#"):
                    print(f"  ✓ Already migrated: {func_name}")
                    skipped_count += 1
                    continue

        # Check if function exists
        if f"def {func_name}(" in content:
            print(f"  Migrating {func_name} to {blueprint_name}...")
            content = comment_out_route_function(content, func_name, blueprint_name)
            migrated_count += 1
        else:
            print(f"  ⚠️  Function not found: {func_name}")

    # Save the updated content
    admin_ui_path.write_text(content)

    print("\nMigration complete!")
    print(f"  Migrated: {migrated_count} routes")
    print(f"  Already migrated: {skipped_count} routes")
    print("\nNext steps:")
    print("  1. Run tests to ensure all routes work")
    print("  2. Update docker-compose.yml to use refactored app")
    print("  3. Test in development environment")


if __name__ == "__main__":
    print("Starting complete route migration...\n")
    migrate_all_routes()
