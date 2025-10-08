"""Creative formats management blueprint for admin UI."""

import json
import logging
import uuid
from datetime import UTC, datetime

# TODO: Missing module - these functions need to be implemented
# from creative_formats import discover_creative_formats_from_url, parse_creative_spec


# Placeholder implementations for missing functions
def parse_creative_spec(url):
    """Parse creative specification from URL - placeholder implementation."""
    return {"success": False, "error": "Creative format parsing not yet implemented", "url": url}


def discover_creative_formats_from_url(url):
    """Discover creative formats from URL - placeholder implementation."""
    return []


from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_, select

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import CreativeFormat, Tenant

logger = logging.getLogger(__name__)

# Create Blueprint
creatives_bp = Blueprint("creatives", __name__)


def _call_webhook_for_creative_status(webhook_url: str, creative_id: str, status: str, creative_data: dict = None):
    """Call webhook to notify about creative status change (AdCP task-status spec).

    Args:
        webhook_url: URL to POST notification to
        creative_id: Creative ID
        status: New status (approved, rejected, pending)
        creative_data: Optional creative data to include
    """
    import requests

    try:
        payload = {
            "object_type": "creative",
            "object_id": creative_id,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if creative_data:
            payload["creative_data"] = creative_data

        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code >= 400:
            logger.warning(
                f"Webhook call failed for creative {creative_id}: HTTP {response.status_code} - {response.text}"
            )
        else:
            logger.info(f"Successfully called webhook for creative {creative_id} status={status}")

    except Exception as e:
        logger.error(f"Error calling webhook for creative {creative_id}: {e}", exc_info=True)


@creatives_bp.route("/", methods=["GET"])
@require_tenant_access()
def index(tenant_id, **kwargs):
    """List creative formats (both standard and custom)."""
    with get_db_session() as db_session:
        # Get tenant name
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return "Tenant not found", 404

        tenant_name = tenant.name

        # Get all formats (standard + custom for this tenant)
        stmt = (
            select(CreativeFormat)
            .filter(or_(CreativeFormat.tenant_id.is_(None), CreativeFormat.tenant_id == tenant_id))
            .order_by(CreativeFormat.is_standard.desc(), CreativeFormat.type, CreativeFormat.name)
        )
        creative_formats = db_session.scalars(stmt).all()

        formats = []
        for cf in creative_formats:
            format_info = {
                "format_id": cf.format_id,
                "name": cf.name,
                "type": cf.type,
                "description": cf.description,
                "is_standard": cf.is_standard,
                "source_url": cf.source_url,
                "created_at": cf.created_at,
            }

            # Add dimensions or duration
            if cf.width and cf.height:  # width and height
                format_info["dimensions"] = f"{cf.width}x{cf.height}"
            elif cf.duration_seconds:  # duration
                format_info["duration"] = f"{cf.duration_seconds}s"

            formats.append(format_info)

    return render_template(
        "creative_formats.html",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        formats=formats,
    )


@creatives_bp.route("/review", methods=["GET"])
@require_tenant_access()
def review_creatives(tenant_id, **kwargs):
    """Unified creative management: view, review, and manage all creatives."""
    from src.core.database.models import Creative, CreativeAssignment, MediaBuy, Principal, Product

    with get_db_session() as db_session:
        # Get tenant
        stmt = select(Tenant).filter_by(tenant_id=tenant_id)
        tenant = db_session.scalars(stmt).first()
        if not tenant:
            return "Tenant not found", 404

        # Get all creatives ordered by status (pending first) then date
        stmt = select(Creative).filter_by(tenant_id=tenant_id).order_by(Creative.status, Creative.created_at.desc())
        creatives = db_session.scalars(stmt).all()

        # Build creative data with context
        creative_list = []
        for creative in creatives:
            # Get principal name
            stmt = select(Principal).filter_by(tenant_id=tenant_id, principal_id=creative.principal_id)
            principal = db_session.scalars(stmt).first()
            principal_name = principal.name if principal else creative.principal_id

            # Get all media buy assignments for this creative
            stmt = select(CreativeAssignment).filter_by(tenant_id=tenant_id, creative_id=creative.creative_id)
            assignments = db_session.scalars(stmt).all()

            # Get media buy details for each assignment
            media_buys = []
            for assignment in assignments:
                stmt = select(MediaBuy).filter_by(media_buy_id=assignment.media_buy_id)
                media_buy = db_session.scalars(stmt).first()
                if media_buy:
                    media_buys.append(
                        {
                            "media_buy_id": media_buy.media_buy_id,
                            "order_name": media_buy.order_name,
                            "package_id": assignment.package_id,
                            "status": media_buy.status,
                            "start_date": media_buy.start_date,
                            "end_date": media_buy.end_date,
                        }
                    )

            # Get promoted offering from first media buy (if any)
            promoted_offering = None
            if media_buys and media_buys[0]:
                stmt = select(MediaBuy).filter_by(media_buy_id=media_buys[0]["media_buy_id"])
                first_buy = db_session.scalars(stmt).first()
                if first_buy and first_buy.raw_request:
                    packages = first_buy.raw_request.get("packages", [])
                    if packages:
                        product_id = packages[0].get("product_id")
                        if product_id:
                            stmt = select(Product).filter_by(product_id=product_id)
                            product = db_session.scalars(stmt).first()
                            if product:
                                promoted_offering = product.name

            # Extract AI review reasoning from creative.data if available
            ai_reasoning = creative.data.get("ai_review_reasoning") if creative.data else None

            creative_list.append(
                {
                    "creative_id": creative.creative_id,
                    "name": creative.name,
                    "format": creative.format,
                    "status": creative.status,
                    "principal_name": principal_name,
                    "principal_id": creative.principal_id,
                    "group_id": creative.group_id,
                    "data": creative.data,
                    "created_at": creative.created_at,
                    "approved_at": creative.approved_at,
                    "approved_by": creative.approved_by,
                    "media_buys": media_buys,
                    "assignment_count": len(media_buys),
                    "promoted_offering": promoted_offering,
                    "ai_reasoning": ai_reasoning,
                }
            )

    return render_template(
        "creative_management.html",
        tenant_id=tenant_id,
        tenant_name=tenant.name,
        creatives=creative_list,
        has_ai_review=bool(tenant.gemini_api_key and tenant.creative_review_criteria),
        approval_mode=tenant.approval_mode,
    )


@creatives_bp.route("/list", methods=["GET"])
@require_tenant_access()
def list_creatives(tenant_id, **kwargs):
    """Redirect to unified creative management page."""
    return redirect(url_for("creatives.review_creatives", tenant_id=tenant_id))


@creatives_bp.route("/add/ai", methods=["GET"])
@require_tenant_access()
def add_ai(tenant_id, **kwargs):
    """Show AI-assisted creative format discovery form."""
    return render_template("creative_format_ai.html", tenant_id=tenant_id)


@creatives_bp.route("/analyze", methods=["POST"])
@require_tenant_access()
def analyze(tenant_id, **kwargs):
    """Analyze creative format with AI."""
    try:
        url = request.form.get("url", "").strip()
        if not url:
            return jsonify({"error": "URL is required"}), 400

        # Use the creative format parser
        result = parse_creative_spec(url)

        if result.get("error"):
            return jsonify({"error": result["error"]}), 400

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error analyzing creative format: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/save", methods=["POST"])
@require_tenant_access()
def save(tenant_id, **kwargs):
    """Save a creative format to the database."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        format_id = f"fmt_{uuid.uuid4().hex[:8]}"

        with get_db_session() as db_session:
            # Check if format already exists
            stmt = select(CreativeFormat).filter_by(name=data.get("name"), tenant_id=tenant_id)
            existing = db_session.scalars(stmt).first()

            if existing:
                return jsonify({"error": f"Format '{data.get('name')}' already exists"}), 400

            # Create new format
            creative_format = CreativeFormat(
                format_id=format_id,
                tenant_id=tenant_id,
                name=data.get("name"),
                type=data.get("type"),
                description=data.get("description"),
                width=data.get("width"),
                height=data.get("height"),
                duration_seconds=data.get("duration_seconds"),
                max_file_size_kb=data.get("max_file_size_kb"),
                supported_mime_types=json.dumps(data.get("supported_mime_types", [])),
                is_standard=False,
                source_url=data.get("source_url"),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db_session.add(creative_format)
            db_session.commit()

            return jsonify({"success": True, "format_id": format_id})

    except Exception as e:
        logger.error(f"Error saving creative format: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/sync-standard", methods=["POST"])
@require_tenant_access()
def sync_standard(tenant_id, **kwargs):
    """Sync standard formats from adcontextprotocol.org."""
    try:
        # This would normally fetch from the protocol site
        # For now, return success with count of 0
        return jsonify({"success": True, "count": 0, "message": "Standard formats sync not yet implemented"})

    except Exception as e:
        logger.error(f"Error syncing standard formats: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@creatives_bp.route("/discover", methods=["POST"])
@require_tenant_access()
def discover(tenant_id, **kwargs):
    """Discover multiple creative formats from a URL."""
    try:
        data = request.get_json()
        url = data.get("url", "").strip()

        if not url:
            return jsonify({"error": "URL is required"}), 400

        # Discover formats from the URL
        formats = discover_creative_formats_from_url(url)

        if not formats:
            return jsonify({"error": "No creative formats found at the URL"}), 404

        return jsonify({"formats": formats})

    except Exception as e:
        logger.error(f"Error discovering formats: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/save-multiple", methods=["POST"])
@require_tenant_access()
def save_multiple(tenant_id, **kwargs):
    """Save multiple discovered creative formats to the database."""
    try:
        data = request.get_json()
        formats = data.get("formats", [])

        if not formats:
            return jsonify({"error": "No formats provided"}), 400

        saved_count = 0
        skipped_count = 0
        errors = []

        with get_db_session() as db_session:
            for format_data in formats:
                # Check if format already exists
                stmt = select(CreativeFormat).filter_by(name=format_data.get("name"), tenant_id=tenant_id)
                existing = db_session.scalars(stmt).first()

                if existing:
                    skipped_count += 1
                    continue

                try:
                    format_id = f"fmt_{uuid.uuid4().hex[:8]}"
                    creative_format = CreativeFormat(
                        format_id=format_id,
                        tenant_id=tenant_id,
                        name=format_data.get("name"),
                        type=format_data.get("type"),
                        description=format_data.get("description"),
                        width=format_data.get("width"),
                        height=format_data.get("height"),
                        duration_seconds=format_data.get("duration_seconds"),
                        max_file_size_kb=format_data.get("max_file_size_kb"),
                        supported_mime_types=json.dumps(format_data.get("supported_mime_types", [])),
                        is_standard=False,
                        source_url=format_data.get("source_url"),
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )

                    db_session.add(creative_format)
                    saved_count += 1

                except Exception as e:
                    errors.append(f"Error saving {format_data.get('name')}: {str(e)}")

            db_session.commit()

        return jsonify(
            {
                "success": True,
                "saved": saved_count,
                "skipped": skipped_count,
                "errors": errors,
            }
        )

    except Exception as e:
        logger.error(f"Error saving multiple formats: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/<format_id>", methods=["GET"])
@require_tenant_access()
def get_format(tenant_id, format_id, **kwargs):
    """Get a specific creative format for editing."""
    with get_db_session() as db_session:
        creative_format = db_session.scalars(select(CreativeFormat).filter_by(format_id=format_id)).first()

        if not creative_format:
            return jsonify({"error": "Format not found"}), 404

        # Check access
        if creative_format.tenant_id and creative_format.tenant_id != tenant_id:
            return jsonify({"error": "Access denied"}), 403

        format_data = {
            "format_id": creative_format.format_id,
            "name": creative_format.name,
            "type": creative_format.type,
            "description": creative_format.description,
            "width": creative_format.width,
            "height": creative_format.height,
            "duration_seconds": creative_format.duration_seconds,
            "max_file_size_kb": creative_format.max_file_size_kb,
            "supported_mime_types": json.loads(creative_format.supported_mime_types or "[]"),
            "is_standard": creative_format.is_standard,
            "source_url": creative_format.source_url,
        }

        return jsonify(format_data)


@creatives_bp.route("/<format_id>/edit", methods=["GET"])
@require_tenant_access()
def edit_format(tenant_id, format_id, **kwargs):
    """Display the edit creative format page."""
    with get_db_session() as db_session:
        creative_format = db_session.scalars(select(CreativeFormat).filter_by(format_id=format_id)).first()

        if not creative_format:
            flash("Format not found", "error")
            return redirect(url_for("creatives.index", tenant_id=tenant_id))

        # Check access
        if creative_format.tenant_id and creative_format.tenant_id != tenant_id:
            flash("Access denied", "error")
            return redirect(url_for("creatives.index", tenant_id=tenant_id))

        # Prepare format data for template
        format_data = {
            "format_id": creative_format.format_id,
            "name": creative_format.name,
            "type": creative_format.type,
            "description": creative_format.description,
            "width": creative_format.width,
            "height": creative_format.height,
            "duration_seconds": creative_format.duration_seconds,
            "max_file_size_kb": creative_format.max_file_size_kb,
            "supported_mime_types": json.loads(creative_format.supported_mime_types or "[]"),
            "is_standard": creative_format.is_standard,
            "source_url": creative_format.source_url,
        }

        # Get tenant name
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        tenant_name = tenant.name if tenant else ""

    return render_template(
        "edit_creative_format.html",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        format=format_data,
    )


@creatives_bp.route("/<format_id>/update", methods=["POST"])
@require_tenant_access()
def update_format(tenant_id, format_id, **kwargs):
    """Update a creative format."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        with get_db_session() as db_session:
            creative_format = db_session.scalars(select(CreativeFormat).filter_by(format_id=format_id)).first()

            if not creative_format:
                return jsonify({"error": "Format not found"}), 404

            # Check access
            if creative_format.tenant_id and creative_format.tenant_id != tenant_id:
                return jsonify({"error": "Access denied"}), 403

            # Don't allow editing standard formats
            if creative_format.is_standard:
                return jsonify({"error": "Cannot edit standard formats"}), 403

            # Update fields
            creative_format.name = data.get("name", creative_format.name)
            creative_format.type = data.get("type", creative_format.type)
            creative_format.description = data.get("description", creative_format.description)
            creative_format.width = data.get("width", creative_format.width)
            creative_format.height = data.get("height", creative_format.height)
            creative_format.duration_seconds = data.get("duration_seconds", creative_format.duration_seconds)
            creative_format.max_file_size_kb = data.get("max_file_size_kb", creative_format.max_file_size_kb)
            creative_format.supported_mime_types = json.dumps(data.get("supported_mime_types", []))
            creative_format.updated_at = datetime.now(UTC)

            db_session.commit()

            return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error updating creative format: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/<format_id>/delete", methods=["POST"])
@require_tenant_access()
def delete_format(tenant_id, format_id, **kwargs):
    """Delete a creative format."""
    try:
        with get_db_session() as db_session:
            creative_format = db_session.scalars(select(CreativeFormat).filter_by(format_id=format_id)).first()

            if not creative_format:
                return jsonify({"error": "Format not found"}), 404

            # Check access
            if creative_format.tenant_id and creative_format.tenant_id != tenant_id:
                return jsonify({"error": "Access denied"}), 403

            # Don't allow deleting standard formats
            if creative_format.is_standard:
                return jsonify({"error": "Cannot delete standard formats"}), 403

            db_session.delete(creative_format)
            db_session.commit()

            return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error deleting creative format: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/review/<creative_id>/approve", methods=["POST"])
@require_tenant_access()
def approve_creative(tenant_id, creative_id, **kwargs):
    """Approve a creative."""
    from src.core.database.models import Creative

    try:
        data = request.get_json() or {}
        approved_by = data.get("approved_by", "admin")

        with get_db_session() as db_session:
            creative = db_session.query(Creative).filter_by(tenant_id=tenant_id, creative_id=creative_id).first()

            if not creative:
                return jsonify({"error": "Creative not found"}), 404

            # Update creative status
            creative.status = "approved"
            creative.approved_at = datetime.now(UTC)
            creative.approved_by = approved_by

            db_session.commit()

            # Find webhook_url from workflow step if it exists
            from src.core.database.models import ObjectWorkflowMapping, WorkflowStep

            stmt = select(ObjectWorkflowMapping).filter_by(object_type="creative", object_id=creative_id)
            mapping = db_session.scalars(stmt).first()

            webhook_url = None
            if mapping:
                stmt = select(WorkflowStep).filter_by(step_id=mapping.step_id)
                workflow_step = db_session.scalars(stmt).first()
                if workflow_step and workflow_step.request_data:
                    webhook_url = workflow_step.request_data.get("webhook_url")

            # Call webhook if configured
            if webhook_url:
                creative_data = {
                    "creative_id": creative.creative_id,
                    "name": creative.name,
                    "format": creative.format,
                    "status": "approved",
                    "approved_by": approved_by,
                    "approved_at": creative.approved_at.isoformat(),
                }
                _call_webhook_for_creative_status(webhook_url, creative_id, "approved", creative_data)

            # Send Slack notification if configured
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if tenant and tenant.slack_webhook_url:
                from src.services.slack_notifier import get_slack_notifier

                tenant_config = {"features": {"slack_webhook_url": tenant.slack_webhook_url}}
                notifier = get_slack_notifier(tenant_config)

                # Get principal name
                from src.core.database.models import Principal

                principal = (
                    db_session.query(Principal)
                    .filter_by(tenant_id=tenant_id, principal_id=creative.principal_id)
                    .first()
                )
                principal_name = principal.name if principal else creative.principal_id

                notifier.send_message(
                    f"✅ Creative approved: {creative.name} ({creative.format}) from {principal_name}"
                )

            return jsonify({"success": True, "status": "approved"})

    except Exception as e:
        logger.error(f"Error approving creative: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@creatives_bp.route("/review/<creative_id>/reject", methods=["POST"])
@require_tenant_access()
def reject_creative(tenant_id, creative_id, **kwargs):
    """Reject a creative with comments."""
    from src.core.database.models import Creative

    try:
        data = request.get_json() or {}
        rejected_by = data.get("rejected_by", "admin")
        rejection_reason = data.get("rejection_reason", "")

        if not rejection_reason:
            return jsonify({"error": "Rejection reason is required"}), 400

        with get_db_session() as db_session:
            creative = db_session.query(Creative).filter_by(tenant_id=tenant_id, creative_id=creative_id).first()

            if not creative:
                return jsonify({"error": "Creative not found"}), 404

            # Update creative status
            creative.status = "rejected"
            creative.approved_at = datetime.now(UTC)
            creative.approved_by = rejected_by

            # Store rejection reason in data field
            if not creative.data:
                creative.data = {}
            creative.data["rejection_reason"] = rejection_reason
            creative.data["rejected_at"] = datetime.now(UTC).isoformat()

            # Mark data field as modified for JSONB update
            from sqlalchemy.orm import attributes

            attributes.flag_modified(creative, "data")

            db_session.commit()

            # Find webhook_url from workflow step if it exists
            from src.core.database.models import ObjectWorkflowMapping, WorkflowStep

            stmt = select(ObjectWorkflowMapping).filter_by(object_type="creative", object_id=creative_id)
            mapping = db_session.scalars(stmt).first()

            webhook_url = None
            if mapping:
                stmt = select(WorkflowStep).filter_by(step_id=mapping.step_id)
                workflow_step = db_session.scalars(stmt).first()
                if workflow_step and workflow_step.request_data:
                    webhook_url = workflow_step.request_data.get("webhook_url")

            # Call webhook if configured
            if webhook_url:
                creative_data = {
                    "creative_id": creative.creative_id,
                    "name": creative.name,
                    "format": creative.format,
                    "status": "rejected",
                    "rejected_by": rejected_by,
                    "rejection_reason": rejection_reason,
                    "rejected_at": creative.data["rejected_at"],
                }
                _call_webhook_for_creative_status(webhook_url, creative_id, "rejected", creative_data)

            # Send Slack notification if configured
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if tenant and tenant.slack_webhook_url:
                from src.services.slack_notifier import get_slack_notifier

                tenant_config = {"features": {"slack_webhook_url": tenant.slack_webhook_url}}
                notifier = get_slack_notifier(tenant_config)

                # Get principal name
                from src.core.database.models import Principal

                principal = (
                    db_session.query(Principal)
                    .filter_by(tenant_id=tenant_id, principal_id=creative.principal_id)
                    .first()
                )
                principal_name = principal.name if principal else creative.principal_id

                notifier.send_message(
                    f"❌ Creative rejected: {creative.name} ({creative.format}) from {principal_name}\nReason: {rejection_reason}"
                )

            return jsonify({"success": True, "status": "rejected"})

    except Exception as e:
        logger.error(f"Error rejecting creative: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _ai_review_creative_impl(tenant_id, creative_id, db_session=None, promoted_offering=None):
    """Internal implementation: Run AI review and return dict result.

    Returns dict with keys:
    - status: "approved", "pending", or "rejected"
    - reason: explanation from AI
    - confidence: "high", "medium", or "low"
    - error: error message if failed
    """
    from sqlalchemy import select

    from src.core.database.models import Creative

    try:
        # Use provided session or create new one
        should_close = False
        if db_session is None:
            db_session = get_db_session().__enter__()
            should_close = True

        try:
            stmt = select(Tenant).filter_by(tenant_id=tenant_id)
            tenant = db_session.scalars(stmt).first()
            if not tenant:
                return {"status": "pending", "error": "Tenant not found", "reason": "Configuration error"}

            if not tenant.gemini_api_key:
                return {
                    "status": "pending",
                    "error": "Gemini API key not configured",
                    "reason": "AI review unavailable - requires manual approval",
                }

            if not tenant.creative_review_criteria:
                return {
                    "status": "pending",
                    "error": "Creative review criteria not configured",
                    "reason": "AI review unavailable - requires manual approval",
                }

            stmt = select(Creative).filter_by(tenant_id=tenant_id, creative_id=creative_id)
            creative = db_session.scalars(stmt).first()

            if not creative:
                return {"status": "pending", "error": "Creative not found", "reason": "Configuration error"}

            # Get media buy and promoted offering if not provided
            if promoted_offering is None:
                promoted_offering = "Unknown"
                if creative.data.get("media_buy_id"):
                    from src.core.database.models import MediaBuy, Product

                    stmt = select(MediaBuy).filter_by(media_buy_id=creative.data["media_buy_id"])
                    media_buy = db_session.scalars(stmt).first()
                    if media_buy and media_buy.raw_request:
                        packages = media_buy.raw_request.get("packages", [])
                        if packages:
                            product_id = packages[0].get("product_id")
                            if product_id:
                                stmt = select(Product).filter_by(product_id=product_id)
                                product = db_session.scalars(stmt).first()
                                if product:
                                    promoted_offering = product.name

            # Build review prompt with three-state instructions
            review_prompt = f"""You are reviewing a creative asset for approval.

Review Criteria:
{tenant.creative_review_criteria}

Creative Details:
- Name: {creative.name}
- Format: {creative.format}
- Promoted Offering: {promoted_offering}
- Creative Data: {json.dumps(creative.data, indent=2)}

Based on the review criteria, determine the appropriate action for this creative.
You MUST respond with one of three decisions:
- APPROVE: Creative clearly meets all criteria
- REQUIRE HUMAN APPROVAL: Unsure or needs human judgment
- REJECT: Creative clearly violates criteria

Respond with a JSON object containing:
{{
    "decision": "APPROVE" or "REQUIRE HUMAN APPROVAL" or "REJECT",
    "reason": "brief explanation of the decision",
    "confidence": "high/medium/low"
}}
"""

            # Call Gemini API
            import google.generativeai as genai

            genai.configure(api_key=tenant.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash-lite")

            response = model.generate_content(review_prompt)
            response_text = response.text.strip()

            # Parse JSON response
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            review_result = json.loads(response_text)

            # Map AI decision to status
            decision = review_result.get("decision", "REQUIRE HUMAN APPROVAL").upper()
            if "APPROVE" in decision and "REQUIRE" not in decision:
                status = "approved"
            elif "REJECT" in decision:
                status = "rejected"
            else:
                status = "pending"

            return {
                "status": status,
                "reason": review_result.get("reason", ""),
                "confidence": review_result.get("confidence", "medium"),
            }

        finally:
            if should_close:
                db_session.close()

    except Exception as e:
        logger.error(f"Error running AI review: {e}", exc_info=True)
        return {"status": "pending", "error": str(e), "reason": "AI review failed - requires manual approval"}


@creatives_bp.route("/review/<creative_id>/ai-review", methods=["POST"])
@require_tenant_access()
def ai_review_creative(tenant_id, creative_id, **kwargs):
    """Flask endpoint wrapper for AI review."""
    result = _ai_review_creative_impl(tenant_id, creative_id)

    if "error" in result:
        return jsonify({"success": False, "error": result["error"]}), 400

    return jsonify(
        {
            "success": True,
            "status": result["status"],
            "reason": result["reason"],
            "confidence": result.get("confidence", "medium"),
        }
    )
