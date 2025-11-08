"""Dynamic product variant generation from signals agents.

This service handles:
1. Querying signals agents with buyer briefs
2. Generating product variants from signals
3. Managing variant lifecycle (creation, expiration, archival)
"""

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import attributes

from src.core.database.database_session import get_db_session
from src.core.database.models import Product, SignalsAgent

logger = logging.getLogger(__name__)


def generate_variants_for_brief(tenant_id: str, brief: str) -> list[Product]:
    """Generate product variants from signals agents based on buyer's brief.

    Args:
        tenant_id: Tenant ID
        brief: Buyer's brief text

    Returns:
        List of Product variants (newly created or existing)
    """
    variants = []

    with get_db_session() as session:
        # Get all dynamic product templates for this tenant
        stmt = select(Product).filter_by(tenant_id=tenant_id, is_dynamic=True, archived_at=None)
        templates = session.scalars(stmt).all()

        if not templates:
            logger.debug(f"No dynamic product templates found for tenant {tenant_id}")
            return []

        for template in templates:
            if not template.signals_agent_ids:
                logger.warning(f"Dynamic product {template.product_id} has no signals agents configured")
                continue

            # Query each configured signals agent
            for agent_id in template.signals_agent_ids:
                try:
                    signals = query_signals_agent(session, tenant_id, agent_id, brief)

                    # Generate variants (up to max_signals)
                    template_variants = generate_variants_from_signals(
                        session, template, signals[: template.max_signals], brief
                    )

                    variants.extend(template_variants)

                except Exception as e:
                    logger.error(f"Error querying signals agent {agent_id}: {e}", exc_info=True)
                    continue

        session.commit()

    return variants


def query_signals_agent(session, tenant_id: str, agent_id: str, brief: str) -> list[dict]:
    """Query a signals agent for matching signals using the signals registry.

    Args:
        session: Database session
        tenant_id: Tenant ID
        agent_id: Signals agent ID
        brief: Buyer's brief

    Returns:
        List of signal dicts from signals agent response
    """
    # Get signals agent from database
    stmt = select(SignalsAgent).filter_by(tenant_id=tenant_id, agent_id=agent_id, enabled=True)
    agent = session.scalars(stmt).first()

    if not agent:
        logger.warning(f"Signals agent {agent_id} not found or disabled")
        return []

    logger.info(f"Querying signals agent {agent.name} ({agent.agent_url}) with brief: {brief}")

    # Use signals registry to query the agent via MCP
    try:
        import asyncio

        from src.core.signals_agent_registry import (
            SignalsAgent as SignalsAgentDataclass,
        )
        from src.core.signals_agent_registry import SignalsAgentRegistry

        registry = SignalsAgentRegistry()

        # Parse auth credentials if present (same as registry does)
        auth = None
        if agent.auth_type and agent.auth_credentials:
            auth = {
                "type": agent.auth_type,
                "credentials": agent.auth_credentials,
            }

        # Convert database model to dataclass for registry
        agent_dataclass = SignalsAgentDataclass(
            agent_url=agent.agent_url,
            name=agent.name,
            enabled=agent.enabled,
            auth=auth,
            auth_header=agent.auth_header,
            timeout=agent.timeout or 30,
        )

        # Create async context and query specific agent
        # Note: This runs in a sync context, so we need to create an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            signals = loop.run_until_complete(
                registry._get_signals_from_agent(
                    agent=agent_dataclass,
                    brief=brief,
                    tenant_id=tenant_id,
                    principal_id=None,  # Optional - not needed for product discovery
                    context=None,  # Optional context
                )
            )
            logger.info(f"Received {len(signals)} signals from agent {agent.name}")
            return signals
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error querying signals agent {agent.name}: {e}", exc_info=True)
        return []


def generate_variants_from_signals(session, template: Product, signals: list[dict], brief: str) -> list[Product]:
    """Generate product variants from template and signals.

    Args:
        session: Database session
        template: Dynamic product template
        signals: List of signal dicts from signals agent
        brief: Buyer's brief (for variant customization)

    Returns:
        List of generated/updated Product variants
    """
    variants = []

    for signal in signals:
        try:
            # Extract activation key from signal
            activation_key = extract_activation_key(signal)
            if not activation_key:
                logger.warning(f"No activation key found for signal {signal.get('signal_agent_segment_id')}")
                continue

            # Generate variant ID (deterministic)
            variant_id = generate_variant_id(template.product_id, activation_key)

            # Check if variant already exists
            stmt = select(Product).filter_by(tenant_id=template.tenant_id, product_id=variant_id)
            existing = session.scalars(stmt).first()

            if existing:
                # Update existing variant
                existing.last_synced_at = datetime.now()  # type: ignore[assignment]
                # Extend expiration if still active
                ttl_days = template.variant_ttl_days or 30
                new_expiration = datetime.now() + timedelta(days=ttl_days)
                if not existing.expires_at or existing.expires_at < new_expiration:
                    existing.expires_at = new_expiration  # type: ignore[assignment]
                variants.append(existing)
                logger.debug(f"Updated existing variant {variant_id}")
                continue

            # Create new variant from template
            variant = create_variant_from_template(template, signal, activation_key, variant_id, brief)

            session.add(variant)
            variants.append(variant)

            logger.info(
                f"Created dynamic variant {variant_id} from template {template.product_id} "
                f"for signal {signal.get('signal_agent_segment_id')}"
            )

        except Exception as e:
            logger.error(f"Error generating variant from signal: {e}", exc_info=True)
            continue

    return variants


def extract_activation_key(signal: dict) -> dict | None:
    """Extract activation key from signal response.

    Args:
        signal: Signal dict from signals agent response

    Returns:
        Activation key dict or None if not found
    """
    # Look for activation key in deployments
    deployments = signal.get("deployments", [])

    for deployment in deployments:
        # Check if this deployment has an activation key and is live
        if deployment.get("is_live") and deployment.get("activation_key"):
            activation_key = deployment["activation_key"]

            # Validate activation key has required fields
            key_type = activation_key.get("type")
            if key_type == "key_value":
                if "key" in activation_key and "value" in activation_key:
                    return activation_key
            elif key_type == "segment_id":
                if "segment_id" in activation_key:
                    return activation_key

    return None


def generate_variant_id(template_id: str, activation_key: dict) -> str:
    """Generate deterministic variant ID from template and activation key.

    Args:
        template_id: Template product ID
        activation_key: Activation key dict

    Returns:
        Variant product ID
    """
    # Create deterministic hash from activation key
    if activation_key.get("type") == "key_value":
        hash_input = f"{activation_key['key']}:{activation_key['value']}"
    elif activation_key.get("type") == "segment_id":
        hash_input = f"segment:{activation_key['segment_id']}"
    else:
        hash_input = str(activation_key)

    hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]

    return f"{template_id}__variant_{hash_suffix}"


def create_variant_from_template(
    template: Product, signal: dict, activation_key: dict, variant_id: str, brief: str
) -> Product:
    """Create a new product variant from template.

    Args:
        template: Dynamic product template
        signal: Signal dict from signals agent
        activation_key: Activation key for targeting
        variant_id: Generated variant ID
        brief: Buyer's brief (for customization)

    Returns:
        New Product variant
    """
    # Copy ALL fields from template
    variant_data = {
        "tenant_id": template.tenant_id,
        "product_id": variant_id,
        "name": customize_name(template.name, signal, activation_key),
        "description": customize_description(template.description, signal, activation_key, brief),
        "formats": template.formats,
        "targeting_template": template.targeting_template,
        "delivery_type": template.delivery_type,
        "measurement": template.measurement,
        "creative_policy": template.creative_policy,
        "price_guidance": template.price_guidance,
        "is_custom": False,  # Variants are generated, not custom
        "countries": template.countries,
        "implementation_config": template.implementation_config,
        "properties": template.properties,
        "property_tags": template.property_tags,
        "delivery_measurement": template.delivery_measurement,
        "product_card": template.product_card,
        "product_card_detailed": template.product_card_detailed,
        "placements": template.placements,
        "reporting_capabilities": template.reporting_capabilities,
        # Variant-specific fields
        "is_dynamic": False,  # Variant is not a template
        "is_dynamic_variant": True,
        "parent_product_id": template.product_id,
        "activation_key": activation_key,
        "signal_metadata": {
            "signal_agent_segment_id": signal.get("signal_agent_segment_id"),
            "name": signal.get("name"),
            "description": signal.get("description"),
            "data_provider": signal.get("data_provider"),
            "coverage_percentage": signal.get("coverage_percentage"),
        },
        "last_synced_at": datetime.now(),
        # Expiration
        "expires_at": datetime.now() + timedelta(days=template.variant_ttl_days or 30),
    }

    return Product(**variant_data)


def customize_name(template_name: str, signal: dict, activation_key: dict) -> str:
    """Customize product name for variant.

    Args:
        template_name: Original template name
        signal: Signal dict
        activation_key: Activation key

    Returns:
        Customized name
    """
    # Simple approach: append signal name
    signal_name = signal.get("name", "")

    if signal_name:
        return f"{template_name} - {signal_name}"

    # Fallback: use activation key
    if activation_key.get("type") == "key_value":
        return f"{template_name} - {activation_key['key']}={activation_key['value']}"
    elif activation_key.get("type") == "segment_id":
        return f"{template_name} - Segment {activation_key['segment_id']}"

    return template_name


def customize_description(
    template_description: str | None, signal: dict, activation_key: dict, brief: str
) -> str | None:
    """Customize product description for variant.

    Args:
        template_description: Original template description
        signal: Signal dict
        activation_key: Activation key
        brief: Buyer's brief

    Returns:
        Customized description
    """
    if not template_description:
        # Generate description from signal if template has none
        signal_desc = signal.get("description", "")
        if signal_desc:
            return f"Targeting based on {signal.get('name', 'signal')}: {signal_desc}"
        return None

    # TODO: Use AI to customize description based on brief and signal
    # For now, just append signal info

    signal_info = []
    if signal.get("name"):
        signal_info.append(f"Signal: {signal['name']}")
    if signal.get("data_provider"):
        signal_info.append(f"Provider: {signal['data_provider']}")
    if signal.get("coverage_percentage"):
        signal_info.append(f"Coverage: {signal['coverage_percentage']}%")

    if signal_info:
        return f"{template_description}\n\n{' | '.join(signal_info)}"

    return template_description


def archive_expired_variants(tenant_id: str | None = None) -> int:
    """Archive expired dynamic product variants.

    Args:
        tenant_id: Optional tenant ID to limit archival

    Returns:
        Number of variants archived
    """
    archived_count = 0

    with get_db_session() as session:
        # Find expired variants
        stmt = select(Product).filter(
            Product.is_dynamic_variant, Product.archived_at.is_(None), Product.expires_at < datetime.now()
        )

        if tenant_id:
            stmt = stmt.filter_by(tenant_id=tenant_id)

        expired_variants = session.scalars(stmt).all()

        for variant in expired_variants:
            variant.archived_at = datetime.now()  # type: ignore[assignment]
            attributes.flag_modified(variant, "archived_at")
            archived_count += 1
            logger.info(f"Archived expired variant {variant.product_id}")

        session.commit()

    return archived_count
