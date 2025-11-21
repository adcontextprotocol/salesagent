"""Integration tests for A2A ADK PR #238 alignment.

This test suite validates that our A2A implementation aligns with the
ADK PR #238 specification for A2A response structure.

Reference: https://github.com/adcontextprotocol/adcp/pull/238

Key requirements validated:
1. Responses MUST include at least one DataPart
2. Responses MAY include TextPart for human-readable messages
3. Last DataPart is authoritative when multiple exist
4. TextPart + DataPart is the recommended pattern
"""

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.mark.integration
class TestADKResponseStructure:
    """Test that artifacts follow ADK PR #238 response structure."""

    def test_artifact_has_required_datapart(self):
        """Test that artifacts always include at least one DataPart."""
        handler = AdCPRequestHandler()

        # Test data
        data = {"products": [], "errors": None}
        description = "Test description"

        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test_1",
            name="test_result",
            data=data,
            description=description,
        )

        # Validate structure
        assert artifact is not None
        assert hasattr(artifact, "parts")
        assert len(artifact.parts) >= 1

        # At least one part must be DataPart
        data_parts = [p for p in artifact.parts if hasattr(p, "root") and hasattr(p.root, "data")]
        assert len(data_parts) >= 1, "Artifact must contain at least one DataPart"

        # Validate DataPart contains correct data
        last_data_part = data_parts[-1]  # Last DataPart is authoritative
        assert last_data_part.root.data == data

    def test_artifact_includes_textpart_when_description_provided(self):
        """Test that TextPart is included when human-readable description is provided."""
        handler = AdCPRequestHandler()

        data = {"test": "data"}
        description = "This is a human-readable message"

        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test_1",
            name="test_result",
            data=data,
            description=description,
        )

        # Should have both TextPart and DataPart
        assert len(artifact.parts) == 2

        # First part should be TextPart with description
        text_part = artifact.parts[0]
        assert hasattr(text_part, "root")
        assert hasattr(text_part.root, "text")
        assert text_part.root.text == description

        # Second part should be DataPart with data
        data_part = artifact.parts[1]
        assert hasattr(data_part, "root")
        assert hasattr(data_part.root, "data")
        assert data_part.root.data == data

    def test_artifact_omits_textpart_when_no_description(self):
        """Test that TextPart is optional - omitted when no description provided."""
        handler = AdCPRequestHandler()

        data = {"test": "data"}

        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test_1",
            name="test_result",
            data=data,
            description=None,  # No description
        )

        # Should have only DataPart
        assert len(artifact.parts) == 1

        # Single part should be DataPart
        data_part = artifact.parts[0]
        assert hasattr(data_part, "root")
        assert hasattr(data_part.root, "data")
        assert data_part.root.data == data

    def test_last_datapart_convention(self):
        """Test that last DataPart is authoritative (ADK convention)."""
        handler = AdCPRequestHandler()

        # Create artifact with description (TextPart + DataPart)
        data = {"final": "data"}
        description = "Human message"

        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test_1",
            name="test_result",
            data=data,
            description=description,
        )

        # Extract all DataParts
        data_parts = [p for p in artifact.parts if hasattr(p, "root") and hasattr(p.root, "data")]

        assert len(data_parts) == 1
        # Last (and only) DataPart should contain the data
        assert data_parts[-1].root.data == data


@pytest.mark.integration
class TestADKPatternCompliance:
    """Test compliance with ADK recommended patterns."""

    def test_recommended_pattern_textpart_plus_datapart(self):
        """Test that we follow the recommended TextPart + DataPart pattern."""
        handler = AdCPRequestHandler()

        # This is the ADK-recommended pattern
        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="result_1",
            name="product_catalog",
            data={"products": [{"id": "prod1", "name": "Banner"}]},
            description="Found 1 product matching your requirements.",
        )

        # Verify recommended structure
        assert len(artifact.parts) == 2

        # Part 1: TextPart (human-readable)
        assert hasattr(artifact.parts[0].root, "text")
        assert "Found 1 product" in artifact.parts[0].root.text

        # Part 2: DataPart (structured)
        assert hasattr(artifact.parts[1].root, "data")
        assert "products" in artifact.parts[1].root.data

    def test_backwards_compatibility_description_field(self):
        """Test that description field is still populated for backwards compatibility."""
        handler = AdCPRequestHandler()

        description = "Human-readable message"
        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test_1",
            name="test_result",
            data={"test": "data"},
            description=description,
        )

        # Description field should still be set for backwards compatibility
        assert artifact.description == description

    def test_artifact_parts_order_textpart_before_datapart(self):
        """Test that TextPart comes before DataPart (ADK pattern)."""
        handler = AdCPRequestHandler()

        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test_1",
            name="test_result",
            data={"test": "data"},
            description="Human message",
        )

        # Verify order: TextPart first, then DataPart
        assert hasattr(artifact.parts[0].root, "text"), "First part should be TextPart"
        assert hasattr(artifact.parts[1].root, "data"), "Second part should be DataPart"


@pytest.mark.integration
class TestADKMandatoryCompliance:
    """Test mandatory ADK requirements."""

    def test_all_artifacts_have_at_least_one_datapart(self):
        """MANDATORY: All artifacts must have at least one DataPart."""
        handler = AdCPRequestHandler()

        test_cases = [
            {"data": {"test": "1"}, "description": "With description"},
            {"data": {"test": "2"}, "description": None},  # No description
        ]

        for case in test_cases:
            artifact = handler._create_artifact_with_text_and_data(
                artifact_id="test",
                name="test",
                data=case["data"],
                description=case["description"],
            )

            # MANDATORY: Must have at least one DataPart
            data_parts = [p for p in artifact.parts if hasattr(p, "root") and hasattr(p.root, "data")]
            assert len(data_parts) >= 1, "Artifact MUST have at least one DataPart"

    def test_textpart_is_optional(self):
        """OPTIONAL: TextPart is optional per ADK spec."""
        handler = AdCPRequestHandler()

        # Create artifact without description
        artifact = handler._create_artifact_with_text_and_data(
            artifact_id="test",
            name="test",
            data={"test": "data"},
            description=None,  # No TextPart
        )

        # Should still be valid with just DataPart
        assert len(artifact.parts) == 1
        text_parts = [p for p in artifact.parts if hasattr(p, "root") and hasattr(p.root, "text")]
        assert len(text_parts) == 0, "TextPart should be omitted when description is None"
