# Test Suite Cleanup Plan

## Issues Identified

### 1. Skipped Migration Test (test_dashboard_reliability.py)
**Current State**: Test is skipped with reason "testing migration internals is not necessary"
**Problem**: If we're not going to run it, why keep it?
**Decision**: **DELETE** - Migration internals are implementation details, not functionality

### 2. AI/Gemini Testing Strategy
**Current State**: Tests skip if `GEMINI_API_KEY` not set
**Problem**:
- We don't want to call Gemini in integration tests (out of our control)
- But we DO need to test AI-dependent functionality
- Current approach blocks CI/CD when API key unavailable

**Proposed Solution**:
```
Unit Tests (src/services/ai_*.py):
- Mock Gemini API responses
- Test our logic for processing AI responses
- Test error handling, rate limiting, retries
- Fast, deterministic, no API keys needed

Integration Tests:
- Test integration between AI service and other components
- Still mock Gemini, but test real database interactions

E2E Tests (optional, manual):
- Separate test suite: tests/ai_validation/
- Requires GEMINI_API_KEY
- Run manually or in separate CI job
- Validates actual AI quality, not functionality
```

**Files to refactor**:
- `tests/integration/test_ai_products.py` - Move to unit tests with mocked Gemini
- `tests/integration/test_mock_ai_per_creative.py` - Move to unit tests
- `src/services/ai_*.py` - Add unit tests with mocked responses

### 3. Slack Notifier Tests
**Current State**: Tests skip if `slack_notifier.py` not found
**Problem**: "Why would we not know if slack_notifier.py exists? Don't we control that?"

**Analysis**: Looking at code, we DO control this. The skip is unnecessary.

**Proposed Solution**:
- Slack webhook testing should be simple: "Did we POST to the URL?"
- Mock `requests.post()` to verify we're calling the webhook
- Don't test Slack's API, just test OUR code
- Remove dynamic file existence checks

**Pattern**:
```python
# GOOD - Mock external dependency
with patch('requests.post') as mock_post:
    send_slack_notification(...)
    mock_post.assert_called_once_with(
        webhook_url,
        json=expected_payload
    )

# BAD - Skip if file doesn't exist
if not os.path.exists('slack_notifier.py'):
    pytest.skip()
```

### 4. API Key Validation Tests
**Current State**: `test_tenant_management_api_integration.py` - 7 tests skip if API key validation fails
**Problem**: "If it's not a useful test, let's get rid of it completely"

**Analysis Needed**:
- What are these tests actually validating?
- Are they testing API key functionality or using API keys to test something else?
- If testing API key functionality → Keep with mocked validation
- If testing something else and API key is incidental → Remove the tests or mock the keys

**Action**: Review and decide whether to:
- Mock API key validation
- Delete tests entirely
- Move to separate authenticated test suite

### 5. A2A Server Tests Location
**Current State**: A2A tests in `tests/integration/`
**Problem**: "Shouldn't A2A server tests be part of end-to-end?"

**Analysis**:
- A2A tests currently test HTTP endpoints against localhost:8091
- They're testing the full stack: HTTP → A2A server → business logic
- This IS end-to-end testing

**Proposed Solution**:
```
tests/unit/ - A2A raw function tests (test tools.py functions directly)
tests/integration/ - A2A + database interactions (mocked HTTP)
tests/e2e/ - Full A2A server tests (real HTTP to localhost:8091)
```

**Files to move**:
- `tests/integration/test_a2a_endpoints_working.py` → `tests/e2e/`
- `tests/integration/test_a2a_regression_prevention.py` → `tests/e2e/`
- Keep `test_a2a_response_message_fields.py` in integration (tests serialization)

## Implementation Order

1. ✅ **Delete obsolete get_signals test** (DONE)
2. **Delete skipped migration test** - Simple deletion
3. **Slack notifier cleanup** - Mock requests, remove file existence checks
4. **Review API key tests** - Decide keep vs delete vs mock
5. **Move A2A tests to e2e** - File organization
6. **AI testing strategy** - Largest refactor, create mocked unit tests

## Testing Philosophy

**Golden Rule**: Don't test things outside our control. Mock external dependencies.

**What to Mock**:
- ✅ Gemini API calls
- ✅ Slack webhook POSTs
- ✅ External HTTP requests
- ✅ Third-party APIs

**What NOT to Mock** (in integration tests):
- ✅ Our database (use real PostgreSQL)
- ✅ Our adapters (test real adapter logic)
- ✅ Our business logic

**What to Test in E2E**:
- ✅ Full HTTP request/response cycle
- ✅ Multi-service interactions
- ✅ Real protocol implementations (MCP, A2A)
- ⚠️ Still mock external APIs (Gemini, Slack, GAM)
