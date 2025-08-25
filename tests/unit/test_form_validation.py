"""Test form validation utilities."""

import pytest

from src.core.validation import validate_form_data


class TestValidateFormData:
    """Test the validate_form_data function."""

    def test_list_based_validation_all_present(self):
        """Test validation with list of required fields - all present."""
        data = {"name": "Test User", "email": "test@example.com"}
        is_valid, errors = validate_form_data(data, ["name", "email"])
        
        assert is_valid is True
        assert errors == []

    def test_list_based_validation_missing_field(self):
        """Test validation with list of required fields - one missing."""
        data = {"name": "Test User"}
        is_valid, errors = validate_form_data(data, ["name", "email"])
        
        assert is_valid is False
        assert len(errors) == 1
        assert "Email is required" in errors

    def test_list_based_validation_empty_field(self):
        """Test validation with empty string treated as missing."""
        data = {"name": "Test User", "email": "   "}
        is_valid, errors = validate_form_data(data, ["name", "email"])
        
        assert is_valid is False
        assert len(errors) == 1
        assert "Email is required" in errors

    def test_dict_based_validation_with_validators(self):
        """Test validation with dictionary of validator functions."""
        def validate_email(value):
            if "@" not in value:
                return "Invalid email format"
            return None

        validators = {
            "email": [validate_email]
        }
        
        # Valid email
        data = {"email": "test@example.com"}
        is_valid, errors = validate_form_data(data, validators)
        assert is_valid is True
        assert errors == []
        
        # Invalid email
        data = {"email": "notanemail"}
        is_valid, errors = validate_form_data(data, validators)
        assert is_valid is False
        assert len(errors) == 1
        assert "Email: Invalid email format" in errors

    def test_empty_validation(self):
        """Test with empty validators."""
        data = {"any": "data"}
        
        # Empty list
        is_valid, errors = validate_form_data(data, [])
        assert is_valid is True
        assert errors == []
        
        # Empty dict
        is_valid, errors = validate_form_data(data, {})
        assert is_valid is True
        assert errors == []