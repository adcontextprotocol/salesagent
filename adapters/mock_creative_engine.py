from typing import List, Dict, Any
from datetime import datetime, timedelta

from adapters.creative_engine import CreativeEngineAdapter
from schemas import Creative, CreativeStatus, AdaptCreativeRequest

class MockCreativeEngine(CreativeEngineAdapter):
    """A mock creative engine that simulates a simple approval and adaptation workflow."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.human_review_required = config.get("human_review_required", True)
        self.adaptation_time_days = config.get("adaptation_time_days", 3)

    def process_creatives(self, creatives: List[Creative]) -> List[CreativeStatus]:
        """Simulates processing creatives, returning their status."""
        processed = []
        for creative in creatives:
            status = "pending_review" if self.human_review_required else "approved"
            detail = "Awaiting manual review from creative team." if self.human_review_required else "Creative auto-approved by system."
            est_approval = datetime.now().astimezone() + timedelta(days=2) if self.human_review_required else datetime.now().astimezone()
            
            processed.append(
                CreativeStatus(
                    creative_id=creative.creative_id,
                    status=status,
                    detail=detail,
                    estimated_approval_time=est_approval
                )
            )
        return processed

    def adapt_creative(self, request: AdaptCreativeRequest) -> CreativeStatus:
        """Simulates adapting a creative to a new format."""
        # In a real system, this would involve complex logic, possibly another AI call.
        # Here, we just approve it after a simulated delay.
        return CreativeStatus(
            creative_id=request.new_creative_id,
            status="pending_review",
            detail=f"Adaptation from {request.original_creative_id} to {request.target_format_id} is in progress.",
            estimated_approval_time=datetime.now().astimezone() + timedelta(days=self.adaptation_time_days)
        )