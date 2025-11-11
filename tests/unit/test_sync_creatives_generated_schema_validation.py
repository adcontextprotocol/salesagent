"""Test that validates sync_creatives response against generated schema.

This test would have caught the bug where internal fields (status, review_feedback)
were leaking into the response, violating AdCP's additionalProperties: false constraint.

WHY THIS TEST EXISTS:
- The existing test_adcp_contract.py only checks that required fields exist
- It doesn't validate against the generated schema with "additionalProperties": false
- This test ensures responses match the actual spec that clients use for validation
"""

import pytest
from pydantic import ValidationError

from src.core.schemas import SyncCreativeResult, SyncCreativesResponse
from src.core.schemas_generated._schemas_v1_media_buy_sync_creatives_response_json import (
    Creative as GeneratedCreative,
)
from src.core.schemas_generated._schemas_v1_media_buy_sync_creatives_response_json import (
    SyncCreativesResponse as GeneratedSyncCreativesResponse,
)
from src.core.schemas_generated._schemas_v1_media_buy_sync_creatives_response_json import (
    SyncCreativesResponse1,
)


def test_sync_creatives_response_validates_against_generated_schema():
    """Test that SyncCreativesResponse output validates against generated AdCP schema.

    This test ensures that:
    1. Internal fields (status, review_feedback) are excluded from model_dump()
    2. Empty lists are excluded for cleaner responses
    3. The output validates against the strict generated schema with additionalProperties: false

    This would have caught the bug reported by users:
    - JS client: "agentConfigs is not iterable"
    - Python client: "Data doesn't match any Union variant"
    """
    # Create response with internal fields (as the implementation does)
    result = SyncCreativeResult(
        creative_id="banner_728x90_lb2",
        action="created",
        status="pending_review",  # Internal field - should be excluded
        review_feedback="AI approved",  # Internal field - should be excluded
        platform_id="gam_12345",
        changes=[],  # Empty list - should be excluded
        errors=[],  # Empty list - should be excluded
        warnings=[],  # Empty list - should be excluded
    )

    response = SyncCreativesResponse(
        creatives=[result],
        dry_run=False,
    )

    # Get the dict that would be sent to clients
    response_dict = response.model_dump()

    # Validate each creative against the generated Creative schema
    # This will fail if we have extra fields (additionalProperties: false)
    creative_data = response_dict["creatives"][0]

    try:
        creative_obj = GeneratedCreative(**creative_data)
        assert creative_obj.creative_id == "banner_728x90_lb2"
        assert creative_obj.action.value == "created"
    except ValidationError as e:
        pytest.fail(f"Creative failed validation against generated schema: {e}")

    # Validate the full response against SyncCreativesResponse1 (success variant)
    try:
        response_obj = SyncCreativesResponse1(**response_dict)
        assert len(response_obj.creatives) == 1
    except ValidationError as e:
        pytest.fail(f"Response failed validation against SyncCreativesResponse1: {e}")

    # Validate against the Union wrapper (what clients actually use)
    try:
        union_response = GeneratedSyncCreativesResponse(root=response_obj)
        assert union_response.root is not None
    except ValidationError as e:
        pytest.fail(f"Response failed validation against Union schema: {e}")

    # Verify internal fields were excluded
    assert "status" not in creative_data, "Internal field 'status' should be excluded"
    assert "review_feedback" not in creative_data, "Internal field 'review_feedback' should be excluded"

    # Verify empty lists were excluded
    assert "changes" not in creative_data, "Empty 'changes' list should be excluded"
    assert "errors" not in creative_data, "Empty 'errors' list should be excluded"
    assert "warnings" not in creative_data, "Empty 'warnings' list should be excluded"


def test_sync_creatives_response_with_populated_optional_fields():
    """Test that non-empty optional fields are included and validate."""
    result = SyncCreativeResult(
        creative_id="creative_2",
        action="updated",
        status="approved",  # Internal - should be excluded
        platform_id="gam_67890",
        changes=["name", "assets"],  # Non-empty - should be included
        errors=[],  # Empty - should be excluded
        warnings=["Deprecated field used"],  # Non-empty - should be included
        assigned_to=["pkg_1", "pkg_2"],  # Non-empty - should be included
    )

    response = SyncCreativesResponse(
        creatives=[result],
        dry_run=False,
    )

    response_dict = response.model_dump()
    creative_data = response_dict["creatives"][0]

    # Validate against generated schema
    try:
        creative_obj = GeneratedCreative(**creative_data)
        assert creative_obj.creative_id == "creative_2"
    except ValidationError as e:
        pytest.fail(f"Response with optional fields failed validation: {e}")

    # Verify populated fields are included
    assert "changes" in creative_data, "Non-empty 'changes' should be included"
    assert creative_data["changes"] == ["name", "assets"]
    assert "warnings" in creative_data, "Non-empty 'warnings' should be included"
    assert "assigned_to" in creative_data, "Non-empty 'assigned_to' should be included"

    # Verify empty fields are excluded
    assert "errors" not in creative_data, "Empty 'errors' should be excluded"

    # Verify internal fields are excluded
    assert "status" not in creative_data


def test_sync_creatives_response_failed_creative():
    """Test that failed creatives with errors validate correctly."""
    result = SyncCreativeResult(
        creative_id="creative_3",
        action="failed",
        status="rejected",  # Internal - should be excluded
        errors=["Invalid format", "Missing required asset"],  # Non-empty - should be included
        warnings=["Size exceeds limit"],  # Non-empty - should be included
    )

    response = SyncCreativesResponse(
        creatives=[result],
        dry_run=False,
    )

    response_dict = response.model_dump()
    creative_data = response_dict["creatives"][0]

    # Validate against generated schema
    try:
        creative_obj = GeneratedCreative(**creative_data)
        assert creative_obj.action.value == "failed"
    except ValidationError as e:
        pytest.fail(f"Failed creative response didn't validate: {e}")

    # Verify errors and warnings are included
    assert "errors" in creative_data
    assert len(creative_data["errors"]) == 2
    assert "warnings" in creative_data

    # Verify internal fields are excluded
    assert "status" not in creative_data
    assert "review_feedback" not in creative_data
