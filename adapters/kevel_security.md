# Kevel Security Perimeter

## Overview

The Kevel adapter implements security boundaries to ensure principals can only access and modify their own campaigns and flights. This document outlines the security mechanisms.

## Principal Mapping

Each AdCP principal maps to a Kevel advertiser ID:

```python
# Principal configuration example:
{
    "principal_id": "publisher_xyz",
    "name": "Publisher XYZ",
    "platform_mappings": {
        "kevel": {
            "advertiser_id": "98765"
        }
    }
}
```

## Security Enforcement

### 1. Advertiser ID Isolation

All Kevel API calls include the advertiser ID from the principal:

```python
# Create Campaign
campaign_payload = {
    "AdvertiserId": int(self.advertiser_id),  # From principal mapping
    "Name": f"AdCP Campaign {media_buy_id}",
    # ...
}
```

This ensures:
- Campaigns are created under the correct advertiser
- Flights inherit advertiser context from campaigns
- Resources are isolated by advertiser

### 2. API Key Security

The Kevel adapter uses:
- Network-level API key for authentication
- Advertiser ID for resource isolation

```python
self.headers = {
    "X-Adzerk-ApiKey": self.api_key,
    "Content-Type": "application/json"
}
```

### 3. Media Buy Tracking

Similar to GAM, the system tracks ownership:

```python
# Media buy creation stores principal association
{
    "media_buy_id": "kevel_12345",
    "principal_id": "publisher_xyz",
    "campaign_id": 12345
}
```

### 4. Creative Management

Creative operations are secured by:
- Association with advertiser-owned flights only
- Template-based creative system respects advertiser boundaries
- Direct URL creatives validated for advertiser ownership

### 5. Reporting Access

Delivery reports are filtered to:
- Only show campaigns owned by the advertiser
- Aggregate at the advertiser level
- Respect Kevel's built-in permissions

## Feature-Based Security

### UserDB Integration

When `userdb_enabled: true`:
- Audience segments are namespaced by network
- Interest targeting uses advertiser-specific segments
- No cross-advertiser audience sharing

```python
# Interest targeting example
'$user.interests CONTAINS "Sports Fans"'  # Network-namespaced
```

### Frequency Capping

When `frequency_capping_enabled: true`:
- Caps apply only to the advertiser's flights
- No visibility into other advertisers' frequency data
- User-level data remains anonymous

## Configuration Security

### Required Configuration

```json
{
    "adapter": "kevel",
    "network_id": "YOUR_NETWORK_ID",
    "api_key": "YOUR_API_KEY",
    "userdb_enabled": false,
    "frequency_capping_enabled": false
}
```

Security considerations:
- `api_key`: Should have minimal required permissions
- `network_id`: Identifies the Kevel network scope
- Feature flags control access to advanced features

## Best Practices

1. **API Key Management**: 
   - Use environment variables for API keys
   - Rotate keys regularly
   - Never commit keys to version control

2. **Advertiser Validation**:
   - Verify advertiser exists before operations
   - Handle advertiser mismatch errors gracefully

3. **Feature Flags**:
   - Only enable UserDB if properly configured
   - Validate audience segments exist before use

4. **Error Handling**:
   - Never expose internal Kevel IDs in errors
   - Log security violations for audit

## Limitations

- Cannot create new advertisers via API
- Cannot access network-level settings
- Cannot modify priority levels (fixed at 5)
- Subject to Kevel API rate limits

## Audit Trail

All operations logged with:
```
Kevel.create_media_buy for principal 'Publisher XYZ' (Kevel advertiser ID: 98765)
Creating campaign with ID: kevel_12345
```

## Data Isolation

The adapter ensures:
- No cross-advertiser data access
- Campaign/flight queries filtered by advertiser
- Creative associations respect ownership
- Reporting data isolated by advertiser