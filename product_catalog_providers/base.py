"""Base interface for product catalog providers."""

from abc import ABC, abstractmethod
from typing import Any

from schemas import Product


class ProductCatalogProvider(ABC):
    """
    Abstract base class for product catalog providers.

    Implementations can fetch products from various sources:
    - Static database
    - Upstream MCP servers
    - AI/RAG systems
    - External APIs
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the provider with configuration.

        Args:
            config: Provider-specific configuration from tenant config
        """
        self.config = config

    @abstractmethod
    async def get_products(
        self,
        brief: str,
        tenant_id: str,
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[Product]:
        """
        Get products that match the given brief.

        Args:
            brief: Description of advertising needs/campaign brief
            tenant_id: Current tenant ID
            principal_id: Optional principal/advertiser ID for personalization
            context: Optional additional context (targeting, budget hints, etc.)
            principal_data: Optional full principal object with ad server mappings

        Returns:
            List of Product objects that match the brief
        """
        pass

    async def initialize(self) -> None:
        """
        Optional initialization method for providers that need setup.
        Called once when the provider is instantiated.
        """
        pass

    async def shutdown(self) -> None:
        """
        Optional cleanup method for providers.
        Called when the server is shutting down.
        """
        pass
