"""Comprehensive A2A response validation framework.

This module provides utilities for validating A2A responses to catch
AttributeError bugs, missing fields, and protocol violations.

Usage:
    from tests.helpers.a2a_response_validator import A2AResponseValidator

    validator = A2AResponseValidator()
    validator.validate_skill_response(response_dict, "create_media_buy")
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]

    def __bool__(self) -> bool:
        """Allow boolean checks: if validation_result: ..."""
        return self.is_valid


class A2AResponseValidator:
    """Validator for A2A skill responses.

    This validator ensures that A2A responses:
    1. Have all required fields
    2. Message fields are properly formatted
    3. No AttributeErrors occurred during construction
    4. Conform to A2A protocol expectations
    """

    # PROTOCOL FIELDS MUST NOT BE IN DATA
    # Per AdCP spec and PR #238, DataPart.data must contain ONLY AdCP-compliant payload
    # "success" and "message" are protocol concerns, not domain data
    FORBIDDEN_FIELDS = {"success", "message"}

    # Optional common fields (not required but expected in many responses)
    COMMON_OPTIONAL_FIELDS = {
        "status",
        "data",
        "error",
        "warning",
        "metadata",
    }

    # Skill-specific required fields (AdCP spec fields only - domain data)
    # Per AdCP spec, these are the fields that MUST be present in the response
    SKILL_REQUIRED_FIELDS = {
        "create_media_buy": set(),  # media_buy_id is optional per schema
        "sync_creatives": {"creatives"},  # Per AdCP spec
        "get_products": {"products"},  # Per AdCP spec
        "list_creatives": {"creatives"},  # Per AdCP spec (query_summary/pagination may be optional)
        "list_creative_formats": {"formats"},  # Per AdCP spec
        "get_signals": {"signals"},  # Per AdCP spec
        "update_media_buy": set(),  # Per AdCP spec, all fields optional in response
        "get_media_buy_delivery": set(),  # Per AdCP spec
        "update_performance_index": set(),  # Per AdCP spec
    }

    def validate_skill_response(self, response: dict[str, Any], skill_name: str | None = None) -> ValidationResult:
        """Validate an A2A skill response for AdCP spec compliance.

        Per AdCP spec and PR #238:
        - DataPart.data MUST contain ONLY AdCP-compliant payload
        - NO protocol fields ("success", "message") in the data
        - Success determined by Task.status.state (completed/failed)
        - Human messages go in Artifact.description or TextPart

        Args:
            response: The response dict returned by _handle_*_skill method
            skill_name: Name of the skill (e.g., "create_media_buy")

        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []

        # 1. Check for FORBIDDEN protocol fields (spec violation)
        for field in self.FORBIDDEN_FIELDS:
            if field in response:
                errors.append(
                    f"Protocol field '{field}' found in response data - violates AdCP spec. "
                    f"Protocol concerns must be in Task.status or Artifact.description, not data."
                )

        # 2. Check skill-specific required fields (AdCP spec fields)
        if skill_name and skill_name in self.SKILL_REQUIRED_FIELDS:
            required = self.SKILL_REQUIRED_FIELDS[skill_name]
            for field in required:
                if field not in response:
                    errors.append(f"Missing required AdCP field for {skill_name}: {field}")

        # 3. Validate that response is a valid dict
        if not isinstance(response, dict):
            errors.append(f"Response must be a dict, got {type(response).__name__}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_adcp_schema_compliance(self, response: dict[str, Any], expected_schema: type) -> ValidationResult:
        """Validate that a response matches AdCP schema expectations.

        Args:
            response: The response dict
            expected_schema: Expected Pydantic model class (e.g., CreateMediaBuyResponse)

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        try:
            # Try to instantiate the schema with the response data
            expected_schema(**response)
        except Exception as e:
            errors.append(f"Response does not match AdCP schema {expected_schema.__name__}: {str(e)}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def check_response_type_safety(self, response_class: type) -> ValidationResult:
        """Check if a response type is AdCP-compliant.

        Per AdCP spec and PR #238:
        - Response must be a Pydantic model with AdCP-defined fields
        - Must NOT have "success" or "message" fields (protocol concerns)
        - Should have model_dump() method for serialization

        Args:
            response_class: Response class to check (e.g., CreateMediaBuyResponse)

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        class_name = response_class.__name__

        # Check for model_dump method (Pydantic requirement)
        if not hasattr(response_class, "model_dump"):
            errors.append(
                f"{class_name} missing model_dump() method. " f"Must be a Pydantic model for AdCP compliance."
            )

        # Check for forbidden protocol fields
        if hasattr(response_class, "model_fields"):
            if "success" in response_class.model_fields:
                errors.append(
                    f"{class_name} has 'success' field - violates AdCP spec. "
                    f"Success is protocol-level (Task.status.state), not domain data."
                )
            if "message" in response_class.model_fields:
                errors.append(
                    f"{class_name} has 'message' field - violates AdCP spec. "
                    f"Messages belong in Artifact.description or TextPart, not domain data."
                )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_artifact_structure(self, artifact: Any) -> ValidationResult:
        """Validate an A2A artifact structure.

        Args:
            artifact: Artifact object from A2A response

        Returns:
            ValidationResult
        """
        errors = []
        warnings = []

        # Check required artifact fields
        if not hasattr(artifact, "artifactId"):
            errors.append("Artifact missing required field: artifactId")
        if not hasattr(artifact, "name"):
            errors.append("Artifact missing required field: name")
        if not hasattr(artifact, "parts"):
            errors.append("Artifact missing required field: parts")

        # Check parts structure
        if hasattr(artifact, "parts"):
            if not isinstance(artifact.parts, list):
                errors.append(f"Artifact parts must be a list, got {type(artifact.parts).__name__}")
            elif len(artifact.parts) == 0:
                warnings.append("Artifact has no parts")
            else:
                for i, part in enumerate(artifact.parts):
                    if not hasattr(part, "type"):
                        errors.append(f"Artifact part {i} missing type field")
                    if not hasattr(part, "data"):
                        errors.append(f"Artifact part {i} missing data field")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


# Global validator instance for convenience
validator = A2AResponseValidator()


def validate_skill_response(response: dict[str, Any], skill_name: str | None = None) -> ValidationResult:
    """Convenience function for validating skill responses."""
    return validator.validate_skill_response(response, skill_name)


def assert_valid_skill_response(response: dict[str, Any], skill_name: str | None = None):
    """Assert that a skill response is valid, raising AssertionError if not."""
    result = validate_skill_response(response, skill_name)

    if not result.is_valid:
        error_msg = f"Invalid A2A skill response for {skill_name or 'unknown skill'}:\n"
        error_msg += "\n".join(f"  - {error}" for error in result.errors)
        if result.warnings:
            error_msg += "\n\nWarnings:\n"
            error_msg += "\n".join(f"  - {warning}" for warning in result.warnings)
        raise AssertionError(error_msg)

    return result
