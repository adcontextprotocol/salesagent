"""Test A2A response attribute access patterns.

Ensures A2A handlers access response attributes correctly per AdCP schema.
Prevents AttributeError bugs like the list_creatives total_count issue.
"""

import pytest

from src.core.schemas import (
    GetProductsResponse,
    ListAuthorizedPropertiesResponse,
    ListCreativeFormatsResponse,
    ListCreativesResponse,
    Pagination,
    QuerySummary,
)


class TestA2AResponseAttributeAccess:
    """Test that A2A handlers access response attributes correctly."""

    def test_list_creatives_response_attribute_access(self):
        """Verify A2A handler accesses ListCreativesResponse attributes correctly.

        This test prevents regression of the bug where A2A handler tried to access:
        - response.total_count (doesn't exist)
        - response.page (doesn't exist)
        - response.limit (doesn't exist)
        - response.has_more (doesn't exist)

        Instead it should access:
        - response.query_summary.total_matching
        - response.pagination.current_page
        - response.pagination.limit
        - response.pagination.has_more
        """
        # Create a minimal ListCreativesResponse
        response = ListCreativesResponse(
            query_summary=QuerySummary(total_matching=10, returned=2, filters_applied=[], sort_applied=None),
            pagination=Pagination(limit=50, offset=0, has_more=True, total_pages=1, current_page=1),
            creatives=[],
        )

        # Verify correct attribute paths exist
        assert response.query_summary.total_matching == 10
        assert response.pagination.current_page == 1
        assert response.pagination.limit == 50
        assert response.pagination.has_more is True

        # Verify incorrect attribute paths don't exist (would cause AttributeError)
        with pytest.raises(AttributeError):
            _ = response.total_count

        with pytest.raises(AttributeError):
            _ = response.page

        with pytest.raises(AttributeError):
            _ = response.limit  # Not on response, only on pagination

        with pytest.raises(AttributeError):
            _ = response.has_more  # Not on response, only on pagination

    def test_get_products_response_attribute_access(self):
        """Verify GetProductsResponse has expected flat structure."""
        response = GetProductsResponse(products=[])

        # Verify expected attributes exist
        assert hasattr(response, "products")
        assert isinstance(response.products, list)

    def test_list_creative_formats_response_attribute_access(self):
        """Verify ListCreativeFormatsResponse has expected flat structure."""
        response = ListCreativeFormatsResponse(formats=[])

        # Verify expected attributes exist
        assert hasattr(response, "formats")
        assert isinstance(response.formats, list)

    def test_list_authorized_properties_response_attribute_access(self):
        """Verify ListAuthorizedPropertiesResponse has expected flat structure."""
        response = ListAuthorizedPropertiesResponse(properties=[], tags={})

        # Verify expected attributes exist
        assert hasattr(response, "properties")
        assert hasattr(response, "tags")
        assert isinstance(response.properties, list)
        assert isinstance(response.tags, dict)

    def test_a2a_list_creatives_handler_attribute_extraction(self):
        """Verify A2A handler can extract attributes correctly from response.

        This simulates what the A2A handler does with the response.
        Tests the FIXED version that accesses nested attributes correctly.
        """
        # Create minimal response
        response = ListCreativesResponse(
            query_summary=QuerySummary(total_matching=5, returned=0, filters_applied=[], sort_applied=None),
            pagination=Pagination(limit=50, offset=0, has_more=False, total_pages=1, current_page=1),
            creatives=[],
        )

        # Simulate what A2A handler does (the fixed version)
        creatives_list = [creative.model_dump() for creative in response.creatives]
        total_count = response.query_summary.total_matching  # ✅ Correct
        page = response.pagination.current_page  # ✅ Correct
        limit = response.pagination.limit  # ✅ Correct
        has_more = response.pagination.has_more  # ✅ Correct

        # Verify extraction worked
        assert creatives_list == []
        assert total_count == 5
        assert page == 1
        assert limit == 50
        assert has_more is False

        # Build A2A response format (what the handler returns)
        a2a_response = {
            "success": True,
            "creatives": creatives_list,
            "total_count": total_count,
            "page": page,
            "limit": limit,
            "has_more": has_more,
            "message": str(response),
        }

        # Verify A2A response has expected structure
        assert a2a_response["success"] is True
        assert a2a_response["total_count"] == 5
        assert a2a_response["page"] == 1
        assert a2a_response["limit"] == 50
        assert a2a_response["has_more"] is False
