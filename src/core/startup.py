"""Startup configuration and validation for AdCP Sales Agent."""

import logging

from src.core.config import validate_configuration
from src.core.logging_config import setup_oauth_logging, setup_structured_logging

logger = logging.getLogger(__name__)


def initialize_application() -> None:
    """Initialize the application with configuration validation and setup.

    This should be called at the start of both the MCP server and Admin UI.

    Raises:
        SystemExit: If configuration validation fails
    """
    try:
        # Setup structured logging FIRST (before any logging calls)
        # This ensures production environments get JSON logs
        setup_structured_logging()

        logger.info("Initializing AdCP Sales Agent...")

        # Setup OAuth-specific logging
        setup_oauth_logging()
        logger.info("Structured logging initialized")

        # Validate all configuration
        validate_configuration()
        logger.info("Configuration validation passed")

        logger.info("Application initialization completed successfully")

    except Exception as e:
        logger.error(f"Application initialization failed: {str(e)}")
        raise SystemExit(1) from e


def validate_startup_requirements() -> None:
    """Validate startup requirements without full initialization.

    This is useful for health checks and lightweight validation.
    """
    try:
        from src.core.config import get_config

        # Just check that config can be loaded
        config = get_config()

        # Basic sanity checks
        if not config.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required")

        if not config.superadmin.emails:
            raise ValueError("SUPER_ADMIN_EMAILS is required")

        logger.info("Startup requirements validation passed")

    except Exception as e:
        logger.error(f"Startup requirements validation failed: {str(e)}")
        raise
