"""Landing page configuration generator for new tenants.

Automatically generates default landing page configurations with sensible defaults
and industry-appropriate messaging when creating new tenants.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def generate_default_landing_config(
    tenant_name: str,
    contact_email: str | None = None,
    logo_url: str | None = None,
    custom_message: str | None = None,
) -> dict[str, Any]:
    """Generate default landing page configuration for a new tenant.

    Args:
        tenant_name: Name of the tenant/publisher
        contact_email: Optional contact email for sales
        logo_url: Optional logo URL for branding
        custom_message: Optional custom hero message

    Returns:
        Dictionary containing landing page configuration
    """

    # Default color scheme (professional blue/green)
    primary_color = "#2563eb"  # Blue
    secondary_color = "#10b981"  # Green

    # Generate hero message
    if custom_message:
        hero_message = custom_message
    else:
        hero_message = f"Discover {tenant_name}'s advertising inventory through AI agents"

    # Generate description
    description = "Browse our products, then connect your buying agent to start campaigns instantly"

    # Default configuration
    config = {
        "hero_message": hero_message,
        "description": description,
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "partner_links": [
            {"name": "Scope3", "url": "https://scope3.com/signup", "description": "AI-powered media buying platform"}
        ],
    }

    # Add optional fields if provided
    if contact_email:
        config["contact_email"] = contact_email

    if logo_url:
        config["logo_url"] = logo_url

    logger.info(f"Generated default landing config for tenant: {tenant_name}")

    return config


def update_tenant_landing_config(tenant_id: str, config_updates: dict[str, Any]) -> None:
    """Update landing page configuration for an existing tenant.

    Args:
        tenant_id: ID of the tenant to update
        config_updates: Dictionary of configuration updates to apply
    """
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Tenant

    try:
        with get_db_session() as session:
            tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()

            if not tenant:
                logger.error(f"Tenant not found: {tenant_id}")
                return

            # Get existing config or create new one
            current_config = tenant.landing_config or {}

            # Merge updates with existing config
            updated_config = {**current_config, **config_updates}

            # Update tenant
            tenant.landing_config = updated_config
            session.commit()

            logger.info(f"Updated landing config for tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Error updating landing config for tenant {tenant_id}: {e}")
        raise


def set_products_public_by_default(tenant_id: str) -> None:
    """Set all products for a tenant to be public by default.

    This ensures new tenants have their products visible on the landing page.

    Args:
        tenant_id: ID of the tenant
    """
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Product

    try:
        with get_db_session() as session:
            # Update all products for this tenant to be public
            products = session.query(Product).filter_by(tenant_id=tenant_id).all()

            for product in products:
                if not hasattr(product, "requires_authentication"):
                    # If the field doesn't exist yet (before migration), skip
                    continue
                product.requires_authentication = False

            session.commit()

            logger.info(f"Set {len(products)} products to public for tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Error setting products to public for tenant {tenant_id}: {e}")
        # Don't raise - this is not critical


def setup_tenant_landing_page(
    tenant_id: str,
    tenant_name: str,
    contact_email: str | None = None,
    logo_url: str | None = None,
    custom_message: str | None = None,
) -> None:
    """Complete landing page setup for a new tenant.

    This function should be called when creating a new tenant to ensure
    they have a fully configured landing page.

    Args:
        tenant_id: ID of the tenant
        tenant_name: Name of the tenant/publisher
        contact_email: Optional contact email for sales
        logo_url: Optional logo URL for branding
        custom_message: Optional custom hero message
    """
    try:
        # Generate default landing configuration
        landing_config = generate_default_landing_config(
            tenant_name=tenant_name, contact_email=contact_email, logo_url=logo_url, custom_message=custom_message
        )

        # Update tenant with landing configuration
        update_tenant_landing_config(tenant_id, landing_config)

        # Set products to be public by default
        set_products_public_by_default(tenant_id)

        logger.info(f"Completed landing page setup for tenant: {tenant_name} ({tenant_id})")

    except Exception as e:
        logger.error(f"Error setting up landing page for tenant {tenant_id}: {e}")
        raise


# Color scheme presets for variety
COLOR_SCHEMES = {
    "blue_green": {"primary": "#2563eb", "secondary": "#10b981"},
    "purple_pink": {"primary": "#7c3aed", "secondary": "#ec4899"},
    "indigo_cyan": {"primary": "#4f46e5", "secondary": "#06b6d4"},
    "orange_red": {"primary": "#ea580c", "secondary": "#dc2626"},
    "emerald_blue": {"primary": "#059669", "secondary": "#2563eb"},
}


def get_random_color_scheme() -> dict[str, str]:
    """Get a random color scheme for variety in tenant landing pages."""
    import random

    scheme_name = random.choice(list(COLOR_SCHEMES.keys()))
    return COLOR_SCHEMES[scheme_name]


def generate_industry_specific_message(tenant_name: str, industry_hint: str = "") -> str:
    """Generate industry-specific hero messages based on tenant name or hints.

    Args:
        tenant_name: Name of the tenant
        industry_hint: Optional hint about the industry (from domain, description, etc.)

    Returns:
        Industry-appropriate hero message
    """
    name_lower = tenant_name.lower()
    hint_lower = industry_hint.lower()

    # News/Media
    if any(
        word in name_lower + " " + hint_lower
        for word in ["news", "media", "times", "post", "journal", "gazette", "herald"]
    ):
        return f"Reach engaged {tenant_name} readers through AI-driven advertising"

    # Sports
    elif any(
        word in name_lower + " " + hint_lower for word in ["sports", "athletic", "league", "team", "espn", "sport"]
    ):
        return f"Target passionate {tenant_name} fans with precision"

    # Entertainment
    elif any(
        word in name_lower + " " + hint_lower
        for word in ["entertainment", "studio", "movies", "tv", "streaming", "netflix", "hulu"]
    ):
        return f"Advertise alongside premium {tenant_name} content"

    # Technology/B2B
    elif any(
        word in name_lower + " " + hint_lower for word in ["tech", "software", "platform", "app", "digital", "cloud"]
    ):
        return f"Connect with {tenant_name}'s professional audience through AI agents"

    # E-commerce/Retail
    elif any(
        word in name_lower + " " + hint_lower for word in ["shop", "store", "retail", "marketplace", "commerce", "buy"]
    ):
        return f"Reach {tenant_name} shoppers with targeted AI-powered campaigns"

    # Default
    else:
        return f"Discover {tenant_name}'s advertising inventory through AI agents"
