"""Hybrid product catalog provider that combines database and signals discovery."""

import json
import logging
from typing import Any

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant
from src.core.schemas import Product

from .base import ProductCatalogProvider
from .database import DatabaseProductCatalog
from .signals import SignalsDiscoveryProvider

logger = logging.getLogger(__name__)


class HybridProductCatalog(ProductCatalogProvider):
    """
    Hybrid product catalog that intelligently combines multiple product sources.

    This provider:
    1. Uses database products as the foundation
    2. Enhances with signals discovery when configured and brief is present
    3. Deduplicates and ranks products by relevance
    4. Provides seamless fallback behavior

    Configuration:
        signals_discovery: Configuration for signals discovery provider
        database: Configuration for database provider (optional, uses defaults)
        ranking_strategy: How to rank combined products ("signals_first", "database_first", "interleaved")
        max_products: Maximum number of products to return (default: 20)
        deduplicate: Remove similar products based on name/description (default: True)
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.ranking_strategy = config.get("ranking_strategy", "signals_first")
        self.max_products = config.get("max_products", 20)
        self.deduplicate = config.get("deduplicate", True)

        # Initialize sub-providers
        database_config = config.get("database", {})
        signals_config = config.get("signals_discovery", {})

        self.database_provider = DatabaseProductCatalog(database_config)
        self.signals_provider = SignalsDiscoveryProvider(signals_config)

        logger.info(f"Initialized hybrid catalog with ranking: {self.ranking_strategy}")

    async def initialize(self) -> None:
        """Initialize all sub-providers."""
        try:
            await self.database_provider.initialize()
            await self.signals_provider.initialize()
            logger.info("Initialized hybrid product catalog providers")
        except Exception as e:
            logger.error(f"Error initializing hybrid providers: {e}")
            # Continue - individual providers handle their own fallbacks

    async def shutdown(self) -> None:
        """Shutdown all sub-providers."""
        try:
            await self.database_provider.shutdown()
            await self.signals_provider.shutdown()
            logger.info("Shut down hybrid product catalog providers")
        except Exception as e:
            logger.error(f"Error shutting down hybrid providers: {e}")

    async def get_products(
        self,
        brief: str,
        tenant_id: str,
        principal_id: str | None = None,
        context: dict[str, Any] | None = None,
        principal_data: dict[str, Any] | None = None,
    ) -> list[Product]:
        """
        Get products from multiple sources and intelligently combine them.
        """
        all_products = []

        # Check if signals discovery is enabled for this tenant
        signals_enabled = await self._is_signals_enabled(tenant_id)

        # Get products from database (always available)
        try:
            database_products = await self.database_provider.get_products(
                brief, tenant_id, principal_id, context, principal_data
            )
            logger.info(f"Retrieved {len(database_products)} products from database")
        except Exception as e:
            logger.error(f"Error getting database products: {e}")
            database_products = []

        # Get products from signals discovery if enabled
        signals_products = []
        if signals_enabled:
            try:
                signals_products = await self.signals_provider.get_products(
                    brief, tenant_id, principal_id, context, principal_data
                )
                logger.info(f"Retrieved {len(signals_products)} products from signals discovery")
            except Exception as e:
                logger.error(f"Error getting signals products: {e}")

        # Combine products according to ranking strategy
        all_products = self._combine_products(database_products, signals_products)

        # Deduplicate if enabled
        if self.deduplicate:
            all_products = self._deduplicate_products(all_products)

        # Limit to max products
        if len(all_products) > self.max_products:
            all_products = all_products[: self.max_products]

        logger.info(f"Returning {len(all_products)} products from hybrid catalog")
        return all_products

    async def _is_signals_enabled(self, tenant_id: str) -> bool:
        """Check if signals discovery is enabled for the tenant."""
        try:
            with get_db_session() as db_session:
                stmt = select(Tenant).filter_by(tenant_id=tenant_id)
                tenant = db_session.scalars(stmt).first()
                if not tenant or not tenant.signals_agent_config:
                    return False

                # Parse signals configuration
                if isinstance(tenant.signals_agent_config, dict):
                    config = tenant.signals_agent_config
                else:
                    config = json.loads(tenant.signals_agent_config)

                # Signals discovery is configured if upstream_url is present
                return bool(config.get("upstream_url"))

        except Exception as e:
            logger.error(f"Error checking signals configuration: {e}")
            return False

    def _combine_products(self, database_products: list[Product], signals_products: list[Product]) -> list[Product]:
        """Combine products from different sources based on ranking strategy."""

        if self.ranking_strategy == "signals_first":
            # Signals products first, then database products
            return signals_products + database_products

        elif self.ranking_strategy == "database_first":
            # Database products first, then signals products
            return database_products + signals_products

        elif self.ranking_strategy == "interleaved":
            # Interleave products from both sources
            combined = []
            max_len = max(len(database_products), len(signals_products))

            for i in range(max_len):
                # Add signals product if available
                if i < len(signals_products):
                    combined.append(signals_products[i])
                # Add database product if available
                if i < len(database_products):
                    combined.append(database_products[i])

            return combined

        else:
            # Default: signals first
            logger.warning(f"Unknown ranking strategy: {self.ranking_strategy}, using signals_first")
            return signals_products + database_products

    def _deduplicate_products(self, products: list[Product]) -> list[Product]:
        """Remove duplicate products based on name similarity."""
        if not products:
            return products

        deduplicated = []
        seen_names: set[str] = set()

        for product in products:
            # Simple deduplication based on normalized product name
            normalized_name = product.name.lower().strip()

            # Check if we've seen a very similar name
            is_duplicate = False
            for seen_name in seen_names:
                if self._names_are_similar(normalized_name, seen_name):
                    is_duplicate = True
                    break

            if not is_duplicate:
                deduplicated.append(product)
                seen_names.add(normalized_name)
            else:
                logger.debug(f"Deduplicating product: {product.name}")

        logger.info(f"Deduplicated {len(products)} products to {len(deduplicated)}")
        return deduplicated

    def _names_are_similar(self, name1: str, name2: str, threshold: float = 0.8) -> bool:
        """Check if two product names are similar enough to be considered duplicates."""
        # Simple similarity check based on word overlap
        words1 = set(name1.split())
        words2 = set(name2.split())

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity (intersection / union)
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold


# Convenience function for easy tenant configuration
async def create_hybrid_catalog_for_tenant(tenant_id: str) -> HybridProductCatalog:
    """
    Create a hybrid catalog configured for a specific tenant.

    This function reads the tenant's signals configuration from the database
    and sets up the hybrid catalog appropriately.
    """
    config: dict[str, Any] = {
        "database": {},  # Use defaults
        "signals_discovery": {},  # Will be populated from tenant config
    }

    try:
        with get_db_session() as db_session:
            stmt = select(Tenant).filter_by(tenant_id=tenant_id)
            tenant = db_session.scalars(stmt).first()
            if tenant and tenant.signals_agent_config:
                # Parse signals configuration from tenant
                if isinstance(tenant.signals_agent_config, dict):
                    signals_config = tenant.signals_agent_config
                else:
                    signals_config = json.loads(tenant.signals_agent_config)

                config["signals_discovery"] = signals_config
                logger.info(f"Loaded signals config for tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Error loading tenant signals config: {e}")
        # Continue with empty signals config (will be disabled)

    catalog = HybridProductCatalog(config)
    await catalog.initialize()

    return catalog
