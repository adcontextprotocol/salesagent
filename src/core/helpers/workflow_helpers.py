"""
Shared Workflow Helpers - Single Source of Truth

This module consolidates workflow creation functions to eliminate duplication
across GAM workflow manager and other adapters.

Replaces 4 separate workflow functions with unified logic.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from src.core.database.database_session import get_db_session
from src.core.database.models import Context, ObjectWorkflowMapping, WorkflowStep
from src.core.schemas import CreateMediaBuyRequest, MediaPackage

logger = logging.getLogger(__name__)


def create_workflow_step(
    tenant_id: str,
    principal_id: str,
    step_type: str,
    tool_name: str,
    request_data: dict[str, Any],
    status: str,
    owner: str,
    media_buy_id: str,
    action: str,
    assigned_to: str | None = None,
    transaction_details: dict[str, Any] | None = None,
    log_func=None,
    audit_logger=None,
) -> str | None:
    """Create a workflow step with object mapping.

    Unified workflow creation function that replaces:
    - create_activation_workflow_step
    - create_manual_order_workflow_step
    - create_approval_workflow_step
    - create_approval_polling_workflow_step

    Args:
        tenant_id: Tenant identifier
        principal_id: Principal identifier
        step_type: Type of workflow step ("approval", "creation", "background_task")
        tool_name: Tool/operation name
        request_data: Action details and instructions
        status: Workflow step status ("approval", "working", "completed")
        owner: Owner of the workflow step ("publisher", "system")
        media_buy_id: Media buy/order ID
        action: Action type for object mapping ("create", "activate", "approve")
        assigned_to: Optional assignee
        transaction_details: Optional transaction details
        log_func: Optional logging function
        audit_logger: Optional audit logger

    Returns:
        Workflow step ID if successful, None otherwise
    """
    # Generate step ID with appropriate prefix
    prefix_map = {
        "creation": "c",  # Manual creation
        "approval": "a",  # Activation/approval
        "background_task": "b",  # Background polling
    }
    prefix = prefix_map.get(step_type, "p")  # Default to "p" for general approval
    step_id = f"{prefix}{uuid.uuid4().hex[:5]}"  # 6 chars total

    try:
        with get_db_session() as db_session:
            # Create a context for this workflow
            context_id = f"ctx_{uuid.uuid4().hex[:12]}"
            context = Context(
                context_id=context_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
            )
            db_session.add(context)

            # Create workflow step
            workflow_step = WorkflowStep(
                step_id=step_id,
                context_id=context_id,
                step_type=step_type,
                tool_name=tool_name,
                request_data=request_data,
                status=status,
                owner=owner,
                assigned_to=assigned_to,
                transaction_details=transaction_details or {},
            )
            db_session.add(workflow_step)

            # Create object mapping to link this step with the media buy
            object_mapping = ObjectWorkflowMapping(
                object_type="media_buy",
                object_id=media_buy_id,
                step_id=step_id,
                action=action,
            )
            db_session.add(object_mapping)

            db_session.commit()

            # Log success
            if log_func:
                log_func(f"✓ Created workflow step {step_id} ({step_type}: {tool_name})")
            if audit_logger:
                audit_logger.log_success(f"Created {step_type} workflow step: {step_id}")

            return step_id

    except Exception as e:
        error_msg = f"Failed to create {step_type} workflow step for {media_buy_id}: {str(e)}"
        if log_func:
            log_func(f"[red]Error: {error_msg}[/red]")
        if audit_logger:
            audit_logger.log_warning(error_msg)
        logger.error(error_msg)
        return None


def build_activation_action_details(
    media_buy_id: str,
    packages: list[MediaPackage],
) -> dict[str, Any]:
    """Build action details for activation workflow (GAM order activation).

    Args:
        media_buy_id: GAM order ID
        packages: List of packages for context

    Returns:
        Action details dictionary
    """
    return {
        "action_type": "activate_gam_order",
        "order_id": media_buy_id,
        "platform": "Google Ad Manager",
        "automation_mode": "confirmation_required",
        "instructions": [
            f"Review GAM Order {media_buy_id} in your GAM account",
            "Verify line item settings, targeting, and creative placeholders are correct",
            "Confirm budget, flight dates, and delivery settings are acceptable",
            "Check that ad units and placements are properly targeted",
            "Once verified, approve this task to automatically activate the order and line items",
        ],
        "gam_order_url": f"https://admanager.google.com/orders/{media_buy_id}",
        "packages": [{"name": pkg.name, "impressions": pkg.impressions, "cpm": pkg.cpm} for pkg in packages],
        "next_action_after_approval": "automatic_activation",
    }


def build_manual_creation_action_details(
    request: CreateMediaBuyRequest,
    packages: list[MediaPackage],
    start_time: datetime,
    end_time: datetime,
    media_buy_id: str,
    order_name: str,
) -> dict[str, Any]:
    """Build action details for manual creation workflow (manual order creation).

    Args:
        request: Create media buy request
        packages: List of packages
        start_time: Campaign start time
        end_time: Campaign end time
        media_buy_id: Generated media buy ID
        order_name: Generated order name

    Returns:
        Action details dictionary
    """
    # Calculate total budget from package budgets (AdCP v2.2.0)
    total_budget_amount = request.get_total_budget()

    return {
        "action_type": "create_gam_order",
        "order_id": media_buy_id,
        "platform": "Google Ad Manager",
        "automation_mode": "manual_creation_required",
        "campaign_name": order_name,
        "total_budget": total_budget_amount,
        "flight_start": start_time.isoformat(),
        "flight_end": end_time.isoformat(),
        "instructions": [
            "Navigate to Google Ad Manager and create a new order",
            f"Set order name to: {order_name}",
            f"Set total budget to: ${total_budget_amount:,.2f}",
            f"Set flight dates: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}",
            "Create line items for each package according to the specifications below",
            "Once order is created, update this workflow with the GAM order ID",
        ],
        "packages": [
            {
                "name": pkg.name,
                "impressions": pkg.impressions,
                "cpm": pkg.cpm,
                "total_budget": (pkg.impressions / 1000) * pkg.cpm,
                "targeting": pkg.targeting_overlay.model_dump() if pkg.targeting_overlay else {},
            }
            for pkg in packages
        ],
        "gam_network_url": "https://admanager.google.com/",
        "next_action_after_creation": "order_id_update_required",
    }


def build_approval_action_details(
    media_buy_id: str,
    approval_type: str = "creative_approval",
) -> dict[str, Any]:
    """Build action details for general approval workflow.

    Args:
        media_buy_id: GAM order ID
        approval_type: Type of approval needed

    Returns:
        Action details dictionary
    """
    return {
        "action_type": approval_type,
        "order_id": media_buy_id,
        "platform": "Google Ad Manager",
        "automation_mode": "approval_required",
        "instructions": [
            f"Review {approval_type.replace('_', ' ')} for GAM Order {media_buy_id}",
            "Check that all requirements are met",
            "Approve this task to proceed with the operation",
        ],
        "gam_order_url": f"https://admanager.google.com/orders/{media_buy_id}",
        "next_action_after_approval": "automatic_processing",
    }


def build_background_polling_action_details(
    media_buy_id: str,
    packages: list[MediaPackage],
    operation: str = "order_approval",
) -> dict[str, Any]:
    """Build action details for background polling workflow (NO_FORECAST_YET).

    Args:
        media_buy_id: GAM order ID
        packages: List of packages for context
        operation: Type of approval operation

    Returns:
        Action details dictionary
    """
    return {
        "action_type": operation,
        "order_id": media_buy_id,
        "platform": "Google Ad Manager",
        "automation_mode": "background_polling",
        "status": "working",
        "instructions": [
            "GAM order approval is pending - forecasting not ready yet",
            "Background task is polling GAM for forecasting completion",
            "Order will be automatically approved when forecasting is ready",
            "Webhook notification will be sent when approval completes",
        ],
        "gam_order_url": f"https://admanager.google.com/orders/{media_buy_id}",
        "packages": [{"name": pkg.name, "impressions": pkg.impressions, "cpm": pkg.cpm} for pkg in packages],
        "next_action": "automatic_approval_when_ready",
        "polling_interval_seconds": 30,
        "max_polling_duration_minutes": 15,
    }
