"""Tests for custom SQLAlchemy JSONType that handles cross-database compatibility."""

import json

import pytest

from src.core.database.json_type import JSONType


class TestJSONType:
    """Test JSONType handles both string and native JSON correctly."""

    def test_process_result_value_with_none(self):
        """Test that None values are returned as None."""
        json_type = JSONType()
        result = json_type.process_result_value(None, None)
        assert result is None

    def test_process_result_value_with_dict(self):
        """Test that dict values (PostgreSQL native JSONB) are returned as-is."""
        json_type = JSONType()
        test_dict = {"key": "value", "nested": {"data": 123}}
        result = json_type.process_result_value(test_dict, None)
        assert result == test_dict
        assert isinstance(result, dict)

    def test_process_result_value_with_list(self):
        """Test that list values (PostgreSQL native JSONB) are returned as-is."""
        json_type = JSONType()
        test_list = ["item1", "item2", "item3"]
        result = json_type.process_result_value(test_list, None)
        assert result == test_list
        assert isinstance(result, list)

    def test_process_result_value_with_json_string_dict(self):
        """Test that JSON string (SQLite) is deserialized to dict."""
        json_type = JSONType()
        json_string = '{"key": "value", "count": 42}'
        result = json_type.process_result_value(json_string, None)
        assert result == {"key": "value", "count": 42}
        assert isinstance(result, dict)

    def test_process_result_value_with_json_string_list(self):
        """Test that JSON string array (SQLite) is deserialized to list."""
        json_type = JSONType()
        json_string = '["domain1.com", "domain2.com", "domain3.com"]'
        result = json_type.process_result_value(json_string, None)
        assert result == ["domain1.com", "domain2.com", "domain3.com"]
        assert isinstance(result, list)

    def test_process_result_value_with_empty_json_string(self):
        """Test that empty JSON array/object strings are properly handled."""
        json_type = JSONType()

        # Empty array
        result = json_type.process_result_value("[]", None)
        assert result == []
        assert isinstance(result, list)

        # Empty object
        result = json_type.process_result_value("{}", None)
        assert result == {}
        assert isinstance(result, dict)

    def test_process_result_value_with_invalid_json_string(self):
        """Test that invalid JSON strings raise ValueError."""
        json_type = JSONType()
        invalid_json = "not valid json"

        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value(invalid_json, None)

    def test_process_result_value_with_malformed_json(self):
        """Test various malformed JSON patterns raise ValueError."""
        json_type = JSONType()

        # Unclosed brackets
        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value('{"key": "value"', None)

        # Trailing comma
        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value('["item1", "item2",]', None)

        # Single quotes instead of double
        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value("{'key': 'value'}", None)

    def test_process_result_value_with_nested_json(self):
        """Test deeply nested JSON structures."""
        json_type = JSONType()
        nested_dict = {
            "level1": {
                "level2": {"level3": {"level4": {"value": "deep"}}},
                "array": [1, 2, 3],
            }
        }
        json_string = json.dumps(nested_dict)

        result = json_type.process_result_value(json_string, None)
        assert result == nested_dict
        assert result["level1"]["level2"]["level3"]["level4"]["value"] == "deep"

    def test_process_result_value_with_special_characters(self):
        """Test JSON with special characters and unicode."""
        json_type = JSONType()
        test_dict = {
            "emoji": "🎉",
            "unicode": "Hëllö Wörld",
            "newlines": "line1\nline2",
            "quotes": 'He said "hello"',
        }
        json_string = json.dumps(test_dict)

        result = json_type.process_result_value(json_string, None)
        assert result == test_dict

    def test_process_result_value_with_null_values_in_array(self):
        """Test that null values in arrays are preserved."""
        json_type = JSONType()
        json_string = '["item1", null, "item2", null, "item3"]'
        result = json_type.process_result_value(json_string, None)
        assert result == ["item1", None, "item2", None, "item3"]

    def test_process_result_value_with_mixed_types_in_array(self):
        """Test arrays with mixed types."""
        json_type = JSONType()
        json_string = '["string", 123, true, null, {"nested": "object"}]'
        result = json_type.process_result_value(json_string, None)
        assert result == ["string", 123, True, None, {"nested": "object"}]

    def test_process_result_value_with_boolean_values(self):
        """Test JSON with boolean values."""
        json_type = JSONType()
        json_string = '{"enabled": true, "disabled": false}'
        result = json_type.process_result_value(json_string, None)
        assert result == {"enabled": True, "disabled": False}

    def test_process_result_value_with_numeric_values(self):
        """Test JSON with various numeric types."""
        json_type = JSONType()
        json_string = '{"int": 42, "float": 3.14, "negative": -10, "zero": 0}'
        result = json_type.process_result_value(json_string, None)
        assert result == {"int": 42, "float": 3.14, "negative": -10, "zero": 0}

    def test_process_result_value_with_empty_string(self):
        """Test that empty string is treated as invalid JSON."""
        json_type = JSONType()

        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value("", None)

    def test_process_result_value_with_whitespace_only_string(self):
        """Test that whitespace-only string is treated as invalid JSON."""
        json_type = JSONType()

        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value("   \n\t  ", None)

    def test_process_result_value_with_unexpected_type(self):
        """Test that unexpected types raise TypeError."""
        json_type = JSONType()

        # Integer (unexpected)
        with pytest.raises(TypeError, match="Unexpected type in JSON column"):
            json_type.process_result_value(42, None)

        # Boolean (unexpected)
        with pytest.raises(TypeError, match="Unexpected type in JSON column"):
            json_type.process_result_value(True, None)

    def test_cache_ok_is_true(self):
        """Test that cache_ok flag is set for query caching."""
        json_type = JSONType()
        assert json_type.cache_ok is True

    def test_impl_is_text(self):
        """Test that the implementation type is Text."""
        from sqlalchemy import Text

        # JSONType.impl is the Text class, so we handle serialization ourselves
        assert JSONType.impl == Text


class TestJSONTypeBindParam:
    """Test process_bind_param input validation."""

    def test_process_bind_param_with_none(self):
        """Test that None values are passed through."""
        json_type = JSONType()
        result = json_type.process_bind_param(None, None)
        assert result is None

    def test_process_bind_param_with_dict(self):
        """Test that dict values are serialized to JSON string."""
        json_type = JSONType()
        test_dict = {"key": "value"}
        result = json_type.process_bind_param(test_dict, None)
        assert result == '{"key": "value"}'
        assert isinstance(result, str)

    def test_process_bind_param_with_list(self):
        """Test that list values are serialized to JSON string."""
        json_type = JSONType()
        test_list = ["item1", "item2"]
        result = json_type.process_bind_param(test_list, None)
        assert result == '["item1", "item2"]'
        assert isinstance(result, str)

    def test_process_bind_param_with_invalid_type(self):
        """Test that non-JSON types are converted to empty dict JSON."""
        json_type = JSONType()

        # String (not dict/list)
        result = json_type.process_bind_param("invalid", None)
        assert result == "{}"

        # Integer
        result = json_type.process_bind_param(42, None)
        assert result == "{}"

        # Boolean
        result = json_type.process_bind_param(True, None)
        assert result == "{}"


class TestJSONTypePostgreSQLOptimization:
    """Test PostgreSQL fast-path optimization."""

    def test_postgresql_dict_fast_path(self):
        """Test that PostgreSQL dicts skip deserialization."""
        from unittest.mock import Mock

        json_type = JSONType()
        dialect = Mock()
        dialect.name = "postgresql"

        test_dict = {"key": "value"}
        result = json_type.process_result_value(test_dict, dialect)

        # Should return immediately without processing
        assert result == test_dict
        assert result is test_dict  # Same object reference

    def test_postgresql_list_fast_path(self):
        """Test that PostgreSQL lists skip deserialization."""
        from unittest.mock import Mock

        json_type = JSONType()
        dialect = Mock()
        dialect.name = "postgresql"

        test_list = ["item1", "item2"]
        result = json_type.process_result_value(test_list, dialect)

        # Should return immediately without processing
        assert result == test_list
        assert result is test_list  # Same object reference

    def test_sqlite_requires_deserialization(self):
        """Test that SQLite strings are still deserialized."""
        from unittest.mock import Mock

        json_type = JSONType()
        dialect = Mock()
        dialect.name = "sqlite"

        json_string = '{"key": "value"}'
        result = json_type.process_result_value(json_string, dialect)

        # Should deserialize
        assert result == {"key": "value"}
        assert isinstance(result, dict)


class TestJSONTypeRealWorldScenarios:
    """Test real-world scenarios from the codebase."""

    def test_authorized_domains_scenario(self):
        """Test the exact scenario that caused the bug."""
        json_type = JSONType()

        # SQLite storage (string)
        sqlite_value = '["example.com", "test.com", "company.com"]'
        result = json_type.process_result_value(sqlite_value, None)
        assert result == ["example.com", "test.com", "company.com"]
        assert isinstance(result, list)

        # PostgreSQL storage (native list)
        postgres_value = ["example.com", "test.com", "company.com"]
        result = json_type.process_result_value(postgres_value, None)
        assert result == ["example.com", "test.com", "company.com"]
        assert isinstance(result, list)

    def test_platform_mappings_scenario(self):
        """Test platform_mappings dict scenario."""
        json_type = JSONType()

        # Complex nested structure
        mappings_dict = {
            "google_ad_manager": {
                "enabled": True,
                "advertiser_id": "123456",
                "trafficker_id": "789012",
            },
            "mock": {"enabled": False},
        }

        # SQLite
        sqlite_value = json.dumps(mappings_dict)
        result = json_type.process_result_value(sqlite_value, None)
        assert result == mappings_dict

        # PostgreSQL
        result = json_type.process_result_value(mappings_dict, None)
        assert result == mappings_dict

    def test_empty_list_default_scenario(self):
        """Test empty list default values."""
        json_type = JSONType()

        # Empty list from PostgreSQL
        result = json_type.process_result_value([], None)
        assert result == []

        # Empty list from SQLite
        result = json_type.process_result_value("[]", None)
        assert result == []

    def test_corrupted_data_scenario(self):
        """Test that corrupted database data raises ValueError."""
        json_type = JSONType()

        # Corrupted data raises ValueError
        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value("corrupted data", None)

        # Partial JSON raises ValueError
        with pytest.raises(ValueError, match="Database contains invalid JSON"):
            json_type.process_result_value('["item1", "item2"', None)
