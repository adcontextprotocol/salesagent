#!/usr/bin/env python3
"""Test the improved AI creative format parsing against our examples."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))


# Test with mocked AI service
@pytest.mark.ai
@patch("src.services.ai_creative_format_service.genai.GenerativeModel")
async def test_parsing_examples(mock_genai_model):
    """Test parsing against all examples and compare results."""
    # Mock the model's generate_content method to return sample format data
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        [
            {
                "name": "Display Banner",
                "type": "display",
                "description": "Standard display banner ad",
                "extends": None,
                "specifications": {
                    "desktop": {
                        "dimensions": [{"width": 728, "height": 90}],
                        "file_types": ["jpg", "png", "gif"],
                        "max_file_size_kb": 150,
                    }
                },
                "platforms": ["desktop", "mobile"],
                "tags": ["standard", "display"],
                "is_premium": False,
            }
        ]
    )
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value = mock_response
    mock_genai_model.return_value = mock_model_instance

    from src.services.ai_creative_format_service import AICreativeFormatService

    service = AICreativeFormatService()

    # Test with sample HTML content
    sample_html = """
    <html>
    <body>
        <h1>Display Banner Ad</h1>
        <table>
            <tr><td>Size</td><td>728x90</td></tr>
            <tr><td>File Types</td><td>JPG, PNG, GIF</td></tr>
            <tr><td>Max Size</td><td>150KB</td></tr>
        </table>
    </body>
    </html>
    """

    # Test parsing with the mocked AI service
    url = "https://example.com/ad-specs"

    try:
        parsed_formats = await service.discover_formats_from_html(sample_html, url)

        # Verify the mocked response was processed correctly
        assert len(parsed_formats) == 1
        assert parsed_formats[0].name == "Display Banner"
        assert parsed_formats[0].type == "display"
        assert parsed_formats[0].description == "Standard display banner ad"

        # Verify the model was called
        assert mock_model_instance.generate_content.called

    except Exception as e:
        pytest.fail(f"Test failed with error: {e}")


if __name__ == "__main__":
    print("Testing improved AI creative format parsing...")
    print("=" * 60)

    # Run the test directly using asyncio
    async def run():
        await test_parsing_examples(MagicMock())

    asyncio.run(run())
    print("\nDone!")
