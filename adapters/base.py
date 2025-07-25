from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from schemas import AcceptProposalResponse, CheckMediaBuyStatusResponse, GetMediaBuyDeliveryResponse, UpdateMediaBuyResponse, Proposal, ReportingPeriod, PackagePerformance

class AdServerAdapter(ABC):
    """Abstract base class for ad server adapters."""

    @abstractmethod
    def accept_proposal(
        self,
        proposal: Proposal,
        accepted_packages: List[str],
        billing_entity: str,
        po_number: str,
        today: datetime
    ) -> AcceptProposalResponse:
        """Converts an accepted proposal into a media buy on the ad server."""
        pass

    @abstractmethod
    def add_creative_assets(
        self,
        media_buy_id: str,
        assets: List[Dict[str, Any]],
        today: datetime
    ) -> List[Dict[str, Any]]:
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
