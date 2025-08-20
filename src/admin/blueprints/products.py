"""Products management blueprint for admin UI."""

import csv
import io
import json
import logging
import uuid
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from ai_product_service import AIProductConfigurationService
from database_session import get_db_session
from default_products import get_default_products, get_industry_specific_products
from models import Product, Tenant
from src.admin.utils import require_tenant_access
from validation import sanitize_form_data, validate_form_data

logger = logging.getLogger(__name__)

# Create Blueprint
products_bp = Blueprint("products", __name__, url_prefix="/tenant/<tenant_id>/products")


@products_bp.route("")
@require_tenant_access()
def list_products(tenant_id):
    """List all products for a tenant."""
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("index"))

            products = db_session.query(Product).filter_by(tenant_id=tenant_id).order_by(Product.name).all()

            # Convert products to dict format for template
            products_list = []
            for product in products:
                product_dict = {
                    "product_id": product.product_id,
                    "name": product.name,
                    "description": product.description,
                    "price_model": product.price_model,
                    "base_price": product.base_price,
                    "currency": product.currency,
                    "min_spend": product.min_spend,
                    "formats": json.loads(product.formats) if product.formats else [],
                    "countries": json.loads(product.countries) if product.countries else [],
                    "created_at": product.created_at,
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
    """Add a new product."""
    if request.method == "POST":
        try:
            # Sanitize form data
            form_data = sanitize_form_data(request.form.to_dict())

            # Validate required fields
            is_valid, errors = validate_form_data(form_data, ["name", "price_model", "base_price"])
            if not is_valid:
                for error in errors:
                    flash(error, "error")
                return redirect(url_for("products.add_product", tenant_id=tenant_id))

            with get_db_session() as db_session:
                # Parse formats and countries
                formats = []
                countries = []

                if "formats" in form_data:
                    formats = [f.strip() for f in form_data["formats"].split(",") if f.strip()]

                if "countries" in form_data:
                    countries = [c.strip().upper() for c in form_data["countries"].split(",") if c.strip()]

                # Create product
                product = Product(
                    product_id=f"prod_{uuid.uuid4().hex[:8]}",
                    tenant_id=tenant_id,
                    name=form_data["name"],
                    description=form_data.get("description", ""),
                    price_model=form_data["price_model"],
                    base_price=float(form_data["base_price"]),
                    currency=form_data.get("currency", "USD"),
                    min_spend=float(form_data["min_spend"]) if form_data.get("min_spend") else None,
                    formats=json.dumps(formats),
                    countries=json.dumps(countries),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                db_session.add(product)
                db_session.commit()

                flash(f"Product '{product.name}' created successfully", "success")
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

        except Exception as e:
            logger.error(f"Error creating product: {e}", exc_info=True)
            flash("Error creating product", "error")
            return redirect(url_for("products.add_product", tenant_id=tenant_id))

    # GET request - show form
    return render_template("add_product.html", tenant_id=tenant_id)


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
                product.price_model = form_data.get("price_model", product.price_model)
                product.base_price = float(form_data.get("base_price", product.base_price))
                product.currency = form_data.get("currency", product.currency)
                product.min_spend = float(form_data["min_spend"]) if form_data.get("min_spend") else None

                # Update formats and countries
                if "formats" in form_data:
                    formats = [f.strip() for f in form_data["formats"].split(",") if f.strip()]
                    product.formats = json.dumps(formats)

                if "countries" in form_data:
                    countries = [c.strip().upper() for c in form_data["countries"].split(",") if c.strip()]
                    product.countries = json.dumps(countries)

                product.updated_at = datetime.now(UTC)
                db_session.commit()

                flash(f"Product '{product.name}' updated successfully", "success")
                return redirect(url_for("products.list_products", tenant_id=tenant_id))

            # GET request - show form
            product_dict = {
                "product_id": product.product_id,
                "name": product.name,
                "description": product.description,
                "price_model": product.price_model,
                "base_price": product.base_price,
                "currency": product.currency,
                "min_spend": product.min_spend,
                "formats": json.loads(product.formats) if product.formats else [],
                "countries": json.loads(product.countries) if product.countries else [],
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


@products_bp.route("/add/ai", methods=["GET"])
@require_tenant_access()
def add_product_ai_form(tenant_id):
    """Show AI-powered product creation form."""
    return render_template("add_product_ai.html", tenant_id=tenant_id)


@products_bp.route("/analyze_ai", methods=["POST"])
@require_tenant_access()
def analyze_product_ai(tenant_id):
    """Analyze product description with AI."""
    try:
        data = request.get_json()
        description = data.get("description", "").strip()

        if not description:
            return jsonify({"error": "Description is required"}), 400

        # Use AI service to analyze
        ai_service = AIProductConfigurationService()
        result = ai_service.analyze_product_description(description)

        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "Failed to analyze description"}), 500

    except Exception as e:
        logger.error(f"Error analyzing product with AI: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@products_bp.route("/bulk", methods=["GET"])
@require_tenant_access()
def bulk_upload_form(tenant_id):
    """Show bulk product upload form."""
    return render_template("bulk_product_upload.html", tenant_id=tenant_id)


@products_bp.route("/bulk/upload", methods=["POST"])
@require_tenant_access()
def bulk_upload(tenant_id):
    """Handle bulk product upload."""
    try:
        if "file" not in request.files:
            flash("No file uploaded", "error")
            return redirect(url_for("products.bulk_upload_form", tenant_id=tenant_id))

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected", "error")
            return redirect(url_for("products.bulk_upload_form", tenant_id=tenant_id))

        # Check file extension
        if not file.filename.lower().endswith((".csv", ".json")):
            flash("Only CSV and JSON files are supported", "error")
            return redirect(url_for("products.bulk_upload_form", tenant_id=tenant_id))

        # Process file
        created_count = 0

        with get_db_session() as db_session:
            if file.filename.lower().endswith(".csv"):
                # Process CSV
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_reader = csv.DictReader(stream)

                for row in csv_reader:
                    try:
                        product = Product(
                            product_id=f"prod_{uuid.uuid4().hex[:8]}",
                            tenant_id=tenant_id,
                            name=row.get("name", ""),
                            description=row.get("description", ""),
                            price_model=row.get("price_model", "cpm"),
                            base_price=float(row.get("base_price", 0)),
                            currency=row.get("currency", "USD"),
                            min_spend=float(row.get("min_spend")) if row.get("min_spend") else None,
                            formats=json.dumps(row.get("formats", "").split(",")),
                            countries=json.dumps(row.get("countries", "").split(",")),
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                        db_session.add(product)
                        created_count += 1
                    except Exception as e:
                        logger.error(f"Error processing row: {e}")
                        continue

            else:
                # Process JSON
                data = json.loads(file.stream.read())
                products_data = data if isinstance(data, list) else [data]

                for item in products_data:
                    try:
                        product = Product(
                            product_id=f"prod_{uuid.uuid4().hex[:8]}",
                            tenant_id=tenant_id,
                            name=item.get("name", ""),
                            description=item.get("description", ""),
                            price_model=item.get("price_model", "cpm"),
                            base_price=float(item.get("base_price", 0)),
                            currency=item.get("currency", "USD"),
                            min_spend=float(item.get("min_spend")) if item.get("min_spend") else None,
                            formats=json.dumps(item.get("formats", [])),
                            countries=json.dumps(item.get("countries", [])),
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                        db_session.add(product)
                        created_count += 1
                    except Exception as e:
                        logger.error(f"Error processing item: {e}")
                        continue

            db_session.commit()
            flash(f"Successfully created {created_count} products", "success")

    except Exception as e:
        logger.error(f"Error in bulk upload: {e}", exc_info=True)
        flash("Error processing file", "error")

    return redirect(url_for("products.list_products", tenant_id=tenant_id))


@products_bp.route("/templates", methods=["GET"])
@require_tenant_access()
def get_templates(tenant_id):
    """Get product templates."""
    try:
        # Get industry filter
        industry = request.args.get("industry", "all")

        # Get templates
        if industry and industry != "all":
            products = get_industry_specific_products(industry)
        else:
            products = get_default_products()

        # Convert to template format
        templates = {}
        for product in products:
            templates[product.get("product_id", product["name"].lower().replace(" ", "_"))] = product

        return jsonify({"templates": templates})

    except Exception as e:
        logger.error(f"Error getting templates: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@products_bp.route("/templates/browse", methods=["GET"])
@require_tenant_access()
def browse_templates(tenant_id):
    """Browse and use product templates."""
    from creative_formats import get_creative_formats

    # Get all available templates
    standard_templates = get_default_products()

    # Get industry templates for different industries
    industry_templates = {
        "news": get_industry_specific_products("news"),
        "sports": get_industry_specific_products("sports"),
        "entertainment": get_industry_specific_products("entertainment"),
        "ecommerce": get_industry_specific_products("ecommerce"),
    }

    # Filter out standard templates from industry lists
    standard_ids = {t["product_id"] for t in standard_templates}
    for industry in industry_templates:
        industry_templates[industry] = [t for t in industry_templates[industry] if t["product_id"] not in standard_ids]

    # Get creative formats for display
    formats = get_creative_formats()

    return render_template(
        "product_templates.html",
        tenant_id=tenant_id,
        standard_templates=standard_templates,
        industry_templates=industry_templates,
        formats=formats,
    )


@products_bp.route("/templates/create", methods=["POST"])
@require_tenant_access()
def create_from_template(tenant_id):
    """Create a product from a template."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        template_id = data.get("template_id")
        if not template_id:
            return jsonify({"error": "Template ID required"}), 400

        # Get all available templates
        all_templates = get_default_products()
        # Add industry templates
        for industry in ["news", "sports", "entertainment", "ecommerce"]:
            all_templates.extend(get_industry_specific_products(industry))

        # Find the template
        template = None
        for t in all_templates:
            if t.get("product_id") == template_id:
                template = t
                break

        if not template:
            return jsonify({"error": "Template not found"}), 404

        # Create product from template
        with get_db_session() as db_session:
            product_id = f"prod_{uuid.uuid4().hex[:8]}"

            # Convert template to product
            product = Product(
                tenant_id=tenant_id,
                product_id=product_id,
                name=template.get("name"),
                description=template.get("description"),
                price_model=template.get("pricing", {}).get("model", "CPM"),
                base_price=template.get("pricing", {}).get("base_price", 0),
                currency=template.get("pricing", {}).get("currency", "USD"),
                min_spend=template.get("pricing", {}).get("min_spend", 0),
                formats=json.dumps(template.get("formats", [])),
                countries=json.dumps(template.get("countries", [])),
                targeting_template=json.dumps(template.get("targeting_template", {})),
                delivery_type=template.get("delivery_type", "standard"),
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db_session.add(product)
            db_session.commit()

            return jsonify(
                {
                    "success": True,
                    "product_id": product_id,
                    "message": f"Product '{template.get('name')}' created successfully",
                }
            )

    except Exception as e:
        logger.error(f"Error creating product from template: {e}", exc_info=True)
        return jsonify({"error": "Failed to create product"}), 500


@products_bp.route("/setup-wizard")
@require_tenant_access()
def setup_wizard(tenant_id):
    """Show product setup wizard for new tenants."""
    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            flash("Tenant not found", "error")
            return redirect(url_for("index"))

        # Check if tenant already has products
        product_count = db_session.query(Product).filter_by(tenant_id=tenant_id).count()

        # Get industry from tenant config
        from src.admin.utils import get_tenant_config_from_db

        config = get_tenant_config_from_db(tenant_id)
        tenant_industry = config.get("industry", "general")

        # Get AI service
        ai_service = AIProductConfigurationService()

        # Get suggestions based on industry
        suggestions = ai_service.get_product_suggestions(
            industry=tenant_industry, include_standard=True, include_industry=True
        )

        # Get creative formats for display
        from creative_formats import get_creative_formats

        formats = get_creative_formats()

        return render_template(
            "product_setup_wizard.html",
            tenant_id=tenant_id,
            tenant_name=tenant.name,
            tenant_industry=tenant_industry,
            has_existing_products=product_count > 0,
            suggestions=suggestions,
            formats=formats,
        )


@products_bp.route("/create-bulk", methods=["POST"])
@require_tenant_access()
def create_bulk(tenant_id):
    """Create multiple products from wizard suggestions."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        product_ids = data.get("product_ids", [])
        if not product_ids:
            return jsonify({"error": "No products selected"}), 400

        # Get all available templates
        all_templates = get_default_products()
        # Add industry templates
        for industry in ["news", "sports", "entertainment", "ecommerce"]:
            all_templates.extend(get_industry_specific_products(industry))

        created_products = []
        errors = []

        with get_db_session() as db_session:
            for template_id in product_ids:
                # Find the template
                template = None
                for t in all_templates:
                    if t.get("product_id") == template_id:
                        template = t
                        break

                if not template:
                    errors.append(f"Template '{template_id}' not found")
                    continue

                try:
                    # Create unique product ID
                    product_id = f"prod_{uuid.uuid4().hex[:8]}"

                    # Convert template to product
                    product = Product(
                        tenant_id=tenant_id,
                        product_id=product_id,
                        name=template.get("name"),
                        description=template.get("description"),
                        price_model=template.get("pricing", {}).get("model", "CPM"),
                        base_price=template.get("pricing", {}).get("base_price", 0),
                        currency=template.get("pricing", {}).get("currency", "USD"),
                        min_spend=template.get("pricing", {}).get("min_spend", 0),
                        formats=json.dumps(template.get("formats", [])),
                        countries=json.dumps(template.get("countries", [])),
                        targeting_template=json.dumps(template.get("targeting_template", {})),
                        delivery_type=template.get("delivery_type", "standard"),
                        status="active",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )

                    db_session.add(product)
                    created_products.append({"product_id": product_id, "name": template.get("name")})

                except Exception as e:
                    logger.error(f"Error creating product from template {template_id}: {e}")
                    errors.append(f"Failed to create '{template.get('name', template_id)}': {str(e)}")

            db_session.commit()

        return jsonify(
            {
                "success": len(created_products) > 0,
                "created": created_products,
                "errors": errors,
                "message": f"Created {len(created_products)} products successfully",
            }
        )

    except Exception as e:
        logger.error(f"Error creating bulk products: {e}", exc_info=True)
        return jsonify({"error": "Failed to create products"}), 500
