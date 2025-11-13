"""Test that ListCreativesResponse properly excludes internal fields from nested Creative objects.

This test ensures that Creative's custom model_dump() is called when serializing
ListCreativesResponse, preventing internal fields from leaking to clients.

Related:
- Original bug: SyncCreativesResponse (f5bd7b8a)
- Systematic fix: ListCreativesResponse nested serialization
- Pattern: All response models with nested Pydantic models need explicit serialization
"""

from datetime import UTC, datetime

from src.core.schemas import Creative, ListCreativesResponse, Pagination, QuerySummary


def test_list_creatives_response_excludes_internal_fields_from_nested_creatives():
    """Test that ListCreativesResponse excludes Creative internal fields.

    Creative has 4 internal fields that should NOT appear in responses:
    - principal_id: Internal advertiser association
    - created_at: Internal audit timestamp
    - updated_at: Internal audit timestamp
    - status: Internal workflow state

    Creative.model_dump() excludes these, but ListCreativesResponse must
    explicitly call it for nested creatives.
    """
    # Create Creative with internal fields populated
    creative = Creative(
        creative_id="test_123",
        name="Test Banner",
        format={"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
        assets={"banner": {"asset_type": "image", "url": "https://example.com/banner.jpg"}},
        # Internal fields - should be excluded from response
        principal_id="principal_456",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        status="approved",
    )

    # Create response with the creative
    response = ListCreativesResponse(
        creatives=[creative],
        query_summary=QuerySummary(total_matching=1, returned=1, filters_applied=["format: display_300x250"]),
        pagination=Pagination(limit=50, offset=0, has_more=False),
    )

    # Dump to dict (what clients receive)
    result = response.model_dump()

    # Verify internal fields are excluded from nested creative
    creative_in_response = result["creatives"][0]

    assert "principal_id" not in creative_in_response, "Internal field 'principal_id' should be excluded"
    assert "created_at" not in creative_in_response, "Internal field 'created_at' should be excluded"
    assert "updated_at" not in creative_in_response, "Internal field 'updated_at' should be excluded"
    assert "status" not in creative_in_response, "Internal field 'status' should be excluded"

    # Verify required AdCP fields are present
    assert "creative_id" in creative_in_response
    assert creative_in_response["creative_id"] == "test_123"
    assert "name" in creative_in_response
    assert "format" in creative_in_response
    assert "assets" in creative_in_response


def test_list_creatives_response_with_multiple_creatives():
    """Test that internal fields are excluded from all creatives in the list."""
    # Create multiple creatives with internal fields
    creatives = [
        Creative(
            creative_id=f"creative_{i}",
            name=f"Test Creative {i}",
            format={"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
            assets={"banner": {"asset_type": "image", "url": f"https://example.com/banner{i}.jpg"}},
            principal_id=f"principal_{i}",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="approved" if i % 2 == 0 else "pending",
        )
        for i in range(3)
    ]

    response = ListCreativesResponse(
        creatives=creatives,
        query_summary=QuerySummary(total_matching=3, returned=3, filters_applied=[]),
        pagination=Pagination(limit=50, offset=0, has_more=False),
    )

    result = response.model_dump()

    # Verify internal fields excluded from all creatives
    for i, creative_data in enumerate(result["creatives"]):
        assert "principal_id" not in creative_data, f"Creative {i}: principal_id should be excluded"
        assert "created_at" not in creative_data, f"Creative {i}: created_at should be excluded"
        assert "updated_at" not in creative_data, f"Creative {i}: updated_at should be excluded"
        assert "status" not in creative_data, f"Creative {i}: status should be excluded"

        # Verify required fields present
        assert creative_data["creative_id"] == f"creative_{i}"


def test_list_creatives_response_with_optional_fields():
    """Test that optional AdCP fields (tags, inputs, approved) are included when present."""
    creative = Creative(
        creative_id="test_with_optional",
        name="Test Creative",
        format={"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
        assets={"banner": {"asset_type": "image", "url": "https://example.com/banner.jpg"}},
        tags=["sports", "premium"],  # Optional AdCP field
        approved=True,  # Optional AdCP field for generative creatives
        # Internal fields
        principal_id="principal_123",
        status="approved",
    )

    response = ListCreativesResponse(
        creatives=[creative],
        query_summary=QuerySummary(total_matching=1, returned=1, filters_applied=[]),
        pagination=Pagination(limit=50, offset=0, has_more=False),
    )

    result = response.model_dump()
    creative_data = result["creatives"][0]

    # Optional AdCP fields should be included
    assert "tags" in creative_data
    assert creative_data["tags"] == ["sports", "premium"]
    assert "approved" in creative_data
    assert creative_data["approved"] is True

    # Internal fields still excluded
    assert "principal_id" not in creative_data
    assert "status" not in creative_data
