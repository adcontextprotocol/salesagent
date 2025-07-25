from abc import ABC, abstractmethod
from typing import List, Dict, Any
from schemas import Creative, CreativeStatus

class CreativeEngineAdapter(ABC):
    """Abstract base class for creative engine adapters."""

    @abstractmethod
    def process_creatives(
        self,
        creatives: List[Creative]
    ) -> List[CreativeStatus]:
        """Processes creative assets, returning their status."""
        pass
