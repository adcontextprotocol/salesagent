# Google Ad Manager Publisher Onboarding Checklist

## Overview

This checklist ensures a smooth onboarding process for publishers using Google Ad Manager with the AdCP Sales Agent. Follow each step carefully to avoid issues during the first media buy.

## Pre-Onboarding Requirements

### 1. Publisher Prerequisites
- [ ] Active Google Ad Manager account
- [ ] Network code available
- [ ] Admin access to GAM account
- [ ] Understanding of GAM hierarchy (advertisers, orders, line items)

### 2. Technical Requirements
- [ ] Service account created in Google Cloud Console
- [ ] Service account has necessary GAM API permissions
- [ ] Service account key (JSON) downloaded securely
- [ ] API access enabled in GAM network settings

## Phase 1: GAM Account Setup

### 1.1 Service Account Configuration
```
Required Permissions:
- [ ] View and manage orders
- [ ] View and manage line items
- [ ] View and manage creatives
- [ ] View and manage companies
- [ ] Run reports
- [ ] View inventory
```

### 1.2 Create Dedicated Resources
- [ ] Create AdCP company in GAM (if not exists)
- [ ] Create trafficking user for AdCP operations
- [ ] Note the following IDs:
  - Company ID: _________________
  - Trafficker User ID: _________________
  - Network Code: _________________

### 1.3 Inventory Setup
- [ ] Identify target ad units for AdCP campaigns
- [ ] Create dedicated ad unit hierarchy (optional but recommended)
  ```
  Example structure:
  - Top Level
    └── AdCP Inventory
        ├── Display
        │   ├── Above the Fold
        │   └── Below the Fold
        └── Video
            ├── Pre-roll
            └── Mid-roll
  ```
- [ ] Document ad unit IDs for configuration
- [ ] Set up placements if using placement targeting

### 1.4 Creative Requirements
- [ ] Define accepted creative formats
- [ ] Set creative specifications (sizes, file types, etc.)
- [ ] Configure creative approval workflow
- [ ] Set up competitive exclusion labels (if needed)

## Phase 2: AdCP Configuration

### 2.1 Tenant Setup
```bash
# Create tenant with GAM adapter
python setup_tenant.py "Publisher Name" \
  --adapter google_ad_manager \
  --gam-network-code YOUR_NETWORK_CODE
```

Configuration needed:
```json
{
  "adapters": {
    "google_ad_manager": {
      "enabled": true,
      "network_code": "YOUR_NETWORK_CODE",
      "service_account_key_file": "/secure/path/to/key.json",
      "company_id": "YOUR_COMPANY_ID",
      "trafficker_id": "YOUR_TRAFFICKER_ID",
      "manual_approval_required": false
    }
  }
}
```

### 2.2 Principal Setup
For each advertiser that will use AdCP:
- [ ] Create advertiser in GAM (if not exists)
- [ ] Note advertiser ID
- [ ] Create principal in AdCP with mapping:
  ```json
  {
    "platform_mappings": {
      "gam": {
        "advertiser_id": "ADVERTISER_ID"
      }
    }
  }
  ```

### 2.3 Product Configuration
- [ ] Define products with appropriate targeting
- [ ] Configure GAM implementation settings:
  ```json
  {
    "order_name_template": "AdCP-{po_number}-{timestamp}",
    "line_item_type": "STANDARD",
    "priority": 8,
    "creative_placeholders": [
      {"width": 300, "height": 250, "expected_creative_count": 1}
    ],
    "targeted_ad_unit_ids": ["123456", "789012"],
    "frequency_caps": [
      {"max_impressions": 3, "time_unit": "DAY", "time_range": 1}
    ]
  }
  ```

## Phase 3: Testing & Validation

### 3.1 Connection Test
```bash
# Run health check
python test_gam_connection.py --tenant-id YOUR_TENANT_ID
```

Verify:
- [ ] Authentication successful
- [ ] Can access network information
- [ ] Can query advertisers
- [ ] Can access configured ad units

### 3.2 Dry Run Test
```bash
# Test without making actual API calls
python test_gam_simple_display.py --dry-run
```

Check:
- [ ] Configuration loads correctly
- [ ] Targeting validation passes
- [ ] API call structure is correct

### 3.3 Small Test Campaign
- [ ] Create test campaign with minimal budget ($10-100)
- [ ] Use short flight dates (3-7 days)
- [ ] Target limited inventory
- [ ] Upload simple creatives
- [ ] Monitor in GAM UI

## Phase 4: Production Readiness

### 4.1 Operational Setup
- [ ] Configure monitoring alerts
- [ ] Set up error notifications
- [ ] Document escalation procedures
- [ ] Create runbooks for common issues

### 4.2 Security Review
- [ ] Service account key stored securely
- [ ] Access controls reviewed
- [ ] Audit logging enabled
- [ ] Principal mappings verified

### 4.3 Performance Configuration
- [ ] Rate limiting configured appropriately
- [ ] Timeout values set for network conditions
- [ ] Retry logic tested
- [ ] Batch sizes optimized

### 4.4 Business Rules
- [ ] Budget limits defined
- [ ] Approval workflows configured
- [ ] Targeting restrictions documented
- [ ] Creative policies aligned

## Phase 5: Go-Live

### 5.1 Final Validation
- [ ] Run full integration test
- [ ] Verify reporting accuracy
- [ ] Test update operations
- [ ] Confirm creative approval flow

### 5.2 Launch Configuration
- [ ] Enable production mode
- [ ] Remove test restrictions
- [ ] Configure production budgets
- [ ] Set appropriate rate limits

### 5.3 Monitoring
- [ ] Health checks scheduled
- [ ] Alerts configured
- [ ] Dashboard access provided
- [ ] Support contacts documented

## Common Issues & Solutions

### Authentication Failures
**Symptom**: "PERMISSION_DENIED" or "UNAUTHENTICATED" errors

**Solutions**:
1. Verify service account has correct permissions
2. Check key file path and permissions
3. Ensure API access is enabled in GAM
4. Confirm network code is correct

### Advertiser Access Issues
**Symptom**: Cannot create orders for advertiser

**Solutions**:
1. Verify advertiser exists in GAM
2. Check advertiser ID in principal mapping
3. Ensure advertiser is active
4. Verify company relationships

### Inventory Targeting Problems
**Symptom**: "Invalid ad unit" or targeting errors

**Solutions**:
1. Confirm ad unit IDs are correct
2. Check ad unit status (not archived)
3. Verify include_descendants setting
4. Test with broader targeting first

### Creative Upload Failures
**Symptom**: Creatives rejected or not associated

**Solutions**:
1. Verify creative specifications match
2. Check file size and format limits
3. Ensure click URLs are valid
4. Review creative approval settings

## Support Resources

### Documentation
- [GAM API Documentation](https://developers.google.com/ad-manager/api/start)
- [Service Account Setup Guide](https://cloud.google.com/iam/docs/service-accounts)
- AdCP Integration Guide (this document)

### Contacts
- AdCP Support: support@adcp.com
- Technical Integration: tech@adcp.com
- GAM Support: Via Google Ads support portal

### Tools
- GAM API Test Tool: `test_gam_connection.py`
- Health Check: `gam_health_check.py`
- Dry Run Tester: `test_gam_simple_display.py --dry-run`

## Appendix: Quick Commands

### Check Tenant Configuration
```bash
python -c "
from database import db_session
from models import Tenant
t = db_session.query(Tenant).filter_by(tenant_id='YOUR_TENANT_ID').first()
print(t.config['adapters']['google_ad_manager'])
"
```

### Test Authentication
```bash
python -c "
from adapters.google_ad_manager import GoogleAdManager
from models import Principal
config = {'network_code': 'YOUR_CODE', 'service_account_key_file': 'PATH_TO_KEY'}
principal = Principal(tenant_id='test', principal_id='test', name='Test')
adapter = GoogleAdManager(config, principal, dry_run=False)
print('Success!' if adapter.client else 'Failed!')
"
```

### Run Health Check
```python
from adapters.gam_health_check import GAMHealthChecker
checker = GAMHealthChecker(config)
status, results = checker.run_all_checks()
for result in results:
    print(f"{result.check_name}: {result.status.value}")
```

## Completion Checklist

Before marking onboarding complete:
- [ ] All phases completed successfully
- [ ] Test campaign delivered impressions
- [ ] Reporting data verified accurate
- [ ] Update operations tested
- [ ] Documentation provided to publisher
- [ ] Support contacts shared
- [ ] Monitoring enabled
- [ ] Sign-off obtained

**Publisher Sign-off**:
- Name: _______________________
- Date: _______________________
- Signature: __________________