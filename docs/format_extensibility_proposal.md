# Format Extensibility Proposal

## Problem Statement

Currently, `FORMAT_REGISTRY` in `schemas.py` is hardcoded, preventing users from:
1. Adding custom formats without code changes
2. Supporting GAM 1x1 placeholders for custom creative templates
3. Configuring platform-specific creative mappings per tenant
4. Overriding format configurations at product level

Real-world examples:
- Publisher with custom video player (640x380) needs GAM placeholder
- Publisher using GAM native creative templates needs 1x1 + `creative_template_id`
- Publisher with header bidding needs 1x1 for all programmatic line items

## Current Database Schema

The database already has a `creative_formats` table with support for:
- Custom formats per tenant (`tenant_id` nullable, NULL = standard)
- Format extension (`extends` field references foundational format)
- Modifications JSON for overrides
- Standard format flag

However, the code doesn't use this table - it only reads from `FORMAT_REGISTRY`.

## Proposed Solution

### 1. Format Lookup Priority

Create a format resolution system with layered priority:

```python
def get_format(format_id: str, tenant_id: str = None, product_id: str = None) -> Format:
    """
    Resolve format with priority:
    1. Product-level override (from product.implementation_config.format_overrides)
    2. Tenant-level custom format (from creative_formats table)
    3. Standard format (from FORMAT_REGISTRY)
    """

    # Check product override first
    if product_id and tenant_id:
        override = get_product_format_override(tenant_id, product_id, format_id)
        if override:
            return override

    # Check tenant custom formats
    if tenant_id:
        custom = get_tenant_custom_format(tenant_id, format_id)
        if custom:
            return custom

    # Fall back to standard registry
    if format_id in FORMAT_REGISTRY:
        return FORMAT_REGISTRY[format_id]

    raise ValueError(f"Unknown format_id: {format_id}")
```

### 2. Database Schema Changes

The `creative_formats` table is already well-designed. Add a new column:

```sql
ALTER TABLE creative_formats ADD COLUMN platform_config TEXT;  -- JSON field
```

This stores platform-specific config like:
```json
{
  "gam": {
    "creative_placeholder": {
      "width": 1,
      "height": 1,
      "creative_template_id": 12345678
    }
  }
}
```

### 3. Product-Level Format Overrides

Add to product's `implementation_config`:

```json
{
  "format_overrides": {
    "programmatic_display": {
      "platform_config": {
        "gam": {
          "creative_placeholder": {
            "width": 1,
            "height": 1,
            "creative_template_id": 87654321
          }
        }
      }
    }
  }
}
```

### 4. GAM Creative Template Support

Update creative placeholder logic in `orders.py`:

```python
# Check for creative_template_id in platform config
gam_cfg = platform_config.get("gam", {})
placeholder_cfg = gam_cfg.get("creative_placeholder", {})

if "creative_template_id" in placeholder_cfg:
    # Use GAM custom creative template (1x1 placeholder)
    creative_placeholder = {
        "size": {
            "width": 1,
            "height": 1,
            "isAspectRatio": False
        },
        "creativeTemplateId": placeholder_cfg["creative_template_id"]
    }
else:
    # Use standard size-based placeholder
    creative_placeholder = {
        "size": {
            "width": placeholder_cfg.get("width"),
            "height": placeholder_cfg.get("height"),
            "isAspectRatio": placeholder_cfg.get("is_aspect_ratio", False)
        }
    }
```

### 5. Admin UI Support

Add UI sections in Admin:

**Tenant Settings → Custom Formats:**
- List existing custom formats
- Add new format button
- Form fields:
  - Format ID (unique)
  - Name
  - Type (display/video/audio/native)
  - Requirements (JSON editor)
  - Platform Config (JSON editor with examples)

**Product Configuration → Format Overrides:**
- Select format from available formats (standard + custom)
- Override platform config
- Useful for products that need specific GAM creative template IDs

### 6. Migration Path

**Phase 1**: Database-backed format resolution (this PR)
- Add `get_format()` helper function
- Update `orders.py` to use `get_format()` instead of `FORMAT_REGISTRY[...]`
- Add product override support
- Keep `FORMAT_REGISTRY` as fallback

**Phase 2**: Admin UI (next PR)
- Custom format management UI
- Format override UI in product config

**Phase 3**: Format discovery (future)
- API endpoint to discover available formats
- Include tenant custom formats in responses

## Implementation Files

### New Files:
1. `src/core/format_resolver.py` - Format lookup logic
2. `alembic/versions/xxx_add_platform_config_to_formats.py` - Migration

### Modified Files:
1. `src/adapters/gam/managers/orders.py` - Use format resolver
2. `src/core/schemas.py` - Add format resolver to exports
3. `src/core/main.py` - Update tools to use format resolver

## Example Use Cases

### Use Case 1: Custom Video Format
```python
# Tenant adds custom format via Admin UI
custom_format = {
    "format_id": "custom_video_640x380",
    "name": "Custom Video Player",
    "type": "video",
    "requirements": {
        "width": 640,
        "height": 380,
        "duration_max": 30
    },
    "platform_config": {
        "gam": {
            "creative_placeholder": {
                "width": 640,
                "height": 380,
                "creative_size_type": "PIXEL"
            },
            "environment_type": "VIDEO_PLAYER"
        }
    }
}
```

### Use Case 2: GAM Native Creative Template
```python
# Product override for native template
product_impl_config = {
    "format_overrides": {
        "native_in_feed": {
            "platform_config": {
                "gam": {
                    "creative_placeholder": {
                        "width": 1,
                        "height": 1,
                        "creative_template_id": 12345678
                    }
                }
            }
        }
    }
}
```

### Use Case 3: Programmatic Header Bidding
```python
# Product for programmatic inventory
product_impl_config = {
    "format_overrides": {
        "display_300x250": {
            "platform_config": {
                "gam": {
                    "creative_placeholder": {
                        "width": 1,
                        "height": 1
                    }
                }
            }
        }
    }
}
```

## Testing Strategy

1. **Unit Tests**:
   - Format resolution priority
   - Product override logic
   - Tenant custom format lookup

2. **Integration Tests**:
   - GAM line item creation with custom formats
   - Creative template ID support
   - 1x1 placeholder generation

3. **E2E Tests**:
   - Create custom format via Admin UI
   - Use custom format in media buy
   - Verify correct GAM line item created

## Documentation Updates

- Add "Custom Formats" section to docs
- Document platform_config structure for each adapter
- Add examples for common use cases
- Update product configuration guide
