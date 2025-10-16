"""Admin UI action logging decorator.

Automatically logs admin UI actions to the audit_logs table for compliance and visibility.
"""

import logging
from functools import wraps

from flask import request, session

logger = logging.getLogger(__name__)


def log_admin_action(operation_name: str, extract_details: callable = None):
    """Decorator to log admin UI actions to audit_logs table.

    Args:
        operation_name: Name of the operation (e.g., "update_tenant_settings")
        extract_details: Optional function to extract details from request/response
                        Signature: extract_details(result, **kwargs) -> dict

    Usage:
        @log_admin_action("update_tenant_settings")
        def update_settings(tenant_id):
            # ... implementation ...
            return result

        @log_admin_action("create_product", extract_details=lambda r, **kw: {"product_id": kw.get("product_id")})
        def create_product(tenant_id, product_id):
            # ... implementation ...
            return result
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from src.core.audit_logger import get_audit_logger

            # Get user from session
            user_info = session.get("user", {})
            if isinstance(user_info, dict):
                user_email = user_info.get("email", "unknown")
            else:
                user_email = str(user_info) if user_info else "unknown"

            # Get tenant_id from kwargs (most admin routes have this)
            tenant_id = kwargs.get("tenant_id")

            # Call the actual route function
            try:
                result = f(*args, **kwargs)
                success = True
                error_message = None
            except Exception as e:
                # Log failed actions too
                result = None
                success = False
                error_message = str(e)
                # Re-raise to let Flask handle it
                raise
            finally:
                # Log the admin action (even if it failed)
                if tenant_id:
                    try:
                        audit_logger = get_audit_logger("AdminUI", tenant_id)

                        # Extract additional details if provided
                        details = {"user": user_email, "action": operation_name, "method": request.method}

                        if extract_details and callable(extract_details):
                            try:
                                extracted = extract_details(result, **kwargs)
                                if isinstance(extracted, dict):
                                    details.update(extracted)
                            except Exception as e:
                                logger.warning(f"Failed to extract details for {operation_name}: {e}")

                        # Add form data for POST requests (sanitized)
                        if request.method == "POST" and request.form:
                            # Only include non-sensitive form fields
                            safe_fields = {}
                            sensitive_keys = {"password", "secret", "token", "key", "credential"}
                            for key, value in request.form.items():
                                if not any(sensitive in key.lower() for sensitive in sensitive_keys):
                                    # Truncate long values
                                    safe_fields[key] = str(value)[:100] if len(str(value)) > 100 else str(value)
                            if safe_fields:
                                details["form_data"] = safe_fields

                        audit_logger.log_operation(
                            operation=f"AdminUI.{operation_name}",
                            principal_name=user_email,
                            principal_id=user_email,
                            adapter_id="admin_ui",
                            success=success,
                            details=details,
                            error=error_message,
                            tenant_id=tenant_id,
                        )
                    except Exception as e:
                        # Don't fail the request if audit logging fails
                        logger.warning(f"Failed to write admin audit log for {operation_name}: {e}")

            return result

        return decorated_function

    return decorator
