# Admin UI - Pricing Options TODO

## Current State
Product creation forms (`add_product.html`, `add_product_gam.html`, `edit_product.html`) only show legacy pricing fields:
- CPM field
- Delivery type (guaranteed/non_guaranteed)
- Price guidance (for non-guaranteed)

## What Needs to be Added

### 1. General Product Form (`templates/add_product.html` and `edit_product.html`)
Add a "Pricing Options" section that allows creating multiple pricing options:

```html
<h3>Pricing Options (AdCP PR #88)</h3>
<div id="pricing-options-container">
  <!-- Repeatable pricing option form -->
  <div class="pricing-option">
    <select name="pricing_model[]">
      <option value="cpm">CPM</option>
      <option value="cpcv">CPCV</option>
      <option value="cpp">CPP</option>
      <option value="cpc">CPC</option>
      <option value="cpv">CPV</option>
      <option value="flat_rate">Flat Rate</option>
    </select>

    <input name="currency[]" placeholder="USD">

    <label>
      <input type="radio" name="pricing_type_0" value="fixed"> Fixed
      <input type="radio" name="pricing_type_0" value="auction"> Auction
    </label>

    <!-- If fixed -->
    <input name="rate[]" placeholder="Rate">

    <!-- If auction -->
    <input name="floor[]" placeholder="Floor CPM">
    <input name="p50[]" placeholder="Median (optional)">

    <!-- Optional -->
    <input name="min_spend_per_package[]" placeholder="Min spend">

    <!-- Parameters based on pricing model -->
    <div class="pricing-parameters">
      <!-- Show/hide based on selected pricing_model -->
    </div>

    <button type="button" onclick="removePricingOption(this)">Remove</button>
  </div>
</div>
<button type="button" onclick="addPricingOption()">+ Add Pricing Option</button>

<!-- Keep legacy fields for backward compatibility -->
<details>
  <summary>Legacy Pricing (Deprecated)</summary>
  <!-- Existing CPM / is_fixed_price fields -->
</details>
```

### 2. GAM Product Form (`templates/add_product_gam.html`)
Similar to above, but:
- Show warning: "GAM adapter currently only supports CPM pricing models"
- Disable non-CPM options or show info message
- Still allow creating pricing_options (validation will work, GAM just won't use them yet)

### 3. Backend Routes
Update product creation/editing routes to handle `pricing_options` form data:

**File**: `src/admin/blueprints/products.py`

```python
# In add_product route
pricing_options_data = []
for i in range(len(request.form.getlist('pricing_model[]'))):
    option = {
        'pricing_model': request.form.getlist('pricing_model[]')[i],
        'currency': request.form.getlist('currency[]')[i],
        'is_fixed': request.form.getlist(f'pricing_type_{i}')[0] == 'fixed',
        'rate': float(request.form.getlist('rate[]')[i]) if request.form.getlist('rate[]')[i] else None,
        'price_guidance': {
            'floor': float(request.form.getlist('floor[]')[i])
        } if request.form.getlist('floor[]')[i] else None,
        # etc.
    }
    pricing_options_data.append(option)

# Create PricingOption database records
for option_data in pricing_options_data:
    pricing_option = PricingOption(
        tenant_id=tenant_id,
        product_id=product_id,
        **option_data
    )
    session.add(pricing_option)
```

### 4. JavaScript for Dynamic Forms
Add JavaScript to:
- Add/remove pricing options dynamically
- Show/hide rate vs floor based on fixed/auction selection
- Show model-specific parameters (demographic for CPP, view_threshold for CPV, etc.)
- Validate form before submission

### 5. Edit Product
When editing, load existing pricing_options from database and populate form.

## Implementation Priority
1. **Backend support** (highest) - Routes to save/load pricing_options
2. **Basic UI** - Add/remove pricing options, core fields
3. **Model-specific parameters** - CPP demographics, CPV thresholds, etc.
4. **Polish** - Validation, help text, responsive design

## Migration from Legacy
For existing products, show:
```
Current pricing: CPM $12.50 (Fixed) - Legacy format
[ Convert to Pricing Options ]
```

Button creates a pricing_option from legacy fields.

## Files to Modify
- `templates/add_product.html`
- `templates/edit_product.html`
- `templates/add_product_gam.html`
- `src/admin/blueprints/products.py`
- `static/js/product-form.js` (new file for pricing options JS)

## Estimated Time
- Backend: 2-3 hours
- Frontend: 3-4 hours
- Testing: 1-2 hours
- **Total: 6-9 hours**
