"""Business Activity Service - Shows meaningful business events.

This service generates activity feed items focused on business-relevant events:
- Product inquiries (searches, recommendations)
- Media buy lifecycle (created, approved, launched, completed)
- Actions needed (approvals, creative reviews)
- Performance alerts (underdelivering, budget concerns)

NOT raw audit logs of every API call.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from src.core.database.database_session import get_db_session
from src.core.database.models import AuditLog, Creative, MediaBuy, Principal, WorkflowStep

logger = logging.getLogger(__name__)


def get_business_activities(tenant_id: str, limit: int = 50) -> list[dict]:
    """Get business-relevant activities for the dashboard.

    Returns activities that matter for business operations:
    - Product searches
    - Media buys created/updated
    - Workflows requiring action
    - Performance milestones

    Args:
        tenant_id: The tenant to get activities for
        limit: Maximum number of activities to return

    Returns:
        List of activity dictionaries with:
        - type: Type of activity (product_search, media_buy, action_needed, etc.)
        - title: Short summary
        - description: Detailed description
        - principal_name: Who did it
        - timestamp: When it happened
        - action_required: Whether user action is needed
        - metadata: Additional context (IDs, amounts, etc.)
    """
    activities = []

    try:
        with get_db_session() as db:
            # 1. Product Searches (last 24 hours)
            yesterday = datetime.now(UTC) - timedelta(days=1)
            product_searches = (
                db.query(AuditLog)
                .filter(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.operation == "AdCP.get_products",
                    AuditLog.timestamp >= yesterday,
                    AuditLog.success,
                )
                .order_by(AuditLog.timestamp.desc())
                .limit(10)
                .all()
            )

            for search in product_searches:
                details = json.loads(search.details) if search.details else {}
                product_count = details.get("product_count", 0)
                brief = details.get("brief", "products")

                activities.append(
                    {
                        "type": "product_search",
                        "title": f"{search.principal_name or 'Advertiser'} searched for {brief}",
                        "description": f"Found {product_count} matching products",
                        "principal_name": search.principal_name or "System",
                        "timestamp": search.timestamp,
                        "action_required": False,
                        "metadata": {"product_count": product_count, "brief": brief},
                    }
                )

            # 2. Media Buys (created/updated in last 7 days)
            week_ago = datetime.now(UTC) - timedelta(days=7)
            recent_buys = (
                db.query(MediaBuy)
                .join(Principal, MediaBuy.principal_id == Principal.principal_id)
                .filter(MediaBuy.tenant_id == tenant_id, MediaBuy.created_at >= week_ago)
                .order_by(MediaBuy.created_at.desc())
                .limit(20)
                .all()
            )

            for buy in recent_buys:
                principal = db.query(Principal).filter_by(principal_id=buy.principal_id).first()
                principal_name = principal.name if principal else "Unknown"

                # Determine activity based on status
                if buy.status == "pending":
                    title = f"{principal_name} created campaign (awaiting approval)"
                    action_required = True
                elif buy.status == "active":
                    title = f"{principal_name}'s campaign is live"
                    action_required = False
                elif buy.status == "completed":
                    title = f"{principal_name}'s campaign completed"
                    action_required = False
                else:
                    title = f"{principal_name} created campaign"
                    action_required = False

                activities.append(
                    {
                        "type": "media_buy",
                        "title": title,
                        "description": f"${buy.budget:,.0f} budget • {buy.start_date} to {buy.end_date}",
                        "principal_name": principal_name,
                        "timestamp": buy.created_at,
                        "action_required": action_required,
                        "metadata": {
                            "media_buy_id": buy.media_buy_id,
                            "budget": buy.budget,
                            "status": buy.status,
                            "start_date": str(buy.start_date),
                            "end_date": str(buy.end_date),
                        },
                    }
                )

            # 3. Workflow Steps Requiring Action
            from src.core.database.models import Context

            pending_workflows = (
                db.query(WorkflowStep)
                .join(Context, WorkflowStep.context_id == Context.context_id)
                .filter(Context.tenant_id == tenant_id, WorkflowStep.status == "requires_approval")
                .order_by(WorkflowStep.created_at.desc())
                .limit(10)
                .all()
            )

            for step in pending_workflows:
                activities.append(
                    {
                        "type": "action_needed",
                        "title": f"Action needed: {step.step_type}",
                        "description": "Workflow requires your approval",
                        "principal_name": "System",
                        "timestamp": step.created_at,
                        "action_required": True,
                        "metadata": {
                            "workflow_id": step.workflow_id,
                            "step_id": step.step_id,
                            "step_type": step.step_type,
                        },
                    }
                )

            # 4. Creatives Needing Review
            pending_creatives = (
                db.query(Creative)
                .filter(Creative.tenant_id == tenant_id, Creative.status == "pending_review")
                .order_by(Creative.created_at.desc())
                .limit(5)
                .all()
            )

            for creative in pending_creatives:
                principal = db.query(Principal).filter_by(principal_id=creative.principal_id).first()
                principal_name = principal.name if principal else "Unknown"

                activities.append(
                    {
                        "type": "creative_review",
                        "title": f"{principal_name} uploaded creative",
                        "description": f"Format: {creative.format} • Awaiting review",
                        "principal_name": principal_name,
                        "timestamp": creative.created_at,
                        "action_required": True,
                        "metadata": {"creative_id": creative.creative_id, "format": creative.format},
                    }
                )

    except Exception as e:
        logger.error(f"Error getting business activities for tenant {tenant_id}: {e}", exc_info=True)
        return []

    # Sort all activities by timestamp (newest first)
    activities.sort(key=lambda x: x["timestamp"], reverse=True)

    # Add relative time formatting
    now = datetime.now(UTC)
    for activity in activities[:limit]:
        timestamp = activity["timestamp"]
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        delta = now - timestamp
        if delta.days > 0:
            activity["time_relative"] = f"{delta.days}d ago"
        elif delta.seconds > 3600:
            activity["time_relative"] = f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            activity["time_relative"] = f"{delta.seconds // 60}m ago"
        else:
            activity["time_relative"] = "Just now"

    return activities[:limit]
