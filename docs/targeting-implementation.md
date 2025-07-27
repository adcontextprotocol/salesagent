# AdCP Targeting Capabilities Documentation

## Overview

AdCP provides a unified targeting interface that maps to platform-specific capabilities across Google Ad Manager, Kevel, and Triton Digital. This document details the targeting options and their platform mappings.

## Current Targeting Schema

```python
class Targeting(BaseModel):
    content_categories_include: List[str] = []
    content_categories_exclude: List[str] = []
    keywords_include: List[str] = []
    keywords_exclude: List[str] = []
    geography: List[str] = []
    device_types: List[str] = []
    platforms: List[str] = []
    audiences: List[str] = []
    dayparting: Optional[Dict[str, Any]] = None
    frequency_cap: Optional[Dict[str, Any]] = None
    custom: Optional[Dict[str, Any]] = None
```

## Targeting Categories

### 1. Geographic Targeting

**Supported Formats:**
- Country codes: `"US"`, `"CA"`, `"GB"`
- State/Province: `"US-CA"`, `"CA-ON"`
- DMA codes: `"DMA-501"` (New York)
- City names: `"city:New York,NY"`
- Postal codes: `"postal:10001"`

**Platform Support:**
| Platform | Country | State | DMA | City | Postal |
|----------|---------|-------|-----|------|--------|
| GAM | ✓ | ✓ | ✓ | ✓ | ✓ |
| Kevel | ✓ | ✓ | ✓ | ✓ | Limited |
| Triton | ✓ | ✓ | ✓ | ✓ | - |

**Example:**
```python
"geography": ["US", "US-CA", "US-NY", "DMA-501"]
```

### 2. Device Targeting

**Supported Values:**
- `"desktop"` - Desktop computers
- `"mobile"` - Mobile phones
- `"tablet"` - Tablet devices
- `"ctv"` - Connected TV
- `"audio_player"` - Audio streaming devices

**Platform Mapping:**
| Device Type | GAM | Kevel | Triton |
|------------|-----|-------|--------|
| desktop | ✓ | ✓ | ✓ |
| mobile | ✓ | ✓ | ✓ |
| tablet | ✓ | ✓ | ✓ |
| ctv | ✓ | Limited | - |
| audio_player | Limited | - | ✓ |

**Example:**
```python
"device_types": ["mobile", "tablet"]
```

### 3. Platform/OS Targeting

**Supported Values:**
- Operating Systems: `"ios"`, `"android"`, `"windows"`, `"macos"`
- Browsers: `"chrome"`, `"safari"`, `"firefox"`, `"edge"`

**Example:**
```python
"platforms": ["ios", "android"]
```

### 4. Content Category Targeting

**IAB Content Categories:**
- `"IAB1"` - Arts & Entertainment
- `"IAB2"` - Automotive
- `"IAB3"` - Business
- `"IAB17"` - Sports
- `"IAB19"` - Technology & Computing

**Example:**
```python
"content_categories_include": ["IAB17", "IAB19"],
"content_categories_exclude": ["IAB7", "IAB14"]  # Exclude Health & Fitness, Society
```

### 5. Keyword Targeting

**Format:**
- Positive keywords: Include in `keywords_include`
- Negative keywords: Include in `keywords_exclude`

**Example:**
```python
"keywords_include": ["sports", "basketball", "nba"],
"keywords_exclude": ["injury", "scandal"]
```

### 6. Audience Targeting

**Types:**
- First-party segments: `"crm:high_value_customers"`
- Third-party segments: `"3p:auto_intenders"`
- Behavioral segments: `"behavior:frequent_travelers"`
- Demographic segments: `"demo:parents_young_children"`

**Platform Support:**
- **GAM**: Full support via Audience Solutions
- **Kevel**: Support via UserDB integration
- **Triton**: Limited to audio listener segments

**Example:**
```python
"audiences": ["crm:loyalty_members", "3p:sports_enthusiasts"]
```

### 7. Dayparting (Time-based Targeting)

**Format:**
```python
"dayparting": {
    "timezone": "America/New_York",
    "schedules": [
        {
            "days": [1, 2, 3, 4, 5],  # Monday-Friday
            "start_hour": 6,
            "end_hour": 10
        },
        {
            "days": [1, 2, 3, 4, 5],  # Monday-Friday
            "start_hour": 16,
            "end_hour": 19
        }
    ]
}
```

**Special Values for Audio (Triton):**
- `"drive_time_morning"`: 6 AM - 10 AM
- `"drive_time_evening"`: 4 PM - 7 PM
- `"midday"`: 10 AM - 3 PM
- `"evening"`: 7 PM - 12 AM

### 8. Frequency Capping

**Format:**
```python
"frequency_cap": {
    "impressions": 3,
    "period": "day",  # "hour", "day", "week", "month"
    "per": "user"     # "user", "ip", "household"
}
```

**Platform Support:**
- **GAM**: Full support, including cross-device
- **Kevel**: User-level and IP-based
- **Triton**: Session and day-level for audio

### 9. Custom Targeting

Platform-specific targeting that doesn't fit standard categories:

**Google Ad Manager:**
```python
"custom": {
    "key_values": {
        "content_rating": ["pg", "pg13"],
        "content_genre": ["action", "drama"]
    },
    "inventory_targeting": {
        "ad_unit_ids": ["12345", "67890"]
    }
}
```

**Kevel:**
```python
"custom": {
    "site_ids": [123, 456],
    "zone_ids": [789, 1011],
    "custom_fields": {
        "subscriber_type": "premium"
    }
}
```

**Triton Digital:**
```python
"custom": {
    "station_ids": ["WABC-FM", "KABC-AM"],
    "genres": ["rock", "talk"],
    "stream_types": ["live", "podcast"]
}
```

## Complete Example

```python
targeting = {
    "geography": ["US", "US-CA", "US-NY"],
    "device_types": ["mobile", "desktop"],
    "platforms": ["ios", "android"],
    "content_categories_include": ["IAB17", "IAB19"],
    "keywords_include": ["sports", "technology"],
    "keywords_exclude": ["gambling"],
    "audiences": ["3p:sports_fans", "behavior:early_adopters"],
    "dayparting": {
        "timezone": "America/New_York",
        "schedules": [
            {
                "days": [0, 6],  # Weekends
                "start_hour": 9,
                "end_hour": 22
            }
        ]
    },
    "frequency_cap": {
        "impressions": 5,
        "period": "day",
        "per": "user"
    }
}
```

## Platform Limitations

### Google Ad Manager
- Most comprehensive targeting options
- Requires pre-defined geo targeting IDs
- Complex key-value setup needed for custom targeting

### Kevel
- Real-time targeting decisions
- Limited third-party data integrations
- Strong custom field support

### Triton Digital
- Audio-focused targeting
- Limited device targeting (audio players only)
- Strong daypart and genre targeting

## Best Practices

1. **Start Broad, Then Narrow**: Begin with broader targeting and refine based on performance.

2. **Platform Awareness**: Understand which targeting features are available on your chosen platform.

3. **Combine Targeting Types**: Use multiple targeting dimensions for precise audience reach.

4. **Monitor Performance**: Use performance indices to identify which targeting combinations work best.

5. **Frequency Caps**: Always set appropriate frequency caps to avoid ad fatigue.

6. **Geographic Precision**: Use the most specific geographic targeting available for local campaigns.

7. **Custom Fields**: Leverage platform-specific custom targeting for unique use cases.