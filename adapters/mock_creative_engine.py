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
        # Formats that can be auto-approved
        self.auto_approve_formats = set(config.get("auto_approve_formats", []))

    def process_creatives(self, creatives: List[Creative]) -> List[CreativeStatus]:
        """Simulates processing creatives, returning their status."""
        processed = []
        for creative in creatives:
            # Check if format is auto-approvable
            is_auto_approvable = creative.format_id in self.auto_approve_formats
            
            # Determine status based on format and configuration
            if is_auto_approvable and not self.human_review_required:
                status = "approved"
                detail = f"Creative auto-approved - format '{creative.format_id}' is in auto-approve list."
                est_approval = None
            elif is_auto_approvable and self.human_review_required:
                # Even with human review required, auto-approve formats bypass it
                status = "approved"
                detail = f"Creative auto-approved - format '{creative.format_id}' bypasses human review."
                est_approval = None
            else:
                # Requires human review
                status = "pending_review"
                detail = f"Awaiting manual review - format '{creative.format_id}' requires human approval."
                est_approval = datetime.now().astimezone() + timedelta(days=2)
            
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