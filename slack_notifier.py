"""
Slack notification system for AdCP Sales Agent.
Sends notifications for new tasks and approvals via Slack webhooks.
"""

import json
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Handles sending notifications to Slack channels via webhooks."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack notifier.
        
        Args:
            webhook_url: Slack webhook URL. If not provided, uses SLACK_WEBHOOK_URL env var.
        """
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        self.enabled = bool(self.webhook_url)
        
        if self.enabled:
            # Validate webhook URL format
            parsed = urlparse(self.webhook_url)
            if not all([parsed.scheme, parsed.netloc]):
                logger.error(f"Invalid Slack webhook URL format: {self.webhook_url}")
                self.enabled = False
        else:
            logger.info("Slack notifications disabled (no webhook URL configured)")
    
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
                    "text": f"Created at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
                    "text": f"Completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
                        "text": f"Submitted at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    }
                ]
            }
        ])
        
        fallback_text = f"New {format_type} creative from {principal_name} pending approval"
        
        return self.send_message(fallback_text, blocks)
    
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


# Global instance
slack_notifier = SlackNotifier()