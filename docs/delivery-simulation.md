# Mock Adapter Delivery Simulation

## Overview

The Mock Adapter includes a real-time delivery simulation system that fires webhooks as campaigns progress. This allows you to test AI agents' responses to delivery updates without waiting for actual campaign durations.

## How It Works

When you create a media buy using the mock adapter, it can automatically:

1. **Start a background simulation thread** that tracks campaign progress
2. **Fire webhooks at regular intervals** with delivery metrics
3. **Accelerate time** so seconds become hours (configurable)
4. **Send realistic metrics** including impressions, spend, pacing, and performance

## Configuration

### Enable in Admin UI

1. Navigate to **Products** for your tenant
2. Click **Configure** on a mock adapter product
3. Scroll to **Delivery Simulation** section
4. Check **Enable Delivery Simulation**
5. Configure acceleration and interval settings
6. Save configuration

### Configuration Options

| Setting | Description | Default | Example Values |
|---------|-------------|---------|----------------|
| **Enabled** | Turn delivery simulation on/off | `false` | `true` / `false` |
| **Time Acceleration** | Real seconds = Simulated seconds | `3600` (1 sec = 1 hour) | `60` (1 sec = 1 min)<br>`86400` (1 sec = 1 day) |
| **Update Interval** | How often to fire webhooks (real-time) | `1.0` seconds | `0.5` (twice per second)<br>`5.0` (every 5 seconds) |

### Example Scenarios

**Fast Testing (1 second = 1 hour)**
```
Time Acceleration: 3600
Update Interval: 1.0 seconds

Result:
- 7-day campaign completes in 168 seconds (~2.8 minutes)
- Webhook fires every 1 second (= 1 hour of campaign time)
- 168 total webhooks
```

**Ultra-Fast Testing (1 second = 1 day)**
```
Time Acceleration: 86400
Update Interval: 1.0 seconds

Result:
- 7-day campaign completes in 7 seconds
- Webhook fires every 1 second (= 1 day of campaign time)
- 7 total webhooks
```

**Slow Motion (1 second = 1 minute)**
```
Time Acceleration: 60
Update Interval: 1.0 seconds

Result:
- 7-day campaign completes in 10,080 seconds (~2.8 hours)
- Webhook fires every 1 second (= 1 minute of campaign time)
- Useful for watching delivery in "real-ish" time
```

## Webhook Payload

Each delivery update webhook includes:

```json
{
  "task_id": "buy_abc123",
  "status": "delivering",
  "timestamp": "2025-10-07T12:34:56.789Z",
  "tenant_id": "tenant_123",
  "principal_id": "principal_456",
  "data": {
    "event_type": "delivery_update",
    "media_buy_id": "buy_abc123",
    "status": "started" | "delivering" | "completed",
    "simulated_time": "2025-10-08T15:00:00Z",
    "progress": {
      "elapsed_hours": 27.5,
      "total_hours": 168.0,
      "progress_percentage": 16.4
    },
    "delivery": {
      "impressions": 45000,
      "spend": 450.00,
      "total_budget": 5000.00,
      "pacing_percentage": 9.0
    },
    "metrics": {
      "cpm": 10.00,
      "clicks": 450,
      "ctr": 0.01
    }
  }
}
```

### Webhook Events

| Status | Description | When Fired |
|--------|-------------|------------|
| `started` | Campaign just began | First webhook (0% progress) |
| `delivering` | Campaign in progress | Every update interval |
| `completed` | Campaign finished | Final webhook (100% progress) |

## Setting Up Webhook Endpoints

### Step 1: Register Webhook in Admin UI

1. Navigate to **Principals** for your tenant
2. Select the principal (advertiser)
3. Click **Manage Webhooks**
4. Add webhook URL with authentication
5. Test webhook delivery

### Step 2: Configure Mock Product

Enable delivery simulation for the product (see Configuration above).

### Step 3: Create Media Buy

When you create a media buy via MCP/A2A:

```python
# Via MCP
result = await client.tools.create_media_buy(
    promoted_offering="Test Campaign",
    product_ids=["prod_mock_1"],
    total_budget=5000.0,
    flight_start_date="2025-10-08",
    flight_end_date="2025-10-15"
)

# Delivery simulation starts automatically
# Webhooks begin firing immediately
```

## Testing with AI Agents

### Example: Agent Monitoring Campaign

Your AI agent can:

1. **Create media buy** → Delivery simulation starts
2. **Receive delivery webhooks** → Process every 1 second
3. **Check pacing** → If under-delivering, take action
4. **Optimize in real-time** → Update bids, targeting, etc.
5. **Complete quickly** → Test full lifecycle in minutes

### Sample Agent Response Logic

```python
async def handle_delivery_webhook(payload):
    progress = payload["data"]["progress"]["progress_percentage"]
    pacing = payload["data"]["delivery"]["pacing_percentage"]

    if progress > pacing + 10:
        # Under-delivering by >10%
        await increase_bids()
    elif progress < pacing - 10:
        # Over-delivering by >10%
        await decrease_bids()

    if payload["data"]["status"] == "completed":
        await generate_final_report()
```

## Advanced Configuration

### Per-Tenant Configuration (Direct Database)

For more advanced users, you can configure delivery simulation directly in the tenant's adapter config:

```json
{
  "adapters": {
    "mock": {
      "enabled": true,
      "delivery_simulation": {
        "enabled": true,
        "time_acceleration": 3600,
        "update_interval_seconds": 1.0
      }
    }
  }
}
```

### Per-Product Configuration (Admin UI Preferred)

Use the Admin UI to configure per-product settings (recommended approach).

## Troubleshooting

### Webhooks Not Firing

**Check:**
1. Is delivery simulation **enabled** in product config?
2. Is webhook configured for the principal?
3. Is webhook URL reachable?
4. Check server logs: `docker-compose logs -f adcp-server`

**Common Issues:**
- Webhook URL requires authentication → Configure auth token
- Firewall blocking outbound requests → Check network settings
- Simulation thread failed → Check logs for errors

### Too Many/Few Webhooks

**Adjust settings:**
- **Too many?** → Increase update interval (e.g., 5.0 seconds)
- **Too few?** → Decrease update interval (e.g., 0.5 seconds)
- **Too fast?** → Decrease time acceleration
- **Too slow?** → Increase time acceleration

### Simulation Not Starting

**Debugging:**
```bash
# Check adapter logs
docker-compose logs -f adcp-server | grep "delivery simulation"

# Should see:
# "🚀 Starting delivery simulation (acceleration: 3600x, interval: 1.0s)"
# "📊 Simulation parameters for buy_abc123..."
```

**If missing:**
1. Verify config saved correctly (check database)
2. Ensure dry_run is `false` (simulation only runs in real mode)
3. Check for errors in media buy creation

## Architecture Notes

### Thread Safety

- Each media buy gets its own background thread
- Threads are daemon threads (won't block shutdown)
- Stop signals allow graceful termination

### Performance Impact

- **Minimal CPU:** Thread sleeps between updates
- **Minimal memory:** ~1KB per active simulation
- **Network:** One HTTP POST per webhook interval

### Scaling Considerations

For production deployments with many concurrent campaigns:

1. **Increase update interval** → Reduce webhook frequency
2. **Use time acceleration wisely** → Don't simulate faster than needed
3. **Monitor webhook endpoint** → Ensure it can handle volume
4. **Consider batching** → Group multiple campaigns if needed

## Future Enhancements

Potential improvements:

- [ ] Delivery anomaly simulation (sudden drops, spikes)
- [ ] Webhook retry with exponential backoff
- [ ] Delivery event history in Admin UI
- [ ] Pause/resume simulation controls
- [ ] Campaign-specific acceleration overrides

## Related Documentation

- [Webhook Management](webhooks.md)
- [Mock Adapter Configuration](../src/adapters/mock_ad_server.py)
- [Push Notification Service](../src/services/push_notification_service.py)
- [Delivery Simulator](../src/services/delivery_simulator.py)
