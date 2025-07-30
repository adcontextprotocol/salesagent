# Product Catalog Providers

The AdCP Sales Agent now supports pluggable product catalog providers, allowing publishers to customize how products are matched to advertising briefs.

## Overview

When an AI agent calls `list_products` with a brief describing their advertising needs, the system uses a configured provider to return relevant products. This enables:

- **Static catalogs** (database)
- **AI-powered matching** (using Gemini or other LLMs)
- **Upstream MCP servers** (agent-to-agent communication)
- **Custom implementations** (your own logic)

## Configuration

Product catalog providers are configured per tenant in the database. Add a `product_catalog` section to your tenant configuration:

```json
{
  "product_catalog": {
    "provider": "ai",  // Provider type: "database", "ai", or "mcp"
    "config": {
      // Provider-specific configuration
    }
  }
}
```

## Available Providers

### 1. Database Provider (Default)

The simplest provider that returns all products from the database. This maintains backward compatibility.

```json
{
  "product_catalog": {
    "provider": "database",
    "config": {}
  }
}
```

**Note:** Currently ignores the brief and returns all products. Future versions may add brief-based filtering.

### 2. AI Provider (Gemini-powered)

Uses Google's Gemini AI to intelligently match products to briefs. This simulates a RAG-like system.

```json
{
  "product_catalog": {
    "provider": "ai",
    "config": {
      "model": "gemini-1.5-flash",  // Gemini model to use
      "max_products": 5,            // Maximum products to return
      "temperature": 0.3,           // Creativity level (0.0-1.0)
      "include_reasoning": false    // Include AI's reasoning (future)
    }
  }
}
```

**Requirements:**
- Set `GEMINI_API_KEY` environment variable
- Products must exist in the database (AI ranks/filters them)

### 3. MCP Provider (Upstream Server)

Delegates product selection to another MCP server, enabling agent-to-agent communication.

```json
{
  "product_catalog": {
    "provider": "mcp",
    "config": {
      "upstream_url": "http://product-catalog.internal:8080/mcp/",
      "upstream_token": "secret-token",  // Optional auth
      "tool_name": "get_products",       // Tool to call
      "timeout": 30                      // Seconds
    }
  }
}
```

The upstream MCP server should expose a tool that accepts:
```json
{
  "brief": "Campaign brief text",
  "tenant_id": "tenant_123",
  "principal_id": "advertiser_456",  // Optional
  "context": {}                      // Optional additional context
}
```

And returns:
```json
{
  "products": [
    {
      "product_id": "prod_1",
      "name": "Premium Display",
      // ... full Product schema
    }
  ]
}
```

## Example Use Cases

### Yahoo Example

As mentioned, if Yahoo has an agent running, they can configure the MCP provider to call their internal product catalog service:

```json
{
  "product_catalog": {
    "provider": "mcp",
    "config": {
      "upstream_url": "http://yahoo-products.internal/mcp/",
      "tool_name": "match_products_to_brief"
    }
  }
}
```

When an advertiser's agent provides a brief like:
> "I need to reach sports fans aged 25-44 with display ads during March Madness"

Yahoo's internal agent can:
1. Parse the brief
2. Check inventory availability
3. Apply business rules
4. Return only relevant products

### AI-Enhanced Small Publisher

A smaller publisher might use the AI provider to add intelligence without building a separate service:

```json
{
  "product_catalog": {
    "provider": "ai",
    "config": {
      "model": "gemini-1.5-pro",
      "max_products": 3,
      "temperature": 0.2
    }
  }
}
```

The AI will analyze the brief and return the most relevant products from their catalog.

## Creating Custom Providers

To implement your own provider:

1. Create a class inheriting from `ProductCatalogProvider`:

```python
from product_catalog_providers.base import ProductCatalogProvider
from schemas import Product
from typing import List, Dict, Any, Optional

class MyCustomProvider(ProductCatalogProvider):
    async def get_products(
        self,
        brief: str,
        tenant_id: str,
        principal_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Product]:
        # Your custom logic here
        # Could call external APIs, run ML models, etc.
        products = await self._fetch_from_my_system(brief)
        return products
```

2. Register your provider:

```python
from product_catalog_providers import register_provider

register_provider('custom', MyCustomProvider)
```

3. Configure tenants to use it:

```json
{
  "product_catalog": {
    "provider": "custom",
    "config": {
      "api_key": "your-api-key",
      "endpoint": "https://api.example.com"
    }
  }
}
```

## Migration Guide

Existing deployments will continue to work with the default database provider. To enable intelligent product matching:

1. Update your tenant configuration in the database
2. Add the `product_catalog` section with your chosen provider
3. Restart the server (providers are cached per tenant)

## Best Practices

1. **Start simple**: Use the database provider initially, then upgrade to AI or MCP as needed
2. **Test thoroughly**: Use the simulation scripts to test product matching
3. **Monitor performance**: The MCP provider adds network latency
4. **Cache wisely**: Consider caching responses for identical briefs
5. **Fail gracefully**: Have a fallback strategy if the provider fails

## Future Enhancements

- **Hybrid providers**: Combine multiple providers (e.g., AI + database fallback)
- **Brief analysis**: Extract structured requirements from natural language briefs
- **Performance tracking**: Learn which products perform well for certain brief types
- **Caching layer**: Reduce API calls for common brief patterns