#!/usr/bin/env python3
"""
Quick Form Mismatch Checker

Finds common form field naming issues like the "Tenant name is required" bug.
Focused on the most common patterns to avoid complexity.
"""

import re
from pathlib import Path


def find_form_fields_simple(file_path):
    """Find form fields in a simple way."""
    content = Path(file_path).read_text()

    # Find input name attributes
    fields = []
    for match in re.finditer(r'name=["\']([^"\']+)["\']', content):
        fields.append(match.group(1))

    return fields


def find_request_form_gets(file_path):
    """Find request.form.get() calls."""
    content = Path(file_path).read_text()

    # Find request.form.get calls
    fields = []
    for match in re.finditer(r'request\.form\.get\(["\']([^"\']+)["\']', content):
        fields.append(match.group(1))

    return fields


def main():
    print("🔍 Quick Form Mismatch Check")
    print("=" * 50)

    # Known problematic patterns
    issues = []

    # Check specific known issues
    settings_file = "src/admin/blueprints/settings.py"
    settings_template = "templates/tenant_settings.html"

    if Path(settings_file).exists() and Path(settings_template).exists():
        backend_fields = find_request_form_gets(settings_file)
        template_fields = find_form_fields_simple(settings_template)

        print(f"🔍 Checking {settings_file} vs {settings_template}")
        print(f"   Backend expects: {sorted(set(backend_fields))}")
        print(f"   Template has: {sorted(set(template_fields))}")

        # Check for the specific tenant_name vs name issue
        if "tenant_name" in backend_fields and "name" in template_fields:
            issues.append("❌ Backend expects 'tenant_name' but template uses 'name'")
        elif "name" in backend_fields and "name" in template_fields:
            print("✅ Tenant name field mapping looks correct")

        # Check for other mismatches
        backend_set = set(backend_fields)
        template_set = set(template_fields)

        missing_in_backend = template_set - backend_set
        missing_in_template = backend_set - template_set

        if missing_in_backend:
            issues.append(f"⚠️  Template fields not used in backend: {missing_in_backend}")
        if missing_in_template:
            issues.append(f"⚠️  Backend expects fields not in template: {missing_in_template}")

    print("\n" + "=" * 50)
    if issues:
        print("❌ Issues found:")
        for issue in issues:
            print(f"   {issue}")

        print("\n💡 Quick fixes:")
        print("   1. Update backend code to match form field names")
        print("   2. Update template field names to match backend")
        print("   3. Add missing fields to forms or remove unused backend code")
    else:
        print("✅ No obvious form field mismatches found")

    return len(issues) == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
