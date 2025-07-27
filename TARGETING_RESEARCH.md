# AdCP Targeting Capabilities Research

## Overview
This document researches the targeting capabilities of each ad server adapter to design a robust, unified targeting system for AdCP.

## Current AdCP Targeting Schema

From schemas.py:
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

## Google Ad Manager (GAM)

### Supported Targeting Types:
1. **Geographic Targeting**
   - Countries, regions, cities, postal codes
   - DMA (Designated Market Areas)
   - Custom geo-targeting with lat/long radius

2. **Device & Technology**
   - Device categories (desktop, mobile, tablet, connected TV)
   - Operating systems
   - Browsers
   - Device manufacturers and models
   - Bandwidth targeting

3. **Inventory Targeting**
   - Ad units
   - Placements
   - Key-values (custom targeting)

4. **Content & Category**
   - Content targeting (URLs, topics)
   - Video content (for video line items)
   - Mobile app categories

5. **Audience Targeting**
   - First-party audiences
   - Third-party audience segments
   - Custom audience segments
   - Similar audiences

6. **Time-based**
   - Day and time targeting (dayparting)
   - Date ranges

7. **Frequency Capping**
   - Impressions per time period per user

### GAM Implementation Notes:
- Uses a complex targeting object structure
- Supports AND/OR logic for combining criteria
- Key-value targeting is very flexible for custom attributes

## Kevel (formerly Adzerk)

### Supported Targeting Types:
1. **Geographic Targeting**
   - Country
   - Region/State
   - Metro/DMA
   - City
   - IP-based targeting

2. **Device & Platform**
   - Device type
   - Operating system
   - Browser

3. **Site/Zone Targeting**
   - Specific sites
   - Specific zones (ad placements)
   - Channels (groups of sites)

4. **Keywords & Categories**
   - Keyword targeting
   - Site categories

5. **Custom Targeting**
   - Custom fields (similar to key-values)
   - User-based targeting with UserDB

6. **Frequency & Pacing**
   - Frequency caps
   - Even pacing options

### Kevel Implementation Notes:
- Uses "Flight" level targeting
- Supports custom targeting via their UserDB
- Real-time decision engine allows dynamic targeting

## Triton Digital (TAP - Triton Advertising Platform)

### Supported Targeting Types:
1. **Geographic Targeting**
   - Country
   - State/Province
   - DMA
   - City

2. **Audio-Specific Targeting**
   - Station/Stream targeting
   - Genre targeting
   - Daypart targeting (drive time, etc.)
   - Live vs on-demand content

3. **Device & Platform**
   - Device type
   - Player/App targeting
   - Connection type

4. **Audience Demographics**
   - Age
   - Gender
   - Household income (where available)

5. **Behavioral**
   - Listening behavior
   - Content preferences

### Triton Implementation Notes:
- Optimized for audio/streaming advertising
- Strong dayparting capabilities for radio patterns
- Limited compared to display advertising platforms

## Unified Targeting Design Recommendations

### 1. Core Targeting Types (Supported by All)
```python
class CoreTargeting(BaseModel):
    # Geographic - use ISO codes where possible
    geography: GeographicTargeting
    
    # Device/Platform
    devices: DeviceTargeting
    
    # Time-based
    schedule: ScheduleTargeting
```

### 2. Geographic Targeting Structure
```python
class GeographicTargeting(BaseModel):
    include: List[GeographicLocation] = []
    exclude: List[GeographicLocation] = []

class GeographicLocation(BaseModel):
    type: Literal["country", "state", "dma", "city", "postal_code", "custom"]
    value: str  # ISO code or identifier
    # For custom/radius targeting
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: Optional[float] = None
```

### 3. Device Targeting Structure
```python
class DeviceTargeting(BaseModel):
    device_types: List[str] = []  # desktop, mobile, tablet, ctv, audio_player
    operating_systems: List[str] = []
    browsers: List[str] = []
    connection_types: List[str] = []  # wifi, cellular, broadband
```

### 4. Schedule/Dayparting Structure
```python
class ScheduleTargeting(BaseModel):
    timezone: str  # IANA timezone
    day_parting: List[DayPart] = []
    
class DayPart(BaseModel):
    days: List[int]  # 0=Monday, 6=Sunday
    start_hour: int  # 0-23
    end_hour: int    # 0-23
```

### 5. Extended Targeting (Platform-Specific)
```python
class ExtendedTargeting(BaseModel):
    # Content/Contextual
    content_categories: List[str] = []
    keywords: List[str] = []
    
    # Audience
    audience_segments: List[AudienceSegment] = []
    
    # Frequency
    frequency_cap: Optional[FrequencyCap] = None
    
    # Platform-specific
    custom: Dict[str, Any] = {}  # For adapter-specific targeting
```

### 6. Adapter Mapping Strategy

Each adapter should:
1. Map common targeting types to their platform-specific format
2. Validate that requested targeting is supported
3. Log warnings for unsupported targeting options
4. Use the `custom` field for platform-specific features

Example mapping for GAM:
- `geography.include` → GAM GeoTargeting
- `devices.device_types` → GAM Technology targeting
- `schedule.day_parting` → GAM DayPartTargeting
- `custom.key_values` → GAM CustomTargeting

## Implementation Plan

1. **Update Targeting Schema**: Enhance the current basic schema with structured sub-types
2. **Create Targeting Validators**: Each adapter validates supported targeting
3. **Add Mapping Methods**: Each adapter implements `_map_targeting()` method
4. **Enhance Dry-Run Output**: Show exactly how targeting maps to each platform
5. **Add Targeting Templates**: Pre-built targeting templates for common use cases

## Next Steps

1. Update schemas.py with enhanced targeting models
2. Implement targeting mapping in each adapter
3. Add validation and warning system
4. Create targeting template library
5. Document targeting capabilities per adapter