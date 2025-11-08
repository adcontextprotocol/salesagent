# GAM Targeting Presets vs Inventory Groups Analysis

## Research Summary

I researched Google Ad Manager's **Targeting Presets** feature to determine if we should use it instead of building our own Inventory Groups concept.

## What GAM Targeting Presets Are

### Purpose
Targeting presets are **reusable targeting templates** that save commonly-used targeting configurations. They work like radio preset buttons - you load them to apply saved targeting criteria.

### What They Include
Based on GAM documentation and API references:

1. **Inventory Targeting**
   - Ad units (included/excluded)
   - Placements
   - At least one placement or ad unit required

2. **Geographic Targeting**
   - Countries, regions, metros, cities, postal codes

3. **Device Targeting**
   - Device categories (mobile, desktop, tablet, CTV)

4. **Custom Targeting**
   - Custom key-value pairs

5. **Other Targeting**
   - User domain targeting
   - Browser targeting
   - Operating system targeting
   - Bandwidth targeting
   - Time of day/day of week

### How They Work

**Creation:**
- Managed from: Inventory → Targeting Presets
- Can save new presets directly in the targeting picker when creating line items

**Application:**
- Load preset to apply targeting to line item
- Can make further adjustments after loading
- Can apply multiple presets sequentially
- GAM warns about conflicts

### **CRITICAL LIMITATION** ⚠️

**Non-Dynamic Updates:**
> "Targeting applied from a targeting preset isn't updated with a targeting preset update. Updating or deleting a targeting preset only affects future items that use that preset—not items that previously used that preset."

This means:
- ❌ Updating a preset doesn't update existing line items
- ❌ Presets are **copy-paste templates**, not live references
- ❌ Changes don't propagate to products/line items already using them

## What Inventory Groups Need To Be

Based on our requirements, Inventory Groups need to:

1. **Live References** - Changes propagate to all products using the group ✅ REQUIRED
2. **Inventory + Formats** - Bundle ad units with compatible creative formats ✅ REQUIRED
3. **Properties** - Map inventory to publisher properties (AdCP spec) ✅ REQUIRED
4. **Product-Level** - Used by products, not line items ✅ REQUIRED
5. **Multi-Product Reuse** - One group used by many products ✅ REQUIRED

## Comparison Matrix

| Feature | GAM Targeting Presets | Our Inventory Groups |
|---------|----------------------|---------------------|
| **Scope** | Line item targeting | Product inventory config |
| **Ad Units** | ✅ Yes | ✅ Yes |
| **Placements** | ✅ Yes | ✅ Yes |
| **Creative Formats** | ❌ No | ✅ Yes (REQUIRED) |
| **Properties** | ❌ No | ✅ Yes (AdCP spec) |
| **Live Updates** | ❌ No (copy-paste) | ✅ Yes (REQUIRED) |
| **Used By** | Line items | Products |
| **Targeting Rules** | ✅ Full targeting | ✅ Optional defaults |
| **API Access** | ✅ TargetingPresetService | ❌ (Our custom table) |

## Key Differences

### 1. **Different Abstraction Level**
- **GAM Presets**: Line item targeting (operational level)
- **Inventory Groups**: Product definition (business level)

### 2. **Update Semantics**
- **GAM Presets**: Copy-paste template (no live updates)
- **Inventory Groups**: Live reference (changes propagate)

### 3. **Scope**
- **GAM Presets**: Targeting only (geo, device, custom targeting)
- **Inventory Groups**: Inventory + Formats + Properties + Targeting

### 4. **Use Case**
- **GAM Presets**: "I often target US mobile users on sports placements"
- **Inventory Groups**: "Homepage Premium Display is these ad units with these formats"

## Recommendation: Build Our Own Inventory Groups

### Why Not Use GAM Targeting Presets?

1. **❌ Non-Dynamic Updates**: The biggest dealbreaker
   - We need changes to propagate to all products
   - GAM presets are copy-paste only

2. **❌ Missing Creative Formats**:
   - GAM presets don't include format restrictions
   - We need to bundle formats with inventory

3. **❌ Missing Properties**:
   - GAM presets don't map to publisher properties
   - We need this for AdCP spec compliance

4. **❌ Wrong Abstraction Level**:
   - GAM presets are for line item targeting
   - We need product-level inventory grouping

5. **❌ Limited to GAM**:
   - Targeting presets only exist in GAM
   - Inventory groups should work for Mock, Kevel, etc.

### What We Can Leverage from GAM

Even though we won't use GAM Targeting Presets directly, we can **integrate** with them:

#### Option 1: Import GAM Presets as Targeting Templates
```python
# When creating inventory group, optionally import from GAM preset
def import_from_gam_preset(tenant_id: str, gam_preset_id: str):
    """Import GAM targeting preset as default targeting for inventory group."""
    gam_client = get_gam_client(tenant_id)
    preset = gam_client.targeting_preset_service.get(gam_preset_id)

    # Extract inventory from preset
    inventory_config = {
        "ad_units": preset.inventory_targeting.ad_unit_ids,
        "placements": preset.inventory_targeting.placement_ids,
        "include_descendants": preset.inventory_targeting.include_descendants
    }

    # Extract other targeting as defaults
    targeting_template = extract_targeting_from_preset(preset)

    return {
        "inventory_config": inventory_config,
        "targeting_template": targeting_template
    }
```

#### Option 2: Sync Inventory Groups → GAM Presets
```python
# When creating/updating inventory group, optionally create/update GAM preset
def sync_to_gam_preset(inventory_group: InventoryGroup):
    """Create/update GAM targeting preset from inventory group."""
    gam_client = get_gam_client(inventory_group.tenant_id)

    preset = {
        "name": inventory_group.name,
        "inventoryTargeting": {
            "targetedAdUnits": inventory_group.inventory_config["ad_units"],
            "targetedPlacements": inventory_group.inventory_config["placements"]
        },
        # Add other targeting from targeting_template
        **convert_targeting_template_to_gam(inventory_group.targeting_template)
    }

    if inventory_group.gam_preset_id:
        gam_client.targeting_preset_service.update(preset)
    else:
        result = gam_client.targeting_preset_service.create(preset)
        inventory_group.gam_preset_id = result.id
```

## Proposed Architecture

### Our Inventory Groups (Primary)
```python
class InventoryGroup(Base):
    id: int
    name: str
    inventory_config: dict  # Ad units + placements
    formats: list[dict]  # Creative formats (GAM presets don't have this)
    publisher_properties: list[dict]  # AdCP properties (GAM presets don't have this)
    targeting_template: dict  # Optional defaults

    # Optional: Reference to GAM preset for sync
    gam_preset_id: str | None
    gam_preset_sync_enabled: bool = False
```

### Integration Points

1. **Import from GAM** (Initial setup):
   ```
   User clicks: "Import from GAM Targeting Preset"
   → Fetch preset from GAM API
   → Extract inventory and targeting
   → User adds formats and properties
   → Save as inventory group
   ```

2. **Sync to GAM** (Optional):
   ```
   User enables: "Sync to GAM Targeting Preset"
   → Create/update GAM preset with inventory and targeting
   → Keep gam_preset_id for future updates
   → When group changes, update GAM preset
   ```

3. **Apply to Line Items** (Automatic):
   ```
   When creating line item from product:
   → Use inventory group's inventory_config
   → Apply targeting_template as base
   → Add product-specific targeting overlays
   → (Optionally) Also apply GAM preset if it exists
   ```

## Benefits of Our Approach

### 1. **Live References**
- Update inventory group → all products updated instantly
- No stale configurations

### 2. **Adapter-Agnostic**
- Works for Mock, Kevel, future adapters
- Not tied to GAM-specific concepts

### 3. **Complete Package**
- Inventory + Formats + Properties + Targeting
- Everything needed for product definition

### 4. **AdCP Spec Compliant**
- `publisher_properties` structure matches spec
- Can derive properties from ad units

### 5. **Optional GAM Integration**
- Can import from GAM presets (one-way)
- Can sync to GAM presets (two-way)
- But not dependent on GAM

## Implementation Plan

### Phase 1: Core Inventory Groups
- [ ] Create `inventory_groups` table
- [ ] Build inventory groups UI
- [ ] Update product form to use groups
- [ ] Implement live reference logic

### Phase 2: GAM Integration (Optional)
- [ ] Add "Import from GAM Preset" button
- [ ] Implement GAM preset fetching via API
- [ ] Add optional "Sync to GAM" toggle
- [ ] Implement bidirectional sync logic

### Phase 3: Enhanced Features
- [ ] Auto-derive properties from ad units
- [ ] Inventory group health checks (stale inventory detection)
- [ ] Bulk operations (apply group to multiple products)

## Conclusion

**We should build our own Inventory Groups concept** rather than relying on GAM Targeting Presets because:

1. ✅ **Live references** (GAM presets are copy-paste only)
2. ✅ **Complete package** (inventory + formats + properties)
3. ✅ **Adapter-agnostic** (works beyond just GAM)
4. ✅ **Product-level** (right abstraction for our use case)
5. ✅ **AdCP compliant** (matches spec requirements)

**However**, we should consider **optional GAM integration**:
- Import from GAM presets (to leverage existing setup)
- Sync to GAM presets (to keep GAM UI in sync)
- But our inventory groups are the source of truth

This gives users who already have GAM presets a migration path, while providing better functionality than GAM presets alone can offer.
