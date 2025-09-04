#!/usr/bin/env python3
"""
AdCP Sales Agent A2A Server using official a2a-sdk library.
Supports both standard A2A message format and JSON-RPC 2.0.
"""

import logging
import os
import sys
import threading
from collections.abc import AsyncGenerator
from typing import Any

# Fix import order to avoid local a2a directory conflict
# Import official a2a-sdk first before adding local paths

original_path = sys.path.copy()

# Temporarily remove current directory to avoid local a2a conflict
if "" in sys.path:
    sys.path.remove("")
if "." in sys.path:
    sys.path.remove(".")

# Official a2a-sdk imports (must be before adding local paths)
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.context import ServerCallContext
from a2a.server.events.event_queue import Event
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard,
    Artifact,
    Message,
    MessageSendParams,
    Part,
    Task,
    TaskIdParams,
    TaskQueryParams,
    TaskState,
    TaskStatus,
)

# Restore paths and add parent directories for local imports
sys.path = original_path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import core functions for direct calls
from datetime import UTC, datetime

from src.core.audit_logger import get_audit_logger
from src.core.auth_utils import get_principal_from_token
from src.core.config_loader import get_current_tenant
from src.core.main import (
    add_creative_assets as core_add_creative_assets_tool,
)
from src.core.main import (
    create_media_buy as core_create_media_buy_tool,
)
from src.core.main import (
    get_products as core_get_products_tool,
)
from src.core.main import (
    get_signals as core_get_signals_tool,
)
from src.core.schemas import (
    AddCreativeAssetsRequest,
    CreateMediaBuyRequest,
    GetProductsRequest,
    GetSignalsRequest,
)
from src.core.testing_hooks import TestingContext
from src.core.tool_context import ToolContext

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Thread-local storage for current request auth token
_request_context = threading.local()


class AdCPRequestHandler(RequestHandler):
    """Request handler for AdCP A2A operations supporting JSON-RPC 2.0."""

    def __init__(self):
        """Initialize the AdCP A2A request handler."""
        self.tasks = {}  # In-memory task storage
        logger.info("AdCP Request Handler initialized for direct function calls")

    def _get_auth_token(self) -> str | None:
        """Extract Bearer token from current request context."""
        return getattr(_request_context, "auth_token", None)

    def _create_tool_context_from_a2a(self, auth_token: str, tool_name: str, context_id: str = None) -> ToolContext:
        """Create a ToolContext from A2A authentication information.

        Args:
            auth_token: Bearer token from Authorization header
            tool_name: Name of the tool being called
            context_id: Optional context ID for conversation tracking

        Returns:
            ToolContext for calling core functions

        Raises:
            ValueError: If authentication fails
        """
        # Authenticate using the token
        principal_id = get_principal_from_token(auth_token)
        if not principal_id:
            raise ValueError("Invalid or missing authentication token")

        # Get tenant info (set as side effect of authentication)
        tenant = get_current_tenant()
        if not tenant:
            raise ValueError("Unable to determine tenant from authentication")

        # Generate context ID if not provided
        if not context_id:
            context_id = f"a2a_{datetime.now(UTC).timestamp()}"

        # Create ToolContext
        return ToolContext(
            context_id=context_id,
            tenant_id=tenant["tenant_id"],
            principal_id=principal_id,
            tool_name=tool_name,
            request_timestamp=datetime.now(UTC),
            metadata={"source": "a2a_server", "protocol": "a2a_jsonrpc"},
            testing_context=TestingContext().model_dump(),  # Default testing context for A2A requests
        )

    def _log_a2a_operation(
        self,
        operation: str,
        tenant_id: str,
        principal_id: str,
        success: bool = True,
        details: dict = None,
        error: str = None,
    ):
        """Log A2A operations to audit system for visibility in activity feed."""
        try:
            if not tenant_id:
                return

            audit_logger = get_audit_logger("A2A", tenant_id)
            audit_logger.log_operation(
                operation=operation,
                principal_name=f"A2A_Client_{principal_id}",
                principal_id=principal_id,
                adapter_id="a2a_client",
                success=success,
                details=details,
                error=error,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning(f"Failed to log A2A operation: {e}")

    async def on_message_send(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> Task | Message:
        """Handle 'message/send' method for non-streaming requests.

        Supports both invocation patterns from AdCP PR #48:
        1. Natural Language: parts[{kind: "text", text: "..."}]
        2. Explicit Skill: parts[{kind: "data", data: {skill: "...", parameters: {...}}}]

        Args:
            params: Parameters including the message and configuration
            context: Server call context

        Returns:
            Task object or Message response
        """
        logger.info(f"Handling message/send request: {params}")

        # Parse message for both text and structured data parts
        message = params.message
        text_parts = []
        skill_invocations = []

        if hasattr(message, "parts") and message.parts:
            for part in message.parts:
                # Handle text parts (natural language invocation)
                if hasattr(part, "text"):
                    text_parts.append(part.text)
                elif hasattr(part, "root") and hasattr(part.root, "text"):
                    text_parts.append(part.root.text)

                # Handle structured data parts (explicit skill invocation)
                elif hasattr(part, "data") and isinstance(part.data, dict):
                    if "skill" in part.data and "parameters" in part.data:
                        skill_invocations.append({"skill": part.data["skill"], "parameters": part.data["parameters"]})
                        logger.info(f"Found explicit skill invocation: {part.data['skill']}")

                # Handle nested data structure (some A2A clients use this format)
                elif hasattr(part, "root") and hasattr(part.root, "data"):
                    data = part.root.data
                    if isinstance(data, dict) and "skill" in data and "parameters" in data:
                        skill_invocations.append({"skill": data["skill"], "parameters": data["parameters"]})
                        logger.info(f"Found explicit skill invocation (nested): {data['skill']}")

        # Combine text for natural language fallback
        combined_text = " ".join(text_parts).strip().lower()

        # Create task for tracking
        task_id = f"task_{len(self.tasks) + 1}"
        # Handle message_id being a number or string
        msg_id = str(params.message.message_id) if hasattr(params.message, "message_id") else None
        context_id = params.message.context_id or msg_id or f"ctx_{task_id}"

        # Prepare task metadata with both invocation types
        task_metadata = {
            "request_text": combined_text,
            "invocation_type": "explicit_skill" if skill_invocations else "natural_language",
        }
        if skill_invocations:
            task_metadata["skills_requested"] = [inv["skill"] for inv in skill_invocations]

        task = Task(
            id=task_id,
            context_id=context_id,
            kind="task",
            status=TaskStatus(state=TaskState.working),
            metadata=task_metadata,
        )
        self.tasks[task_id] = task

        try:
            # Get authentication token
            auth_token = self._get_auth_token()
            if not auth_token:
                raise ValueError("Missing authentication token - Bearer token required in Authorization header")

            # Route: Handle explicit skill invocations first, then natural language fallback
            if skill_invocations:
                # Process explicit skill invocations
                results = []
                for invocation in skill_invocations:
                    skill_name = invocation["skill"]
                    parameters = invocation["parameters"]
                    logger.info(f"Processing explicit skill: {skill_name} with parameters: {parameters}")

                    try:
                        result = await self._handle_explicit_skill(skill_name, parameters, auth_token)
                        results.append({"skill": skill_name, "result": result, "success": True})
                    except Exception as e:
                        logger.error(f"Error in explicit skill {skill_name}: {e}")
                        results.append({"skill": skill_name, "error": str(e), "success": False})

                # Create artifacts for all skill results
                for i, res in enumerate(results):
                    artifact_data = res["result"] if res["success"] else {"error": res["error"]}
                    task.artifacts = task.artifacts or []
                    task.artifacts.append(
                        Artifact(
                            artifactId=f"skill_result_{i+1}",
                            name=f"{'error' if not res['success'] else res['skill']}_result",
                            parts=[Part(type="data", data=artifact_data)],
                        )
                    )

                # Check if any skills failed and determine task status
                failed_skills = [res["skill"] for res in results if not res["success"]]
                successful_skills = [res["skill"] for res in results if res["success"]]

                if failed_skills and not successful_skills:
                    # All skills failed - mark task as failed
                    task.status = TaskStatus(state=TaskState.failed)
                    return task
                elif successful_skills:
                    # Log successful skill invocations
                    try:
                        tool_context = self._create_tool_context_from_a2a(auth_token, successful_skills[0])
                        self._log_a2a_operation(
                            "explicit_skill_invocation",
                            tool_context.tenant_id,
                            tool_context.principal_id,
                            True,
                            {"skills": successful_skills, "count": len(successful_skills)},
                        )
                    except Exception as e:
                        logger.warning(f"Could not log skill invocations: {e}")

            # Natural language fallback (existing keyword-based routing)
            elif any(word in combined_text for word in ["product", "inventory", "available", "catalog"]):
                result = await self._get_products(combined_text, auth_token)
                # Extract tenant and principal for logging
                try:
                    tool_context = self._create_tool_context_from_a2a(auth_token, "get_products")
                    tenant_id = tool_context.tenant_id
                    principal_id = tool_context.principal_id
                except Exception as e:
                    logger.warning(f"Could not extract context for logging: {e}")
                    tenant_id = "unknown"
                    principal_id = "unknown"

                self._log_a2a_operation(
                    "get_products",
                    tenant_id,
                    principal_id,
                    True,
                    {
                        "query": combined_text[:100],
                        "product_count": len(result.get("products", [])) if isinstance(result, dict) else 0,
                    },
                )
                task.artifacts = [
                    Artifact(
                        artifactId="product_catalog_1", name="product_catalog", parts=[Part(type="data", data=result)]
                    )
                ]
            elif any(word in combined_text for word in ["price", "pricing", "cost", "cpm", "budget"]):
                result = self._get_pricing()
                # Extract tenant and principal for logging
                try:
                    tool_context = self._create_tool_context_from_a2a(auth_token, "get_pricing")
                    tenant_id = tool_context.tenant_id
                    principal_id = tool_context.principal_id
                except Exception as e:
                    logger.warning(f"Could not extract context for logging: {e}")
                    tenant_id = "unknown"
                    principal_id = "unknown"

                self._log_a2a_operation(
                    "get_pricing",
                    tenant_id,
                    principal_id,
                    True,
                    {
                        "query": combined_text[:100],
                        "pricing_models": len(result.get("pricing_models", [])) if isinstance(result, dict) else 0,
                    },
                )
                task.artifacts = [
                    Artifact(
                        artifactId="pricing_info_1", name="pricing_information", parts=[Part(type="data", data=result)]
                    )
                ]
            elif any(word in combined_text for word in ["target", "audience"]):
                result = self._get_targeting()
                # Extract tenant and principal for logging
                try:
                    tool_context = self._create_tool_context_from_a2a(auth_token, "get_targeting")
                    tenant_id = tool_context.tenant_id
                    principal_id = tool_context.principal_id
                except Exception as e:
                    logger.warning(f"Could not extract context for logging: {e}")
                    tenant_id = "unknown"
                    principal_id = "unknown"

                self._log_a2a_operation(
                    "get_targeting",
                    tenant_id,
                    principal_id,
                    True,
                    {
                        "query": combined_text[:100],
                        "targeting_categories": (
                            len(result.get("targeting_options", {})) if isinstance(result, dict) else 0
                        ),
                    },
                )
                task.artifacts = [
                    Artifact(
                        artifactId="targeting_opts_1", name="targeting_options", parts=[Part(type="data", data=result)]
                    )
                ]
            elif any(word in combined_text for word in ["create", "buy", "campaign", "media"]):
                result = await self._create_media_buy(combined_text, auth_token)
                # Extract tenant and principal for logging
                try:
                    tool_context = self._create_tool_context_from_a2a(auth_token, "create_media_buy")
                    tenant_id = tool_context.tenant_id
                    principal_id = tool_context.principal_id
                except Exception as e:
                    logger.warning(f"Could not extract context for logging: {e}")
                    tenant_id = "unknown"
                    principal_id = "unknown"

                self._log_a2a_operation(
                    "create_media_buy",
                    tenant_id,
                    principal_id,
                    result.get("success", False),
                    {"query": text[:100], "success": result.get("success", False)},
                    result.get("message") if not result.get("success") else None,
                )
                if result.get("success"):
                    task.artifacts = [
                        Artifact(
                            artifactId="media_buy_1", name="media_buy_created", parts=[Part(type="data", data=result)]
                        )
                    ]
                else:
                    task.artifacts = [
                        Artifact(
                            artifactId="media_buy_error_1",
                            name="media_buy_error",
                            parts=[Part(type="data", data=result)],
                        )
                    ]
            else:
                # General help response
                capabilities = {
                    "supported_queries": [
                        "product_catalog",
                        "targeting_options",
                        "pricing_information",
                        "campaign_creation",
                    ],
                    "example_queries": [
                        "What video ad products do you have available?",
                        "Show me targeting options",
                        "What are your pricing models?",
                        "How do I create a media buy?",
                    ],
                }
                # Extract tenant and principal for logging
                try:
                    tool_context = self._create_tool_context_from_a2a(auth_token, "get_capabilities")
                    tenant_id = tool_context.tenant_id
                    principal_id = tool_context.principal_id
                except Exception as e:
                    logger.warning(f"Could not extract context for logging: {e}")
                    tenant_id = "unknown"
                    principal_id = "unknown"

                self._log_a2a_operation(
                    "get_capabilities",
                    tenant_id,
                    principal_id,
                    True,
                    {"query": text[:100], "response_type": "capabilities"},
                )
                task.artifacts = [
                    Artifact(
                        artifactId="capabilities_1", name="capabilities", parts=[Part(type="data", data=capabilities)]
                    )
                ]

            # Mark task as completed
            task.status = TaskStatus(state=TaskState.completed)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Try to get context for error logging
            try:
                auth_token = self._get_auth_token()
                if auth_token:
                    tool_context = self._create_tool_context_from_a2a(auth_token, "error_handler")
                    tenant_id = tool_context.tenant_id
                    principal_id = tool_context.principal_id
                else:
                    tenant_id = "unknown"
                    principal_id = "unknown"
            except:
                tenant_id = "unknown"
                principal_id = "unknown"

            self._log_a2a_operation(
                "message_processing",
                tenant_id,
                principal_id,
                False,
                {"error_type": type(e).__name__},
                str(e),
            )
            task.status = TaskStatus(state=TaskState.failed)
            task.artifacts = [
                Artifact(artifactId="error_1", name="error", parts=[Part(type="data", data={"error": str(e)})])
            ]

        self.tasks[task_id] = task
        return task

    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> AsyncGenerator[Event]:
        """Handle 'message/stream' method for streaming requests.

        Args:
            params: Parameters including the message and configuration
            context: Server call context

        Yields:
            Event objects from the agent's execution
        """
        # For now, implement non-streaming behavior
        # In production, this would yield events as they occur
        task = await self.on_message_send(params, context)

        # Yield a single event with the complete task
        yield Event(type="task_update", data=task.model_dump())

    async def on_get_task(
        self,
        params: TaskQueryParams,
        context: ServerCallContext | None = None,
    ) -> Task | None:
        """Handle 'tasks/get' method to retrieve task status.

        Args:
            params: Parameters specifying the task ID
            context: Server call context

        Returns:
            Task object if found, otherwise None
        """
        task_id = params.task_id
        return self.tasks.get(task_id)

    async def on_cancel_task(
        self,
        params: TaskIdParams,
        context: ServerCallContext | None = None,
    ) -> Task | None:
        """Handle 'tasks/cancel' method to cancel a task.

        Args:
            params: Parameters specifying the task ID
            context: Server call context

        Returns:
            Task object with canceled status, or None if not found
        """
        task_id = params.task_id
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus(state=TaskState.canceled)
            self.tasks[task_id] = task
        return task

    async def on_resubscribe_to_task(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle task resubscription requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Task resubscription not supported")

    async def on_get_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle get push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def on_set_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle set push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def on_list_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle list push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def on_delete_task_push_notification_config(
        self,
        params: Any,
        context: ServerCallContext | None = None,
    ) -> Any:
        """Handle delete push notification config requests."""
        # Not implemented for now
        from a2a.types import UnsupportedOperationError

        raise UnsupportedOperationError("Push notifications not supported")

    async def _handle_explicit_skill(self, skill_name: str, parameters: dict, auth_token: str) -> dict:
        """Handle explicit AdCP skill invocations.

        Maps skill names to appropriate handlers and validates parameters.

        Args:
            skill_name: The AdCP skill name (e.g., "get_products")
            parameters: Dictionary of skill-specific parameters
            auth_token: Bearer token for authentication

        Returns:
            Dictionary containing the skill result

        Raises:
            ValueError: For unknown skills or invalid parameters
        """
        logger.info(f"Handling explicit skill: {skill_name} with parameters: {list(parameters.keys())}")

        # Map skill names to handlers
        skill_handlers = {
            # Core AdCP Media Buy Skills (6 total)
            "get_products": self._handle_get_products_skill,
            "create_media_buy": self._handle_create_media_buy_skill,
            "add_creative_assets": self._handle_add_creative_assets_skill,
            "approve_creative": self._handle_approve_creative_skill,
            "get_media_buy_status": self._handle_get_media_buy_status_skill,
            "optimize_media_buy": self._handle_optimize_media_buy_skill,
            # Core AdCP Signals Skills (2 total)
            "get_signals": self._handle_get_signals_skill,
            "search_signals": self._handle_search_signals_skill,
            # Legacy skill names (for backward compatibility)
            "get_pricing": lambda params, token: self._get_pricing(),
            "get_targeting": lambda params, token: self._get_targeting(),
        }

        if skill_name not in skill_handlers:
            available_skills = list(skill_handlers.keys())
            raise ValueError(f"Unknown skill '{skill_name}'. Available skills: {available_skills}")

        try:
            handler = skill_handlers[skill_name]
            if skill_name in ["get_pricing", "get_targeting"]:
                # These are simple handlers without async
                return handler(parameters, auth_token)
            else:
                # These are async handlers that call core tools
                return await handler(parameters, auth_token)
        except Exception as e:
            logger.error(f"Error in skill handler {skill_name}: {e}")
            raise ValueError(f"Skill {skill_name} failed: {str(e)}")

    async def _handle_get_products_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit get_products skill invocation."""
        try:
            # Create ToolContext from A2A auth info
            tool_context = self._create_tool_context_from_a2a(
                auth_token=auth_token,
                tool_name="get_products",
            )

            # Map A2A parameters to GetProductsRequest
            brief = parameters.get("brief", "")
            promoted_offering = parameters.get("promoted_offering", "")

            if not brief and not promoted_offering:
                raise ValueError("Either 'brief' or 'promoted_offering' parameter is required")

            # Use brief as promoted_offering if not provided
            if not promoted_offering and brief:
                promoted_offering = f"Business seeking to advertise: {brief}"

            request = GetProductsRequest(brief=brief, promoted_offering=promoted_offering)

            # Call core function directly
            response = await core_get_products_tool.fn(request, tool_context)

            # Convert to A2A response format
            return {
                "products": [product.model_dump() for product in response.products],
                "message": response.message or "Products retrieved successfully",
            }

        except Exception as e:
            logger.error(f"Error in get_products skill: {e}")
            return {"products": [], "message": f"Unable to retrieve products: {str(e)}"}

    async def _handle_create_media_buy_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit create_media_buy skill invocation."""
        try:
            # Create ToolContext from A2A auth info
            tool_context = self._create_tool_context_from_a2a(
                auth_token=auth_token,
                tool_name="create_media_buy",
            )

            # Map A2A parameters to CreateMediaBuyRequest
            # Required parameters
            required_params = ["product_ids", "total_budget", "flight_start_date", "flight_end_date"]
            missing_params = [param for param in required_params if param not in parameters]

            if missing_params:
                return {
                    "success": False,
                    "message": f"Missing required parameters: {missing_params}",
                    "required_parameters": required_params,
                    "received_parameters": list(parameters.keys()),
                }

            # Create request object with parameter mapping
            request = CreateMediaBuyRequest(
                product_ids=parameters["product_ids"],
                total_budget=float(parameters["total_budget"]),
                flight_start_date=parameters["flight_start_date"],
                flight_end_date=parameters["flight_end_date"],
                # Optional parameters with defaults
                preferred_deal_ids=parameters.get("preferred_deal_ids", []),
                custom_targeting=parameters.get("custom_targeting", {}),
                creative_requirements=parameters.get("creative_requirements", {}),
                optimization_goal=parameters.get("optimization_goal", "impressions"),
            )

            # Call core function directly
            response = core_create_media_buy_tool.fn(request, tool_context)

            # Convert response to A2A format
            return {
                "success": True,
                "media_buy_id": response.media_buy_id,
                "status": response.status,
                "message": response.message or "Media buy created successfully",
                "packages": [package.model_dump() for package in response.packages] if response.packages else [],
                "next_steps": response.next_steps if hasattr(response, "next_steps") else [],
            }

        except Exception as e:
            logger.error(f"Error in create_media_buy skill: {e}")
            return {
                "success": False,
                "message": f"Failed to create media buy: {str(e)}",
                "error": str(e),
            }

    async def _handle_add_creative_assets_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit add_creative_assets skill invocation."""
        try:
            # Create ToolContext from A2A auth info
            tool_context = self._create_tool_context_from_a2a(
                auth_token=auth_token,
                tool_name="add_creative_assets",
            )

            # Map A2A parameters to AddCreativeAssetsRequest
            # Required parameters
            if "media_buy_id" not in parameters and "buyer_ref" not in parameters:
                return {
                    "success": False,
                    "message": "Either 'media_buy_id' or 'buyer_ref' parameter is required",
                    "required_parameters": ["media_buy_id OR buyer_ref", "assets"],
                    "received_parameters": list(parameters.keys()),
                }

            if "assets" not in parameters:
                return {
                    "success": False,
                    "message": "Missing required parameter: 'assets'",
                    "required_parameters": ["media_buy_id OR buyer_ref", "assets"],
                    "received_parameters": list(parameters.keys()),
                }

            # Create request object with parameter mapping
            request = AddCreativeAssetsRequest(
                media_buy_id=parameters.get("media_buy_id"),
                buyer_ref=parameters.get("buyer_ref"),
                assets=parameters["assets"],
                creative_group_name=parameters.get("creative_group_name"),
            )

            # Call core function directly
            response = core_add_creative_assets_tool.fn(request, tool_context)

            # Convert response to A2A format
            return {
                "success": True,
                "message": response.message or "Creative assets added successfully",
                "creative_ids": response.creative_ids if hasattr(response, "creative_ids") else [],
                "status": response.status if hasattr(response, "status") else "pending_review",
            }

        except Exception as e:
            logger.error(f"Error in add_creative_assets skill: {e}")
            return {
                "success": False,
                "message": f"Failed to add creative assets: {str(e)}",
                "error": str(e),
            }

    async def _handle_approve_creative_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit approve_creative skill invocation."""
        # TODO: Implement full approve_creative skill handler
        return {
            "success": False,
            "message": "approve_creative skill not yet implemented in explicit invocation",
            "parameters_received": parameters,
        }

    async def _handle_get_signals_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit get_signals skill invocation."""
        try:
            # Create ToolContext from A2A auth info
            tool_context = self._create_tool_context_from_a2a(
                auth_token=auth_token,
                tool_name="get_signals",
            )

            # Map A2A parameters to GetSignalsRequest (no required parameters)
            request = GetSignalsRequest(
                signal_types=parameters.get("signal_types", []),
                categories=parameters.get("categories", []),
            )

            # Call core function directly
            response = await core_get_signals_tool.fn(request, tool_context)

            # Convert response to A2A format
            return {
                "signals": [signal.model_dump() for signal in response.signals],
                "message": response.message or "Signals retrieved successfully",
                "total_count": len(response.signals),
            }

        except Exception as e:
            logger.error(f"Error in get_signals skill: {e}")
            return {
                "signals": [],
                "message": f"Unable to retrieve signals: {str(e)}",
                "error": str(e),
            }

    async def _handle_search_signals_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit search_signals skill invocation."""
        # TODO: Implement full search_signals skill handler
        return {
            "signals": [],
            "message": "search_signals skill not yet implemented in explicit invocation",
            "parameters_received": parameters,
        }

    async def _handle_get_media_buy_status_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit get_media_buy_status skill invocation."""
        # TODO: Implement full get_media_buy_status skill handler
        return {
            "success": False,
            "message": "get_media_buy_status skill not yet implemented in explicit invocation",
            "parameters_received": parameters,
        }

    async def _handle_optimize_media_buy_skill(self, parameters: dict, auth_token: str) -> dict:
        """Handle explicit optimize_media_buy skill invocation."""
        # TODO: Implement full optimize_media_buy skill handler
        return {
            "success": False,
            "message": "optimize_media_buy skill not yet implemented in explicit invocation",
            "parameters_received": parameters,
        }

    async def _get_products(self, query: str, auth_token: str) -> dict:
        """Get available advertising products by calling core functions directly.

        Args:
            query: User's product query
            auth_token: Bearer token for authentication

        Returns:
            Dictionary containing product information
        """
        try:
            # Create ToolContext from A2A auth info
            tool_context = self._create_tool_context_from_a2a(
                auth_token=auth_token,
                tool_name="get_products",
            )

            # Create request object - need a promoted_offering for AdCP compliance
            # Extract promoted offering from the query or use a reasonable default
            promoted_offering = self._extract_promoted_offering_from_query(query)

            request = GetProductsRequest(brief=query, promoted_offering=promoted_offering)

            # Call core function directly using the underlying function
            response = await core_get_products_tool.fn(request, tool_context)

            # Convert to A2A response format
            return {
                "products": [product.model_dump() for product in response.products],
                "message": response.message or "Products retrieved successfully",
            }

        except Exception as e:
            logger.error(f"Error getting products: {e}")
            # Return empty products list instead of fallback data
            return {"products": [], "message": f"Unable to retrieve products: {str(e)}"}

    def _extract_promoted_offering_from_query(self, query: str) -> str:
        """Extract or infer promoted_offering from the user query.

        AdCP requires promoted_offering to be provided. We'll try to extract
        it from the query or provide a reasonable default.
        """
        # Look for common patterns that might indicate the promoted offering
        query_lower = query.lower()

        # If the query mentions specific brands or products, use those
        if "advertise" in query_lower or "promote" in query_lower:
            # Try to extract what they're promoting
            parts = query.split()
            for i, word in enumerate(parts):
                if word.lower() in ["advertise", "promote", "advertising", "promoting"]:
                    if i + 1 < len(parts):
                        # Take the next few words as the offering
                        offering_parts = parts[i + 1 : i + 4]  # Take up to 3 words
                        offering = " ".join(offering_parts).strip(".,!?")
                        if len(offering) > 5:  # Make sure it's substantial
                            return f"Business promoting {offering}"

        # Default offering based on query type
        if any(word in query_lower for word in ["video", "display", "banner", "ad"]):
            return "Brand advertising products and services"
        elif any(word in query_lower for word in ["coffee", "beverage", "food"]):
            return "Food and beverage company"
        elif any(word in query_lower for word in ["tech", "software", "app", "digital"]):
            return "Technology company digital products"
        else:
            # Generic fallback that should pass AdCP validation
            return "Business advertising products and services"

    def _get_pricing(self) -> dict:
        """Get pricing information.

        Returns:
            Dictionary containing pricing models and information
        """
        return {
            "pricing_models": [
                {
                    "type": "CPM",
                    "description": "Cost per thousand impressions",
                    "ranges": {
                        "video": {"min": 15, "max": 50},
                        "display": {"min": 2, "max": 10},
                        "native": {"min": 5, "max": 20},
                    },
                },
                {
                    "type": "CPC",
                    "description": "Cost per click",
                    "ranges": {"min": 0.50, "max": 5.00},
                },
                {
                    "type": "Guaranteed",
                    "description": "Fixed price for guaranteed delivery",
                    "minimum_commitment": 10000,
                },
            ],
            "volume_discounts": [
                {"threshold": 50000, "discount": "5%"},
                {"threshold": 100000, "discount": "10%"},
                {"threshold": 500000, "discount": "15%"},
            ],
        }

    def _get_targeting(self) -> dict:
        """Get available targeting options.

        Returns:
            Dictionary containing targeting capabilities
        """
        return {
            "targeting_options": {
                "demographics": {
                    "age_ranges": ["18-24", "25-34", "35-44", "45-54", "55+"],
                    "gender": ["male", "female", "unknown"],
                    "household_income": ["0-50k", "50-100k", "100-150k", "150k+"],
                },
                "geography": {
                    "levels": ["country", "state", "dma", "city", "zip"],
                    "available_countries": ["US", "CA", "UK", "AU"],
                },
                "interests": {
                    "categories": [
                        "Technology",
                        "Sports",
                        "Entertainment",
                        "Travel",
                        "Food & Dining",
                        "Health & Fitness",
                    ]
                },
                "contextual": {
                    "content_categories": ["News", "Sports", "Entertainment", "Business"],
                    "keywords": "Custom keyword targeting available",
                },
                "devices": {
                    "types": ["desktop", "mobile", "tablet", "ctv"],
                    "operating_systems": ["ios", "android", "windows", "macos"],
                },
            }
        }

    async def _create_media_buy(self, request: str, auth_token: str) -> dict:
        """Create a media buy based on the request.

        Args:
            request: User's media buy request
            auth_token: Bearer token for authentication

        Returns:
            Dictionary containing media buy creation result
        """
        # For now, return a mock response indicating authentication is working
        # but media buy creation needs more implementation
        try:
            # Verify authentication works
            tool_context = self._create_tool_context_from_a2a(
                auth_token=auth_token,
                tool_name="create_media_buy",
            )

            return {
                "success": False,
                "message": f"Authentication successful for {tool_context.principal_id}, but media buy creation needs more details",
                "required_fields": ["product_ids", "total_budget", "flight_start_date", "flight_end_date"],
                "authenticated_tenant": tool_context.tenant_id,
                "authenticated_principal": tool_context.principal_id,
                "example": {
                    "product_ids": ["video_premium"],
                    "total_budget": 10000,
                    "flight_start_date": "2025-02-01",
                    "flight_end_date": "2025-02-28",
                },
            }
        except Exception as e:
            return {"success": False, "message": f"Authentication failed: {str(e)}", "error": str(e)}


def create_agent_card() -> AgentCard:
    """Create the agent card describing capabilities.

    Returns:
        AgentCard with AdCP Sales Agent capabilities
    """
    server_url = os.getenv("FLY_APP_NAME")
    if server_url:
        server_url = f"https://{server_url}.fly.dev/a2a/"
    else:
        server_url = "https://adcp-sales-agent.fly.dev/a2a/"

    from a2a.types import AgentSkill

    return AgentCard(
        name="AdCP Sales Agent",
        description="AI agent for programmatic advertising campaigns via AdCP protocol",
        version="1.0.0",
        protocol_version="1.0",
        capabilities={
            "google_a2a_compatible": True,
            "parts_array_format": True,
            "supports_json_rpc": True,
        },
        default_input_modes=["message"],
        default_output_modes=["message"],
        skills=[
            # Core AdCP Media Buy Skills (6 total)
            AgentSkill(
                id="get_products",
                name="get_products",
                description="Browse available advertising products and inventory",
                tags=["products", "inventory", "catalog", "adcp"],
            ),
            AgentSkill(
                id="create_media_buy",
                name="create_media_buy",
                description="Create advertising campaigns with products, targeting, and budget",
                tags=["campaign", "media", "buy", "adcp"],
            ),
            AgentSkill(
                id="add_creative_assets",
                name="add_creative_assets",
                description="Upload and associate creative assets with media buys",
                tags=["creative", "assets", "upload", "adcp"],
            ),
            AgentSkill(
                id="approve_creative",
                name="approve_creative",
                description="Review and approve/reject creative assets (admin only)",
                tags=["creative", "approval", "review", "adcp"],
            ),
            AgentSkill(
                id="get_media_buy_status",
                name="get_media_buy_status",
                description="Check status and performance of media buys",
                tags=["status", "performance", "tracking", "adcp"],
            ),
            AgentSkill(
                id="optimize_media_buy",
                name="optimize_media_buy",
                description="Optimize media buy performance and targeting",
                tags=["optimization", "performance", "targeting", "adcp"],
            ),
            # Core AdCP Signals Skills (2 total)
            AgentSkill(
                id="get_signals",
                name="get_signals",
                description="Discover available targeting signals (audiences, contextual, etc.)",
                tags=["signals", "targeting", "discovery", "adcp"],
            ),
            AgentSkill(
                id="search_signals",
                name="search_signals",
                description="Search and filter targeting signals by criteria",
                tags=["signals", "search", "targeting", "adcp"],
            ),
            # Legacy Skills (for backward compatibility)
            AgentSkill(
                id="get_pricing",
                name="get_pricing",
                description="Get pricing information and rate cards",
                tags=["pricing", "cost", "budget", "legacy"],
            ),
            AgentSkill(
                id="get_targeting",
                name="get_targeting",
                description="Explore available targeting options",
                tags=["targeting", "audience", "demographics", "legacy"],
            ),
        ],
        url=server_url,
        authentication="bearer-token",
        documentation_url="https://github.com/your-org/adcp-sales-agent",
    )


def main():
    """Main entry point for the A2A server."""
    host = os.getenv("A2A_HOST", "0.0.0.0")
    port = int(os.getenv("A2A_PORT", "8091"))

    # Initialize components
    agent_card = create_agent_card()
    request_handler = AdCPRequestHandler()

    logger.info(f"Starting AdCP A2A Agent on {host}:{port}")
    logger.info("Using official a2a-sdk with A2AStarletteApplication")

    # Create Starlette application
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # Build the Starlette app with standard routing at /a2a
    app = a2a_app.build(
        agent_card_url="/.well-known/agent.json",
        rpc_url="/a2a",  # Use standard /a2a endpoint directly
        extended_agent_card_url="/agent.json",
    )

    # Add middleware for backward compatibility with numeric messageId
    @app.middleware("http")
    async def messageId_compatibility_middleware(request, call_next):
        """Middleware to handle both numeric and string messageId for backward compatibility."""
        import json

        # Only process JSON-RPC requests to /a2a
        if request.url.path == "/a2a" and request.method == "POST":
            # Read the body
            body = await request.body()
            try:
                data = json.loads(body)

                # Check if this is a JSON-RPC request with numeric messageId
                if isinstance(data, dict) and "params" in data:
                    params = data.get("params", {})
                    if "message" in params and isinstance(params["message"], dict):
                        message = params["message"]
                        # Convert numeric messageId to string if needed
                        if "messageId" in message and isinstance(message["messageId"], int | float):
                            logger.warning(
                                f"Converting numeric messageId {message['messageId']} to string for compatibility"
                            )
                            message["messageId"] = str(message["messageId"])
                            # Update the request body
                            body = json.dumps(data).encode()

                # Also handle the outer id field for JSON-RPC
                if "id" in data and isinstance(data["id"], int | float):
                    logger.warning(f"Converting numeric JSON-RPC id {data['id']} to string for compatibility")
                    data["id"] = str(data["id"])
                    body = json.dumps(data).encode()

            except (json.JSONDecodeError, KeyError):
                # Not JSON or doesn't have expected structure, pass through
                pass

            # Create new request with potentially modified body
            from starlette.requests import Request

            request = Request(request.scope, receive=lambda: {"type": "http.request", "body": body})

        response = await call_next(request)
        return response

    # Add authentication middleware for Bearer token extraction
    @app.middleware("http")
    async def auth_middleware(request, call_next):
        """Extract Bearer token and set authentication context for A2A requests."""
        # Only process A2A endpoint requests (handle both /a2a and /a2a/)
        if request.url.path in ["/a2a", "/a2a/"] and request.method == "POST":
            # Extract Bearer token from Authorization header (case-insensitive)
            auth_header = request.headers.get("authorization", "").strip()
            # Also try Authorization with capital A (case variations)
            if not auth_header:
                auth_header = request.headers.get("Authorization", "").strip()

            logger.info(
                f"Processing A2A request to {request.url.path} with auth header: {'Bearer...' if auth_header.startswith('Bearer ') else repr(auth_header[:20]) + '...' if auth_header else 'missing'}"
            )

            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer " prefix
                # Store token in thread-local storage for handler access
                _request_context.auth_token = token
                logger.info(f"Extracted Bearer token for A2A request: {token[:10]}...")
            else:
                logger.warning(f"A2A request to {request.url.path} missing Bearer token in Authorization header")
                _request_context.auth_token = None

        response = await call_next(request)

        # Clean up thread-local storage
        if hasattr(_request_context, "auth_token"):
            delattr(_request_context, "auth_token")

        return response

    # Add alias for agent-card.json (some clients look for this)
    @app.route("/.well-known/agent-card.json", methods=["GET"])
    async def agent_card_alias(request):
        """Alias for agent.json to support different client expectations."""
        from starlette.responses import JSONResponse

        return JSONResponse(agent_card.model_dump())

    # Run with uvicorn
    import uvicorn

    logger.info("Standard A2A endpoints: /.well-known/agent.json, /a2a, /agent.json")
    logger.info("JSON-RPC 2.0 support enabled at /a2a")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
