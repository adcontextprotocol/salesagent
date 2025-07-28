# Triton Digital Security Perimeter

## Overview

The Triton Digital adapter enforces security boundaries specific to audio advertising campaigns. This document details the security implementation for the TAP (Triton Advertising Platform) integration.

## Principal Mapping

Each AdCP principal maps to a Triton advertiser entity:

```python
# Principal configuration example:
{
    "principal_id": "audio_brand_123",
    "name": "Audio Brand ABC",
    "platform_mappings": {
        "triton": {
            "advertiser_id": "TRITON_ADV_789"
        }
    }
}
```

## Security Enforcement

### 1. Advertiser Isolation

All TAP API calls include advertiser context:

```python
# Campaign creation with advertiser ID
campaign_data = {
    "name": f"AdCP Campaign {request.po_number}",
    "advertiser_id": self.advertiser_id,  # From principal mapping
    "budget": request.total_budget,
    # ...
}
```

### 2. Authentication & Authorization

The adapter uses:
- Bearer token authentication
- Advertiser-scoped permissions

```python
self.headers = {
    "Authorization": f"Bearer {self.auth_token}",
    "Content-Type": "application/json"
}
```

### 3. Station-Level Security

Audio campaigns have additional security considerations:

```python
# Station targeting is validated against advertiser permissions
"targeting": {
    "stations": ["WABC-FM", "WXYZ-AM"],  # Must be authorized stations
    "dayparts": targeting.get("dayparts", [])
}
```

The adapter ensures:
- Only authorized stations can be targeted
- Station-advertiser relationships are validated
- No cross-network station access

### 4. Audio Creative Security

Audio-specific security measures:
- Audio files uploaded to advertiser-specific storage
- VAST URLs generated with secure tokens
- Companion banners linked to audio spots

```python
creative_data = {
    "advertiser_id": self.advertiser_id,
    "name": asset['name'],
    "audio_url": asset['url'],  # Must be from approved CDN
    "duration": asset.get('duration', 30)
}
```

### 5. Reporting Boundaries

Delivery reports respect:
- Station-level permissions
- Advertiser data isolation
- Aggregation rules for competitive separation

## Audio-Specific Security

### Stream Targeting

- Live streams vs. podcast targeting isolated
- Station ownership validated
- Format restrictions enforced (AM/FM/Digital)

### Daypart Security

Audio dayparts have special handling:
- Drive time slots require station approval
- Premium inventory access controlled
- Local vs. national separation

### Audience Data

When audience targeting is enabled:
- First-party data remains advertiser-specific
- Third-party segments require authorization
- No cross-advertiser audience sharing

## Configuration Security

### Required Configuration

```json
{
    "adapter": "triton_digital",
    "base_url": "https://tap-api.tritondigital.com/v1",
    "auth_token": "YOUR_AUTH_TOKEN",
    "advertiser_id": "TRITON_ADV_789"
}
```

Security notes:
- `auth_token`: Should be advertiser-scoped
- `base_url`: Always use HTTPS
- Token should have minimal required scopes

## Best Practices

1. **Token Management**:
   - Use OAuth2 flow for token generation
   - Implement token refresh logic
   - Store tokens securely

2. **Station Validation**:
   - Verify station permissions before targeting
   - Handle market exclusivity rules
   - Respect competitive separation

3. **Audio File Security**:
   - Validate audio file sources
   - Enforce duration limits
   - Check encoding standards

4. **Error Handling**:
   - Never expose station IDs in errors
   - Log permission violations
   - Handle rate limits gracefully

## Limitations

- Cannot create new advertisers
- Cannot access competitive campaigns
- Station targeting requires pre-authorization
- Subject to inventory availability

## Audit Trail

Operations are logged with context:
```
Triton.create_media_buy for principal 'Audio Brand ABC' (Triton advertiser ID: TRITON_ADV_789)
Creating audio campaign with budget: $50,000
Targeting stations: WABC-FM, WXYZ-AM
```

## Data Protection

The adapter ensures:
- No cross-advertiser data leakage
- Station performance data isolation
- Audience insights remain advertiser-specific
- Competitive separation maintained

## Special Considerations

### Podcast vs. Broadcast

- Podcast campaigns have different security model
- Dynamic ad insertion requires special tokens
- Download tracking isolated by advertiser

### Local Market Protection

- DMA-level exclusivity enforced
- Local advertiser protection
- National vs. local inventory separation

### Real-Time Bidding

When RTB is enabled:
- Bid requests filtered by advertiser
- Win notifications isolated
- Pricing data protected