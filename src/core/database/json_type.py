"""Custom SQLAlchemy JSON type that handles cross-database compatibility.

This type ensures consistent behavior between SQLite (which stores JSON as strings)
and PostgreSQL (which has native JSONB support).
"""

import json
import logging
from typing import Any

from sqlalchemy import JSON, TypeDecorator

logger = logging.getLogger(__name__)


class JSONType(TypeDecorator):
    """JSON type that automatically deserializes string JSON from SQLite.

    SQLite stores JSON as text strings, while PostgreSQL uses native JSONB.
    This type decorator ensures that regardless of the database backend,
    Python code always receives deserialized Python objects (dict/list).

    Usage:
        class MyModel(Base):
            data = Column(JSONType)  # Instead of Column(JSON)

    Features:
    - Automatically deserializes JSON strings to Python objects
    - Handles None values gracefully
    - Logs warnings for invalid JSON (returns None)
    - Works with both SQLite and PostgreSQL
    - Cache-safe for SQLAlchemy query caching
    """

    impl = JSON
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Process value returned from database.

        Args:
            value: Raw value from database (may be string, dict, list, or None)
            dialect: Database dialect (postgres, sqlite, etc.)

        Returns:
            Python object (dict/list) or None
        """
        if value is None:
            return None

        # If already deserialized (PostgreSQL native JSONB), return as-is
        if isinstance(value, dict | list):
            return value

        # If string (SQLite JSON storage), deserialize it
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in database, returning None. Error: {e}, Value preview: {value[:100]}")
                return None

        # Unexpected type - log warning and return as-is
        logger.warning(f"Unexpected JSON column type: {type(value).__name__}. Expected str, dict, or list.")
        return value
