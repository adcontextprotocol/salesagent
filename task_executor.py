"""
Task Executor - Core business logic layer shared by both MCP and A2A protocols.

This module contains all the actual task/tool implementation logic, completely
protocol-agnostic. Both MCP and A2A servers will call into this layer.
"""

import json
import uuid
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from schemas import *
from schemas import Principal  # Explicit import for clarity

logger = logging.getLogger(__name__)
from config_loader import get_current_tenant, get_tenant_config
from db_config import get_db_connection
from adapters.mock_ad_server import MockAdServer as MockAdServerAdapter
from adapters.google_ad_manager import GoogleAdManager
from adapters.kevel import Kevel
from adapters.triton_digital import TritonDigital
from adapters.mock_creative_engine import MockCreativeEngine
from product_catalog_providers.factory import get_product_catalog_provider
from policy_check_service import PolicyCheckService, PolicyStatus
from slack_notifier import get_slack_notifier
from audit_logger import AuditLogger


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResult:
    """Result of a task execution."""
    def __init__(self, 
                 status: TaskStatus,
                 message: str,
                 data: Optional[Dict[str, Any]] = None,
                 error: Optional[str] = None,
                 task_id: Optional[str] = None):
        self.status = status
        self.message = message
        self.data = data or {}
        self.error = error
        self.task_id = task_id or str(uuid.uuid4())
        self.timestamp = datetime.utcnow()


class TaskExecutor:
    """
    Core task executor that implements all ADCP business logic.
    Protocol-agnostic implementation that can be used by both MCP and A2A.
    """
    
    def __init__(self):
        self.media_buys: Dict[str, Tuple[CreateMediaBuyRequest, str]] = {}
        self.creative_statuses: Dict[str, CreativeStatusField] = {}
        self.creative_library: Dict[str, Creative] = {}
        self.creative_groups: Dict[str, CreativeGroup] = {}
        self.human_tasks: Dict[str, Dict] = {}
        self.tenant_id = None  # Will be set during authentication
        self.audit_logger = AuditLogger("task_executor")
        self.policy_service = PolicyCheckService()
        # Import context manager
        from context_manager import ContextManager
        self.context_manager = ContextManager()
        
    def authenticate(self, token: str, tenant_id: str) -> Optional[str]:
        """Authenticate a token and return principal_id."""
        # Store tenant_id for later use
        self.tenant_id = tenant_id
        # Also update the audit logger's tenant_id
        self.audit_logger.tenant_id = tenant_id
        
        # First check if it's a principal token
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT principal_id FROM principals WHERE access_token = ? AND tenant_id = ?", 
            (token, tenant_id)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        
        # Then check if it's an admin token for the tenant
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT admin_token FROM tenants WHERE tenant_id = ?",
            (tenant_id,)
        )
        tenant_result = cursor.fetchone()
        conn.close()
        
        if tenant_result and tenant_result[0] == token:
            return f"{tenant_id}_admin"
        
        return None
    
    def get_adapter(self, principal_id: str) -> Any:
        """Get the appropriate ad server adapter for a principal."""
        tenant = get_current_tenant()
        if not tenant:
            raise ValueError("No tenant context set")
        
        # Get principal's platform mappings
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT platform_mappings FROM principals WHERE principal_id = ? AND tenant_id = ?",
            (principal_id, tenant['tenant_id'])
        )
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise ValueError(f"Principal {principal_id} not found")
        
        platform_mappings = json.loads(result[0]) if result[0] else {}
        
        # Create principal object
        principal = Principal(
            principal_id=principal_id,
            name=principal_id,  # Could fetch actual name if needed
            platform_mappings=platform_mappings
        )
        
        # Get adapter based on tenant config
        ad_server = tenant.get('ad_server', 'mock')
        adapter_config = tenant.get('adapters', {}).get(ad_server, {})
        
        if ad_server == 'google_ad_manager':
            return GoogleAdManager(config=adapter_config, principal=principal, tenant_id=tenant['tenant_id'])
        elif ad_server == 'kevel':
            return Kevel(config=adapter_config, principal=principal, tenant_id=tenant['tenant_id'])
        elif ad_server == 'triton_digital':
            return TritonDigital(config=adapter_config, principal=principal, tenant_id=tenant['tenant_id'])
        else:
            return MockAdServerAdapter(config=adapter_config, principal=principal, tenant_id=tenant['tenant_id'])
    
    # --- Product Discovery Tasks ---
    
    async def get_products(self, 
                          principal_id: str,
                          brief: Optional[str] = None,
                          countries: Optional[List[str]] = None,
                          formats: Optional[List[str]] = None,
                          targeting_features: Optional[List[str]] = None,
                          promoted_offering: Optional[str] = None,
                          context_id: Optional[str] = None,
                          protocol: str = "a2a") -> TaskResult:
        """Get available products based on filters."""
        try:
            tenant = get_current_tenant()
            if not tenant:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="No tenant context",
                    error="Tenant not found"
                )
            
            # Get or create context with error handling
            try:
                context_id = self.context_manager.get_or_create_context(
                    context_id=context_id,
                    tenant_id=tenant['tenant_id'],
                    principal_id=principal_id,
                    protocol=protocol
                )
            except Exception as e:
                # Log error but continue with a temporary context
                self.audit_logger.log_warning(f"Failed to manage context: {e}")
                context_id = f"tmp_{uuid.uuid4().hex[:8]}"
            
            # Save request to context with error handling
            try:
                self.context_manager.save_message(
                    context_id=context_id,
                    message_type="request",
                    method="get_products",
                    request_data={
                        "brief": brief,
                        "countries": countries,
                        "formats": formats,
                        "targeting_features": targeting_features,
                        "promoted_offering": promoted_offering
                    },
                    response_data=None
                )
            except Exception as e:
                # Log error but continue - don't fail the whole operation
                self.audit_logger.log_warning(f"Failed to save request to context: {e}")
            
            # Get the product catalog provider
            # Build tenant config from individual fields
            tenant_config = {
                'product_catalog': {
                    'provider': 'database',  # Default to database provider
                    'config': {}
                }
            }
            provider = await get_product_catalog_provider(tenant['tenant_id'], tenant_config)
            
            # Get products from provider using the new interface
            # Note: database provider currently ignores the brief
            products = await provider.get_products(
                brief=brief or "",
                tenant_id=tenant['tenant_id'],
                principal_id=principal_id,
                context={
                    'countries': countries,
                    'formats': formats,
                    'targeting_features': targeting_features,
                    'promoted_offering': promoted_offering
                }
            )
            
            # Check if clarification is needed
            if brief and not products:
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    message="I couldn't find products matching your brief. Could you provide more details about your advertising goals?",
                    data={
                        "products": [],
                        "clarification_needed": True,
                        "context_id": None
                    }
                )
            
            # Add policy compliance check
            policy_status = PolicyStatus.ALLOWED
            if promoted_offering:
                policy_result = self.policy_service.check_compliance(promoted_offering)
                policy_status = policy_result.status
            
            # Prepare response data
            response_data = {
                "products": [p.model_dump() for p in products],
                "context_id": context_id,
                "policy_compliance": {
                    "status": policy_status.value,
                    "details": None
                }
            }
            
            # Save response to context with error handling
            try:
                self.context_manager.save_message(
                    context_id=context_id,
                    message_type="response",
                    method="get_products",
                    request_data=None,
                    response_data=response_data
                )
            except Exception as e:
                self.audit_logger.log_warning(f"Failed to save response to context: {e}")
            
            # Update context state with discovered products
            try:
                self.context_manager.update_context_state(
                    context_id=context_id,
                    state={
                        "last_products_shown": [p.product_id for p in products],
                        "last_brief": brief
                    }
                )
            except Exception as e:
                self.audit_logger.log_warning(f"Failed to update context state: {e}")
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Found {len(products)} products matching your criteria",
                data=response_data
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to get products",
                error=str(e)
            )
    
    async def get_signals(self,
                         principal_id: str,
                         query: Optional[str] = None,
                         type: Optional[str] = None,
                         category: Optional[str] = None) -> TaskResult:
        """Get available signals for targeting."""
        try:
            # Mock implementation - would connect to real signal provider
            signals = []
            
            # Add sample signals based on query
            if query:
                if "sports" in query.lower():
                    signals.extend([
                        {
                            "signal_id": "sports_content",
                            "name": "Sports Content Context",
                            "type": "contextual",
                            "description": "Pages with sports-related content"
                        },
                        {
                            "signal_id": "sports_fans_2025",
                            "name": "Sports Fans Q1 2025",
                            "type": "audience",
                            "description": "Users interested in sports"
                        }
                    ])
                if "auto" in query.lower():
                    signals.append({
                        "signal_id": "auto_intenders_q1_2025",
                        "name": "Auto Intenders Q1 2025",
                        "type": "audience",
                        "description": "Users researching vehicle purchases"
                    })
            
            # Filter by type if specified
            if type:
                signals = [s for s in signals if s.get("type") == type]
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Found {len(signals)} available signals",
                data={
                    "signals": signals,
                    "context_id": f"sig_{uuid.uuid4().hex[:8]}"
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to get signals",
                error=str(e)
            )
    
    # --- Media Buy Creation Tasks ---
    
    def create_media_buy(self,
                        principal_id: str,
                        product_ids: List[str],
                        total_budget: float,
                        flight_start_date: str,
                        flight_end_date: str,
                        targeting_overlay: Optional[Dict] = None,
                        promoted_offering: Optional[str] = None) -> TaskResult:
        """Create a new media buy."""
        try:
            # Policy compliance check
            policy_status = PolicyStatus.ALLOWED
            if promoted_offering:
                policy_result = self.policy_service.check_compliance(promoted_offering)
                policy_status = policy_result.status
                
                if policy_status == PolicyStatus.REJECTED:
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        message="Media buy creation blocked due to policy violation",
                        error=f"Policy violation: {policy_result.details}",
                        data={
                            "policy_compliance": {
                                "status": policy_status.value,
                                "details": policy_result.details
                            }
                        }
                    )
            
            # Create the media buy
            media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"
            
            # Ensure targeting_overlay is a Targeting object
            from schemas import Targeting
            if targeting_overlay is None:
                targeting_overlay = Targeting()  # Empty targeting
            elif isinstance(targeting_overlay, dict):
                targeting_overlay = Targeting(**targeting_overlay)
                
            request = CreateMediaBuyRequest(
                product_ids=product_ids,
                total_budget=total_budget,
                flight_start_date=flight_start_date,
                flight_end_date=flight_end_date,
                targeting_overlay=targeting_overlay
            )
            
            self.media_buys[media_buy_id] = (request, principal_id)
            
            # Also persist to database
            tenant = get_current_tenant()
            conn = get_db_connection()
            try:
                # Convert targeting_overlay to dict for JSON storage
                targeting_dict = targeting_overlay.model_dump() if targeting_overlay else {}
                
                cursor = conn.connection.cursor() if hasattr(conn, 'connection') else conn.cursor()
                cursor.execute("""
                    INSERT INTO media_buys (
                        media_buy_id, tenant_id, principal_id, 
                        order_name, advertiser_name,
                        budget, start_date, end_date,
                        status, raw_request
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    media_buy_id,
                    tenant['tenant_id'],
                    principal_id,
                    f"Media Buy {media_buy_id}",  # Default order name
                    principal_id,  # Using principal_id as advertiser name for now
                    total_budget,
                    flight_start_date,
                    flight_end_date,
                    "pending_approval",
                    json.dumps({
                        "product_ids": product_ids,
                        "total_budget": total_budget,
                        "flight_start_date": str(flight_start_date),
                        "flight_end_date": str(flight_end_date),
                        "targeting_overlay": targeting_dict,
                        "promoted_offering": promoted_offering
                    })
                ))
                conn.connection.commit() if hasattr(conn, 'connection') else conn.commit()
            except Exception as e:
                self.audit_logger.log_warning(f"Failed to persist media buy to database: {e}")
                # Continue - don't fail the whole operation
            finally:
                conn.close()
            
            # Get adapter and create in ad server
            adapter = self.get_adapter(principal_id)
            
            # Determine if this needs manual approval
            tenant = get_current_tenant()
            needs_approval = tenant.get('human_review_required', False)
            
            if needs_approval:
                # Create human task for approval
                task_id = f"task_{uuid.uuid4().hex[:8]}"
                self.human_tasks[task_id] = {
                    "task_id": task_id,
                    "type": "media_buy_approval",
                    "media_buy_id": media_buy_id,
                    "status": "pending",
                    "created_at": datetime.utcnow(),
                    "details": {
                        "budget": total_budget,
                        "products": product_ids
                    }
                }
                
                status = "pending_approval"
                message = "Media buy created and pending approval"
            else:
                # Auto-approve
                status = "active"
                message = "Media buy created successfully"
            
            # Log the action
            self.audit_logger.log_operation(
                operation="create_media_buy",
                principal_name=principal_id,  # Using principal_id as name for now
                principal_id=principal_id,
                adapter_id="",  # No adapter ID in this context
                success=True,
                details={"media_buy_id": media_buy_id, "budget": total_budget}
            )
            
            # Notify via Slack if configured (disabled for now - method not implemented)
            # notifier = get_slack_notifier()
            # if notifier:
            #     notifier.notify_media_buy_created(
            #         media_buy_id,
            #         principal_id,
            #         total_budget,
            #         product_ids
            #     )
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=message,
                data={
                    "media_buy_id": media_buy_id,
                    "status": status,
                    "context_id": f"ctx_{uuid.uuid4().hex[:8]}",
                    "policy_compliance": {
                        "status": policy_status.value,
                        "details": None if policy_status == PolicyStatus.ALLOWED else "Manual review required"
                    }
                }
            )
            
        except Exception as e:
            self.audit_logger.log_operation(
                operation="create_media_buy",
                principal_name=principal_id,
                principal_id=principal_id,
                adapter_id="",
                success=False,
                error=str(e)
            )
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to create media buy",
                error=str(e)
            )
    
    # --- Creative Management Tasks ---
    
    def submit_creatives(self,
                        principal_id: str,
                        media_buy_id: str,
                        creatives: List[Dict]) -> TaskResult:
        """Submit creatives for a media buy."""
        try:
            if media_buy_id not in self.media_buys:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Media buy not found",
                    error=f"Media buy {media_buy_id} does not exist"
                )
            
            buy_request, buy_principal = self.media_buys[media_buy_id]
            if buy_principal != principal_id:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Unauthorized",
                    error="You don't have access to this media buy"
                )
            
            creative_ids = []
            tenant = get_current_tenant()
            auto_approve_formats = tenant.get('auto_approve_formats', [])
            
            for creative_data in creatives:
                creative_id = f"cr_{uuid.uuid4().hex[:8]}"
                
                # Determine if auto-approve
                format_id = creative_data.get('format', 'unknown')
                if format_id in auto_approve_formats:
                    status = "approved"
                else:
                    status = "pending_review"
                
                self.creative_statuses[creative_id] = CreativeStatusField(
                    creative_id=creative_id,
                    status=status,
                    feedback=None if status == "approved" else "Awaiting manual review"
                )
                
                creative_ids.append(creative_id)
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Submitted {len(creative_ids)} creatives",
                data={
                    "creative_ids": creative_ids,
                    "context_id": f"ctx_{uuid.uuid4().hex[:8]}"
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to submit creatives",
                error=str(e)
            )
    
    # --- Media Buy Management Tasks ---
    
    def get_media_buy_status(self,
                            principal_id: str,
                            media_buy_id: str) -> TaskResult:
        """Get the status of a media buy."""
        try:
            # Check in-memory first
            if media_buy_id in self.media_buys:
                request, owner_principal_id = self.media_buys[media_buy_id]
                
                # Check authorization
                if principal_id != owner_principal_id:
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        message="Unauthorized",
                        error="You don't have access to this media buy"
                    )
                
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    message="Media buy status retrieved",
                    data={
                        "media_buy_id": media_buy_id,
                        "status": "pending_approval",
                        "budget": request.total_budget,
                        "flight_start_date": str(request.flight_start_date),
                        "flight_end_date": str(request.flight_end_date)
                    }
                )
            
            # Check database
            conn = get_db_connection()
            try:
                cursor = conn.connection.cursor() if hasattr(conn, 'connection') else conn.cursor()
                cursor.execute("""
                    SELECT principal_id, status, budget, start_date, end_date, raw_request
                    FROM media_buys 
                    WHERE media_buy_id = ?
                """, (media_buy_id,))
                
                row = cursor.fetchone()
                if not row:
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        message="Media buy not found",
                        error=f"Media buy {media_buy_id} does not exist"
                    )
                
                db_principal_id, status, budget, start_date, end_date, raw_request = row
                
                # Check authorization
                if principal_id != db_principal_id:
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        message="Unauthorized",
                        error="You don't have access to this media buy"
                    )
                
                return TaskResult(
                    status=TaskStatus.COMPLETED,
                    message="Media buy status retrieved",
                    data={
                        "media_buy_id": media_buy_id,
                        "status": status,
                        "budget": float(budget),
                        "flight_start_date": str(start_date),
                        "flight_end_date": str(end_date)
                    }
                )
            finally:
                conn.close()
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to get media buy status",
                error=str(e)
            )
    
    def update_media_buy(self,
                        principal_id: str,
                        media_buy_id: str,
                        updates: Dict[str, Any]) -> TaskResult:
        """Update a media buy."""
        try:
            if media_buy_id not in self.media_buys:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Media buy not found",
                    error=f"Media buy {media_buy_id} does not exist"
                )
            
            request, owner_principal_id = self.media_buys[media_buy_id]
            
            # Check authorization
            if principal_id != owner_principal_id:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Unauthorized",
                    error="You don't have access to this media buy"
                )
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(request, key):
                    setattr(request, key, value)
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message="Media buy updated successfully",
                data={
                    "media_buy_id": media_buy_id,
                    "updates": updates
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to update media buy",
                error=str(e)
            )
    
    def get_creative_status(self,
                           principal_id: str,
                           creative_id: str) -> TaskResult:
        """Get the status of a creative."""
        try:
            if creative_id not in self.creative_statuses:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Creative not found",
                    error=f"Creative {creative_id} does not exist"
                )
            
            status = self.creative_statuses[creative_id]
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message="Creative status retrieved",
                data={
                    "creative_id": creative_id,
                    "status": status.status,
                    "review_feedback": status.review_feedback
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to get creative status",
                error=str(e)
            )
    
    # --- Delivery Monitoring Tasks ---
    
    def get_media_buy_delivery(self,
                              principal_id: str,
                              media_buy_id: str,
                              start_date: Optional[str] = None,
                              end_date: Optional[str] = None) -> TaskResult:
        """Get delivery data for a media buy."""
        try:
            if media_buy_id not in self.media_buys:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Media buy not found",
                    error=f"Media buy {media_buy_id} does not exist"
                )
            
            buy_request, buy_principal = self.media_buys[media_buy_id]
            if buy_principal != principal_id:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Unauthorized",
                    error="You don't have access to this media buy"
                )
            
            # Mock delivery data
            today = date.today()
            campaign_start = datetime.strptime(buy_request.flight_start_date, "%Y-%m-%d").date()
            campaign_end = datetime.strptime(buy_request.flight_end_date, "%Y-%m-%d").date()
            
            # Determine status
            if today < campaign_start:
                status = "scheduled"
            elif today > campaign_end:
                status = "completed"
            else:
                status = "active"
            
            # Calculate mock metrics
            if status == "active" or status == "completed":
                days_active = min((today - campaign_start).days + 1, 
                                 (campaign_end - campaign_start).days + 1)
                daily_spend = buy_request.total_budget / ((campaign_end - campaign_start).days + 1)
                spend = daily_spend * days_active
                impressions = int(spend * 1000)  # Mock CPM of $1
                clicks = int(impressions * 0.001)  # Mock CTR of 0.1%
            else:
                spend = 0
                impressions = 0
                clicks = 0
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Media buy is {status} with ${spend:.2f} spent",
                data={
                    "media_buy_id": media_buy_id,
                    "status": status,
                    "metrics": {
                        "spend": spend,
                        "impressions": impressions,
                        "clicks": clicks,
                        "ctr": clicks / impressions if impressions > 0 else 0,
                        "cpm": (spend / impressions * 1000) if impressions > 0 else 0
                    },
                    "context_id": f"ctx_{uuid.uuid4().hex[:8]}"
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to get delivery data",
                error=str(e)
            )
    
    # --- Targeting Capabilities Tasks ---
    

    # ========== Core Messaging Methods ==========
    
    def send_message(
        self, 
        principal_id: str,
        content: str,
        context_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        protocol: str = "unknown"
    ) -> Dict[str, Any]:
        """Send a message in the conversation.
        
        This is a core method for AI agent communication protocols.
        Returns an A2A-compatible Task object.
        """
        # Generate message ID and task ID
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        # Ensure context_id is not None (required by A2A protocol)
        if not context_id:
            context_id = f"ctx_{uuid.uuid4().hex[:8]}"
        
        # Store in context if context_id provided
        if context_id and self.context_manager and self.tenant_id:
            try:
                # Ensure context exists (create if needed)
                actual_context_id = self.context_manager.get_or_create_context(
                    context_id=context_id,
                    tenant_id=self.tenant_id,
                    principal_id=principal_id,
                    protocol=protocol
                )
                
                # Get current context state
                context = self.context_manager.get_context_state(actual_context_id)
                
                # Update conversation state
                conversation = context.get('state', {}) if context else {}
                if 'messages' not in conversation:
                    conversation['messages'] = []
                
                conversation['messages'].append({
                    'id': message_id,
                    'principal_id': principal_id,
                    'content': content,
                    'timestamp': timestamp,
                    'metadata': metadata or {}
                })
                
                # Save updated context
                self.context_manager.update_context_state(
                    context_id=actual_context_id,
                    state=conversation,
                    metadata={'last_message_id': message_id}
                )
                
                # Also save message to context_messages table
                self.context_manager.save_message(
                    context_id=actual_context_id,
                    message_type="request",
                    method="message/send",
                    request_data={"content": content, "metadata": metadata},
                    response_data=None
                )
            except Exception as e:
                logger.warning(f"Failed to update context: {e}")
        
        # Log the message
        self.audit_logger.log_operation(
            operation="send_message",
            principal_name=principal_id,
            principal_id=principal_id,
            adapter_id="",
            success=True,
            details={
                "message_id": message_id,
                "context_id": context_id,
                "protocol": protocol
            }
        )
        
        # Return A2A-compatible Message object (not Task)
        # Ensure content is never None
        message_content = content if content is not None else ""
        
        return {
            "kind": "message",
            "messageId": message_id,
            "role": "agent",  # Changed from "user" to "agent" for A2A protocol compliance
            "parts": [
                {
                    "kind": "text",
                    "text": message_content
                }
            ],
            "contextId": context_id,
            "timestamp": timestamp,
            "metadata": metadata or {}
        }
    
    def get_messages(
        self,
        principal_id: str,
        context_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Retrieve messages from the conversation history.
        
        This supports conversation continuity in AI agent protocols.
        Returns A2A-compatible Task object.
        """
        messages = []
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        # Ensure context_id is not None
        if not context_id:
            context_id = f"ctx_{uuid.uuid4().hex[:8]}"
        
        if context_id and self.context_manager:
            try:
                # First try to get messages from the database
                db_messages = self.context_manager.get_conversation_history(
                    context_id=context_id,
                    limit=limit
                )
                
                # Convert database messages to the expected format
                for db_msg in db_messages:
                    # Parse request_data if it's a string (JSON)
                    request_data = db_msg.get('request_data', {})
                    if isinstance(request_data, str):
                        try:
                            import json
                            request_data = json.loads(request_data) if request_data else {}
                        except:
                            request_data = {}
                    
                    content = ''
                    if db_msg.get('message_type') == 'request':
                        content = request_data.get('content', '') if request_data else ''
                    else:
                        content = 'Response'
                    
                    messages.append({
                        'id': f"msg_{uuid.uuid4().hex[:8]}",
                        'role': 'user' if db_msg.get('message_type') == 'request' else 'assistant',
                        'content': content or '',  # Ensure never None
                        'timestamp': db_msg.get('created_at', datetime.utcnow().isoformat())
                    })
                
                # Also check in-memory state for any recent messages not yet persisted
                context = self.context_manager.get_context_state(context_id)
                if context:
                    conversation = context.get('state', {})
                    state_messages = conversation.get('messages', [])
                    
                    # Add any messages from state that aren't in db_messages
                    existing_ids = {msg.get('id') for msg in messages}
                    for msg in state_messages:
                        if msg.get('id') not in existing_ids:
                            messages.append(msg)
                    
                    # Apply pagination
                    messages = messages[offset:offset + limit]
            except Exception as e:
                print(f"Failed to retrieve messages: {e}")
        
        # Convert messages to A2A format
        formatted_messages = []
        for msg in messages:
            # Ensure content is never None
            msg_content = msg.get('content', '')
            if msg_content is None:
                msg_content = ''
            
            formatted_messages.append({
                "messageId": msg.get('id', f"msg_{uuid.uuid4().hex[:8]}"),
                "role": msg.get('role', 'user'),
                "parts": [
                    {
                        "kind": "text",
                        "text": msg_content
                    }
                ],
                "timestamp": msg.get('timestamp', datetime.utcnow().isoformat())
            })
        
        # Return A2A-compatible Task object
        return {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": "completed"
            },
            "artifacts": [
                {
                    "artifactId": f"artifact_messages_{task_id}",
                    "name": "Message History",
                    "parts": [
                        {
                            "kind": "text", 
                            "text": f"Retrieved {len(formatted_messages)} messages"
                        }
                    ]
                }
            ],
            "history": formatted_messages,
            "kind": "task",
            "metadata": {
                "total_count": len(messages),
                "limit": limit,
                "offset": offset
            }
        }
    
    def clear_context(
        self,
        principal_id: str,
        context_id: str
    ) -> Dict[str, Any]:
        """Clear the conversation context.
        
        Allows agents to start fresh conversations.
        Returns A2A-compatible Task object.
        """
        success = False
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        if self.context_manager:
            try:
                # Create fresh context
                self.context_manager.update_context_state(
                    context_id=context_id,
                    state={"messages": []},
                    metadata={"cleared_at": timestamp}
                )
                success = True
            except Exception as e:
                print(f"Failed to clear context: {e}")
        
        # Return A2A-compatible Task object
        return {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": "completed" if success else "failed"
            },
            "artifacts": [
                {
                    "artifactId": f"artifact_clear_{task_id}",
                    "name": "Context Clear Result",
                    "parts": [
                        {
                            "kind": "text",
                            "text": f"Context {'cleared successfully' if success else 'clear failed'}"
                        }
                    ]
                }
            ],
            "history": [],
            "kind": "task",
            "metadata": {
                "success": success,
                "timestamp": timestamp
            }
        }
    
    def get_conversation_state(
        self,
        principal_id: str,
        context_id: str
    ) -> Dict[str, Any]:
        """Get the current conversation state.
        
        Useful for debugging and state inspection.
        """
        state = {}
        
        if self.context_manager and context_id:
            try:
                context = self.context_manager.get_context_state(context_id)
                if context:
                    state = {
                        "context_id": context_id,
                        "conversation": context.get('state', {}),
                        "metadata": context.get('metadata', {}),
                        "created_at": context.get('created_at'),
                        "updated_at": context.get('updated_at')
                    }
            except Exception as e:
                print(f"Failed to get conversation state: {e}")
                state = {"error": str(e)}
        
        return state

    def get_targeting_capabilities(self,
                                    principal_id: str,
                                    channels: Optional[List[str]] = None) -> TaskResult:
        """Get available targeting dimensions."""
        try:
            from targeting_dimensions import (
                get_overlay_dimensions,
                get_managed_dimensions,
                Channel
            )
            
            # Default to all channels if not specified
            if not channels:
                channels = ["display", "video", "audio"]
            
            overlay_dims = {}
            for channel_str in channels:
                try:
                    channel = Channel[channel_str.upper()]
                    overlay_dims[channel_str] = get_overlay_dimensions(channel)
                except KeyError:
                    pass
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Retrieved targeting capabilities for {len(channels)} channels",
                data={
                    "overlay_dimensions": overlay_dims,
                    "context_id": f"ctx_{uuid.uuid4().hex[:8]}"
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to get targeting capabilities",
                error=str(e)
            )
    
    # --- Human Task Management ---
    
    def create_human_task(self,
                         principal_id: str,
                         task_type: str,
                         description: str,
                         metadata: Optional[Dict] = None) -> TaskResult:
        """Create a task requiring human intervention."""
        try:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            
            self.human_tasks[task_id] = {
                "task_id": task_id,
                "type": task_type,
                "description": description,
                "status": "pending",
                "created_at": datetime.utcnow(),
                "created_by": principal_id,
                "metadata": metadata or {}
            }
            
            # Notify via Slack if configured
            notifier = get_slack_notifier()
            if notifier:
                notifier.notify_task_created(task_id, task_type, description)
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Human task created: {task_id}",
                data={
                    "task_id": task_id,
                    "status": "pending",
                    "context_id": f"ctx_{uuid.uuid4().hex[:8]}"
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to create human task",
                error=str(e)
            )
    
    def verify_task(self,
                   principal_id: str,
                   task_id: str) -> TaskResult:
        """Verify if a task was completed correctly."""
        try:
            if task_id not in self.human_tasks:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    message="Task not found",
                    error=f"Task {task_id} does not exist"
                )
            
            task = self.human_tasks[task_id]
            
            # Mock verification logic
            if task["status"] == "completed":
                verified = True
                verification_details = "Task completed successfully"
            else:
                verified = False
                verification_details = f"Task is still {task['status']}"
            
            return TaskResult(
                status=TaskStatus.COMPLETED,
                message=f"Task verification: {'passed' if verified else 'failed'}",
                data={
                    "task_id": task_id,
                    "verified": verified,
                    "details": verification_details,
                    "context_id": f"ctx_{uuid.uuid4().hex[:8]}"
                }
            )
            
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                message="Failed to verify task",
                error=str(e)
            )