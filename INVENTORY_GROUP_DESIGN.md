# Inventory Group Design Specification

## Problem Statement

Currently, creating products requires manually configuring:
1. Ad units/placements selection
2. Creative format mapping
3. Property authorization
4. Targeting rules

This is **repetitive** when multiple products target the same inventory. Changes require updating every product individually.

## Solution: Inventory Groups

An **Inventory Group** is a reusable, named collection of:
- **Inventory** (ad units, placements)
- **Creative Formats** (which formats work with this inventory)
- **Properties** (which sites/apps/properties this represents)
- **Targeting** (optional default targeting rules)

### Naming

**Inventory Group** vs alternatives:
- ✅ **Inventory Group** - Clear, descriptive
- ✅ **Inventory Package** - Good, but "package" overloaded with media buy packages
- ✅ **Inventory Profile** - Clear
- ❌ **Inventory Template** - Implies one-time use
- ❌ **Ad Unit Group** - Too narrow (also includes placements)

**Recommendation: "Inventory Group"**

## Database Schema

### New Table: `inventory_groups`

```python
class InventoryGroup(Base):
    __tablename__ = "inventory_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False
    )

    # Basic info
    group_id: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "homepage_premium"
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g., "Homepage Premium Display"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inventory selection
    # References ProductInventoryMapping records by inventory_id
    # Structure: {
    #   "ad_units": ["23312403859", "23312403860"],
    #   "placements": ["45678901"],
    #   "include_descendants": true
    # }
    inventory_config: Mapped[dict] = mapped_column(JSONType, nullable=False)

    # Creative formats (FormatId objects)
    # Structure: [{"agent_url": "...", "id": "display_300x250_image"}]
    formats: Mapped[list[dict]] = mapped_column(JSONType, nullable=False)

    # Properties (spec-compliant publisher_properties)
    # Structure: [
    #   {
    #     "publisher_domain": "cnn.com",
    #     "property_ids": ["cnn_homepage"],  # OR
    #     "property_tags": ["premium_news"]
    #   }
    # ]
    publisher_properties: Mapped[list[dict]] = mapped_column(JSONType, nullable=False)

    # Optional default targeting
    # Structure: AdCP targeting object
    targeting_template: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Metadata
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant")
    products = relationship("Product", back_populates="inventory_group")

    __table_args__ = (
        UniqueConstraint("tenant_id", "group_id", name="uq_inventory_group"),
        Index("idx_inventory_groups_tenant", "tenant_id"),
    )
```

### Update `products` Table

```python
class Product(Base):
    # Add reference to inventory group
    inventory_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_groups.id", ondelete="SET NULL"),
        nullable=True
    )

    # Keep custom fields for products that don't use groups
    # (these are ignored if inventory_group_id is set)
    # ... existing fields ...

    # Relationship
    inventory_group = relationship("InventoryGroup", back_populates="products")
```

### Data Flow

**When Product Has Inventory Group:**
```python
def get_product_inventory_config(product):
    if product.inventory_group_id:
        # Use group configuration
        group = product.inventory_group
        return {
            "formats": group.formats,
            "publisher_properties": group.publisher_properties,
            "inventory_config": group.inventory_config,
            "targeting_template": group.targeting_template or product.targeting_template
        }
    else:
        # Use product's custom configuration
        return {
            "formats": product.formats,
            "publisher_properties": derive_from_product(product),
            "inventory_config": product.implementation_config,
            "targeting_template": product.targeting_template
        }
```

**When Inventory Group Changes:**
- All products referencing that group automatically get updated config
- No product data needs to change
- Products can override specific settings (e.g., pricing, targeting)

## User Experience

### Workflow 1: Create Inventory Group First

1. **Navigate to Inventory Browser** (`/admin/tenant/{id}/inventory`)
2. **Select ad units/placements** (checkboxes)
3. **Click "Create Inventory Group from Selection"** (new button)
4. **Fill out form:**
   - Name: "Homepage Premium Display"
   - Description: "Premium homepage inventory across all sections"
   - Creative Formats: Select compatible formats
   - Properties: Map to properties (or auto-derive from ad unit paths)
   - Default Targeting: Optional key-value pairs
5. **Save** → Creates inventory group
6. **Create Product** → Select "Homepage Premium Display" from dropdown
7. **Add pricing/delivery** → Product inherits inventory config

### Workflow 2: Create from Product Form

1. **Navigate to Add Product** (`/admin/tenant/{id}/products/add`)
2. **Inventory section:**
   ```
   ┌─────────────────────────────────────┐
   │ Inventory Configuration             │
   ├─────────────────────────────────────┤
   │ ○ Use Inventory Group (Recommended) │
   │   [Dropdown: Select group...      ▼]│
   │                                     │
   │ ○ Custom Configuration              │
   │   [Browse Ad Units] [Browse Plac.] │
   └─────────────────────────────────────┘
   ```
3. **If "Custom"** → Show existing UI (ad units, placements, formats, properties)
4. **If "Inventory Group"** → Hide inventory selection, show group summary

### Workflow 3: Modify Inventory Group

1. **Navigate to Inventory Groups** (`/admin/tenant/{id}/inventory-groups`)
2. **See list of groups:**
   ```
   Homepage Premium Display
     - 12 ad units, 3 placements
     - 5 creative formats
     - Used by 3 products
     [Edit] [Delete]

   Sports Sidebar Package
     - 8 ad units
     - 4 creative formats
     - Used by 2 products
     [Edit] [Delete]
   ```
3. **Click Edit** → Modify inventory, formats, properties
4. **Save** → All products using this group automatically updated

## UI Components

### New Page: Inventory Groups List

**Route:** `/admin/tenant/{id}/inventory-groups`

**Layout:**
```
┌────────────────────────────────────────────────┐
│ Inventory Groups                    [+ Create] │
├────────────────────────────────────────────────┤
│                                                │
│ ┌─────────────────────────────────────────┐  │
│ │ 📦 Homepage Premium Display             │  │
│ │ Premium homepage inventory across all   │  │
│ │ sections                                │  │
│ │                                         │  │
│ │ Inventory: 12 ad units, 3 placements   │  │
│ │ Formats: Display (300x250, 728x90),    │  │
│ │          Video (Instream)               │  │
│ │ Properties: cnn.com (homepage, news)    │  │
│ │ Used by: 3 products                     │  │
│ │                                         │  │
│ │ [Edit] [Delete] [View Products]        │  │
│ └─────────────────────────────────────────┘  │
│                                                │
│ ┌─────────────────────────────────────────┐  │
│ │ 📦 Sports Sidebar Package               │  │
│ │ ...                                     │  │
│ └─────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

### New Page: Create/Edit Inventory Group

**Route:** `/admin/tenant/{id}/inventory-groups/add`

**Sections:**

1. **Basic Info**
   - Name (required)
   - Description (optional)

2. **Inventory Selection** (reuse inventory browser code)
   - Ad Units (browse/search/select)
   - Placements (browse/search/select)
   - Include descendants checkbox

3. **Creative Formats** (reuse format selector code)
   - Format search/filter
   - Format grid with checkboxes
   - Size filtering from selected inventory

4. **Properties** (NEW - spec-compliant)
   ```
   Publisher Properties (Which sites/apps?)

   ┌─────────────────────────────────────┐
   │ Publisher Domain: cnn.com           │
   │                                     │
   │ Coverage:                           │
   │ ○ Specific Properties               │
   │   [Select: homepage, politics, ...]│
   │                                     │
   │ ○ Property Tags                     │
   │   [Input: premium_news, breaking]  │
   │                                     │
   │ ○ Auto-derive from ad units ✓      │
   │   Preview: homepage, news, sports   │
   └─────────────────────────────────────┘

   [+ Add Another Publisher Domain]
   ```

5. **Default Targeting** (optional)
   - Key-value pairs
   - Geographic targeting
   - Device targeting

### Updated: Product Form

**Inventory Section Redesign:**

```html
<h3>Inventory Configuration</h3>

<div class="inventory-mode-selector">
  <label>
    <input type="radio" name="inventory_mode" value="group" checked>
    Use Inventory Group (Recommended)
  </label>
  <p>Select a pre-configured inventory group with ad units, formats, and properties.</p>

  <div id="inventory-group-section">
    <select name="inventory_group_id">
      <option value="">Select inventory group...</option>
      {% for group in inventory_groups %}
      <option value="{{ group.id }}">
        {{ group.name }}
        ({{ group.inventory_summary }})
      </option>
      {% endfor %}
    </select>

    <!-- Show group preview when selected -->
    <div id="group-preview" style="display: none;">
      <div class="group-summary">
        <h4>Selected Group: <span id="group-name"></span></h4>
        <div id="group-details">
          <!-- Populated via JS -->
        </div>
      </div>
    </div>
  </div>
</div>

<div class="inventory-mode-selector">
  <label>
    <input type="radio" name="inventory_mode" value="custom">
    Custom Configuration
  </label>
  <p>Manually configure ad units, placements, formats, and properties for this product only.</p>

  <div id="inventory-custom-section" style="display: none;">
    <!-- Existing UI: ad units, placements, formats, properties -->
  </div>
</div>
```

**JavaScript:**
```javascript
// Toggle between group/custom mode
function toggleInventoryMode() {
  const mode = document.querySelector('input[name="inventory_mode"]:checked').value;

  if (mode === 'group') {
    document.getElementById('inventory-group-section').style.display = 'block';
    document.getElementById('inventory-custom-section').style.display = 'none';
  } else {
    document.getElementById('inventory-group-section').style.display = 'none';
    document.getElementById('inventory-custom-section').style.display = 'block';
  }
}

// Load group preview
async function loadGroupPreview(groupId) {
  const response = await fetch(`/admin/tenant/${tenantId}/inventory-groups/${groupId}/preview`);
  const group = await response.json();

  document.getElementById('group-name').textContent = group.name;
  document.getElementById('group-details').innerHTML = `
    <div><strong>Inventory:</strong> ${group.ad_unit_count} ad units, ${group.placement_count} placements</div>
    <div><strong>Formats:</strong> ${group.format_names.join(', ')}</div>
    <div><strong>Properties:</strong> ${group.property_summary}</div>
  `;
  document.getElementById('group-preview').style.display = 'block';
}
```

## Backend Implementation

### New Blueprint: `inventory_groups.py`

```python
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for

inventory_groups_bp = Blueprint("inventory_groups", __name__)

@inventory_groups_bp.route("/")
@require_tenant_access()
def list_inventory_groups(tenant_id):
    """List all inventory groups for this tenant."""
    with get_db_session() as session:
        groups = session.scalars(
            select(InventoryGroup)
            .filter_by(tenant_id=tenant_id)
            .order_by(InventoryGroup.name)
        ).all()

        # Count products using each group
        groups_data = []
        for group in groups:
            product_count = session.scalar(
                select(func.count())
                .select_from(Product)
                .where(Product.inventory_group_id == group.id)
            )

            groups_data.append({
                "id": group.id,
                "group_id": group.group_id,
                "name": group.name,
                "description": group.description,
                "inventory_summary": get_inventory_summary(group),
                "format_summary": get_format_summary(group),
                "property_summary": get_property_summary(group),
                "product_count": product_count,
            })

        return render_template(
            "inventory_groups_list.html",
            tenant_id=tenant_id,
            groups=groups_data
        )

@inventory_groups_bp.route("/add", methods=["GET", "POST"])
@require_tenant_access()
def add_inventory_group(tenant_id):
    """Create new inventory group."""
    if request.method == "POST":
        # Parse form data
        form_data = sanitize_form_data(request.form.to_dict())

        # Create inventory group
        group = InventoryGroup(
            tenant_id=tenant_id,
            group_id=form_data.get("group_id") or generate_group_id(form_data["name"]),
            name=form_data["name"],
            description=form_data.get("description"),
            inventory_config=parse_inventory_config(form_data),
            formats=parse_formats(form_data),
            publisher_properties=parse_publisher_properties(form_data),
            targeting_template=parse_targeting_template(form_data)
        )

        with get_db_session() as session:
            session.add(group)
            session.commit()

        flash(f"Inventory group '{group.name}' created successfully!", "success")
        return redirect(url_for("inventory_groups.list_inventory_groups", tenant_id=tenant_id))

    # GET: Show form
    return render_template(
        "add_inventory_group.html",
        tenant_id=tenant_id,
        formats=get_creative_formats(tenant_id),
        authorized_properties=get_authorized_properties(tenant_id)
    )

@inventory_groups_bp.route("/<int:group_id>/edit", methods=["GET", "POST"])
@require_tenant_access()
def edit_inventory_group(tenant_id, group_id):
    """Edit existing inventory group."""
    # Similar to add, but pre-populate form
    pass

@inventory_groups_bp.route("/<int:group_id>/delete", methods=["DELETE"])
@require_tenant_access()
def delete_inventory_group(tenant_id, group_id):
    """Delete inventory group."""
    with get_db_session() as session:
        group = session.get(InventoryGroup, group_id)

        if not group or group.tenant_id != tenant_id:
            return jsonify({"error": "Inventory group not found"}), 404

        # Check if any products use this group
        product_count = session.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.inventory_group_id == group_id)
        )

        if product_count > 0:
            return jsonify({
                "error": f"Cannot delete inventory group - used by {product_count} product(s)"
            }), 400

        session.delete(group)
        session.commit()

    return jsonify({"success": True, "message": "Inventory group deleted successfully"})

@inventory_groups_bp.route("/<int:group_id>/preview")
@require_tenant_access(api_mode=True)
def preview_inventory_group(tenant_id, group_id):
    """Get inventory group preview for product form."""
    with get_db_session() as session:
        group = session.get(InventoryGroup, group_id)

        if not group or group.tenant_id != tenant_id:
            return jsonify({"error": "Inventory group not found"}), 404

        return jsonify({
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "ad_unit_count": len(group.inventory_config.get("ad_units", [])),
            "placement_count": len(group.inventory_config.get("placements", [])),
            "format_names": get_format_names(group.formats),
            "property_summary": get_property_summary(group),
        })
```

### Helper Functions

```python
def get_inventory_summary(group: InventoryGroup) -> str:
    """Generate human-readable inventory summary."""
    config = group.inventory_config
    ad_units = len(config.get("ad_units", []))
    placements = len(config.get("placements", []))

    parts = []
    if ad_units:
        parts.append(f"{ad_units} ad unit{'s' if ad_units != 1 else ''}")
    if placements:
        parts.append(f"{placements} placement{'s' if placements != 1 else ''}")

    return ", ".join(parts) or "No inventory"

def get_format_summary(group: InventoryGroup) -> str:
    """Generate human-readable format summary."""
    from src.core.format_resolver import get_format

    format_names = []
    for fmt in group.formats:
        try:
            format_obj = get_format(fmt["id"], fmt["agent_url"], group.tenant_id)
            format_names.append(format_obj.name)
        except:
            format_names.append(fmt["id"])

    return ", ".join(format_names[:3]) + (f" (+{len(format_names) - 3} more)" if len(format_names) > 3 else "")

def get_property_summary(group: InventoryGroup) -> str:
    """Generate human-readable property summary."""
    props = group.publisher_properties

    if not props:
        return "No properties"

    # Collect all domains
    domains = [p["publisher_domain"] for p in props]

    # Collect property IDs and tags
    all_ids = []
    all_tags = []
    for p in props:
        all_ids.extend(p.get("property_ids", []))
        all_tags.extend(p.get("property_tags", []))

    parts = []
    parts.append(f"{len(domains)} domain{'s' if len(domains) != 1 else ''}")
    if all_ids:
        parts.append(f"{len(all_ids)} propert{'ies' if len(all_ids) != 1 else 'y'}")
    if all_tags:
        parts.append(f"{len(all_tags)} tag{'s' if len(all_tags) != 1 else ''}")

    return ", ".join(parts)
```

## Migration Strategy

### Phase 1: Add Inventory Groups (Non-Breaking)

1. Create `inventory_groups` table
2. Add `inventory_group_id` to `products` table (nullable)
3. Create inventory groups UI
4. Update product form to support both modes
5. Existing products continue to work (use custom config)

### Phase 2: Migrate Existing Products (Optional)

1. Admin can manually create groups from existing product configs
2. Assign products to groups
3. Clean up duplicate configs

### Phase 3: Simplify Product Schema (Breaking)

1. Remove legacy fields from products:
   - `properties` (replaced by group's `publisher_properties`)
   - `property_tags` (replaced by group's `publisher_properties`)
   - Maybe: `formats`, `implementation_config` (if always using groups)
2. Products become lightweight references to inventory groups + pricing/delivery

## Benefits

### For Publishers (Sales Agent Admins)

1. **Less Repetition**: Create inventory config once, reuse across products
2. **Easier Maintenance**: Update inventory group → all products updated
3. **Better Organization**: See all products using a specific inventory set
4. **Faster Product Creation**: Select group + add pricing = done

### For Developers

1. **DRY Code**: Inventory config logic in one place
2. **Cleaner Product Model**: Products focus on pricing/delivery, not inventory
3. **Easier Testing**: Test inventory groups independently
4. **Spec Compliance**: `publisher_properties` structure matches AdCP spec

### For Buyers

1. **Consistent Data**: All products using same group have same property definitions
2. **Clear Property Info**: `publisher_properties` includes `publisher_domain`
3. **Better Validation**: Can validate `adagents.json` authorization

## Edge Cases

### What if product wants to override formats?

**Option 1:** Product-level format overrides (additive)
```python
effective_formats = group.formats + product.additional_formats
```

**Option 2:** Product can switch to custom mode
- Unlink from group
- Copy group config to product
- Edit as custom

**Recommendation:** Start with Option 2 (simpler), add Option 1 if needed

### What if product wants different targeting?

Products already have `targeting_template` field. Logic:
```python
effective_targeting = product.targeting_template or group.targeting_template
```

Product targeting overrides group targeting.

### What if inventory group is deleted?

Prevent deletion if products reference it (show error with product list).

Alternative: Cascade to SET NULL (products become custom config).

### What if ad units in group are deleted from GAM?

Inventory sync should detect this and mark group as "needs review" (stale inventory).

Show warning in inventory groups list: ⚠️ "2 ad units no longer exist"

## Implementation Checklist

- [ ] Create database migration for `inventory_groups` table
- [ ] Add `inventory_group_id` to `products` table
- [ ] Create `InventoryGroup` SQLAlchemy model
- [ ] Create `inventory_groups` blueprint
- [ ] Build inventory groups list UI
- [ ] Build add/edit inventory group form
- [ ] Add "Create Inventory Group" button to inventory browser
- [ ] Update product form with group/custom toggle
- [ ] Update product creation logic to handle groups
- [ ] Add group preview API endpoint
- [ ] Update `get_products` to return group-based config
- [ ] Add deletion protection for groups with products
- [ ] Write tests for inventory group CRUD
- [ ] Write tests for product-group relationship
- [ ] Document inventory group workflow in admin guide
