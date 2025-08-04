"""Move config JSON to proper database columns

Revision ID: 005_move_config_to_columns
Revises: 004_add_superadmin_config
Create Date: 2025-02-04

"""
from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = '005_move_config_to_columns'
down_revision = '004_add_superadmin_config'
branch_labels = None
depends_on = None


def upgrade():
    """Move config fields to proper database columns."""
    
    # Get the current connection to check column existence
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_columns = [col['name'] for col in inspector.get_columns('tenants')]
    
    # Add new columns to tenants table only if they don't exist
    if 'ad_server' not in existing_columns:
        op.add_column('tenants', sa.Column('ad_server', sa.String(50), nullable=True))
    if 'max_daily_budget' not in existing_columns:
        op.add_column('tenants', sa.Column('max_daily_budget', sa.Integer(), nullable=False, server_default='10000'))
    if 'enable_aee_signals' not in existing_columns:
        op.add_column('tenants', sa.Column('enable_aee_signals', sa.Boolean(), nullable=False, server_default='1'))
    if 'authorized_emails' not in existing_columns:
        op.add_column('tenants', sa.Column('authorized_emails', sa.Text(), nullable=True))  # JSON array
    if 'authorized_domains' not in existing_columns:
        op.add_column('tenants', sa.Column('authorized_domains', sa.Text(), nullable=True))  # JSON array
    if 'slack_webhook_url' not in existing_columns:
        op.add_column('tenants', sa.Column('slack_webhook_url', sa.String(500), nullable=True))
    if 'admin_token' not in existing_columns:
        op.add_column('tenants', sa.Column('admin_token', sa.String(100), nullable=True))
    
    # Creative engine settings
    if 'auto_approve_formats' not in existing_columns:
        op.add_column('tenants', sa.Column('auto_approve_formats', sa.Text(), nullable=True))  # JSON array
    if 'human_review_required' not in existing_columns:
        op.add_column('tenants', sa.Column('human_review_required', sa.Boolean(), nullable=False, server_default='1'))
    
    # Create adapter_config table for adapter-specific settings
    existing_tables = inspector.get_table_names()
    if 'adapter_config' not in existing_tables:
        op.create_table(
            'adapter_config',
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('adapter_type', sa.String(50), nullable=False),
        
        # Mock adapter
        sa.Column('mock_dry_run', sa.Boolean(), nullable=True),
        
        # Google Ad Manager
        sa.Column('gam_network_code', sa.String(50), nullable=True),
        sa.Column('gam_refresh_token', sa.Text(), nullable=True),
        sa.Column('gam_company_id', sa.String(50), nullable=True),
        sa.Column('gam_trafficker_id', sa.String(50), nullable=True),
        sa.Column('gam_manual_approval_required', sa.Boolean(), nullable=True, server_default='0'),
        
        # Kevel
        sa.Column('kevel_network_id', sa.String(50), nullable=True),
        sa.Column('kevel_api_key', sa.String(100), nullable=True),
        sa.Column('kevel_manual_approval_required', sa.Boolean(), nullable=True, server_default='0'),
        
        # Triton
        sa.Column('triton_station_id', sa.String(50), nullable=True),
        sa.Column('triton_api_key', sa.String(100), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
        )
        
        # Create index on adapter_type
        op.create_index('idx_adapter_config_type', 'adapter_config', ['adapter_type'])
    
    # Migrate existing data
    connection = op.get_bind()
    
    # Get all tenants with their config
    tenants = connection.execute(sa.text("SELECT tenant_id, config FROM tenants"))
    
    for tenant in tenants:
        tenant_id = tenant[0]
        config = tenant[1]
        
        # Parse config JSON
        if isinstance(config, str):
            config = json.loads(config)
        
        # Extract ad server from adapters
        ad_server = None
        adapter_config = {}
        
        if 'adapters' in config:
            for adapter_name, adapter_data in config['adapters'].items():
                if adapter_data.get('enabled', False):
                    ad_server = adapter_name
                    adapter_config = adapter_data
                    break
        
        # Update tenant columns
        update_data = {
            'ad_server': ad_server,
            'max_daily_budget': config.get('features', {}).get('max_daily_budget', 10000),
            'enable_aee_signals': config.get('features', {}).get('enable_aee_signals', True),
            'admin_token': config.get('admin_token'),
            'human_review_required': config.get('creative_engine', {}).get('human_review_required', True)
        }
        
        # Handle JSON arrays
        if 'authorized_emails' in config:
            update_data['authorized_emails'] = json.dumps(config['authorized_emails'])
        if 'authorized_domains' in config:
            update_data['authorized_domains'] = json.dumps(config['authorized_domains'])
        if 'creative_engine' in config and 'auto_approve_formats' in config['creative_engine']:
            update_data['auto_approve_formats'] = json.dumps(config['creative_engine']['auto_approve_formats'])
        
        # Handle Slack webhook specially (might be in integrations)
        if 'integrations' in config and 'slack' in config['integrations']:
            update_data['slack_webhook_url'] = config['integrations']['slack'].get('webhook_url')
        
        # Build UPDATE statement
        set_clause = ', '.join([f"{k} = :{k}" for k in update_data.keys()])
        update_stmt = sa.text(f"UPDATE tenants SET {set_clause} WHERE tenant_id = :tenant_id")
        
        update_data['tenant_id'] = tenant_id
        connection.execute(update_stmt, update_data)
        
        # Insert adapter config if we have one
        if ad_server and adapter_config:
            insert_data = {
                'tenant_id': tenant_id,
                'adapter_type': ad_server
            }
            
            if ad_server == 'mock':
                insert_data['mock_dry_run'] = adapter_config.get('dry_run', False)
                
            elif ad_server == 'google_ad_manager' or ad_server == 'gam':
                insert_data['adapter_type'] = 'google_ad_manager'  # Normalize
                insert_data['gam_network_code'] = adapter_config.get('network_code') or adapter_config.get('network_id')
                insert_data['gam_refresh_token'] = adapter_config.get('refresh_token')
                insert_data['gam_company_id'] = adapter_config.get('company_id')
                insert_data['gam_trafficker_id'] = adapter_config.get('trafficker_id')
                insert_data['gam_manual_approval_required'] = adapter_config.get('manual_approval_required', False)
                
            elif ad_server == 'kevel':
                insert_data['kevel_network_id'] = adapter_config.get('network_id')
                insert_data['kevel_api_key'] = adapter_config.get('api_key')
                insert_data['kevel_manual_approval_required'] = adapter_config.get('manual_approval_required', False)
                
            elif ad_server == 'triton':
                insert_data['triton_station_id'] = adapter_config.get('station_id')
                insert_data['triton_api_key'] = adapter_config.get('api_key')
            
            # Check if adapter config already exists for this tenant
            existing = connection.execute(
                sa.text("SELECT COUNT(*) FROM adapter_config WHERE tenant_id = :tenant_id"),
                {'tenant_id': tenant_id}
            ).scalar()
            
            if existing == 0:
                # Build INSERT statement
                columns = list(insert_data.keys())
                values = [f":{k}" for k in columns]
                insert_stmt = sa.text(f"INSERT INTO adapter_config ({', '.join(columns)}) VALUES ({', '.join(values)})")
                
                connection.execute(insert_stmt, insert_data)


def downgrade():
    """Restore config JSON from database columns."""
    
    # First reconstruct config JSON from columns
    connection = op.get_bind()
    
    # Get all tenants with their new column data
    tenants = connection.execute(sa.text("""
        SELECT t.tenant_id, t.ad_server, t.max_daily_budget, t.enable_aee_signals,
               t.authorized_emails, t.authorized_domains, t.slack_webhook_url,
               t.admin_token, t.auto_approve_formats, t.human_review_required,
               ac.adapter_type, ac.mock_dry_run, ac.gam_network_code, ac.gam_refresh_token,
               ac.gam_company_id, ac.gam_trafficker_id, ac.gam_manual_approval_required,
               ac.kevel_network_id, ac.kevel_api_key, ac.kevel_manual_approval_required,
               ac.triton_station_id, ac.triton_api_key
        FROM tenants t
        LEFT JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
    """))
    
    for row in tenants:
        tenant_id = row[0]
        
        # Reconstruct config JSON
        config = {
            'features': {
                'max_daily_budget': row[2],
                'enable_aee_signals': bool(row[3])
            },
            'creative_engine': {
                'human_review_required': bool(row[9])
            },
            'adapters': {}
        }
        
        # Add optional fields
        if row[4]:  # authorized_emails
            config['authorized_emails'] = json.loads(row[4])
        if row[5]:  # authorized_domains
            config['authorized_domains'] = json.loads(row[5])
        if row[6]:  # slack_webhook_url
            config['integrations'] = {'slack': {'webhook_url': row[6]}}
        if row[7]:  # admin_token
            config['admin_token'] = row[7]
        if row[8]:  # auto_approve_formats
            config['creative_engine']['auto_approve_formats'] = json.loads(row[8])
        
        # Add adapter config
        if row[10]:  # adapter_type
            adapter_type = row[10]
            adapter_config = {'enabled': True}
            
            if adapter_type == 'mock':
                adapter_config['dry_run'] = bool(row[11])
                
            elif adapter_type == 'google_ad_manager':
                if row[12]:
                    adapter_config['network_code'] = row[12]
                if row[13]:
                    adapter_config['refresh_token'] = row[13]
                if row[14]:
                    adapter_config['company_id'] = row[14]
                if row[15]:
                    adapter_config['trafficker_id'] = row[15]
                adapter_config['manual_approval_required'] = bool(row[16])
                
            elif adapter_type == 'kevel':
                if row[17]:
                    adapter_config['network_id'] = row[17]
                if row[18]:
                    adapter_config['api_key'] = row[18]
                adapter_config['manual_approval_required'] = bool(row[19])
                
            elif adapter_type == 'triton':
                if row[20]:
                    adapter_config['station_id'] = row[20]
                if row[21]:
                    adapter_config['api_key'] = row[21]
            
            config['adapters'][adapter_type] = adapter_config
        
        # Update tenant config
        update_stmt = sa.text("UPDATE tenants SET config = :config WHERE tenant_id = :tenant_id")
        connection.execute(update_stmt, {'config': json.dumps(config), 'tenant_id': tenant_id})
    
    # Drop adapter_config table
    op.drop_index('idx_adapter_config_type', 'adapter_config')
    op.drop_table('adapter_config')
    
    # Drop columns from tenants table
    op.drop_column('tenants', 'human_review_required')
    op.drop_column('tenants', 'auto_approve_formats')
    op.drop_column('tenants', 'admin_token')
    op.drop_column('tenants', 'slack_webhook_url')
    op.drop_column('tenants', 'authorized_domains')
    op.drop_column('tenants', 'authorized_emails')
    op.drop_column('tenants', 'enable_aee_signals')
    op.drop_column('tenants', 'max_daily_budget')
    op.drop_column('tenants', 'ad_server')