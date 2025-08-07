#!/usr/bin/env python3
"""
Sync all GAM-enabled tenants via the sync API.
This script is intended to be run as a cron job.
"""

import os
import sys
import logging
import requests
from datetime import datetime

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_config import get_db_connection
from sync_api import initialize_superadmin_api_key

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def sync_all_gam_tenants():
    """Sync all tenants that have Google Ad Manager configured."""
    # Get API key
    api_key = initialize_superadmin_api_key()
    
    # Get all GAM tenants from database
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT t.tenant_id, t.name
        FROM tenants t
        JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
        WHERE t.ad_server = 'google_ad_manager'
        AND t.is_active = true
        AND ac.gam_network_code IS NOT NULL
        AND ac.gam_refresh_token IS NOT NULL
    """)
    
    tenants = cursor.fetchall()
    conn.close()
    
    if not tenants:
        logger.info("No GAM tenants found to sync")
        return
    
    logger.info(f"Found {len(tenants)} GAM tenants to sync")
    
    # Sync each tenant
    for tenant in tenants:
        tenant_id = tenant['tenant_id']
        tenant_name = tenant['name']
        
        logger.info(f"Syncing tenant: {tenant_name} ({tenant_id})")
        
        try:
            # Call sync API
            response = requests.post(
                f'http://localhost:{os.environ.get("ADMIN_UI_PORT", 8001)}/api/v1/sync/trigger/{tenant_id}',
                headers={'X-API-Key': api_key},
                json={'sync_type': 'full'},
                timeout=300  # 5 minute timeout per tenant
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'completed':
                    logger.info(f"✓ Sync completed for {tenant_name}")
                    if 'summary' in result:
                        summary = result['summary']
                        logger.info(f"  - Ad units: {summary.get('ad_units', {}).get('total', 0)}")
                        logger.info(f"  - Targeting keys: {summary.get('custom_targeting', {}).get('total_keys', 0)}")
                else:
                    logger.warning(f"Sync status for {tenant_name}: {result.get('status')}")
            elif response.status_code == 409:
                logger.info(f"Sync already in progress for {tenant_name}")
            else:
                logger.error(f"Failed to sync {tenant_name}: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Sync timeout for {tenant_name}")
        except Exception as e:
            logger.error(f"Error syncing {tenant_name}: {e}")
    
    logger.info("Sync job completed")


if __name__ == "__main__":
    logger.info("Starting scheduled sync job")
    sync_all_gam_tenants()