#!/usr/bin/env python3
"""
Test script to validate creative format parsing against stored examples.
"""

import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_creative_format_service import AICreativeFormatService


def load_expected_output(file_path: str) -> dict[str, Any]:
    """Load expected output JSON file."""
    with open(file_path) as f:
        return json.load(f)


def load_raw_html(file_path: str) -> str:
    """Load raw HTML file."""
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def compare_format(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Compare actual vs expected format and return differences."""
    differences = []

    # Check required fields
    required_fields = ["name", "format_id", "type"]
    for field in required_fields:
        if actual.get(field) != expected.get(field):
            differences.append(f"{field}: '{actual.get(field)}' != '{expected.get(field)}'")

    # Check numeric fields with tolerance
    numeric_fields = ["width", "height", "duration_seconds", "max_file_size_kb"]
    for field in numeric_fields:
        if field in expected:
            actual_val = actual.get(field)
            expected_val = expected[field]
            if actual_val != expected_val:
                differences.append(f"{field}: {actual_val} != {expected_val}")

    # Check description (allow some flexibility)
    if expected.get("description"):
        if not actual.get("description"):
            differences.append("Missing description")
        elif (
            expected["description"].lower() not in actual["description"].lower()
            and actual["description"].lower() not in expected["description"].lower()
        ):
            differences.append(f"Description mismatch: '{actual.get('description')}' vs '{expected['description']}'")

    return differences


async def parse_example_directory(example_dir: Path) -> dict[str, Any]:
    """Parse formats for a single example directory."""
    results = {"success": True, "formats_tested": 0, "formats_passed": 0, "errors": []}

    # Find all raw HTML files
    raw_html_dir = example_dir / "raw_html"
    expected_output_dir = example_dir / "expected_output"

    if not raw_html_dir.exists():
        results["success"] = False
        results["errors"].append(f"Raw HTML directory not found: {raw_html_dir}")
        return results

    # Process each HTML file
    for html_file in raw_html_dir.glob("*.html"):
        base_name = html_file.stem
        expected_file = expected_output_dir / f"{base_name}.json"

        if not expected_file.exists():
            results["errors"].append(f"Expected output not found for {html_file.name}")
            continue

        print(f"\nTesting {example_dir.name}/{html_file.name}...")

        try:
            # Load files
            html_content = load_raw_html(html_file)
            expected_data = load_expected_output(expected_file)

            # Parse with the service
            extractor = CreativeFormatExtractor()
            # Mock the URL since we're testing with local files
            source_url = expected_data["formats"][0].get("source_url", "") if expected_data["formats"] else ""

            # Extract formats from HTML
            service = AICreativeFormatService()
            format_specs = await service.discover_formats_from_html(html_content, source_url)
            # Convert FormatSpecification objects to dicts
            actual_formats = [asdict(spec) for spec in format_specs]

            # Compare results
            expected_formats = expected_data["formats"]
            results["formats_tested"] += len(expected_formats)

            if len(actual_formats) != len(expected_formats):
                results["errors"].append(
                    f"{html_file.name}: Found {len(actual_formats)} formats, expected {len(expected_formats)}"
                )
                results["success"] = False

            # Compare each format
            for i, expected_format in enumerate(expected_formats):
                if i < len(actual_formats):
                    actual_format = actual_formats[i]
                    differences = compare_format(actual_format, expected_format)

                    if differences:
                        results["errors"].append(
                            f"{html_file.name} - Format {i+1} ({expected_format['name']}):\n  "
                            + "\n  ".join(differences)
                        )
                        results["success"] = False
                    else:
                        results["formats_passed"] += 1
                        print(f"  ✓ {expected_format['name']}")
                else:
                    results["errors"].append(f"{html_file.name}: Missing format {i+1} ({expected_format['name']})")
                    results["success"] = False

        except Exception as e:
            results["errors"].append(f"{html_file.name}: Error during parsing - {str(e)}")
            results["success"] = False

    return results


async def main():
    """Run all parsing tests."""
    print("Creative Format Parsing Test Suite")
    print("=" * 50)

    examples_dir = Path(__file__).parent / "creative_format_parsing_examples"

    if not examples_dir.exists():
        print(f"ERROR: Examples directory not found: {examples_dir}")
        return 1

    all_results = {}
    total_formats_tested = 0
    total_formats_passed = 0

    # Test each platform's examples
    for platform_dir in examples_dir.iterdir():
        if platform_dir.is_dir() and not platform_dir.name.startswith("."):
            print(f"\nTesting {platform_dir.name} examples...")
            results = await test_parsing_example(platform_dir)
            all_results[platform_dir.name] = results
            total_formats_tested += results["formats_tested"]
            total_formats_passed += results["formats_passed"]

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    for platform, results in all_results.items():
        status = "PASS" if results["success"] else "FAIL"
        print(f"\n{platform}: {status}")
        print(f"  Formats tested: {results['formats_tested']}")
        print(f"  Formats passed: {results['formats_passed']}")

        if results["errors"]:
            print("  Errors:")
            for error in results["errors"]:
                print(f"    - {error}")

    print(f"\nTotal formats tested: {total_formats_tested}")
    print(f"Total formats passed: {total_formats_passed}")

    if total_formats_tested > 0:
        success_rate = (total_formats_passed / total_formats_tested) * 100
        print(f"Success rate: {success_rate:.1f}%")

    # Return exit code
    return 0 if all(r["success"] for r in all_results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
