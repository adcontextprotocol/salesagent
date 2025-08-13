"""Add JSON validation constraints.

Revision ID: 016_add_json_validation
Revises: 015_workflow_improvements
Create Date: 2025-01-13

This migration adds CHECK constraints for JSON fields in PostgreSQL
to ensure data integrity. SQLite will skip these as it doesn't support
CHECK constraints on JSON columns.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = '016_add_json_validation'
down_revision = '015_workflow_improvements'
branch_labels = None
depends_on = None


def upgrade():
    """Add JSON validation constraints for PostgreSQL."""
    
    # Get database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    # Only add constraints for PostgreSQL
    if dialect_name == 'postgresql':
        # Tenant table constraints
        op.execute(text("""
            ALTER TABLE tenants 
            ADD CONSTRAINT check_authorized_emails_is_array 
            CHECK (jsonb_typeof(authorized_emails) = 'array' OR authorized_emails IS NULL)
        """))
        
        op.execute(text("""
            ALTER TABLE tenants 
            ADD CONSTRAINT check_authorized_domains_is_array 
            CHECK (jsonb_typeof(authorized_domains) = 'array' OR authorized_domains IS NULL)
        """))
        
        op.execute(text("""
            ALTER TABLE tenants 
            ADD CONSTRAINT check_auto_approve_formats_is_array 
            CHECK (jsonb_typeof(auto_approve_formats) = 'array' OR auto_approve_formats IS NULL)
        """))
        
        op.execute(text("""
            ALTER TABLE tenants 
            ADD CONSTRAINT check_policy_settings_is_object 
            CHECK (jsonb_typeof(policy_settings) = 'object' OR policy_settings IS NULL)
        """))
        
        # Product table constraints
        op.execute(text("""
            ALTER TABLE products 
            ADD CONSTRAINT check_formats_is_array 
            CHECK (jsonb_typeof(formats) = 'array')
        """))
        
        op.execute(text("""
            ALTER TABLE products 
            ADD CONSTRAINT check_targeting_template_is_object 
            CHECK (jsonb_typeof(targeting_template) = 'object')
        """))
        
        op.execute(text("""
            ALTER TABLE products 
            ADD CONSTRAINT check_countries_is_array 
            CHECK (jsonb_typeof(countries) = 'array' OR countries IS NULL)
        """))
        
        # Principal table constraints
        op.execute(text("""
            ALTER TABLE principals 
            ADD CONSTRAINT check_platform_mappings_is_object 
            CHECK (jsonb_typeof(platform_mappings) = 'object')
        """))
        
        # WorkflowStep table constraints
        op.execute(text("""
            ALTER TABLE workflow_steps 
            ADD CONSTRAINT check_comments_is_array 
            CHECK (jsonb_typeof(comments) = 'array')
        """))
        
        op.execute(text("""
            ALTER TABLE workflow_steps 
            ADD CONSTRAINT check_request_data_is_object 
            CHECK (jsonb_typeof(request_data) = 'object' OR request_data IS NULL)
        """))
        
        op.execute(text("""
            ALTER TABLE workflow_steps 
            ADD CONSTRAINT check_response_data_is_object 
            CHECK (jsonb_typeof(response_data) = 'object' OR response_data IS NULL)
        """))
        
        # MediaBuy table constraints
        op.execute(text("""
            ALTER TABLE media_buys 
            ADD CONSTRAINT check_raw_request_is_object 
            CHECK (jsonb_typeof(raw_request) = 'object')
        """))
        
        # GAM tables constraints (if they exist)
        try:
            op.execute(text("""
                ALTER TABLE gam_orders 
                ADD CONSTRAINT check_applied_labels_is_array 
                CHECK (jsonb_typeof(applied_labels) = 'array' OR applied_labels IS NULL)
            """))
            
            op.execute(text("""
                ALTER TABLE gam_line_items 
                ADD CONSTRAINT check_delivery_data_is_object 
                CHECK (jsonb_typeof(delivery_data) = 'object' OR delivery_data IS NULL)
            """))
        except Exception:
            # Tables might not exist in all deployments
            pass
    
    print(f"JSON validation constraints added for {dialect_name}")


def downgrade():
    """Remove JSON validation constraints."""
    
    # Get database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    # Only remove constraints for PostgreSQL
    if dialect_name == 'postgresql':
        # Remove tenant constraints
        constraints = [
            'check_authorized_emails_is_array',
            'check_authorized_domains_is_array',
            'check_auto_approve_formats_is_array',
            'check_policy_settings_is_object'
        ]
        for constraint in constraints:
            try:
                op.execute(text(f"ALTER TABLE tenants DROP CONSTRAINT IF EXISTS {constraint}"))
            except Exception:
                pass
        
        # Remove product constraints
        constraints = [
            'check_formats_is_array',
            'check_targeting_template_is_object',
            'check_countries_is_array'
        ]
        for constraint in constraints:
            try:
                op.execute(text(f"ALTER TABLE products DROP CONSTRAINT IF EXISTS {constraint}"))
            except Exception:
                pass
        
        # Remove principal constraints
        try:
            op.execute(text("ALTER TABLE principals DROP CONSTRAINT IF EXISTS check_platform_mappings_is_object"))
        except Exception:
            pass
        
        # Remove workflow_steps constraints
        constraints = [
            'check_comments_is_array',
            'check_request_data_is_object',
            'check_response_data_is_object'
        ]
        for constraint in constraints:
            try:
                op.execute(text(f"ALTER TABLE workflow_steps DROP CONSTRAINT IF EXISTS {constraint}"))
            except Exception:
                pass
        
        # Remove media_buys constraints
        try:
            op.execute(text("ALTER TABLE media_buys DROP CONSTRAINT IF EXISTS check_raw_request_is_object"))
        except Exception:
            pass
        
        # Remove GAM table constraints
        try:
            op.execute(text("ALTER TABLE gam_orders DROP CONSTRAINT IF EXISTS check_applied_labels_is_array"))
            op.execute(text("ALTER TABLE gam_line_items DROP CONSTRAINT IF EXISTS check_delivery_data_is_object"))
        except Exception:
            pass