# GAM Line Item Fields Analysis

## Executive Summary

When creating GAM line items from media products, numerous technical fields are required that aren't visible to users in the AdCP protocol. These fields must be stored in the `implementation_config` JSONB field of the Product model.

## Critical Fields Already Identified

### 1. **Line Item Priority** (CRITICAL)
- **Field**: `priority`
- **Type**: Integer (1-16, where 1 is highest)
- **User Visibility**: Hidden from users
- **Why Needed**: Determines which line item wins when multiple compete for same impression
- **Default**: 8 (middle priority)
- **Use Cases**:
  - Guaranteed inventory: Priority 4-6
  - Non-guaranteed: Priority 8-12
  - House ads: Priority 16

### 2. **Inventory Targeting** (REQUIRED)
GAM requires all line items to target specific inventory. Cannot be empty.

#### Ad Units
- **Field**: `targeted_ad_unit_ids`
- **Type**: Array of GAM ad unit IDs (strings)
- **Additional**: `include_descendants` (boolean, default true)
- **Why Needed**: Specifies which ad units can serve this inventory
- **Fallback**: Network root ad unit (if not specified)

#### Placements
- **Field**: `targeted_placement_ids`
- **Type**: Array of GAM placement IDs (strings)
- **Why Needed**: Alternative to ad units for grouping inventory
- **Use Case**: Pre-defined placement packages

### 3. **Creative Placeholders** (REQUIRED)
- **Field**: `creative_placeholders`
- **Type**: Array of objects with:
  - `width`: Integer
  - `height`: Integer
  - `expected_creative_count`: Integer (default 1)
  - `is_native`: Boolean (determines NATIVE vs PIXEL)
- **Why Needed**: GAM must know what creative sizes to expect
- **Default**: `[{width: 300, height: 250, expected_creative_count: 1}]`

### 4. **Line Item Type** (CRITICAL)
- **Field**: `line_item_type`
- **Type**: String enum
- **Values**:
  - Guaranteed: `STANDARD`, `SPONSORSHIP`
  - Non-guaranteed: `NETWORK`, `BULK`, `PRICE_PRIORITY`, `HOUSE`
- **Why Needed**: Determines billing, priority ranges, and approval workflows
- **Default**: `STANDARD`
- **Business Impact**: Guaranteed types require manual activation approval

### 5. **Cost Type**
- **Field**: `cost_type`
- **Type**: String enum
- **Values**: `CPM`, `CPC`, `CPD` (cost per day), `CPU` (cost per unit), `VCPM` (viewable CPM)
- **Default**: `CPM`
- **Why Needed**: Determines how GAM calculates billing

### 6. **Goal Settings**
Controls delivery pacing and targets.

#### Primary Goal Type
- **Field**: `primary_goal_type`
- **Type**: String enum
- **Values**: `DAILY`, `LIFETIME`, `NONE`
- **Why Needed**: How GAM paces delivery
- **Constraint**: `DAILY` requires flight duration ≥ 3 days
- **Default**: `DAILY` (fallback to `LIFETIME` if flight < 3 days)

#### Primary Goal Unit Type
- **Field**: `primary_goal_unit_type`
- **Type**: String enum
- **Values**: `IMPRESSIONS`, `CLICKS`, `VIEWABLE_IMPRESSIONS`
- **Default**: `IMPRESSIONS`

### 7. **Creative Rotation Type**
- **Field**: `creative_rotation_type`
- **Type**: String enum
- **Values**: `EVEN`, `OPTIMIZED`, `WEIGHTED`, `SEQUENTIAL`
- **Default**: `EVEN`
- **Why Needed**: How GAM rotates multiple creatives

### 8. **Delivery Rate Type**
- **Field**: `delivery_rate_type`
- **Type**: String enum
- **Values**: `EVENLY`, `FRONTLOADED`, `AS_FAST_AS_POSSIBLE`
- **Default**: `EVENLY`
- **Why Needed**: Pacing strategy within the day

## Advanced Optional Fields

### 9. **Frequency Caps**
Limits how often users see ads.
- **Field**: `frequency_caps`
- **Type**: Array of objects:
  - `max_impressions`: Integer
  - `time_range`: Integer (number of time units)
  - `time_unit`: String (`MINUTE`, `HOUR`, `DAY`, `WEEK`, `MONTH`, `LIFETIME`)
- **Example**: `[{max_impressions: 3, time_range: 1, time_unit: "DAY"}]`
- **Use Case**: Premium inventory, brand safety

### 10. **Custom Targeting**
Key-value pairs for custom targeting dimensions.
- **Field**: `custom_targeting_keys`
- **Type**: Object/Dictionary
- **Why Needed**: Publisher-specific targeting (e.g., content categories, custom segments)
- **Integration**: Merged with AdCP overlay targeting

### 11. **Competitive Exclusion Labels**
Prevents competing brands from showing together.
- **Field**: `competitive_exclusion_labels`
- **Type**: Array of GAM label IDs (strings)
- **Use Case**: Brand safety, competitive separation

### 12. **Discount Settings**
Applied discounts to the line item.
- **Field**: `discount_type`
- **Type**: String enum: `PERCENTAGE`, `ABSOLUTE_VALUE`
- **Field**: `discount_value`
- **Type**: Float
- **Use Case**: Sales promotions, negotiated rates

### 13. **Video-Specific Settings**
Required for video line items.

#### Environment Type
- **Field**: `environment_type`
- **Type**: String enum: `BROWSER`, `VIDEO_PLAYER`
- **Default**: `BROWSER`
- **Required For**: Video ads

#### Video Duration
- **Field**: `video_max_duration`
- **Type**: Integer (milliseconds)
- **Use Case**: Pre-roll, mid-roll specifications

#### Skippability
- **Field**: `skip_offset`
- **Type**: Integer (milliseconds) - when skip button appears
- **Note**: Requires `videoSkippableAdType: ENABLED`

#### Companion Ads
- **Field**: `companion_delivery_option`
- **Type**: String enum: `OPTIONAL`, `AT_LEAST_ONE`, `ALL`, `UNKNOWN`
- **Use Case**: Video ads with display companions

### 14. **Advanced Delivery Controls**

#### Allow Overbook
- **Field**: `allow_overbook`
- **Type**: Boolean
- **Default**: False
- **Why Needed**: Allow guaranteed line items to exceed available inventory forecasts
- **Risk**: May under-deliver if forecast is wrong

#### Skip Inventory Check
- **Field**: `skip_inventory_check`
- **Type**: Boolean
- **Default**: False
- **Use Case**: When you're confident about inventory availability

#### Disable Viewability Optimization
- **Field**: `disable_viewability_avg_revenue_optimization`
- **Type**: Boolean
- **Why Needed**: Prevent GAM from optimizing delivery based on viewability predictions

## Mapping: Product Fields → Line Item Creation

### User-Visible Fields (From AdCP Protocol)
These are visible to buyers in AdCP and stored in product table directly:
- `name` → line item name
- `cpm` → costPerUnit
- `delivery_type` → influences line_item_type selection
- `formats` → drives creative_placeholders generation
- `targeting_template` → base targeting (before overlay)

### Hidden Technical Fields (implementation_config)
These are internal trafficking requirements stored in `implementation_config`:

**Always Required:**
1. `priority` - Line item priority (1-16)
2. `targeted_ad_unit_ids` or `targeted_placement_ids` - Inventory targeting
3. `creative_placeholders` - Creative size specifications
4. `line_item_type` - GAM line item type

**Commonly Required:**
5. `cost_type` - Billing method (default CPM)
6. `primary_goal_type` - Delivery pacing strategy
7. `primary_goal_unit_type` - What to optimize for
8. `creative_rotation_type` - Multi-creative rotation
9. `delivery_rate_type` - Intra-day pacing

**Product-Specific:**
10. `custom_targeting_keys` - Publisher custom targeting
11. `frequency_caps` - Frequency capping rules
12. `competitive_exclusion_labels` - Competitive separation
13. Video fields (if applicable): `environment_type`, `video_max_duration`, `skip_offset`, `companion_delivery_option`
14. Advanced controls: `allow_overbook`, `skip_inventory_check`, `disable_viewability_avg_revenue_optimization`

## Recommendations

### 1. UI Enhancement Priority

**High Priority** (Required for basic functionality):
- Line item priority selector (1-16)
- Inventory targeting (ad units or placements)
- Creative placeholder builder (sizes and counts)
- Line item type selector (guaranteed vs non-guaranteed)

**Medium Priority** (Improves flexibility):
- Goal type settings (DAILY vs LIFETIME)
- Creative rotation strategy
- Delivery rate type
- Frequency cap builder

**Low Priority** (Advanced use cases):
- Custom targeting key-value editor
- Competitive exclusion label selector
- Video-specific settings panel
- Advanced delivery controls

### 2. Default Value Strategy

Create sensible defaults based on product `delivery_type`:

**For Guaranteed Products:**
```json
{
  "line_item_type": "STANDARD",
  "priority": 6,
  "cost_type": "CPM",
  "primary_goal_type": "DAILY",
  "primary_goal_unit_type": "IMPRESSIONS",
  "creative_rotation_type": "EVEN",
  "delivery_rate_type": "EVENLY"
}
```

**For Non-Guaranteed Products:**
```json
{
  "line_item_type": "PRICE_PRIORITY",
  "priority": 10,
  "cost_type": "CPM",
  "primary_goal_type": "NONE",
  "primary_goal_unit_type": "IMPRESSIONS",
  "creative_rotation_type": "OPTIMIZED",
  "delivery_rate_type": "AS_FAST_AS_POSSIBLE"
}
```

### 3. Validation Requirements

Before creating line items, validate:
1. ✅ Inventory targeting is not empty (ad units or placements)
2. ✅ Creative placeholders match product formats
3. ✅ Priority is appropriate for line item type
4. ✅ If DAILY goal type, flight duration ≥ 3 days
5. ✅ Video fields present if environment_type is VIDEO_PLAYER
6. ✅ Frequency caps have valid time units and ranges

### 4. Admin UI Enhancements

**Product Configuration Page** should have sections:

1. **Basic Settings** (visible to users via AdCP)
   - Name, description, formats, pricing

2. **GAM Trafficking Configuration** (hidden from AdCP buyers)
   - Line item priority
   - Line item type
   - Inventory targeting (ad units/placements browser)
   - Creative specifications

3. **Advanced GAM Settings** (collapsible)
   - Goal and pacing controls
   - Frequency capping
   - Custom targeting
   - Video settings (if applicable)
   - Delivery overrides

### 5. Implementation Considerations

**Database:**
- All these fields stored in `products.implementation_config` JSONB column
- No schema changes needed - already flexible

**Code Changes Needed:**
- Admin UI form for editing implementation_config
- Validation logic for required fields
- Default value generation based on delivery_type
- Line item creation code to consume these fields (already exists in original GAM adapter)

**Migration Path:**
- Existing products may have null/empty implementation_config
- Add migration to populate defaults based on delivery_type
- Admin UI should highlight products missing required trafficking fields

## Example implementation_config

### Standard Display Product
```json
{
  "line_item_type": "STANDARD",
  "priority": 6,
  "cost_type": "CPM",
  "targeted_ad_unit_ids": ["12345678", "23456789"],
  "include_descendants": true,
  "creative_placeholders": [
    {
      "width": 300,
      "height": 250,
      "expected_creative_count": 3,
      "is_native": false
    },
    {
      "width": 728,
      "height": 90,
      "expected_creative_count": 2,
      "is_native": false
    }
  ],
  "primary_goal_type": "DAILY",
  "primary_goal_unit_type": "IMPRESSIONS",
  "creative_rotation_type": "EVEN",
  "delivery_rate_type": "EVENLY",
  "frequency_caps": [
    {
      "max_impressions": 5,
      "time_range": 1,
      "time_unit": "DAY"
    }
  ]
}
```

### Video Pre-Roll Product
```json
{
  "line_item_type": "STANDARD",
  "priority": 8,
  "cost_type": "CPM",
  "environment_type": "VIDEO_PLAYER",
  "targeted_placement_ids": ["98765432"],
  "creative_placeholders": [
    {
      "width": 640,
      "height": 480,
      "expected_creative_count": 1,
      "is_native": false
    }
  ],
  "video_max_duration": 30000,
  "skip_offset": 5000,
  "companion_delivery_option": "OPTIONAL",
  "primary_goal_type": "DAILY",
  "primary_goal_unit_type": "IMPRESSIONS",
  "creative_rotation_type": "EVEN",
  "delivery_rate_type": "EVENLY"
}
```

### Programmatic Non-Guaranteed
```json
{
  "line_item_type": "PRICE_PRIORITY",
  "priority": 12,
  "cost_type": "CPM",
  "targeted_ad_unit_ids": ["11111111"],
  "include_descendants": true,
  "creative_placeholders": [
    {
      "width": 300,
      "height": 250,
      "expected_creative_count": 1,
      "is_native": false
    }
  ],
  "primary_goal_type": "NONE",
  "primary_goal_unit_type": "IMPRESSIONS",
  "creative_rotation_type": "OPTIMIZED",
  "delivery_rate_type": "AS_FAST_AS_POSSIBLE",
  "custom_targeting_keys": {
    "content_category": ["sports", "news"],
    "page_type": ["article"]
  }
}
```

## Next Steps

1. **Phase 1: Core Fields UI**
   - Build admin form for priority, line item type, and inventory targeting
   - Add defaults generation for new products
   - Implement validation before line item creation

2. **Phase 2: Creative Placeholders**
   - UI to map product formats to GAM creative placeholders
   - Auto-generation based on formats field
   - Manual override capability

3. **Phase 3: Advanced Settings**
   - Frequency cap builder
   - Custom targeting editor
   - Video settings panel

4. **Phase 4: Inventory Browser**
   - Integration with GAM inventory sync
   - Browse ad units and placements
   - Auto-suggest based on product characteristics
