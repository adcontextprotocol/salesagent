from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from schemas import *

class CreativeEngineAdapter(ABC):
    """Abstract base class for creative engine adapters."""
    @abstractmethod
    def process_assets(self, media_buy_id: str, assets: List[Dict[str, Any]]) -> List[AssetStatus]:
        pass

class AdServerAdapter(ABC):
    """Abstract base class for ad server adapters."""

    def __init__(self, config: Dict[str, Any], creative_engine: Optional[CreativeEngineAdapter] = None):
        self.config = config
        self.creative_engine = creative_engine

    @abstractmethod
    def create_media_buy(
        self,
        request: CreateMediaBuyRequest,
        packages: List[MediaPackage],
        start_time: datetime,
        end_time: datetime
    ) -> CreateMediaBuyResponse:
        """Creates a new media buy on the ad server from selected packages."""
        pass

    @abstractmethod
    def add_creative_assets(
        self,
        media_buy_id: str,
        assets: List[Dict[str, Any]],
        today: datetime
    ) -> List[AssetStatus]:
        """Adds creative assets to an existing media buy."""
        pass

    @abstractmethod
    def check_media_buy_status(
        self,
        media_buy_id: str,
        today: datetime
    ) -> CheckMediaBuyStatusResponse:
        """Checks the status of a media buy on the ad server."""
        pass

    @abstractmethod
    def get_media_buy_delivery(
        self,
        media_buy_id: str,
        date_range: ReportingPeriod,
        today: datetime
    ) -> GetMediaBuyDeliveryResponse:
        """Gets delivery data for a media buy."""
        pass

    @abstractmethod
    def update_media_buy_performance_index(
        self,
        media_buy_id: str,
        package_performance: List[PackagePerformance]
    ) -> bool:
        """Updates the performance index for packages in a media buy."""
        pass

    @abstractmethod
    def update_media_buy(
        self,
        media_buy_id: str,
        action: str,
        package_id: Optional[str],
        budget: Optional[int],
        today: datetime
    ) -> UpdateMediaBuyResponse:
        """Updates a media buy with a specific action."""
        pass