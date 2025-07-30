from .gam import GAMAdapter
from .kevel import KevelAdapter
from .triton import TritonAdapter
from .creative_engine import CreativeEngineAdapter
from .xandr import XandrAdapter
from .base import AdServerAdapter

# Map of adapter type strings to adapter classes
ADAPTER_REGISTRY = {
    'gam': GAMAdapter,
    'google_ad_manager': GAMAdapter,
    'kevel': KevelAdapter,
    'triton': TritonAdapter,
    'creative_engine': CreativeEngineAdapter,
    'xandr': XandrAdapter,
    'microsoft_monetize': XandrAdapter
}

def get_adapter(adapter_type: str, config: dict, principal):
    """Factory function to get the appropriate adapter instance."""
    adapter_class = ADAPTER_REGISTRY.get(adapter_type.lower())
    if not adapter_class:
        raise ValueError(f"Unknown adapter type: {adapter_type}")
    return adapter_class(config, principal)