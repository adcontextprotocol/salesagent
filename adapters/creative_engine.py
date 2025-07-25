from abc import ABC, abstractmethod
from typing import List, Dict, Any
from schemas import CreativeAsset

class CreativeEngineAdapter(ABC):
    """Abstract base class for creative engine adapters."""

    @abstractmethod
    def process_assets(
        self,
        media_buy_id: str,
        assets: List[CreativeAsset]
    ) -> List[Dict[str, Any]]:
        """Processes creative assets, returning their status."""
        pass
