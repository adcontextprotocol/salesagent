from typing import List, Dict, Any
from datetime import datetime, timedelta

from adapters.creative_engine import CreativeEngineAdapter
from schemas import CreativeAsset, AssetStatus

class MockCreativeEngine(CreativeEngineAdapter):
    """A mock creative engine that simulates a simple approval workflow."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.human_review_required = config.get("human_review_required", True)

    def process_assets(
        self,
        media_buy_id: str,
        assets: List[CreativeAsset]
    ) -> List[AssetStatus]:
        """Simulates processing assets, returning their status."""
        processed_assets = []
        for asset in assets:
            status = "pending_review" if self.human_review_required else "approved"
            estimated_approval = datetime.now().astimezone() + timedelta(days=2) if self.human_review_required else datetime.now().astimezone()
            
            processed_assets.append(
                AssetStatus(
                    creative_id=asset.creative_id,
                    status=status,
                    estimated_approval_time=estimated_approval
                )
            )
        return processed_assets
