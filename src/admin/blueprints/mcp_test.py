"""McpTest management blueprint."""

import logging

from flask import Blueprint, jsonify

from src.admin.utils import require_tenant_access  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

# Create blueprint
mcp_test_bp = Blueprint("mcp_test", __name__)


@mcp_test_bp.route("/mcp-test", methods=["GET"])
@require_tenant_access()
def mcp_test(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501
