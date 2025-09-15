"""
Google Ad Manager Client Manager

Handles GAM API client initialization, management, and service access.
Provides centralized access to GAM API services.
"""

import logging
from typing import Any

from googleads import ad_manager

from .auth import GAMAuthManager

logger = logging.getLogger(__name__)


class GAMClientManager:
    """Manages GAM API client and service access."""

    def __init__(self, config: dict[str, Any], network_code: str):
        """Initialize client manager.

        Args:
            config: Authentication and client configuration
            network_code: GAM network code
        """
        self.config = config
        self.network_code = network_code
        self.auth_manager = GAMAuthManager(config)
        self._client: ad_manager.AdManagerClient | None = None

    def get_client(self) -> ad_manager.AdManagerClient:
        """Get or create the GAM API client.

        Returns:
            Initialized AdManagerClient instance

        Raises:
            ValueError: If network code is missing
            Exception: If client initialization fails
        """
        if self._client is None:
            self._client = self._init_client()
        return self._client

    def _init_client(self) -> ad_manager.AdManagerClient:
        """Initialize the Ad Manager client.

        Returns:
            Initialized AdManagerClient

        Raises:
            ValueError: If configuration is invalid
            Exception: If client creation fails
        """
        if not self.network_code:
            raise ValueError("Network code is required for GAM client initialization")

        try:
            # Get credentials from auth manager
            credentials = self.auth_manager.get_credentials()

            # Create AdManager client
            ad_manager_client = ad_manager.AdManagerClient(
                credentials, "AdCP Sales Agent", network_code=self.network_code
            )

            logger.info(
                f"GAM client initialized for network {self.network_code} using {self.auth_manager.get_auth_method()}"
            )
            return ad_manager_client

        except Exception as e:
            logger.error(f"Error initializing GAM client: {e}")
            raise

    def get_service(self, service_name: str):
        """Get a specific GAM API service.

        Args:
            service_name: Name of the service (e.g., 'OrderService', 'LineItemService')

        Returns:
            GAM service instance
        """
        client = self.get_client()
        return client.GetService(service_name, version="v202411")

    def get_statement_builder(self):
        """Get a StatementBuilder for GAM API queries.

        Returns:
            StatementBuilder instance
        """
        client = self.get_client()
        return client.GetService("StatementBuilder", version="v202411")

    def is_connected(self) -> bool:
        """Check if client is connected and working.

        Returns:
            True if client is connected, False otherwise
        """
        try:
            client = self.get_client()
            # Simple test call - get network info
            network_service = client.GetService("NetworkService", version="v202411")
            network_service.getCurrentNetwork()
            return True
        except Exception as e:
            logger.warning(f"GAM client connection test failed: {e}")
            return False

    def reset_client(self) -> None:
        """Reset the client connection (force re-initialization on next access)."""
        self._client = None
        logger.info("GAM client reset - will re-initialize on next access")
