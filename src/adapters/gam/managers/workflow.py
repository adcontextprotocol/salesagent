"""
GAM Workflow Manager - Human-in-the-Loop Workflow Management

This module handles workflow step creation, notification, and management
for Google Ad Manager operations requiring human intervention.

REFACTORED: Now uses shared workflow helpers to eliminate duplication.
"""

import logging
from datetime import datetime
from typing import Any

from src.core.config_loader import get_tenant_config
from src.core.schemas import CreateMediaBuyRequest, MediaPackage

logger = logging.getLogger(__name__)


class GAMWorkflowManager:
    """Manages Human-in-the-Loop workflows for Google Ad Manager operations."""

    def __init__(self, tenant_id: str, principal=None, audit_logger=None, log_func=None):
        """Initialize workflow manager.

        Args:
            tenant_id: Tenant identifier for configuration
            principal: Principal object for context creation
            audit_logger: Audit logging instance
            log_func: Logging function for output
        """
        self.tenant_id = tenant_id
        self.principal = principal
        self.audit_logger = audit_logger
        self.log = log_func or logger.info

    def create_activation_workflow_step(self, media_buy_id: str, packages: list[MediaPackage]) -> str | None:
        """Creates a workflow step for human approval of order activation.

        Args:
            media_buy_id: The GAM order ID awaiting activation
            packages: List of packages in the media buy for context

        Returns:
            str: The workflow step ID if created successfully, None otherwise
        """
        # Lazy import to avoid circular dependencies
        from src.core.helpers.workflow_helpers import (
            build_activation_action_details,
            create_workflow_step,
        )

        # Build action details using shared helper
        action_details = build_activation_action_details(media_buy_id, packages)

        # Create workflow step using unified helper
        step_id = create_workflow_step(
            tenant_id=self.tenant_id,
            principal_id=self.principal.principal_id,
            step_type="approval",
            tool_name="activate_gam_order",
            request_data=action_details,
            status="approval",
            owner="publisher",
            media_buy_id=media_buy_id,
            action="activate",
            transaction_details={"gam_order_id": media_buy_id},
            log_func=self.log,
            audit_logger=self.audit_logger,
        )

        if step_id:
            # Send Slack notification if configured
            self._send_workflow_notification(step_id, action_details)

        return step_id

    def create_manual_order_workflow_step(
        self,
        request: CreateMediaBuyRequest,
        packages: list[MediaPackage],
        start_time: datetime,
        end_time: datetime,
        media_buy_id: str,
    ) -> str | None:
        """Creates a workflow step for manual creation of GAM order (manual mode).

        Args:
            request: The original media buy request
            packages: List of packages to be created
            start_time: Campaign start time
            end_time: Campaign end time
            media_buy_id: Generated media buy ID for tracking

        Returns:
            str: The workflow step ID if created successfully, None otherwise
        """
        # Lazy import to avoid circular dependencies
        from src.core.helpers.media_buy_helpers import build_order_name
        from src.core.helpers.workflow_helpers import (
            build_manual_creation_action_details,
            create_workflow_step,
        )

        order_name = build_order_name(
            request=request,
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            tenant_id=self.tenant_id,
            adapter_type="gam",
        )

        # Build action details using shared helper
        action_details = build_manual_creation_action_details(
            request=request,
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            media_buy_id=media_buy_id,
            order_name=order_name,
        )

        # Create workflow step using unified helper
        step_id = create_workflow_step(
            tenant_id=self.tenant_id,
            principal_id=self.principal.principal_id,
            step_type="creation",
            tool_name="create_gam_order",
            request_data=action_details,
            status="approval",
            owner="publisher",
            media_buy_id=media_buy_id,
            action="create",
            transaction_details={"campaign_name": order_name},
            log_func=self.log,
            audit_logger=self.audit_logger,
        )

        if step_id:
            # Send Slack notification if configured
            self._send_workflow_notification(step_id, action_details)

        return step_id

    def create_approval_workflow_step(self, media_buy_id: str, approval_type: str = "creative_approval") -> str | None:
        """Creates a workflow step for human approval of creative assets.

        Args:
            media_buy_id: The GAM order ID requiring approval
            approval_type: Type of approval needed

        Returns:
            str: The workflow step ID if created successfully, None otherwise
        """
        # Lazy import to avoid circular dependencies
        from src.core.helpers.workflow_helpers import (
            build_approval_action_details,
            create_workflow_step,
        )

        # Build action details using shared helper
        action_details = build_approval_action_details(media_buy_id, approval_type)

        # Create workflow step using unified helper
        step_id = create_workflow_step(
            tenant_id=self.tenant_id,
            principal_id=self.principal.principal_id,
            step_type="approval",
            tool_name=approval_type,
            request_data=action_details,
            status="approval",
            owner="publisher",
            media_buy_id=media_buy_id,
            action="approve",
            transaction_details={"gam_order_id": media_buy_id},
            log_func=self.log,
            audit_logger=self.audit_logger,
        )

        if step_id:
            # Send Slack notification if configured
            self._send_workflow_notification(step_id, action_details)

        return step_id

    def create_approval_polling_workflow_step(
        self, media_buy_id: str, packages: list[MediaPackage], operation: str = "order_approval"
    ) -> str | None:
        """Creates a workflow step for background approval polling (NO_FORECAST_YET).

        This workflow step tracks background polling of GAM order approval status.
        When forecasting is ready, the order will be automatically approved and
        a webhook notification will be sent.

        Args:
            media_buy_id: The GAM order ID awaiting approval
            packages: List of packages in the media buy for context
            operation: Type of approval operation (e.g., "order_approval")

        Returns:
            str: The workflow step ID if created successfully, None otherwise
        """
        # Lazy import to avoid circular dependencies
        from src.core.helpers.workflow_helpers import (
            build_background_polling_action_details,
            create_workflow_step,
        )

        # Build action details using shared helper
        action_details = build_background_polling_action_details(media_buy_id, packages, operation)

        # Create workflow step using unified helper
        step_id = create_workflow_step(
            tenant_id=self.tenant_id,
            principal_id=self.principal.principal_id,
            step_type="background_task",
            tool_name=operation,
            request_data=action_details,
            status="working",
            owner="system",
            media_buy_id=media_buy_id,
            action="approve",
            assigned_to="background_approval_service",
            transaction_details={"gam_order_id": media_buy_id, "polling_started": datetime.now().isoformat()},
            log_func=self.log,
            audit_logger=self.audit_logger,
        )

        if step_id:
            # Send Slack notification if configured
            self._send_workflow_notification(step_id, action_details)

        return step_id

    def _send_workflow_notification(self, step_id: str, action_details: dict[str, Any]) -> None:
        """Send Slack notification for workflow step if configured.

        Args:
            step_id: The workflow step ID
            action_details: Details about the workflow step
        """
        try:
            tenant_config = get_tenant_config(self.tenant_id)
            slack_webhook_url = tenant_config.get("slack", {}).get("webhook_url")

            if not slack_webhook_url:
                self.log("[yellow]No Slack webhook configured - skipping notification[/yellow]")
                return

            import requests

            action_type = action_details.get("action_type", "workflow_step")
            automation_mode = action_details.get("automation_mode", "unknown")

            if action_type == "create_gam_order":
                title = "🔨 Manual GAM Order Creation Required"
                color = "#FF9500"  # Orange
                description = "Manual mode activated - human intervention needed to create GAM order"
            elif action_type == "activate_gam_order":
                title = "✅ GAM Order Activation Approval Required"
                color = "#FFD700"  # Gold
                description = "Order created successfully - approval needed for activation"
            else:
                title = "🔔 Workflow Step Requires Attention"
                color = "#36A2EB"  # Blue
                description = f"Workflow step {step_id} needs human intervention"

            # Build Slack message
            slack_payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": title,
                        "text": description,
                        "fields": [
                            {"title": "Step ID", "value": step_id, "short": True},
                            {
                                "title": "Automation Mode",
                                "value": automation_mode.replace("_", " ").title(),
                                "short": True,
                            },
                            {
                                "title": "Action Required",
                                "value": action_details.get("instructions", ["Check admin dashboard"])[0],
                                "short": False,
                            },
                        ],
                        "footer": "AdCP Sales Agent",
                        "ts": int(datetime.now().timestamp()),
                    }
                ]
            }

            # Send notification
            response = requests.post(
                slack_webhook_url,
                json=slack_payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.log(f"✓ Sent Slack notification for workflow step {step_id}")
                if self.audit_logger:
                    self.audit_logger.log_success(f"Sent Slack notification for workflow step: {step_id}")
            else:
                self.log(f"[yellow]Slack notification failed with status {response.status_code}[/yellow]")

        except Exception as e:
            self.log(f"[yellow]Failed to send Slack notification: {str(e)}[/yellow]")
            # Don't fail the workflow creation if notification fails
