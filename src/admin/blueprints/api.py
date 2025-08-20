"""API management blueprint."""

import logging
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, text

from database_session import get_db_session
from models import MediaBuy, Principal, Product, SuperadminConfig
from src.admin.utils import require_auth

logger = logging.getLogger(__name__)

# Create blueprint
api_bp = Blueprint("api", __name__)


@api_bp.route("/health", methods=["GET"])
def api_health():
    """API health check endpoint."""
    try:
        with get_db_session() as db_session:
            db_session.execute(text("SELECT 1"))
            return jsonify({"status": "healthy"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy"}), 500


@api_bp.route("/tenant/<tenant_id>/revenue-chart")
@require_auth()
def revenue_chart_api(tenant_id):
    """API endpoint for revenue chart data."""
    period = request.args.get("period", "7d")

    # Parse period
    if period == "7d":
        days = 7
    elif period == "30d":
        days = 30
    elif period == "90d":
        days = 90
    else:
        days = 7

    with get_db_session() as db_session:
        # Calculate date range
        date_start = datetime.now(UTC) - timedelta(days=days)

        # Query revenue by principal
        results = (
            db_session.query(Principal.name, func.sum(MediaBuy.budget).label("revenue"))
            .join(
                MediaBuy,
                (MediaBuy.principal_id == Principal.principal_id) & (MediaBuy.tenant_id == Principal.tenant_id),
            )
            .filter(
                MediaBuy.tenant_id == tenant_id,
                MediaBuy.created_at >= date_start,
                MediaBuy.status.in_(["active", "completed"]),
            )
            .group_by(Principal.name)
            .order_by(func.sum(MediaBuy.budget).desc())
            .limit(10)
            .all()
        )

        labels = []
        values = []
        for name, revenue in results:
            labels.append(name or "Unknown")
            values.append(float(revenue) if revenue else 0.0)

        return jsonify({"labels": labels, "values": values})


@api_bp.route("/oauth/status", methods=["GET"])
@require_auth()
def oauth_status():
    """Check if OAuth credentials are properly configured for GAM."""
    try:
        # Check for GAM OAuth credentials in superadmin_config table (as per original implementation)
        with get_db_session() as db_session:
            client_id_row = (
                db_session.query(SuperadminConfig.config_value).filter_by(config_key="gam_oauth_client_id").first()
            )

            client_secret_row = (
                db_session.query(SuperadminConfig.config_value).filter_by(config_key="gam_oauth_client_secret").first()
            )

        if client_id_row and client_id_row[0] and client_secret_row and client_secret_row[0]:
            # Credentials exist in database
            client_id = client_id_row[0]
            return jsonify(
                {
                    "configured": True,
                    "client_id_prefix": client_id[:20] if len(client_id) > 20 else client_id,
                    "has_secret": True,
                    "source": "database",
                }
            )
        else:
            # No credentials found in database
            return jsonify(
                {
                    "configured": False,
                    "error": "GAM OAuth credentials not configured in superadmin settings.",
                    "help": "Super admins can configure GAM OAuth credentials in the superadmin settings page.",
                }
            )

    except Exception as e:
        logger.error(f"Error checking OAuth status: {e}")
        return (
            jsonify(
                {
                    "configured": False,
                    "error": f"Error checking OAuth configuration: {str(e)}",
                }
            ),
            500,
        )


@api_bp.route("/tenant/<tenant_id>/products/suggestions", methods=["GET"])
@require_auth()
def get_product_suggestions(tenant_id):
    """API endpoint to get product suggestions based on industry and criteria."""
    try:
        from default_products import (
            get_default_products,
            get_industry_specific_products,
        )

        # Get query parameters
        industry = request.args.get("industry")
        include_standard = request.args.get("include_standard", "true").lower() == "true"
        delivery_type = request.args.get("delivery_type")  # 'guaranteed', 'non_guaranteed', or None for all
        max_cpm = request.args.get("max_cpm", type=float)
        formats = request.args.getlist("formats")  # Can specify multiple format IDs

        # Get suggestions
        suggestions = []

        # Get industry-specific products if industry specified
        if industry:
            industry_products = get_industry_specific_products(industry)
            suggestions.extend(industry_products)
        elif include_standard:
            # If no industry specified but standard requested, get default products
            suggestions.extend(get_default_products())

        # Filter suggestions based on criteria
        filtered_suggestions = []
        for product in suggestions:
            # Filter by delivery type
            if delivery_type and product.get("delivery_type") != delivery_type:
                continue

            # Filter by max CPM
            if max_cpm:
                if product.get("cpm") and product["cpm"] > max_cpm:
                    continue
                elif product.get("price_guidance"):
                    if product["price_guidance"]["min"] > max_cpm:
                        continue

            # Filter by formats
            if formats:
                product_formats = set(product.get("formats", []))
                requested_formats = set(formats)
                if not product_formats.intersection(requested_formats):
                    continue

            filtered_suggestions.append(product)

        # Sort suggestions by relevance
        # Prioritize: 1) Industry-specific, 2) Lower CPM, 3) More formats
        def sort_key(product):
            is_industry_specific = product["product_id"] not in [p["product_id"] for p in get_default_products()]
            avg_cpm = (
                product.get("cpm", 0)
                or (product.get("price_guidance", {}).get("min", 0) + product.get("price_guidance", {}).get("max", 0))
                / 2
            )
            format_count = len(product.get("formats", []))
            return (-int(is_industry_specific), avg_cpm, -format_count)

        filtered_suggestions.sort(key=sort_key)

        # Check existing products to mark which are already created
        with get_db_session() as db_session:
            existing_products = db_session.query(Product.product_id).filter_by(tenant_id=tenant_id).all()
            existing_ids = {product[0] for product in existing_products}

        # Add metadata to suggestions
        for suggestion in filtered_suggestions:
            suggestion["already_exists"] = suggestion["product_id"] in existing_ids
            suggestion["is_industry_specific"] = suggestion["product_id"] not in [
                p["product_id"] for p in get_default_products()
            ]

            # Calculate match score (0-100)
            score = 100
            if delivery_type and suggestion.get("delivery_type") == delivery_type:
                score += 20
            if formats:
                matching_formats = len(set(suggestion.get("formats", [])).intersection(set(formats)))
                score += matching_formats * 10
            if industry and suggestion["is_industry_specific"]:
                score += 30

            suggestion["match_score"] = min(score, 100)

        return jsonify(
            {
                "suggestions": filtered_suggestions,
                "total_count": len(filtered_suggestions),
                "criteria": {
                    "industry": industry,
                    "delivery_type": delivery_type,
                    "max_cpm": max_cpm,
                    "formats": formats,
                },
            }
        )

    except Exception as e:
        logger.error(f"Error getting product suggestions: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/tenant/<tenant_id>/products/quick-create", methods=["POST"])
@require_auth()
def quick_create_products(tenant_id):
    """Quick create multiple products from suggestions."""
    from flask import session

    # Check access
    if session.get("role") == "viewer":
        return jsonify({"error": "Access denied"}), 403

    if session.get("role") == "tenant_admin" and session.get("tenant_id") != tenant_id:
        return jsonify({"error": "Access denied"}), 403

    try:
        data = request.get_json()
        product_ids = data.get("product_ids", [])

        if not product_ids:
            return jsonify({"error": "No product IDs provided"}), 400

        from default_products import (
            get_default_products,
            get_industry_specific_products,
        )

        # Get all available templates
        all_templates = get_default_products()
        # Add industry templates
        for industry in ["news", "sports", "entertainment", "ecommerce"]:
            all_templates.extend(get_industry_specific_products(industry))

        # Create a map for quick lookup
        template_map = {t["product_id"]: t for t in all_templates}

        with get_db_session() as db_session:
            created = []
            errors = []

            for product_id in product_ids:
                if product_id not in template_map:
                    errors.append(f"Template not found: {product_id}")
                    continue

                template = template_map[product_id]

                try:
                    # Check if already exists
                    existing_product = (
                        db_session.query(Product).filter_by(tenant_id=tenant_id, product_id=product_id).first()
                    )
                    if existing_product:
                        errors.append(f"Product already exists: {product_id}")
                        continue

                    # Convert format IDs to format objects
                    raw_formats = template.get("formats", [])
                    format_objects = []

                    for fmt in raw_formats:
                        if isinstance(fmt, str):
                            # Convert string format ID to format object
                            # For basic display formats, create minimal format objects
                            if fmt.startswith("display_"):
                                # Extract dimensions from format ID like "display_300x250"
                                try:
                                    dimensions = fmt.replace("display_", "")
                                    width, height = map(int, dimensions.split("x"))
                                    format_obj = {
                                        "format_id": fmt,
                                        "name": f"{width}x{height} Display",
                                        "type": "display",
                                        "width": width,
                                        "height": height,
                                        "delivery_options": {"hosted": None},
                                    }
                                except ValueError:
                                    # If we can't parse dimensions, create a basic format
                                    format_obj = {
                                        "format_id": fmt,
                                        "name": fmt.replace("_", " ").title(),
                                        "type": "display",
                                        "delivery_options": {"hosted": None},
                                    }
                            elif fmt.startswith("video_"):
                                # Extract duration from format ID like "video_15s"
                                try:
                                    duration_str = fmt.replace("video_", "").replace("s", "")
                                    duration = int(duration_str)
                                    format_obj = {
                                        "format_id": fmt,
                                        "name": f"{duration} Second Video",
                                        "type": "video",
                                        "duration": duration,
                                        "delivery_options": {"vast": {"mime_types": ["video/mp4"]}},
                                    }
                                except ValueError:
                                    format_obj = {
                                        "format_id": fmt,
                                        "name": fmt.replace("_", " ").title(),
                                        "type": "video",
                                        "delivery_options": {"vast": {"mime_types": ["video/mp4"]}},
                                    }
                            else:
                                # Generic format
                                format_obj = {
                                    "format_id": fmt,
                                    "name": fmt.replace("_", " ").title(),
                                    "type": "display",  # Default to display
                                    "delivery_options": {"hosted": None},
                                }
                            format_objects.append(format_obj)
                        else:
                            # Already a format object
                            format_objects.append(fmt)

                    # Insert product
                    # Calculate is_fixed_price based on delivery_type and cpm
                    is_fixed_price = (
                        template.get("delivery_type", "guaranteed") == "guaranteed" and template.get("cpm") is not None
                    )

                    new_product = Product(
                        product_id=template["product_id"],
                        tenant_id=tenant_id,
                        name=template["name"],
                        description=template.get("description", ""),
                        formats=format_objects,  # Use converted format objects
                        delivery_type=template.get("delivery_type", "guaranteed"),
                        is_fixed_price=is_fixed_price,
                        cpm=template.get("cpm"),
                        price_guidance=template.get("price_guidance"),  # Use price_guidance, not separate min/max
                        countries=template.get("countries"),  # Pass as Python object, not JSON string
                        targeting_template=template.get("targeting_template", {}),  # Pass as Python object
                        implementation_config=template.get("implementation_config", {}),  # Pass as Python object
                    )
                    db_session.add(new_product)
                    created.append(product_id)

                except Exception as e:
                    errors.append(f"Failed to create {product_id}: {str(e)}")

            db_session.commit()

        return jsonify(
            {
                "success": True,
                "created": created,
                "errors": errors,
                "created_count": len(created),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/gam/test-connection", methods=["POST"])
@require_auth()
def gam_test_connection():
    """TODO: Extract implementation from admin_ui.py lines 3408-3578.
    Complex GAM OAuth and API integration - implement in phase 2."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@api_bp.route("/gam/get-advertisers", methods=["POST"])
@require_auth()
def gam_get_advertisers():
    """TODO: Extract implementation from admin_ui.py lines 3580-3653.
    GAM advertiser fetching - implement in phase 2."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501
