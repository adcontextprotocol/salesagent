# AdCP Sales Agent API Reference

This document provides a complete reference for all MCP tools available in the AdCP Sales Agent server.

## Table of Contents

1. [Discovery Tools](#discovery-tools)
2. [Planning Tools](#planning-tools)
3. [Buying Tools](#buying-tools)
4. [Creative Management](#creative-management)
5. [Monitoring & Reporting](#monitoring--reporting)
6. [Media Buy Management](#media-buy-management)

## Discovery Tools

### `discover_products`

Discover available advertising products based on natural language campaign brief.

**Parameters:**
- `campaign_brief` (string, required): Natural language description of campaign goals

**Example:**
```json
{
  "campaign_brief": "I want to reach pet owners in California with video ads during prime time"
}
```

**Response:**
```json
{
  "recommended_products": [
    {
      "product_id": "connected_tv_prime",
      "name": "Connected TV - Prime Time",
      "description": "Premium CTV inventory 8PM-11PM",
      "min_spend": 10000,
      "targeting_available": ["geography", "interests", "device_types"]
    }
  ]
}
```

### `describe_product`

Get detailed information about a specific product.

**Parameters:**
- `product_id` (string, required): The product identifier

**Response includes:**
- Full product details
- Pricing information
- Available targeting options
- Creative specifications

## Planning Tools

### `get_avails`

Check availability and pricing for specific products.

**Parameters:**
- `product_ids` (array, required): List of product IDs to check
- `start_date` (string, required): Campaign start date (YYYY-MM-DD)
- `end_date` (string, required): Campaign end date (YYYY-MM-DD)
- `budget` (number, optional): Budget to allocate
- `targeting_overlay` (object, optional): Additional targeting criteria

**Response:**
```json
{
  "packages": [
    {
      "package_id": "pkg_001",
      "product_id": "connected_tv_prime",
      "name": "CTV Prime - CA",
      "impressions": 500000,
      "cpm": 45.00,
      "total_cost": 22500
    }
  ],
  "total_budget": 22500,
  "total_impressions": 500000
}
```

## Buying Tools

### `create_media_buy`

Create a new media buy from selected packages.

**Parameters:**
- `packages` (array, required): List of package IDs to purchase
- `po_number` (string, optional): Purchase order number
- `total_budget` (number, required): Total budget for the buy
- `targeting_overlay` (object, optional): Additional targeting to apply

**Response:**
```json
{
  "media_buy_id": "gam_123456",
  "status": "pending_activation",
  "creative_deadline": "2024-01-15T23:59:59Z"
}
```

## Creative Management

### `add_creative_assets`

Upload creative assets and assign to packages.

**Parameters:**
- `media_buy_id` (string, required): The media buy identifier
- `assets` (array, required): List of creative assets

**Asset Object:**
```json
{
  "creative_id": "banner_001",
  "name": "Spring Campaign Banner",
  "format": "image",
  "media_url": "https://cdn.example.com/banner.jpg",
  "click_url": "https://example.com/landing",
  "width": 300,
  "height": 250,
  "package_assignments": ["pkg_001", "pkg_002"]
}
```

**Supported Formats:**
- `image`: JPEG, PNG, GIF
- `video`: MP4, VAST
- `audio`: MP3, AAC (Triton only)
- `custom`: Template-based (Kevel only)

## Monitoring & Reporting

### `check_media_buy_status`

Get current status of a media buy.

**Parameters:**
- `media_buy_id` (string, required): The media buy identifier

**Response:**
```json
{
  "media_buy_id": "gam_123456",
  "status": "active",
  "last_updated": "2024-01-20T10:30:00Z"
}
```

**Status Values:**
- `pending_activation`: Awaiting creatives
- `pending_approval`: Under review
- `active`: Currently delivering
- `paused`: Temporarily stopped
- `completed`: Finished
- `failed`: Error state

### `get_media_buy_delivery`

Get delivery metrics for a date range.

**Parameters:**
- `media_buy_id` (string, required): The media buy identifier
- `start_date` (string, required): Report start date
- `end_date` (string, required): Report end date

**Response:**
```json
{
  "totals": {
    "impressions": 250000,
    "spend": 11250.00,
    "clicks": 500,
    "video_completions": 175000
  },
  "by_package": [
    {
      "package_id": "pkg_001",
      "impressions": 125000,
      "spend": 5625.00
    }
  ]
}
```

### `update_media_buy_performance_index`

Update performance indices for AI optimization.

**Parameters:**
- `media_buy_id` (string, required): The media buy identifier
- `package_performance` (array, required): Performance updates

**Performance Object:**
```json
{
  "package_id": "pkg_001",
  "performance_index": 1.2
}
```

**Index Values:**
- `1.0`: Baseline performance
- `> 1.0`: Above average (e.g., 1.2 = 20% better)
- `< 1.0`: Below average (e.g., 0.8 = 20% worse)

## Media Buy Management

The following tools provide comprehensive control over active media buys using a unified interface.

### `update_media_buy`

Update a media buy with campaign-level and/or package-level changes. This tool mirrors the structure of `create_media_buy` for consistency.

**Semantics:** Uses PATCH semantics - only fields provided are updated. Omitted fields remain unchanged. For packages, only those explicitly listed are affected.

**Parameters:**
- `media_buy_id` (string, required): The media buy identifier
- `active` (boolean, optional): True to activate, False to pause entire campaign
- `flight_start_date` (string, optional): Change start date if not started (YYYY-MM-DD)
- `flight_end_date` (string, optional): Extend or shorten campaign (YYYY-MM-DD)
- `total_budget` (number, optional): Update total budget
- `targeting_overlay` (object, optional): Update global targeting
- `pacing` (string, optional): "even", "asap", or "daily_budget"
- `daily_budget` (number, optional): Daily spend cap across all packages
- `packages` (array, optional): Package-specific updates (see PackageUpdate)
- `creatives` (array, optional): Add new creatives
- `creative_assignments` (object, optional): Update creative-to-package mapping
- `today` (string, optional): Date for testing/simulation (YYYY-MM-DD)

**Example - Pause entire campaign:**
```json
{
  "media_buy_id": "gam_123456",
  "active": false
}
```

**Example - Update budget and extend campaign:**
```json
{
  "media_buy_id": "gam_123456",
  "total_budget": 75000,
  "flight_end_date": "2024-02-15"
}
```

**Example - Update specific packages:**
```json
{
  "media_buy_id": "gam_123456",
  "packages": [
    {
      "package_id": "premium_sports",
      "active": false,
      "budget": 25000
    },
    {
      "package_id": "drive_time",
      "impressions": 1000000,
      "daily_impressions": 50000
    }
  ]
}
```

### `update_package`

Update one or more packages within a media buy. Provides a focused interface for package-level changes.

**Semantics:** Uses PATCH semantics - only packages listed are affected. Unlisted packages remain unchanged. To effectively "remove" a package from delivery, set `active: false`.

**Parameters:**
- `media_buy_id` (string, required): The media buy identifier
- `packages` (array, required): List of PackageUpdate objects
- `today` (string, optional): Date for testing/simulation (YYYY-MM-DD)

**PackageUpdate Object:**
```json
{
  "package_id": "string (required)",
  "active": "boolean (optional) - true to activate, false to pause",
  "budget": "number (optional) - new budget in dollars",
  "impressions": "number (optional) - direct impression goal",
  "cpm": "number (optional) - update CPM rate",
  "daily_budget": "number (optional) - daily spend cap",
  "daily_impressions": "number (optional) - daily impression cap",
  "pacing": "string (optional) - even, asap, or front_loaded",
  "creative_ids": "array (optional) - update creative assignments",
  "targeting_overlay": "object (optional) - package-specific targeting"
}
```

**Example - Update multiple packages:**
```json
{
  "media_buy_id": "kevel_789012",
  "packages": [
    {
      "package_id": "premium_sports",
      "active": true,
      "budget": 30000,
      "pacing": "front_loaded"
    },
    {
      "package_id": "entertainment",
      "active": false
    },
    {
      "package_id": "news",
      "impressions": 500000,
      "daily_impressions": 25000,
      "creative_ids": ["banner_v2", "video_v2"]
    }
  ]
}
```

**Important:** In the above example:
- `premium_sports`: Activated with new budget and pacing
- `entertainment`: Paused (removed from delivery)
- `news`: Updated with new impression goals and creatives
- Any other packages (e.g., `lifestyle`, `tech`) continue unchanged

### Response Format

All media buy management tools return the same response format:

**Success Response:**
```json
{
  "status": "accepted",
  "implementation_date": "2024-01-20T15:00:00Z",
  "detail": "Successfully executed pause_media_buy in Google Ad Manager"
}
```

**Error Response:**
```json
{
  "status": "failed",
  "reason": "Flight 'invalid_pkg' not found",
  "detail": "Additional error context if available"
}
```

### Notes on Updates

1. **PATCH Semantics**: Both `update_media_buy` and `update_package` use PATCH semantics:
   - Only fields/packages explicitly provided are modified
   - Omitted fields/packages remain unchanged
   - This is NOT a replace operation - you don't need to include all packages

2. **Package Management**:
   - To pause a package: Include it with `active: false`
   - To remove from delivery: Set `active: false` (same as pause)
   - To add new packages: Use a separate tool (not yet implemented) or create a new media buy
   - Unlisted packages continue running unchanged

3. **Budget vs Impressions**: When updating a package, you can specify either `budget` (which recalculates impressions based on CPM) or `impressions` (which sets the goal directly). If both are provided, `impressions` takes precedence.

4. **Atomic Updates**: Each update is processed independently. If one fails, it returns immediately with an error.

5. **Platform Support**: Not all platforms support all update fields. The adapter will log warnings for unsupported features in dry-run mode.

6. **Daily Caps**: Daily budget and impression caps help control pacing but may not be supported by all platforms.

7. **Targeting Updates**: Package-level targeting overlays are additive to campaign-level targeting

## Authentication

All API calls require authentication via the `x-adcp-auth` header:

```bash
curl -X POST http://localhost:8000/mcp/sse \
  -H "Content-Type: application/json" \
  -H "x-adcp-auth: your_auth_token" \
  -d '{"method": "tools/call", "params": {"name": "discover_products", "arguments": {...}}}'
```

## Error Handling

All tools return errors in a consistent format:

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Start date must be in the future"
  }
}
```

Common error codes:
- `AUTHENTICATION_FAILED`: Invalid or missing auth token
- `INVALID_PARAMETER`: Parameter validation failed
- `NOT_FOUND`: Resource not found
- `ADAPTER_ERROR`: Ad server API error
- `PERMISSION_DENIED`: Principal lacks required permissions

## Platform Differences

While the API provides a unified interface, some features vary by platform:

### Google Ad Manager
- Full targeting support
- Approval workflow for creatives
- Sophisticated reporting

### Kevel
- Real-time decisioning
- Custom creative templates
- Simplified targeting

### Triton Digital
- Audio-only creatives
- Station/genre targeting
- Daypart optimization

## Rate Limits

- Discovery endpoints: 100 requests/minute
- Buying endpoints: 20 requests/minute
- Reporting endpoints: 60 requests/minute
- Update endpoints: 30 requests/minute

## Best Practices

1. **Use Dry Run Mode**: Test complex operations with `ADCP_DRY_RUN=true`
2. **Batch Operations**: Combine multiple updates when possible
3. **Monitor Status**: Regular status checks ensure smooth delivery
4. **Handle Deadlines**: Submit creatives before the deadline
5. **Use Performance Indices**: Regular updates improve AI optimization

## Human-in-the-Loop Task Queue

### create_human_task

Creates a task requiring human intervention.

**Request:**
```json
{
  "task_type": "creative_approval",
  "priority": "high",
  "creative_id": "creative_123",
  "error_detail": "Format requires manual review",
  "context_data": {
    "format": "dooh_billboard"
  },
  "due_in_hours": 24
}
```

**Response:**
```json
{
  "task_id": "task_a1b2c3d4",
  "status": "pending",
  "due_by": "2025-07-29T18:00:00Z"
}
```

### get_pending_tasks

Retrieves pending human tasks with optional filtering.

**Request:**
```json
{
  "principal_id": null,
  "task_type": "creative_approval",
  "priority": "high",
  "include_overdue": true
}
```

**Response:**
```json
{
  "tasks": [
    {
      "task_id": "task_a1b2c3d4",
      "task_type": "creative_approval",
      "principal_id": "acme_corp",
      "status": "pending",
      "priority": "high",
      "creative_id": "creative_123",
      "error_detail": "Format requires manual review",
      "created_at": "2025-07-28T12:00:00Z",
      "due_by": "2025-07-29T18:00:00Z"
    }
  ],
  "total_count": 1,
  "overdue_count": 0
}
```

### assign_task

Assigns a task to a human operator (admin only).

**Request:**
```json
{
  "task_id": "task_a1b2c3d4",
  "assigned_to": "reviewer@company.com"
}
```

**Response:**
```json
{
  "status": "success",
  "detail": "Task task_a1b2c3d4 assigned to reviewer@company.com"
}
```

### complete_task

Completes a human task with resolution details (admin only).

**Request:**
```json
{
  "task_id": "task_a1b2c3d4",
  "resolution": "approved",
  "resolution_detail": "Creative meets brand safety guidelines",
  "resolved_by": "reviewer@company.com"
}
```

**Response:**
```json
{
  "status": "success",
  "detail": "Task task_a1b2c3d4 completed with resolution: approved"
}
```

### verify_task

Verifies if a task was completed correctly by checking actual state against expected outcome.

**Request:**
```json
{
  "task_id": "task_a1b2c3d4",
  "expected_outcome": {
    "daily_budget": 100.0,
    "package_premium_sports_budget": 500.0
  }
}
```

**Response:**
```json
{
  "task_id": "task_a1b2c3d4",
  "verified": false,
  "actual_state": {
    "daily_budget": null,
    "package_premium_sports_budget": 0
  },
  "expected_state": {
    "daily_budget": 100.0,
    "package_premium_sports_budget": 500.0
  },
  "discrepancies": [
    "Daily budget is $null, expected $100.0"
  ]
}
```

### mark_task_complete

Marks a task as complete with automatic verification (admin only).

**Request:**
```json
{
  "task_id": "task_a1b2c3d4",
  "override_verification": false,
  "completed_by": "admin@publisher.com"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "task_id": "task_a1b2c3d4",
  "verified": true,
  "verification_details": {
    "actual_state": {"daily_budget": 100.0},
    "expected_state": {"daily_budget": 100.0},
    "discrepancies": []
  },
  "message": "Task marked complete by admin@publisher.com"
}
```

**Response (Verification Failed):**
```json
{
  "status": "verification_failed",
  "verified": false,
  "discrepancies": [
    "Daily budget is $50, expected $100"
  ],
  "message": "Task verification failed. Use override_verification=true to force completion."
}
```