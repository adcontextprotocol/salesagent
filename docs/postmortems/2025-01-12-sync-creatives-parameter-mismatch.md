# Postmortem: sync_creatives Parameter Mismatch CI Failures

**Date**: 2025-01-12
**Impact**: E2E tests failing in CI for multiple commits
**Root Cause**: Parameter signature mismatch between MCP wrappers and shared implementation functions
**Status**: RESOLVED (commit 5ed0df5) but **SYSTEMIC ISSUES REMAIN**

---

## Executive Summary

A merge conflict resolution in PR #352 changed the parameter `webhook_url` (string) to `push_notification_config` (dict) in the A2A raw function (`tools.py`), but the corresponding MCP wrapper in `main.py` was not updated. This caused E2E test failures that took multiple attempts to fix because:

1. The merge conflict only showed changes in `tools.py`, not `main.py`
2. There are NO automated checks to catch parameter signature mismatches
3. The shared implementation pattern requires THREE function signatures to stay aligned (impl, MCP wrapper, A2A raw)
4. Manual code review is error-prone for this type of issue

**Current Status**: Fixed `sync_creatives`, but **TWO OTHER TOOLS have the SAME BUG**:
- ❌ `create_media_buy` - MCP wrapper missing `push_notification_config`
- ❌ `update_media_buy` - MCP wrapper missing `push_notification_config`

---

## Timeline

1. **PR #352** (719f5f1): Changed `webhook_url` → `push_notification_config` in A2A server
2. **Merge Conflict**: `tools.py` had conflict, accepted main's version with `push_notification_config`
3. **Issue**: MCP wrapper in `main.py` still used `webhook_url` parameter
4. **E2E Test Failure**: `_sync_creatives_impl() got an unexpected keyword argument 'webhook_url'`
5. **Multiple Fix Attempts**: Fixed `tools.py` first, but error persisted
6. **Final Fix** (5ed0df5): Fixed MCP wrapper in `main.py` to convert `webhook_url` → `push_notification_config`

---

## Root Cause Analysis

### 1. Why This Happened: Shared Implementation Architecture

The codebase follows a **shared implementation pattern** to avoid code duplication:

```
CORRECT ARCHITECTURE:
  MCP Tool (main.py)     → _tool_name_impl() → [real implementation]
         ↓                         ↑
    webhook_url              push_notification_config
         |                         |
         +-------------------------+
                  MISMATCH!

  A2A Raw (tools.py)    → _tool_name_impl() → [real implementation]
         ↓                         ↑
push_notification_config    push_notification_config
         |                         |
         +-------------------------+
                   CORRECT
```

**Three function signatures must stay aligned:**
1. **`_tool_name_impl()`** - Shared implementation with canonical parameters
2. **`tool_name()` (MCP wrapper)** - Thin wrapper with `@mcp.tool()` decorator
3. **`tool_name_raw()` (A2A raw)** - Thin wrapper for A2A server

**When parameters change in the implementation:**
- All three signatures must be updated
- MCP wrapper and A2A raw must convert/adapt parameters if needed
- There are NO automated checks to enforce this

---

### 2. Why the Merge Conflict Didn't Catch It

Git merge conflicts only show **file-level** conflicts, not **logical dependencies** across files:

```bash
# PR #352 changed:
src/core/tools.py:
-  webhook_url: str = None
+  push_notification_config: dict = None

# Merge conflict showed:
<<<<<<< HEAD
  webhook_url: str = None
=======
  push_notification_config: dict = None
>>>>>>> main

# Resolution: Accept main's version (push_notification_config)
```

**What the merge resolution DID NOT show:**
- `src/core/main.py` also needs updating (different file)
- MCP wrapper signature must match _impl signature
- Manual code review required to catch this

**Why this is hard to catch:**
- `main.py` and `tools.py` are separate files
- No immediate test failure during merge
- Only fails when E2E tests actually call the tool
- Error message is cryptic: "unexpected keyword argument"

---

### 3. Why Merge Conflicts Are Dangerous for This Pattern

The shared implementation pattern creates **invisible dependencies**:

```python
# File 1: src/core/main.py
def _sync_creatives_impl(
    # ... other params ...
    push_notification_config: dict | None = None,  # ✅ Correct
):
    """Shared implementation."""
    # Real logic here

@mcp.tool()
def sync_creatives(
    # ... other params ...
    webhook_url: str | None = None,  # ❌ WRONG - doesn't match _impl!
):
    """MCP wrapper - SHOULD convert webhook_url → push_notification_config"""
    return _sync_creatives_impl(
        # ... other params ...
        webhook_url=webhook_url,  # ❌ BUG: _impl expects push_notification_config
    )

# File 2: src/core/tools.py
def sync_creatives_raw(
    # ... other params ...
    push_notification_config: dict = None,  # ✅ Correct
):
    """A2A raw function."""
    from src.core.main import _sync_creatives_impl
    return _sync_creatives_impl(
        # ... other params ...
        push_notification_config=push_notification_config,  # ✅ Correct
    )
```

**The bug is invisible during merge because:**
1. `tools.py` merge conflict: ✅ Resolved correctly (accepted `push_notification_config`)
2. `main.py` no merge conflict: ❌ Silently wrong (`webhook_url` never updated)
3. `_impl` signature: ✅ Correct (`push_notification_config`)
4. **Result**: MCP wrapper calls `_impl()` with wrong parameter name

---

### 4. Why Tests Didn't Catch It Earlier

**Unit tests passed** because they mock everything:
```python
# Unit test - passes even with signature mismatch
@patch('src.core.main._sync_creatives_impl')
def test_sync_creatives(mock_impl):
    mock_impl.return_value = SyncCreativesResponse(...)
    # Test never actually calls _impl with real parameters
```

**Integration tests caught it** because they use real function calls:
```python
# E2E test - fails with signature mismatch
response = await client.tools.sync_creatives(
    creatives=[...],
    webhook_url="http://example.com",  # MCP wrapper accepts this
)
# MCP wrapper calls: _sync_creatives_impl(webhook_url=...)
# _impl expects: push_notification_config
# ERROR: unexpected keyword argument 'webhook_url'
```

**Why it took multiple attempts to fix:**
1. First attempt: Fixed `tools.py` (A2A raw) - but MCP wrapper still broken
2. Tests still failed - error persisted
3. Second attempt: Fixed MCP wrapper in `main.py` - finally resolved

---

## Systemic Issues

### Issue 1: No Automated Signature Validation

**Current State**: Zero automated checks for signature alignment

**What's Missing**:
- Pre-commit hook to check parameter names match
- CI check to validate MCP wrapper → _impl → A2A raw alignment
- Type checking to catch parameter mismatches (mypy doesn't catch this)

**Evidence**:
```bash
# Current signature mismatches (as of 2025-01-12):
$ python /tmp/check_param_alignment.py

❌ Found 3 signature mismatches:

  sync_creatives - MCP wrapper:
    Missing: ['push_notification_config']
    Extra: ['webhook_url']

  create_media_buy - MCP wrapper:
    Extra: ['webhook_url']

  update_media_buy - MCP wrapper:
    Missing: ['push_notification_config']
    Extra: ['webhook_url']
```

**Impact**: Two other tools have the SAME BUG right now!

---

### Issue 2: Shared Implementation Pattern is Fragile

**Problem**: Three functions must stay in sync, but there's no enforcement

**Current Architecture**:
```
_tool_name_impl()           ← Source of truth (parameters)
    ↑           ↑
    |           |
MCP wrapper   A2A raw       ← Must match _impl parameters
(main.py)    (tools.py)     ← Different files = hard to keep in sync
```

**Why it's fragile:**
1. Parameter changes require updates in THREE places
2. No compile-time checking (Python is dynamic)
3. No runtime checking (until actual call)
4. Files are separate (cross-file dependency)
5. Merge conflicts only show one file at a time

**Example of fragility:**
```python
# Change 1: Update _impl signature
def _sync_creatives_impl(
    new_param: str,  # Added new parameter
    push_notification_config: dict | None = None,
):
    pass

# Change 2: Must update MCP wrapper (easy to forget!)
@mcp.tool()
def sync_creatives(
    new_param: str,  # ❌ FORGOT TO ADD - compile succeeds, runtime fails!
    webhook_url: str | None = None,
):
    pass

# Change 3: Must update A2A raw (in different file!)
def sync_creatives_raw(
    new_param: str,  # ❌ FORGOT TO ADD - compile succeeds, runtime fails!
    push_notification_config: dict = None,
):
    pass
```

---

### Issue 3: Legacy Parameter Names Create Confusion

**Problem**: Some MCP wrappers use legacy parameter names for backwards compatibility

**Example**:
- AdCP spec: `push_notification_config` (dict with url, authentication)
- Legacy MCP: `webhook_url` (string) - simpler API for clients
- Implementation: `push_notification_config` (dict) - follows spec

**This creates three-way conversion**:
```python
# MCP client calls with legacy parameter
sync_creatives(webhook_url="http://example.com")

# MCP wrapper converts to spec format
push_notification_config = {
    "url": webhook_url,
    "authentication": {"type": "none"}
}

# Calls implementation with spec-compliant parameter
_sync_creatives_impl(push_notification_config=push_notification_config)
```

**Why this is confusing:**
- Different parameter names at different layers
- Easy to forget conversion step
- Merge conflicts show parameter name changes
- Not obvious which layer needs updating

---

## Other Tools with Same Issue

**Current signature check results:**

### ❌ create_media_buy
```python
# MCP wrapper (main.py) - line 3970
@mcp.tool()
def create_media_buy(
    webhook_url: str | None = None,  # ❌ WRONG
):
    pass

# Should be:
@mcp.tool()
def create_media_buy(
    push_notification_config: dict = None,  # ✅ Correct
    webhook_url: str | None = None,        # ✅ Legacy support (optional)
):
    # Convert legacy webhook_url if provided
    if webhook_url and not push_notification_config:
        push_notification_config = {
            "url": webhook_url,
            "authentication": {"type": "none"}
        }
```

### ❌ update_media_buy
```python
# MCP wrapper (main.py) - check line ~4660
@mcp.tool()
def update_media_buy(
    webhook_url: str | None = None,  # ❌ WRONG
):
    pass

# Should match _impl signature with push_notification_config
```

**Impact**: These tools will fail in production if clients pass `push_notification_config` dict!

---

## Prevention Strategies

### Strategy 1: Automated Signature Validation (HIGH PRIORITY)

**Implementation**: Pre-commit hook to check signature alignment

```python
# .pre-commit-hooks/check_parameter_alignment.py
"""
Validate that MCP wrappers and A2A raw functions match _impl signatures.
Fails if parameter names don't align (excluding legacy parameters).
"""
def check_tool_signatures():
    tools = [
        ('create_media_buy', '_create_media_buy_impl', 'create_media_buy_raw'),
        ('sync_creatives', '_sync_creatives_impl', 'sync_creatives_raw'),
        ('update_media_buy', '_update_media_buy_impl', 'update_media_buy_raw'),
        # ... other tools
    ]

    for mcp_name, impl_name, raw_name in tools:
        impl_params = get_params('src/core/main.py', impl_name)
        mcp_params = get_params('src/core/main.py', mcp_name)
        raw_params = get_params('src/core/tools.py', raw_name)

        # Allow legacy webhook_url in MCP wrapper (for compatibility)
        legacy_params = {'webhook_url'}

        # Check MCP wrapper
        mcp_core = mcp_params - legacy_params
        if impl_params != mcp_core:
            raise SignatureMismatchError(...)

        # Check A2A raw (must match exactly)
        if impl_params != raw_params:
            raise SignatureMismatchError(...)
```

**Add to `.pre-commit-config.yaml`**:
```yaml
  - id: check-parameter-alignment
    name: Check MCP/A2A parameter alignment
    entry: uv run python .pre-commit-hooks/check_parameter_alignment.py
    language: system
    pass_filenames: false
    always_run: true
```

---

### Strategy 2: Documentation and Code Comments

**Add to each MCP wrapper**:
```python
@mcp.tool()
def sync_creatives(
    # ... params ...
    webhook_url: str | None = None,  # Legacy parameter for backwards compatibility
    push_notification_config: dict | None = None,  # AdCP spec parameter
):
    """
    ⚠️ IMPORTANT: This wrapper MUST stay in sync with _sync_creatives_impl() signature.

    When updating parameters:
    1. Update _sync_creatives_impl() first
    2. Update this MCP wrapper (convert legacy params if needed)
    3. Update sync_creatives_raw() in tools.py
    4. Run: python .pre-commit-hooks/check_parameter_alignment.py
    """
```

---

### Strategy 3: Testing Improvements

**Add integration test for parameter forwarding**:
```python
def test_sync_creatives_parameter_forwarding():
    """Verify MCP wrapper forwards all parameters to _impl correctly."""

    # Mock the _impl function to capture parameters
    with patch('src.core.main._sync_creatives_impl') as mock_impl:
        mock_impl.return_value = SyncCreativesResponse(...)

        # Call MCP wrapper with push_notification_config
        sync_creatives(
            creatives=[],
            push_notification_config={"url": "http://example.com"}
        )

        # Verify _impl was called with correct parameter name
        call_kwargs = mock_impl.call_args.kwargs
        assert 'push_notification_config' in call_kwargs
        assert 'webhook_url' not in call_kwargs
```

---

### Strategy 4: Type Checking with mypy

**Current mypy config doesn't catch this** because:
- Parameters are optional with defaults
- No type mismatch (both are optional)
- Parameter names aren't type-checked

**Potential enhancement**:
```python
from typing import Unpack, TypedDict

class SyncCreativesParams(TypedDict, total=False):
    creatives: list[dict]
    patch: bool
    push_notification_config: dict | None
    # ... other params

def _sync_creatives_impl(**kwargs: Unpack[SyncCreativesParams]):
    pass

# This would catch parameter name mismatches at type-check time
```

**Limitation**: Doesn't help with legacy parameter conversion

---

## Recommendations

### Immediate Actions (Critical - Fix Now)

1. **Fix remaining signature mismatches**:
   ```bash
   # Fix create_media_buy MCP wrapper
   # Fix update_media_buy MCP wrapper
   ```

2. **Add pre-commit hook for signature validation**:
   ```bash
   # Implement .pre-commit-hooks/check_parameter_alignment.py
   # Add to .pre-commit-config.yaml
   # Test with: pre-commit run check-parameter-alignment --all-files
   ```

3. **Add integration tests for parameter forwarding**:
   ```bash
   # Add test_sync_creatives_parameter_forwarding()
   # Add test_create_media_buy_parameter_forwarding()
   # Add test_update_media_buy_parameter_forwarding()
   ```

### Short-Term Improvements (Next Sprint)

4. **Add inline documentation**:
   - Document shared implementation pattern in CLAUDE.md
   - Add warning comments to each MCP wrapper
   - Create troubleshooting guide for signature mismatches

5. **Improve error messages**:
   ```python
   # Better error message when parameter mismatch occurs
   try:
       return _sync_creatives_impl(**kwargs)
   except TypeError as e:
       if 'unexpected keyword argument' in str(e):
           raise ToolError(
               f"Parameter mismatch calling _sync_creatives_impl. "
               f"This is a bug in the MCP wrapper. "
               f"Expected parameters: {_sync_creatives_impl.__code__.co_varnames}"
           )
       raise
   ```

6. **CI job to validate signatures**:
   ```yaml
   # .github/workflows/test.yml
   - name: Validate parameter signatures
     run: |
       python .pre-commit-hooks/check_parameter_alignment.py
   ```

### Long-Term Architectural Changes (Consider for Refactor)

7. **Eliminate duplication with decorators**:
   ```python
   # Potential approach: Generate MCP wrapper from _impl
   @mcp_tool_wrapper
   def _sync_creatives_impl(
       creatives: list[dict],
       push_notification_config: dict | None = None,
   ):
       """Implementation with canonical parameters."""
       pass

   # Decorator auto-generates:
   # - MCP wrapper with @mcp.tool() decorator
   # - A2A raw function
   # - Parameter validation
   ```

8. **Centralize parameter conversion**:
   ```python
   # Single place for legacy parameter conversion
   class ParameterAdapter:
       @staticmethod
       def adapt_webhook_params(webhook_url=None, push_notification_config=None):
           if webhook_url and not push_notification_config:
               return {
                   "url": webhook_url,
                   "authentication": {"type": "none"}
               }
           return push_notification_config
   ```

---

## Lessons Learned

1. **Shared implementation patterns require extra vigilance**
   - Three function signatures must stay aligned
   - Cross-file dependencies are hard to track
   - Manual code review is error-prone

2. **Merge conflicts hide logical dependencies**
   - Git only shows file-level conflicts
   - Cross-file changes require manual coordination
   - Automated checks are essential

3. **Integration tests catch what unit tests miss**
   - Unit tests mock everything (hide bugs)
   - Integration tests use real function calls (reveal bugs)
   - E2E tests are last line of defense (expensive failures)

4. **Legacy parameter support creates technical debt**
   - Backwards compatibility adds complexity
   - Parameter conversion is error-prone
   - Clear migration path needed

5. **Type checking has limits**
   - mypy doesn't catch parameter name mismatches
   - Runtime validation needed
   - Automated tools complement but don't replace testing

---

## Conclusion

The `sync_creatives` parameter mismatch was caused by:
- **Immediate cause**: Merge conflict resolution in `tools.py` without updating `main.py`
- **Root cause**: No automated checks for shared implementation pattern alignment
- **Systemic issue**: Two other tools (`create_media_buy`, `update_media_buy`) have the SAME BUG

**Critical next steps:**
1. Fix remaining signature mismatches (create_media_buy, update_media_buy)
2. Add pre-commit hook for signature validation
3. Add integration tests for parameter forwarding
4. Document shared implementation pattern and maintenance requirements

**This type of bug will happen again unless we implement automated validation.**

---

## References

- Commit 5ed0df5: Fix sync_creatives MCP wrapper
- PR #352: Webhook delivery A2A server changes
- CLAUDE.md: MCP/A2A Shared Implementation Pattern (section 3.2)
- `/tmp/check_param_alignment.py`: Signature validation script (in postmortem)

---

## Appendix A: Signature Validation Script

This script was used to detect the signature mismatches:

```python
#!/usr/bin/env python3
"""Check if MCP wrappers and A2A raw functions match their _impl signatures."""
import ast
import sys

def extract_function_params(file_path, func_name):
    """Extract parameter names from a function."""
    with open(file_path, 'r') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            params = []
            for arg in node.args.args:
                params.append(arg.arg)
            return set(params)
    return None

# Define tools to check
tools = [
    {
        'name': 'sync_creatives',
        'impl': '_sync_creatives_impl',
        'mcp_wrapper': 'sync_creatives',
        'a2a_raw': 'sync_creatives_raw',
    },
    {
        'name': 'create_media_buy',
        'impl': '_create_media_buy_impl',
        'mcp_wrapper': 'create_media_buy',
        'a2a_raw': 'create_media_buy_raw',
    },
    {
        'name': 'update_media_buy',
        'impl': '_update_media_buy_impl',
        'mcp_wrapper': 'update_media_buy',
        'a2a_raw': 'update_media_buy_raw',
    },
]

main_py = 'src/core/main.py'
tools_py = 'src/core/tools.py'

issues_found = []

for tool in tools:
    print(f"\n{'='*80}")
    print(f"Checking: {tool['name']}")
    print('='*80)

    impl_params = extract_function_params(main_py, tool['impl'])
    mcp_params = extract_function_params(main_py, tool['mcp_wrapper'])
    raw_params = extract_function_params(tools_py, tool['a2a_raw'])

    if not impl_params:
        print(f"❌ Could not find {tool['impl']}")
        continue
    if not mcp_params:
        print(f"❌ Could not find {tool['mcp_wrapper']}")
        continue
    if not raw_params:
        print(f"❌ Could not find {tool['a2a_raw']}")
        continue

    print(f"\n_impl params: {sorted(impl_params)}")
    print(f"MCP wrapper params: {sorted(mcp_params)}")
    print(f"A2A raw params: {sorted(raw_params)}")

    # Check MCP wrapper alignment
    if impl_params != mcp_params:
        mismatch = {
            'tool': tool['name'],
            'type': 'MCP wrapper',
            'missing_in_wrapper': impl_params - mcp_params,
            'extra_in_wrapper': mcp_params - impl_params,
        }
        issues_found.append(mismatch)

        print(f"\n⚠️  MCP WRAPPER MISMATCH:")
        if mismatch['missing_in_wrapper']:
            print(f"  Parameters in _impl but NOT in MCP wrapper:")
            for p in sorted(mismatch['missing_in_wrapper']):
                print(f"    - {p}")
        if mismatch['extra_in_wrapper']:
            print(f"  Parameters in MCP wrapper but NOT in _impl:")
            for p in sorted(mismatch['extra_in_wrapper']):
                print(f"    - {p}")
    else:
        print("\n✅ MCP wrapper signature matches _impl")

    # Check A2A raw alignment
    if impl_params != raw_params:
        mismatch = {
            'tool': tool['name'],
            'type': 'A2A raw',
            'missing_in_raw': impl_params - raw_params,
            'extra_in_raw': raw_params - impl_params,
        }
        issues_found.append(mismatch)

        print(f"\n⚠️  A2A RAW FUNCTION MISMATCH:")
        if mismatch['missing_in_raw']:
            print(f"  Parameters in _impl but NOT in A2A raw:")
            for p in sorted(mismatch['missing_in_raw']):
                print(f"    - {p}")
        if mismatch['extra_in_raw']:
            print(f"  Parameters in A2A raw but NOT in _impl:")
            for p in sorted(mismatch['extra_in_raw']):
                print(f"    - {p}")
    else:
        print("\n✅ A2A raw function signature matches _impl")

print(f"\n\n{'='*80}")
print("SUMMARY")
print('='*80)

if not issues_found:
    print("✅ All tool signatures are aligned!")
    sys.exit(0)
else:
    print(f"❌ Found {len(issues_found)} signature mismatches:")
    for issue in issues_found:
        print(f"\n  {issue['tool']} - {issue['type']}:")
        if issue.get('missing_in_wrapper') or issue.get('missing_in_raw'):
            missing = issue.get('missing_in_wrapper') or issue.get('missing_in_raw')
            print(f"    Missing: {sorted(missing)}")
        if issue.get('extra_in_wrapper') or issue.get('extra_in_raw'):
            extra = issue.get('extra_in_wrapper') or issue.get('extra_in_raw')
            print(f"    Extra: {sorted(extra)}")
    sys.exit(1)
```

Save as `.pre-commit-hooks/check_parameter_alignment.py` and add to pre-commit config.

---

## Appendix B: Affected Code Locations

**Files needing fixes:**

1. **src/core/main.py**:
   - Line ~3970: `create_media_buy()` MCP wrapper - add `push_notification_config` parameter
   - Line ~4660: `update_media_buy()` MCP wrapper - add `push_notification_config` parameter

2. **tests/integration/**:
   - Add `test_sync_creatives_parameter_forwarding.py`
   - Add `test_create_media_buy_parameter_forwarding.py`
   - Add `test_update_media_buy_parameter_forwarding.py`

3. **.pre-commit-config.yaml**:
   - Add `check-parameter-alignment` hook

4. **docs/CLAUDE.md**:
   - Add section on shared implementation pattern maintenance
   - Document parameter alignment requirements
   - Add troubleshooting guide for signature mismatches
