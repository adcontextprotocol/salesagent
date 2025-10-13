"""Creative Agent Registry for dynamic format discovery per AdCP v2.4.

This module provides:
1. Creative agent registry (system defaults + tenant-specific)
2. Dynamic format discovery via MCP
3. Format caching (in-memory with TTL)
4. Multi-agent support for DCO platforms, custom creative agents

Architecture:
- Default agent: https://creative.adcontextprotocol.org (always available)
- Tenant agents: Configured in tenant.config.creative_agents[]
- Format resolution: Query agents via MCP, cache results
- Preview generation: Delegate to creative agent
- Generative creative: Use agent's create_generative_creative tool
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from src.core.schemas import Format


@dataclass
class CreativeAgent:
    """Represents a creative agent that provides format definitions and creative services."""

    agent_url: str
    name: str
    enabled: bool = True
    priority: int = 1  # Lower = higher priority in search results
    auth: dict[str, Any] | None = None  # Optional auth config for private agents


@dataclass
class CachedFormats:
    """Cached format list from a creative agent."""

    formats: list[Format]
    fetched_at: datetime
    ttl_seconds: int = 3600  # 1 hour default

    def is_expired(self) -> bool:
        """Check if cache has expired."""
        return datetime.now(UTC) > self.fetched_at + timedelta(seconds=self.ttl_seconds)


class CreativeAgentRegistry:
    """Registry of creative agents with dynamic format discovery and caching.

    Usage:
        registry = CreativeAgentRegistry()

        # Get all formats from all agents
        formats = await registry.list_all_formats(tenant_id="tenant_123")

        # Search formats across agents
        results = await registry.search_formats(query="300x250", tenant_id="tenant_123")

        # Get specific format
        fmt = await registry.get_format(
            agent_url="https://creative.adcontextprotocol.org",
            format_id="display_300x250_image"
        )
    """

    # Default creative agent (always available)
    DEFAULT_AGENT = CreativeAgent(
        agent_url="https://creative.adcontextprotocol.org",
        name="AdCP Standard Creative Agent",
        enabled=True,
        priority=1,
    )

    def __init__(self):
        """Initialize registry with empty cache."""
        self._format_cache: dict[str, CachedFormats] = {}  # Key: agent_url

    def _get_tenant_agents(self, tenant_id: str | None) -> list[CreativeAgent]:
        """Get list of creative agents for a tenant.

        Returns:
            List of CreativeAgent instances (default + tenant-specific)
        """
        agents = [self.DEFAULT_AGENT]

        if not tenant_id:
            return agents

        # Load tenant-specific agents from database
        from sqlalchemy import select

        from src.core.database.database_session import get_db_session
        from src.core.database.models import Tenant as TenantModel

        with get_db_session() as session:
            stmt = select(TenantModel).filter_by(tenant_id=tenant_id)
            tenant = session.scalars(stmt).first()

            if not tenant or not tenant.config:
                return agents

            # Parse creative_agents from tenant config
            tenant_agents_config = tenant.config.get("creative_agents", [])
            for agent_config in tenant_agents_config:
                agents.append(
                    CreativeAgent(
                        agent_url=agent_config["agent_url"],
                        name=agent_config["name"],
                        enabled=agent_config.get("enabled", True),
                        priority=agent_config.get("priority", 10),
                        auth=agent_config.get("auth"),
                    )
                )

        # Sort by priority (lower number = higher priority)
        agents.sort(key=lambda a: a.priority)
        return [a for a in agents if a.enabled]

    async def _fetch_formats_from_agent(self, agent: CreativeAgent) -> list[Format]:
        """Fetch format list from a creative agent via MCP.

        Args:
            agent: CreativeAgent to query

        Returns:
            List of Format objects from the agent
        """
        # Build MCP client
        headers = {}
        if agent.auth and agent.auth.get("type") == "bearer":
            token = agent.auth.get("token") or self._get_auth_token(agent.auth.get("token_env"))
            headers["Authorization"] = f"Bearer {token}"

        transport = StreamableHttpTransport(url=f"{agent.agent_url}/mcp", headers=headers)
        client = Client(transport=transport)

        async with client:
            # Call list_creative_formats tool
            result = await client.call_tool("list_creative_formats", {})

            # Parse result into Format objects
            formats = []
            if isinstance(result.content, list) and result.content:
                # Extract formats from MCP response
                formats_data = result.content[0].text if hasattr(result.content[0], "text") else result.content[0]

                # Parse JSON if needed
                import json

                if isinstance(formats_data, str):
                    formats_data = json.loads(formats_data)

                # Convert to Format objects
                if isinstance(formats_data, dict) and "formats" in formats_data:
                    for fmt_data in formats_data["formats"]:
                        # Ensure agent_url is set
                        fmt_data["agent_url"] = agent.agent_url
                        formats.append(Format(**fmt_data))

            return formats

    def _get_auth_token(self, token_env: str | None) -> str | None:
        """Get auth token from environment variable.

        Args:
            token_env: Environment variable name

        Returns:
            Token value or None
        """
        if not token_env:
            return None

        import os

        return os.environ.get(token_env)

    async def get_formats_for_agent(self, agent: CreativeAgent, force_refresh: bool = False) -> list[Format]:
        """Get formats from agent with caching.

        Args:
            agent: CreativeAgent to query
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of Format objects
        """
        # Check cache
        cached = self._format_cache.get(agent.agent_url)
        if cached and not cached.is_expired() and not force_refresh:
            return cached.formats

        # Fetch from agent
        formats = await self._fetch_formats_from_agent(agent)

        # Update cache
        self._format_cache[agent.agent_url] = CachedFormats(
            formats=formats, fetched_at=datetime.now(UTC), ttl_seconds=3600
        )

        return formats

    async def list_all_formats(self, tenant_id: str | None = None, force_refresh: bool = False) -> list[Format]:
        """List all formats from all registered agents.

        Args:
            tenant_id: Optional tenant ID for tenant-specific agents
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of all Format objects across all agents
        """
        agents = self._get_tenant_agents(tenant_id)
        all_formats = []

        for agent in agents:
            try:
                formats = await self.get_formats_for_agent(agent, force_refresh=force_refresh)
                all_formats.extend(formats)
            except Exception as e:
                # Log error but continue with other agents
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to fetch formats from {agent.agent_url}: {e}")
                continue

        return all_formats

    async def search_formats(
        self, query: str, tenant_id: str | None = None, type_filter: str | None = None
    ) -> list[Format]:
        """Search formats across all agents.

        Args:
            query: Search query (matches format_id, name, description)
            tenant_id: Optional tenant ID for tenant-specific agents
            type_filter: Optional format type filter (display, video, etc.)

        Returns:
            List of matching Format objects
        """
        all_formats = await self.list_all_formats(tenant_id)
        query_lower = query.lower()

        results = []
        for fmt in all_formats:
            # Match query against format_id, name, or description
            if (
                query_lower in fmt.format_id.lower()
                or query_lower in fmt.name.lower()
                or (fmt.description and query_lower in fmt.description.lower())
            ):
                # Apply type filter if provided
                if type_filter and fmt.type != type_filter:
                    continue

                results.append(fmt)

        return results

    async def get_format(self, agent_url: str, format_id: str) -> Format | None:
        """Get a specific format from an agent.

        Args:
            agent_url: URL of the creative agent
            format_id: Format ID to retrieve

        Returns:
            Format object or None if not found
        """
        # Find agent
        agent = CreativeAgent(agent_url=agent_url, name="Unknown", enabled=True)

        # Get formats (uses cache)
        formats = await self.get_formats_for_agent(agent)

        # Find matching format
        for fmt in formats:
            if fmt.format_id == format_id:
                return fmt

        return None

    async def generate_preview(self, agent_url: str, format_id: str, creative_assets: dict[str, Any]) -> dict[str, Any]:
        """Generate a preview for a creative using the creative agent.

        Args:
            agent_url: URL of the creative agent
            format_id: Format ID for the creative
            creative_assets: Creative assets (URLs, content, etc.)

        Returns:
            Preview generation result with preview_url
        """
        # Build MCP client
        transport = StreamableHttpTransport(url=f"{agent_url}/mcp")
        client = Client(transport=transport)

        async with client:
            result = await client.call_tool("generate_preview", {"format_id": format_id, "assets": creative_assets})

            # Parse result
            import json

            if isinstance(result.content, list) and result.content:
                preview_data = result.content[0].text if hasattr(result.content[0], "text") else result.content[0]
                if isinstance(preview_data, str):
                    preview_data = json.loads(preview_data)
                return preview_data

            return {}

    async def create_generative_creative(
        self, agent_url: str, format_id: str, brand_manifest: dict[str, Any], prompt: str
    ) -> dict[str, Any]:
        """Create a generative creative using the creative agent.

        Args:
            agent_url: URL of the creative agent
            format_id: Format ID (must be generative type)
            brand_manifest: Brand context and guidelines
            prompt: Creative generation prompt

        Returns:
            Generated creative with assets and preview_url
        """
        # Build MCP client
        transport = StreamableHttpTransport(url=f"{agent_url}/mcp")
        client = Client(transport=transport)

        async with client:
            result = await client.call_tool(
                "create_generative_creative",
                {"format_id": format_id, "brand_manifest": brand_manifest, "prompt": prompt},
            )

            # Parse result
            import json

            if isinstance(result.content, list) and result.content:
                creative_data = result.content[0].text if hasattr(result.content[0], "text") else result.content[0]
                if isinstance(creative_data, str):
                    creative_data = json.loads(creative_data)
                return creative_data

            return {}


# Global registry instance
_registry: CreativeAgentRegistry | None = None


def get_creative_agent_registry() -> CreativeAgentRegistry:
    """Get the global creative agent registry instance."""
    global _registry
    if _registry is None:
        _registry = CreativeAgentRegistry()
    return _registry
