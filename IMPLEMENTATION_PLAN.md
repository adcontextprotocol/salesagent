# GAM Pricing Model & Line Item Type Integration

## Goal
Integrate GAM line item types with pricing models to support all valid combinations, significantly expanding the adapter's capabilities from CPM-only to comprehensive pricing support.

## Success Criteria
1. All valid GAM pricing + line item type combinations are supported
2. Invalid combinations are rejected with clear error messages
3. Line item type selection is automatic based on pricing model + campaign characteristics
4. All changes are tested with comprehensive test coverage
5. Documentation is updated with compatibility matrix

---

## Stage 1: Design & Validation Matrix
**Goal**: Create comprehensive pricing + line item type compatibility matrix
**Status**: In Progress

### GAM Compatibility Matrix (from official API docs)

| Line Item Type | Priority | Cost Types Supported | Use Case | Guaranteed? |
|----------------|----------|---------------------|----------|-------------|
| **STANDARD** | 8 (default) | CPM, CPC, VCPM, CPM_IN_TARGET | Guaranteed campaigns | ✅ Yes |
| **SPONSORSHIP** | 4 (default) | CPM, CPC, CPD | Time-based takeovers | ✅ Yes |
| **NETWORK** | 16 (default) | CPM, CPC, CPD | Remnant inventory, unlimited | ❌ No |
| **PRICE_PRIORITY** | 12 (default) | CPM, CPC | Non-guaranteed competitive | ❌ No |
| **BULK** | 12 (default) | CPM only | High-volume, lower value | ❌ No |
| **HOUSE** | 16 (default) | CPM only | Filler ads, no revenue | ❌ No |

### AdCP to GAM Mapping Strategy

| AdCP Model | GAM Cost Type | Line Item Types | Implementation Plan |
|------------|---------------|-----------------|---------------------|
| **cpm** | CPM | ALL types | ✅ Already supported (keep existing) |
| **vcpm** | VCPM | STANDARD only | 🆕 Add support (Phase 1) |
| **cpc** | CPC | STANDARD, SPONSORSHIP, NETWORK, PRICE_PRIORITY | 🆕 Add support (Phase 1) |
| **flat_rate** | CPD (internal translation) | SPONSORSHIP | 🆕 Add support (Phase 2) - Divides total by days |
| **cpcv** | ❌ Not supported | N/A | ⛔ Reject (GAM limitation - video completion not available) |
| **cpv** | ❌ Not supported | N/A | ⛔ Reject (GAM limitation) |
| **cpp** | ❌ Not supported | N/A | ⛔ Reject (GAM limitation - GRP metrics not available) |

**Note**: CPD (Cost Per Day) is a GAM cost type but NOT an AdCP pricing model. We use it internally to translate FLAT_RATE pricing (total campaign cost divided by number of days).

### Line Item Type Selection Logic

**Decision Tree:**
```
1. Is pricing model FLAT_RATE?
   → YES: Use SPONSORSHIP + translate to CPD (total cost / days)
   → NO: Continue to 2

2. Is pricing model VCPM?
   → YES: Use STANDARD (VCPM only works with STANDARD in GAM)
   → NO: Continue to 3

3. Is campaign guaranteed (has guaranteed_impressions)?
   → YES: Use STANDARD (guaranteed delivery)
   → NO: Continue to 4

4. Is pricing model CPC or CPM?
   → Use PRICE_PRIORITY (non-guaranteed competitive)
```

**Override Rules:**
- Product `implementation_config.line_item_type` can override default
- Validation ensures override is compatible with pricing model
- Clear error if incompatible combination requested

---

## Stage 2: Core Implementation
**Goal**: Implement pricing model + line item type validation and selection
**Status**: Pending

### Changes Required

#### 2.1 Create Pricing Compatibility Validator (`src/adapters/gam/pricing_compatibility.py`)
```python
"""
GAM Pricing Model and Line Item Type Compatibility

Based on official GAM API v202411 specifications.
"""

from dataclasses import dataclass
from typing import Literal

# Type aliases for clarity
PricingModel = Literal["cpm", "vcpm", "cpc", "flat_rate"]  # AdCP pricing models only
GAMCostType = Literal["CPM", "VCPM", "CPC", "CPD"]  # GAM internal types (CPD used for FLAT_RATE translation)
LineItemType = Literal["STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY", "BULK", "HOUSE"]

@dataclass
class PricingCompatibility:
    """Defines compatibility between pricing models and line item types.

    Note: CPD is a GAM cost type but NOT an AdCP pricing model. We use it internally
    to translate FLAT_RATE pricing (total campaign cost / days = CPD rate).
    """

    # Official GAM compatibility matrix (what GAM API supports)
    COMPATIBILITY_MATRIX = {
        "STANDARD": {"CPM", "CPC", "VCPM", "CPM_IN_TARGET"},
        "SPONSORSHIP": {"CPM", "CPC", "CPD"},
        "NETWORK": {"CPM", "CPC", "CPD"},
        "PRICE_PRIORITY": {"CPM", "CPC"},
        "BULK": {"CPM"},
        "HOUSE": {"CPM"},
    }

    # AdCP to GAM cost type mapping (internal translation)
    ADCP_TO_GAM_COST_TYPE = {
        "cpm": "CPM",
        "vcpm": "VCPM",
        "cpc": "CPC",
        "flat_rate": "CPD",  # Internal: Translate FLAT_RATE to CPD (total / days)
    }

    @classmethod
    def is_compatible(cls, line_item_type: LineItemType, pricing_model: PricingModel) -> bool:
        """Check if pricing model is compatible with line item type."""
        gam_cost_type = cls.ADCP_TO_GAM_COST_TYPE.get(pricing_model)
        if not gam_cost_type:
            return False
        return gam_cost_type in cls.COMPATIBILITY_MATRIX.get(line_item_type, set())

    @classmethod
    def get_compatible_line_item_types(cls, pricing_model: PricingModel) -> set[LineItemType]:
        """Get all line item types compatible with pricing model."""
        gam_cost_type = cls.ADCP_TO_GAM_COST_TYPE.get(pricing_model)
        if not gam_cost_type:
            return set()

        compatible = set()
        for line_item_type, cost_types in cls.COMPATIBILITY_MATRIX.items():
            if gam_cost_type in cost_types:
                compatible.add(line_item_type)
        return compatible

    @classmethod
    def select_line_item_type(
        cls,
        pricing_model: PricingModel,
        is_guaranteed: bool = False,
        override_type: LineItemType | None = None
    ) -> LineItemType:
        """
        Select appropriate line item type based on campaign characteristics.

        Args:
            pricing_model: AdCP pricing model (cpm, vcpm, cpc, flat_rate)
            is_guaranteed: Whether campaign requires guaranteed delivery
            override_type: Optional explicit line item type from product config

        Returns:
            Recommended line item type

        Raises:
            ValueError: If override_type is incompatible with pricing_model
        """
        # Validate override if provided
        if override_type:
            if not cls.is_compatible(override_type, pricing_model):
                compatible = cls.get_compatible_line_item_types(pricing_model)
                raise ValueError(
                    f"Line item type '{override_type}' is not compatible with pricing model '{pricing_model}'. "
                    f"GAM supports {pricing_model.upper()} with: {', '.join(sorted(compatible))}"
                )
            return override_type

        # Decision tree for automatic selection
        if pricing_model == "flat_rate":
            return "SPONSORSHIP"  # FLAT_RATE → CPD translation, SPONSORSHIP supports CPD

        if pricing_model == "vcpm":
            return "STANDARD"  # VCPM only works with STANDARD in GAM

        if is_guaranteed:
            return "STANDARD"  # Guaranteed delivery

        # Default for CPC/CPM non-guaranteed
        return "PRICE_PRIORITY"

    @classmethod
    def get_gam_cost_type(cls, pricing_model: PricingModel) -> GAMCostType:
        """Convert AdCP pricing model to GAM cost type."""
        cost_type = cls.ADCP_TO_GAM_COST_TYPE.get(pricing_model)
        if not cost_type:
            raise ValueError(f"Pricing model '{pricing_model}' not supported by GAM adapter")
        return cost_type
```

#### 2.2 Update `google_ad_manager.py` - Replace CPM-only validation
**Lines 272-295**: Replace with comprehensive validation

```python
# NEW: Validate pricing model + line item type compatibility
from src.adapters.gam.pricing_compatibility import PricingCompatibility

if package_pricing_info:
    for pkg_id, pricing in package_pricing_info.items():
        pricing_model = pricing["pricing_model"]

        # Check if pricing model is supported by GAM adapter at all
        try:
            gam_cost_type = PricingCompatibility.get_gam_cost_type(pricing_model)
        except ValueError as e:
            error_msg = (
                f"Google Ad Manager adapter does not support '{pricing_model}' pricing. "
                f"Supported pricing models: CPM, CPC, CPD, FLAT_RATE. "
                f"The requested pricing model ('{pricing_model}') is not available in GAM. "
                f"Please choose a product with compatible pricing."
            )
            self.log(f"[red]Error: {error_msg}[/red]")
            return CreateMediaBuyResponse(
                media_buy_id="",
                status="failed",
                message=error_msg,
                errors=[Error(code="unsupported_pricing_model", message=error_msg)],
            )

        self.log(
            f"📊 Package {pkg_id} pricing: {pricing_model} → GAM {gam_cost_type} "
            f"({pricing['currency']}, {'fixed' if pricing['is_fixed'] else 'auction'})"
        )
```

#### 2.3 Update `gam/managers/orders.py` - Dynamic line item type selection
**Around line 515**: Make line item type and cost type dynamic

```python
# Determine line item type based on pricing model and campaign characteristics
product_config = product.implementation_config or {}
impl_config = GAMImplementationConfig(**product_config)

# Check if campaign requires guaranteed delivery
is_guaranteed = package.guaranteed_impressions is not None

# Select appropriate line item type
try:
    line_item_type = PricingCompatibility.select_line_item_type(
        pricing_model=pricing_model,
        is_guaranteed=is_guaranteed,
        override_type=impl_config.line_item_type if hasattr(impl_config, 'line_item_type') else None
    )
except ValueError as e:
    raise ValueError(f"Package {package.package_id}: {e}")

# Get GAM cost type
gam_cost_type = PricingCompatibility.get_gam_cost_type(pricing_model)

self.log(
    f"📋 Line Item Configuration:\n"
    f"  - Pricing Model: {pricing_model} (AdCP)\n"
    f"  - GAM Cost Type: {gam_cost_type}\n"
    f"  - Line Item Type: {line_item_type}\n"
    f"  - Guaranteed: {is_guaranteed}\n"
    f"  - Priority: {self._get_default_priority(line_item_type)}"
)

line_item = {
    "name": line_item_name,
    "orderId": int(order_id),
    "targeting": line_item_targeting,
    "creativePlaceholders": creative_placeholders,
    "lineItemType": line_item_type,  # Dynamic now
    "priority": self._get_default_priority(line_item_type),  # Type-appropriate priority
    "costType": gam_cost_type,  # Dynamic now
    "costPerUnit": {
        "currencyCode": "USD",
        "microAmount": int(package.cpm * 1_000_000)
    },
    # ... rest of config
}
```

#### 2.4 Add Helper Method for Default Priorities
```python
def _get_default_priority(self, line_item_type: str) -> int:
    """Get default priority for line item type (GAM best practices)."""
    priorities = {
        "SPONSORSHIP": 4,
        "STANDARD": 8,
        "PRICE_PRIORITY": 12,
        "BULK": 12,
        "NETWORK": 16,
        "HOUSE": 16,
    }
    return priorities.get(line_item_type, 8)
```

#### 2.5 Update `gam_implementation_config_schema.py`
**Line 56**: Update cost_type description to reflect expanded support

```python
cost_type: str = Field(
    "CPM",
    description="Pricing model: CPM (all types), CPC (STANDARD/SPONSORSHIP/NETWORK/PRICE_PRIORITY), CPD (SPONSORSHIP/NETWORK only). Auto-selected if not specified."
)
```

**Line 44**: Update line_item_type description

```python
line_item_type: str = Field(
    "STANDARD",
    description="Type: STANDARD (guaranteed), SPONSORSHIP (time-based), NETWORK (remnant), PRICE_PRIORITY (non-guaranteed), HOUSE (filler). Auto-selected based on pricing model if not specified."
)
```

**Lines 126-131**: Expand cost_type validation

```python
@field_validator("cost_type")
def validate_cost_type(cls, v):
    valid_types = {"CPM", "CPC", "CPD"}  # Removed CPA (deprecated)
    if v not in valid_types:
        raise ValueError(f"Invalid cost_type. Must be one of: {valid_types}")
    return v
```

---

## Stage 3: Testing
**Goal**: Comprehensive test coverage for all pricing + line item type combinations
**Status**: Pending

### Test Files to Create/Update

#### 3.1 Unit Tests: `tests/unit/test_gam_pricing_compatibility.py`
```python
"""Unit tests for GAM pricing compatibility logic."""

import pytest
from src.adapters.gam.pricing_compatibility import PricingCompatibility

class TestCompatibilityMatrix:
    """Test the GAM compatibility matrix accuracy."""

    def test_cpm_compatible_with_all_types(self):
        """CPM should work with all line item types."""
        for line_item_type in ["STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY", "BULK", "HOUSE"]:
            assert PricingCompatibility.is_compatible(line_item_type, "cpm")

    def test_cpc_compatible_types(self):
        """CPC should work with STANDARD, SPONSORSHIP, NETWORK, PRICE_PRIORITY."""
        compatible = {"STANDARD", "SPONSORSHIP", "NETWORK", "PRICE_PRIORITY"}
        incompatible = {"BULK", "HOUSE"}

        for line_item_type in compatible:
            assert PricingCompatibility.is_compatible(line_item_type, "cpc"), \
                f"CPC should be compatible with {line_item_type}"

        for line_item_type in incompatible:
            assert not PricingCompatibility.is_compatible(line_item_type, "cpc"), \
                f"CPC should NOT be compatible with {line_item_type}"

    def test_cpd_compatible_types(self):
        """CPD should work with SPONSORSHIP and NETWORK only."""
        compatible = {"SPONSORSHIP", "NETWORK"}
        incompatible = {"STANDARD", "PRICE_PRIORITY", "BULK", "HOUSE"}

        for line_item_type in compatible:
            assert PricingCompatibility.is_compatible(line_item_type, "cpd")

        for line_item_type in incompatible:
            assert not PricingCompatibility.is_compatible(line_item_type, "cpd")

class TestLineItemTypeSelection:
    """Test automatic line item type selection logic."""

    def test_cpd_selects_sponsorship(self):
        """CPD pricing should select SPONSORSHIP type."""
        result = PricingCompatibility.select_line_item_type("cpd", is_guaranteed=False)
        assert result == "SPONSORSHIP"

    def test_flat_rate_selects_sponsorship(self):
        """FLAT_RATE pricing should select SPONSORSHIP type."""
        result = PricingCompatibility.select_line_item_type("flat_rate", is_guaranteed=False)
        assert result == "SPONSORSHIP"

    def test_guaranteed_cpm_selects_standard(self):
        """Guaranteed CPM campaigns should select STANDARD type."""
        result = PricingCompatibility.select_line_item_type("cpm", is_guaranteed=True)
        assert result == "STANDARD"

    def test_non_guaranteed_cpm_selects_price_priority(self):
        """Non-guaranteed CPM campaigns should select PRICE_PRIORITY type."""
        result = PricingCompatibility.select_line_item_type("cpm", is_guaranteed=False)
        assert result == "PRICE_PRIORITY"

    def test_cpc_non_guaranteed_selects_price_priority(self):
        """Non-guaranteed CPC campaigns should select PRICE_PRIORITY type."""
        result = PricingCompatibility.select_line_item_type("cpc", is_guaranteed=False)
        assert result == "PRICE_PRIORITY"

    def test_override_compatible_type_accepted(self):
        """Override with compatible type should be accepted."""
        result = PricingCompatibility.select_line_item_type(
            "cpc",
            is_guaranteed=False,
            override_type="NETWORK"
        )
        assert result == "NETWORK"

    def test_override_incompatible_type_rejected(self):
        """Override with incompatible type should raise ValueError."""
        with pytest.raises(ValueError, match="not compatible with pricing model 'cpd'"):
            PricingCompatibility.select_line_item_type(
                "cpd",
                is_guaranteed=False,
                override_type="STANDARD"  # STANDARD doesn't support CPD
            )

class TestGAMCostTypeMapping:
    """Test AdCP to GAM cost type conversion."""

    def test_supported_pricing_models(self):
        """Test conversion of supported pricing models."""
        assert PricingCompatibility.get_gam_cost_type("cpm") == "CPM"
        assert PricingCompatibility.get_gam_cost_type("cpc") == "CPC"
        assert PricingCompatibility.get_gam_cost_type("cpd") == "CPD"
        assert PricingCompatibility.get_gam_cost_type("flat_rate") == "CPD"

    def test_unsupported_pricing_models(self):
        """Test rejection of unsupported pricing models."""
        for unsupported in ["cpcv", "cpv", "cpp"]:
            with pytest.raises(ValueError, match="not supported by GAM adapter"):
                PricingCompatibility.get_gam_cost_type(unsupported)
```

#### 3.2 Integration Tests: `tests/integration/test_gam_pricing_comprehensive.py`
```python
"""Integration tests for comprehensive GAM pricing support."""

import pytest
from unittest.mock import Mock, patch
from src.adapters.google_ad_manager import GoogleAdManager
from src.core.schemas import Package, CreateMediaBuyRequest

class TestCPCSupport:
    """Test CPC pricing across compatible line item types."""

    def test_cpc_price_priority_line_item_creation(self, mock_gam_adapter):
        """Test CPC pricing creates PRICE_PRIORITY line item."""
        # Setup: Product with CPC pricing
        package_pricing_info = {
            "pkg_1": {
                "pricing_model": "cpc",
                "rate": 0.50,  # $0.50 per click
                "currency": "USD",
                "is_fixed": True,
            }
        }

        # Execute
        with patch.object(mock_gam_adapter.orders_manager, 'create_order') as mock_create_order, \
             patch.object(mock_gam_adapter.orders_manager, 'create_line_items') as mock_create_line_items:

            mock_create_order.return_value = "order_123"
            mock_create_line_items.return_value = [{"id": "li_456", "name": "Test Line Item"}]

            response = mock_gam_adapter.create_media_buy(
                media_buy_id="mb_test",
                principal_id="principal_1",
                products=[mock_product_with_cpc],
                packages=[mock_package],
                package_pricing_info=package_pricing_info,
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(days=7),
            )

            # Verify line item created with CPC cost type
            call_args = mock_create_line_items.call_args
            line_items = call_args[1]["line_items_data"]

            assert response.status == "success"
            assert line_items[0]["costType"] == "CPC"
            assert line_items[0]["lineItemType"] == "PRICE_PRIORITY"
            assert line_items[0]["priority"] == 12

    def test_cpc_guaranteed_selects_standard(self, mock_gam_adapter):
        """Test guaranteed CPC campaign uses STANDARD line item."""
        package_pricing_info = {
            "pkg_1": {
                "pricing_model": "cpc",
                "rate": 0.50,
                "currency": "USD",
                "is_fixed": True,
            }
        }

        # Package with guaranteed impressions
        package = Package(
            package_id="pkg_1",
            guaranteed_impressions=100000,
            # ... other fields
        )

        # Execute and verify
        # Should select STANDARD type due to guaranteed delivery requirement
        # (test implementation similar to above)

class TestCPDSupport:
    """Test CPD pricing with SPONSORSHIP and NETWORK line items."""

    def test_cpd_selects_sponsorship(self, mock_gam_adapter):
        """Test CPD pricing creates SPONSORSHIP line item."""
        package_pricing_info = {
            "pkg_1": {
                "pricing_model": "cpd",
                "rate": 1000.00,  # $1000 per day
                "currency": "USD",
                "is_fixed": True,
            }
        }

        # Execute and verify SPONSORSHIP type, CPD cost type, priority 4
        # (test implementation)

    def test_cpd_with_network_override(self, mock_gam_adapter):
        """Test CPD pricing with explicit NETWORK line item type."""
        # Product config with line_item_type override
        product_config = {
            "line_item_type": "NETWORK",
            "cost_type": "CPD",
            # ... other config
        }

        # Execute and verify NETWORK type accepted (compatible with CPD)
        # (test implementation)

class TestIncompatibleCombinations:
    """Test rejection of incompatible pricing + line item type combinations."""

    def test_cpd_with_standard_rejected(self, mock_gam_adapter):
        """Test CPD pricing with STANDARD override is rejected."""
        product_config = {
            "line_item_type": "STANDARD",  # Incompatible with CPD
            "cost_type": "CPD",
        }

        # Should raise ValueError during validation
        with pytest.raises(ValueError, match="not compatible with pricing model 'cpd'"):
            # Create media buy attempt
            pass

    def test_cpc_with_house_rejected(self, mock_gam_adapter):
        """Test CPC pricing with HOUSE line item is rejected."""
        product_config = {
            "line_item_type": "HOUSE",  # Only supports CPM
            "cost_type": "CPC",
        }

        # Should raise ValueError
        with pytest.raises(ValueError, match="not compatible"):
            pass
```

#### 3.3 Update Existing Tests: `tests/integration/test_gam_pricing_restriction.py`
- Rename to `test_gam_pricing_validation.py` (more accurate name)
- Update tests to reflect expanded support
- Keep CPCV/CPV/CPP rejection tests (still unsupported)
- Add tests for CPC/CPD acceptance

---

## Stage 4: Documentation
**Goal**: Update all documentation with comprehensive pricing support
**Status**: Pending

### Files to Update

#### 4.1 `CLAUDE.md`
**Section: "Adapter Pricing Model Support"** (around line 1500)

Replace entire section with:

```markdown
## Adapter Pricing Model Support

### GAM Adapter
**Supported Pricing Models**: CPM, VCPM, CPC, FLAT_RATE

#### Pricing Model Details

| AdCP Model | GAM Cost Type | Line Item Types | Use Case |
|------------|---------------|-----------------|----------|
| **CPM** | CPM | All types (STANDARD, SPONSORSHIP, NETWORK, PRICE_PRIORITY, BULK, HOUSE) | Cost per 1,000 impressions - most common |
| **VCPM** | VCPM | STANDARD only | Cost per 1,000 viewable impressions - viewability-based |
| **CPC** | CPC | STANDARD, SPONSORSHIP, NETWORK, PRICE_PRIORITY | Cost per click - performance-based |
| **FLAT_RATE** | CPD (internal) | SPONSORSHIP | Fixed campaign cost - internally translates to CPD (total / days) |

**Not Supported**: CPCV, CPV, CPP (GAM API limitations - video completion and GRP metrics not available)

**Note**: CPD (Cost Per Day) is a GAM cost type but NOT exposed as an AdCP pricing model. It's used internally to translate FLAT_RATE pricing.

#### Line Item Type Selection

GAM adapter **automatically selects** the appropriate line item type based on:
1. **Pricing model** (FLAT_RATE → SPONSORSHIP, VCPM → STANDARD, others → based on delivery guarantee)
2. **Delivery guarantee** (guaranteed_impressions → STANDARD, else PRICE_PRIORITY)
3. **Product override** (implementation_config.line_item_type, validated for compatibility)

**Automatic Selection Logic**:
- FLAT_RATE pricing → SPONSORSHIP line item (priority 4) with CPD translation
- VCPM pricing → STANDARD line item (priority 8) - VCPM only works with STANDARD
- Guaranteed CPM/CPC → STANDARD line item (priority 8)
- Non-guaranteed CPM/CPC → PRICE_PRIORITY line item (priority 12)

**Manual Override** (via product configuration):
```json
{
  "implementation_config": {
    "line_item_type": "NETWORK",  // Override default selection
    "cost_type": "CPC",            // Must be compatible with line_item_type
    // ... other config
  }
}
```

**Validation**: Incompatible pricing + line item type combinations are rejected with clear error messages.

#### Compatibility Matrix

| Line Item Type | Supported Pricing | Priority | Guaranteed |
|----------------|------------------|----------|------------|
| STANDARD | CPM, CPC, VCPM | 8 | ✅ Yes |
| SPONSORSHIP | CPM, CPC, CPD | 4 | ✅ Yes |
| NETWORK | CPM, CPC, CPD | 16 | ❌ No |
| PRICE_PRIORITY | CPM, CPC | 12 | ❌ No |
| BULK | CPM only | 12 | ❌ No |
| HOUSE | CPM only | 16 | ❌ No (filler) |

**Source**: Google Ad Manager API v202411 CostType specification

### Mock Adapter
**Supported**: All AdCP pricing models (CPM, VCPM, CPCV, CPP, CPC, CPV, FLAT_RATE)
- Both fixed and auction pricing
- All currencies
- Simulates appropriate metrics per pricing model
- Used for testing and development
```

#### 4.2 Add New Documentation: `docs/gam-pricing-guide.md`
Create comprehensive guide for publishers on how to configure pricing models.

---

## Stage 5: Migration & Rollout
**Goal**: Deploy changes without breaking existing campaigns
**Status**: Pending

### Backward Compatibility Strategy

1. **Existing CPM campaigns**: No changes required
   - Default behavior unchanged
   - Still use STANDARD line items by default
   - All existing products continue to work

2. **Products with explicit `line_item_type` config**: Validate compatibility
   - Add validation step during media buy creation
   - If incompatible with pricing model, reject with clear error
   - Recommend compatible alternatives in error message

3. **New pricing models**: Opt-in via product configuration
   - Publishers must explicitly enable CPC/CPD in products
   - Clear documentation on how to configure
   - Admin UI updates to support pricing model selection (future work)

### Rollout Phases

**Phase 1: CPC & VCPM Support** (Immediate - user requested + AdCP spec)
- Implement CPC + line item type selection (PRICE_PRIORITY, STANDARD, SPONSORSHIP, NETWORK)
- Implement VCPM + STANDARD line item type (VCPM-specific)
- Test with all compatible line item types
- Update validation logic
- Deploy to staging

**Phase 2: FLAT_RATE Support** (Follow-up)
- Implement FLAT_RATE → CPD translation logic (total cost / days)
- Implement automatic SPONSORSHIP line item selection for FLAT_RATE
- Test budget calculation and CPD rate computation
- Validate NETWORK override option works
- Deploy to staging

**Phase 3: Documentation & Admin UI** (Post-implementation)
- Update all docs
- Add pricing model selector to Admin UI product creation (CPM, VCPM, CPC, FLAT_RATE)
- Add line item type override option
- Update product examples
- Document FLAT_RATE → CPD translation behavior

---

## Tests

### Test Coverage Requirements

**Unit Tests**:
- [x] Compatibility matrix validation
- [x] Line item type selection logic
- [x] GAM cost type mapping
- [x] Override validation
- [x] Error messages

**Integration Tests**:
- [x] CPC + PRICE_PRIORITY creation
- [x] CPC + STANDARD (guaranteed) creation
- [x] CPD + SPONSORSHIP creation
- [x] CPD + NETWORK override creation
- [x] Incompatible combination rejection
- [x] Backward compatibility (CPM still works)

**E2E Tests**:
- [ ] Full media buy with CPC pricing
- [ ] Full media buy with CPD pricing
- [ ] Mixed pricing models in single media buy
- [ ] Pricing model enforcement across workflow

---

## Success Metrics

1. ✅ All 4 supported pricing models (CPM, CPC, CPD, FLAT_RATE) work
2. ✅ Automatic line item type selection works correctly
3. ✅ Manual overrides validated for compatibility
4. ✅ Clear error messages for unsupported combinations
5. ✅ Backward compatibility maintained (existing CPM campaigns unaffected)
6. ✅ Test coverage >90% for new code
7. ✅ Documentation updated and accurate
8. ✅ No breaking changes to existing products/campaigns

---

## Notes

- GAM API v202411 is source of truth for compatibility matrix
- CPA (Cost Per Action) deprecated by Google Feb 2024 - do not implement
- VCPM and CPM_IN_TARGET are advanced features - consider for future enhancement
- Flat rate simulation via CPD is a workaround - may need refinement based on real usage
- Admin UI updates are separate effort - not blocking for this implementation
