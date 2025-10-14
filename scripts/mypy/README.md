# Mypy Fix Scripts

Utilities to help fix mypy errors incrementally.

## Scripts

### 1. Install Type Stubs (Quick Win)
```bash
bash scripts/mypy/01_install_type_stubs.sh
```

**What it does:**
- Installs type stubs for: psycopg2, requests, pytz, waitress
- Configures mypy.ini to ignore libraries without stubs (googleads, authlib, flask_socketio)

**Impact:** Fixes ~20 errors, enables better type checking

**Time:** 30 seconds

---

### 2. Find Implicit Optional
```bash
python scripts/mypy/02_find_implicit_optional.py
```

**What it does:**
- Finds all function signatures with `arg: Type = None`
- Should be `arg: Type | None = None`
- Reports findings (does not modify files)

**Impact:** Identifies ~150 errors to fix

**Time:** 5 seconds to run

**Example output:**
```
src/core/main.py:
  Line 123: context: Context = None
    Fix: context: Context | None = None
```

**How to fix:**
1. Run script to find issues
2. Manually fix or use automated tool: `uv add --dev no-implicit-optional && no-implicit-optional src/`
3. Review changes carefully

---

### 3. Find Missing Annotations
```bash
python scripts/mypy/03_find_missing_annotations.py
```

**What it does:**
- Parses mypy output for "Need type annotation" errors
- Shows specific variables needing type hints
- Provides fix suggestions

**Impact:** Identifies ~37 errors to fix

**Time:** 10 seconds to run

**Example output:**
```
src/adapters/gam/utils/validation.py:
  Line 111: issues
    Hint: issues: list[<type>] = ...
```

**How to fix:**
1. Add type hints as suggested
2. Use concrete types instead of `<type>`
3. Example: `issues: list[ValidationIssue] = []`

---

### 4. Find Schema Mismatches
```bash
python scripts/mypy/04_find_schema_mismatches.py
```

**What it does:**
- Finds fields used in Response objects that aren't in AdCP spec
- Checks status values against spec
- Scans both mypy errors and source code

**Impact:** Identifies ~141 errors to fix

**Time:** 15 seconds to run

**Example output:**
```
CreateMediaBuyResponse:
  Valid fields: adcp_version, status, buyer_ref, task_id, errors, media_buy

  src/adapters/mock_ad_server.py:400
    Unexpected field: message
```

**How to fix:**
1. Remove non-spec fields
2. Use `errors` array for error messages:
   ```python
   errors=[Error(code="...", details="...", message="...")]
   ```
3. Check AdCP spec: https://adcontextprotocol.org/schemas/v1/

---

## Usage Workflow

### Phase 1: Quick Wins
```bash
# 1. Install type stubs (30 sec)
bash scripts/mypy/01_install_type_stubs.sh

# 2. Check improvement
uv run mypy src/ --config-file=mypy.ini 2>&1 | tail -1
# Before: Found 1620 errors
# After:  Found ~1600 errors (20 fixed)
```

### Phase 2: Identify Issues
```bash
# 3. Find implicit Optional (5 sec)
python scripts/mypy/02_find_implicit_optional.py > implicit_optional.txt

# 4. Find missing annotations (10 sec)
python scripts/mypy/03_find_missing_annotations.py > missing_annotations.txt

# 5. Find schema mismatches (15 sec)
python scripts/mypy/04_find_schema_mismatches.py > schema_mismatches.txt
```

### Phase 3: Fix Issues
```bash
# Fix implicit Optional (automated)
uv add --dev no-implicit-optional
no-implicit-optional src/
git diff  # Review changes

# Fix missing annotations (manual)
# Open missing_annotations.txt and fix each one

# Fix schema mismatches (manual)
# Open schema_mismatches.txt and fix each one
```

### Phase 4: Verify
```bash
# Run mypy to check progress
uv run mypy src/ --config-file=mypy.ini

# Run tests to ensure nothing broke
./run_all_tests.sh ci
```

---

## Expected Results

### After Phase 1 (Quick Wins)
- ~20 errors fixed (type stubs)
- Time: 1 hour
- Effort: Easy

### After Phase 2 (Implicit Optional)
- ~150 errors fixed (implicit Optional)
- Time: 2 hours (automated + review)
- Effort: Easy

### After Phase 3 (Missing Annotations)
- ~37 errors fixed (type annotations)
- Time: 2-4 hours
- Effort: Medium

### After Phase 4 (Schema Mismatches)
- ~141 errors fixed (spec compliance)
- Time: 8-16 hours
- Effort: Hard (requires spec review)

### Total Progress
- Before: 1,620 errors
- After Phases 1-4: ~1,272 errors remaining
- Fixed: ~348 errors (21%)
- Time: 13-23 hours

---

## Next Steps (Advanced)

### Convert Models to Mapped[]
High-impact fix for ~310 errors:

```python
# Before (Column style)
class Tenant(Base):
    tenant_id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)

# After (Mapped[] style)
class Tenant(Base):
    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
```

**Impact:** Fixes ~310 errors (19% of total)
**Time:** 4-8 hours
**Effort:** Medium (semi-automated)

See MYPY_ANALYSIS_REPORT.md for detailed guide.

---

## Tips

1. **Work incrementally** - Fix one category at a time
2. **Test after each phase** - Run tests to catch regressions
3. **Review changes carefully** - Especially automated fixes
4. **Focus on high-impact** - Models → Schema → Annotations
5. **Track progress** - Run mypy periodically to see improvement

---

## Support

For detailed analysis and strategy, see:
- `MYPY_ANALYSIS_REPORT.md` - Full error analysis and recommendations
- `mypy_analysis.py` - Analysis script that generated the report

For questions or issues with these scripts, check:
- mypy documentation: https://mypy.readthedocs.io/
- SQLAlchemy 2.0 migration: https://docs.sqlalchemy.org/en/20/changelog/migration_20.html
- AdCP specification: https://adcontextprotocol.org/schemas/v1/
