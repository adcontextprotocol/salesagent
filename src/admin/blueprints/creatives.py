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
from sqlalchemy import or_

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import CreativeFormat, Tenant

logger = logging.getLogger(__name__)

# Create Blueprint
creatives_bp = Blueprint("creatives", __name__)


@creatives_bp.route("/", methods=["GET"])
@require_tenant_access()
def index(tenant_id, **kwargs):
    """List creative formats (both standard and custom)."""
    with get_db_session() as db_session:
        # Get tenant name
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            return "Tenant not found", 404

        tenant_name = tenant.name

        # Get all formats (standard + custom for this tenant)
        creative_formats = (
            db_session.query(CreativeFormat)
            .filter(or_(CreativeFormat.tenant_id.is_(None), CreativeFormat.tenant_id == tenant_id))
            .order_by(CreativeFormat.is_standard.desc(), CreativeFormat.type, CreativeFormat.name)
            .all()
        )

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


@creatives_bp.route("/list", methods=["GET"])
@require_tenant_access()
def list_creatives(tenant_id, **kwargs):
    """List all uploaded creatives and their media buy associations."""
    from src.core.database.models import Creative, CreativeAssignment, MediaBuy, Principal

    with get_db_session() as db_session:
        # Get tenant name
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            return "Tenant not found", 404

        tenant_name = tenant.name

        # Get all creatives for this tenant with their assignments
        creatives = db_session.query(Creative).filter_by(tenant_id=tenant_id).order_by(Creative.created_at.desc()).all()

        # Build creative data with media buy associations
        creative_list = []
        for creative in creatives:
            # Get principal name
            principal = (
                db_session.query(Principal).filter_by(tenant_id=tenant_id, principal_id=creative.principal_id).first()
            )
            principal_name = principal.name if principal else creative.principal_id

            # Get all assignments for this creative
            assignments = (
                db_session.query(CreativeAssignment)
                .filter_by(tenant_id=tenant_id, creative_id=creative.creative_id)
                .all()
            )

            # Get media buy details for each assignment
            media_buys = []
            for assignment in assignments:
                media_buy = db_session.query(MediaBuy).filter_by(media_buy_id=assignment.media_buy_id).first()
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

            creative_list.append(
                {
                    "creative_id": creative.creative_id,
                    "name": creative.name,
                    "format": creative.format,
                    "status": creative.status,
                    "principal_name": principal_name,
                    "principal_id": creative.principal_id,
                    "group_id": creative.group_id,
                    "created_at": creative.created_at,
                    "approved_at": creative.approved_at,
                    "approved_by": creative.approved_by,
                    "media_buys": media_buys,
                    "assignment_count": len(media_buys),
                }
            )

    return render_template(
        "creatives_list.html",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        creatives=creative_list,
    )


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
            existing = db_session.query(CreativeFormat).filter_by(name=data.get("name"), tenant_id=tenant_id).first()

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
                existing = (
                    db_session.query(CreativeFormat)
                    .filter_by(name=format_data.get("name"), tenant_id=tenant_id)
                    .first()
                )

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
        creative_format = db_session.query(CreativeFormat).filter_by(format_id=format_id).first()

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
        creative_format = db_session.query(CreativeFormat).filter_by(format_id=format_id).first()

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
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
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
            creative_format = db_session.query(CreativeFormat).filter_by(format_id=format_id).first()

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
            creative_format = db_session.query(CreativeFormat).filter_by(format_id=format_id).first()

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
