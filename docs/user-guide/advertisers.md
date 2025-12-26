# Advertiser Management

Advertisers (also called "principals") are the entities that can access your MCP API to create media buys. Each advertiser gets their own API token.

## Creating Advertisers

### Via Admin UI

1. Navigate to **Advertisers** in the Admin UI
2. Click **Add Advertiser**
3. Enter advertiser details:
   - **Name**: Display name
   - **Contact Email**: For notifications
   - **GAM Advertiser ID** (if using GAM): Links to existing GAM advertiser

### API Token

Each advertiser gets a unique API token for MCP access:

1. Go to **Advertisers** > select advertiser
2. Click **View Token**
3. Copy the token for use in MCP client configuration

Tokens can be regenerated if compromised.

## Platform Mappings

For ad server integration, advertisers need platform mappings:

### Google Ad Manager

```json
{
  "platform_mappings": {
    "google_ad_manager": {
      "advertiser_id": "123456",
      "enabled": true
    }
  }
}
```

The `advertiser_id` links to the GAM advertiser for order creation.

## Access Control

Advertisers can only:
- View products available to them
- Create media buys under their account
- Manage their own creatives
- View their own campaigns

They cannot access other advertisers' data or system configuration.

## MCP Client Configuration

Advertisers connect via MCP using their token:

```python
from fastmcp.client import Client, StreamableHttpTransport

transport = StreamableHttpTransport(
    url="https://your-domain.com/mcp/",
    headers={"x-adcp-auth": "advertiser-api-token"}
)

async with Client(transport=transport) as client:
    # Advertiser can now call MCP tools
    products = await client.call_tool("get_products", {})
```

## Notifications

Configure email notifications for advertisers:
- Media buy status changes
- Creative approval/rejection
- Campaign delivery alerts
