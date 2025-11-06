#!/usr/bin/env python
"""Debug script to test creative agent connectivity with adcp library."""

import asyncio
import logging

from adcp import ADCPMultiAgentClient, AgentConfig, ListCreativeFormatsRequest

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_creative_agent():
    """Test connecting to creative agent and listing formats."""
    logger.info("Testing AdCP Creative Agent connectivity...")

    # Configure agent
    agent_config = AgentConfig(
        id="AdCP Standard Creative Agent",
        agent_uri="https://creative.adcontextprotocol.org",
        protocol="mcp",
        auth_token=None,  # No auth required
        auth_type="token",
        auth_header="x-adcp-auth",
        timeout=30.0,
    )

    # Create client
    client = ADCPMultiAgentClient(agents=[agent_config])

    # Create request
    request = ListCreativeFormatsRequest()

    logger.info(f"Calling list_creative_formats on {agent_config.agent_uri}")

    # Call agent
    try:
        result = await client.agent("AdCP Standard Creative Agent").list_creative_formats(request)

        logger.info(f"Result status: {result.status}")
        logger.info(f"Result type: {type(result)}")

        if result.status == "completed":
            formats_data = result.data
            logger.info(f"Result data type: {type(formats_data)}")
            logger.info(f"Result data: {formats_data}")

            if hasattr(formats_data, "formats"):
                logger.info(f"Number of formats: {len(formats_data.formats)}")
                if formats_data.formats:
                    logger.info(f"First format: {formats_data.formats[0]}")
            else:
                logger.error("Result data does not have 'formats' attribute")
        else:
            logger.error(f"Result status is not 'completed': {result.status}")
            if hasattr(result, "error"):
                logger.error(f"Error: {result.error}")

    except Exception as e:
        logger.error(f"Exception calling creative agent: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(test_creative_agent())
