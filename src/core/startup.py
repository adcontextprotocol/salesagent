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
        import os

        from src.core.config import get_config

        # Just check that config can be loaded
        config = get_config()

        # Super admin access - at least one must be set
        super_admin_emails = os.environ.get("SUPER_ADMIN_EMAILS", "")
        super_admin_domains = os.environ.get("SUPER_ADMIN_DOMAINS", "")
        if not super_admin_emails and not super_admin_domains:
            raise ValueError(
                "SUPER_ADMIN_EMAILS or SUPER_ADMIN_DOMAINS is required. " "Set at least one to grant admin access."
            )

        logger.info("Startup requirements validation passed")

    except Exception as e:
        logger.error(f"Startup requirements validation failed: {str(e)}")
        raise
