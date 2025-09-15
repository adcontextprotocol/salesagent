"""
Google Ad Manager Authentication Manager

Handles OAuth credentials, service account authentication, and credential management
for Google Ad Manager API access.
"""

import logging
from typing import Any

import google.oauth2.service_account
from googleads import oauth2

logger = logging.getLogger(__name__)


class GAMAuthManager:
    """Manages authentication credentials for Google Ad Manager API."""

    def __init__(self, config: dict[str, Any]):
        """Initialize authentication manager with configuration.

        Args:
            config: Dictionary containing authentication configuration:
                - refresh_token: OAuth refresh token (preferred)
                - service_account_key_file: Path to service account JSON file (legacy)
        """
        self.config = config
        self.refresh_token = config.get("refresh_token")
        self.key_file = config.get("service_account_key_file")

        # Validate that we have at least one authentication method
        if not self.refresh_token and not self.key_file:
            raise ValueError("GAM config requires either 'refresh_token' or 'service_account_key_file'")

    def get_credentials(self):
        """Get authenticated credentials for GAM API.

        Returns:
            Authenticated credentials object for use with GAM client.

        Raises:
            ValueError: If authentication configuration is invalid
            Exception: If credential creation fails
        """
        try:
            if self.refresh_token:
                return self._get_oauth_credentials()
            elif self.key_file:
                return self._get_service_account_credentials()
            else:
                raise ValueError("No valid authentication method configured")
        except Exception as e:
            logger.error(f"Error creating GAM credentials: {e}")
            raise

    def _get_oauth_credentials(self):
        """Get OAuth credentials using refresh token and Pydantic configuration."""
        try:
            from src.core.config import get_gam_oauth_config

            # Get validated configuration
            gam_config = get_gam_oauth_config()
            client_id = gam_config.client_id
            client_secret = gam_config.client_secret

        except Exception as e:
            raise ValueError(f"GAM OAuth configuration error: {str(e)}") from e

        # Create GoogleAds OAuth2 client
        oauth2_client = oauth2.GoogleRefreshTokenClient(
            client_id=client_id, client_secret=client_secret, refresh_token=self.refresh_token
        )

        return oauth2_client

    def _get_service_account_credentials(self):
        """Get service account credentials from JSON key file (legacy)."""
        credentials = google.oauth2.service_account.Credentials.from_service_account_file(
            self.key_file, scopes=["https://www.googleapis.com/auth/dfp"]
        )
        return credentials

    def is_oauth_configured(self) -> bool:
        """Check if OAuth authentication is configured."""
        return self.refresh_token is not None

    def is_service_account_configured(self) -> bool:
        """Check if service account authentication is configured."""
        return self.key_file is not None

    def get_auth_method(self) -> str:
        """Get the current authentication method name."""
        if self.is_oauth_configured():
            return "oauth"
        elif self.is_service_account_configured():
            return "service_account"
        else:
            return "none"
