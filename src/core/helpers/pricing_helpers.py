"""Pricing option helper utilities.

Handles the RootModel wrapper pattern used by adcp 2.14.0+ for discriminated unions.
"""

from typing import Any


def pricing_option_has_rate(pricing_option: Any) -> bool:
    """Check if a pricing option has a rate value.

    Handles multiple formats:
    - Dict format (from JSON/serialization): checks po["rate"]
    - Pydantic RootModel wrapper (adcp 2.14.0+): checks po.root.rate
    - Direct attribute access (SQLAlchemy models): checks po.rate

    Args:
        pricing_option: A pricing option in any supported format

    Returns:
        True if the pricing option has a non-None rate value
    """
    # Dict format (JSON/serialization)
    if isinstance(pricing_option, dict):
        return pricing_option.get("rate") is not None

    # Try RootModel wrapper first (adcp 2.14.0+ Pydantic models)
    root = getattr(pricing_option, "root", None)
    if root is not None:
        return getattr(root, "rate", None) is not None

    # Direct attribute (SQLAlchemy models or plain objects)
    return getattr(pricing_option, "rate", None) is not None
