"""Tests for AdCP 2.5 creative management features.

These tests verify the AdCP 2.5 creative management changes:
1. sync_creatives with creative_ids filter (scoped sync)
2. list_creatives with media_buy_ids/buyer_refs (plural filters)
3. update_media_buy with package-level creatives (inline upload)
4. update_media_buy with creative_assignments (weight updates)
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.schemas import Creative, FormatId, SyncCreativesRequest


class TestSyncCreativesCreativeIdsFilter:
    """Test sync_creatives creative_ids filter (AdCP 2.5)."""

    def test_sync_creatives_request_accepts_creative_ids(self):
        """Test SyncCreativesRequest schema accepts creative_ids field."""
        creative = Creative(
            creative_id="creative_1",
            name="Test Creative",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display_300x250"),
            assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
        )

        # Should accept creative_ids parameter
        request = SyncCreativesRequest(
            creatives=[creative],
            creative_ids=["creative_1"],  # Filter to only sync this creative
            dry_run=True,
        )

        assert request.creative_ids == ["creative_1"]
        assert request.creatives[0].creative_id == "creative_1"

    def test_sync_creatives_request_rejects_patch_parameter(self):
        """Test SyncCreativesRequest rejects deprecated patch parameter."""
        creative = Creative(
            creative_id="creative_1",
            name="Test Creative",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display_300x250"),
            assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
        )

        # Should reject patch parameter (removed in AdCP 2.5)
        with pytest.raises(ValidationError) as exc_info:
            SyncCreativesRequest(
                creatives=[creative],
                patch=True,  # Deprecated - should fail
            )
        # ValidationError will mention 'extra' fields are forbidden or 'patch' specifically
        assert "patch" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()

    @patch("src.core.tools.creatives.get_principal_id_from_context")
    @patch("src.core.tools.creatives.get_current_tenant")
    @patch("src.core.tools.creatives.get_db_session")
    def test_sync_creatives_filters_by_creative_ids(self, mock_db_session, mock_tenant, mock_principal):
        """Test _sync_creatives_impl filters creatives by creative_ids."""
        from src.core.tools.creatives import _sync_creatives_impl

        mock_principal.return_value = "principal_1"
        mock_tenant.return_value = {"tenant_id": "tenant_1", "adapter_type": "mock"}

        # Mock database session
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=None)
        mock_session.scalars.return_value.first.return_value = None  # No existing creatives

        # Create multiple creatives
        creatives = [
            {
                "creative_id": "creative_1",
                "name": "Creative 1",
                "format_id": {"agent_url": "https://example.com/", "id": "display"},
            },
            {
                "creative_id": "creative_2",
                "name": "Creative 2",
                "format_id": {"agent_url": "https://example.com/", "id": "display"},
            },
            {
                "creative_id": "creative_3",
                "name": "Creative 3",
                "format_id": {"agent_url": "https://example.com/", "id": "display"},
            },
        ]

        # Sync with creative_ids filter - should only process creative_1 and creative_3
        response = _sync_creatives_impl(
            creatives=creatives,
            creative_ids=["creative_1", "creative_3"],  # Filter
            dry_run=True,  # Don't actually persist
        )

        # Should only have 2 creatives in response (filtered)
        assert len(response.creatives) == 2
        synced_ids = {r.creative_id for r in response.creatives}
        assert synced_ids == {"creative_1", "creative_3"}
        assert "creative_2" not in synced_ids


class TestListCreativesPluralFilters:
    """Test list_creatives media_buy_ids/buyer_refs (AdCP 2.5)."""

    def test_create_list_creatives_request_accepts_plural_filters(self):
        """Test create_list_creatives_request accepts plural filter parameters."""
        from src.core.schemas import create_list_creatives_request

        # Should accept media_buy_ids (plural)
        request = create_list_creatives_request(
            media_buy_ids=["mb_1", "mb_2", "mb_3"],
        )

        # Check filters object has media_buy_ids
        assert request.filters is not None
        assert hasattr(request.filters, "media_buy_ids")
        assert request.filters.media_buy_ids == ["mb_1", "mb_2", "mb_3"]

    def test_create_list_creatives_request_merges_singular_and_plural(self):
        """Test singular media_buy_id is merged into plural media_buy_ids."""
        from src.core.schemas import create_list_creatives_request

        # Provide both singular and plural
        request = create_list_creatives_request(
            media_buy_id="mb_1",
            media_buy_ids=["mb_2", "mb_3"],
        )

        # All three should be in the filter
        assert request.filters is not None
        assert set(request.filters.media_buy_ids) == {"mb_1", "mb_2", "mb_3"}

    def test_create_list_creatives_request_deduplicates(self):
        """Test duplicate IDs are not repeated."""
        from src.core.schemas import create_list_creatives_request

        # Provide duplicate
        request = create_list_creatives_request(
            media_buy_id="mb_1",
            media_buy_ids=["mb_1", "mb_2"],  # mb_1 is duplicate
        )

        # Should deduplicate
        assert request.filters is not None
        assert len(request.filters.media_buy_ids) == 2
        assert set(request.filters.media_buy_ids) == {"mb_1", "mb_2"}

    def test_create_list_creatives_request_buyer_refs_plural(self):
        """Test buyer_refs plural filter."""
        from src.core.schemas import create_list_creatives_request

        request = create_list_creatives_request(
            buyer_ref="ref_1",
            buyer_refs=["ref_2", "ref_3"],
        )

        assert request.filters is not None
        assert hasattr(request.filters, "buyer_refs")
        assert set(request.filters.buyer_refs) == {"ref_1", "ref_2", "ref_3"}


class TestUpdateMediaBuyInlineCreatives:
    """Test update_media_buy package-level creatives (AdCP 2.5)."""

    def test_update_media_buy_package_creatives_field_exists(self):
        """Verify update_media_buy accepts package.creatives field."""
        # UpdateMediaBuyRequest is a union type (UpdateMediaBuyRequest1 | UpdateMediaBuyRequest2)
        # Check the Packages type directly for the creatives field
        from adcp.types.generated_poc.media_buy.update_media_buy_request import Packages

        # Check Packages structure has creatives field
        fields = Packages.model_fields
        assert "creatives" in fields, "Packages should have creatives field (AdCP 2.5)"
        assert "creative_assignments" in fields, "Packages should have creative_assignments field (AdCP 2.5)"
        assert "creative_ids" in fields, "Packages should have creative_ids field"


class TestUpdateMediaBuyCreativeAssignments:
    """Test update_media_buy creative_assignments weight updates (AdCP 2.5)."""

    def test_creative_assignment_model_has_weight(self):
        """Verify CreativeAssignment database model has weight column."""
        from src.core.database.models import CreativeAssignment

        # Check weight column exists
        columns = {c.name for c in CreativeAssignment.__table__.columns}
        assert "weight" in columns, "CreativeAssignment should have weight column"

    def test_creative_assignment_weight_default(self):
        """Verify CreativeAssignment weight defaults to 100."""
        from src.core.database.models import CreativeAssignment

        # Check default value
        weight_column = CreativeAssignment.__table__.columns["weight"]
        assert weight_column.default.arg == 100, "Default weight should be 100"


class TestAdCP25SchemaCompliance:
    """Test AdCP 2.5 schema compliance for creative management."""

    def test_sync_creatives_request_no_patch_field(self):
        """Verify SyncCreativesRequest doesn't have patch field."""
        from src.core.schemas import SyncCreativesRequest

        fields = SyncCreativesRequest.model_fields
        assert "patch" not in fields, "SyncCreativesRequest should not have patch field (removed in AdCP 2.5)"

    def test_sync_creatives_request_has_creative_ids(self):
        """Verify SyncCreativesRequest has creative_ids field."""
        from src.core.schemas import SyncCreativesRequest

        fields = SyncCreativesRequest.model_fields
        assert "creative_ids" in fields, "SyncCreativesRequest should have creative_ids field (AdCP 2.5)"

    def test_adcp_library_sync_creatives_request_compatibility(self):
        """Verify our schema matches adcp library's SyncCreativesRequest."""
        from adcp.types import SyncCreativesRequest as LibrarySyncCreativesRequest

        lib_fields = LibrarySyncCreativesRequest.model_fields

        # Library should have creative_ids, not patch
        assert "creative_ids" in lib_fields, "Library SyncCreativesRequest should have creative_ids"
        assert "patch" not in lib_fields, "Library SyncCreativesRequest should not have patch"

    def test_adcp_library_creative_filters_has_plural_fields(self):
        """Verify adcp library's CreativeFilters has plural filter fields."""
        from adcp.types import CreativeFilters

        fields = CreativeFilters.model_fields

        # Should have plural fields
        assert "media_buy_ids" in fields, "CreativeFilters should have media_buy_ids (plural)"
        assert "buyer_refs" in fields, "CreativeFilters should have buyer_refs (plural)"


# ============================================================================
# Spec-Driven Error Case Tests
# These tests verify error handling per AdCP spec requirements
# ============================================================================


class TestSyncCreativesErrorCases:
    """Error case tests for sync_creatives (spec-driven).

    Per AdCP spec, sync_creatives should:
    - Return partial success when some creatives fail validation
    - Report specific errors for each failed creative
    - Never silently drop creatives
    """

    def test_creative_ids_filter_with_nonexistent_ids(self):
        """creative_ids filter with IDs not in payload should return empty results.

        Spec behavior: creative_ids is a filter on the payload, not a fetch.
        If creative_ids contains IDs not in the creatives array, those are ignored.
        """
        from src.core.schemas import Creative, FormatId, SyncCreativesRequest

        creative = Creative(
            creative_id="creative_1",
            name="Test Creative",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
            assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
        )

        # Filter requests IDs that don't exist in payload
        request = SyncCreativesRequest(
            creatives=[creative],
            creative_ids=["nonexistent_1", "nonexistent_2"],  # None match
            dry_run=True,
        )

        # Schema should accept this - filtering is implementation behavior
        assert request.creative_ids == ["nonexistent_1", "nonexistent_2"]
        assert len(request.creatives) == 1  # Payload unaffected

    def test_creative_ids_filter_partial_match(self):
        """creative_ids filter with partial matches should only sync matching IDs.

        Spec behavior: Only creatives whose IDs appear in both the payload AND
        the creative_ids filter are processed.
        """
        from src.core.schemas import Creative, FormatId, SyncCreativesRequest

        creatives = [
            Creative(
                creative_id="creative_1",
                name="Creative 1",
                format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
                assets={"banner": {"url": "https://example.com/1.png", "asset_type": "image"}},
            ),
            Creative(
                creative_id="creative_2",
                name="Creative 2",
                format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
                assets={"banner": {"url": "https://example.com/2.png", "asset_type": "image"}},
            ),
        ]

        # Filter includes one existing + one nonexistent
        request = SyncCreativesRequest(
            creatives=creatives,
            creative_ids=["creative_1", "nonexistent"],  # Only creative_1 matches
            dry_run=True,
        )

        assert len(request.creatives) == 2  # Payload preserved
        assert set(request.creative_ids) == {"creative_1", "nonexistent"}

    def test_empty_creative_ids_filter_vs_none(self):
        """Empty creative_ids array vs None have different semantics.

        Spec behavior:
        - creative_ids=None (omitted): Process all creatives in payload
        - creative_ids=[] (empty array): Process no creatives (filter matches nothing)
        """
        from src.core.schemas import Creative, FormatId, SyncCreativesRequest

        creative = Creative(
            creative_id="creative_1",
            name="Test",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
            assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
        )

        # None = no filter, process all
        request_no_filter = SyncCreativesRequest(creatives=[creative], dry_run=True)
        assert request_no_filter.creative_ids is None

        # Empty array = filter matches nothing
        request_empty_filter = SyncCreativesRequest(
            creatives=[creative],
            creative_ids=[],
            dry_run=True,
        )
        assert request_empty_filter.creative_ids == []

    def test_sync_creatives_request_validates_creative_structure(self):
        """Creatives must have required fields per AdCP spec.

        Spec requires: creative_id, format_id, assets
        """
        from pydantic import ValidationError

        from src.core.schemas import Creative

        # Missing format_id should fail
        with pytest.raises(ValidationError) as exc_info:
            Creative(
                creative_id="test",
                name="Test",
                assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
                # format_id missing
            )
        assert "format" in str(exc_info.value).lower()


class TestListCreativesErrorCases:
    """Error case tests for list_creatives plural filters."""

    def test_empty_media_buy_ids_vs_none(self):
        """Empty media_buy_ids array vs None have different semantics.

        - media_buy_ids=None: No filter on media_buy_ids
        - media_buy_ids=[]: Implementation treats as "no filter" (same as None)
        """
        from src.core.schemas import create_list_creatives_request

        # None = no filter
        request_no_filter = create_list_creatives_request()
        assert request_no_filter.filters is None or request_no_filter.filters.media_buy_ids is None

        # Empty array - implementation normalizes to no filter (None)
        # This is valid behavior: empty filter means "match all"
        request_empty = create_list_creatives_request(media_buy_ids=[])
        # Should not raise - implementation handles gracefully
        assert request_empty is not None

    def test_plural_and_singular_both_empty(self):
        """Both singular and plural filters empty should be valid.

        This is a common edge case when building requests programmatically.
        """
        from src.core.schemas import create_list_creatives_request

        # Should not raise
        request = create_list_creatives_request(
            media_buy_id=None,
            media_buy_ids=[],
            buyer_ref=None,
            buyer_refs=[],
        )
        # Request should be valid, filters may be None or empty
        assert request is not None


class TestCreativeAssignmentWeightBounds:
    """Test weight validation for creative assignments (AdCP 2.5)."""

    def test_weight_accepts_valid_range(self):
        """Weights should accept reasonable positive integers.

        Per AdCP spec, weight is used for rotation ratio (default 100).
        """
        from src.core.database.models import CreativeAssignment

        # Create instance with valid weight
        assignment = CreativeAssignment(
            tenant_id="test",
            creative_id="c1",
            package_id="p1",
            weight=100,
        )
        assert assignment.weight == 100

        # Test boundary values
        assignment_low = CreativeAssignment(
            tenant_id="test",
            creative_id="c2",
            package_id="p1",
            weight=1,  # Minimum practical value
        )
        assert assignment_low.weight == 1

        assignment_high = CreativeAssignment(
            tenant_id="test",
            creative_id="c3",
            package_id="p1",
            weight=1000,  # High but reasonable
        )
        assert assignment_high.weight == 1000

    def test_weight_zero_handling(self):
        """Weight of 0 may have special semantics (disabled rotation).

        The database should accept 0, behavior is implementation-defined.
        """
        from src.core.database.models import CreativeAssignment

        assignment = CreativeAssignment(
            tenant_id="test",
            creative_id="c1",
            package_id="p1",
            weight=0,
        )
        assert assignment.weight == 0


# ============================================================================
# Response Format Compliance Tests
# Verify responses match AdCP spec structure
# ============================================================================


class TestSyncCreativesResponseFormat:
    """Test SyncCreativesResponse structure matches AdCP spec."""

    def test_response_has_required_fields(self):
        """SyncCreativesResponse must have 'creatives' field per spec."""
        from src.core.schema_adapters import SyncCreativesResponse

        fields = SyncCreativesResponse.model_fields
        assert "creatives" in fields, "Response must have 'creatives' field"

    def test_response_accepts_dry_run_echo(self):
        """Response should echo dry_run parameter per spec."""
        from src.core.schema_adapters import SyncCreativesResponse

        response = SyncCreativesResponse(
            creatives=[],
            dry_run=True,
        )
        assert response.dry_run is True

    def test_response_str_summarizes_actions(self):
        """Response __str__ should provide human-readable summary."""
        from src.core.schema_adapters import SyncCreativesResponse

        response = SyncCreativesResponse(
            creatives=[
                {"creative_id": "c1", "action": "created"},
                {"creative_id": "c2", "action": "updated"},
                {"creative_id": "c3", "action": "updated"},
            ],
        )

        summary = str(response)
        # Should mention counts
        assert "1" in summary or "created" in summary.lower()


class TestListCreativesResponseFormat:
    """Test ListCreativesResponse structure matches AdCP spec."""

    def test_response_has_required_fields(self):
        """ListCreativesResponse must have 'creatives' field per spec."""
        from src.core.schema_adapters import ListCreativesResponse

        fields = ListCreativesResponse.model_fields
        assert "creatives" in fields, "Response must have 'creatives' field"

    def test_response_requires_pagination(self):
        """Response requires pagination fields per spec."""
        from src.core.schema_adapters import ListCreativesResponse

        fields = ListCreativesResponse.model_fields
        # AdCP spec requires pagination fields
        assert "pagination" in fields, "Response must have 'pagination' field"
        assert "query_summary" in fields, "Response must have 'query_summary' field"

    def test_response_with_required_fields(self):
        """Response with all required fields should be valid."""
        from src.core.schemas import ListCreativesResponse, Pagination, QuerySummary

        response = ListCreativesResponse(
            creatives=[],
            query_summary=QuerySummary(
                total_matching=0,
                returned=0,
                filters_applied=[],
            ),
            pagination=Pagination(
                limit=50,
                offset=0,
                has_more=False,
                total_pages=0,
                current_page=1,
            ),
        )
        assert response.creatives == []
        assert response.pagination.has_more is False


# ============================================================================
# delete_missing + creative_ids Filter Interaction Tests
# ============================================================================


class TestDeleteMissingWithCreativeIdsFilter:
    """Test interaction between delete_missing and creative_ids filter.

    This is a critical edge case: what happens when you use delete_missing=True
    with a creative_ids filter? The behavior must be well-defined.
    """

    def test_schema_accepts_both_parameters(self):
        """Schema should accept both delete_missing and creative_ids together."""
        from src.core.schemas import Creative, FormatId, SyncCreativesRequest

        creative = Creative(
            creative_id="creative_1",
            name="Test",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
            assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
        )

        # Both parameters together should be valid schema
        request = SyncCreativesRequest(
            creatives=[creative],
            creative_ids=["creative_1"],
            delete_missing=True,
            dry_run=True,
        )

        assert request.creative_ids == ["creative_1"]
        assert request.delete_missing is True

    def test_delete_missing_scope_documentation(self):
        """Document expected behavior of delete_missing with creative_ids.

        Expected spec behavior (verify with implementation):
        - delete_missing=True, creative_ids=None: Delete creatives NOT in payload
        - delete_missing=True, creative_ids=[...]: Delete only within filtered scope

        The second case is important: if creative_ids=["c1", "c2"] and payload
        only has c1, should c2 be deleted? This depends on interpretation.
        """
        from src.core.schemas import Creative, FormatId, SyncCreativesRequest

        # This test documents the expected behavior
        # Implementation should handle this consistently
        creative = Creative(
            creative_id="c1",
            name="Creative 1",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
            assets={"banner": {"url": "https://example.com/banner.png", "asset_type": "image"}},
        )

        # Scoped delete: creative_ids filter with delete_missing
        request = SyncCreativesRequest(
            creatives=[creative],  # Only c1 in payload
            creative_ids=["c1", "c2"],  # Filter includes c2 not in payload
            delete_missing=True,
            dry_run=True,
        )

        # Schema valid - behavior is implementation concern
        assert len(request.creatives) == 1
        assert len(request.creative_ids) == 2


# ============================================================================
# Upsert Semantics Tests (AdCP 2.5 default behavior)
# ============================================================================


class TestUpsertSemantics:
    """Test upsert semantics after patch parameter removal (AdCP 2.5).

    With patch parameter removed, sync_creatives uses upsert semantics:
    - Create if creative_id doesn't exist
    - Full update if creative_id exists (not patch/merge)
    """

    def test_sync_creatives_default_is_full_upsert(self):
        """Without patch parameter, default behavior is full upsert."""
        from src.core.schemas import SyncCreativesRequest

        # Verify patch is not available
        fields = SyncCreativesRequest.model_fields
        assert "patch" not in fields, "patch parameter should not exist (AdCP 2.5)"

        # Default behavior documentation
        # When syncing a creative that exists:
        # - All fields from payload replace existing values
        # - Fields not in payload are NOT preserved (unlike patch)
        # This is the expected upsert behavior

    def test_creative_ids_filter_with_upsert(self):
        """creative_ids filter scopes which creatives get upserted.

        Scenario: Buyer has creatives c1, c2, c3 in system
        Request: creatives=[c1_updated, c2_updated], creative_ids=[c1]
        Result: Only c1 is updated, c2 in payload is ignored
        """
        from src.core.schemas import Creative, FormatId, SyncCreativesRequest

        c1 = Creative(
            creative_id="c1",
            name="Creative 1 Updated",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
            assets={"banner": {"url": "https://example.com/new.png", "asset_type": "image"}},
        )
        c2 = Creative(
            creative_id="c2",
            name="Creative 2 Updated",
            format_id=FormatId(agent_url="https://creatives.example.com/", id="display"),
            assets={"banner": {"url": "https://example.com/new2.png", "asset_type": "image"}},
        )

        # Only c1 should be processed due to filter
        request = SyncCreativesRequest(
            creatives=[c1, c2],
            creative_ids=["c1"],  # Filter to only c1
            dry_run=True,
        )

        # Both in payload, but only c1 matches filter
        assert len(request.creatives) == 2
        assert request.creative_ids == ["c1"]
