# Implementation Config Flow Example

This document shows how `implementation_config` flows through the system from product definition to ad server implementation.

## 1. Publisher Defines Products

The publisher (e.g., Yahoo using Google Ad Manager) defines products with implementation details:

```python
# In database or upstream catalog
{
    "product_id": "ros_display_300x250",
    "name": "Run of Site - Medium Rectangle",
    "description": "Standard 300x250 display ads across all site content",
    "formats": [{
        "format_id": "display_300x250",
        "name": "Medium Rectangle",
        "type": "display",
        "specs": {"width": 300, "height": 250}
    }],
    "cpm": 2.50,
    "implementation_config": {
        # GAM-specific configuration
        "placement_ids": ["123456789", "123456790"],
        "ad_unit_path": "/1234/run_of_site/display",
        "size_mapping": ["300x250", "320x250"],
        "key_values": {"tier": "standard"},
        "frequency_caps": {
            "impressions": 10,
            "time_unit": "day"
        },
        "targeting": {
            "geo_country_any_of": ["US", "CA"]
        }
    }
}
```

## 2. Advertiser Requests Products

```python
# Advertiser's agent calls list_products
request = ListProductsRequest(
    brief="I need cost-effective display ads for brand awareness"
)

# Returns products including implementation_config
products = await list_products(request)
```

## 3. Advertiser Creates Media Buy

```python
# Advertiser selects a product and creates media buy
request = CreateMediaBuyRequest(
    po_number="PO-12345",
    total_budget=5000.0,
    flight_start_date="2025-02-01",
    flight_end_date="2025-02-28",
    media_packages=[
        MediaPackage(
            product_id="ros_display_300x250",  # Selected product
            impressions=2000000,
            cpm=2.50,
            delivery_type="non_guaranteed"
        )
    ]
)
```

## 4. System Retrieves Product and Implementation Config

In `create_media_buy` handler (main.py):

```python
def create_media_buy(req: CreateMediaBuyRequest, context: Context):
    # Get principal info
    principal = get_principal_object(principal_id)
    
    # For each package, get the product with implementation_config
    for package in req.media_packages:
        product = get_product_by_id(package.product_id)
        # product.implementation_config contains GAM setup details
        
    # Pass to adapter
    adapter = GoogleAdManager(principal)
    response = adapter.create_media_buy(req, products_with_config)
```

## 5. Adapter Uses Implementation Config

In the Google Ad Manager adapter:

```python
def create_media_buy(self, request, products):
    # Get advertiser ID from principal
    advertiser_id = self.principal.platform_mappings.gam_advertiser_id
    
    for package, product in zip(request.media_packages, products):
        config = product.implementation_config
        
        # Create GAM line item using implementation details
        line_item = {
            "name": f"{request.po_number} - {product.name}",
            "advertiserId": advertiser_id,  # From principal
            "targeting": {
                "inventoryTargeting": {
                    "targetedPlacementIds": config["placement_ids"]  # From product
                },
                "customTargeting": {
                    # Merge product targeting with any overlay
                    **config.get("key_values", {}),
                    **convert_overlay_to_key_values(request.targeting_overlay)
                }
            },
            "creativePlaceholders": [{
                "size": {
                    "width": 300,
                    "height": 250
                }
            }],
            "costPerUnit": {
                "currencyCode": "USD",
                "microAmount": int(product.cpm * 1000000)
            },
            "frequencyCaps": config.get("frequency_caps")
        }
        
        # Create in GAM
        gam_service.create_line_item(line_item)
```

## Key Points

1. **Publisher owns implementation_config**: It describes how to implement products on THEIR ad server
2. **Advertiser provides their ID**: From principal.platform_mappings (e.g., GAM advertiser ID)
3. **Adapter combines both**: Uses advertiser ID + product implementation config
4. **Product catalog can be dynamic**: Upstream server can generate implementation_config on the fly

## Example with Upstream Catalog

An upstream catalog server could dynamically generate implementation_config:

```python
@mcp.tool
async def get_products(brief: str, principal_data: Dict):
    # Generate products based on available inventory
    products = []
    
    # Check what's available right now
    available_placements = check_inventory_availability()
    
    # Build product with current placement IDs
    product = {
        "product_id": "dynamic_ros_display",
        "name": "Run of Site Display",
        "cpm": calculate_dynamic_price(brief),
        "implementation_config": {
            "placement_ids": available_placements,
            "ad_unit_path": "/1234/dynamic",
            # Could even include principal-specific settings
            "advertiser_category": get_advertiser_category(principal_data)
        }
    }
    
    products.append(product)
    return {"products": products}
```

## Benefits

1. **Flexibility**: Products can have any ad server-specific configuration
2. **Abstraction**: Advertisers don't see internal implementation details
3. **Dynamic**: Upstream catalogs can generate config based on availability
4. **Portable**: Same product structure works across different ad servers