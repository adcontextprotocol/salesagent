# A2A (Agent-to-Agent) Protocol Implementation

## Overview

The AdCP Sales Agent implements the A2A protocol using the standard `python-a2a` library, allowing AI agents to query advertising inventory and create media buys programmatically.

## Server Implementation

- **Library**: Standard `python-a2a` with custom business logic
- **Location**: `src/a2a/adcp_a2a_server.py`
- **Port**: 8091 (local), available at `/a2a` path in production
- **Authentication**: Required via Bearer tokens

## Authentication

All A2A requests require authentication using advertiser tokens:

```bash
# Using the provided query script (recommended)
A2A_TOKEN=your_token ./scripts/a2a_query.py "What products are available?"

# Using curl directly
curl -X POST "http://localhost:8091/tasks/send" \
  -H "Authorization: Bearer your_token" \
  -H "Content-Type: application/json" \
  -d '{"message": {"content": {"text": "What products?"}}}'
```

## Supported Queries

The A2A server responds intelligently to natural language queries about:
- Available advertising products and inventory
- Pricing and CPM rates
- Targeting options
- Campaign creation requests

## Integration with MCP

The A2A server acts as a bridge to the MCP (Model Context Protocol) backend:
1. Receives natural language queries via A2A protocol
2. Authenticates the advertiser
3. Calls appropriate MCP tools with proper context
4. Returns tenant-specific products and information

## Getting Tokens

1. Access Admin UI: http://localhost:8001
2. Navigate to "Advertisers"
3. Create new advertiser or copy existing token

## Example Usage

```bash
# Query products
A2A_TOKEN=demo_token_123 ./scripts/a2a_query.py "What products do you have?"

# Create campaign
A2A_TOKEN=demo_token_123 ./scripts/a2a_query.py \
  "Create a video ad campaign with $5000 budget for next month"
```

## Production Endpoint

```bash
A2A_ENDPOINT=https://adcp-sales-agent.fly.dev/a2a \
A2A_TOKEN=production_token \
./scripts/a2a_query.py "What products are available?"
```