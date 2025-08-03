# Google Ad Manager Inventory Management

## Overview

The AdCP Sales Agent now includes a comprehensive inventory management system for Google Ad Manager (GAM). This system automatically discovers, syncs, and manages ad units, placements, and labels from GAM, making it easy to configure which inventory each product targets.

## Key Features

### 1. Automatic Inventory Discovery
- **Ad Units**: Discovers entire ad unit hierarchy with sizes and targeting info
- **Placements**: Syncs all placement configurations
- **Labels**: Imports competitive exclusion and other labels
- **Caching**: 24-hour cache to reduce API calls
- **Database Storage**: All inventory stored in local database for fast access

### 2. Inventory Browser UI
- **Tree View**: Hierarchical display of ad unit structure
- **Search**: Find inventory by name, path, or status
- **Real-time Sync**: Refresh inventory on demand
- **Visual Status**: Active/inactive/archived indicators

### 3. Product Configuration
- **Easy Selection**: Checkbox-based ad unit selection
- **Smart Suggestions**: AI-powered recommendations based on product specs
- **Size Matching**: Automatically suggests units matching creative sizes
- **Bulk Operations**: Select/deselect entire branches

### 4. Database Schema

#### GAM Inventory Table
```sql
CREATE TABLE gam_inventory (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    inventory_type VARCHAR(20) NOT NULL,  -- 'ad_unit', 'placement', 'label'
    inventory_id VARCHAR(50) NOT NULL,    -- GAM ID
    name VARCHAR(255) NOT NULL,
    path JSON,                            -- Array of path components
    status VARCHAR(20) NOT NULL,          -- 'ACTIVE', 'INACTIVE', 'ARCHIVED', 'STALE'
    metadata JSON,                        -- Full inventory details
    last_synced TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

#### Product Inventory Mappings
```sql
CREATE TABLE product_inventory_mappings (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    inventory_type VARCHAR(20) NOT NULL,
    inventory_id VARCHAR(50) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL
);
```

## Usage Guide

### 1. Initial Setup

When setting up a GAM publisher:

```bash
# Create tenant with GAM enabled
python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code YOUR_NETWORK \
  --gam-key-file /path/to/service-account.json
```

### 2. Sync Inventory

#### Via Admin UI
1. Navigate to tenant dashboard
2. Click "Inventory →" tab (only visible for GAM tenants)
3. Click "Sync Now" button
4. Wait for sync to complete (usually 10-30 seconds)

#### Via API
```python
# POST /api/tenant/{tenant_id}/inventory/sync
```

### 3. Configure Product Inventory

#### Via Admin UI
1. Go to Products tab
2. Edit a product
3. Click "Configure Inventory →" button
4. Select ad units from the tree
5. Or click "Get Suggestions" for AI recommendations
6. Save configuration

#### Via API
```python
# GET /api/tenant/{tenant_id}/product/{product_id}/inventory
# POST /api/tenant/{tenant_id}/product/{product_id}/inventory
{
    "ad_unit_ids": ["123456", "789012"],
    "placement_ids": ["345678"],  # Optional
    "primary_ad_unit_id": "123456"  # Optional
}
```

### 4. Search Inventory

```python
# GET /api/tenant/{tenant_id}/inventory/search?q=sports&type=ad_unit&status=ACTIVE
```

## How It Works

### Discovery Process

1. **Authentication**: Uses service account credentials from tenant config
2. **API Calls**: Queries GAM APIs for inventory data
3. **Hierarchical Processing**: Builds complete tree structure
4. **Metadata Extraction**: Captures sizes, targeting, labels
5. **Database Storage**: Upserts all items with conflict resolution

### Suggestion Algorithm

The system suggests ad units based on:

1. **Size Match** (10 points): Exact creative size matches
2. **Keyword Match** (5 points): Product name/description in path
3. **Explicit Targeting** (3 points): Units marked for direct sale
4. **Specificity** (2 points): Deeper paths score higher

### Caching Strategy

- **24-hour TTL**: Inventory cached for one day
- **Manual Refresh**: Users can force sync anytime
- **Stale Detection**: Old items marked as STALE
- **Incremental Updates**: Only changed items updated

## API Endpoints

### Inventory Sync
```
POST /api/tenant/{tenant_id}/inventory/sync
```

### Get Ad Unit Tree
```
GET /api/tenant/{tenant_id}/inventory/tree
Response: {
    "root_units": [...],
    "total_units": 156,
    "last_sync": "2025-01-28T10:30:00Z",
    "needs_refresh": false
}
```

### Search Inventory
```
GET /api/tenant/{tenant_id}/inventory/search?q=keyword&type=ad_unit&status=ACTIVE
```

### Get Product Inventory
```
GET /api/tenant/{tenant_id}/product/{product_id}/inventory
```

### Update Product Inventory
```
POST /api/tenant/{tenant_id}/product/{product_id}/inventory
Body: {
    "ad_unit_ids": ["123", "456"],
    "placement_ids": ["789"]
}
```

### Get Inventory Suggestions
```
GET /api/tenant/{tenant_id}/inventory/suggest?sizes=300x250&sizes=728x90&keywords=sports
```

## Security Considerations

1. **Tenant Isolation**: Each tenant only sees their own inventory
2. **Service Account**: Uses tenant-specific GAM credentials
3. **Access Control**: Requires authentication and tenant membership
4. **Audit Trail**: All sync operations logged

## Troubleshooting

### Sync Failures

**Problem**: Inventory sync fails with authentication error
**Solution**: 
1. Verify service account key file exists
2. Check GAM API permissions
3. Ensure network code is correct

**Problem**: No ad units discovered
**Solution**:
1. Verify service account has inventory read permissions
2. Check if ad units exist in GAM
3. Look for filters excluding inventory

### Missing Inventory

**Problem**: Some ad units not appearing
**Solution**:
1. Check ad unit status (archived units hidden)
2. Verify no permission restrictions
3. Force refresh to get latest data

### Performance Issues

**Problem**: Slow inventory loading
**Solution**:
1. Check last sync time (may need refresh)
2. Use search instead of browsing full tree
3. Consider pagination for large inventories

## Best Practices

1. **Regular Syncs**: Schedule daily syncs during off-peak hours
2. **Naming Conventions**: Use clear ad unit names for easy search
3. **Size Standards**: Stick to IAB standard sizes when possible
4. **Archiving**: Archive unused ad units to reduce clutter
5. **Documentation**: Document special ad units in descriptions

## Future Enhancements

1. **Auto-sync**: Webhook-based real-time updates
2. **Bulk Edit**: Update multiple products at once
3. **Templates**: Save common inventory selections
4. **Analytics**: Show inventory performance metrics
5. **Forecasting**: Integrate GAM forecasting API

## Example: Complete Setup Flow

```python
# 1. Create tenant
tenant = create_tenant("Sports Publisher", adapter="google_ad_manager")

# 2. Sync inventory
sync_inventory(tenant.tenant_id)

# 3. Create product
product = create_product(
    tenant_id=tenant.tenant_id,
    name="Homepage Takeover",
    formats=["display_728x90", "display_300x250"]
)

# 4. Get suggestions
suggestions = get_inventory_suggestions(
    tenant_id=tenant.tenant_id,
    sizes=[{"width": 728, "height": 90}],
    keywords=["homepage", "top"]
)

# 5. Configure inventory
update_product_inventory(
    tenant_id=tenant.tenant_id,
    product_id=product.product_id,
    ad_unit_ids=[s["inventory"]["id"] for s in suggestions[:5]]
)
```

This completes the inventory management system, providing publishers with a powerful way to manage their GAM inventory within AdCP.