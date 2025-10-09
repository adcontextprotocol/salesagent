"""Database schema definitions for SQLite and PostgreSQL."""

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

CREATE TABLE IF NOT EXISTS creative_formats (
    format_id TEXT PRIMARY KEY,
    tenant_id TEXT,  -- NULL for standard formats, populated for custom formats
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('display', 'video', 'audio', 'native')),
    description TEXT,
    width INTEGER,
    height INTEGER,
    duration_seconds INTEGER,
    max_file_size_kb INTEGER,
    specs TEXT NOT NULL,
    is_standard BOOLEAN DEFAULT 1,
    is_foundational BOOLEAN DEFAULT 0,  -- True for base formats that can be extended
    extends TEXT,  -- Reference to foundational format_id
    modifications TEXT,  -- JSON with modifications to base format
    source_url TEXT,  -- URL where format was discovered
    platform_config TEXT,  -- JSON with platform-specific config (e.g., GAM creative template IDs)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (extends) REFERENCES creative_formats(format_id) ON DELETE RESTRICT
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
    countries TEXT,
    implementation_config TEXT,
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

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'viewer')),
    google_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE IF NOT EXISTS media_buys (
    media_buy_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    order_name TEXT NOT NULL,
    advertiser_name TEXT NOT NULL,
    campaign_objective TEXT,
    kpi_goal TEXT,
    budget REAL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approved_by TEXT,
    raw_request TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES principals(tenant_id, principal_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    media_buy_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_to TEXT,
    due_date TIMESTAMP,
    completed_at TIMESTAMP,
    completed_by TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (media_buy_id) REFERENCES media_buys(media_buy_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operation TEXT NOT NULL,
    principal_name TEXT,
    principal_id TEXT,
    adapter_id TEXT,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    details TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_subdomain ON tenants(subdomain);
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_tenant ON principals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_token ON principals(access_token);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_media_buys_tenant ON media_buys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_media_buys_status ON media_buys(status);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_media_buy ON tasks(media_buy_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);

CREATE TABLE IF NOT EXISTS superadmin_config (
    config_key TEXT PRIMARY KEY,
    config_value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);
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

CREATE TABLE IF NOT EXISTS creative_formats (
    format_id VARCHAR(50) PRIMARY KEY,
    tenant_id VARCHAR(50),  -- NULL for standard formats, populated for custom formats
    name VARCHAR(255) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('display', 'video', 'audio', 'native')),
    description TEXT,
    width INTEGER,
    height INTEGER,
    duration_seconds INTEGER,
    max_file_size_kb INTEGER,
    specs JSONB NOT NULL,
    is_standard BOOLEAN DEFAULT TRUE,
    is_foundational BOOLEAN DEFAULT FALSE,  -- True for base formats that can be extended
    extends VARCHAR(50),  -- Reference to foundational format_id
    modifications JSONB,  -- JSON with modifications to base format
    source_url TEXT,  -- URL where format was discovered
    platform_config JSONB,  -- Platform-specific config (e.g., GAM creative template IDs)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (extends) REFERENCES creative_formats(format_id) ON DELETE RESTRICT
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
    countries JSONB,
    implementation_config JSONB,
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

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(50) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'manager', 'viewer')),
    google_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_buys (
    media_buy_id VARCHAR(100) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    principal_id VARCHAR(100) NOT NULL,
    order_name VARCHAR(255) NOT NULL,
    advertiser_name VARCHAR(255) NOT NULL,
    campaign_objective VARCHAR(100),
    kpi_goal VARCHAR(255),
    budget DECIMAL(15,2),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    approved_at TIMESTAMP,
    approved_by VARCHAR(255),
    raw_request JSONB NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, principal_id) REFERENCES principals(tenant_id, principal_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(100) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    media_buy_id VARCHAR(100) NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    assigned_to VARCHAR(255),
    due_date TIMESTAMP,
    completed_at TIMESTAMP,
    completed_by VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (media_buy_id) REFERENCES media_buys(media_buy_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    operation VARCHAR(100) NOT NULL,
    principal_name VARCHAR(255),
    principal_id VARCHAR(100),
    adapter_id VARCHAR(50),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    details JSONB,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subdomain ON tenants(subdomain);
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_tenant ON principals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_principals_token ON principals(access_token);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_media_buys_tenant ON media_buys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_media_buys_status ON media_buys(status);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_media_buy ON tasks(media_buy_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);

CREATE TABLE IF NOT EXISTS superadmin_config (
    config_key VARCHAR(100) PRIMARY KEY,
    config_value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(255)
);
"""


def get_schema(db_type: str) -> str:
    """Get the appropriate schema for the database type."""
    schemas = {"sqlite": SCHEMA_SQLITE, "postgresql": SCHEMA_POSTGRESQL}

    schema = schemas.get(db_type)
    if not schema:
        raise ValueError(f"Unsupported database type: {db_type}. Use 'sqlite' or 'postgresql'")

    return schema
