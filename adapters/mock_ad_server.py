import sqlite3
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

    def __init__(self, config: Dict[str, Any], creative_engine: Optional[CreativeEngineAdapter] = None):
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
        
        conn = sqlite3.connect('adcp.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        final_packages = []
        for pkg in proposal.media_packages:
            if pkg.package_id in accepted_packages:
                placement_id = int(pkg.package_id.split('_')[1])
                cursor.execute("SELECT daily_impression_capacity FROM placements WHERE id = ?", (placement_id,))
                result = cursor.fetchone()
                capacity = result['daily_impression_capacity'] if result else 100000 # Default if not found
                
                pkg_dump = pkg.model_dump()
                pkg_dump['daily_impression_capacity'] = capacity
                final_packages.append(pkg_dump)
        
        conn.close()

        self._media_buys[media_buy_id] = {
            "media_buy_id": media_buy_id,
            "status": "pending_creative",
            "billing_entity": billing_entity,
            "po_number": po_number,
            "accepted_packages": accepted_packages,
            "creatives": [],
            "start_time": proposal.start_time,
            "end_time": proposal.end_time,
            "total_budget": sum(pkg['budget'] for pkg in final_packages),
            "media_packages": final_packages
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
            asset_with_status = {"data": asset_data, "status": "pending_processing"}
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

        if media_buy["status"] == "pending_approval":
            assets_to_process = [c['data'] for c in media_buy['creatives'] if c['status'] == 'pending_processing']
            if assets_to_process and self.creative_engine:
                processed_statuses = self.creative_engine.process_assets(media_buy_id, assets_to_process)
                for p_status in processed_statuses:
                    for c in media_buy['creatives']:
                        if c['data']['creative_id'] == p_status.creative_id:
                            c['status'] = p_status.status
            
            all_approved = all(c['status'] == 'approved' for c in media_buy['creatives'])
            if all_approved:
                 media_buy["status"] = "ready"
            else:
                return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="pending_approval")

        if today < start_dt:
            return CheckMediaBuyStatusResponse(media_buy_id=media_buy_id, status="ready")

        package_data = self._get_package_delivery_status(media_buy, today)
        total_spend = sum(p['spend'] for p in package_data)
        total_impressions = sum(p['impressions'] for p in package_data)
        
        overall_status = "completed" if today > media_buy['end_time'] else "live"

        return CheckMediaBuyStatusResponse(
            media_buy_id=media_buy_id,
            status=overall_status,
            delivery=Delivery(spend=total_spend, impressions=total_impressions, pacing="on_track"),
            packages=[PackageStatus(**pkg) for pkg in package_data],
            last_updated=today
        )

    def _get_package_delivery_status(self, media_buy: Dict[str, Any], today: datetime) -> list:
        start_date = media_buy['start_time']
        end_date = media_buy['end_time']
        reporting_date = today - timedelta(days=1)

        if reporting_date < start_date: return []
        if reporting_date > end_date: reporting_date = end_date
            
        days_elapsed = (reporting_date - start_date).days + 1
        package_delivery = []

        for package in media_buy['media_packages']:
            total_impressions = 0
            for _ in range(days_elapsed):
                capacity = package.get('daily_impression_capacity', 0)
                delivered_impressions = int(capacity * random.uniform(0.85, 1.0))
                total_impressions += delivered_impressions

            spend = (total_impressions / 1000) * package['cpm']
            
            package_delivery.append({
                "package_id": package['package_id'],
                "status": "live" if today <= end_date else "completed",
                "spend": round(spend, 2),
                "impressions": total_impressions,
                "pacing": "on_track"
            })
        return package_delivery
        
    # --- Other methods remain the same ---
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