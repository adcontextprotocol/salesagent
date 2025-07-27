# Adapter Development Guide

This guide explains how to create new ad server adapters for the AdCP:Buy server.

## Overview

Adapters translate between the AdCP protocol and platform-specific APIs. Each adapter inherits from `AdServerAdapter` and implements required methods.

## Base Adapter Class

```python
from adapters.base import AdServerAdapter
from schemas import *

class MyPlatformAdapter(AdServerAdapter):
    adapter_name = "myplatform"  # Used for principal ID mapping
    
    def __init__(self, config, principal, dry_run=False, creative_engine=None):
        super().__init__(config, principal, dry_run, creative_engine)
        
        # Get platform-specific advertiser ID
        self.advertiser_id = self.principal.get_adapter_id("myplatform")
        if not self.advertiser_id:
            raise ValueError(f"Principal {principal.principal_id} needs myplatform_advertiser_id")
```

## Required Methods

### 1. create_media_buy

Convert AdCP packages into platform campaigns/orders.

```python
def create_media_buy(self, request, packages, start_time, end_time):
    """
    Args:
        request: CreateMediaBuyRequest with targeting, budget, etc.
        packages: List[MediaPackage] from get_avails
        start_time/end_time: Campaign flight dates
    
    Returns:
        CreateMediaBuyResponse with media_buy_id and status
    """
    if self.dry_run:
        self.log("Would create campaign in MyPlatform")
        self.log(f"  Budget: ${request.total_budget}")
        self.log(f"  Packages: {len(packages)}")
        return CreateMediaBuyResponse(
            media_buy_id=f"myplatform_{int(time.time())}",
            status="pending_activation"
        )
    
    # Actual API calls here
```

### 2. add_creative_assets

Upload creatives and assign to packages.

```python
def add_creative_assets(self, media_buy_id, assets, today):
    """
    Args:
        media_buy_id: Platform-specific campaign ID
        assets: List of creative assets with metadata
        today: Current date for scheduling
    
    Returns:
        List[AssetStatus] with approval status
    """
    statuses = []
    for asset in assets:
        if self.dry_run:
            self.log(f"Would upload {asset['format']} creative: {asset['name']}")
            statuses.append(AssetStatus(
                creative_id=asset['creative_id'],
                status="approved"
            ))
        else:
            # Platform API call
            # Validate format compatibility
            # Upload and get platform ID
            pass
    return statuses
```

### 3. check_media_buy_status

Monitor campaign state.

```python
def check_media_buy_status(self, media_buy_id, today):
    """
    Returns:
        CheckMediaBuyStatusResponse with current status
    """
    # Status mapping:
    # Platform "DRAFT" -> "pending_activation"
    # Platform "RUNNING" -> "active"
    # Platform "PAUSED" -> "paused"
    # Platform "ENDED" -> "completed"
```

### 4. get_media_buy_delivery

Retrieve performance metrics.

```python
def get_media_buy_delivery(self, media_buy_id, date_range, today):
    """
    Args:
        date_range: ReportingPeriod with start/end dates
    
    Returns:
        AdapterGetMediaBuyDeliveryResponse with metrics
    """
    if self.dry_run:
        # Simulate realistic delivery
        days_elapsed = (today.date() - date_range.start_date).days
        progress = min(days_elapsed / 14, 1.0)
        impressions = int(1000000 * progress * 0.95)  # 95% delivery
        
        return AdapterGetMediaBuyDeliveryResponse(
            totals=DeliveryTotals(
                impressions=impressions,
                spend=impressions * 25 / 1000  # $25 CPM
            )
        )
```

### 5. update_media_buy

Handle standardized update actions.

```python
def update_media_buy(self, media_buy_id, action, package_id, budget, today):
    """
    Supported actions:
    - pause_media_buy / resume_media_buy
    - pause_package / resume_package  
    - update_package_budget
    - update_package_impressions
    """
    if action not in ["pause_media_buy", "resume_media_buy", ...]:
        return UpdateMediaBuyResponse(
            status="failed",
            reason=f"Action '{action}' not supported"
        )
    
    if self.dry_run:
        self.log(f"Would execute {action} in MyPlatform")
        # Show the actual API call that would be made
    
    # Platform-specific implementation
```

## Configuration

Add your adapter to `config.json`:

```json
{
  "adapters": {
    "myplatform": {
      "api_key": "your-api-key",
      "api_endpoint": "https://api.myplatform.com/v1",
      "custom_field": "value"
    }
  }
}
```

## Principal Mapping

Principals need platform-specific IDs in the database:

```sql
UPDATE principals 
SET myplatform_advertiser_id = '12345'
WHERE principal_id = 'acme_corp';
```

## Dry Run Mode

Always implement dry run support:

```python
if self.dry_run:
    self.log("Would call: POST /api/campaigns")
    self.log(f"  Payload: {json.dumps(payload, indent=2)}")
    return mock_response
else:
    response = requests.post(url, json=payload)
    return parse_response(response)
```

## Testing Your Adapter

1. **Unit Tests**: See `tests/test_adapters.py`
2. **Dry Run**: Set `ADCP_DRY_RUN=true` and verify output
3. **Integration**: Test with real API in staging
4. **Simulation**: Run `simulation_full.py` with your adapter

## Platform Considerations

### Targeting Mapping
- Map AdCP targeting to platform-specific format
- Log warnings for unsupported targeting
- Use `custom` field for platform-specific options

### Status Normalization
- Convert platform statuses to AdCP values
- Handle platform-specific edge cases
- Provide meaningful error messages

### Creative Validation
- Check format compatibility upfront
- Validate technical specifications
- Handle platform-specific requirements

## Example: Minimal Adapter

```python
class MinimalAdapter(AdServerAdapter):
    adapter_name = "minimal"
    
    def create_media_buy(self, request, packages, start_time, end_time):
        media_buy_id = f"minimal_{uuid.uuid4()}"
        self.log(f"Created minimal campaign: {media_buy_id}")
        return CreateMediaBuyResponse(
            media_buy_id=media_buy_id,
            status="active"  # No approval needed
        )
    
    def add_creative_assets(self, media_buy_id, assets, today):
        return [AssetStatus(
            creative_id=a['creative_id'], 
            status="approved"
        ) for a in assets]
    
    def check_media_buy_status(self, media_buy_id, today):
        return CheckMediaBuyStatusResponse(
            media_buy_id=media_buy_id,
            status="active"
        )
    
    def get_media_buy_delivery(self, media_buy_id, date_range, today):
        # Simple linear delivery
        campaign_days = 14
        elapsed = (today.date() - date_range.start_date).days
        progress = min(elapsed / campaign_days, 1.0)
        
        return AdapterGetMediaBuyDeliveryResponse(
            totals=DeliveryTotals(
                impressions=int(1000000 * progress),
                spend=10000 * progress
            )
        )
    
    def update_media_buy_performance_index(self, media_buy_id, package_performance):
        self.log("Performance index received")
        return True
    
    def update_media_buy(self, media_buy_id, action, package_id, budget, today):
        self.log(f"Update action: {action}")
        return UpdateMediaBuyResponse(status="accepted")
```

## Best Practices

1. **Error Handling**: Always return meaningful errors
2. **Logging**: Use `self.log()` for dry run compatibility
3. **Validation**: Check inputs before API calls
4. **Idempotency**: Make operations repeatable
5. **Documentation**: Comment platform-specific behavior