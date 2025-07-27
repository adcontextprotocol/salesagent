# Platform Mapping Guide

This guide explains how AdCP concepts map to specific ad server platforms in the reference implementation.

## Platform Overview

| AdCP Concept | Google Ad Manager | Kevel | Triton Digital |
|--------------|------------------|-------|----------------|
| Media Buy | Order | Campaign | Campaign |
| Package | Line Item | Flight | Flight |
| Principal | Advertiser | Advertiser | Advertiser |
| Creative | Creative | Creative | Audio Asset |

## Targeting Implementation

### Geographic Targeting

**Google Ad Manager**
```python
# In adapters/google_ad_manager.py
def _build_targeting(self, targeting_overlay):
    targeting = {}
    if targeting_overlay.geography:
        # GAM requires geo IDs, not codes
        # "US-CA" needs to map to GAM ID 21137 (California)
        targeting['geoTargeting'] = {
            'targetedLocations': [
                {'id': self._get_gam_geo_id(geo)} 
                for geo in targeting_overlay.geography
            ]
        }
```

**Kevel**
```python
# Kevel uses direct geo codes
targeting = {
    'geo': {
        'countries': ['US'],
        'regions': ['CA', 'NY'],
        'metros': [501]  # DMA codes
    }
}
```

**Triton Digital**
```python
# Limited to audio market geography
targeting = {
    'markets': ['Los Angeles', 'New York'],
    'states': ['CA', 'NY']
}
```

### Device Targeting Limitations

- **GAM**: Full device targeting including CTV
- **Kevel**: Desktop/mobile/tablet only
- **Triton**: Audio players only (no visual device targeting)

## Status Mapping

Each platform uses different status values:

### Google Ad Manager
- `DRAFT` → `pending_activation`
- `PENDING_APPROVAL` → `pending_approval`
- `APPROVED` → `scheduled`
- `DELIVERING` → `active`
- `PAUSED` → `paused`
- `COMPLETED` → `completed`

### Kevel
- `IsActive: false` + no impressions → `pending_activation`
- `IsActive: true` + future start → `scheduled`
- `IsActive: true` + delivering → `active`
- `IsActive: false` + has impressions → `paused`

### Triton Digital
- `active: false` → `paused`
- `active: true` + future start → `scheduled`  
- `active: true` + delivering → `active`
- Past end date → `completed`

## Creative Format Support

### Video Creative Handling

**GAM**: VAST XML required
```python
creative = {
    'xsi_type': 'VideoCreative',
    'vastXmlUrl': asset['media_url']
}
```

**Kevel**: Direct video URL
```python
creative = {
    'ThirdPartyUrl': asset['media_url']
}
```

**Triton**: Not supported (audio only)

### Custom Templates (Kevel Only)

```python
if asset['format'] == 'custom' and asset.get('template_id'):
    creative_payload['TemplateId'] = asset['template_id']
    creative_payload['Data'] = asset.get('template_data', {})
```

## Update Action Mapping

The standardized update actions map differently:

### pause_media_buy

- **GAM**: `OrderService.performOrderAction(PauseOrders)`
- **Kevel**: `PUT /campaign/{id} {"IsActive": false}`
- **Triton**: `PUT /campaigns/{id} {"active": false}`

### update_package_budget

- **GAM**: Recalculate impressions, update LineItem goal
- **Kevel**: Update Flight impressions based on CPM
- **Triton**: Update Flight goal value

## Authentication Patterns

### Header-Based (All Platforms)
```python
# GAM
headers = {'Authorization': f'Bearer {oauth_token}'}

# Kevel  
headers = {'X-Adzerk-ApiKey': api_key}

# Triton
headers = {'Authorization': f'Bearer {auth_token}'}
```

### Principal Mapping
Each principal needs platform-specific IDs:
```sql
-- Database schema
ALTER TABLE principals ADD COLUMN gam_advertiser_id VARCHAR(50);
ALTER TABLE principals ADD COLUMN kevel_advertiser_id VARCHAR(50);
ALTER TABLE principals ADD COLUMN triton_advertiser_id VARCHAR(50);
```

## Error Handling

### Rate Limiting
- **GAM**: 8 QPS limit, exponential backoff
- **Kevel**: 100 requests/second
- **Triton**: 10 requests/second

### Common Errors

**Invalid Targeting**
```python
if platform == "triton" and "video" in formats:
    raise ValueError("Triton only supports audio creatives")
```

**Budget Validation**
```python
if platform == "gam" and budget < 100:
    raise ValueError("GAM minimum budget is $100")
```

## Testing Adapters

### Dry Run Mode
```python
if self.dry_run:
    self.log(f"[yellow]Would call: POST {endpoint}[/yellow]")
    self.log(f"Payload: {json.dumps(payload, indent=2)}")
    return mock_response
```

### Platform Sandboxes
- **GAM**: Test network available
- **Kevel**: Sandbox environment at sandbox.adzerk.net
- **Triton**: Contact for test credentials

## Performance Considerations

### Batch Operations
- **GAM**: Batch create up to 500 line items
- **Kevel**: Single API calls only
- **Triton**: Batch reporting available

### Caching
- **GAM**: Cache geo targeting IDs (rarely change)
- **Kevel**: Cache flight IDs for updates
- **Triton**: Cache campaign structure

## Debugging Tips

1. **Enable Verbose Logging**
   ```bash
   export ADCP_LOG_LEVEL=DEBUG
   ```

2. **Check Platform Limits**
   - GAM: 450 line items per order
   - Kevel: 10,000 flights per campaign
   - Triton: 50 flights per campaign

3. **Validate Targeting**
   - Use platform UI to verify targeting setup
   - Check platform-specific targeting docs
   - Test with minimal targeting first