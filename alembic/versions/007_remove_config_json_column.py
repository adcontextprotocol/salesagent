"""Remove config JSON column after full migration

Revision ID: 007_remove_config_json_column  
Revises: 006_add_remaining_config_fields
Create Date: 2025-02-04

"""
from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = '007_remove_config_json_column'
down_revision = '006_add_remaining_config_fields'
branch_labels = None
depends_on = None


def upgrade():
    """Remove the config JSON column since all data has been migrated."""
    
    # Before dropping, verify all tenants have been migrated
    connection = op.get_bind()
    
    # Check if any tenant is missing critical fields
    result = connection.execute(sa.text("""
        SELECT COUNT(*) 
        FROM tenants 
        WHERE ad_server IS NULL
    """))
    
    missing_count = result.scalar()
    if missing_count > 0:
        raise Exception(f"Cannot remove config column: {missing_count} tenants missing ad_server field")
    
    # Drop the config column
    op.drop_column('tenants', 'config')


def downgrade():
    """Restore config JSON column and reconstruct data."""
    
    # Add config column back
    op.add_column('tenants', sa.Column('config', sa.Text(), nullable=True))
    
    # Reconstruct config from all the separate columns
    connection = op.get_bind()
    
    # Get all tenants with their column data
    tenants_table = sa.table('tenants',
        sa.column('tenant_id', sa.String),
        sa.column('config', sa.Text),
        sa.column('ad_server', sa.String),
        sa.column('max_daily_budget', sa.Integer),
        sa.column('enable_aee_signals', sa.Boolean),
        sa.column('authorized_emails', sa.Text),
        sa.column('authorized_domains', sa.Text),
        sa.column('slack_webhook_url', sa.String),
        sa.column('slack_audit_webhook_url', sa.String),
        sa.column('hitl_webhook_url', sa.String),
        sa.column('admin_token', sa.String),
        sa.column('auto_approve_formats', sa.Text),
        sa.column('human_review_required', sa.Boolean),
        sa.column('policy_settings', sa.Text)
    )
    
    # Also need adapter_config data
    adapter_config_table = sa.table('adapter_config',
        sa.column('tenant_id', sa.String),
        sa.column('adapter_type', sa.String),
        sa.column('mock_dry_run', sa.Boolean),
        sa.column('gam_network_code', sa.String),
        sa.column('gam_refresh_token', sa.Text),
        sa.column('gam_company_id', sa.String),
        sa.column('gam_trafficker_id', sa.String),
        sa.column('gam_manual_approval_required', sa.Boolean),
        sa.column('kevel_network_id', sa.String),
        sa.column('kevel_api_key', sa.String),
        sa.column('kevel_manual_approval_required', sa.Boolean),
        sa.column('triton_station_id', sa.String),
        sa.column('triton_api_key', sa.String)
    )
    
    tenants = connection.execute(
        sa.select([tenants_table])
    )
    
    for row in tenants:
        tenant_id = row.tenant_id
        
        # Build base config structure
        config = {
            'features': {
                'max_daily_budget': row.max_daily_budget or 10000,
                'enable_aee_signals': bool(row.enable_aee_signals)
            },
            'creative_engine': {
                'human_review_required': bool(row.human_review_required)
            },
            'adapters': {}
        }
        
        # Add optional fields
        if row.authorized_emails:
            config['authorized_emails'] = json.loads(row.authorized_emails)
        if row.authorized_domains:
            config['authorized_domains'] = json.loads(row.authorized_domains)
        if row.slack_webhook_url:
            config['features']['slack_webhook_url'] = row.slack_webhook_url
        if row.slack_audit_webhook_url:
            config['features']['slack_audit_webhook_url'] = row.slack_audit_webhook_url
        if row.hitl_webhook_url:
            config['features']['hitl_webhook_url'] = row.hitl_webhook_url
        if row.admin_token:
            config['admin_token'] = row.admin_token
        if row.auto_approve_formats:
            config['creative_engine']['auto_approve_formats'] = json.loads(row.auto_approve_formats)
        if row.policy_settings:
            config['policy_settings'] = json.loads(row.policy_settings)
        
        # Get adapter config
        adapter_row = connection.execute(
            sa.select([adapter_config_table]).where(
                adapter_config_table.c.tenant_id == tenant_id
            )
        ).first()
        
        if adapter_row and row.ad_server:
            adapter_type = row.ad_server
            adapter_config = {'enabled': True}
            
            if adapter_type == 'mock':
                if adapter_row.mock_dry_run is not None:
                    adapter_config['dry_run'] = bool(adapter_row.mock_dry_run)
                    
            elif adapter_type == 'google_ad_manager':
                if adapter_row.gam_network_code:
                    adapter_config['network_code'] = adapter_row.gam_network_code
                if adapter_row.gam_refresh_token:
                    adapter_config['refresh_token'] = adapter_row.gam_refresh_token
                if adapter_row.gam_company_id:
                    adapter_config['company_id'] = adapter_row.gam_company_id
                if adapter_row.gam_trafficker_id:
                    adapter_config['trafficker_id'] = adapter_row.gam_trafficker_id
                adapter_config['manual_approval_required'] = bool(adapter_row.gam_manual_approval_required)
                
            elif adapter_type == 'kevel':
                if adapter_row.kevel_network_id:
                    adapter_config['network_id'] = adapter_row.kevel_network_id
                if adapter_row.kevel_api_key:
                    adapter_config['api_key'] = adapter_row.kevel_api_key
                adapter_config['manual_approval_required'] = bool(adapter_row.kevel_manual_approval_required)
                
            elif adapter_type == 'triton':
                if adapter_row.triton_station_id:
                    adapter_config['station_id'] = adapter_row.triton_station_id
                if adapter_row.triton_api_key:
                    adapter_config['api_key'] = adapter_row.triton_api_key
            
            config['adapters'][adapter_type] = adapter_config
        
        # Update tenant with reconstructed config
        connection.execute(
            tenants_table.update().where(
                tenants_table.c.tenant_id == tenant_id
            ).values(config=json.dumps(config))
        )