#!/usr/bin/env python3
"""
Safe migration script to populate implementation_config for existing products.

This script is designed to be PRODUCTION SAFE:
- Dry-run by default (no changes unless --apply flag is used)
- Detailed logging of every change
- Validates all generated configs before saving
- Skips products that already have implementation_config
- Can target specific tenants or run for all
"""

import argparse
import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def migrate_product_configs(dry_run: bool = True, tenant_id: str | None = None):
    """Migrate products to have implementation_config with smart defaults.

    Args:
        dry_run: If True, only show what would be changed (no actual changes)
        tenant_id: If provided, only migrate products for this tenant
    """
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Product
    from src.services.gam_product_config_service import GAMProductConfigService

    logger.info("=" * 80)
    logger.info("GAM Product Configuration Migration")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'APPLY (will make changes)'}")
    logger.info(f"Target: {f'Tenant {tenant_id}' if tenant_id else 'All tenants'}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("")

    service = GAMProductConfigService()
    stats = {
        "total_products": 0,
        "already_configured": 0,
        "to_migrate": 0,
        "migrated": 0,
        "errors": 0,
    }

    try:
        with get_db_session() as db_session:
            # Build query
            query = db_session.query(Product)
            if tenant_id:
                query = query.filter_by(tenant_id=tenant_id)

            products = query.all()
            stats["total_products"] = len(products)

            logger.info(f"Found {stats['total_products']} products to examine")
            logger.info("")

            for product in products:
                logger.info(f"Processing product: {product.product_id} ({product.name})")
                logger.info(f"  Tenant: {product.tenant_id}")
                logger.info(f"  Delivery Type: {product.delivery_type}")
                logger.info(f"  Formats: {product.formats}")

                # Check if already has configuration
                if product.implementation_config:
                    logger.info("  ✓ Already has implementation_config - SKIPPING")
                    # Handle both dict and string storage
                    if isinstance(product.implementation_config, dict):
                        logger.info(f"    Current config keys: {list(product.implementation_config.keys())}")
                    else:
                        logger.info(f"    Current config type: {type(product.implementation_config).__name__}")
                    stats["already_configured"] += 1
                    logger.info("")
                    continue

                stats["to_migrate"] += 1

                try:
                    # Generate default configuration
                    default_config = service.generate_default_config(product.delivery_type, product.formats)

                    logger.info("  → Generated default config:")
                    logger.info(f"    Line Item Type: {default_config['line_item_type']}")
                    logger.info(f"    Priority: {default_config['priority']}")
                    logger.info(f"    Goal Type: {default_config['primary_goal_type']}")
                    logger.info(f"    Creative Placeholders: {len(default_config['creative_placeholders'])} sizes")
                    for placeholder in default_config["creative_placeholders"]:
                        logger.info(
                            f"      - {placeholder['width']}x{placeholder['height']} "
                            f"(count: {placeholder['expected_creative_count']}, "
                            f"native: {placeholder['is_native']})"
                        )

                    # Validate the generated config
                    is_valid, error_msg = service.validate_config(default_config)
                    if not is_valid:
                        logger.error(f"  ✗ Generated config is INVALID: {error_msg}")
                        stats["errors"] += 1
                        logger.info("")
                        continue

                    logger.info("  ✓ Config is valid")

                    # Apply changes if not dry-run
                    if not dry_run:
                        product.implementation_config = default_config
                        db_session.flush()  # Validate before committing
                        logger.info("  ✓ APPLIED configuration to database")
                        stats["migrated"] += 1
                    else:
                        logger.info("  → Would apply configuration (dry-run mode)")

                except Exception as e:
                    logger.error(f"  ✗ ERROR generating config: {e}", exc_info=True)
                    stats["errors"] += 1

                logger.info("")

            # Commit all changes if not dry-run
            if not dry_run and stats["to_migrate"] > 0:
                db_session.commit()
                logger.info("✓ All changes committed to database")

    except Exception as e:
        logger.error(f"FATAL ERROR during migration: {e}", exc_info=True)
        return False

    # Print summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total products examined:     {stats['total_products']}")
    logger.info(f"Already configured (skipped): {stats['already_configured']}")
    logger.info(f"Needed migration:             {stats['to_migrate']}")
    if dry_run:
        logger.info(f"Would migrate:                {stats['to_migrate'] - stats['errors']}")
    else:
        logger.info(f"Successfully migrated:        {stats['migrated']}")
    logger.info(f"Errors:                       {stats['errors']}")
    logger.info("=" * 80)

    if dry_run:
        logger.info("")
        logger.info("⚠️  This was a DRY RUN - no changes were made to the database")
        logger.info("To apply these changes, run with --apply flag:")
        logger.info(f"  python {sys.argv[0]} --apply")
        if tenant_id:
            logger.info(f"  (for tenant {tenant_id})")
    else:
        logger.info("")
        logger.info("✓ Migration completed successfully")

    return stats["errors"] == 0


def main():
    parser = argparse.ArgumentParser(
        description="Migrate existing products to have implementation_config with smart defaults",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run for all tenants (safe - no changes)
  python scripts/migrate_product_configs.py

  # Dry-run for specific tenant
  python scripts/migrate_product_configs.py --tenant test_tenant

  # Apply changes for all tenants (CAREFUL!)
  python scripts/migrate_product_configs.py --apply

  # Apply changes for specific tenant only
  python scripts/migrate_product_configs.py --apply --tenant test_tenant

Safety Features:
  - Dry-run by default (no changes unless --apply is used)
  - Skips products that already have implementation_config
  - Validates all generated configs before saving
  - Detailed logging of every operation
  - Can target specific tenant for testing
        """,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes (default is dry-run)",
    )

    parser.add_argument(
        "--tenant",
        type=str,
        help="Only migrate products for this tenant (useful for testing)",
    )

    args = parser.parse_args()

    # Confirm if applying changes
    if args.apply:
        if args.tenant:
            logger.warning(f"⚠️  About to apply changes to tenant '{args.tenant}'")
        else:
            logger.warning("⚠️  About to apply changes to ALL tenants")

        response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
        if response != "yes":
            logger.info("Migration cancelled by user")
            return 1

    # Run migration
    success = migrate_product_configs(dry_run=not args.apply, tenant_id=args.tenant)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
