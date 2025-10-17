# Creative Agent Bug Report: Missing `dimensions` Attribute

## Summary
The creative agent at `https://creative.adcontextprotocol.org` fails to generate previews with error: `'Format' object has no attribute 'dimensions'`

## Environment
- **Creative Agent**: https://creative.adcontextprotocol.org
- **Sales Agent**: AdCP v2.4 reference implementation
- **Date**: 2025-10-17
- **Protocol**: MCP (Model Context Protocol)

## Request Details

### MCP Call
```
Tool: preview_creative
Endpoint: https://creative.adcontextprotocol.org/mcp
```

### Parameters Sent
```json
{
  "format_id": "display_336x280_html",
  "creative_manifest": {
    "name": "Test HTML Creative",
    "assets": {
      "primary": {
        "asset_type": "html",
        "content": "<div>Test Ad</div>"
      }
    }
  }
}
```

### Notes on Request Format
- `format_id` is passed as separate parameter (not in manifest)
- `assets` is a dictionary with role keys per AdCP spec
- `asset_type` field is used (not `type`)

## Response Received

### Error Response
```json
{
  "error": "Preview generation failed: 'Format' object has no attribute 'dimensions'",
  "traceback": "equest.creative_manifest, input_set)\n                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/src/creative_agent/storage.py\", line 82, in generate_preview_html\n    if format_obj.dimensions:\n       ^^^^^^^^^^^^^^^^^^^^^\n  File \"/app/.venv/lib/python3.12/site-packages/pydantic/main.py\", line 1026, in __getattr__\n    raise AttributeError(f'{type(self).__name__!r} object has no attribute {item!r}')\nAttributeError: 'Format' object has no attribute 'dimensions'\n"
}
```

## Expected Response Structure

Based on AdCP PR #119 and current sales agent implementation, the expected response should be:

```json
{
  "previews": [
    {
      "variant_id": "default",
      "variant_name": "Default",
      "renders": [
        {
          "render_id": "desktop",
          "render_name": "Desktop",
          "preview_url": "https://preview.example.com/creative-123.html",
          "dimensions": {
            "width": 336,
            "height": 280
          }
        }
      ]
    }
  ]
}
```

## Root Cause Analysis

The traceback shows:
1. Error occurs in `/app/src/creative_agent/storage.py` at line 82
2. Code attempts to access `format_obj.dimensions`
3. The `Format` Pydantic model doesn't have a `dimensions` attribute

## Possible Issues

### Issue 1: Outdated Format Model
The `Format` model may be using an old schema that doesn't include `dimensions`. Modern formats should have dimensions either:
- As a direct attribute: `format.dimensions`
- Or calculated from constraints: `format.width`, `format.height`

### Issue 2: Wrong Attribute Name
The code may be looking for the wrong attribute. Possible alternatives:
- `format.size`
- `format.width` and `format.height` (separate fields)
- `format.constraints.dimensions`

### Issue 3: Format Not Loaded Properly
The format may not be fully loaded/populated when accessed in `generate_preview_html()`.

## Impact

This prevents preview generation for **all** creatives synced via the AdCP protocol:
- Sales agents cannot generate preview URLs
- Creatives show up with `url: null` in database
- No preview images/HTML available for review
- Blocks creative approval workflows

## Reproduction Steps

1. Set up MCP client pointing to `https://creative.adcontextprotocol.org/mcp`
2. Call `preview_creative` tool with:
   - `format_id`: `"display_336x280_html"` (or any display format)
   - `creative_manifest`: Valid manifest with HTML asset
3. Observe error response

## Test Script

See attached test script that reproduces the issue:

```python
#!/usr/bin/env python3
"""Test script to reproduce creative agent dimensions bug."""

import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_preview():
    transport = StreamableHttpTransport(url="https://creative.adcontextprotocol.org/mcp")
    client = Client(transport=transport)

    async with client:
        result = await client.call_tool(
            "preview_creative",
            {
                "format_id": "display_336x280_html",
                "creative_manifest": {
                    "name": "Test Creative",
                    "assets": {
                        "primary": {
                            "asset_type": "html",
                            "content": "<div>Test Ad</div>"
                        }
                    }
                }
            }
        )
        print(result)

asyncio.run(test_preview())
```

## Suggested Fix

In `/app/src/creative_agent/storage.py` line 82, change:

```python
# BEFORE (broken)
if format_obj.dimensions:
    width = format_obj.dimensions.width
    height = format_obj.dimensions.height

# AFTER (suggested fix - check what attributes actually exist)
if hasattr(format_obj, 'dimensions') and format_obj.dimensions:
    width = format_obj.dimensions.width
    height = format_obj.dimensions.height
elif hasattr(format_obj, 'width') and hasattr(format_obj, 'height'):
    width = format_obj.width
    height = format_obj.height
elif hasattr(format_obj, 'size'):
    width = format_obj.size.width
    height = format_obj.size.height
else:
    # Parse from format_id as fallback
    # e.g., "display_336x280_html" -> width=336, height=280
    parts = format_id.split('_')
    if len(parts) >= 2 and 'x' in parts[1]:
        dims = parts[1].split('x')
        width = int(dims[0])
        height = int(dims[1])
    else:
        width = None
        height = None
```

## Additional Context

### Format Discovery Works
The `list_creative_formats` tool works correctly and returns format definitions. The issue is specifically in the `preview_creative` tool when it tries to access format dimensions.

### Multiple Format Types Affected
This likely affects:
- All display formats (300x250, 728x90, etc.)
- Video formats (if they use the same code path)
- Any format that requires dimension information for preview generation

## Contact
- **Reporter**: AdCP Sales Agent Development Team
- **Date**: 2025-10-17
- **Related**: This blocks AdCP v2.4 creative sync workflows in production
