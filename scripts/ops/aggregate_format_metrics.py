#!/usr/bin/env python3
"""
Aggregate format performance metrics for all GAM-enabled tenants.

This script queries GAM ReportService for historical data by COUNTRY_CODE + CREATIVE_SIZE,
calculates CPM percentiles, and stores results in format_performance_metrics table.

Intended to be run as a daily cron job:
  0 2 * * * /path/to/aggregate_format_metrics.py

Arguments:
  --period-days N  Number of days to aggregate (default: 30)
  --tenant-id ID   Process single tenant only (optional)
"""

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.services.format_metrics_service import (
    FormatMetricsAggregationService,
    aggregate_all_tenants,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for format metrics aggregation."""
    parser = argparse.ArgumentParser(description="Aggregate format performance metrics from GAM")
    parser.add_argument(
        "--period-days",
        type=int,
        default=30,
        help="Number of days to aggregate (default: 30)",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        help="Process single tenant only (optional)",
    )

    args = parser.parse_args()

    logger.info(
        f"Starting format metrics aggregation (period_days={args.period_days}, tenant_id={args.tenant_id or 'all'})"
    )

    try:
        if args.tenant_id:
            # Process single tenant
            from src.adapters.gam.client import GAMClientManager
            from src.core.database.database_session import get_db_session
            from src.core.database.models import AdapterConfig, Tenant

            with get_db_session() as db_session:
                # Get tenant and adapter config
                tenant = db_session.query(Tenant).filter_by(tenant_id=args.tenant_id).first()
                if not tenant:
                    logger.error(f"Tenant {args.tenant_id} not found")
                    sys.exit(1)

                adapter_config = db_session.query(AdapterConfig).filter_by(tenant_id=args.tenant_id).first()
                if not adapter_config or not adapter_config.gam_refresh_token:
                    logger.error(f"Tenant {args.tenant_id} does not have GAM configured")
                    sys.exit(1)

                # Initialize GAM client
                gam_config = {
                    "refresh_token": adapter_config.gam_refresh_token,
                }
                client_manager = GAMClientManager(gam_config, adapter_config.gam_network_code)
                gam_client = client_manager.get_client()

                # Aggregate metrics
                service = FormatMetricsAggregationService(db_session)
                summary = service.aggregate_metrics_for_tenant(args.tenant_id, gam_client, args.period_days)

                logger.info(f"Aggregation complete for tenant {args.tenant_id}: {summary}")

        else:
            # Process all tenants
            summary = aggregate_all_tenants(period_days=args.period_days)
            logger.info(
                f"Aggregation complete: {summary['successful']} successful, "
                f"{summary['failed']} failed out of {summary['total_tenants']} tenants"
            )

            # Exit with error code if any failed
            if summary["failed"] > 0:
                sys.exit(1)

    except Exception as e:
        logger.error(f"Format metrics aggregation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
