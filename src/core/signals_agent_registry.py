"""Signals Agent Registry for upstream signals discovery integration.

This module provides:
1. Signals agent registry (tenant-specific agents)
2. Dynamic signals discovery via MCP
3. Multi-agent support for different signals providers

Architecture:
- No default agent (tenant-specific only)
- Tenant agents: Configured in signals_agents database table
- Signals resolution: Query agents via MCP, handle responses
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.core.utils.mcp_client import MCPCompatibilityError, MCPConnectionError, create_mcp_client

logger = logging.getLogger(__name__)


@dataclass
class SignalsAgent:
    """Represents a signals discovery agent that provides product enhancement via signals.

    Note: priority, max_signal_products, and fallback_to_database are configured per-product,
    not per-agent.
    """

    agent_url: str
    name: str
    enabled: bool = True
    auth: dict[str, Any] | None = None  # Optional auth config for private agents
    auth_header: str | None = None  # HTTP header name for auth (e.g., "Authorization", "x-api-key")
    forward_promoted_offering: bool = True
    timeout: int = 30


class SignalsAgentRegistry:
    """Registry of signals discovery agents with dynamic discovery.

    Usage:
        registry = SignalsAgentRegistry()

        # Get signals from all agents
        signals = await registry.get_signals(
            brief="automotive targeting",
            tenant_id="tenant_123",
            promoted_offering="Tesla Model 3"
        )
    """

    def __init__(self):
        """Initialize registry with empty cache."""
        self._client_cache: dict[str, Client] = {}  # Key: agent_url

    def _get_tenant_agents(self, tenant_id: str) -> list[SignalsAgent]:
        """Get list of signals agents for a tenant.

        Returns:
            List of SignalsAgent instances (tenant-specific only)
        """
        agents = []

        # Load tenant-specific agents from database
        from sqlalchemy import select

        from src.core.database.database_session import get_db_session
        from src.core.database.models import SignalsAgent as SignalsAgentModel

        with get_db_session() as session:
            stmt = select(SignalsAgentModel).filter_by(tenant_id=tenant_id, enabled=True)
            db_agents = session.scalars(stmt).all()

            for db_agent in db_agents:
                # Parse auth credentials if present
                auth = None
                if db_agent.auth_type and db_agent.auth_credentials:
                    auth = {
                        "type": db_agent.auth_type,
                        "credentials": db_agent.auth_credentials,
                    }

                agents.append(
                    SignalsAgent(
                        agent_url=db_agent.agent_url,
                        name=db_agent.name,
                        enabled=db_agent.enabled,
                        auth=auth,
                        auth_header=db_agent.auth_header,
                        forward_promoted_offering=db_agent.forward_promoted_offering,
                        timeout=db_agent.timeout,
                    )
                )

        # Sort by name for consistent ordering
        agents.sort(key=lambda a: a.name)
        return [a for a in agents if a.enabled]

    async def _get_signals_from_agent(
        self,
        agent: SignalsAgent,
        brief: str,
        tenant_id: str,
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch signals from a signals discovery agent via MCP.

        Args:
            agent: SignalsAgent to query
            brief: Search brief/query
            tenant_id: Tenant identifier
            principal_id: Optional principal identifier
            context: Optional context data
            principal_data: Optional principal information

        Returns:
            List of signal objects from the agent
        """
        try:
            # Use unified MCP client for standardized connection handling
            async with create_mcp_client(
                agent_url=agent.agent_url,
                auth=agent.auth,
                auth_header=agent.auth_header,
                timeout=agent.timeout,
                max_retries=3,
            ) as client:
                # Build parameters for get_signals
                params: dict[str, Any] = {
                    "brief": brief,
                    "tenant_id": tenant_id,
                }

                if principal_id:
                    params["principal_id"] = principal_id

                if principal_data:
                    params["principal_data"] = principal_data

                if context:
                    params["context"] = context

                # Include promoted_offering if configured and available
                if agent.forward_promoted_offering and context and "promoted_offering" in context:
                    params["promoted_offering"] = context["promoted_offering"]

                # Call get_signals tool
                result = await asyncio.wait_for(client.call_tool("get_signals", params), timeout=agent.timeout)

                # Parse result into signals list
                signals_data = None
                if hasattr(result, "structured_content") and result.structured_content:
                    signals_data = result.structured_content
                    logger.info(f"_get_signals_from_agent: Using structured_content, type={type(signals_data)}")
                elif isinstance(result.content, list) and result.content:
                    # Fallback: Parse from content field (legacy)
                    signals_data = result.content[0].text if hasattr(result.content[0], "text") else result.content[0]
                    logger.info(
                        f"_get_signals_from_agent: Using legacy content field, signals_data (first 500 chars): {str(signals_data)[:500]}"
                    )

                    # Parse JSON if needed
                    import json

                    if isinstance(signals_data, str):
                        signals_data = json.loads(signals_data)

                signals = []
                if signals_data:
                    logger.info(
                        f"_get_signals_from_agent: After parse, type={type(signals_data)}, keys={list(signals_data.keys()) if isinstance(signals_data, dict) else 'not a dict'}"
                    )

                    # Extract signals array
                    if isinstance(signals_data, dict) and "signals" in signals_data:
                        logger.info(
                            f"_get_signals_from_agent: Found 'signals' key with {len(signals_data['signals'])} items"
                        )
                        signals = signals_data["signals"]
                    elif isinstance(signals_data, list):
                        logger.info(f"_get_signals_from_agent: Direct array with {len(signals_data)} items")
                        signals = signals_data
                    else:
                        logger.warning(f"_get_signals_from_agent: Unexpected response format. Data: {signals_data}")

                return signals

        except MCPCompatibilityError as e:
            # MCP SDK compatibility issue - log and re-raise as RuntimeError for backward compatibility
            logger.warning(f"MCP SDK compatibility issue: {e}")
            raise RuntimeError(str(e)) from e

        except MCPConnectionError as e:
            # Connection failed after retries - log and re-raise as RuntimeError for backward compatibility
            logger.error(f"Failed to connect to signals agent: {e}")
            raise RuntimeError(str(e)) from e

    async def get_signals(
        self,
        brief: str,
        tenant_id: str,
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Get signals from all registered agents for a tenant.

        Args:
            brief: Search brief/query
            tenant_id: Tenant identifier
            principal_id: Optional principal identifier
            context: Optional context data (may include promoted_offering)
            principal_data: Optional principal information

        Returns:
            List of all signal objects across all agents
        """
        agents = self._get_tenant_agents(tenant_id)
        all_signals = []

        logger.info(f"get_signals: Found {len(agents)} agents for tenant {tenant_id}")

        for agent in agents:
            logger.info(f"get_signals: Fetching from {agent.agent_url}")
            try:
                signals = await self._get_signals_from_agent(
                    agent,
                    brief=brief,
                    tenant_id=tenant_id,
                    principal_id=principal_id,
                    context=context,
                    principal_data=principal_data,
                )
                logger.info(f"get_signals: Got {len(signals)} signals from {agent.agent_url}")
                all_signals.extend(signals)
            except Exception as e:
                # Log error but continue with other agents
                logger.error(f"Failed to fetch signals from {agent.agent_url}: {e}", exc_info=True)
                continue

        logger.info(f"get_signals: Returning {len(all_signals)} total signals")
        return all_signals

    async def test_connection(self, agent_url: str, auth: dict[str, Any] | None = None) -> dict[str, Any]:
        """Test connection to a signals agent.

        Args:
            agent_url: URL of the signals agent
            auth: Optional authentication configuration

        Returns:
            dict with success status and message/error
        """
        try:
            # Create test agent config (minimal fields for testing)
            test_agent = SignalsAgent(
                agent_url=agent_url,
                name="Test Agent",
                enabled=True,
                auth=auth,
                timeout=30,
            )

            # Try to fetch signals with minimal query
            signals = await self._get_signals_from_agent(
                test_agent,
                brief="test",
                tenant_id="test_tenant",
            )

            return {
                "success": True,
                "message": "Successfully connected to signals agent",
                "signal_count": len(signals),
            }

        except Exception as e:
            logger.error(f"Connection test failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}",
            }


# Global registry instance
_registry: SignalsAgentRegistry | None = None


def get_signals_agent_registry() -> SignalsAgentRegistry:
    """Get the global signals agent registry instance."""
    global _registry
    if _registry is None:
        _registry = SignalsAgentRegistry()
    return _registry
