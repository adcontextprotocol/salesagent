"""
AdCP Sales Agent - ADK Implementation
Fully compliant with AdCP v2.4 specification
"""

import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool


class ConversationAnalyzer:
    """Analyzes conversation history to extract insights."""

    @staticmethod
    def analyze(messages: list[str]) -> dict[str, Any]:
        """Extract insights from conversation history."""
        analysis = {
            "budget_indicators": [],
            "format_preferences": [],
            "audience_signals": [],
            "campaign_objectives": [],
            "urgency_level": "normal",
            "geographic_targets": [],
        }

        # Combine all messages for analysis
        full_text = " ".join(messages).lower() if messages else ""

        # Budget detection
        budget_patterns = [
            r"\$[\d,]+[km]?\b",
            r"\b\d+k\s+budget\b",
            r"\b\d+m\s+budget\b",
        ]
        for pattern in budget_patterns:
            matches = re.findall(pattern, full_text)
            if matches:
                analysis["budget_indicators"].extend(matches)

        # Parse budget range from indicators
        analysis["budget_range"] = [0, 1000000]  # Default range
        if analysis["budget_indicators"]:
            # Try to parse the first budget indicator
            for indicator in analysis["budget_indicators"]:
                try:
                    # Remove $ and commas
                    amount_str = indicator.replace("$", "").replace(",", "").lower()
                    # Handle k and m suffixes
                    if "k" in amount_str:
                        amount = float(amount_str.replace("k", "")) * 1000
                    elif "m" in amount_str:
                        amount = float(amount_str.replace("m", "")) * 1000000
                    else:
                        amount = float(amount_str.split()[0])  # Handle "X budget"
                    # Set range around the amount (+/- 20%)
                    analysis["budget_range"] = [amount * 0.8, amount * 1.2]
                    break
                except:
                    continue

        # Format detection
        format_keywords = {
            "video": ["video", "pre-roll", "mid-roll", "youtube"],
            "display": ["display", "banner", "rectangle", "leaderboard"],
            "audio": ["audio", "podcast", "spotify", "radio"],
            "native": ["native", "sponsored content"],
            "ctv": ["ctv", "connected tv", "ott", "streaming tv"],
        }

        for format_type, keywords in format_keywords.items():
            if any(kw in full_text for kw in keywords):
                if format_type not in analysis["format_preferences"]:
                    analysis["format_preferences"].append(format_type)

        # Audience signals
        audience_keywords = {
            "sports_fans": ["sports", "nfl", "nba", "soccer", "football"],
            "tech_enthusiasts": ["tech", "technology", "gadget", "software"],
            "luxury_shoppers": ["luxury", "premium", "high-end", "exclusive"],
            "health_conscious": ["health", "fitness", "wellness", "organic"],
            "gamers": ["gaming", "video games", "esports", "console"],
            "travelers": ["travel", "vacation", "tourism", "hotels"],
        }

        for audience, keywords in audience_keywords.items():
            if any(kw in full_text for kw in keywords):
                if audience not in analysis["audience_signals"]:
                    analysis["audience_signals"].append(audience)

        # Campaign objectives
        if "awareness" in full_text or "reach" in full_text:
            analysis["campaign_objectives"].append("awareness")
        if "conversion" in full_text or "sales" in full_text or "roi" in full_text:
            analysis["campaign_objectives"].append("conversion")
        if "traffic" in full_text or "clicks" in full_text:
            analysis["campaign_objectives"].append("traffic")

        # Urgency detection
        if any(word in full_text for word in ["urgent", "asap", "immediately"]):
            analysis["urgency_level"] = "high"
        elif any(word in full_text for word in ["soon", "quickly", "fast"]):
            analysis["urgency_level"] = "medium"

        # Geographic targets
        if "united states" in full_text or "usa" in full_text or "u.s." in full_text:
            analysis["geographic_targets"].append("United States")
        if "uk" in full_text or "united kingdom" in full_text:
            analysis["geographic_targets"].append("United Kingdom")
        if "canada" in full_text:
            analysis["geographic_targets"].append("Canada")

        return analysis


class ProductRanker:
    """Ranks products based on conversation context."""

    @staticmethod
    def rank(products: list[dict[str, Any]], analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Score and rank products based on conversation analysis."""
        if not products:
            return []

        scored_products = []

        for product in products:
            score = 0
            match_reasons = []

            # Format matching (30 points max)
            if "formats" in product and analysis["format_preferences"]:
                product_formats = [f.get("type", "").lower() for f in product["formats"]]
                for pref_format in analysis["format_preferences"]:
                    if any(pref_format in fmt for fmt in product_formats):
                        score += 30
                        match_reasons.append(f"Supports {pref_format} format")
                        break

            # Audience matching (25 points max)
            if analysis["audience_signals"]:
                product_desc = json.dumps(product).lower()
                for audience in analysis["audience_signals"]:
                    if audience.replace("_", " ") in product_desc:
                        score += 25
                        match_reasons.append(f"Reaches {audience.replace('_', ' ')}")
                        break

            # Objective alignment (20 points max)
            if analysis["campaign_objectives"]:
                for objective in analysis["campaign_objectives"]:
                    score += 20
                    match_reasons.append(f"Aligns with {objective} goals")
                    break

            # Geographic coverage (15 points max)
            if analysis["geographic_targets"] and "countries" in product:
                product_countries = [c.lower() for c in product.get("countries", [])]
                for geo in analysis["geographic_targets"]:
                    if any(geo.lower() in country for country in product_countries):
                        score += 15
                        match_reasons.append("Available in target markets")
                        break

            # Urgency bonus (10 points max)
            if analysis["urgency_level"] == "high":
                score += 10
                match_reasons.append("Available immediately")

            # Add scoring metadata
            product["_relevance_score"] = score
            product["_recommendation_reason"] = " | ".join(match_reasons) if match_reasons else "General match"

            scored_products.append(product)

        # Sort by score (highest first)
        return sorted(scored_products, key=lambda x: x["_relevance_score"], reverse=True)


# Helper function to setup path and context for direct calls
def setup_direct_call():
    """Setup path and create mock context for direct tool calls."""
    # Add parent directory to path so we can import main.py modules
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    # Create a minimal context that provides what tools need
    class MockContext:
        def __init__(self):
            self.headers = {"x-adcp-auth": os.getenv("ADCP_AUTH_TOKEN", "test-token-1234")}

        def get_http_request(self):
            # Return a mock request with headers
            class MockRequest:
                def __init__(self, headers):
                    self.headers = headers

            return MockRequest(self.headers)

    return MockContext()


# Get products by calling the tool directly (no MCP protocol needed!)
async def get_products_direct(brief: str, promoted_offering: str) -> list[dict[str, Any]]:
    """Get products by calling the AdCP tool directly."""

    context = setup_direct_call()

    try:
        # Import the necessary modules from main.py
        from config_loader import set_current_tenant
        from main import get_products, init_db
        from schemas import GetProductsRequest

        # Initialize database if needed
        init_db()

        # Set up tenant context (use default tenant)
        set_current_tenant("default")

        # Create request with required fields
        request = GetProductsRequest(brief=brief, promoted_offering=promoted_offering)

        # Call the tool directly!
        # get_products is decorated with @mcp.tool, so we need to call the underlying function
        if hasattr(get_products, "__wrapped__"):
            # If it's a decorated function, get the original
            result = await get_products.__wrapped__(request, context)
        elif callable(get_products):
            # If it's directly callable
            result = await get_products(request, context)
        else:
            # Try to call it as a tool
            result = await get_products.fn(request, context)

        # Extract products from response and convert to dicts
        products = []
        if hasattr(result, "products"):
            products = result.products
        elif isinstance(result, dict):
            products = result.get("products", [])
        else:
            return []

        # Convert Pydantic models to dictionaries
        dict_products = []
        for p in products:
            if hasattr(p, "model_dump"):
                # Pydantic v2
                dict_products.append(p.model_dump())
            elif hasattr(p, "dict"):
                # Pydantic v1
                dict_products.append(p.dict())
            elif isinstance(p, dict):
                # Already a dict
                dict_products.append(p)
            else:
                # Try to convert to dict
                try:
                    dict_products.append(dict(p))
                except:
                    print(f"Warning: Could not convert product to dict: {type(p)}")
                    continue

        return dict_products

    except Exception as e:
        print(f"Error calling get_products directly: {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
        return []


# Create get_products function matching AdCP protocol
async def get_products(brief: str, promoted_offering: str) -> dict[str, Any]:
    """
    Get products from the AdCP server, matching the standard protocol.

    Args:
        brief: Description of advertising needs for contextual filtering (REQUIRED)
        promoted_offering: Description of advertiser and product/service being promoted (REQUIRED)

    Returns:
        Dict containing products list following AdCP protocol
    """
    try:
        # Get products using direct call with both required parameters
        products = await get_products_direct(brief, promoted_offering)

        # Return in AdCP protocol format
        return {"products": products, "total_count": len(products)}
    except Exception as e:
        print(f"Error in get_products: {e}")
        import traceback

        traceback.print_exc()
        return {"products": [], "total_count": 0, "error": str(e)}


# Create media buy function matching AdCP protocol
async def create_media_buy(
    product_ids: list[str],
    start_date: str,
    end_date: str,
    budget: float,
    targeting_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a media buy for selected products.

    Args:
        product_ids: List of product IDs to purchase
        start_date: Campaign start date (YYYY-MM-DD)
        end_date: Campaign end date (YYYY-MM-DD)
        budget: Total budget in USD
        targeting_overlay: Optional targeting parameters

    Returns:
        Dict with media_buy_id and status
    """
    context = setup_direct_call()

    try:

        from config_loader import set_current_tenant
        from main import create_media_buy as create_buy_direct
        from main import init_db
        from schemas import CreateMediaBuyRequest, Targeting

        # Initialize database if needed
        init_db()
        set_current_tenant("default")

        # Parse dates
        start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

        # Create request
        request = CreateMediaBuyRequest(
            product_ids=product_ids,
            start_date=start,
            end_date=end,
            budget=budget,
            targeting_overlay=Targeting(**targeting_overlay) if targeting_overlay else None,
        )

        # Call the tool directly
        if hasattr(create_buy_direct, "__wrapped__"):
            result = create_buy_direct.__wrapped__(request, context)
        else:
            result = create_buy_direct(request, context)

        # Convert result to dict
        if hasattr(result, "model_dump"):
            return result.model_dump()
        elif hasattr(result, "dict"):
            return result.dict()
        else:
            return {"media_buy_id": str(result.media_buy_id), "status": result.status}

    except Exception as e:
        print(f"Error in create_media_buy: {e}")
        import traceback

        traceback.print_exc()
        return {"error": str(e), "status": "failed"}


# Check media buy status function
async def check_media_buy_status(context_id: str) -> dict[str, Any]:
    """
    Check the status of a pending media buy.

    Args:
        context_id: The context ID returned from create_media_buy

    Returns:
        Dict with media_buy_id, status, and details
    """
    context = setup_direct_call()

    try:
        from config_loader import set_current_tenant
        from main import check_media_buy_status as check_status_direct
        from main import init_db
        from schemas import CheckMediaBuyStatusRequest

        init_db()
        set_current_tenant("default")

        request = CheckMediaBuyStatusRequest(context_id=context_id)

        if hasattr(check_status_direct, "__wrapped__"):
            result = check_status_direct.__wrapped__(request, context)
        else:
            result = check_status_direct(request, context)

        if hasattr(result, "model_dump"):
            return result.model_dump()
        elif hasattr(result, "dict"):
            return result.dict()
        else:
            return {"media_buy_id": str(result.media_buy_id), "status": result.status}

    except Exception as e:
        print(f"Error checking status: {e}")
        return {"error": str(e), "status": "error"}


# Get signals function (optional but part of AdCP v2.4)
async def get_signals(query: str | None = None, type: str | None = None, category: str | None = None) -> dict[str, Any]:
    """
    Discover available signals for targeting.

    Args:
        query: Natural language search query
        type: Filter by signal type
        category: Filter by category

    Returns:
        Dict with available signals
    """
    context = setup_direct_call()

    try:
        from config_loader import set_current_tenant
        from main import get_signals as get_signals_direct
        from main import init_db
        from schemas import GetSignalsRequest

        init_db()
        set_current_tenant("default")

        request = GetSignalsRequest(query=query, type=type, category=category)

        if hasattr(get_signals_direct, "__wrapped__"):
            result = await get_signals_direct.__wrapped__(request, context)
        else:
            result = await get_signals_direct(request, context)

        if hasattr(result, "model_dump"):
            return result.model_dump()
        elif hasattr(result, "dict"):
            return result.dict()
        else:
            return dict(result)

    except Exception as e:
        print(f"Error getting signals: {e}")
        return {"signals": [], "error": str(e)}


# Add creative assets function
async def add_creative_assets(media_buy_id: str, creatives: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Add creative assets to a media buy.

    Args:
        media_buy_id: The ID of the media buy
        creatives: List of creative asset specifications

    Returns:
        Dict with status and creative IDs
    """
    context = setup_direct_call()

    try:
        from config_loader import set_current_tenant
        from main import add_creative_assets as add_assets_direct
        from main import init_db
        from schemas import AddCreativeAssetsRequest, Creative

        init_db()
        set_current_tenant("default")

        # Convert creative dicts to Creative objects
        creative_objs = []
        for c in creatives:
            creative_objs.append(Creative(**c))

        request = AddCreativeAssetsRequest(media_buy_id=media_buy_id, creatives=creative_objs)

        if hasattr(add_assets_direct, "__wrapped__"):
            result = await add_assets_direct.__wrapped__(request, context)
        else:
            result = await add_assets_direct(request, context)

        if hasattr(result, "model_dump"):
            return result.model_dump()
        elif hasattr(result, "dict"):
            return result.dict()
        else:
            return dict(result)

    except Exception as e:
        print(f"Error adding creative assets: {e}")
        return {"error": str(e), "status": "failed"}


# Create tools from the functions
get_products_tool = FunctionTool(get_products)
create_media_buy_tool = FunctionTool(create_media_buy)
check_media_buy_status_tool = FunctionTool(check_media_buy_status)
get_signals_tool = FunctionTool(get_signals)
add_creative_assets_tool = FunctionTool(add_creative_assets)

# Create the agent with proper ADK configuration and all AdCP tools
root_agent = LlmAgent(
    name="adcp_sales_agent",
    model="gemini-2.0-flash-exp",
    instruction="""
You are an intelligent sales agent implementing the AdCP (Advertising Context Protocol) v2.4 standard.

Your capabilities include:
1. **Product Discovery**: Use get_products to find relevant advertising inventory
2. **Signal Discovery**: Use get_signals to explore available targeting options
3. **Media Buy Creation**: Use create_media_buy to purchase selected products
4. **Status Checking**: Use check_media_buy_status to monitor pending purchases
5. **Creative Management**: Use add_creative_assets to attach creatives to media buys

WORKFLOW:
1. When users describe their advertising needs:
   - Extract key requirements (budget, format, audience, geography, dates)
   - Call get_products with:
     * brief: Detailed description of their needs (e.g., "video ads for sports content with $10K budget")
     * promoted_offering: Description of their business/product (e.g., "sports streaming service")

2. When users want to explore targeting options:
   - Use get_signals to discover available audiences and contextual signals
   - Help them understand targeting capabilities

3. When users are ready to purchase:
   - Use create_media_buy with selected product_ids, dates, and budget
   - If the buy requires approval, note the context_id
   - Use check_media_buy_status to monitor approval status

4. When users have creative assets:
   - Use add_creative_assets to attach them to the media buy
   - Help them understand creative requirements and formats

5. Always provide clear explanations of:
   - Why products match their needs
   - Available targeting options
   - Next steps in the process

IMPORTANT:
- Both 'brief' and 'promoted_offering' are REQUIRED for get_products
- Dates should be in YYYY-MM-DD format
- Budget is in USD
- Be proactive in gathering all needed information before making tool calls

Be helpful, professional, and guide advertisers through the entire buying process.
""",
    tools=[
        get_products_tool,
        create_media_buy_tool,
        check_media_buy_status_tool,
        get_signals_tool,
        add_creative_assets_tool,
    ],
    description="Full AdCP v2.4 compliant sales agent for advertising inventory",
)

# Export the agent for ADK to find
__all__ = ["root_agent"]
