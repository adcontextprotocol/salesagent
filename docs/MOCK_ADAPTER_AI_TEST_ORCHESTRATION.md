# Mock Adapter AI Test Orchestration

**Complete Guide to Natural Language Testing with the Mock Adapter**

## Table of Contents
1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [How It Works](#how-it-works)
5. [Usage Examples](#usage-examples)
6. [What You Can Test](#what-you-can-test)
7. [Implementation Details](#implementation-details)
8. [Migration from Old System](#migration-from-old-system)
9. [Configuration](#configuration)
10. [Test Results](#test-results)

---

## Overview

The AI Test Orchestrator uses **Gemini AI (gemini-2.5-flash-lite)** to interpret natural language test instructions and control the mock adapter's behavior. This enables comprehensive AdCP protocol testing without hardcoded scenarios or special test products.

**Key Concept**: Buyers write what they want to test in plain English → AI interprets intent → Mock adapter executes the scenario

### Benefits

- **Natural Language**: No keywords to memorize
- **Flexible**: AI handles phrasing variations automatically
- **Complex Scenarios**: Multi-step, conditional logic supported
- **Per-Creative Control**: Each creative controls its own behavior
- **Zero Config**: No special products or principals needed
- **Safe Fallback**: Works without AI (auto-approves)
- **Self-Documenting**: Test intent clear from message

---

## Quick Start

### Create Media Buy with Test Scenario

```python
from fastmcp.client import Client, StreamableHttpTransport

headers = {"x-adcp-auth": "your_token"}
transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
client = Client(transport=transport)

async with client:
    # Test: Wait 10 seconds before responding
    result = await client.tools.create_media_buy(
        promoted_offering="Wait 10 seconds before responding",
        packages=[...],
        buyer_ref="test-001"
    )
```

### Sync Creatives with Per-Creative Control

```python
# Each creative's name controls its own outcome
result = await client.tools.sync_creatives(
    media_buy_id="buy_123",
    creatives=[
        {
            "name": "approve this banner",
            "id": "creative_1",
            "format": "display_300x250",
            "media_url": "https://example.com/banner.jpg",
            "click_url": "https://example.com/click"
        },
        {
            "name": "reject for missing click URL",
            "id": "creative_2",
            "format": "display_300x250",
            "media_url": "https://example.com/banner2.jpg",
            "click_url": "https://example.com/click2"
        },
        {
            "name": "ask for brand logo",
            "id": "creative_3",
            "format": "display_300x250",
            "media_url": "https://example.com/banner3.jpg",
            "click_url": "https://example.com/click3"
        }
    ]
)
# Result: creative_1 approved, creative_2 rejected, creative_3 pending
```

---

## Architecture

```
Buyer Message (natural language)
    ↓
Gemini 2.5 Flash Lite
    ↓
TestScenario (structured)
    ↓
Mock Adapter Execution
    ↓
Protocol Response (delayed, rejected, questioned, etc.)
```

### Three-Phase Process

1. **AI Interpretation**: Gemini parses natural language → structured `TestScenario`
2. **Mock Adapter Execution**: Applies scenario (delays, rejections, questions, etc.)
3. **Protocol Response**: Returns AdCP-compliant response with test behavior

### Message Field Locations

**For `create_media_buy`**:
- Uses `promoted_offering` (brief field) for test instructions
- Mock adapter doesn't need real briefs, so this field is available for testing

**For `sync_creatives`**:
- Uses each creative's `name` field for per-creative instructions
- Each creative controls its own test behavior independently
- AI processes one creative at a time

**For delivery**:
- Test scenario stored at media buy creation
- Delivery methods automatically use stored instructions
- No separate AI call needed for delivery

---

## How It Works

### 1. Buyer Sends Message

```python
# In the promoted_offering field
promoted_offering="Wait 10 seconds then reject with reason 'Budget too high'"
```

### 2. AI Interprets Intent

Gemini receives a structured prompt:
```
You are a test orchestrator for an advertising protocol mock server.
A buyer has sent test instructions: "Wait 10 seconds then reject with reason 'Budget too high'"

Return JSON describing what the mock server should do:
{
  "delay_seconds": 10,
  "should_reject": true,
  "rejection_reason": "Budget too high"
}
```

### 3. Mock Adapter Execution

```python
# Mock adapter reads the TestScenario
if scenario.delay_seconds:
    time.sleep(scenario.delay_seconds)  # Wait 10 seconds

if scenario.should_reject:
    raise Exception(f"Media buy rejected: {scenario.rejection_reason}")
```

### 4. Protocol Response

```
HTTP 500
Exception: Media buy rejected: Budget too high
```

---

## Usage Examples

### Example 1: Simple Delay

```python
await client.create_media_buy(
    promoted_offering="Wait 10 seconds before responding",
    packages=[...],
    buyer_ref="test-delay"
)
# Mock adapter delays 10 seconds, then proceeds normally
```

### Example 2: Rejection

```python
await client.create_media_buy(
    promoted_offering="Reject this with reason 'Budget exceeds inventory'",
    packages=[...],
    buyer_ref="test-reject"
)
# Raises: Exception("Media buy rejected: Budget exceeds inventory")
```

### Example 3: Question / Clarification

```python
await client.create_media_buy(
    promoted_offering="Ask me for more details about the target audience",
    packages=[...],
    buyer_ref="test-question"
)
# Returns: CreateMediaBuyResponse(
#     status="pending",
#     message="Additional information needed: Please specify target audience details"
# )
```

### Example 4: Human-in-the-Loop Simulation

```python
await client.create_media_buy(
    promoted_offering="Simulate human approval workflow with 5 minute review",
    packages=[...],
    buyer_ref="test-hitl"
)
# Creates workflow step, delays 5 minutes, then approves
```

### Example 5: Async Workflow

```python
await client.create_media_buy(
    promoted_offering="Return pending status and require polling",
    packages=[...],
    buyer_ref="test-async"
)
# Returns: CreateMediaBuyResponse(
#     status="submitted",
#     media_buy_id="pending_abc123"
# )
# Buyer must poll to get final status
```

### Example 6: Per-Creative Control

```python
await client.sync_creatives(
    media_buy_id="buy_123",
    creatives=[
        {
            "name": "approve this one",
            "id": "creative_1",
            ...
        },
        {
            "name": "reject for missing click URL",
            "id": "creative_2",
            ...
        },
        {
            "name": "ask for brand logo",
            "id": "creative_3",
            ...
        }
    ]
)
# Each creative's name field controls its own outcome
# AI processes each one individually
```

### Example 7: Delivery Testing

```python
# Set delivery instructions at media buy creation
await client.create_media_buy(
    promoted_offering="""
        Day 1-2: Normal delivery
        Day 3: Simulate platform slowdown (30% of expected)
        Day 4: Simulate complete outage
        Day 5+: Resume normal delivery
    """,
    packages=[...],
    buyer_ref="test-delivery"
)

# Later: Delivery methods automatically use stored instructions
delivery = await client.get_media_buy_delivery(media_buy_id="buy_123")
# Behavior changes based on campaign day
```

### Example 8: Complex Multi-Step Scenario

```python
await client.create_media_buy(
    promoted_offering="""
        Simulate a complex approval workflow:
        1. Wait 2 minutes for initial review
        2. Ask me to clarify the target demographic
        3. After clarification, wait another 5 minutes
        4. Then approve with standard terms
    """,
    packages=[...],
    buyer_ref="test-complex"
)
# AI interprets the sequence and orchestrates multi-turn interaction
```

---

## What You Can Test

### Timing Control

- **Delays**: `delay_seconds` - Delay response by N seconds
- **Async Mode**: `use_async` - Return pending status, require polling

```python
"Wait 10 seconds before responding"
"Return pending status and require polling"
```

### Response Control

- **Rejections**: `should_reject`, `rejection_reason` - Reject with reason
- **Questions**: `should_ask_question`, `question_text` - Ask for clarification
- **Errors**: `error_message` - Raise exception with message

```python
"Reject this with reason 'Budget too high'"
"Ask me for more details about target audience"
"Simulate platform error: Service temporarily unavailable"
```

### Human-in-the-Loop

- **HITL Simulation**: `simulate_hitl` - Create workflow step
- **HITL Delay**: `hitl_delay_minutes` - How long to wait
- **HITL Outcome**: `hitl_outcome` - "approve" or "reject"

```python
"Simulate human approval after 5 minutes"
"Create workflow step requiring manual review, then reject"
```

### Creative Actions

- **Per-Creative Directives**: Each creative controls its own behavior
  - `approve` - Creative approved
  - `reject` - Creative rejected with reason
  - `request_changes` - Needs modifications (pending status)
  - `ask_for_field` - Missing required field (pending status)

```python
# In creative name fields:
"approve this banner"
"reject for missing click URL"
"ask for brand logo"
"request changes to add captions"
```

### Delivery Simulation

- **Delivery Profile**: `delivery_profile` - "slow", "fast", "uneven", "normal"
- **Outage**: `simulate_outage` - Raise platform error
- **Percentage**: `delivery_percentage` - Override with specific percentage

```python
"Deliver slowly over the campaign"
"Simulate platform outage on day 3"
"Deliver exactly 50% of expected impressions"
```

---

## Implementation Details

### Core Components

**`AITestOrchestrator`** (`src/adapters/ai_test_orchestrator.py`)
- Configures Gemini API (`gemini-2.5-flash-lite`)
- Builds prompts for each operation type
- Parses AI responses into `TestScenario` objects
- Handles errors gracefully (falls back to normal behavior)

**`TestScenario`** (dataclass)
```python
@dataclass
class TestScenario:
    delay_seconds: Optional[int] = None
    use_async: bool = False
    should_accept: bool = True
    should_reject: bool = False
    rejection_reason: Optional[str] = None
    should_ask_question: bool = False
    question_text: Optional[str] = None
    simulate_hitl: bool = False
    hitl_delay_minutes: Optional[int] = None
    hitl_outcome: Optional[str] = None
    creative_actions: list[dict] = None  # Per-creative directives
    delivery_profile: Optional[str] = None
    simulate_outage: bool = False
    delivery_percentage: Optional[float] = None
    error_message: Optional[str] = None
```

**Mock Adapter Integration** (`src/adapters/mock_ad_server.py`)

*create_media_buy*:
```python
# Check promoted_offering field for test instructions
scenario = None
test_message = request.promoted_offering
if test_message and isinstance(test_message, str) and test_message.strip():
    try:
        orchestrator = AITestOrchestrator()
        scenario = orchestrator.interpret_message(test_message, "create_media_buy")
    except Exception as e:
        self.log(f"⚠️ AI orchestrator unavailable: {e}")

# Execute AI scenario if present
if scenario:
    if scenario.delay_seconds:
        time.sleep(scenario.delay_seconds)
    if scenario.should_reject:
        raise Exception(f"Media buy rejected: {scenario.rejection_reason}")
    # ... more scenario handling
```

*sync_creatives*:
```python
# Process each creative individually
for asset in assets:
    creative_name = asset.get("name", "")

    # Try AI orchestration first
    if orchestrator and creative_name and creative_name.strip():
        try:
            scenario = orchestrator.interpret_message(creative_name, "sync_creatives")

            if scenario.should_reject:
                results.append(AssetStatus(creative_id=asset["id"], status="rejected"))
            elif scenario.creative_actions:
                # Handle specific action
                action = scenario.creative_actions[0]
                # ... apply action
        except Exception as e:
            # Fall back to auto-approve
            results.append(AssetStatus(creative_id=asset["id"], status="approved"))
```

*get_delivery*:
```python
# Load stored test scenario from media buy
test_scenario_data = buy.get("test_scenario")
test_scenario = None
if test_scenario_data:
    test_scenario = TestScenario(**test_scenario_data)

# Apply delivery simulation
if test_scenario and test_scenario.simulate_outage:
    raise Exception("Simulated platform outage")
elif test_scenario and test_scenario.delivery_profile:
    delivery_progress = self._calculate_delivery_progress(
        test_scenario.delivery_profile, current_day, campaign_duration
    )
    # ... apply delivery profile
```

### Test Storage

Test scenarios are stored in the media buy at creation time:

```python
self._media_buys[media_buy_id] = {
    "media_buy_id": media_buy_id,
    "name": order_name,
    "packages": packages,
    "total_budget": total_budget,
    "start_time": start_time,
    "end_time": end_time,
    "creatives": [],
    "test_scenario": scenario.__dict__ if scenario else None,  # Stored for delivery
}
```

This allows delivery methods to use the test scenario without requiring another AI call.

---

## Simulation Control Capabilities

Beyond AI-powered test orchestration, the mock adapter provides extensive simulation controls for realistic testing scenarios.

### Delivery Simulation

**Time-Accelerated Campaigns**: Test full campaign lifecycles in seconds/minutes instead of days/weeks.

**Configuration via Admin UI:**
1. Navigate to **Products** → Select mock product → **Configure**
2. Scroll to **Delivery Simulation** section
3. Configure:
   - **Enable Delivery Simulation**: Turn on/off
   - **Time Acceleration**: Real seconds = Simulated hours (default: `3600` = 1 sec = 1 hour)
   - **Update Interval**: Webhook frequency in real-time seconds (default: `1.0`)

**Example Scenarios:**

```
Fast Testing (1 second = 1 hour):
- Time Acceleration: 3600
- Update Interval: 1.0 seconds
- Result: 7-day campaign completes in 168 seconds (~2.8 minutes)
- Webhooks: Every 1 second (= 1 hour of campaign time)

Ultra-Fast Testing (1 second = 1 day):
- Time Acceleration: 86400
- Update Interval: 1.0 seconds
- Result: 7-day campaign completes in 7 seconds
- Webhooks: Every 1 second (= 1 day of campaign time)

Slow Motion (1 second = 1 minute):
- Time Acceleration: 60
- Update Interval: 1.0 seconds
- Result: 7-day campaign completes in 10,080 seconds (~2.8 hours)
- Useful for watching delivery in "real-ish" time
```

**Webhook Payload**: AdCP V2.3 compliant `GetMediaBuyDeliveryResponse`
- `notification_type`: `scheduled` (periodic) or `final` (completed)
- `sequence_number`: Incremental counter starting at 1
- `next_expected_at`: ISO timestamp for next webhook
- `media_buy_deliveries`: Array with impressions, spend, clicks, CTR

### Human-in-the-Loop (HITL) Simulation

**Test approval workflows** without requiring actual human intervention.

**Configuration** (via principal's `platform_mappings.mock.hitl_config`):

```json
{
  "mock": {
    "hitl_config": {
      "enabled": true,
      "mode": "sync",  // or "async" or "mixed"
      "sync_settings": {
        "delay_ms": 2000,
        "streaming_updates": true,
        "update_interval_ms": 500
      },
      "async_settings": {
        "auto_complete": true,
        "auto_complete_delay_ms": 10000,
        "webhook_url": "https://your-app.com/webhooks/hitl"
      },
      "approval_simulation": {
        "enabled": true,
        "approval_probability": 0.8,
        "rejection_reasons": [
          "Budget exceeds limits",
          "Invalid targeting"
        ]
      }
    }
  }
}
```

**HITL Modes:**
- **`sync`**: Delays response by configured time (simulates slow approval)
- **`async`**: Returns pending status, completes via webhook later
- **`mixed`**: Per-operation mode overrides

**Example - Sync Mode:**
```python
# Principal configured with 2-second HITL delay
start = time.time()
result = await client.tools.create_media_buy(...)
elapsed = time.time() - start

# Should take ~2 seconds due to HITL delay
assert 1.8 <= elapsed <= 2.5
assert result.status == "active"
```

**Example - Async Mode:**
```python
# Returns immediately with pending status
result = await client.tools.create_media_buy(...)
assert result.status == "pending"

# Webhook fired after auto_complete_delay_ms
# Agent receives completion notification
```

### Traffic & Performance Simulation

**Configure via Admin UI** (Mock Product → Configure):

**Traffic Simulation:**
- **Impressions**: Volume per day (e.g., 100,000)
- **Fill Rate**: Percentage of requests filled (e.g., 85%)
- **CTR**: Click-through rate (e.g., 1.2%)
- **Viewability**: Percentage viewable (e.g., 70%)

**Performance Simulation:**
- **Latency**: API response time in milliseconds (e.g., 150ms)
- **Error Rate**: Percentage of failed requests (e.g., 2%)

**Test Scenarios** (predefined modes):
- **Normal**: Standard behavior
- **High Demand**: Increased traffic and competition
- **Degraded**: Slow responses, partial failures
- **Outage**: Complete service failure

### Targeting Capabilities

**Mock adapter supports ALL targeting dimensions** (unlike real adapters with limitations):

✅ **Geographic**: Countries, regions, metros
✅ **Device Types**: Desktop, mobile, tablet, CTV, DOOH, audio
✅ **Operating Systems**: iOS, Android, Windows, etc.
✅ **Browsers**: Chrome, Safari, Firefox, etc.
✅ **Content Categories**: IAB taxonomy
✅ **Keywords**: Contextual targeting
✅ **Custom Key-Value Pairs**: AEE integration, custom signals

**Example - Complex Targeting:**
```python
result = await client.tools.create_media_buy(
    promoted_offering="Multi-dimension targeting test",
    product_ids=["prod_1"],
    total_budget=5000.0,
    flight_start_date="2025-10-10",
    flight_end_date="2025-10-17",
    targeting_overlay={
        "geo_country_any_of": ["US", "CA"],
        "geo_region_any_of": ["CA", "NY", "TX"],
        "device_type_any_of": ["mobile", "tablet"],
        "os_any_of": ["ios", "android"],
        "browser_any_of": ["chrome", "safari"],
        "content_cat_any_of": ["sports", "entertainment"],
        "keywords_any_of": ["basketball", "playoffs"],
        "key_value_pairs": [
            {"key": "aee_audience", "value": "sports_enthusiasts"},
            {"key": "content_rating", "value": "family_friendly"}
        ]
    }
)
# Mock adapter accepts ALL targeting without errors
```

**Note**: For testing targeting errors, configure mock to reject specific dimensions.

### Combining AI Orchestration + Simulation

**Powerful combination** for comprehensive testing:

```python
# 1. AI-controlled test scenario
await client.tools.create_media_buy(
    promoted_offering="""
        Simulate slow delivery ramp-up for first 3 days,
        then simulate platform issues on day 4,
        followed by recovery with accelerated delivery.
    """,
    product_ids=["prod_mock_1"],
    total_budget=10000.0,
    flight_start_date="2025-10-10",
    flight_end_date="2025-10-17"
)

# 2. Delivery simulation running at 3600x speed (1 sec = 1 hour)
# 3. HITL enabled with 2-second approval delay
# 4. Webhooks firing every 1 second with realistic metrics
# 5. Agent responds to delivery updates in real-time

# Result: Full campaign lifecycle tested in ~3 minutes
```

### Setting Up Webhook Endpoints

**For delivery simulation webhooks:**

1. **Register webhook in Admin UI:**
   - Navigate to **Principals** → Select principal → **Manage Webhooks**
   - Add webhook URL with authentication
   - Test webhook delivery

2. **Enable delivery simulation** in product config (see above)

3. **Create media buy** → Simulation starts automatically, webhooks begin firing

**Sample webhook handler:**
```python
async def handle_delivery_webhook(payload):
    """Process AdCP V2.3 delivery webhook."""
    delivery = payload["data"]["media_buy_deliveries"][0]
    progress = delivery["totals"]["impressions"]
    budget_spent = delivery["totals"]["spend"]

    # Check pacing
    if is_under_pacing(progress, budget_spent):
        await increase_bids()
    elif is_over_pacing(progress, budget_spent):
        await decrease_bids()

    # Check if completed
    if payload["data"]["notification_type"] == "final":
        await generate_final_report()
```

---

## Migration from Old System

### What Was Removed

The AI orchestrator completely replaced the old regex-based system:

**Deprecated:**
- ❌ `MockTestDirectives` (regex pattern matching)
- ❌ `_initialize_mock_objects()` (hardcoded GAM-like test data)
- ❌ Special test products and principals
- ❌ Hardcoded ad units, targeting keys, templates
- ❌ 350+ lines of test infrastructure code

**Removed Files:**
- `src/adapters/mock_test_directives.py`
- `tests/unit/test_mock_test_directives.py`
- `tests/integration/test_mock_adapter_directives.py`

**Archived Documentation:**
- `DEPRECATED_MOCK_ADAPTER_TEST_DIRECTIVES.md`
- `DEPRECATED_MOCK_DIRECTIVES_SUMMARY.md`

### Migration Path

**Before** (regex):
```python
# Required specific keywords
promoted_offering="Campaign with slow delivery. Fail on day 3."
```

**After** (AI):
```python
# Natural language
promoted_offering="Test slow ramp-up delivery, then simulate platform issues on day 3"
```

Both achieve the same result, but AI is more flexible and understands variations.

**For creatives** (AI only):
```python
# Each creative controls its own behavior
creatives=[
    {"name": "approve this banner", ...},
    {"name": "reject this video for missing captions", ...}
]
```

---

## Configuration

### API Key

Set `GEMINI_API_KEY` environment variable:

```bash
# In .env.secrets file
GEMINI_API_KEY="your-gemini-api-key"
```

### Fallback Behavior

If AI orchestrator fails (no API key, network error, parsing error):
- Logs warning
- Falls back to normal mock adapter behavior (auto-approve)
- Does not block operations

This ensures testing works even without AI.

---

## Test Results

### Unit Tests (23/23 passing)

```bash
uv run pytest tests/unit/test_ai_orchestrator.py -v

# Test categories:
✓ Initialization (3 tests)
✓ JSON extraction (3 tests)
✓ Scenario parsing (5 tests)
✓ Prompt building (3 tests)
✓ Real AI integration (6 tests) - Uses live Gemini API
```

### Real AI Integration Tests

```bash
✓ test_interpret_simple_delay - "Wait 10 seconds" → delay_seconds=10
✓ test_interpret_rejection - "Reject with reason X" → should_reject=True
✓ test_interpret_hitl - "Human approval after 2 min" → simulate_hitl=True
✓ test_interpret_creative_reject - "reject for missing URL" → reject action
✓ test_interpret_creative_approve - "approve this" → approve action
✓ test_interpret_creative_ask_for_field - "ask for logo" → ask action
```

### Mock Adapter Tests

```bash
uv run pytest tests/unit/ -k "mock" --tb=short -v

# Result: 11/11 passing
✓ test_mock_ad_server_create_media_buy
✓ test_next_event_calculator_lifecycle_progression
✓ test_response_headers_with_campaign_info
✓ ... 8 more
```

---

## Advantages Over Regex Parsing

1. **Natural Language**: Buyers don't need to learn specific keywords
2. **Flexible**: Handles variations in phrasing automatically
3. **Complex Scenarios**: Can understand multi-step, conditional logic
4. **Contextual**: Interprets intent based on operation type
5. **Extensible**: New capabilities just need prompt updates, not code changes
6. **Self-Documenting**: Test intent is clear from the message itself

---

## Limitations

1. **API Dependency**: Requires Gemini API key and network access
2. **Non-Deterministic**: Same input might produce slightly different interpretations
3. **Latency**: Adds ~200-500ms for AI inference (per creative for sync_creatives)
4. **Cost**: Small API cost per request (though minimal with gemini-2.5-flash-lite)
5. **Stateless**: No memory across operations (by design)

---

## Future Enhancements

- **Batch Creative Processing**: Optimize to process multiple creatives in one AI call
- **Multi-Agent Support**: Different test behaviors per buyer/agent
- **Scenario Library**: Pre-defined test scripts buyers can reference
- **Recording Mode**: Capture real scenarios for replay
- **Fine-Tuning**: Train custom model on common test patterns

---

## Summary

**AI-powered test orchestration is production-ready!**

✅ **Natural language** test instructions via Gemini
✅ **Per-creative control** for granular testing
✅ **23/23 tests passing** including real AI integration
✅ **Delivery simulation** with stored scenarios
✅ **Zero config** - no special products needed
✅ **Safe fallback** - works without AI
✅ **350+ lines removed** - cleaner codebase

**Key Files:**
- `src/adapters/ai_test_orchestrator.py` - Core orchestrator
- `src/adapters/mock_ad_server.py` - Mock adapter integration
- `tests/unit/test_ai_orchestrator.py` - Comprehensive tests
- `tests/integration/test_mock_ai_per_creative.py` - Integration tests

Buyers can now write what they want to test in plain English, and the mock adapter orchestrates the appropriate behavior automatically!
