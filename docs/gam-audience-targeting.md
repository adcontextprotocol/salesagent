# Google Ad Manager Audience Targeting Guide

## Overview

Google Ad Manager (GAM) provides multiple methods for audience targeting, enabling publishers to deliver ads to specific user segments. This guide covers the various audience targeting options available through the AdCP integration.

## Audience Targeting Methods

### 1. Custom Targeting (Key-Value Pairs)

Custom targeting is the most flexible method for audience targeting in GAM. It uses key-value pairs to target specific audience segments.

#### How It Works
- **Keys**: Define the targeting dimension (e.g., "interest", "demographic", "behavior")
- **Values**: Specific segments within that dimension (e.g., "sports", "auto_intender", "high_income")

#### Types of Custom Targeting Keys
- **PREDEFINED**: Values must be pre-defined in GAM
- **FREEFORM**: Values can be passed dynamically without pre-definition

#### Example Usage
```json
{
  "targeting_overlay": {
    "key_value_pairs": {
      "interest": ["sports", "technology"],
      "demographic": ["millennial"],
      "purchase_intent": ["auto_buyer_q1_2025"]
    }
  }
}
```

### 2. First-Party Audience Segments

First-party audiences are created from your own data sources and user interactions.

#### Sources
- **Google Analytics 360**: Website visitor segments
- **Publisher Provided Identifiers (PPID)**: Custom user IDs
- **Tag-based segments**: Users who visited specific pages or performed actions
- **CRM uploads**: Customer lists uploaded to GAM

#### Segment Types
- **RULE_BASED**: Dynamic segments based on user behavior rules
- **SHARED**: Segments shared from other Google products
- **PUBLISHER_PROVIDED**: Custom segments from publisher data

### 3. Third-Party Audience Segments

Third-party audiences come from external data providers integrated with GAM.

#### Common Providers
- **Google Audiences**: Google's aggregated audience data
- **Data Management Platforms (DMPs)**:
  - Oracle BlueKai
  - Adobe Audience Manager
  - Salesforce DMP
  - Lotame
- **Specialized Data Providers**:
  - Nielsen
  - Experian
  - Acxiom

#### Integration Methods
1. **Direct GAM Integration**: Data providers with direct GAM partnerships
2. **Cookie Sync**: Matching user cookies between DMP and GAM
3. **Server-to-Server**: API-based audience segment transfer
4. **Pixel-based**: JavaScript tags for real-time audience qualification

### 4. Google Audiences (Native Integration)

Google provides built-in audience segments available in GAM.

#### Categories
- **Affinity Audiences**: Users with strong interest in specific topics
- **In-Market Audiences**: Users actively researching/shopping
- **Demographics**: Age, gender, parental status, household income
- **Detailed Demographics**: Education, employment, homeownership

#### Example Segments
- "Auto Intenders - Luxury Vehicles"
- "Sports Fans - Basketball"
- "Parents of Young Children (0-6)"
- "Technology Early Adopters"

## Implementation in AdCP

### 1. Discovery

Use the inventory discovery system to find available audience targeting options:

```python
# Discover custom targeting keys
custom_keys = discovery.discover_custom_targeting()

# Discover audience segments
audiences = discovery.discover_audience_segments()
```

### 2. Targeting Configuration

Apply audience targeting through the targeting overlay:

```json
{
  "targeting_overlay": {
    // Custom key-value targeting
    "key_value_pairs": {
      "audience": ["sports_enthusiasts"],
      "interest": ["auto_shopping"]
    },
    
    // Direct audience segment targeting (if supported)
    "audience_segment_ids": ["123456", "789012"],
    
    // Geographic + audience combination
    "geo_country_any_of": ["US"],
    "key_value_pairs": {
      "income": ["high_income"]
    }
  }
}
```

### 3. Best Practices

#### Hierarchy of Targeting
1. Start broad (geography, device)
2. Layer in contextual targeting (ad units, content)
3. Add audience targeting for refinement
4. Avoid over-targeting (limits scale)

#### Performance Optimization
- Test audience segments incrementally
- Monitor fill rates when adding targeting
- Use OR logic for audience groups when possible
- Consider audience size (minimum 1000 users recommended)

#### Privacy Compliance
- Respect user consent for behavioral targeting
- Follow GDPR/CCPA requirements
- Use Google's privacy-safe audiences when available
- Implement proper data retention policies

## DMP Integration Patterns

### 1. Real-Time Bidding (RTB) Integration
```
User Visit → DMP Pixel Fires → Audience Qualification → 
GAM Receives Segment ID → Ad Decision
```

### 2. Batch Upload Pattern
```
DMP Export → CSV/API Transfer → GAM Audience Import → 
Daily Segment Refresh
```

### 3. Server-Side Integration
```
Publisher Server → DMP API Call → Audience Segments → 
Pass to GAM via GPT Parameters
```

## Troubleshooting

### Common Issues

1. **Low Fill Rate**
   - Audience segment too small
   - Over-restrictive targeting combination
   - Segment not properly synced

2. **Audience Not Matching**
   - Cookie sync issues between DMP and GAM
   - Segment refresh delays
   - Privacy/consent blocking

3. **Performance Issues**
   - Too many key-value pairs (limit 20 per request)
   - Complex audience logic
   - Real-time lookup latency

### Debugging Steps

1. Check audience segment size in GAM UI
2. Verify key-value pairs are properly formatted
3. Test with GAM's preview tool
4. Review delivery diagnostics for targeting issues
5. Check audience match rates in reporting

## Code Examples

### Creating Media Buy with Audience Targeting

```python
# Using custom targeting
result = await client.tools.create_media_buy(
    product_ids=["premium_display"],
    total_budget=10000,
    flight_start_date="2025-02-01",
    flight_end_date="2025-02-28",
    targeting_overlay={
        "geo_country_any_of": ["US"],
        "key_value_pairs": {
            "audience": ["sports_fans", "auto_intenders"],
            "income": ["affluent"],
            "behavior": ["frequent_shoppers"]
        }
    }
)

# Using signals (AdCP v2.4+)
result = await client.tools.create_media_buy(
    product_ids=["targeted_video"],
    total_budget=15000,
    flight_start_date="2025-02-01",
    flight_end_date="2025-02-28",
    targeting_overlay={
        "geo_country_any_of": ["US", "CA"],
        "signals": [
            "auto_intenders_q1_2025",
            "sports_enthusiasts",
            "high_value_consumers"
        ]
    }
)
```

### Discovering Available Audiences

```python
# Get all targeting options
targeting_data = inventory_service.get_all_targeting_data(tenant_id)

# Browse custom targeting
for key in targeting_data['customKeys']:
    print(f"Key: {key['name']} ({key['type']})")
    for value in targeting_data['customValues'][key['id']]:
        print(f"  - {value['display_name']}")

# Browse audience segments
for audience in targeting_data['audiences']:
    print(f"Audience: {audience['name']}")
    print(f"  Type: {audience['type']}")
    print(f"  Size: {audience['size']:,}" if audience['size'] else "  Size: Unknown")
```

## Conclusion

GAM's audience targeting capabilities provide powerful tools for reaching specific user segments. The key to success is:

1. Understanding available targeting methods
2. Properly implementing data integrations
3. Balancing targeting precision with scale
4. Monitoring performance and optimizing
5. Maintaining privacy compliance

The AdCP integration provides comprehensive access to these targeting capabilities through a standardized interface, making it easier to implement sophisticated audience targeting strategies across different ad serving platforms.