# Product Implementation Configuration

The `implementation_config` field in products bridges the gap between what advertisers see and what ad servers need to execute campaigns.

## Overview

Every product has two aspects:
1. **User-facing details**: Name, description, pricing, formats (what advertisers see)
2. **Implementation details**: Placement IDs, targeting keys, ad server settings (what's needed to create the campaign)

The `implementation_config` field stores the technical details needed to implement a product on your ad server.

## Schema

```python
class Product(BaseModel):
    # User-facing fields
    product_id: str
    name: str
    description: str
    formats: List[Format]
    targeting_template: Targeting
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    is_fixed_price: bool
    cpm: Optional[float] = None
    price_guidance: Optional[PriceGuidance] = None
    
    # Implementation details
    implementation_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Ad server-specific configuration"
    )
```

## Examples

### Google Ad Manager Product
```json
{
  "product_id": "ros_display_300x250",
  "name": "Run of Site - Medium Rectangle",
  "description": "Standard 300x250 display ads across all content",
  "formats": [...],
  "cpm": 2.50,
  "implementation_config": {
    "ad_server": "google_ad_manager",
    "placement_ids": ["123456789", "123456790"],
    "ad_unit_path": "/network/run_of_site/display",
    "size_mapping": ["300x250", "320x250"],
    "frequency_caps": {
      "impressions": 10,
      "time_unit": "day",
      "time_count": 1
    },
    "custom_targeting": {
      "product": "ros_display"
    }
  }
}
```

### Kevel Product
```json
{
  "product_id": "premium_sports",
  "name": "Sports Premium Display",
  "implementation_config": {
    "ad_server": "kevel",
    "site_id": 12345,
    "ad_types": [5, 16],  // Kevel ad type IDs
    "zone_ids": [789, 790],
    "keywords": ["sports", "premium"],
    "flight_categories": ["Sports Content"]
  }
}
```

### Video Product with Player Settings
```json
{
  "product_id": "video_preroll",
  "name": "Video Pre-roll",
  "implementation_config": {
    "ad_server": "google_ad_manager",
    "placement_ids": ["987654321"],
    "ad_unit_path": "/network/video/preroll",
    "player_size": ["640x360", "1280x720"],
    "max_pod_length": 60,
    "skippable_after": 5,
    "companion_sizes": ["300x250", "728x90"],
    "video_position": "preroll",
    "mime_types": ["video/mp4", "video/webm"]
  }
}
```

## Usage in Media Buy Creation

When a media buy is created, the adapter uses the implementation_config:

```python
# In GoogleAdManager adapter
def create_order(self, request: CreateMediaBuyRequest, products: List[Product]):
    for package in request.media_packages:
        product = get_product(package.product_id)
        config = product.implementation_config
        
        # Create line item using implementation details
        line_item = {
            "name": f"{request.name} - {product.name}",
            "targeting": {
                "inventoryTargeting": {
                    "targetedPlacementIds": config["placement_ids"]
                },
                "customTargeting": config.get("custom_targeting", {})
            },
            "creativePlaceholders": [{
                "size": {"width": 300, "height": 250}
            }],
            "costPerUnit": {
                "currencyCode": "USD",
                "microAmount": int(product.cpm * 1000000)
            }
        }
```

## Principal-Aware Implementation

The upstream catalog can customize implementation based on the principal:

```python
@mcp.tool
async def get_products(principal_data: Dict[str, Any], ...):
    # Get advertiser's ad server account
    if 'gam_advertiser_id' in principal_data['platform_mappings']:
        # Return GAM-compatible products
        product['implementation_config']['advertiser_id'] = principal_data['platform_mappings']['gam_advertiser_id']
    
    # Apply advertiser-specific settings
    if principal_id in VIP_ADVERTISERS:
        product['implementation_config']['priority'] = 'high'
        product['implementation_config']['frequency_caps'] = None  # No caps for VIPs
```

## Run-of-Site Best Practices

Every publisher should offer standard run-of-site products:

1. **Standard Display Sizes**
   - 300x250 (Medium Rectangle)
   - 728x90 (Leaderboard)
   - 300x600 (Half Page)
   - 320x50 (Mobile Banner)

2. **Common Implementation Config**
   ```json
   {
     "ad_server": "your_ad_server",
     "placement_ids": ["all_your_placements"],
     "frequency_caps": {"impressions": 10, "time_unit": "day"},
     "position_targeting": "any",
     "device_targeting": ["desktop", "mobile", "tablet"]
   }
   ```

3. **Pricing Strategy**
   - Run-of-site should be your most affordable option
   - Fixed CPM for predictability
   - No complex targeting that increases cost

## Validation

Before creating a media buy, validate the product can be implemented:

```python
# Check advertiser has required ad server account
impl_config = product.implementation_config
if impl_config['ad_server'] == 'google_ad_manager':
    if 'gam_advertiser_id' not in principal.platform_mappings:
        raise Error("Advertiser needs GAM account for this product")

# Verify placements exist
placement_ids = impl_config.get('placement_ids', [])
if not validate_placements_exist(placement_ids):
    raise Error("Invalid placement configuration")
```

## Security Considerations

1. **Don't Expose Sensitive Data**
   - Keep internal IDs in implementation_config
   - Don't expose rate cards or margin information
   - Mask placement IDs if needed

2. **Validate Access**
   - Ensure advertiser can access the specified inventory
   - Check competitive exclusions
   - Verify budget meets minimums

3. **Audit Trail**
   - Log what implementation config was used
   - Track any modifications made
   - Store config with the media buy

## Migration Guide

To add implementation_config to existing products:

1. **Identify Your Placements**
   ```sql
   -- Example: Find all placement IDs for run-of-site
   SELECT placement_id, placement_name 
   FROM ad_server_placements 
   WHERE category = 'run_of_site';
   ```

2. **Update Product Records**
   ```python
   product.implementation_config = {
       "ad_server": "google_ad_manager",
       "placement_ids": ["123", "456", "789"],
       "ad_unit_path": "/network/ros",
       # Add other settings
   }
   ```

3. **Test Implementation**
   - Create test media buy
   - Verify line items created correctly
   - Check targeting applied properly

## Future Enhancements

- **Dynamic Configuration**: Adjust config based on availability
- **Multi-Ad Server**: Support products across multiple ad servers
- **Template System**: Reusable implementation templates
- **Optimization Hints**: Include performance optimization settings