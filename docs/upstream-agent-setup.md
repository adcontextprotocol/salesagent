# Setting Up an Upstream Product Catalog Agent

This guide shows how to implement and deploy an upstream MCP server that handles product catalog requests for your AdCP Sales Agent.

## Overview

Instead of using a static database or the built-in AI provider, you can delegate product selection to your own intelligent agent. This enables:

- Custom business logic for product selection
- Integration with your inventory management system
- Real-time availability checking
- Proprietary matching algorithms
- Multi-step reasoning about which products to offer

## Step 1: Create Your Upstream MCP Server

Here's a complete example of an upstream product catalog server:

```python
# upstream_product_catalog_server.py
from fastmcp import FastMCP

mcp = FastMCP(
    name="YahooProductCatalog",
    description="Yahoo's intelligent product matching system"
)

@mcp.tool
async def get_products(
    brief: str,
    tenant_id: str = None,
    principal_id: str = None,
    context: dict = None
) -> dict:
    """
    Intelligently match products to advertising briefs.
    """
    # Your custom logic here:
    # 1. Parse the brief
    # 2. Check inventory availability
    # 3. Apply business rules
    # 4. Score and rank products
    # 5. Return best matches
    
    products = await your_matching_logic(brief)
    
    return {"products": products}

if __name__ == "__main__":
    mcp.run(transport='http', host='0.0.0.0', port=9000)
```

## Step 2: Run Your Upstream Server

### Option A: Direct Python
```bash
python upstream_product_catalog_server.py
```

### Option B: Docker
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "upstream_product_catalog_server.py"]
```

### Option C: As a Service
```yaml
# docker-compose.yml
services:
  product-catalog:
    build: ./product-catalog
    ports:
      - "9000:9000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - DATABASE_URL=${CATALOG_DB_URL}
```

## Step 3: Configure Your Tenant

Update your tenant configuration in the AdCP database to use the MCP provider:

```sql
-- Update tenant config to use upstream MCP server
UPDATE tenants 
SET config = jsonb_set(
    config,
    '{product_catalog}',
    '{
        "provider": "mcp",
        "config": {
            "upstream_url": "http://product-catalog.internal:9000/mcp/",
            "upstream_token": "your-secret-token",
            "tool_name": "get_products",
            "timeout": 30
        }
    }'::jsonb
)
WHERE tenant_id = 'your_tenant_id';
```

Or via the Admin UI:
1. Navigate to Tenant Settings
2. Edit Configuration
3. Add the product_catalog section

## Step 4: Test the Integration

Use the test script to verify your upstream server is working:

```python
# test_upstream_integration.py
import asyncio
from product_catalog_providers.factory import get_product_catalog_provider

async def test():
    tenant_config = {
        "product_catalog": {
            "provider": "mcp",
            "config": {
                "upstream_url": "http://localhost:9000/mcp/",
                "tool_name": "get_products"
            }
        }
    }
    
    provider = await get_product_catalog_provider("test", tenant_config)
    products = await provider.get_products(
        brief="I need sports advertising during March Madness",
        tenant_id="test"
    )
    
    print(f"Got {len(products)} products from upstream")
    for p in products:
        print(f"- {p.name}: {p.description}")

asyncio.run(test())
```

## Real-World Example: Yahoo Sports

Here's how Yahoo might implement their product catalog agent:

```python
@mcp.tool
async def get_products(brief: str, **kwargs) -> dict:
    # 1. Extract intent from brief
    intent = await analyze_brief_with_ai(brief)
    
    # 2. Check special events
    if "march madness" in brief.lower():
        # Check NCAA tournament schedule
        games = await get_march_madness_schedule()
        if games:
            products.append({
                "product_id": "yahoo_sports_march_madness_premium",
                "name": "March Madness Premium - Live Game Display",
                "description": f"Premium display during {len(games)} live games",
                "formats": [{"format_id": "display_300x250", ...}],
                "delivery_type": "guaranteed",
                "is_fixed_price": False,
                "price_guidance": {
                    "floor": 25.0,
                    "p50": 40.0,
                    "p75": 55.0
                },
                "implementation_config": {
                    "ad_server": "google_ad_manager",
                    "placement_ids": ["sports_march_madness_atf"],
                    "targeting": {
                        "content_cat_any_of": ["sports", "basketball"],
                        "custom_targeting": {"event": "march_madness"}
                    }
                }
            })
    
    # 3. Check inventory availability
    for product in potential_products:
        avails = await check_real_time_inventory(
            product_id=product['product_id'],
            dates=intent.get('flight_dates')
        )
        if avails['available_impressions'] > intent.get('min_impressions', 0):
            products.append(product)
    
    # 4. Apply Yahoo-specific business rules
    if intent.get('advertiser_category') == 'competitor':
        products = filter_competitive_conflicts(products)
    
    # 5. Rank by relevance and margin
    products = rank_by_business_value(products, intent)
    
    return {"products": products[:5]}  # Top 5 matches
```

## Advanced Features

### 1. Multi-Step Reasoning
Your upstream agent can perform complex reasoning:

```python
@mcp.tool
async def get_products(brief: str, **kwargs) -> dict:
    # Step 1: Understand the brief
    understanding = await llm.analyze(f"Extract requirements from: {brief}")
    
    # Step 2: Generate product ideas
    ideas = await llm.generate(f"Given {understanding}, suggest ad products")
    
    # Step 3: Check feasibility
    feasible_products = []
    for idea in ideas:
        if await is_feasible(idea):
            product = await create_product_spec(idea)
            feasible_products.append(product)
    
    # Step 4: Optimize selection
    final_selection = await optimize_for_advertiser_goals(
        feasible_products, 
        understanding['goals']
    )
    
    return {"products": final_selection}
```

### 2. Real-Time Inventory Integration
```python
async def check_inventory(product_id: str, dates: dict) -> dict:
    # Query your ad server
    avails = await ad_server.get_availability(
        product_id=product_id,
        start_date=dates['start'],
        end_date=dates['end']
    )
    
    return {
        'available': avails.impressions > 0,
        'impressions': avails.impressions,
        'fill_rate': avails.fill_rate,
        'competing_campaigns': avails.competitors
    }
```

### 3. Authentication
Secure your upstream server:

```python
from fastmcp.exceptions import ToolError

@mcp.tool
async def get_products(brief: str, context: Context) -> dict:
    # Verify the caller
    auth_header = context.request.headers.get('Authorization')
    if not verify_token(auth_header):
        raise ToolError("Unauthorized")
    
    # Process request...
```

### 4. Caching
Improve performance with intelligent caching:

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
async def get_cached_products(brief_hash: str) -> list:
    # Expensive product matching logic
    pass

@mcp.tool
async def get_products(brief: str, **kwargs) -> dict:
    # Create cache key from brief
    brief_hash = hashlib.md5(brief.encode()).hexdigest()
    
    # Try cache first
    products = await get_cached_products(brief_hash)
    
    return {"products": products}
```

## Deployment Patterns

### 1. Sidecar Pattern
Run the catalog agent alongside your ad server:
```yaml
services:
  ad-server:
    image: your-ad-server
  
  catalog-agent:
    image: catalog-agent
    environment:
      - AD_SERVER_URL=http://ad-server:8080
```

### 2. Microservice Pattern
Deploy as independent service:
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ AdCP Sales  │────▶│   Catalog    │────▶│  Ad Server  │
│   Agent     │     │   Service    │     │   APIs      │
└─────────────┘     └──────────────┘     └─────────────┘
```

### 3. Serverless Pattern
Use AWS Lambda or Google Cloud Functions:
```python
# lambda_handler.py
def lambda_handler(event, context):
    brief = event['brief']
    products = match_products(brief)
    return {"products": products}
```

## Monitoring and Debugging

### 1. Add Logging
```python
import logging

logger = logging.getLogger(__name__)

@mcp.tool
async def get_products(brief: str, **kwargs) -> dict:
    logger.info(f"Received brief: {brief[:100]}...")
    start_time = time.time()
    
    products = await match_products(brief)
    
    logger.info(f"Matched {len(products)} products in {time.time()-start_time:.2f}s")
    return {"products": products}
```

### 2. Health Checks
```python
@mcp.tool
async def health() -> dict:
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime": get_uptime(),
        "last_request": last_request_time
    }
```

### 3. Metrics
Track performance:
```python
from prometheus_client import Counter, Histogram

request_count = Counter('catalog_requests_total', 'Total requests')
request_duration = Histogram('catalog_request_duration_seconds', 'Request duration')

@mcp.tool
@request_duration.time()
async def get_products(brief: str, **kwargs) -> dict:
    request_count.inc()
    # ... rest of implementation
```

## Common Issues and Solutions

### Issue: Timeout Errors
**Solution**: Increase timeout in tenant config or optimize your matching logic
```json
{
  "product_catalog": {
    "provider": "mcp",
    "config": {
      "timeout": 60  // Increase from default 30s
    }
  }
}
```

### Issue: Network Connectivity
**Solution**: Use Docker networks or service discovery
```yaml
networks:
  adcp-network:
    driver: bridge
```

### Issue: Authentication Failures
**Solution**: Verify token configuration matches between systems

## Testing Your Integration

1. **Unit Test Your Matcher**:
```python
async def test_sports_matching():
    products = await matcher.match_products(
        "I need sports advertising"
    )
    assert any('sports' in p.name.lower() for p in products)
```

2. **Integration Test**:
```bash
# Start your upstream server
python upstream_product_catalog_server.py &

# Run integration test
python test_upstream_integration.py
```

3. **End-to-End Test**:
```bash
# Use the AdCP simulation with your upstream server
python simulation_full.py --use-mcp-catalog
```

## Summary

By implementing an upstream product catalog agent, you gain complete control over how products are matched to advertising briefs. This enables sophisticated business logic, real-time inventory integration, and custom AI reasoning - all while maintaining compatibility with the AdCP protocol.