#!/usr/bin/env python3
"""Test the improved AI creative format parsing against our examples."""

import asyncio
import json
import os
import sys
import pytest
from pathlib import Path
from typing import Dict, Any, List

pytestmark = pytest.mark.unit
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

# Mark test to skip if GEMINI_API_KEY is not set
@pytest.mark.skipif(
    os.getenv('GEMINI_API_KEY') == 'test_key_for_mocking',
    reason="Requires real GEMINI_API_KEY for AI testing"
)
@pytest.mark.ai
async def test_parsing_examples():
    """Test parsing against all examples and compare results."""
    from ai_creative_format_service import AICreativeFormatService
    service = AICreativeFormatService()
    examples_dir = Path(__file__).parent / "creative_format_parsing_examples"
    
    results = []
    
    # Process each publisher
    for publisher_dir in examples_dir.iterdir():
        if publisher_dir.is_dir() and not publisher_dir.name.startswith('.'):
            print(f"\n{'='*60}")
            print(f"Testing {publisher_dir.name.upper()} examples")
            print(f"{'='*60}")
            
            # Load HTML files
            raw_html_dir = publisher_dir / "raw_html"
            expected_output_dir = publisher_dir / "expected_output"
            
            for html_file in raw_html_dir.glob("*.html"):
                format_name = html_file.stem
                expected_file = expected_output_dir / f"{format_name}.json"
                
                if not expected_file.exists():
                    print(f"⚠️  No expected output for {format_name}")
                    continue
                
                print(f"\nTesting: {format_name}")
                print("-" * 40)
                
                # Load HTML
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Load expected output
                with open(expected_file, 'r') as f:
                    expected_data = json.load(f)
                    expected_formats = expected_data.get('formats', [])
                
                # Construct URL based on publisher
                if publisher_dir.name == 'yahoo':
                    url = "https://adspecs.yahooinc.com/premium-ads/" + format_name.replace('_', '-')
                elif publisher_dir.name == 'nytimes':
                    url = "https://advertising.nytimes.com/formats/display-formats/" + format_name.replace('_', '-')
                else:
                    url = f"https://example.com/{format_name}"
                
                # Parse with AI
                try:
                    parsed_formats = await service.discover_formats_from_html(html_content, url)
                    
                    # Convert to comparable format
                    parsed_data = []
                    for fmt in parsed_formats:
                        parsed_data.append({
                            "name": fmt.name,
                            "type": fmt.type,
                            "description": fmt.description,
                            "extends": fmt.extends,
                            "width": fmt.width,
                            "height": fmt.height,
                            "duration_seconds": fmt.duration_seconds,
                            "max_file_size_kb": fmt.max_file_size_kb,
                            "specs": fmt.specs
                        })
                    
                    # Compare results
                    print(f"Expected {len(expected_formats)} formats, parsed {len(parsed_data)} formats")
                    
                    # Check each expected format
                    for i, expected in enumerate(expected_formats):
                        print(f"\nFormat {i+1}: {expected['name']}")
                        
                        # Find matching parsed format
                        matched = None
                        for parsed in parsed_data:
                            if parsed['name'] == expected['name'] or \
                               (parsed.get('width') == expected.get('width') and 
                                parsed.get('height') == expected.get('height')):
                                matched = parsed
                                break
                        
                        if matched:
                            # Compare fields
                            compare_fields = ['type', 'extends', 'width', 'height', 'duration_seconds']
                            for field in compare_fields:
                                expected_val = expected.get(field)
                                parsed_val = matched.get(field)
                                if expected_val != parsed_val:
                                    print(f"  ❌ {field}: expected {expected_val}, got {parsed_val}")
                                elif expected_val:
                                    print(f"  ✅ {field}: {parsed_val}")
                            
                            # Check specs
                            if expected.get('specs') and matched.get('specs'):
                                print(f"  📋 specs: {matched['specs']}")
                        else:
                            print(f"  ❌ Format not found in parsed results")
                    
                    # Save parsed results for inspection
                    output_file = Path(f"parsed_{publisher_dir.name}_{format_name}.json")
                    with open(output_file, 'w') as f:
                        json.dump({"formats": parsed_data}, f, indent=2)
                    print(f"\n💾 Saved parsed results to {output_file}")
                    
                    results.append({
                        "publisher": publisher_dir.name,
                        "format": format_name,
                        "expected_count": len(expected_formats),
                        "parsed_count": len(parsed_data),
                        "success": len(parsed_data) > 0
                    })
                    
                except Exception as e:
                    print(f"❌ Error parsing {format_name}: {e}")
                    results.append({
                        "publisher": publisher_dir.name,
                        "format": format_name,
                        "error": str(e),
                        "success": False
                    })
    
    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    successful = sum(1 for r in results if r.get('success'))
    total = len(results)
    
    print(f"✅ Successful: {successful}/{total}")
    print(f"❌ Failed: {total - successful}/{total}")
    
    for result in results:
        status = "✅" if result.get('success') else "❌"
        print(f"{status} {result['publisher']}/{result['format']}", end="")
        if result.get('error'):
            print(f" - Error: {result['error']}")
        else:
            print(f" - Expected: {result.get('expected_count', '?')}, Parsed: {result.get('parsed_count', '?')}")


if __name__ == "__main__":
    print("Testing improved AI creative format parsing...")
    print("=" * 60)
    asyncio.run(test_parsing_examples())