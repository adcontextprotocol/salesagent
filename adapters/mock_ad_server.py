from datetime import datetime, timedelta
import random
from typing import List, Dict, Any, Optional

from adapters.base import AdServerAdapter, CreativeEngineAdapter
from schemas import (
    AcceptProposalResponse, CheckMediaBuyStatusResponse, GetMediaBuyDeliveryResponse,
    UpdateMediaBuyResponse, Proposal, ReportingPeriod, PackagePerformance,
    AssetStatus, Delivery, PackageStatus, DeliveryTotals, CreativeAsset
)

class MockAdServer(AdServerAdapter):
    """
    A mock ad server that simulates the entire media buy lifecycle.
    It manages the state of media buys in-memory and orchestrates creative approval.
    """
    _media_buys: Dict[str, Any] = {}

    def __init__(self, config: Dict[str, Any], creative_engine: CreativeEngineAdapter):
        super().__init__(config, creative_engine)

    def accept_proposal(
        self,
        proposal: Proposal,
        accepted_packages: List[str],
        billing_entity: str,
        po_number: str,
        today: datetime
    ) -> AcceptProposalResponse:
        media_buy_id = f"buy_{po_number.lower().replace(' ', '_')}"
        final_packages = [pkg for pkg in proposal.media_packages if pkg.package_id in accepted_packages]

        self._media_buys[media_buy_id] = {
            "media_buy_id": media_buy_id,
            "status": "pending_creative",
            "billing_entity": billing_entity,
            "po_number": po_number,
            "accepted_packages": accepted_packages,
            "creatives": [], # This will store the asset dicts with their statuses
            "start_time": proposal.start_time,
            "end_time": proposal.end_time,
            "total_budget": sum(pkg.budget for pkg in final_packages),
            "media_packages": [pkg.model_dump() for pkg in final_packages]
        }

        creative_deadline = max(proposal.start_time - timedelta(days=5), today)
        return AcceptProposalResponse(
            media_buy_id=media_buy_id,
            status="pending_creative",
            creative_deadline=creative_deadline
        )

    def add_creative_assets(
        self,
        media_buy_id: str,
        assets: List[Dict[str, Any]],
        today: datetime
    ) -> List[AssetStatus]:
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
        
        media_buy = self._media_buys[media_buy_id]
        initial_statuses = []
        for asset_data in assets:
            # Store the full asset data along with an initial processing status
            asset_with_status = {
                "data": asset_data,
                "status": "pending_processing" # Initial state before creative engine review
            }
            media_buy["creatives"].append(asset_with_status)
            initial_statuses.append(AssetStatus(creative_id=asset_data['creative_id'], status="submitted"))

        media_buy["status"] = "pending_approval"
        return initial_statuses

    def check_media_buy_status(
        self,
        media_buy_id: str,
        today: datetime
    ) -> CheckMediaBuyStatusResponse:
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")

        media_buy = self._media_buys[media_buy_id]
        start_dt = media_buy['start_time']

        # --- Creative Approval Workflow ---
        if media_buy["status"] == "pending_approval":
            assets_to_process = [
                CreativeAsset(**c['data']) for c in media_buy['creatives'] if c['status'] == 'pending_processing'
            ]
            if assets_to_process and self.creative_engine:
                processed_statuses = self.creative_engine.process_assets(media_buy_id, assets_to_process)
                # Update the status in our media_buy state
                for p_status in processed_statuses:
                    for c in media_buy['creatives']:
                        if c['data']['creative_id'] == p_status.creative_id:
                            c['status'] = p_status.status
                            c['estimated_approval_time'] = p_status.estimated_approval_time
            
            # Check if all creatives are now approved
            all_approved = all(c['status'] == 'approved' for c in media_buy['creatives'])
            if all_approved:
                 media_buy["status"] = "ready"
            else:
                # Return a pending status if still waiting for approvals
                return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="pending_approval")

        if today < start_dt:
            return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="ready")

        # --- Delivery Reporting ---
        delivery_data = self._get_delivery_status(media_buy, today)
        package_data = self._get_package_delivery_status(media_buy, today)

        return CheckMediaBuyStatusResponse(
            media_buy_id=media_buy_id,
            status=delivery_data['status'],
            delivery=Delivery(**delivery_data),
            packages=[PackageStatus(**pkg) for pkg in package_data],
            last_updated=today
        )
    
    # ... (The rest of the methods remain largely the same)
    def get_media_buy_delivery(
        self,
        media_buy_id: str,
        date_range: ReportingPeriod,
        today: datetime
    ) -> GetMediaBuyDeliveryResponse:
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
        
        media_buy = self._media_buys[media_buy_id]
        package_delivery = self._get_package_delivery_status(media_buy, today)
        total_spend = sum(p['spend'] for p in package_delivery)
        total_impressions = sum(p['impressions'] for p in package_delivery)

        return GetMediaBuyDeliveryResponse(
            media_buy_id=media_buy_id,
            reporting_period=date_range,
            totals=DeliveryTotals(
                impressions=total_impressions,
                spend=total_spend,
                clicks=int(total_impressions * 0.01),
                video_completions=int(total_impressions * 0.7)
            ),
            by_package=package_delivery,
            currency="USD"
        )

    def update_media_buy_performance_index(
        self,
        media_buy_id: str,
        package_performance: List[PackagePerformance]
    ) -> bool:
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
        
        media_buy = self._media_buys[media_buy_id]
        for perf in package_performance:
            for pkg in media_buy["media_packages"]:
                if pkg["package_id"] == perf.package_id:
                    pkg["performance_index"] = perf.performance_index
                    break
        return True

    def update_media_buy(
        self,
        media_buy_id: str,
        action: str,
        package_id: Optional[str],
        budget: Optional[int],
        today: datetime
    ) -> UpdateMediaBuyResponse:
        if media_buy_id not in self._media_buys:
            raise ValueError(f"Media buy with ID '{media_buy_id}' not found.")
        
        media_buy = self._media_buys[media_buy_id]
        
        if action == "change_package_budget" and package_id and budget is not None:
            for pkg in media_buy["media_packages"]:
                if pkg["package_id"] == package_id:
                    pkg["budget"] = budget
                    break
            media_buy["total_budget"] = sum(pkg["budget"] for pkg in media_buy["media_packages"])
        else:
            raise ValueError(f"Action '{action}' not supported by this mock server.")

        return UpdateMediaBuyResponse(
            status="accepted",
            implementation_date=today + timedelta(days=1)
        )

    def _get_delivery_status(self, media_buy: Dict[str, Any], today: datetime) -> dict:
        start_date = media_buy['start_time']
        end_date = media_buy['end_time']
        total_budget = media_buy['total_budget']
        total_days = (end_date - start_date).days
        daily_budget = total_budget / total_days if total_days > 0 else total_budget

        reporting_date = today - timedelta(days=1)
        if reporting_date < start_date:
            return {"status": "live", "spend": 0, "impressions": 0, "pacing": "on_track"}
        if reporting_date > end_date:
            reporting_date = end_date
        
        days_elapsed = (reporting_date - start_date).days + 1
        
        total_spend = sum(daily_budget * random.uniform(0.5, 1.0) for _ in range(days_elapsed))
        
        avg_cpm = sum(pkg['cpm'] for pkg in media_buy['media_packages']) / len(media_buy['media_packages'])
        impressions = int((total_spend / avg_cpm) * 1000) if avg_cpm > 0 else 0

        return {
            "status": "live" if today <= end_date else "completed",
            "spend": round(total_spend, 2),
            "impressions": impressions,
            "pacing": "on_track"
        }

    def _get_package_delivery_status(self, media_buy: Dict[str, Any], today: datetime) -> list:
        start_date = media_buy['start_time']
        end_date = media_buy['end_time']
        reporting_date = today - timedelta(days=1)

        if reporting_date < start_date:
            return []
        if reporting_date > end_date:
            reporting_date = end_date
            
        days_elapsed = (reporting_date - start_date).days + 1
        package_delivery = []

        for package in media_buy['media_packages']:
            package_total_days = (end_date - start_date).days
            package_daily_budget = package['budget'] / package_total_days if package_total_days > 0 else package['budget']
            
            package_spend = sum(package_daily_budget * random.uniform(0.5, 1.0) for _ in range(days_elapsed))
            package_impressions = int((package_spend / package['cpm']) * 1000) if package['cpm'] > 0 else 0
            
            package_delivery.append({
                "package_id": package['package_id'],
                "status": "live" if today <= end_date else "completed",
                "spend": round(package_spend, 2),
                "impressions": package_impressions,
                "pacing": "on_track"
            })
        return package_delivery
