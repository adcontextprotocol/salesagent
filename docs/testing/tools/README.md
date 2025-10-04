# Test Coverage Analysis Tools

This directory contains tool documentation. The actual tools are in `/scripts`.

## Available Tools

### 1. analyze_test_coverage.py

**Location**: `/scripts/analyze_test_coverage.py`

Analyzes A2A skill test coverage and identifies anti-patterns.

**Usage**:
```bash
# Run analysis
uv run python scripts/analyze_test_coverage.py

# Strict mode (exits 1 if issues found - good for CI)
uv run python scripts/analyze_test_coverage.py --strict
```

**Output**:
- Coverage percentage (implemented vs tested skills)
- List of untested skills
- Over-mocking violations with line numbers
- Spec compliance issues

### 2. detect_test_antipatterns.py

**Location**: `/scripts/detect_test_antipatterns.py`

Pre-commit hook that detects testing anti-patterns.

**Usage**:
```bash
# Check specific file
uv run python scripts/detect_test_antipatterns.py tests/integration/test_foo.py

# Runs automatically as pre-commit hook
git commit  # Hook runs automatically
```

**Detects**:
- `patch.object(handler, "_handle_*")` in integration tests
- `patch("src.core.main._*_impl")` internal mocking
- Missing tests for new skill handlers

**Pre-commit Configuration**: `.pre-commit-config.yaml`

## See Also

- [../coverage-analysis.md](../coverage-analysis.md) - Why we need these tools
- [../preventing-over-mocking.md](../preventing-over-mocking.md) - How to write proper tests
- [../remediation-plan.md](../remediation-plan.md) - Action plan
