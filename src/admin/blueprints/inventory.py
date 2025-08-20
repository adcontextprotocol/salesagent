"""Inventory and orders management blueprint."""

import logging

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy import func

from database_session import get_db_session
from models import GAMOrder, MediaBuy, Tenant
from src.admin.utils import require_auth, require_tenant_access

logger = logging.getLogger(__name__)

# Create blueprint
inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/tenant/<tenant_id>/targeting")
@require_auth()
def targeting_browser(tenant_id):
    """Display targeting browser page."""
    # Check access
    if session.get("role") != "super_admin" and session.get("tenant_id") != tenant_id:
        return "Access denied", 403

    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        row = (tenant.tenant_id, tenant.name) if tenant else None
        if not row:
            return "Tenant not found", 404

    tenant = {"tenant_id": row[0], "name": row[1]}

    return render_template(
        "targeting_browser_simple.html",
        tenant=tenant,
        tenant_id=tenant_id,
        tenant_name=row[1],
    )


@inventory_bp.route("/tenant/<tenant_id>/inventory")
@require_auth()
def inventory_browser(tenant_id):
    """Display inventory browser page."""
    # Check access
    if session.get("role") != "super_admin" and session.get("tenant_id") != tenant_id:
        return "Access denied", 403

    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        row = (tenant.tenant_id, tenant.name) if tenant else None
        if not row:
            return "Tenant not found", 404

    tenant = {"tenant_id": row[0], "name": row[1]}

    # Get inventory type from query param
    inventory_type = request.args.get("type", "all")

    return render_template(
        "inventory_browser.html",
        tenant=tenant,
        tenant_id=tenant_id,
        tenant_name=row[1],
        inventory_type=inventory_type,
    )


@inventory_bp.route("/tenant/<tenant_id>/orders")
@require_auth()
def orders_browser(tenant_id):
    """Display GAM orders browser page."""
    # Check access
    if session.get("role") != "super_admin" and session.get("tenant_id") != tenant_id:
        return "Access denied", 403

    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            return "Tenant not found", 404

        # Get GAM orders from database
        orders = db_session.query(GAMOrder).filter_by(tenant_id=tenant_id).order_by(GAMOrder.updated_at.desc()).all()

        # Calculate summary stats
        total_orders = len(orders)
        active_orders = sum(1 for o in orders if o.status == "ACTIVE")

        # Get total revenue from media buys
        total_revenue = db_session.query(func.sum(MediaBuy.budget)).filter_by(tenant_id=tenant_id).scalar() or 0

        return render_template(
            "orders_browser.html",
            tenant=tenant,
            tenant_id=tenant_id,
            orders=orders,
            total_orders=total_orders,
            active_orders=active_orders,
            total_revenue=total_revenue,
        )


@inventory_bp.route("/api/tenant/<tenant_id>/sync/orders", methods=["POST"])
@require_tenant_access(api_mode=True)
def sync_orders(tenant_id):
    """Sync GAM orders for a tenant."""
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()

            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            if not tenant.gam_network_code or not tenant.gam_refresh_token:
                return jsonify({"error": "GAM not configured for this tenant"}), 400

            # Import GAM sync functionality
            from adapters.gam_order_sync import sync_gam_orders

            # Perform sync
            result = sync_gam_orders(
                tenant_id=tenant_id,
                network_code=tenant.gam_network_code,
                refresh_token=tenant.gam_refresh_token,
            )

            return jsonify(result)

    except Exception as e:
        logger.error(f"Error syncing orders: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@inventory_bp.route("/api/tenant/<tenant_id>/orders", methods=["GET"])
@require_tenant_access(api_mode=True)
def get_orders(tenant_id):
    """Get orders for a tenant."""
    try:
        with get_db_session() as db_session:
            # Get filter parameters
            status = request.args.get("status")
            advertiser = request.args.get("advertiser")

            # Build query
            query = db_session.query(GAMOrder).filter_by(tenant_id=tenant_id)

            if status:
                query = query.filter_by(status=status)
            if advertiser:
                query = query.filter_by(advertiser_name=advertiser)

            # Get orders
            orders = query.order_by(GAMOrder.updated_at.desc()).all()

            # Convert to JSON
            orders_data = []
            for order in orders:
                orders_data.append(
                    {
                        "order_id": order.order_id,
                        "name": order.name,
                        "status": order.status,
                        "advertiser_name": order.advertiser_name,
                        "trafficker_name": order.trafficker_name,
                        "total_impressions_delivered": order.total_impressions_delivered,
                        "total_clicks_delivered": order.total_clicks_delivered,
                        "total_ctr": order.total_ctr,
                        "start_date": order.start_date.isoformat() if order.start_date else None,
                        "end_date": order.end_date.isoformat() if order.end_date else None,
                        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                    }
                )

            return jsonify(
                {
                    "orders": orders_data,
                    "total": len(orders_data),
                }
            )

    except Exception as e:
        logger.error(f"Error getting orders: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@inventory_bp.route("/api/tenant/<tenant_id>/orders/<order_id>", methods=["GET"])
@require_tenant_access(api_mode=True)
def get_order_details(tenant_id, order_id):
    """Get details for a specific order."""
    try:
        with get_db_session() as db_session:
            order = db_session.query(GAMOrder).filter_by(tenant_id=tenant_id, order_id=order_id).first()

            if not order:
                return jsonify({"error": "Order not found"}), 404

            # Get line items count (would need GAMLineItem model)
            # line_items_count = db_session.query(GAMLineItem).filter_by(
            #     tenant_id=tenant_id,
            #     order_id=order_id
            # ).count()

            return jsonify(
                {
                    "order": {
                        "order_id": order.order_id,
                        "name": order.name,
                        "status": order.status,
                        "advertiser_id": order.advertiser_id,
                        "advertiser_name": order.advertiser_name,
                        "trafficker_id": order.trafficker_id,
                        "trafficker_name": order.trafficker_name,
                        "salesperson_name": order.salesperson_name,
                        "total_impressions_delivered": order.total_impressions_delivered,
                        "total_clicks_delivered": order.total_clicks_delivered,
                        "total_ctr": order.total_ctr,
                        "start_date": order.start_date.isoformat() if order.start_date else None,
                        "end_date": order.end_date.isoformat() if order.end_date else None,
                        "created_at": order.created_at.isoformat() if order.created_at else None,
                        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                        # "line_items_count": line_items_count,
                    }
                }
            )

    except Exception as e:
        logger.error(f"Error getting order details: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
