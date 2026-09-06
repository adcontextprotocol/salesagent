#!/usr/bin/env python3
"""
Unit tests for A2A auth-optional discovery endpoints.

Tests that discovery endpoints (list_creative_formats, list_authorized_properties, get_products)
properly handle both authenticated and unauthenticated requests according to AdCP spec.

After the identity-at-transport-boundary refactor , handlers receive
a pre-resolved identity parameter rather than resolving auth internally.
"""

import pytest
from a2a.types import InvalidRequestError

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from tests.factories.principal import PrincipalFactory
from tests.helpers.capture_wrapper_req import stub_impl


class TestAuthOptionalSkills:
    """Test auth-optional skill handling in A2A server."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = AdCPRequestHandler()
        self.mock_identity = PrincipalFactory.make_identity(
            principal_id="test_principal", tenant_id="default", tenant={"tenant_id": "default"}, protocol="a2a"
        )
        self.anon_identity = PrincipalFactory.make_identity(
            principal_id=None, tenant_id="default", tenant={"tenant_id": "default"}, protocol="a2a"
        )

    @pytest.mark.asyncio
    async def test_list_creative_formats_without_auth(self):
        """list_creative_formats should work with anonymous identity (no principal)."""
        with stub_impl("list_creative_formats") as mock_tool:
            mock_tool.return_value = {"formats": []}

            result = await self.handler._dispatch_skill("list_creative_formats", {}, self.anon_identity)

            assert result is not None
            assert "formats" in result
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_creative_formats_with_auth(self):
        """list_creative_formats should work with authenticated identity."""
        with stub_impl("list_creative_formats") as mock_tool:
            mock_tool.return_value = {"formats": []}

            result = await self.handler._dispatch_skill("list_creative_formats", {}, self.mock_identity)

            assert result is not None
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_products_without_auth(self):
        """get_products should work with anonymous identity."""
        with stub_impl("get_products") as mock_tool:
            mock_tool.return_value = {"products": []}

            result = await self.handler._dispatch_skill("get_products", {"brief": "test campaign"}, self.anon_identity)

            assert result is not None
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_products_with_auth(self):
        """get_products should work with authenticated identity."""
        with stub_impl("get_products") as mock_tool:
            mock_tool.return_value = {"products": []}

            result = await self.handler._dispatch_skill("get_products", {"brief": "test campaign"}, self.mock_identity)

            assert result is not None
            mock_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_media_buy_requires_auth(self):
        """create_media_buy should reject None identity (not a discovery endpoint)."""
        with pytest.raises(InvalidRequestError) as exc_info:
            await self.handler._handle_explicit_skill(
                skill_name="create_media_buy", parameters={"product_ids": ["prod_1"]}, identity=None
            )

    @pytest.mark.asyncio
    async def test_update_media_buy_requires_auth(self):
        """update_media_buy should reject None identity."""
        with pytest.raises(InvalidRequestError) as exc_info:
            await self.handler._handle_explicit_skill(
                skill_name="update_media_buy", parameters={"media_buy_id": "mb_1"}, identity=None
            )
