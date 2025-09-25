# API Reference

## Overview

The AdCP Sales Agent provides two main APIs:
1. **MCP API** - Model Context Protocol interface for AI agents to buy advertising
2. **Super Admin API** - REST API for managing tenants and system configuration

## MCP API (Model Context Protocol)

The MCP API is the primary interface for AI agents to interact with the advertising system. It uses the MCP protocol over HTTP transport with header-based authentication.

### Authentication

All MCP requests require authentication via the `x-adcp-auth` header:

```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

headers = {"x-adcp-auth": "your_token"}
transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
client = Client(transport=transport)
```

### Discovery Tools

#### `get_products`

Discover available advertising products based on natural language brief.

**Parameters:**
- `brief` (string, optional): Natural language description of campaign goals
- `category` (string, optional): Product category filter

**Example:**
```python
async with client:
    products = await client.tools.get_products(
        brief="video ads for sports content targeting millennials"
    )
```

**Response:**
```json
{
  "products": [
    {
      "product_id": "connected_tv_sports",
      "name": "Connected TV - Sports",
      "description": "Premium CTV inventory on sports channels",
      "formats": ["video_1920x1080", "video_1280x720"],
      "min_spend": 10000,
      "pricing_type": "CPM",
      "price_cpm": 45.00,
      "targeting_available": ["geo", "demo", "interests"]
    }
  ]
}
```

#### `get_signals` (Optional)

Discover available targeting signals (audiences, contextual, geographic).

**Parameters:**
- `query` (string, optional): Search query for signals
- `type` (string, optional): Signal type filter ("audience", "contextual", "geo")

**Response:**
```json
{
  "signals": [
    {
      "signal_id": "sports_enthusiasts_2025",
      "name": "Sports Enthusiasts",
      "type": "audience",
      "description": "Users interested in sports content",
      "reach": 2500000
    }
  ]
}
```

### Planning Tools

#### `get_avails`

Check availability and forecast for products.

**Parameters:**
- `product_ids` (array, required): Products to check
- `flight_start_date` (string, required): Start date (YYYY-MM-DD)
- `flight_end_date` (string, required): End date (YYYY-MM-DD)
- `total_budget` (number, optional): Budget to allocate
- `targeting_overlay` (object, optional): Additional targeting

**Response:**
```json
{
  "packages": [
    {
      "package_id": "pkg_001",
      "product_id": "connected_tv_sports",
      "impressions": 500000,
      "cpm": 45.00,
      "total_cost": 22500
    }
  ],
  "total_budget": 22500,
  "total_impressions": 500000
}
```

### Buying Tools

#### `create_media_buy`

Create a new media buy with selected products.

**Parameters:**
- `product_ids` (array, required): Products to purchase
- `total_budget` (number, required): Total campaign budget
- `flight_start_date` (string, required): Start date
- `flight_end_date` (string, required): End date
- `targeting_overlay` (object, optional): Additional targeting including signals
- `creative_requirements` (object, optional): Required creative formats

**Example:**
```python
result = await client.tools.create_media_buy(
    product_ids=["connected_tv_sports"],
    total_budget=50000,
    flight_start_date="2025-02-01",
    flight_end_date="2025-02-28",
    targeting_overlay={
        "geo_country_any_of": ["US"],
        "signals": ["sports_enthusiasts_2025", "auto_intenders_q1_2025"]
    }
)
```

### Creative Management

#### `upload_creative`

Upload a creative asset for approval.

**Parameters:**
- `media_buy_id` (string, required): Associated media buy
- `creative_url` (string, required): URL to creative asset
- `format` (string, required): Creative format identifier
- `metadata` (object, optional): Additional creative metadata

#### `get_creative_status`

Check approval status of uploaded creatives.

**Parameters:**
- `media_buy_id` (string, required): Media buy to check
- `creative_id` (string, optional): Specific creative to check

### Monitoring & Reporting

#### `check_media_buy_status`

Get current status and performance of a media buy.

**Parameters:**
- `media_buy_id` (string, required): Media buy identifier

**Response:**
```json
{
  "media_buy_id": "mb_123",
  "status": "active",
  "flight_progress": 0.45,
  "budget_spent": 22500,
  "impressions_delivered": 450000,
  "performance": {
    "ctr": 0.025,
    "viewability": 0.78,
    "completion_rate": 0.85
  }
}
```

#### `get_media_buy_report`

Get detailed performance report.

**Parameters:**
- `media_buy_id` (string, required): Media buy identifier
- `start_date` (string, optional): Report start date
- `end_date` (string, optional): Report end date
- `dimensions` (array, optional): Report dimensions
- `metrics` (array, optional): Metrics to include

### Media Buy Management

#### `pause_media_buy`

Pause an active media buy.

**Parameters:**
- `media_buy_id` (string, required): Media buy to pause
- `reason` (string, optional): Reason for pausing

#### `resume_media_buy`

Resume a paused media buy.

**Parameters:**
- `media_buy_id` (string, required): Media buy to resume

#### `update_media_buy`

Complete lifecycle management for advertising campaigns with safety guardrails and admin controls.

**Parameters:**
- `media_buy_id` (string, required): Media buy to update
- `action` (string, required): Lifecycle action to perform
- `package_id` (string, optional): Specific package for package actions
- `budget` (number, optional): New budget for budget actions

**Available Actions:**

##### Standard Actions (All Users)
- **`pause_media_buy`** - Pause entire campaign/order
- **`resume_media_buy`** - Resume entire campaign/order
- **`pause_package`** - Pause specific line item/package
- **`resume_package`** - Resume specific line item/package
- **`update_package_budget`** - Update budget for specific package
- **`update_package_impressions`** - Update impression goal for specific package

##### Lifecycle Actions
- **`activate_order`** - Activate non-guaranteed orders for delivery
- **`submit_for_approval`** - Submit guaranteed orders for manual approval
- **`approve_order`** - Approve orders (admin users only)
- **`archive_order`** - Archive completed campaigns

**Order Activation Rules:**

*Non-Guaranteed Orders (Automatic Activation)*
Line Item Types: `NETWORK`, `BULK`, `PRICE_PRIORITY`, `HOUSE`

```json
{
  "method": "update_media_buy",
  "params": {
    "media_buy_id": "12345",
    "action": "activate_order"
  }
}
```

✅ **Success Response:**
- Order and line items activated immediately
- Status: `accepted`
- Audit log entry created

*Guaranteed Orders (Manual Approval Required)*
Line Item Types: `STANDARD`, `SPONSORSHIP`

❌ **Blocked Response:**
```json
{
  "status": "failed",
  "reason": "Cannot auto-activate order with guaranteed line items (['STANDARD']). Use submit_for_approval instead."
}
```

**Approval Workflow:**

*1. Submit for Approval*
```json
{
  "method": "update_media_buy",
  "params": {
    "media_buy_id": "12345",
    "action": "submit_for_approval"
  }
}
```

*2. Admin Approval*
```json
{
  "method": "update_media_buy",
  "params": {
    "media_buy_id": "12345",
    "action": "approve_order"
  }
}
```

**Admin Requirements:**
- Principal must have `gam_admin: true` in `platform_mappings`
- OR `is_admin: true` in `platform_mappings`
- OR `role: "admin"` attribute

**Archive Requirements:**
- Order status must be: `DELIVERED`, `COMPLETED`, `CANCELLED`, or `PAUSED`

**Error Handling:**
- NO QUIET FAILURES - All requests fail loudly with clear error messages
- Common errors include permission denied, invalid status, guaranteed item blocking

## Tenant Management API

The Tenant Management API provides REST endpoints for system administration and tenant management.

### Authentication

All Tenant Management API requests require the API key in the header:

```bash
curl -H "X-Tenant-Management-API-Key: sk-your-api-key"
```

### Initial Setup

#### Initialize API Key

**One-time setup** to generate the tenant management API key:

```bash
POST /api/v1/tenant-management/init-api-key
```

Returns the API key - save it securely as it cannot be retrieved again!

### Tenant Management

#### List Tenants

```bash
GET /api/v1/tenant-management/tenants
```

**Response:**
```json
{
  "tenants": [
    {
      "tenant_id": "tenant_123",
      "name": "Sports Publisher",
      "subdomain": "sports",
      "ad_server": "google_ad_manager",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

#### Create Tenant

```bash
POST /api/v1/tenant-management/tenants
```

**Body:**
```json
{
  "name": "Sports Publisher",
  "subdomain": "sports",
  "ad_server": "google_ad_manager",
  "gam_refresh_token": "1//oauth-refresh-token",
  "gam_network_code": "123456789",
  "features": {
    "max_daily_budget": 50000,
    "enable_axe_signals": true
  }
}
```

**Supported Ad Servers:**
- `google_ad_manager` - Google Ad Manager
- `kevel` - Kevel Ad Server
- `triton_digital` - Triton Digital
- `mock` - Mock server for testing

#### Get Tenant

```bash
GET /api/v1/tenant-management/tenants/{tenant_id}
```

#### Update Tenant

```bash
PUT /api/v1/tenant-management/tenants/{tenant_id}
```

**Body:**
```json
{
  "name": "Updated Name",
  "features": {
    "max_daily_budget": 100000
  }
}
```

#### Delete Tenant

```bash
DELETE /api/v1/tenant-management/tenants/{tenant_id}
```

### Principal (Advertiser) Management

#### List Principals

```bash
GET /api/v1/tenant-management/tenants/{tenant_id}/principals
```

#### Create Principal

```bash
POST /api/v1/tenant-management/tenants/{tenant_id}/principals
```

**Body:**
```json
{
  "name": "Acme Advertiser",
  "gam_advertiser_id": "456789",
  "access_token": "auto_generated_or_custom"
}
```

### GAM Integration

#### Sync GAM Inventory

Trigger inventory synchronization from Google Ad Manager:

```bash
POST /api/v1/tenant-management/tenants/{tenant_id}/sync-inventory
```

#### Sync GAM Orders

Synchronize orders and line items from GAM:

```bash
POST /api/v1/tenant-management/tenants/{tenant_id}/sync-orders
```

### System Management

#### Health Check

```bash
GET /api/v1/tenant-management/health
```

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "2.3.0",
  "tenants_count": 5,
  "active_media_buys": 23
}
```

#### Audit Logs

```bash
GET /api/v1/tenant-management/audit-logs?tenant_id={tenant_id}&limit=100
```

## Error Handling

Both APIs return standard HTTP status codes:

- `200` - Success
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (missing or invalid auth)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (duplicate resource)
- `500` - Internal Server Error

Error responses include details:

```json
{
  "error": {
    "code": "INVALID_TARGETING",
    "message": "Geographic targeting is required for this product",
    "details": {
      "field": "targeting_overlay.geo_country_any_of",
      "required": true
    }
  }
}
```

## Rate Limiting

- MCP API: 1000 requests per minute per token
- Super Admin API: 100 requests per minute per API key

## Webhooks & Notifications

The system provides comprehensive real-time notifications for all major workflow events, offering immediate visibility into campaign creation processes, approval requirements, and execution status.

### Slack Notifications

#### Event Types

The system sends detailed Slack notifications for the following media buy events:

- **`approval_required`** 🔔 - Manual approval needed for media buy operations
- **`config_approval_required`** ⚙️ - Configuration-based approval required (tenant/product settings)
- **`created`** 🎉 - Media buy created and activated successfully
- **`failed`** ❌ - Media buy creation failed due to validation or execution errors
- **`activated`** 🚀 - Campaign went live

#### Notification Details

Each notification includes comprehensive context:

- Principal/advertiser name and campaign details
- Total budget, PO number, and flight dates
- Product IDs and package information
- Workflow step ID for tracking
- Context ID for session management
- Direct action buttons to Admin UI
- Error details and troubleshooting information (for failures)

#### Configuration

Configure Slack notifications per tenant via the Admin UI:

```json
{
  "features": {
    "slack_webhook_url": "https://hooks.slack.com/services/...",
    "slack_audit_webhook_url": "https://hooks.slack.com/services/..."
  }
}
```

#### Notification Flow Integration

1. **Validation Phase**: No notifications (errors handled inline)
2. **Manual Approval Check**: → `approval_required` notification
3. **Config Approval Check**: → `config_approval_required` notification
4. **Execution Phase**: → Success/failure notifications based on outcome
5. **Completion**: Workflow status updated, success notification sent

### Standard Webhooks

The system also supports standard webhook delivery for:

- `media_buy.created` - New media buy created
- `media_buy.approved` - Media buy approved and active
- `creative.approved` - Creative approved
- `creative.rejected` - Creative rejected
- `campaign.completed` - Campaign finished delivery

Configure webhook URLs per tenant in the Admin UI.

## SDKs and Examples

### Python SDK

```python
# Install
pip install adcp-client

# Usage
from adcp import Client

client = Client(
    url="http://localhost:8080",
    token="your_token"
)

# Create media buy
buy = await client.create_media_buy(
    products=["ctv_sports"],
    budget=50000,
    dates=("2025-02-01", "2025-02-28")
)
```

### Example Implementations

- `examples/scope3_integration.py` - Scope3 app integration
- `examples/upstream_quickstart.py` - Basic MCP client
- `tools/simulations/simulation_full.py` - Complete campaign lifecycle
- `tools/demos/demo_ai_products.py` - AI product discovery

## Testing the APIs

### MCP API Testing

```bash
# Use MCP Inspector
npm install -g @modelcontextprotocol/inspector
npx inspector http://localhost:8080/mcp/

# Run simulation
uv run python tools/simulations/run_simulation.py
```

### Tenant Management API Testing

```bash
# Run test script
python scripts/test_tenant_management_api.py

# Unit tests
uv run pytest tests/integration/test_tenant_management_api_integration.py -v
```

## Security Best Practices

1. **Never expose API keys in code** - Use environment variables
2. **Use HTTPS in production** - Encrypt all API traffic
3. **Rotate tokens regularly** - Implement token rotation policy
4. **Audit all operations** - Review audit logs regularly
5. **Implement rate limiting** - Protect against abuse
6. **Validate all inputs** - Prevent injection attacks
7. **Use least privilege** - Grant minimum required permissions
