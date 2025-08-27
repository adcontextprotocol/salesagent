# End-to-End Testing Guide for AdCP with Strategy Simulation

This guide demonstrates the complete end-to-end testing framework for the AdCP Sales Agent using strategy-based simulation and official protocol clients.

## Overview

The AdCP system now supports **strategy-based testing** that provides:

- **Unified Strategy System**: Same strategy concept works for both production optimization and testing simulation
- **Time Progression Control**: Jump to specific campaign events for deterministic testing
- **Realistic Simulation**: Mock adapter responds according to strategy configuration
- **Multi-Protocol Testing**: Test both MCP and A2A protocols with official clients
- **Parallel Testing**: Run multiple test scenarios concurrently with different strategies

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MCP Client    │    │   A2A Client    │    │ MCP Inspector   │
│   (FastMCP)     │    │   (a2a CLI)     │    │   (Manual)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │  AdCP Server    │
                    │   (Test Mode)   │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │ Strategy System │
                    │ + Mock Adapter  │
                    └─────────────────┘
```

## Quick Start

### 1. Start Test Environment

```bash
# Start isolated test containers
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be healthy
docker-compose -f docker-compose.test.yml ps
```

### 2. Run Automated E2E Tests

```bash
# Run comprehensive test suite
uv run python tests/e2e/test_strategy_simulation_end_to_end.py

# Run specific pytest tests
uv run pytest tests/e2e/ -v
```

### 3. Manual Testing with MCP Inspector

```bash
# Launch MCP Inspector for interactive testing
./scripts/launch_mcp_inspector.sh

# Access at http://localhost:6274
```

### 4. A2A Testing with CLI

```bash
# Test A2A protocol directly
A2A_AUTH_TOKEN=test_advertiser_456 uv run a2a send http://localhost:9091 "What products do you have?"

# Test with different queries
A2A_AUTH_TOKEN=test_advertiser_456 uv run a2a send http://localhost:9091 "Show me video ads for sports content"
```

## Strategy System

### Strategy Types

#### Production Strategies
- `conservative_pacing` - 80% pacing rate, cautious optimization
- `aggressive_scaling` - 130% pacing rate, fast delivery
- `premium_guaranteed` - Focus on viewability and premium placement

#### Simulation Strategies (prefix: `sim_`)
- `sim_happy_path` - Everything works perfectly
- `sim_creative_rejection` - Force creative policy violations
- `sim_budget_exceeded` - Trigger budget overspend scenarios
- `sim_inventory_shortage` - Simulate low inventory availability

### Strategy Usage in Requests

All AdCP requests now accept optional `strategy_id` parameter:

```python
# MCP Client Example
await mcp.call_tool("get_products", {
    "brief": "video ads for sports",
    "promoted_offering": "athletic shoes",
    "strategy_id": "sim_happy_path"  # Links all operations
})

await mcp.call_tool("create_media_buy", {
    "product_ids": ["prod_1"],
    "budget": 50000.0,
    "start_date": "2025-08-01",
    "end_date": "2025-08-15",
    "strategy_id": "sim_happy_path"  # Same strategy context
})
```

## Time Progression Testing

### Simulation Control API

Control time and events in simulations:

```python
# Jump to specific campaign events
await mcp.call_tool("simulation_control", {
    "strategy_id": "sim_test_123",
    "action": "jump_to",
    "parameters": {"event": "campaign-start"}
})

# Jump by relative time
await mcp.call_tool("simulation_control", {
    "strategy_id": "sim_test_123",
    "action": "jump_to",
    "parameters": {"event": "+7d"}  # Jump forward 7 days
})

# Reset simulation
await mcp.call_tool("simulation_control", {
    "strategy_id": "sim_test_123",
    "action": "reset",
    "parameters": {}
})
```

### Available Jump Events

**Campaign Lifecycle:**
- `campaign-created`, `campaign-start`, `campaign-50-percent`, `campaign-end`

**Creative Lifecycle:**
- `creative-submitted`, `creative-approved`, `creative-rejected-policy`

**Error Scenarios:**
- `error-budget-exceeded`, `error-policy-violation`, `error-inventory-unavailable`

**Performance Milestones:**
- `milestone-first-impression`, `milestone-optimization-triggered`

## Test Scenarios

### Scenario 1: Happy Path

```python
async def test_happy_path():
    strategy_id = "sim_test_happy_001"

    # Create campaign
    campaign = await create_media_buy(strategy_id=strategy_id)

    # Jump through lifecycle
    await jump_to_event(strategy_id, "campaign-start")
    await jump_to_event(strategy_id, "campaign-50-percent")

    # Verify delivery
    delivery = await get_delivery_report(campaign_id, strategy_id=strategy_id)
    assert delivery["spend"] > 0
```

### Scenario 2: Budget Exceeded

```python
async def test_budget_exceeded():
    strategy_id = "sim_test_budget_001"

    # Create campaign
    campaign = await create_media_buy(strategy_id=strategy_id, budget=25000)

    # Trigger budget exceeded
    await jump_to_event(strategy_id, "error-budget-exceeded")

    # Verify overspend
    delivery = await get_delivery_report(campaign_id, strategy_id=strategy_id)
    assert delivery["spend"] > 25000  # Should be overspent
```

### Scenario 3: Parallel Strategies

```python
async def test_parallel_strategies():
    # Two campaigns with different strategies
    strategy_a = "sim_test_parallel_a"
    strategy_b = "sim_test_parallel_b"

    campaign_a = await create_media_buy(strategy_id=strategy_a)
    campaign_b = await create_media_buy(strategy_id=strategy_b)

    # Different scenarios
    await set_scenario(strategy_a, "high_performance")
    await set_scenario(strategy_b, "underperforming")

    # Compare results
    delivery_a = await get_delivery_report(campaign_a, strategy_id=strategy_a)
    delivery_b = await get_delivery_report(campaign_b, strategy_id=strategy_b)

    assert delivery_a["spend"] > delivery_b["spend"]
```

## Mock Adapter Strategy Behavior

The mock adapter responds differently based on strategy:

### Production Strategies
- **Conservative Pacing**: 80% of normal delivery rate
- **Aggressive Scaling**: 130% of normal delivery rate
- **Premium Guaranteed**: Higher viewability, premium inventory only

### Simulation Strategies
- **Happy Path**: Perfect delivery, no errors
- **Budget Exceeded**: Overspends by 15%
- **Creative Rejection**: Forces creative policy violations
- **High Performance**: 130% delivery acceleration
- **Underperforming**: 60% of expected delivery

## Authentication

### Test Tokens

The test environment provides these tokens:

```bash
# Admin token (full access)
TEST_ADMIN_TOKEN="test_admin_123"

# Advertiser token (campaign management)
TEST_ADVERTISER_TOKEN="test_advertiser_456"
```

### Using Tokens

**MCP Client:**
```python
headers = {"x-adcp-auth": "test_advertiser_456"}
transport = StreamableHttpTransport(url="http://localhost:9080/mcp/", headers=headers)
```

**A2A CLI:**
```bash
A2A_AUTH_TOKEN=test_advertiser_456 uv run a2a send http://localhost:9091 "query"
```

## Testing Checklist

### ✅ Core Functionality
- [ ] MCP client can connect and authenticate
- [ ] A2A CLI can connect and authenticate
- [ ] Products can be retrieved with strategy context
- [ ] Media buys can be created with strategy
- [ ] Delivery reports reflect strategy behavior

### ✅ Strategy System
- [ ] Production strategies affect pacing/bidding
- [ ] Simulation strategies enable time control
- [ ] Parallel strategies work independently
- [ ] Strategy persistence across operations

### ✅ Time Progression
- [ ] Can jump to campaign events
- [ ] Can advance time by duration
- [ ] Can reset simulation state
- [ ] Events trigger appropriate behavior

### ✅ Error Scenarios
- [ ] Budget exceeded simulation works
- [ ] Creative rejection simulation works
- [ ] Inventory shortage simulation works
- [ ] Error recovery scenarios work

### ✅ Protocol Compliance
- [ ] MCP Inspector can explore all tools
- [ ] A2A queries return proper responses
- [ ] Authentication works across protocols
- [ ] Error handling is consistent

## Troubleshooting

### Common Issues

**Test Server Not Starting:**
```bash
# Check container status
docker-compose -f docker-compose.test.yml ps

# Check logs
docker-compose -f docker-compose.test.yml logs adcp-server

# Restart services
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose.test.yml up -d
```

**Authentication Failures:**
```bash
# Verify tokens are correctly configured
curl -H "x-adcp-auth: test_advertiser_456" http://localhost:9080/health
```

**Simulation Not Working:**
- Ensure strategy_id starts with "sim_" prefix
- Check that strategy was created in database
- Verify simulation control permissions

**MCP Inspector Issues:**
```bash
# Check if npx is available
npx --version

# Install MCP Inspector manually
npm install -g @modelcontextprotocol/inspector
```

## Advanced Usage

### Custom Test Strategies

Create custom simulation strategies:

```python
strategy_id = f"sim_custom_test_{uuid.uuid4().hex[:8]}"

# Strategy will be auto-created with custom behavior
await mcp.call_tool("create_media_buy", {
    "strategy_id": strategy_id,
    # ... other parameters
})

# Customize behavior
await mcp.call_tool("simulation_control", {
    "strategy_id": strategy_id,
    "action": "set_scenario",
    "parameters": {"scenario": "custom_behavior"}
})
```

### Performance Testing

Test with realistic load:

```python
async def stress_test():
    # Create multiple concurrent campaigns
    strategies = [f"sim_stress_{i}" for i in range(10)]

    tasks = []
    for strategy in strategies:
        task = create_and_run_campaign(strategy_id=strategy)
        tasks.append(task)

    # Wait for all to complete
    results = await asyncio.gather(*tasks)

    # Analyze performance
    avg_response_time = sum(r["duration"] for r in results) / len(results)
    print(f"Average response time: {avg_response_time:.2f}s")
```

## Next Steps

1. **Extend Test Coverage**: Add more edge case scenarios
2. **Performance Benchmarking**: Measure response times under load
3. **Integration Tests**: Test with real ad server adapters
4. **Regression Testing**: Automate against production-like data
5. **Monitoring Integration**: Add observability to test runs

## Resources

- [MCP Inspector Documentation](https://modelcontextprotocol.io/tools/inspector)
- [A2A CLI Usage](https://github.com/adcontextprotocol/adcp)
- [FastMCP Client Documentation](https://fastmcp.dev/docs/client)
- [AdCP Protocol Specification](https://adcontextprotocol.github.io/)

---

For questions or issues with the testing framework, check the existing test examples or create new test scenarios following the patterns above.
