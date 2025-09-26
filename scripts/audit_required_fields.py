#!/usr/bin/env python3
"""
Required Fields Audit Script

Analyzes all Pydantic models to identify potentially over-strict validation
that could cause issues like the 'brief' is required problem.
"""

import inspect
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pydantic import BaseModel

from src.core.schemas import *


def analyze_model_fields(model_class):
    """Analyze a Pydantic model for required fields and their defaults."""
    if not hasattr(model_class, "model_fields"):
        return None

    field_analysis = {
        "required_fields": [],
        "optional_with_defaults": [],
        "optional_no_defaults": [],
        "potentially_over_strict": [],
    }

    for field_name, field_info in model_class.model_fields.items():
        is_required = field_info.is_required()
        default_val = getattr(field_info, "default", None)

        if is_required:
            field_analysis["required_fields"].append(
                {
                    "name": field_name,
                    "type": str(field_info.annotation) if hasattr(field_info, "annotation") else "Unknown",
                    "description": getattr(field_info, "description", "") or "No description",
                }
            )

            # Check for potentially over-strict requirements
            # Only flag fields that could reasonably have defaults
            if field_name in ["brief", "description", "title", "comment"]:
                field_analysis["potentially_over_strict"].append(field_name)
            # 'name' is often a legitimate requirement for business entities
            elif "optional" in (getattr(field_info, "description", "") or "").lower():
                field_analysis["potentially_over_strict"].append(field_name)

        elif default_val is not None and default_val != ...:
            field_analysis["optional_with_defaults"].append({"name": field_name, "default": default_val})
        else:
            field_analysis["optional_no_defaults"].append(field_name)

    return field_analysis


def main():
    """Run the required fields audit."""
    print("🔍 REQUIRED FIELDS AUDIT")
    print("=" * 60)
    print("Analyzing all Request/Response models for validation issues...\n")

    # Get all classes from schemas module
    all_classes = []
    for name, obj in globals().items():
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and obj != BaseModel
            and (name.endswith("Request") or name.endswith("Response"))
        ):
            all_classes.append((name, obj))

    # Analyze Request models (these are most likely to have validation issues)
    request_models = [(name, cls) for name, cls in all_classes if name.endswith("Request")]

    print(f"Found {len(request_models)} Request models to analyze:\n")

    issues_found = []

    for model_name, model_class in sorted(request_models):
        analysis = analyze_model_fields(model_class)
        if not analysis:
            continue

        print(f"📋 {model_name}")
        print("-" * 40)

        # Show required fields
        if analysis["required_fields"]:
            print("🔴 REQUIRED fields:")
            for field in analysis["required_fields"]:
                print(f"   • {field['name']}: {field['type']}")
                if field["description"]:
                    print(f"     Description: {field['description']}")

        # Show optional fields with defaults
        if analysis["optional_with_defaults"]:
            print("🟢 OPTIONAL fields (with defaults):")
            for field in analysis["optional_with_defaults"]:
                print(f"   • {field['name']} = {field['default']}")

        # Highlight potentially over-strict fields
        if analysis["potentially_over_strict"]:
            print("⚠️  POTENTIALLY OVER-STRICT:")
            for field_name in analysis["potentially_over_strict"]:
                print(f"   • {field_name} - Consider making optional with default")
            issues_found.append(f"{model_name}: {', '.join(analysis['potentially_over_strict'])}")

        print()  # Blank line

    # Summary
    print("\n" + "=" * 60)
    print("🚨 SUMMARY OF POTENTIAL ISSUES")
    print("=" * 60)

    if issues_found:
        print("The following models have potentially over-strict validation:")
        for issue in issues_found:
            print(f"• {issue}")
        print(f"\nTotal models with potential issues: {len(issues_found)}")
    else:
        print("✅ No obvious validation issues found!")

    # Specific recommendations
    print("\n📝 RECOMMENDATIONS:")
    print("1. Fields like 'brief', 'description', 'name' should usually be optional with defaults")
    print("2. Required fields should only be those that are truly necessary for business logic")
    print("3. Consider defaults that make sense for most use cases (e.g., brief='', countries=['US'])")
    print("4. Test all Request models can be created with minimal parameters")

    # Known good patterns
    print("\n✅ GOOD PATTERNS FOUND:")
    good_patterns = []

    # Check GetProductsRequest (should now be good)
    analysis = analyze_model_fields(GetProductsRequest)
    if analysis:
        required_count = len(analysis["required_fields"])
        optional_count = len(analysis["optional_with_defaults"])
        if required_count == 1 and optional_count >= 1:  # Only promoted_offering required
            good_patterns.append("GetProductsRequest - brief is optional with default")

    # Check SignalDeliverTo (should now be good)
    analysis = analyze_model_fields(SignalDeliverTo)
    if analysis:
        optional_count = len(analysis["optional_with_defaults"])
        if optional_count >= 2:  # platforms and countries have defaults
            good_patterns.append("SignalDeliverTo - platforms and countries have sensible defaults")

    for pattern in good_patterns:
        print(f"• {pattern}")

    if not good_patterns:
        print("• Run this audit after making fixes to see improvements!")


if __name__ == "__main__":
    main()
