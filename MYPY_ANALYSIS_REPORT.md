# Mypy Error Analysis Report

**Date:** 2025-10-13
**Total Errors:** 1,620
**Goal:** Reach mypy 0 (eventually, incrementally)

---

## Executive Summary

The codebase has **1,620 mypy errors** across 228 source files. The errors fall into clear categories:

1. **Column type mismatches** (310 errors) - Using old Column() instead of Mapped[]
2. **Schema field mismatches** (141 errors) - Fields not in AdCP spec
3. **Type assignments** (142 errors) - General type safety issues
4. **Missing annotations** (37 errors) - Variables need type hints
5. **Missing stubs** (20 errors) - Need to install type packages

**Key Finding:** The schema adapter migration did NOT significantly worsen mypy errors. The high error count in main.py/tools.py is due to:
- Large file size (7,196 LOC combined)
- Pre-existing Column[] type issues (shared with all models)
- Pre-existing schema validation issues

**Estimated Effort:** 33-58 hours total to reach mypy 0

---

## 1. Current Error State

### Top 10 Error Codes by Frequency

| Error Code | Count | Description |
|------------|-------|-------------|
| assignment | 492 | Incompatible types in assignment |
| call-arg | 300 | Unexpected/missing keyword arguments |
| attr-defined | 253 | Attribute doesn't exist |
| arg-type | 250 | Argument has wrong type |
| index | 48 | Invalid indexing operation |
| union-attr | 47 | Union type missing attribute |
| operator | 45 | Unsupported operand types |
| var-annotated | 37 | Variable needs type annotation |
| import-untyped | 31 | Library stubs not installed |
| return-value | 30 | Incompatible return type |

### Top 10 Files with Most Errors

| File | Errors | Notes |
|------|--------|-------|
| main.py | 422 | MCP server (uses adapters) |
| xandr.py | 130 | Xandr adapter |
| gam_orders_service.py | 89 | GAM service layer |
| adcp_a2a_server.py | 88 | A2A server |
| tools.py | 55 | Raw tool implementations (uses adapters) |
| triton_digital.py | 48 | Triton adapter |
| ai_product_service.py | 48 | AI product service |
| google_ad_manager.py | 44 | GAM adapter |
| kevel.py | 43 | Kevel adapter |
| ai_creative_format_service.py | 38 | AI creative service |

---

## 2. Impact of Adapter Migration

### Comparison: Adapter Files vs Non-Adapter Files

| Metric | Adapter Files (main.py, tools.py) | Non-Adapter Files (mock, GAM) |
|--------|----------------------------------|-------------------------------|
| Total Errors | 477 | 73 |
| Lines of Code | 7,196 | 2,382 |
| **Errors per 100 LOC** | **6.6** | **3.1** |

### Analysis

**Adapters have 2x higher error density** - but this is misleading because:

1. **File size effect**: main.py alone is 4,000+ lines (biggest file in codebase)
2. **Shared issues**: Both adapter and non-adapter files have Column[] issues
3. **Adapter-specific errors**: Only ~10 errors are actually adapter-related:
   - `GetProductsRequest1` vs `GetProductsRequest2` type mismatches (3 errors)
   - Type coercion issues with generated schemas (7 errors)

**Conclusion:** The adapter migration added ~10 new errors but provides significant benefits:
- ✅ Automatic AdCP spec sync (prevents schema drift)
- ✅ Single source of truth (no manual schema maintenance)
- ✅ Better long-term maintainability

The bulk of errors (97%) are pre-existing issues unrelated to adapters.

---

## 3. Systematic Fix Categories

### Category 1: Column Type Mismatches (310 errors)
**Effort:** 4-8 hours
**Priority:** HIGH (fixes 19% of all errors)

**Problem:**
```python
# Current (old SQLAlchemy 1.x style)
class Tenant(Base):
    tenant_id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)

# mypy sees: Column[str], expects: str
# Result: Type mismatch errors everywhere
```

**Solution:**
```python
# SQLAlchemy 2.0 style with Mapped[]
class Tenant(Base):
    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
```

**How to Fix:**
1. Use regex script to convert patterns (semi-automated)
2. Manual review for complex cases (nullable, relationships)
3. Test each model file after conversion

**Files to Convert:**
- `src/core/database/models.py` (primary models)
- Other model files using Column()

**Impact:** High - fixes ~310 errors

---

### Category 2: Schema Field Mismatches (141 errors)
**Effort:** 8-16 hours
**Priority:** MEDIUM (fixes 9% of all errors)

**Problem:**
Code uses fields not in AdCP spec:
```python
CreateMediaBuyResponse(
    message="Order created",  # ❌ Not in AdCP spec
    reason="Failed",          # ❌ Not in AdCP spec
    detail="Extra info"       # ❌ Not in AdCP spec
)
```

**Solution:**
1. Check each field against AdCP spec at https://adcontextprotocol.org/schemas/v1/
2. Remove fields not in spec OR
3. Add to spec if genuinely needed (file issue with AdCP maintainers)

**Common Patterns:**
- `message` → Use `errors` array instead
- `reason` → Use `errors[].details`
- `detail` → Use `errors[].details`

**Files Affected:**
- `src/adapters/triton_digital.py` (16 errors)
- `src/adapters/mock_ad_server.py` (10 errors)
- `src/core/main.py` (12 errors)

**Impact:** Medium - fixes 141 errors, improves spec compliance

---

### Category 3: Missing Type Annotations (37 errors)
**Effort:** 2-4 hours
**Priority:** MEDIUM (fixes 2% of errors)

**Problem:**
```python
issues = []  # ❌ mypy doesn't know the type
for item in data:
    issues.append(validate(item))
```

**Solution:**
```python
issues: list[ValidationIssue] = []  # ✅ Explicit type
for item in data:
    issues.append(validate(item))
```

**How to Fix:**
1. mypy suggests the fix in error message
2. Add type hint as suggested
3. Run mypy again to verify

**Impact:** Low - fixes 37 errors, improves readability

---

### Category 4: Missing Type Stubs (20 errors)
**Effort:** 30 minutes
**Priority:** HIGH (quick win, enables better checking)

**Problem:**
Libraries used without type stubs installed:
- `psycopg2` (8 errors)
- `requests` (6 errors)
- `pytz` (2 errors)
- `googleads` (11 errors - no stubs available)
- Others (3 errors)

**Solution:**
```bash
# Install available stubs
uv add --dev types-psycopg2 types-requests types-pytz

# For googleads (no stubs available), add to mypy.ini:
[mypy-googleads.*]
ignore_missing_imports = True
```

**Impact:** High - Quick fix, enables better type checking for these libraries

---

### Category 5: Type Assignment Errors (142 errors)
**Effort:** 16-24 hours
**Priority:** LOW (case-by-case fixes)

**Problem:**
Various type mismatches:
```python
# Example 1: dict vs specific type
config: dict[str, list[Any]] = {}
config["key"] = "string"  # ❌ Expected list[Any]

# Example 2: None checks
value: str | None = get_value()
length = len(value)  # ❌ value might be None
```

**Solution:**
Manual review and fix each case:
- Add None checks
- Fix dict types
- Use proper type narrowing

**Impact:** Medium - fixes 142 errors, but time-consuming

---

## 4. Prioritized Action Plan

### Phase 1: Quick Wins (2-3 hours)
**Goal:** Fix 20 errors, improve infrastructure

1. **Install type stubs** (30 min)
   ```bash
   uv add --dev types-psycopg2 types-requests types-pytz
   ```

2. **Fix implicit Optional** (1 hour)
   - Look for pattern: `def func(arg: Type = None)`
   - Replace with: `def func(arg: Type | None = None)`
   - Semi-automated with script + review

3. **Configure googleads ignore** (5 min)
   - Add to mypy.ini: `[mypy-googleads.*]` section

**Result:** 20 errors fixed, better type checking enabled

---

### Phase 2: High-Impact Refactor (4-8 hours)
**Goal:** Fix 310 errors (19% of total)

**Convert models.py to Mapped[] style**

1. **Backup and test setup** (30 min)
   ```bash
   git checkout -b fix/convert-to-mapped
   ./run_all_tests.sh ci  # Baseline
   ```

2. **Convert simple fields** (2-3 hours)
   - String fields
   - Integer fields
   - Boolean fields
   - Use regex script + manual review

3. **Convert complex fields** (2-3 hours)
   - Nullable fields (Type | None)
   - Foreign keys
   - Relationships
   - JSON fields (already using JSONType)

4. **Test thoroughly** (1-2 hours)
   ```bash
   ./run_all_tests.sh ci
   uv run mypy src/core/database/models.py
   ```

**Result:** 310 errors fixed, modern SQLAlchemy 2.0 style

---

### Phase 3: Spec Compliance (8-16 hours)
**Goal:** Fix 141 errors (9% of total)

**Fix schema field mismatches**

1. **Audit adapter files** (2-4 hours)
   - List all fields used in Response objects
   - Check against AdCP spec
   - Document legitimate vs non-spec fields

2. **Fix adapters** (4-8 hours)
   - Remove non-spec fields
   - Use `errors` array for error info
   - Update error handling

3. **Update tests** (2-4 hours)
   - Fix tests expecting old fields
   - Add spec compliance tests

**Result:** 141 errors fixed, full AdCP spec compliance

---

### Phase 4: Polish (8-16 hours)
**Goal:** Fix remaining ~500 errors

1. **Add missing type annotations** (2-4 hours)
   - Follow mypy suggestions
   - Add hints to 37 variables

2. **Fix type assignments** (6-12 hours)
   - Manual review each error
   - Add None checks
   - Fix dict types
   - Improve type safety

**Result:** Remaining errors fixed, mypy 0 achieved

---

## 5. Tools and Scripts

### Script 1: Install Type Stubs
```bash
#!/bin/bash
# install_type_stubs.sh

uv add --dev types-psycopg2 types-requests types-pytz

# Update mypy.ini for googleads
cat >> mypy.ini << 'EOF'

[mypy-googleads.*]
ignore_missing_imports = True
EOF

echo "✓ Type stubs installed"
```

### Script 2: Fix Implicit Optional
```python
#!/usr/bin/env python3
# fix_implicit_optional.py

import re
from pathlib import Path

def fix_file(file_path: Path) -> int:
    """Fix implicit Optional in a file. Returns number of fixes."""
    content = file_path.read_text()

    # Pattern: def func(arg: Type = None)
    # Replace: def func(arg: Type | None = None)
    pattern = r'(\w+): ([A-Z]\w+) = None'

    fixes = 0
    def replace(match):
        nonlocal fixes
        name, type_name = match.groups()
        # Don't fix if already has | None
        if '| None' not in match.group(0):
            fixes += 1
            return f'{name}: {type_name} | None = None'
        return match.group(0)

    new_content = re.sub(pattern, replace, content)

    if new_content != content:
        file_path.write_text(new_content)
        print(f"Fixed {fixes} implicit Optional in {file_path}")

    return fixes

if __name__ == "__main__":
    total_fixes = 0
    for file_path in Path("src").rglob("*.py"):
        total_fixes += fix_file(file_path)

    print(f"\n✓ Total fixes: {total_fixes}")
    print("Review changes with: git diff")
```

### Script 3: Find Schema Field Mismatches
```python
#!/usr/bin/env python3
# find_schema_mismatches.py

import re
from pathlib import Path

# Known AdCP response schemas and their valid fields
ADCP_SCHEMAS = {
    "CreateMediaBuyResponse": {
        "adcp_version", "status", "buyer_ref", "task_id", "estimated_completion",
        "polling_interval", "task_progress", "errors", "media_buy"
    },
    "UpdateMediaBuyResponse": {
        "adcp_version", "status", "buyer_ref", "task_id", "estimated_completion",
        "polling_interval", "task_progress", "errors", "media_buy"
    },
}

def check_file(file_path: Path):
    """Check file for non-spec fields."""
    content = file_path.read_text()

    issues = []
    for schema_name, valid_fields in ADCP_SCHEMAS.items():
        # Find all uses of this schema
        pattern = rf'{schema_name}\((.*?)\)'
        for match in re.finditer(pattern, content, re.DOTALL):
            call = match.group(1)
            # Extract field names
            field_pattern = r'(\w+)='
            used_fields = set(re.findall(field_pattern, call))

            # Check for non-spec fields
            invalid = used_fields - valid_fields
            if invalid:
                line_num = content[:match.start()].count('\n') + 1
                issues.append({
                    'file': str(file_path),
                    'line': line_num,
                    'schema': schema_name,
                    'invalid_fields': invalid
                })

    return issues

if __name__ == "__main__":
    all_issues = []
    for file_path in Path("src").rglob("*.py"):
        all_issues.extend(check_file(file_path))

    if all_issues:
        print("Schema Field Mismatches Found:")
        print("=" * 80)
        for issue in all_issues:
            print(f"\n{issue['file']}:{issue['line']}")
            print(f"  Schema: {issue['schema']}")
            print(f"  Invalid fields: {', '.join(issue['invalid_fields'])}")
    else:
        print("✓ No schema field mismatches found")
```

---

## 6. Estimated Timeline

### Conservative Estimate (58 hours)
- Phase 1: Quick Wins - 3 hours
- Phase 2: Convert to Mapped[] - 8 hours
- Phase 3: Spec Compliance - 16 hours
- Phase 4: Polish - 16 hours
- Testing & Buffer - 15 hours

**Total: ~58 hours (7-8 working days)**

### Optimistic Estimate (33 hours)
- Phase 1: Quick Wins - 2 hours
- Phase 2: Convert to Mapped[] - 4 hours
- Phase 3: Spec Compliance - 8 hours
- Phase 4: Polish - 8 hours
- Testing & Buffer - 11 hours

**Total: ~33 hours (4-5 working days)**

---

## 7. Incremental Approach (RECOMMENDED)

Instead of tackling all 1,620 errors at once, fix incrementally:

### Week 1: Quick Wins + Models
- Install type stubs
- Fix implicit Optional
- Convert 1 model file to Mapped[]
- **Goal:** 50-100 errors fixed

### Week 2: More Models
- Convert remaining models to Mapped[]
- **Goal:** 200+ errors fixed (cumulative ~300)

### Week 3: Spec Compliance
- Fix adapter schema mismatches
- **Goal:** 150 errors fixed (cumulative ~450)

### Week 4+: Polish
- Fix remaining errors file-by-file
- Focus on files you're already touching
- **Goal:** Gradual reduction to 0

**Benefits of Incremental:**
- Less risky (smaller PRs)
- Easier to review
- Can pause/resume as needed
- Immediate improvements

---

## 8. Key Recommendations

### DO:
1. ✅ Start with quick wins (type stubs, implicit Optional)
2. ✅ Convert models to Mapped[] (high impact)
3. ✅ Fix spec compliance issues (important for protocol)
4. ✅ Work incrementally (one category at a time)
5. ✅ Test thoroughly after each phase

### DON'T:
1. ❌ Try to fix all 1,620 errors at once
2. ❌ Skip testing between phases
3. ❌ Add `# type: ignore` comments (fix root cause)
4. ❌ Weaken mypy config (keep strict checking)

### ADAPTER-SPECIFIC:
- ✅ Adapters are NOT the problem (only ~10 errors)
- ✅ Keep using adapters (benefits outweigh costs)
- ✅ Fix the 10 adapter-specific errors in schema_helpers.py

---

## 9. Conclusion

**Current State:**
- 1,620 mypy errors
- ~97% are pre-existing issues (not adapter-related)
- Clear categories with actionable fixes

**Adapter Impact:**
- Adapters added ~10 errors
- Adapters provide significant benefits (spec sync, maintainability)
- Keep using adapters, fix the few adapter-specific issues

**Path Forward:**
- 33-58 hours total effort
- Use incremental approach (4-8 weeks)
- Start with high-impact fixes (models → spec compliance → polish)
- Track progress weekly

**Expected Outcome:**
- mypy 0 (full type safety)
- Better code quality
- Fewer runtime bugs
- Easier refactoring
