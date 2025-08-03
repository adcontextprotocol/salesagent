"""
Slack notification system for AdCP Sales Agent.
Sends notifications for new tasks and approvals via Slack webhooks.
"""

import json
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Handles sending notifications to Slack channels via webhooks."""
    
    def __init__(self, webhook_url: Optional[str] = None, audit_webhook_url: Optional[str] = None, tenant_config: Optional[Dict[str, Any]] = None):
        """
        Initialize Slack notifier.
        
        Args:
            webhook_url: Slack webhook URL. If not provided, checks tenant config then SLACK_WEBHOOK_URL env var.
            audit_webhook_url: Separate webhook for audit logs. If not provided, checks tenant config then SLACK_AUDIT_WEBHOOK_URL env var.
            tenant_config: Tenant configuration dict to check for webhook URLs
        """
        # Only use tenant config - no fallback to env vars
        if tenant_config and tenant_config.get('features'):
            features = tenant_config['features']
            self.webhook_url = webhook_url or features.get('slack_webhook_url')
            self.audit_webhook_url = audit_webhook_url or features.get('slack_audit_webhook_url')
        else:
            # If no tenant config, disable Slack
            self.webhook_url = webhook_url
            self.audit_webhook_url = audit_webhook_url
            
        self.enabled = bool(self.webhook_url)
        self.audit_enabled = bool(self.audit_webhook_url)
        
        if self.enabled:
            # Validate webhook URL format
            parsed = urlparse(self.webhook_url)
            if not all([parsed.scheme, parsed.netloc]):
                logger.error(f"Invalid Slack webhook URL format: {self.webhook_url}")
                self.enabled = False
        else:
            logger.info("Slack notifications disabled (no webhook URL configured)")
            
        if self.audit_enabled:
            # Validate audit webhook URL format
            parsed = urlparse(self.audit_webhook_url)
            if not all([parsed.scheme, parsed.netloc]):
                logger.error(f"Invalid Slack audit webhook URL format: {self.audit_webhook_url}")
                self.audit_enabled = False
            else:
                logger.info("Slack audit logging enabled")
    
    def send_message(self, text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Send a message to Slack.
        
        Args:
            text: Plain text message (fallback for notifications)
            blocks: Rich Block Kit blocks for formatted messages
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    def notify_new_task(
        self,
        task_id: str,
        task_type: str,
        principal_name: str,
        media_buy_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        tenant_name: Optional[str] = None
    ) -> bool:
        """
        Send notification for a new task requiring approval.
        
        Args:
            task_id: Unique task identifier
            task_type: Type of task (e.g., 'create_media_buy', 'update_media_buy')
            principal_name: Name of the principal requesting the action
            media_buy_id: Associated media buy ID if applicable
            details: Additional task details
            tenant_name: Tenant/publisher name
            
        Returns:
            True if notification sent successfully
        """
        # Create formatted message with blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔔 New Task Requires Approval"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Task ID:*\n`{task_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:*\n{task_type.replace('_', ' ').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Principal:*\n{principal_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Tenant:*\n{tenant_name or 'Default'}"
                    }
                ]
            }
        ]
        
        # Add media buy info if available
        if media_buy_id:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Media Buy:* `{media_buy_id}`"
                }
            })
        
        # Add details if provided
        if details:
            detail_text = self._format_details(details)
            if detail_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{detail_text}"
                    }
                })
        
        # Add action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View in Admin UI"
                    },
                    "url": f"{os.getenv('ADMIN_UI_URL', 'http://localhost:8001')}/operations",
                    "style": "primary"
                }
            ]
        })
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Created at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        })
        
        # Fallback text for notifications
        fallback_text = (
            f"New task {task_id} ({task_type}) from {principal_name} requires approval"
        )
        
        return self.send_message(fallback_text, blocks)
    
    def notify_task_completed(
        self,
        task_id: str,
        task_type: str,
        completed_by: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Send notification when a task is completed.
        
        Args:
            task_id: Task identifier
            task_type: Type of task
            completed_by: User who completed the task
            success: Whether task completed successfully
            error_message: Error message if task failed
            
        Returns:
            True if notification sent successfully
        """
        emoji = "✅" if success else "❌"
        status = "Completed" if success else "Failed"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Task {status}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Task ID:*\n`{task_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:*\n{task_type.replace('_', ' ').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Completed By:*\n{completed_by}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{status}"
                    }
                ]
            }
        ]
        
        if error_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_message}```"
                }
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        })
        
        fallback_text = f"Task {task_id} {status.lower()} by {completed_by}"
        
        return self.send_message(fallback_text, blocks)
    
    def notify_creative_pending(
        self,
        creative_id: str,
        principal_name: str,
        format_type: str,
        media_buy_id: Optional[str] = None
    ) -> bool:
        """
        Send notification for a creative pending approval.
        
        Args:
            creative_id: Creative identifier
            principal_name: Principal who submitted the creative
            format_type: Creative format (e.g., 'video', 'display_300x250')
            media_buy_id: Associated media buy if applicable
            
        Returns:
            True if notification sent successfully
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🎨 New Creative Pending Approval"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Creative ID:*\n`{creative_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Format:*\n{format_type}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Principal:*\n{principal_name}"
                    }
                ]
            }
        ]
        
        if media_buy_id:
            blocks[1]["fields"].append({
                "type": "mrkdwn",
                "text": f"*Media Buy:*\n`{media_buy_id}`"
            })
        
        blocks.extend([
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Review Creative"
                        },
                        "url": f"{os.getenv('ADMIN_UI_URL', 'http://localhost:8001')}/operations#creatives",
                        "style": "primary"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Submitted at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    }
                ]
            }
        ])
        
        fallback_text = f"New {format_type} creative from {principal_name} pending approval"
        
        return self.send_message(fallback_text, blocks)
    
    def notify_audit_log(
        self,
        operation: str,
        principal_name: str,
        success: bool,
        adapter_id: str,
        tenant_name: Optional[str] = None,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        security_alert: bool = False
    ) -> bool:
        """
        Send audit log entry to Slack audit channel.
        
        Args:
            operation: Operation performed (e.g., 'create_media_buy', 'update_media_buy')
            principal_name: Principal who performed the operation
            success: Whether operation succeeded
            adapter_id: Adapter used for the operation
            tenant_name: Tenant/publisher name
            error_message: Error message if operation failed
            details: Additional operation details
            security_alert: Whether this is a security-related event
            
        Returns:
            True if notification sent successfully
        """
        if not self.audit_enabled:
            return False
        
        # Determine emoji and color based on event type
        if security_alert:
            emoji = "🚨"
            color = "danger"
            header_text = "Security Alert"
        elif not success:
            emoji = "❌"
            color = "danger"
            header_text = "Operation Failed"
        else:
            emoji = "📝"
            color = "good"
            header_text = "Audit Log"
        
        # Create message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {header_text}"
                }
            }
        ]
        
        # Add main info section
        fields = [
            {
                "type": "mrkdwn",
                "text": f"*Operation:*\n{operation}"
            },
            {
                "type": "mrkdwn",
                "text": f"*Principal:*\n{principal_name}"
            }
        ]
        
        if tenant_name:
            fields.append({
                "type": "mrkdwn",
                "text": f"*Tenant:*\n{tenant_name}"
            })
            
        fields.append({
            "type": "mrkdwn",
            "text": f"*Status:*\n{'✅ Success' if success else '❌ Failed'}"
        })
        
        blocks.append({
            "type": "section",
            "fields": fields
        })
        
        # Add error message if present
        if error_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_message}```"
                }
            })
        
        # Add details if present
        if details:
            detail_text = self._format_audit_details(details)
            if detail_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{detail_text}"
                    }
                })
        
        # Add color attachment for visual indicator
        attachments = [{
            "color": color,
            "blocks": blocks
        }]
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Logged at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | Adapter: {adapter_id}"
                }
            ]
        })
        
        # Fallback text
        fallback_text = f"{emoji} {operation} by {principal_name} - {'Success' if success else 'Failed'}"
        
        # Send to audit webhook
        payload = {
            "text": fallback_text,
            "attachments": attachments
        }
        
        try:
            response = requests.post(
                self.audit_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack audit notification: {e}")
            return False
    
    def _format_details(self, details: Dict[str, Any]) -> str:
        """Format task details for Slack message."""
        formatted_parts = []
        
        # Common fields to highlight
        highlight_fields = [
            'budget', 'daily_budget', 'total_budget',
            'start_date', 'end_date', 'flight_start_date', 'flight_end_date',
            'targeting_overlay', 'performance_goal'
        ]
        
        for field in highlight_fields:
            if field in details:
                value = details[field]
                if 'budget' in field and isinstance(value, (int, float)):
                    value = f"${value:,.2f}"
                elif 'date' in field:
                    value = str(value)
                field_name = field.replace('_', ' ').title()
                formatted_parts.append(f"• {field_name}: {value}")
        
        return "\n".join(formatted_parts) if formatted_parts else None
    
    def _format_audit_details(self, details: Dict[str, Any]) -> str:
        """Format audit details for Slack message."""
        formatted_parts = []
        
        # Important audit fields
        important_fields = [
            'media_buy_id', 'creative_id', 'task_id',
            'budget', 'total_budget', 'daily_budget',
            'action', 'resolution', 'package_id'
        ]
        
        for field in important_fields:
            if field in details:
                value = details[field]
                if 'budget' in field and isinstance(value, (int, float)):
                    value = f"${value:,.2f}"
                field_name = field.replace('_', ' ').title()
                formatted_parts.append(f"• {field_name}: `{value}`")
        
        # Add any custom fields not in the important list
        for field, value in details.items():
            if field not in important_fields and not field.startswith('_'):
                field_name = field.replace('_', ' ').title()
                formatted_parts.append(f"• {field_name}: {value}")
        
        return "\n".join(formatted_parts[:5]) if formatted_parts else None  # Limit to 5 items


# Global instance (will be overridden per-tenant in actual usage)
slack_notifier = SlackNotifier()

def get_slack_notifier(tenant_config: Optional[Dict[str, Any]] = None) -> SlackNotifier:
    """Get a Slack notifier instance configured for the specific tenant."""
    return SlackNotifier(tenant_config=tenant_config)