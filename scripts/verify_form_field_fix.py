#!/usr/bin/env python3
"""
Verify that the tenant name form field fix is correct.

This script checks that the settings.py file correctly uses request.form.get("name")
instead of the incorrect request.form.get("tenant_name").
"""

from pathlib import Path


def check_tenant_name_fix():
    """Verify the form field fix is applied correctly."""
    settings_file = Path("src/admin/blueprints/settings.py")

    if not settings_file.exists():
        print("❌ settings.py file not found")
        return False

    content = settings_file.read_text()

    # Check if the fix is applied
    if 'request.form.get("name"' in content:
        print("✅ Form field fix is correctly applied")
        print('   Found: request.form.get("name")')

        # Check that the old incorrect pattern is not present
        if 'request.form.get("tenant_name"' in content:
            print("❌ WARNING: Old incorrect pattern still exists")
            print('   Found: request.form.get("tenant_name")')
            return False

        return True

    elif 'request.form.get("tenant_name"' in content:
        print("❌ Form field fix NOT applied")
        print('   Still using incorrect: request.form.get("tenant_name")')
        print('   Should be: request.form.get("name")')
        return False

    else:
        print("⚠️  Could not find form field access pattern")
        return False


def check_template_form_field():
    """Verify the template uses the correct field name."""
    template_file = Path("templates/tenant_settings.html")

    if not template_file.exists():
        print("❌ tenant_settings.html template not found")
        return False

    content = template_file.read_text()

    # Check for the form field
    if 'name="name"' in content:
        print('✅ Template correctly uses name="name"')
        return True
    else:
        print('❌ Template does not use name="name"')
        return False


def main():
    print("🔍 Verifying tenant name form field fix...")
    print("=" * 50)

    backend_ok = check_tenant_name_fix()
    template_ok = check_template_form_field()

    print("\n" + "=" * 50)
    if backend_ok and template_ok:
        print("✅ VERIFICATION PASSED")
        print("   The tenant name form field fix is correctly applied")
        print("   Backend and template are properly aligned")
        return True
    else:
        print("❌ VERIFICATION FAILED")
        print("   Form field mismatch still exists")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
