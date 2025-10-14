#!/usr/bin/env python3
"""Find schema field mismatches (fields not in AdCP spec).

Scans codebase for Response object instantiations and checks if
all fields are in the AdCP specification.
"""

import re
import subprocess
from pathlib import Path

# Known AdCP response schemas and their valid fields
# Source: https://adcontextprotocol.org/schemas/v1/
ADCP_RESPONSE_SCHEMAS = {
    "CreateMediaBuyResponse": {
        "adcp_version",
        "status",
        "buyer_ref",
        "task_id",
        "estimated_completion",
        "polling_interval",
        "task_progress",
        "errors",
        "media_buy",
        # Testing hooks (allowed in testing mode)
        "is_test",
        "dry_run",
        "test_session_id",
        "response_headers",
    },
    "UpdateMediaBuyResponse": {
        "adcp_version",
        "status",
        "buyer_ref",
        "task_id",
        "estimated_completion",
        "polling_interval",
        "task_progress",
        "errors",
        "media_buy",
        # Testing hooks
        "is_test",
        "dry_run",
        "test_session_id",
        "response_headers",
    },
    "GetMediaBuyDeliveryResponse": {
        "adcp_version",
        "buyer_ref",
        "media_buy",
        "reporting_period",
        "delivery_metrics",
        "package_metrics",
        # Testing hooks
        "is_test",
        "dry_run",
        "test_session_id",
        "response_headers",
    },
    "UpdatePerformanceIndexResponse": {
        "adcp_version",
        "status",
        "buyer_ref",
        "task_id",
        "estimated_completion",
        "polling_interval",
        "task_progress",
        "errors",
        "performance_index",
        # Testing hooks
        "is_test",
        "dry_run",
        "test_session_id",
        "response_headers",
    },
}


def run_mypy() -> str:
    """Run mypy and capture output."""
    result = subprocess.run(
        ["uv", "run", "mypy", "src/", "--config-file=mypy.ini"],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def parse_schema_errors(output: str) -> list[dict]:
    """Parse schema-related errors from mypy output."""
    errors = []

    for line in output.split("\n"):
        # Look for "Unexpected keyword argument" errors
        if "Unexpected keyword argument" in line:
            # Format: file.py:123: error: Unexpected keyword argument "field" for "Schema"
            match = re.match(
                r'^(.*?):(\d+): error: Unexpected keyword argument "(\w+)" for "(\w+)"',
                line,
            )
            if match:
                file_path, line_num, field, schema = match.groups()
                if schema in ADCP_RESPONSE_SCHEMAS:
                    errors.append(
                        {
                            "file": file_path,
                            "line": int(line_num),
                            "field": field,
                            "schema": schema,
                            "type": "unexpected_field",
                        }
                    )

        # Look for status value errors
        elif 'has incompatible type "Literal' in line and "status" in line:
            match = re.match(
                r'^(.*?):(\d+): error: Argument "status" .* has incompatible type "Literal\[\'(.*?)\'\]"',
                line,
            )
            if match:
                file_path, line_num, status_value = match.groups()
                errors.append(
                    {
                        "file": file_path,
                        "line": int(line_num),
                        "field": "status",
                        "value": status_value,
                        "type": "invalid_status",
                    }
                )

    return errors


def check_file_for_schemas(file_path: Path) -> list[dict]:
    """Scan file for Response schema instantiations."""
    content = file_path.read_text()
    issues = []

    for schema_name, valid_fields in ADCP_RESPONSE_SCHEMAS.items():
        # Find all instantiations of this schema
        pattern = rf"{schema_name}\((.*?)\)"
        for match in re.finditer(pattern, content, re.DOTALL):
            call_content = match.group(1)

            # Extract field names (simple parsing, may miss complex cases)
            field_pattern = r"(\w+)\s*="
            used_fields = set(re.findall(field_pattern, call_content))

            # Check for non-spec fields
            invalid = used_fields - valid_fields
            if invalid:
                line_num = content[: match.start()].count("\n") + 1
                issues.append(
                    {
                        "file": str(file_path),
                        "line": line_num,
                        "schema": schema_name,
                        "invalid_fields": invalid,
                        "type": "field_scan",
                    }
                )

    return issues


def main():
    print("=" * 80)
    print("Schema Field Mismatch Finder")
    print("=" * 80)
    print("\nScanning for AdCP schema violations...\n")

    # Method 1: Parse mypy errors
    print("1. Checking mypy errors...")
    mypy_output = run_mypy()
    mypy_errors = parse_schema_errors(mypy_output)

    # Method 2: Scan files directly
    print("2. Scanning source files...\n")
    scan_issues = []
    for file_path in Path("src").rglob("*.py"):
        scan_issues.extend(check_file_for_schemas(file_path))

    # Combine and deduplicate
    all_issues = mypy_errors + scan_issues

    if not all_issues:
        print("✓ No schema field mismatches found!")
        return

    print(f"Found {len(all_issues)} schema issues:\n")
    print("=" * 80)

    # Group by type
    unexpected_fields = [i for i in all_issues if i.get("type") in ["unexpected_field", "field_scan"]]
    invalid_status = [i for i in all_issues if i.get("type") == "invalid_status"]

    if unexpected_fields:
        print("\n1. UNEXPECTED FIELDS (not in AdCP spec):\n")
        by_schema = {}
        for issue in unexpected_fields:
            schema = issue.get("schema")
            if schema not in by_schema:
                by_schema[schema] = []
            by_schema[schema].append(issue)

        for schema, issues in sorted(by_schema.items()):
            print(f"  {schema}:")
            valid = ", ".join(sorted(ADCP_RESPONSE_SCHEMAS[schema]))
            print(f"    Valid fields: {valid}\n")

            for issue in issues:
                print(f"    {issue['file']}:{issue['line']}")
                if "field" in issue:
                    print(f"      Unexpected field: {issue['field']}")
                elif "invalid_fields" in issue:
                    print(f"      Unexpected fields: {', '.join(issue['invalid_fields'])}")
                print()

    if invalid_status:
        print("\n2. INVALID STATUS VALUES:\n")
        print("  Valid status values per operation:")
        print("    create_media_buy: submitted, working, input-required, completed,")
        print("                      canceled, failed, rejected, auth-required")
        print("    update_media_buy: completed, working, submitted, input-required")
        print()

        for issue in invalid_status:
            print(f"  {issue['file']}:{issue['line']}")
            print(f"    Invalid status: '{issue['value']}'")
            print()

    print("=" * 80)
    print(f"Total: {len(all_issues)} schema violations")
    print("=" * 80)
    print("\nFix suggestions:")
    print("  1. Remove fields not in AdCP spec")
    print("  2. Use 'errors' array for error messages:")
    print("     errors=[Error(code='...',details='...',message='...')]")
    print("  3. Use correct status values per operation")
    print("  4. Check spec: https://adcontextprotocol.org/schemas/v1/")


if __name__ == "__main__":
    main()
