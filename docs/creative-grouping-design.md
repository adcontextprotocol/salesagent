# Creative Grouping Design for AdCP Sales Agent

## Research Summary

Based on research of major ad servers, here's how creative management works across platforms:

### Google Ad Manager
- **Creative Library**: Centralized repository shared across advertiser
- **Line Item Creative Associations**: Links between library creatives and line items
- **Override Capability**: Can override settings (click-through URL, dates) per association
- **Display Control**: "One or more", "Only one", "As many as possible", "All"
- **Creative Sets**: Support for previewing master creative IDs

### Kevel (formerly Adzerk)
- **Creative-Flight-Ad Model**: Creative → Ad (via Flight mapping)
- **Multiple Creatives per Flight**: Full support with percentage goals
- **Creative Reuse**: Same creative can be mapped to multiple flights
- **Distribution Control**: Percentage-based serving within flights

### Triton Digital TAP
- **Integration with Frequency**: Advanced creative management platform
- **Multiple Creatives per Flight**: Supported with rotation options
- **Distribution Rules**: Weighted or sequential rotation
- **Targeting per Creative**: Can apply rules to specific creatives

## Proposed Creative Group Hierarchy

### Design Goals
1. Support creative reuse across media buys/packages
2. Enable rotation and distribution control
3. Maintain principal isolation
4. Support adapter-specific features
5. Provide grouping for organizational purposes

### Proposed Schema

```python
# Creative Group - organizational container
class CreativeGroup(BaseModel):
    """Groups creatives for organizational and management purposes."""
    group_id: str
    principal_id: str
    name: str
    description: Optional[str]
    created_at: datetime
    tags: Optional[List[str]] = []  # For filtering/organization

# Enhanced Creative model
class Creative(BaseModel):
    """Individual creative asset."""
    creative_id: str
    principal_id: str
    group_id: Optional[str]  # Optional group membership
    format_id: str
    content_uri: str
    name: str
    click_through_url: Optional[str]
    metadata: Optional[Dict[str, Any]] = {}  # Platform-specific metadata
    status: CreativeStatus
    created_at: datetime
    updated_at: datetime

# Creative Assignment with enhanced control
class CreativeAssignment(BaseModel):
    """Maps creatives to packages with distribution control."""
    assignment_id: str
    media_buy_id: str
    package_id: str
    creative_id: str
    
    # Distribution control
    weight: Optional[int] = 100  # Relative weight for rotation
    percentage_goal: Optional[float] = None  # Percentage of impressions
    rotation_type: Optional[Literal["weighted", "sequential", "even"]] = "weighted"
    
    # Override settings (platform-specific)
    override_click_url: Optional[str] = None
    override_start_date: Optional[datetime] = None
    override_end_date: Optional[datetime] = None
    
    # Targeting override (creative-specific targeting)
    targeting_overlay: Optional[Targeting] = None
    
    is_active: bool = True
```

### Key Features

#### 1. Creative Library
- Creatives exist independently of media buys
- Can be organized into groups for easier management
- Reusable across multiple packages/media buys

#### 2. Assignment Flexibility
- Map same creative to multiple packages
- Control distribution within package (weight/percentage)
- Override settings per assignment without changing base creative

#### 3. Rotation Strategies
- **Weighted**: Serve based on relative weights
- **Sequential**: Rotate in order
- **Even**: Equal distribution

#### 4. Platform Mapping

**Google Ad Manager**:
- Creative → GAM Creative object
- CreativeAssignment → LineItemCreativeAssociation
- weight/percentage → Creative rotation settings

**Kevel**:
- Creative → Kevel Creative
- CreativeAssignment → Ad (Creative-Flight mapping)
- percentage_goal → Flight percentage goals

**Triton Digital**:
- Creative → TAP Creative asset
- CreativeAssignment → Flight-Creative mapping
- rotation_type → TAP rotation rules

## Implementation Plan

### Phase 1: Core Models
1. Add CreativeGroup and enhanced Creative models
2. Add CreativeAssignment model
3. Update database schema

### Phase 2: API Updates
1. Add `create_creative_group` tool
2. Add `create_creative` tool (separate from media buy)
3. Add `assign_creative` tool
4. Add `get_creatives` tool with group filtering
5. Update `submit_creatives` to handle assignments

### Phase 3: Adapter Updates
1. Update MockAdapter to demonstrate grouping
2. Update GAM adapter for LineItemCreativeAssociation
3. Update Kevel adapter for Ad creation
4. Update Triton adapter for creative mapping

### Phase 4: Admin Features
1. Add admin view for pending creatives
2. Add approval workflow
3. Add creative performance reporting

## Benefits

1. **Reusability**: Same creative across multiple campaigns
2. **Flexibility**: Override settings without duplicating creatives
3. **Organization**: Group creatives by campaign, theme, format
4. **Performance**: Track creative performance across uses
5. **Efficiency**: Reduce duplicate uploads to platforms

## Migration Path

For existing implementations:
1. Current `creative_assignments` dict becomes CreativeAssignment records
2. Creatives in media buys get extracted to library
3. Maintain backward compatibility with legacy endpoints