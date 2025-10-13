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

from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import AuditLog

logger = logging.getLogger(__name__)


def get_business_activities(tenant_id: str, limit: int = 50) -> list[dict]:
    """Get all audit log activities for the dashboard.

    Shows ALL operations from audit logs, allowing users to see real-time activity.
    Users can filter on the frontend if needed.

    Args:
        tenant_id: The tenant to get activities for
        limit: Maximum number of activities to return

    Returns:
        List of activity dictionaries with:
        - type: Type of activity (derived from operation name)
        - title: Short summary
        - description: Detailed description
        - principal_name: Who did it
        - timestamp: When it happened
        - action_required: Whether user action is needed
        - metadata: Additional context from audit log details
    """
    activities = []

    try:
        with get_db_session() as db:
            # Get ALL recent audit logs (last 7 days) - no filtering by operation
            week_ago = datetime.now(UTC) - timedelta(days=7)
            stmt = (
                select(AuditLog)
                .filter(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.timestamp >= week_ago,
                )
                .order_by(AuditLog.timestamp.desc())
                .limit(limit * 2)  # Get more than we need in case we filter some out
            )
            recent_logs = db.scalars(stmt).all()

            for log in recent_logs:
                # Parse details if available
                details = {}
                if log.details:
                    try:
                        if isinstance(log.details, str):
                            details = json.loads(log.details)
                        elif isinstance(log.details, dict):
                            details = log.details
                    except (json.JSONDecodeError, TypeError):
                        details = {}

                # Determine activity type based on operation
                operation = log.operation or "unknown"
                if operation.startswith("A2A."):
                    activity_type = "a2a"
                    icon = "📡"
                elif operation.startswith("AdCP."):
                    activity_type = "adcp"
                    icon = "🔌"
                elif operation.startswith("MCP."):
                    activity_type = "mcp"
                    icon = "🔗"
                else:
                    activity_type = "system"
                    icon = "⚙️"

                # Build title from operation
                operation_clean = operation.replace("AdCP.", "").replace("A2A.", "").replace("MCP.", "")
                principal_name = log.principal_name or "System"

                # Create descriptive title based on operation
                # Skip successful policy checks - only show failures
                if "policy_check" in operation and log.success:
                    continue

                # Handle explicit skill invocation with rich context
                if "explicit_skill_invocation" in operation:
                    skills = details.get("skills", [])
                    if not skills:
                        continue  # Skip if no skill info

                    # Extract the primary skill (first one)
                    primary_skill = skills[0] if skills else "unknown"

                    # Make it human-readable based on skill name
                    if "create_media_buy" in primary_skill:
                        # Try to extract meaningful info from details
                        budget = details.get("total_budget", details.get("budget"))
                        packages = details.get("packages", details.get("package_count"))

                        if budget and packages:
                            title = f"{principal_name} created media buy with {packages} packages for ${budget:,.0f}"
                        elif budget:
                            title = f"{principal_name} created media buy for ${budget:,.0f}"
                        elif packages:
                            title = f"{principal_name} created media buy with {packages} packages"
                        else:
                            title = f"{principal_name} created media buy"
                    elif "get_products" in primary_skill or "list_products" in primary_skill:
                        count = details.get("product_count", details.get("count"))
                        if count:
                            title = f"{principal_name} searched for products (found {count})"
                        else:
                            title = f"{principal_name} searched for products"
                    elif "sync_creatives" in primary_skill or "upload_creative" in primary_skill:
                        count = details.get("creative_count", details.get("count"))
                        if count:
                            title = f"{principal_name} uploaded {count} creative(s)"
                        else:
                            title = f"{principal_name} uploaded creative"
                    elif "get_media_buy_delivery" in primary_skill:
                        buy_id = details.get("media_buy_id", "")
                        if buy_id:
                            title = f"{principal_name} checked delivery for {buy_id}"
                        else:
                            title = f"{principal_name} checked media buy delivery"
                    else:
                        # Generic skill invocation
                        skill_clean = primary_skill.replace("_", " ").title()
                        title = f"{principal_name} called {skill_clean}"

                elif "get_products" in operation or "list_products" in operation:
                    title = f"{principal_name} searched for products"
                elif "create_media_buy" in operation:
                    title = f"{principal_name} created media buy"
                elif "upload_creative" in operation or "sync_creative" in operation:
                    title = f"{principal_name} uploaded creative"
                elif "policy_check" in operation and not log.success:
                    # Only show failed policy checks
                    title = f"{principal_name} policy check failed"
                elif "list_creatives" in operation:
                    title = f"{principal_name} listed creatives"
                else:
                    title = f"{principal_name}: {operation_clean}"

                # Build description
                if log.success:
                    status_text = "✓ Success"
                    badge_type = "success"
                else:
                    status_text = f"✗ Failed: {log.error_message or 'Unknown error'}"
                    badge_type = "error"

                # Extract key details for description
                description_parts = [status_text]
                if details.get("product_count"):
                    description_parts.append(f"{details['product_count']} products")
                if details.get("media_buy_id"):
                    description_parts.append(f"Buy: {details['media_buy_id']}")
                if details.get("creative_id"):
                    description_parts.append(f"Creative: {details['creative_id']}")
                if details.get("total_budget"):
                    description_parts.append(f"Budget: ${details['total_budget']:,.0f}")

                description = " • ".join(description_parts)

                # Build links to related objects
                links = []
                if details.get("media_buy_id"):
                    links.append(
                        {
                            "text": f"View Media Buy {details['media_buy_id']}",
                            "url": f"/tenant/{tenant_id}/media-buy/{details['media_buy_id']}",
                            "icon": "💰",
                        }
                    )
                if details.get("creative_id"):
                    links.append(
                        {
                            "text": f"View Creative {details['creative_id']}",
                            "url": f"/tenant/{tenant_id}/creative/{details['creative_id']}",
                            "icon": "🎨",
                        }
                    )

                # Always add link to full audit log in workflows
                links.append(
                    {
                        "text": "View in Audit Log",
                        "url": f"/tenant/{tenant_id}/workflows#audit-logs",
                        "icon": "📋",
                    }
                )

                activities.append(
                    {
                        "type": activity_type,
                        "title": title,
                        "description": description,
                        "principal_name": principal_name,
                        "timestamp": log.timestamp,
                        "action_required": False,  # Will add workflow support later
                        "metadata": {
                            "operation": operation,
                            "success": log.success,
                            "details": details,
                        },
                        "links": links,
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
