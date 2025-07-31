#!/usr/bin/env python3
"""
Quick test script to check NYTimes format parsing.
"""

import json
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_creative_format_service import AICreativeFormatService


async def test_nytimes_parsing():
    """Test parsing of NYTimes Slideshow Flex XL format."""
    
    # Load HTML
    html_path = Path("creative_format_parsing_examples/nytimes/raw_html/slideshow_flex_xl.html")
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Load expected output
    expected_path = Path("creative_format_parsing_examples/nytimes/expected_output/slideshow_flex_xl.json")
    with open(expected_path, 'r') as f:
        expected_data = json.load(f)
    
    print("Testing NYTimes Slideshow Flex XL parsing...")
    print("=" * 50)
    
    # Parse with AI service
    service = AICreativeFormatService()
    source_url = "https://advertising.nytimes.com/formats/display-formats/slideshow-flex-xl/"
    
    try:
        format_specs = await service.discover_formats_from_html(html_content, source_url)
        
        print(f"\nFound {len(format_specs)} formats")
        print(f"Expected {len(expected_data['formats'])} formats")
        
        print("\nExtracted formats:")
        for i, spec in enumerate(format_specs):
            print(f"\n{i+1}. {spec.name}")
            print(f"   Type: {spec.type}")
            print(f"   Dimensions: {spec.width}x{spec.height}" if spec.width and spec.height else "   Dimensions: Not specified")
            print(f"   Description: {spec.description[:100]}..." if spec.description else "   Description: None")
            if spec.specs:
                print(f"   Additional specs: {json.dumps(spec.specs, indent=6)}")
        
        print("\n" + "=" * 50)
        print("Expected formats:")
        for i, fmt in enumerate(expected_data['formats']):
            print(f"\n{i+1}. {fmt['name']}")
            print(f"   Dimensions: {fmt['width']}x{fmt['height']}")
            
    except Exception as e:
        print(f"Error during parsing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_nytimes_parsing())