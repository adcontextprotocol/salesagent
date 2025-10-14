# Mypy Quick Start Guide

**Goal:** Fix mypy errors incrementally to reach mypy 0

---

## 🚀 Get Started in 5 Minutes

### Step 1: Check Current State
```bash
uv run mypy src/ --config-file=mypy.ini 2>&1 | tail -1
# Expected: Found 1620 errors in 98 files
```

### Step 2: Quick Win (30 seconds)
```bash
bash scripts/mypy/01_install_type_stubs.sh
```

### Step 3: Check Improvement
```bash
uv run mypy src/ --config-file=mypy.ini 2>&1 | tail -1
# Expected: Found ~1600 errors (20 fixed!)
```

---

## 📊 Current Status

- **Total Errors:** 1,620
- **Worst File:** main.py (422 errors)
- **Easiest Fixes:** Type stubs, implicit Optional
- **Hardest Fixes:** Type assignments, schema mismatches

---

## 🎯 Priority Fix Order

### 1️⃣ Install Type Stubs (30 min)
**What:** Install missing type information packages
**Impact:** 20 errors fixed
**Effort:** Easy (automated)

```bash
bash scripts/mypy/01_install_type_stubs.sh
```

---

### 2️⃣ Fix Implicit Optional (1-2 hours)
**What:** Change `arg: Type = None` → `arg: Type | None = None`
**Impact:** 150+ errors fixed
**Effort:** Easy (semi-automated)

```bash
# Find issues
python scripts/mypy/02_find_implicit_optional.py

# Auto-fix (requires review)
uv add --dev no-implicit-optional
no-implicit-optional src/
git diff  # Review changes carefully
```

---

### 3️⃣ Convert Models to Mapped[] (4-8 hours)
**What:** Convert Column() to Mapped[] (SQLAlchemy 2.0)
**Impact:** 310 errors fixed
**Effort:** Medium (semi-automated)

```python
# Before
class Tenant(Base):
    tenant_id = Column(String(50), primary_key=True)

# After
class Tenant(Base):
    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
```

**Process:**
1. Start with src/core/database/models.py
2. Convert simple fields first (String, Integer, Boolean)
3. Test after each conversion
4. Handle complex cases (relationships, nullable)

---

### 4️⃣ Fix Schema Mismatches (8-16 hours)
**What:** Remove fields not in AdCP spec
**Impact:** 141 errors fixed
**Effort:** Hard (manual review)

```bash
# Find issues
python scripts/mypy/04_find_schema_mismatches.py
```

**Common fixes:**
- Remove `message`, `reason`, `detail` fields
- Use `errors=[Error(...)]` instead
- Check spec: https://adcontextprotocol.org/schemas/v1/

---

### 5️⃣ Add Missing Annotations (2-4 hours)
**What:** Add type hints to variables
**Impact:** 37 errors fixed
**Effort:** Medium (manual)

```bash
# Find issues
python scripts/mypy/03_find_missing_annotations.py
```

**Common patterns:**
```python
issues = []              → issues: list[ValidationIssue] = []
config = {}              → config: dict[str, Any] = {}
result = None            → result: str | None = None
```

---

## 🔍 Checking Progress

### Quick Check
```bash
uv run mypy src/ --config-file=mypy.ini 2>&1 | tail -1
```

### Detailed Check
```bash
uv run mypy src/ --config-file=mypy.ini
```

### Check Specific File
```bash
uv run mypy src/core/main.py --config-file=mypy.ini
```

### Check Error Count by Type
```bash
uv run mypy src/ --config-file=mypy.ini 2>&1 | grep -E "\[.*\]$" | sed -E 's/.*\[(.*)\]$/\1/' | sort | uniq -c | sort -rn
```

---

## 📈 Expected Progress

| Phase | Hours | Errors Fixed | Cumulative % |
|-------|-------|--------------|--------------|
| Type Stubs | 0.5 | 20 | 1% |
| Implicit Optional | 1.5 | 150 | 10% |
| Models to Mapped[] | 6 | 310 | 30% |
| Schema Mismatches | 12 | 141 | 40% |
| Missing Annotations | 3 | 37 | 42% |
| Remaining Fixes | 22 | 962 | 100% |
| **Total** | **45** | **1,620** | **100%** |

---

## 🛠️ Available Tools

All in `scripts/mypy/`:

| Script | Purpose | Time |
|--------|---------|------|
| 01_install_type_stubs.sh | Install type packages | 30s |
| 02_find_implicit_optional.py | Find implicit Optional | 5s |
| 03_find_missing_annotations.py | Find missing type hints | 10s |
| 04_find_schema_mismatches.py | Find non-spec fields | 15s |

---

## ⚠️ Common Mistakes

### DON'T:
❌ Try to fix all errors at once
❌ Add `# type: ignore` comments
❌ Skip testing after changes
❌ Weaken mypy configuration
❌ Commit untested code

### DO:
✅ Work incrementally (one category at a time)
✅ Test after each change
✅ Review automated fixes carefully
✅ Commit working code frequently
✅ Track progress with mypy

---

## 🆘 Troubleshooting

### "Library stubs not installed"
```bash
# Install the specific stub package
uv add --dev types-<library>

# Example
uv add --dev types-requests
```

### "Incompatible types in assignment"
Check if you're assigning the wrong type:
```python
# Wrong
value: str = None  # None is not a str

# Right
value: str | None = None
```

### "Column[str] expected str"
Convert to Mapped[] style (see Phase 3)

### "Unexpected keyword argument"
Check AdCP spec - field might not exist (see Phase 4)

---

## 📚 Resources

- **Full Analysis:** MYPY_ANALYSIS_REPORT.md (20 pages)
- **Summary:** MYPY_SUMMARY.md (5 pages)
- **Tool Docs:** scripts/mypy/README.md
- **mypy Docs:** https://mypy.readthedocs.io/
- **SQLAlchemy 2.0:** https://docs.sqlalchemy.org/en/20/changelog/migration_20.html
- **AdCP Spec:** https://adcontextprotocol.org/schemas/v1/

---

## 🎉 Quick Start Checklist

- [ ] Check current error count
- [ ] Install type stubs (30 min)
- [ ] Find implicit Optional issues
- [ ] Fix one file with implicit Optional
- [ ] Test changes
- [ ] Check new error count
- [ ] Celebrate progress! 🎊

---

## Next Steps

```bash
# 1. Start now
bash scripts/mypy/01_install_type_stubs.sh

# 2. Check improvement
uv run mypy src/ --config-file=mypy.ini 2>&1 | tail -1

# 3. Find next issues
python scripts/mypy/02_find_implicit_optional.py

# 4. Fix incrementally
# (see full guide in MYPY_ANALYSIS_REPORT.md)
```

Good luck! 🚀
