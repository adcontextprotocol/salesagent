from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import random

from adapters.base import AdServerAdapter
from schemas import *

class MockAdServer(AdServerAdapter):
    """
    A mock ad server that simulates the lifecycle of a media buy.
    It conforms to the AdServerAdapter interface.
    """
    _media_buys: Dict[str, Dict[str, Any]] = {}

    def create_media_buy(self, request: CreateMediaBuyRequest, packages: List[MediaPackage], start_time: datetime, end_time: datetime) -> CreateMediaBuyResponse:
        """Simulates the creation of a media buy."""
        media_buy_id = f"buy_{request.po_number}"
        
        total_budget = sum(p.cpm for p in packages if p.delivery_type == 'guaranteed')
        # In a real scenario, non-guaranteed budget would be handled differently
        
        self._media_buys[media_buy_id] = {
            "id": media_buy_id,
            "po_number": request.po_number,
            "billing_entity": request.billing_entity,
            "packages": [p.model_dump() for p in packages],
            "total_budget": total_budget,
            "start_time": start_time,
            "end_time": end_time,
            "creatives": []
        }
        
        return CreateMediaBuyResponse(
            media_buy_id=media_buy_id,
            status="pending_creative",
            creative_deadline=datetime.now() + timedelta(days=2)
        )

    def add_creative_assets(self, media_buy_id: str, assets: List[Dict[str, Any]], today: datetime) -> List[AssetStatus]:
        """Simulates adding creatives and returns an 'approved' status."""
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy {media_buy_id} not found.")
        
        self._media_buys[media_buy_id]["creatives"].extend(assets)
        
        return [AssetStatus(creative_id=asset['id'], status="approved") for asset in assets]

    def check_media_buy_status(self, media_buy_id: str, today: datetime) -> CheckMediaBuyStatusResponse:
        """Simulates checking the status of a media buy."""
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy {media_buy_id} not found.")
        
        buy = self._media_buys[media_buy_id]
        start_date = buy['start_time']
        end_date = buy['end_time']

        if today < start_date:
            status = "pending_start"
        elif today > end_date:
            status = "completed"
        else:
            status = "delivering"
            
        return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status=status)

    def get_media_buy_delivery(self, media_buy_id: str, date_range: ReportingPeriod, today: datetime) -> GetMediaBuyDeliveryResponse:
        """Simulates getting delivery data for a media buy."""
        # This is a simplified simulation. A real one would be more complex.
        return GetMediaBuyDeliveryResponse(
            media_buy_id=media_buy_id,
            reporting_period=date_range,
            totals=DeliveryTotals(impressions=10000, spend=100.0, clicks=100, video_completions=5000),
            by_package=[],
            currency="USD"
        )

    def update_media_buy_performance_index(self, media_buy_id: str, package_performance: List[PackagePerformance]) -> bool:
        return True

    def update_media_buy(self, media_buy_id: str, action: str, package_id: Optional[str], budget: Optional[int], today: datetime) -> UpdateMediaBuyResponse:
        return UpdateMediaBuyResponse(status="accepted")
