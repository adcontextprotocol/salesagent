# Google Ad Manager Security Perimeter

## Overview

The Google Ad Manager adapter enforces strict security boundaries to ensure that each principal can only access and modify their own advertising resources. This document details the security mechanisms in place.

## Principal Mapping

Every AdCP principal is mapped to a specific Google Ad Manager advertiser ID:

```python
# Principal configuration example:
{
    "principal_id": "acme_corp",
    "name": "ACME Corporation",
    "platform_mappings": {
        "gam": {
            "advertiser_id": "123456789"
        }
    }
}
```

## Security Enforcement

### 1. Advertiser ID Isolation

All API calls to Google Ad Manager include the advertiser ID from the principal's mapping:

```python
# Create Order (Campaign)
order = {
    'advertiserId': self.advertiser_id,  # From principal mapping
    'name': f'AdCP Order {media_buy_id}',
    # ...
}
```

This ensures that:
- Orders are created under the correct advertiser
- Line items inherit the advertiser from their parent order
- Creatives are associated with the correct advertiser

### 2. Media Buy Ownership Verification

The system maintains a database mapping of media buy IDs to principal IDs:

```python
# In main.py _verify_principal()
if media_buys[media_buy_id]["principal_id"] != principal_id:
    raise PermissionError(f"Principal '{principal_id}' does not own media buy '{media_buy_id}'.")
```

This prevents:
- Cross-principal media buy access
- Unauthorized updates or deletions
- Data leakage between advertisers

### 3. Read Operations

When fetching data from Google Ad Manager:

```python
# Get line items for a specific order
statement = (self.client.new_statement_builder()
             .where('orderId = :orderId')
             .with_bind_variable('orderId', int(media_buy_id)))
```

The adapter:
- Only queries resources owned by the principal's advertiser
- Filters results to ensure no cross-advertiser data exposure
- Uses GAM's built-in permissions model

### 4. Creative Upload Security

Creative assets are:
- Associated with the principal's advertiser ID
- Linked only to line items owned by that advertiser
- Subject to GAM's native security controls

```python
creative = {
    'advertiserId': self.advertiser_id,
    'name': asset['name'],
    # ...
}
```

## Configuration Security

### Service Account Permissions

The GAM service account should have minimal required permissions:
- Order management for specific advertisers only
- Creative upload and association rights
- Reporting access limited to owned resources

### Network-Level Security

The adapter configuration includes:
- `network_code`: Identifies the GAM network
- `service_account_key_file`: Path to secure credentials
- `company_id`: Parent company for advertiser hierarchy
- `trafficker_id`: User ID for audit trail

## Audit Trail

All operations are logged with:
- Principal name and ID
- Advertiser ID used
- Operation performed
- Timestamp

Example:
```
[bold]GoogleAdManager.create_media_buy[/bold] for principal 'ACME Corp' (GAM advertiser ID: 123456789)
```

## Best Practices

1. **Credential Management**: Store service account keys securely, never in version control
2. **Principal Validation**: Always verify principal ownership before operations
3. **Error Handling**: Never expose internal IDs or cross-advertiser data in error messages
4. **Logging**: Maintain detailed audit logs for compliance
5. **Regular Audits**: Periodically review principal mappings and permissions

## Limitations

- Cannot create new advertisers (must be pre-configured)
- Cannot access global network settings
- Cannot modify other advertisers' resources

## Reporting API

### Overview

The GAM adapter includes comprehensive reporting capabilities for retrieving spend and impression data:

- **Date Ranges**: `lifetime` (daily), `this_month` (daily), `today` (hourly)
- **Hierarchical Filtering**: By advertiser, order, or line item
- **Timezone Handling**: Automatic detection and caching of network timezone
- **Data Freshness**: 4-hour delay (per Google documentation)

### API Endpoints

```
GET /api/tenant/{tenant_id}/gam/reporting
GET /api/tenant/{tenant_id}/principals/{principal_id}/gam/reporting
```

### Timezone Behavior

1. **Network Timezone**: Automatically fetched from GAM and cached in adapter config
2. **Report Configuration**: Uses `timeZoneType: 'PUBLISHER'` for consistency
3. **Data Format**:
   - DATE: `YYYY-MM-DD` format
   - HOUR: Integer `0-23`
   - All timestamps in network's timezone

### Currency Handling

- All revenue values in micros (1,000,000 micros = 1 currency unit)
- Automatic conversion in the reporting service

### Security Considerations

- Reports respect principal's advertiser scope
- No cross-advertiser data leakage
- Audit logging for all report requests
- Subject to GAM API rate limits per advertiser
