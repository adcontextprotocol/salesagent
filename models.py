"""SQLAlchemy models for database schema."""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, 
    DECIMAL, Date, JSON, UniqueConstraint, Index, CheckConstraint,
    ForeignKeyConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class Tenant(Base):
    __tablename__ = 'tenants'
    
    tenant_id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True, nullable=False)
    config = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    billing_plan = Column(String(50), default='standard')
    billing_contact = Column(String(255))
    
    # Relationships
    products = relationship("Product", back_populates="tenant", cascade="all, delete-orphan")
    principals = relationship("Principal", back_populates="tenant", cascade="all, delete-orphan")
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    media_buys = relationship("MediaBuy", back_populates="tenant", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_subdomain', 'subdomain'),
    )

class CreativeFormat(Base):
    __tablename__ = 'creative_formats'
    
    format_id = Column(String(50), primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=True)
    name = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)
    description = Column(Text)
    width = Column(Integer)
    height = Column(Integer)
    duration_seconds = Column(Integer)
    max_file_size_kb = Column(Integer)
    specs = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    is_standard = Column(Boolean, default=True)
    is_foundational = Column(Boolean, default=False)
    extends = Column(String(50), ForeignKey('creative_formats.format_id', ondelete='RESTRICT'), nullable=True)
    modifications = Column(JSON, nullable=True)  # JSONB in PostgreSQL
    source_url = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", backref="creative_formats")
    base_format = relationship("CreativeFormat", remote_side=[format_id], backref="extensions")
    
    __table_args__ = (
        CheckConstraint("type IN ('display', 'video', 'audio', 'native')"),
    )

class Product(Base):
    __tablename__ = 'products'
    
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), primary_key=True)
    product_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    formats = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    targeting_template = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    delivery_type = Column(String(50), nullable=False)
    is_fixed_price = Column(Boolean, nullable=False)
    cpm = Column(DECIMAL(10, 2))
    price_guidance = Column(JSON)  # JSONB in PostgreSQL
    is_custom = Column(Boolean, default=False)
    expires_at = Column(DateTime)
    countries = Column(JSON)  # JSONB in PostgreSQL
    implementation_config = Column(JSON)  # JSONB in PostgreSQL
    
    # Relationships
    tenant = relationship("Tenant", back_populates="products")
    
    __table_args__ = (
        Index('idx_products_tenant', 'tenant_id'),
    )

class Principal(Base):
    __tablename__ = 'principals'
    
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), primary_key=True)
    principal_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    platform_mappings = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    access_token = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="principals")
    media_buys = relationship("MediaBuy", back_populates="principal")
    
    __table_args__ = (
        Index('idx_principals_tenant', 'tenant_id'),
        Index('idx_principals_token', 'access_token'),
    )

class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(String(50), primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    google_id = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'manager', 'viewer')"),
        Index('idx_users_tenant', 'tenant_id'),
        Index('idx_users_email', 'email'),
        Index('idx_users_google_id', 'google_id'),
    )

class MediaBuy(Base):
    __tablename__ = 'media_buys'
    
    media_buy_id = Column(String(100), primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    principal_id = Column(String(100), nullable=False)
    order_name = Column(String(255), nullable=False)
    advertiser_name = Column(String(255), nullable=False)
    campaign_objective = Column(String(100))
    kpi_goal = Column(String(255))
    budget = Column(DECIMAL(15, 2))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(50), nullable=False, default='draft')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    approved_at = Column(DateTime)
    approved_by = Column(String(255))
    raw_request = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    
    # Relationships
    tenant = relationship("Tenant", back_populates="media_buys")
    principal = relationship("Principal", foreign_keys=[tenant_id, principal_id],
                           primaryjoin="and_(MediaBuy.tenant_id==Principal.tenant_id, MediaBuy.principal_id==Principal.principal_id)")
    tasks = relationship("Task", back_populates="media_buy", cascade="all, delete-orphan")
    
    __table_args__ = (
        ForeignKeyConstraint(['tenant_id', 'principal_id'], ['principals.tenant_id', 'principals.principal_id'], ondelete='CASCADE'),
        Index('idx_media_buys_tenant', 'tenant_id'),
        Index('idx_media_buys_status', 'status'),
    )

class Task(Base):
    __tablename__ = 'tasks'
    
    task_id = Column(String(100), primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    media_buy_id = Column(String(100), ForeignKey('media_buys.media_buy_id', ondelete='CASCADE'), nullable=False)
    task_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default='pending')
    assigned_to = Column(String(255))
    due_date = Column(DateTime)
    completed_at = Column(DateTime)
    completed_by = Column(String(255))
    task_metadata = Column('metadata', JSON)  # JSONB in PostgreSQL
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="tasks")
    media_buy = relationship("MediaBuy", back_populates="tasks")
    
    __table_args__ = (
        Index('idx_tasks_tenant', 'tenant_id'),
        Index('idx_tasks_media_buy', 'media_buy_id'),
        Index('idx_tasks_status', 'status'),
    )

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime, server_default=func.now())
    operation = Column(String(100), nullable=False)
    principal_name = Column(String(255))
    principal_id = Column(String(100))
    adapter_id = Column(String(50))
    success = Column(Boolean, nullable=False)
    error_message = Column(Text)
    details = Column(JSON)  # JSONB in PostgreSQL
    
    # Relationships
    tenant = relationship("Tenant", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_audit_logs_tenant', 'tenant_id'),
        Index('idx_audit_logs_timestamp', 'timestamp'),
    )


class GAMInventory(Base):
    __tablename__ = 'gam_inventory'
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    inventory_type = Column(String(20), nullable=False)  # 'ad_unit', 'placement', 'label'
    inventory_id = Column(String(50), nullable=False)  # GAM ID
    name = Column(String(255), nullable=False)
    path = Column(JSON)  # Array of path components for ad units
    status = Column(String(20), nullable=False)
    inventory_metadata = Column(JSON)  # Full inventory details
    last_synced = Column(DateTime, nullable=False, default=func.now())
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'inventory_type', 'inventory_id', name='uq_gam_inventory'),
        Index('idx_gam_inventory_tenant', 'tenant_id'),
        Index('idx_gam_inventory_type', 'inventory_type'),
        Index('idx_gam_inventory_status', 'status'),
    )


class ProductInventoryMapping(Base):
    __tablename__ = 'product_inventory_mappings'
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False)
    product_id = Column(String(50), nullable=False)
    inventory_type = Column(String(20), nullable=False)  # 'ad_unit' or 'placement'
    inventory_id = Column(String(50), nullable=False)  # GAM inventory ID
    is_primary = Column(Boolean, default=False)  # Primary targeting for the product
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    # Add foreign key constraint for product
    __table_args__ = (
        ForeignKeyConstraint(
            ['tenant_id', 'product_id'],
            ['products.tenant_id', 'products.product_id'],
            ondelete='CASCADE'
        ),
        Index('idx_product_inventory_mapping', 'tenant_id', 'product_id'),
        UniqueConstraint('tenant_id', 'product_id', 'inventory_type', 'inventory_id', 
                        name='uq_product_inventory'),
    )


