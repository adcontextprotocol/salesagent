# Google Ad Manager Integration Plan - First Media Buy

## Executive Summary

This document outlines a step-by-step plan for executing our first Google Ad Manager (GAM) media buy through the AdCP Sales Agent. The initial implementation will focus on simple display creatives running on lightly-targeted, non-guaranteed line items.

## Pre-Flight Checklist

### 1. GAM Account Setup
- [ ] Service account created with proper permissions
- [ ] Network code verified
- [ ] Company ID confirmed
- [ ] Trafficker user account created and ID obtained
- [ ] Test advertiser created in GAM
- [ ] Ad units and placements configured

### 2. AdCP Configuration
- [ ] Tenant created with GAM adapter enabled
- [ ] Principal created with GAM advertiser ID mapping
- [ ] Product configured with basic display formats
- [ ] Service account key file securely stored
- [ ] Implementation config validated

### 3. Technical Validation
- [ ] GAM API client can authenticate successfully
- [ ] Can query existing advertisers
- [ ] Can list ad units and placements
- [ ] Geo mapping files loaded correctly
- [ ] Database connections working

## Step-by-Step Execution Plan

### Phase 1: Configuration Validation (Day 1)

#### 1.1 Validate Tenant Configuration
```json
{
  "adapters": {
    "google_ad_manager": {
      "enabled": true,
      "network_code": "123456",
      "service_account_key_file": "/path/to/key.json",
      "company_id": "789012",
      "trafficker_id": "345678"
    }
  }
}
```

#### 1.2 Validate Principal Mapping
```json
{
  "principal_id": "test_advertiser",
  "name": "Test Advertiser Inc",
  "platform_mappings": {
    "gam": {
      "advertiser_id": "111222333"
    }
  }
}
```

#### 1.3 Validate Product Configuration
```json
{
  "product_id": "display_run_of_network",
  "name": "Display - Run of Network",
  "formats": ["display_300x250", "display_728x90"],
  "implementation_config": {
    "order_name_template": "AdCP-{po_number}-{timestamp}",
    "line_item_type": "STANDARD",
    "priority": 8,
    "cost_type": "CPM",
    "creative_placeholders": [
      {"width": 300, "height": 250, "expected_creative_count": 1},
      {"width": 728, "height": 90, "expected_creative_count": 1}
    ],
    "targeted_ad_unit_ids": ["123456", "789012"],
    "include_descendants": true,
    "frequency_caps": [
      {"max_impressions": 3, "time_unit": "DAY", "time_range": 1}
    ]
  }
}
```

### Phase 2: Dry Run Testing (Day 2)

#### 2.1 Test Order Creation
```bash
# Run dry-run simulation
python run_simulation.py --dry-run --adapter gam
```

Expected output:
- Order creation API call details
- Line item configuration
- Targeting parameters
- No actual GAM API calls made

#### 2.2 Validate API Call Structure
Check that dry-run logs show:
- Correct advertiser ID
- Proper order structure
- Valid line item configuration
- Appropriate targeting

### Phase 3: GAM Environment Preparation (Day 3)

#### 3.1 Create Test Ad Units
In GAM UI:
1. Create test ad unit hierarchy
2. Note ad unit IDs for configuration
3. Set up appropriate inventory categorization

#### 3.2 Configure Trafficking Settings
1. Create advertiser if not exists
2. Set up company relationships
3. Configure user permissions
4. Enable necessary features

#### 3.3 Set Up Test Creatives
1. Prepare 300x250 test creative
2. Prepare 728x90 test creative
3. Ensure click-through URLs are valid
4. Test creative upload separately

### Phase 4: First Live Test (Day 4)

#### 4.1 Create Minimal Media Buy
```python
# Test parameters
{
  "product_ids": ["display_run_of_network"],
  "total_budget": 100.00,  # $100 test budget
  "flight_start_date": "2025-02-01",
  "flight_end_date": "2025-02-07",  # 1 week test
  "targeting_overlay": {
    "geo_country_any_of": ["US"],
    "frequency_caps": [
      {"max_impressions": 1, "time_unit": "DAY", "time_range": 1}
    ]
  }
}
```

#### 4.2 Monitor Creation Process
1. Watch server logs for API calls
2. Verify order created in GAM UI
3. Check line item configuration
4. Confirm targeting applied correctly

#### 4.3 Upload Test Creatives
1. Use simple image creatives
2. Verify creative approval status
3. Check creative-line item associations
4. Test preview in GAM

### Phase 5: Validation & Monitoring (Day 5)

#### 5.1 Verify in GAM UI
- [ ] Order appears with correct name
- [ ] Budget matches request
- [ ] Flight dates are accurate
- [ ] Line items created properly
- [ ] Targeting applied correctly
- [ ] Creatives associated

#### 5.2 Test Delivery
1. Use GAM preview tool
2. Check forecasting numbers
3. Verify no conflicts
4. Test creative rendering

#### 5.3 Monitor Initial Delivery
1. Wait for first impressions
2. Check delivery reports
3. Verify pacing
4. Monitor for errors

## Error Handling Strategy

### Common GAM Errors and Responses

1. **Authentication Errors**
   - Error: `AUTHENTICATION_ERROR`
   - Response: Check service account permissions
   - Recovery: Regenerate keys, verify network access

2. **Permission Errors**
   - Error: `PERMISSION_DENIED` 
   - Response: Verify advertiser ID mapping
   - Recovery: Check user roles in GAM

3. **Validation Errors**
   - Error: `INVALID_ARGUMENT`
   - Response: Log full request details
   - Recovery: Adjust parameters based on error

4. **Quota Errors**
   - Error: `QUOTA_EXCEEDED`
   - Response: Implement exponential backoff
   - Recovery: Batch operations, respect limits

## Success Criteria

### Minimum Viable Success
1. ✅ Order created in GAM
2. ✅ Line items properly configured
3. ✅ Creatives uploaded and approved
4. ✅ Targeting applied correctly
5. ✅ First impressions delivered

### Full Success
1. ✅ All API operations logged
2. ✅ Error handling works properly
3. ✅ Delivery reports accurate
4. ✅ Update operations functional
5. ✅ Complete audit trail

## Risk Mitigation

### Technical Risks
1. **API Changes**: Keep SDK updated, monitor deprecations
2. **Rate Limits**: Implement proper throttling
3. **Data Sync**: Regular validation against GAM
4. **Credentials**: Secure storage, rotation plan

### Business Risks
1. **Wrong Advertiser**: Double-check mappings
2. **Budget Overrun**: Set conservative limits
3. **Targeting Errors**: Validate all parameters
4. **Creative Issues**: Pre-approve all assets

## Rollback Plan

If issues occur:
1. **Immediate**: Pause all line items via API
2. **Short-term**: Archive order in GAM
3. **Investigation**: Full audit log review
4. **Fix**: Address root cause
5. **Retry**: New test with fixes

## Post-Launch Monitoring

### Day 1-3
- Hourly delivery checks
- Error log monitoring
- Performance validation
- Pacing verification

### Day 4-7
- Daily summary reports
- Optimization opportunities
- Issue identification
- Process refinement

### Week 2+
- Weekly performance review
- Feature expansion planning
- Scale testing preparation
- Documentation updates

## Next Steps After Success

1. **Expand Targeting**: Test more complex targeting
2. **Multiple Line Items**: Test package variations
3. **Creative Formats**: Add video, native
4. **Budget Management**: Test updates, pauses
5. **Reporting**: Enhance delivery analytics
6. **Scale Testing**: Increase volumes gradually

## Emergency Contacts

- GAM Support: [Define contact]
- Technical Lead: [Define contact]
- Business Owner: [Define contact]
- On-call Engineer: [Define contact]

## Appendix: Test Scripts

### A. Connection Test
```python
# test_gam_connection.py
from adapters.google_ad_manager import GoogleAdManager
from models import Principal

# Test connection only
config = {
    "network_code": "123456",
    "service_account_key_file": "/path/to/key.json",
    "company_id": "789012",
    "trafficker_id": "345678"
}

principal = Principal(
    tenant_id="test_tenant",
    principal_id="test_principal",
    name="Test Principal",
    platform_mappings={"gam": {"advertiser_id": "111222333"}}
)

try:
    adapter = GoogleAdManager(config, principal, dry_run=False)
    print("✅ GAM connection successful")
except Exception as e:
    print(f"❌ GAM connection failed: {e}")
```

### B. Simple Media Buy Test
```python
# test_simple_media_buy.py
import asyncio
from datetime import datetime, timedelta
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test_simple_buy():
    headers = {"x-adcp-auth": "test_token"}
    transport = StreamableHttpTransport(
        url="http://localhost:8080/mcp/", 
        headers=headers
    )
    client = Client(transport=transport)
    
    async with client:
        # Create simple media buy
        result = await client.tools.create_media_buy(
            product_ids=["display_run_of_network"],
            total_budget=100.0,
            flight_start_date=(datetime.now() + timedelta(days=1)).date(),
            flight_end_date=(datetime.now() + timedelta(days=8)).date(),
            targeting_overlay={
                "geo_country_any_of": ["US"]
            }
        )
        print(f"Created media buy: {result.media_buy_id}")
        
asyncio.run(test_simple_buy())
```

## Document Version
- Version: 1.0
- Date: 2025-01-28
- Status: Draft
- Next Review: After first successful test