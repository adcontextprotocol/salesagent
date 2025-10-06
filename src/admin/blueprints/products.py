"""Products management blueprint for admin UI."""

import json
import logging
import uuid

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import Product, Tenant
from src.core.validation import sanitize_form_data
from src.services.gam_product_config_service import GAMProductConfigService

logger = logging.getLogger(__name__)

# Create Blueprint
products_bp = Blueprint("products", __name__)


def get_creative_formats():
    """Get all available creative formats for the product form.

    Returns standard AdCP formats from FORMAT_REGISTRY (authoritative source).
    Custom tenant-specific formats are stored in database but not used for product creation.
    """
    from src.core.schemas import FORMAT_REGISTRY

    formats_list = []

    # Use FORMAT_REGISTRY as authoritative source for standard formats
    for _format_id, fmt in FORMAT_REGISTRY.items():
        format_dict = {
            "format_id": fmt.format_id,
            "name": fmt.name,
            "type": fmt.type,
            "description": f"{fmt.name} - {fmt.iab_specification or 'Standard format'}",
            "dimensions": None,
            "duration": None,
        }

        # Add dimensions for display/video formats
        if fmt.requirements and "width" in fmt.requirements and "height" in fmt.requirements:
            format_dict["dimensions"] = f"{fmt.requirements['width']}x{fmt.requirements['height']}"

        # Add duration for video/audio formats
        if fmt.requirements and "duration" in fmt.requirements:
            format_dict["duration"] = f"{fmt.requirements['duration']}s"
        elif fmt.requirements and "duration_max" in fmt.requirements:
            format_dict["duration"] = f"{fmt.requirements['duration_max']}s"

        formats_list.append(format_dict)

    # Sort by type, then name
    formats_list.sort(key=lambda x: (x["type"], x["name"]))

    return formats_list


@products_bp.route("/")
@require_tenant_access()
def list_products(tenant_id):
    """List all products for a tenant."""
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            products = db_session.query(Product).filter_by(tenant_id=tenant_id).order_by(Product.name).all()

            # Convert products to dict format for template
            products_list = []
            for product in products:
                product_dict = {
                    "product_id": product.product_id,
                    "name": product.name,
                    "description": product.description,
                    "delivery_type": product.delivery_type,
                    "is_fixed_price": product.is_fixed_price,
                    "cpm": product.cpm,
                    "price_guidance": product.price_guidance,
                    "formats": (
                        product.formats
                        if isinstance(product.formats, list)
                        else json.loads(product.formats) if product.formats else []
                    ),
                    "countries": (
                        product.countries
                        if isinstance(product.countries, list)
                        else json.loads(product.countries) if product.countries else []
                    ),
                    "created_at": product.created_at if hasattr(product, "created_at") else None,
                }
                products_list.append(product_dict)

            return render_template(
                "products.html",
                tenant=tenant,
                tenant_id=tenant_id,
                products=products_list,
            )

    except Exception as e:
        logger.error(f"Error loading products: {e}", exc_info=True)
        flash("Error loading products", "error")
        return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))


@products_bp.route("/add", methods=["GET", "POST"])
@require_tenant_access()
def add_product(tenant_id):
    """Add a new product - adapter-specific form."""
    # Get tenant's adapter type
    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            flash("Tenant not found", "error")
            return redirect(url_for("products.list_products", tenant_id=tenant_id))

        adapter_type = tenant.ad_server or "mock"

    if request.method == "POST":
        try:
            # Sanitize form data
            form_data = sanitize_form_data(request.form.to_dict())

            # Validate required fields
            if not form_data.get("name"):
                flash("Product name is required", "error")
                return redirect(url_for("products.add_product", tenant_id=tenant_id))

            with get_db_session() as db_session:
                # Parse formats - expecting multiple checkbox values
                formats = request.form.getlist("formats")
                if not formats:
                    formats = []

                # Parse countries - from multi-select
                countries = request.form.getlist("countries")
                if not countries or "ALL" in countries:
                    countries = None  # None means all countries

                # Get pricing based on delivery type
                delivery_type = form_data.get("delivery_type", "guaranteed")
                cpm = None
                price_guidance = None

                if delivery_type == "guaranteed":
                    cpm = float(form_data.get("cpm", 0)) if form_data.get("cpm") else None
                else:
                    # Non-guaranteed - use price guidance
                    price_min = (
                        float(form_data.get("price_guidance_min", 0)) if form_data.get("price_guidance_min") else None
                    )
                    price_max = (
                        float(form_data.get("price_guidance_max", 0)) if form_data.get("price_guidance_max") else None
                    )
                    if price_min and price_max:
                        price_guidance = {"min": price_min, "max": price_max}

                # Build implementation config based on adapter type
                implementation_config = {}
                if adapter_type == "google_ad_manager":
                    # Parse GAM-specific fields from unified form
                    gam_config_service = GAMProductConfigService()
                    base_config = gam_config_service.generate_default_config(delivery_type, formats)

                    # Add ad unit/placement targeting if provided
                    ad_unit_ids = form_data.get("targeted_ad_unit_ids", "").strip()
                    if ad_unit_ids:
                        base_config["targeted_ad_unit_ids"] = [id.strip() for id in ad_unit_ids.split("\n") if id.strip()]

                    placement_ids = form_data.get("targeted_placement_ids", "").strip()
                    if placement_ids:
                        base_config["targeted_placement_ids"] = [
                            id.strip() for id in placement_ids.split("\n") if id.strip()
                        ]

                    base_config["include_descendants"] = form_data.get("include_descendants") == "on"

                    # Add advanced GAM settings if provided
                    if form_data.get("line_item_type"):
                        base_config["line_item_type"] = form_data["line_item_type"]
                    if form_data.get("priority"):
                        base_config["priority"] = int(form_data["priority"])
                    if form_data.get("cost_type"):
                        base_config["cost_type"] = form_data["cost_type"]
                    if form_data.get("creative_rotation_type"):
                        base_config["creative_rotation_type"] = form_data["creative_rotation_type"]
                    if form_data.get("delivery_rate_type"):
                        base_config["delivery_rate_type"] = form_data["delivery_rate_type"]

                    implementation_config = base_config
                else:
                    # For other adapters, use simple config
                    gam_config_service = GAMProductConfigService()
                    implementation_config = gam_config_service.generate_default_config(delivery_type, formats)

                # Create product with correct fields matching the Product model
                product = Product(
                    product_id=form_data.get("product_id") or f"prod_{uuid.uuid4().hex[:8]}",
                    tenant_id=tenant_id,
                    name=form_data["name"],
                    description=form_data.get("description", ""),
                    formats=formats,  # List, not JSON string
                    countries=countries,  # List or None
                    delivery_type=delivery_type,
                    is_fixed_price=(delivery_type == "guaranteed"),
                    cpm=cpm,
                    price_guidance=price_guidance,
                    targeting_template={},  # Empty targeting template
                    implementation_config=implementation_config
                )
                db_session.add(product)
                db_session.commit()

                flash(f"Product '{product.name}' created successfully!", "success")
                # Redirect to products list
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

        except Exception as e:
            logger.error(f"Error creating product: {e}", exc_info=True)
            flash("Error creating product", "error")
            return redirect(url_for("products.add_product", tenant_id=tenant_id))

    # GET request - show adapter-specific form
    if adapter_type == "google_ad_manager":
        # For GAM: unified form with inventory selection
        # Check if inventory has been synced
        from src.core.database.models import GAMInventory

        with get_db_session() as db_session:
            inventory_count = db_session.query(GAMInventory).filter_by(tenant_id=tenant_id).count()
            inventory_synced = inventory_count > 0

        return render_template(
            "add_product_gam.html", tenant_id=tenant_id, inventory_synced=inventory_synced, formats=get_creative_formats()
        )
    else:
        # For Mock and other adapters: simple form
        formats = get_creative_formats()
        return render_template("add_product.html", tenant_id=tenant_id, formats=formats)


@products_bp.route("/<product_id>/edit", methods=["GET", "POST"])
@require_tenant_access()
def edit_product(tenant_id, product_id):
    """Edit an existing product."""
    try:
        with get_db_session() as db_session:
            product = db_session.query(Product).filter_by(tenant_id=tenant_id, product_id=product_id).first()
            if not product:
                flash("Product not found", "error")
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

            if request.method == "POST":
                # Sanitize form data
                form_data = sanitize_form_data(request.form.to_dict())

                # Update product
                product.name = form_data.get("name", product.name)
                product.description = form_data.get("description", product.description)
                product.delivery_type = form_data.get("delivery_type", product.delivery_type)
                product.is_fixed_price = form_data.get("is_fixed_price", "true").lower() == "true"

                # Update pricing based on delivery type
                if product.is_fixed_price:
                    product.cpm = float(form_data.get("cpm")) if form_data.get("cpm") else product.cpm
                    product.price_guidance = None
                else:
                    product.cpm = None
                    price_min = (
                        float(form_data.get("price_guidance_min")) if form_data.get("price_guidance_min") else None
                    )
                    price_max = (
                        float(form_data.get("price_guidance_max")) if form_data.get("price_guidance_max") else None
                    )
                    if price_min and price_max:
                        product.price_guidance = {"min": price_min, "max": price_max}

                # Update formats and countries
                if "formats" in form_data:
                    formats = [f.strip() for f in form_data["formats"].split(",") if f.strip()]
                    product.formats = formats

                if "countries" in form_data:
                    countries = [c.strip().upper() for c in form_data["countries"].split(",") if c.strip()]
                    product.countries = countries
                db_session.commit()

                flash(f"Product '{product.name}' updated successfully", "success")
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

            # GET request - show form
            product_dict = {
                "product_id": product.product_id,
                "name": product.name,
                "description": product.description,
                "delivery_type": product.delivery_type,
                "is_fixed_price": product.is_fixed_price,
                "cpm": product.cpm,
                "price_guidance": product.price_guidance,
                "formats": (
                    product.formats
                    if isinstance(product.formats, list)
                    else json.loads(product.formats) if product.formats else []
                ),
                "countries": (
                    product.countries
                    if isinstance(product.countries, list)
                    else json.loads(product.countries) if product.countries else []
                ),
            }

            return render_template(
                "edit_product.html",
                tenant_id=tenant_id,
                product=product_dict,
            )

    except Exception as e:
        logger.error(f"Error editing product: {e}", exc_info=True)
        flash("Error editing product", "error")
        return redirect(url_for("products.list_products", tenant_id=tenant_id))


@products_bp.route("/<product_id>/delete", methods=["DELETE"])
@require_tenant_access()
def delete_product(tenant_id, product_id):
    """Delete a product."""
    try:
        with get_db_session() as db_session:
            # Find the product
            product = db_session.query(Product).filter_by(tenant_id=tenant_id, product_id=product_id).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            # Store product name for response
            product_name = product.name

            # Check if product is used in any active media buys
            # Import here to avoid circular imports
            from src.core.database.models import MediaBuy

            active_buys = (
                db_session.query(MediaBuy)
                .filter_by(tenant_id=tenant_id)
                .filter(MediaBuy.status.in_(["pending", "active", "paused"]))
                .all()
            )

            # Check if any active media buys reference this product
            for buy in active_buys:
                # Check both config (legacy) and raw_request (current) fields for backward compatibility
                config_product_ids = []
                try:
                    # Legacy field: may not exist on older MediaBuy records
                    config_data = getattr(buy, "config", None)
                    if config_data:
                        config_product_ids = config_data.get("product_ids", [])
                except (AttributeError, TypeError):
                    pass

                # Current field: should always exist
                raw_request_product_ids = (buy.raw_request or {}).get("product_ids", [])
                all_product_ids = config_product_ids + raw_request_product_ids

                if product_id in all_product_ids:
                    return (
                        jsonify(
                            {
                                "error": f"Cannot delete product '{product_name}' - it is used in active media buy '{buy.media_buy_id}'"
                            }
                        ),
                        400,
                    )

            # Delete the product
            db_session.delete(product)
            db_session.commit()

            logger.info(f"Product {product_id} ({product_name}) deleted by tenant {tenant_id}")

            return jsonify({"success": True, "message": f"Product '{product_name}' deleted successfully"})

    except Exception as e:
        logger.error(f"Error deleting product {product_id}: {e}", exc_info=True)
        # Sanitize error messages to prevent information leakage
        error_message = str(e)
        if "ValidationError" in error_message or "pattern" in error_message.lower():
            logger.warning(f"Product validation error for {product_id}: {error_message}")
            return jsonify({"error": "Product data validation failed"}), 400

        logger.error(f"Product deletion failed for {product_id}: {error_message}")
        return jsonify({"error": "Failed to delete product. Please contact support."}), 500


@products_bp.route("/<product_id>/gam-config", methods=["GET", "POST"])
@require_tenant_access()
def gam_product_config(tenant_id, product_id):
    """Configure GAM-specific implementation settings for a product."""
    try:
        with get_db_session() as db_session:
            product = db_session.query(Product).filter_by(tenant_id=tenant_id, product_id=product_id).first()

            if not product:
                flash("Product not found", "error")
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

            # Check if inventory has been synced for this tenant
            from src.core.database.models import GAMInventory

            inventory_count = db_session.query(GAMInventory).filter_by(tenant_id=tenant_id).count()
            inventory_synced = inventory_count > 0

            if request.method == "POST":
                # Parse form data into GAM configuration
                gam_config_service = GAMProductConfigService()
                # Pass the full request.form (not to_dict) to preserve arrays
                impl_config = gam_config_service.parse_form_config(request.form)

                # Validate configuration
                is_valid, error_msg = gam_config_service.validate_config(impl_config)
                if not is_valid:
                    flash(f"Configuration validation failed: {error_msg}", "error")
                    # Re-render form with current data
                    return render_template(
                        "adapters/gam_product_config.html",
                        tenant_id=tenant_id,
                        product=product,
                        config=impl_config,
                        inventory_synced=inventory_synced,
                    )

                # Update product with new configuration
                # Use flag_modified to ensure SQLAlchemy detects JSONB mutations
                from sqlalchemy.orm import attributes

                product.implementation_config = impl_config
                attributes.flag_modified(product, "implementation_config")
                db_session.commit()

                flash(f"GAM configuration saved for '{product.name}'", "success")
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

            # GET request - show configuration form
            # Load existing config or empty dict
            config = product.implementation_config or {}

            return render_template(
                "adapters/gam_product_config.html",
                tenant_id=tenant_id,
                product=product,
                config=config,
                inventory_synced=inventory_synced,
            )

    except Exception as e:
        logger.error(f"Error configuring GAM product: {e}", exc_info=True)
        flash("Error configuring product", "error")
        return redirect(url_for("products.list_products", tenant_id=tenant_id))
