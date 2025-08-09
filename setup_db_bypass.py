#!/usr/bin/env python
"""Create database directly without Alembic migrations."""

from sqlalchemy import create_engine
from models import Base
import os

# Use SQLite for local development
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///adcp_local.db')

# Create engine
engine = create_engine(DATABASE_URL)

# Create all tables
Base.metadata.create_all(engine)

print(f"✅ Database tables created successfully at {DATABASE_URL}")
print("Note: This bypasses migrations. Run 'uv run alembic stamp head' after fixing migration issues.")