"""Database configuration with support for multiple backends."""

import os
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import sqlite3

class DatabaseConfig:
    """Flexible database configuration supporting SQLite and PostgreSQL."""
    
    @staticmethod
    def get_db_config() -> Dict[str, Any]:
        """Get database configuration from environment or defaults."""
        
        # Support DATABASE_URL for easy deployment (Heroku, Railway, etc.)
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            return DatabaseConfig._parse_database_url(database_url)
        
        # Individual environment variables
        db_type = os.environ.get('DB_TYPE', 'sqlite').lower()
        
        if db_type == 'sqlite':
            # Use persistent directory for SQLite
            data_dir = os.environ.get('DATA_DIR', os.path.expanduser('~/.adcp'))
            os.makedirs(data_dir, exist_ok=True)
            
            return {
                'type': 'sqlite',
                'path': os.path.join(data_dir, 'adcp.db'),
                'check_same_thread': False  # Allow multi-threaded access
            }
        
        elif db_type == 'postgresql':
            return {
                'type': 'postgresql',
                'host': os.environ.get('DB_HOST', 'localhost'),
                'port': int(os.environ.get('DB_PORT', '5432')),
                'database': os.environ.get('DB_NAME', 'adcp'),
                'user': os.environ.get('DB_USER', 'adcp'),
                'password': os.environ.get('DB_PASSWORD', ''),
                'sslmode': os.environ.get('DB_SSLMODE', 'prefer')
            }
        
        else:
            raise ValueError(f"Unsupported database type: {db_type}. Use 'sqlite' or 'postgresql'")
    
    @staticmethod
    def _parse_database_url(url: str) -> Dict[str, Any]:
        """Parse DATABASE_URL into configuration dict."""
        parsed = urlparse(url)
        
        if parsed.scheme == 'sqlite':
            return {
                'type': 'sqlite',
                'path': parsed.path.lstrip('/'),
                'check_same_thread': False
            }
        
        elif parsed.scheme in ['postgres', 'postgresql']:
            return {
                'type': 'postgresql',
                'host': parsed.hostname,
                'port': parsed.port or 5432,
                'database': parsed.path.lstrip('/'),
                'user': parsed.username,
                'password': parsed.password or '',
                'sslmode': 'require' if 'sslmode=require' in url else 'prefer'
            }
        
        else:
            raise ValueError(f"Unsupported database scheme: {parsed.scheme}. Use 'sqlite' or 'postgresql'")
    
    @staticmethod
    def get_connection_string() -> str:
        """Get connection string for SQLAlchemy."""
        config = DatabaseConfig.get_db_config()
        
        if config['type'] == 'sqlite':
            return f"sqlite:///{config['path']}"
        
        elif config['type'] == 'postgresql':
            password = config['password']
            if password:
                auth = f"{config['user']}:{password}"
            else:
                auth = config['user']
            
            return (f"postgresql://{auth}@{config['host']}:{config['port']}"
                   f"/{config['database']}?sslmode={config['sslmode']}")
        
        else:
            raise ValueError(f"Unsupported database type: {config['type']}")


class DatabaseConnection:
    """Database connection wrapper supporting multiple backends."""
    
    def __init__(self):
        self.config = DatabaseConfig.get_db_config()
        self.connection = None
    
    def connect(self):
        """Connect to database based on configuration."""
        if self.config['type'] == 'sqlite':
            self.connection = sqlite3.connect(
                self.config['path'],
                check_same_thread=self.config['check_same_thread']
            )
            # Enable Row objects instead of tuples
            self.connection.row_factory = sqlite3.Row
            # Enable foreign keys for SQLite
            self.connection.execute("PRAGMA foreign_keys = ON")
        
        elif self.config['type'] == 'postgresql':
            import psycopg2
            import psycopg2.extras
            self.connection = psycopg2.connect(
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                sslmode=self.config['sslmode'],
                cursor_factory=psycopg2.extras.DictCursor
            )
        
        return self.connection
    
    def execute(self, query: str, params: Optional[tuple] = None):
        """Execute a query with proper parameter substitution."""
        cursor = self.connection.cursor()
        
        # Convert parameter placeholders based on database type
        if self.config['type'] == 'postgresql' and '?' in query:
            # Convert SQLite-style ? to %s for PostgreSQL
            query = query.replace('?', '%s')
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        return cursor
    
    def cursor(self):
        """Get a database cursor."""
        return self.connection.cursor()
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
    
    def __enter__(self):
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and close connection."""
        self.close()
        return False


def get_db_connection() -> DatabaseConnection:
    """Get a database connection using current configuration."""
    conn = DatabaseConnection()
    conn.connect()
    return conn