#!/usr/bin/env python3
"""
Form Field Validation Script

This script validates that form fields in templates match the expected fields in backend handlers.
Prevents issues like the "Tenant name is required" error caused by field name mismatches.

Usage:
    python scripts/validate_form_fields.py
    python scripts/validate_form_fields.py --fix-mismatches
"""

import argparse
import re
import sys
from pathlib import Path


class FormFieldValidator:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.templates_dir = self.project_root / "templates"
        self.src_dir = self.project_root / "src"
        self.errors = []
        self.warnings = []

    def find_form_fields_in_template(self, template_path: Path) -> dict[str, list[str]]:
        """Extract form fields from HTML template."""
        if not template_path.exists():
            return {}

        content = template_path.read_text(encoding="utf-8")

        # Find all form actions and their fields
        forms = {}

        # Pattern to match form tags and their actions (including Jinja2 templates)
        form_pattern = r'<form[^>]*action=["\']([^"\'{}]+(?:\{\{[^}]+\}\}[^"\'{}]*)*)["\'][^>]*>'
        input_pattern = r'<input[^>]*name=["\']([^"\']+)["\'][^>]*>'
        select_pattern = r'<select[^>]*name=["\']([^"\']+)["\'][^>]*>'
        textarea_pattern = r'<textarea[^>]*name=["\']([^"\']+)["\'][^>]*>'

        form_matches = re.finditer(form_pattern, content, re.IGNORECASE)

        for form_match in form_matches:
            action = form_match.group(1)
            form_start = form_match.start()

            # Find the end of this form
            form_end_pattern = r"</form>"
            form_end_match = re.search(form_end_pattern, content[form_start:], re.IGNORECASE)
            if form_end_match:
                form_end = form_start + form_end_match.end()
                form_content = content[form_start:form_end]
            else:
                # If no closing tag found, take rest of file
                form_content = content[form_start:]

            # Extract all form fields within this form
            fields = set()
            for pattern in [input_pattern, select_pattern, textarea_pattern]:
                field_matches = re.finditer(pattern, form_content, re.IGNORECASE)
                for match in field_matches:
                    fields.add(match.group(1))

            if fields:
                forms[action] = list(fields)

        return forms

    def find_request_form_usage(self, python_file: Path) -> dict[str, list[str]]:
        """Extract request.form.get() calls from Python files."""
        if not python_file.exists():
            return {}

        content = python_file.read_text(encoding="utf-8")

        # Pattern to match request.form.get("field_name")
        pattern = r'request\.form\.get\(["\']([^"\']+)["\']'

        matches = re.finditer(pattern, content)

        # Try to associate with route decorators
        routes = {}
        lines = content.split("\n")

        for i, line in enumerate(lines):
            # Look for route decorators
            route_match = re.search(r'@[^.]*\.route\(["\']([^"\']+)["\'].*methods.*POST', line, re.IGNORECASE)
            if route_match:
                route_path = route_match.group(1)

                # Look for request.form.get calls in the next 50 lines
                fields = set()
                for j in range(i, min(i + 50, len(lines))):
                    form_matches = re.finditer(pattern, lines[j])
                    for match in form_matches:
                        fields.add(match.group(1))

                if fields:
                    routes[route_path] = list(fields)

        return routes

    def normalize_route_path(self, path: str) -> str:
        """Normalize route paths for comparison."""
        # Convert Flask route parameters to generic form
        path = re.sub(r"<[^>]+>", "*", path)
        # Remove leading/trailing slashes for comparison
        return path.strip("/")

    def validate_forms(self) -> bool:
        """Main validation function."""
        template_forms = {}
        python_routes = {}

        print("🔍 Scanning templates for form fields...")

        # Scan all templates
        for template_path in self.templates_dir.rglob("*.html"):
            forms = self.find_form_fields_in_template(template_path)
            for action, fields in forms.items():
                template_forms[action] = {
                    "fields": fields,
                    "template": str(template_path.relative_to(self.project_root)),
                }

        print(f"   Found {len(template_forms)} forms in templates")

        print("🔍 Scanning Python files for request.form usage...")

        # Scan all Python files
        for python_file in self.src_dir.rglob("*.py"):
            routes = self.find_request_form_usage(python_file)
            for route, fields in routes.items():
                python_routes[route] = {"fields": fields, "file": str(python_file.relative_to(self.project_root))}

        print(f"   Found {len(python_routes)} POST routes in Python files")

        print("\n🔍 Validating form field matches...")

        # Cross-reference forms with routes
        mismatches_found = False

        for template_action, template_info in template_forms.items():
            template_fields = set(template_info["fields"])

            # Try to find matching Python route
            matching_routes = []
            normalized_action = self.normalize_route_path(template_action)

            for route_path, route_info in python_routes.items():
                normalized_route = self.normalize_route_path(route_path)

                # Check if paths match (allowing for parameter differences)
                if self.paths_match(normalized_action, normalized_route):
                    matching_routes.append((route_path, route_info))

            if not matching_routes:
                self.warnings.append(f"⚠️  No matching Python route found for form action: {template_action}")
                print(f"   Template: {template_info['template']}")
                continue

            # Check field matches for each matching route
            for _route_path, route_info in matching_routes:
                route_fields = set(route_info["fields"])

                # Check for mismatches
                template_only = template_fields - route_fields
                route_only = route_fields - template_fields

                if template_only or route_only:
                    mismatches_found = True
                    self.errors.append(f"❌ Field mismatch for {template_action}:")
                    print(f"   Template: {template_info['template']}")
                    print(f"   Route: {route_info['file']}")

                    if template_only:
                        print(f"   📝 Form fields not used in backend: {sorted(template_only)}")
                    if route_only:
                        print(f"   🔧 Backend expects fields not in form: {sorted(route_only)}")
                    print()
                else:
                    print(f"✅ {template_action} - All fields match")

        return not mismatches_found

    def paths_match(self, path1: str, path2: str) -> bool:
        """Check if two route paths match, allowing for parameter differences."""
        # Split paths into segments
        segments1 = path1.split("/")
        segments2 = path2.split("/")

        if len(segments1) != len(segments2):
            return False

        for seg1, seg2 in zip(segments1, segments2, strict=False):
            # If either segment is a wildcard (*), it matches
            if seg1 == "*" or seg2 == "*":
                continue
            # Otherwise they must match exactly
            if seg1 != seg2:
                return False

        return True

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("FORM FIELD VALIDATION SUMMARY")
        print("=" * 60)

        if not self.errors and not self.warnings:
            print("✅ All form fields are properly matched!")
            return True

        if self.errors:
            print(f"❌ Found {len(self.errors)} critical issues:")
            for error in self.errors:
                print(f"   {error}")
            print()

        if self.warnings:
            print(f"⚠️  Found {len(self.warnings)} warnings:")
            for warning in self.warnings:
                print(f"   {warning}")
            print()

        print("💡 Common fixes:")
        print("   - Update field names in templates to match backend expectations")
        print("   - Update backend code to use field names from forms")
        print("   - Add missing form fields or remove unused backend code")

        return len(self.errors) == 0


def main():
    parser = argparse.ArgumentParser(description="Validate form field naming consistency")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--fix-mismatches", action="store_true", help="Attempt to fix common mismatches")

    args = parser.parse_args()

    validator = FormFieldValidator(args.project_root)

    print("🚀 Starting form field validation...")
    success = validator.validate_forms()
    validator.print_summary()

    if not success:
        print("\n🔧 To fix the tenant name issue specifically:")
        print("   File: src/admin/blueprints/settings.py")
        print("   Change: request.form.get('tenant_name') → request.form.get('name')")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
