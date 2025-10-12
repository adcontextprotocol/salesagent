"""
Response factory for creating AdCP-compliant response objects.

This module provides factory functions that ensure all required fields are present
in response objects, preventing validation errors at runtime.

The factory pattern ensures:
1. All required fields are explicitly handled
2. Sensible defaults are provided where appropriate
3. Type safety and validation happen at creation time
4. Consistency across all response creation sites
"""

from datetime import datetime
from typing import Any

from src.core.schemas import CreateMediaBuyResponse, Error


def create_media_buy_response(
    *,
    buyer_ref: str,
    status: str,
    media_buy_id: str | None = None,
    task_id: str | None = None,
    creative_deadline: datetime | None = None,
    packages: list[dict[str, Any]] | None = None,
    errors: list[Error] | None = None,
    workflow_step_id: str | None = None,
    adcp_version: str = "2.3.0",
) -> CreateMediaBuyResponse:
    """
    Create a CreateMediaBuyResponse with all required fields.

    This factory function ensures buyer_ref and status (the two required fields per AdCP spec)
    are always provided, preventing validation errors.

    Args:
        buyer_ref: REQUIRED - Buyer reference for tracking (cannot be None)
        status: REQUIRED - Task status (submitted, working, input-required, completed, failed, etc.)
        media_buy_id: Optional media buy identifier
        task_id: Optional task identifier for async operations
        creative_deadline: Optional deadline for creative submission
        packages: Optional list of created packages with IDs
        errors: Optional list of errors if operation failed
        workflow_step_id: Optional workflow step ID (internal use)
        adcp_version: AdCP protocol version (default: 2.3.0)

    Returns:
        CreateMediaBuyResponse with all required fields populated

    Raises:
        ValueError: If buyer_ref or status is None/empty

    Example:
        >>> # Success case
        >>> response = create_media_buy_response(
        ...     buyer_ref="campaign_123",
        ...     status="completed",
        ...     media_buy_id="mb_456"
        ... )
        >>>
        >>> # Failure case
        >>> response = create_media_buy_response(
        ...     buyer_ref="campaign_123",
        ...     status="failed",
        ...     errors=[Error(code="validation_error", message="Invalid budget")]
        ... )
        >>>
        >>> # Approval required case
        >>> response = create_media_buy_response(
        ...     buyer_ref="campaign_123",
        ...     status="input-required",
        ...     task_id="task_789"
        ... )
    """
    # Validate required fields
    if not buyer_ref:
        raise ValueError(
            "buyer_ref is required for CreateMediaBuyResponse. "
            "This should be taken from the request object (req.buyer_ref)"
        )

    if not status:
        raise ValueError(
            "status is required for CreateMediaBuyResponse. "
            "Must be one of: submitted, working, input-required, completed, failed, rejected, auth-required"
        )

    # Validate status value
    valid_statuses = [
        "submitted",
        "working",
        "input-required",
        "completed",
        "failed",
        "canceled",
        "rejected",
        "auth-required",
    ]
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    # Create response with all fields
    return CreateMediaBuyResponse(
        adcp_version=adcp_version,
        status=status,
        buyer_ref=buyer_ref,
        media_buy_id=media_buy_id,
        task_id=task_id,
        creative_deadline=creative_deadline,
        packages=packages or [],
        errors=errors,
        workflow_step_id=workflow_step_id,
    )


def create_media_buy_error_response(
    *,
    buyer_ref: str,
    error_code: str,
    error_message: str,
    status: str = "failed",
    adcp_version: str = "2.3.0",
) -> CreateMediaBuyResponse:
    """
    Create an error response for create_media_buy operations.

    Convenience function for creating error responses with proper structure.

    Args:
        buyer_ref: REQUIRED - Buyer reference from request
        error_code: Error code (validation_error, authentication_error, etc.)
        error_message: Human-readable error description
        status: Status to return (default: failed)
        adcp_version: AdCP protocol version (default: 2.3.0)

    Returns:
        CreateMediaBuyResponse with error populated

    Example:
        >>> response = create_media_buy_error_response(
        ...     buyer_ref=req.buyer_ref,
        ...     error_code="validation_error",
        ...     error_message="Budget exceeds maximum allowed"
        ... )
    """
    return create_media_buy_response(
        buyer_ref=buyer_ref,
        status=status,
        adcp_version=adcp_version,
        errors=[Error(code=error_code, message=error_message)],
    )


def create_media_buy_approval_response(
    *,
    buyer_ref: str,
    media_buy_id: str,
    task_id: str | None = None,
    workflow_step_id: str | None = None,
    adcp_version: str = "2.3.0",
) -> CreateMediaBuyResponse:
    """
    Create a response for media buy requiring approval.

    Args:
        buyer_ref: REQUIRED - Buyer reference from request
        media_buy_id: Pending media buy ID
        task_id: Optional task ID for tracking approval
        workflow_step_id: Optional workflow step ID
        adcp_version: AdCP protocol version (default: 2.3.0)

    Returns:
        CreateMediaBuyResponse with input-required status

    Example:
        >>> response = create_media_buy_approval_response(
        ...     buyer_ref=req.buyer_ref,
        ...     media_buy_id="mb_pending_123"
        ... )
    """
    return create_media_buy_response(
        buyer_ref=buyer_ref,
        status="input-required",
        media_buy_id=media_buy_id,
        task_id=task_id,
        workflow_step_id=workflow_step_id,
        adcp_version=adcp_version,
    )


# Export all factory functions
__all__ = [
    "create_media_buy_response",
    "create_media_buy_error_response",
    "create_media_buy_approval_response",
]
