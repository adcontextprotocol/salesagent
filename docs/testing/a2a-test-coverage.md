# A2A Skill Test Coverage

This document describes the test coverage requirements and enforcement for A2A skills.

## Coverage Requirements

**100% A2A skill test coverage is required.**

Every skill advertised in the A2A agent card must have:
1. An integration test that exercises the full code path
2. Mocks only external I/O (auth, database, adapters)
3. Tests real business logic and parameter validation

## Enforcement

Coverage is enforced by pre-commit hooks:

### 1. Skill Coverage Check (`a2a-skill-coverage`)

**Script**: `scripts/check_a2a_skill_coverage.py`

Compares skills in agent card with test methods:
- ✅ Passes if all skills have tests
- ❌ Fails if any skill lacks a test

```bash
# Run manually
uv run python scripts/check_a2a_skill_coverage.py
```

### 2. Over-Mocking Detection (`no-excessive-mocking`)

**Script**: `scripts/check_test_mocking.py`

Prevents mocking internal implementation:
- ✅ Allows mocking external I/O (auth, database, adapters)
- ❌ Blocks mocking internal functions (_impl, _handle_*)

```bash
# Run manually
uv run python scripts/check_test_mocking.py
```

## Test Patterns

### ✅ Good Pattern: Mock External I/O

```python
@pytest.mark.asyncio
async def test_get_products_skill(handler, sample_tenant, sample_principal, validator):
    """Test get_products with real code execution."""
    handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])

    # Mock ONLY external auth/database lookups
    with (
        patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_auth,
        patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_tenant,
    ):
        mock_auth.return_value = sample_principal["principal_id"]
        mock_tenant.return_value = {"tenant_id": sample_tenant["tenant_id"]}

        # Real code execution happens here
        result = await handler.on_message_send(params)

        # Verify real results
        assert isinstance(result, Task)
        artifact_data = validator.extract_adcp_payload_from_a2a_artifact(result.artifacts[0])
        assert "products" in artifact_data
```

###  ❌ Bad Pattern: Mock Internal Implementation

```python
# DON'T DO THIS - Mocks internal handler, code never runs!
with patch.object(handler, "_handle_get_products_skill") as mock_handler:
    mock_handler.return_value = {"products": [...]}
    result = await handler.on_message_send(params)
```

## Adding New Skills

When adding a new A2A skill:

1. **Add skill to agent card** (`src/a2a_server/adcp_a2a_server.py`)
2. **Add integration test** (`tests/integration/test_a2a_skill_invocation.py`)
3. **Use proper mocking pattern** (external I/O only)
4. **Verify coverage**: `uv run python scripts/check_a2a_skill_coverage.py`

### Test Template

```python
@pytest.mark.asyncio
async def test_<skill_name>_skill(self, handler, sample_tenant, sample_principal, validator):
    """Test <skill_name> skill invocation."""
    handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])

    with (
        patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_get_principal,
        patch("src.a2a_server.adcp_a2a_server.get_current_tenant") as mock_get_tenant,
    ):
        mock_get_principal.return_value = sample_principal["principal_id"]
        mock_get_tenant.return_value = {"tenant_id": sample_tenant["tenant_id"]}

        # Create skill invocation
        skill_params = {/* skill parameters */}
        message = self.create_message_with_skill("<skill_name>", skill_params)
        params = MessageSendParams(message=message)

        # Execute real code path
        result = await handler.on_message_send(params)

        # Verify results
        assert isinstance(result, Task)
        assert result.metadata["invocation_type"] == "explicit_skill"
        assert "<skill_name>" in result.metadata["skills_requested"]
        assert result.artifacts is not None
```

## Current Coverage Status

As of the latest commit:
- **24 total tests** (10 original + 14 new)
- **17 passing** (71% pass rate)
- **7 exposing bugs** in implementation
- **100% skill coverage** (all advertised skills have tests)

See `tests/integration/test_a2a_skill_invocation.py` for all tests.

## CI Integration

Pre-commit hooks run automatically on `git commit`:
- Check skill coverage (blocks commit if <100%)
- Check for over-mocking (blocks if internal mocks found)

To skip hooks (not recommended):
```bash
git commit --no-verify
```

## References

- **Test File**: `tests/integration/test_a2a_skill_invocation.py`
- **Coverage Script**: `scripts/check_a2a_skill_coverage.py`
- **Mocking Script**: `scripts/check_test_mocking.py`
- **Pre-commit Config**: `.pre-commit-config.yaml`
- **Issue #248**: Original tracking issue
