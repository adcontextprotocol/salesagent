# Creative Format Parsing Examples

This directory contains examples of creative format specifications from various ad platforms and the expected parsing output. These examples are used to test and improve the AI-powered creative format parsing functionality.

## Directory Structure

```
creative_format_parsing_examples/
├── yahoo/
│   ├── raw_html/           # Original HTML pages from Yahoo
│   └── expected_output/    # Expected JSON parsing results
├── google/
│   ├── raw_html/           # Original HTML pages from Google
│   └── expected_output/    # Expected JSON parsing results
└── iab/
    ├── raw_html/           # Original HTML pages from IAB
    └── expected_output/    # Expected JSON parsing results
```

## Expected Output Format

Each expected output JSON file should contain a `formats` array with objects following this structure:

```json
{
  "formats": [
    {
      "name": "Format Name",
      "format_id": "unique_identifier",
      "type": "display|video|audio|native",
      "description": "Format description",
      "width": 300,
      "height": 250,
      "duration_seconds": 30,  // For video/audio
      "max_file_size_kb": 200,
      "file_types": ["jpg", "png", "gif"],
      "is_standard": false,
      "specs": {
        // Additional specifications
      },
      "source_url": "URL where format was found"
    }
  ]
}
```

## Testing

Use the `test_creative_format_parsing.py` script to validate the parsing against these examples:

```bash
python test_creative_format_parsing.py
```

## Adding New Examples

1. Download the HTML page to the appropriate `raw_html/` directory
2. Create the expected output JSON in the `expected_output/` directory
3. Run the test script to ensure parsing works correctly
