"""Database schema definitions that work across different database backends."""

# SQL schema with vendor-specific variations
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    subdomain TEXT UNIQUE NOT NULL,
    config TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    billing_plan TEXT DEFAULT 'standard',
    billing_contact TEXT
);

CREATE TABLE IF NOT EXISTS products (
    tenant_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    formats TEXT NOT NULL,
    targeting_template TEXT NOT NULL,
    delivery_type TEXT NOT NULL,
    is_fixed_price BOOLEAN NOT NULL,
    cpm REAL,
    price_guidance TEXT,
    is_custom BOOLEAN DEFAULT 0,
    expires_at TIMESTAMP,
    PRIMARY KEY (tenant_id, product_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE IF NOT EXISTS principals (
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    name TEXT NOT NULL,
    platform_mappings TEXT NOT NULL,
    access_token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_subdomain ON tenants(subdomain);
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_tenant ON principals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_token ON principals(access_token);
"""

SCHEMA_POSTGRESQL = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    config JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    billing_plan VARCHAR(50) DEFAULT 'standard',
    billing_contact VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS products (
    tenant_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    formats JSONB NOT NULL,
    targeting_template JSONB NOT NULL,
    delivery_type VARCHAR(50) NOT NULL,
    is_fixed_price BOOLEAN NOT NULL,
    cpm DECIMAL(10,2),
    price_guidance JSONB,
    is_custom BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP,
    PRIMARY KEY (tenant_id, product_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS principals (
    tenant_id VARCHAR(50) NOT NULL,
    principal_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    platform_mappings JSONB NOT NULL,
    access_token VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subdomain ON tenants(subdomain);
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_tenant ON principals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_token ON principals(access_token);
"""

SCHEMA_MYSQL = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    config JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    billing_plan VARCHAR(50) DEFAULT 'standard',
    billing_contact VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
    tenant_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    formats JSON NOT NULL,
    targeting_template JSON NOT NULL,
    delivery_type VARCHAR(50) NOT NULL,
    is_fixed_price BOOLEAN NOT NULL,
    cpm DECIMAL(10,2),
    price_guidance JSON,
    is_custom BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP NULL,
    PRIMARY KEY (tenant_id, product_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS principals (
    tenant_id VARCHAR(50) NOT NULL,
    principal_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    platform_mappings JSON NOT NULL,
    access_token VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, principal_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_subdomain ON tenants(subdomain);
CREATE INDEX idx_products_tenant ON products(tenant_id);
CREATE INDEX idx_principals_tenant ON principals(tenant_id);
CREATE INDEX idx_principals_token ON principals(access_token);
"""

def get_schema(db_type: str) -> str:
    """Get the appropriate schema for the database type."""
    schemas = {
        'sqlite': SCHEMA_SQLITE,
        'postgresql': SCHEMA_POSTGRESQL,
        'mysql': SCHEMA_MYSQL
    }
    
    schema = schemas.get(db_type)
    if not schema:
        raise ValueError(f"Unsupported database type: {db_type}")
    
    return schema