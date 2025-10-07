"""Custom SQLAlchemy JSON type that handles cross-database compatibility.

This type ensures consistent behavior between SQLite (which stores JSON as strings)
and PostgreSQL (which has native JSONB support).
"""

import json
import logging
from typing import Any

from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)


class JSONType(TypeDecorator):
    """JSON type that automatically handles JSON serialization/deserialization.

    SQLite stores JSON as text strings, while PostgreSQL uses native JSONB.
    This type decorator ensures that regardless of the database backend,
    Python code always receives deserialized Python objects (dict/list).

    Usage:
        class MyModel(Base):
            data = Column(JSONType)  # Instead of Column(JSON)

    Features:
    - Automatically serializes Python objects to JSON strings for storage
    - Automatically deserializes JSON strings to Python objects when reading
    - Handles None values gracefully (stores as SQL NULL, not JSON 'null')
    - Validates data before storage
    - Optimized for PostgreSQL (skips unnecessary processing)
    - Works with both SQLite and PostgreSQL
    - Cache-safe for SQLAlchemy query caching

    Error Handling:
    - Invalid JSON in database raises ValueError (fail-fast for data integrity)
    - Non-JSON types being stored are logged and converted to empty dict
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Process value being sent to database.

        Args:
            value: Python object to store (dict, list, or None)
            dialect: Database dialect (postgres, sqlite, etc.)

        Returns:
            JSON string ready for database storage, or None for SQL NULL
        """
        if value is None:
            return None

        # Validate that we're storing proper JSON-serializable types
        if not isinstance(value, dict | list):
            logger.warning(
                f"JSONType received non-JSON type: {type(value).__name__}. "
                f"Converting to empty dict to prevent data corruption."
            )
            value = {}

        # Serialize to JSON string for database storage
        try:
            return json.dumps(value)
        except (TypeError, ValueError) as e:
            logger.error(
                f"Failed to serialize value to JSON: {e}. "
                f"Value type: {type(value).__name__}, "
                f"Value preview: {str(value)[:100]}"
            )
            # Fall back to empty dict
            return json.dumps({})

    def process_result_value(self, value: Any, dialect: Dialect) -> dict | list | None:
        """Process value returned from database.

        Args:
            value: Raw value from database (may be string, dict, list, or None)
            dialect: Database dialect (postgres, sqlite, etc.)

        Returns:
            Python object (dict/list) or None

        Raises:
            ValueError: If database contains invalid JSON (data corruption)
            TypeError: If database returns unexpected type
        """
        if value is None:
            return None

        # PostgreSQL fast path - already deserialized by driver
        if dialect and dialect.name == "postgresql" and isinstance(value, dict | list):
            return value

        # If already deserialized (defensive check)
        if isinstance(value, dict | list):
            return value

        # SQLite path - deserialize JSON string
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(
                    f"CRITICAL: Database contains invalid JSON. "
                    f"This indicates data corruption. "
                    f"Error: {e}, Value preview: {value[:100]}"
                )
                raise ValueError(
                    f"Database contains invalid JSON data: {e}. " "Please investigate data corruption immediately."
                ) from e

        # Unexpected type - fail loudly
        logger.error(
            f"Unexpected type in JSON column: {type(value).__name__}. "
            f"Expected str (SQLite), dict, or list (PostgreSQL). "
            f"Value: {repr(value)[:100]}"
        )
        raise TypeError(
            f"Unexpected type in JSON column: {type(value).__name__}. " "This may indicate a database schema issue."
        )
