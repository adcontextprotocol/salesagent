"""A2A 'success' field: single derivation, not 3 duplicated inline copies (#1868 review).

Three sites independently stamped response_data["success"] onto the A2A wire:
_serialize_for_a2a (the declared "single serialization point", which correctly
derives success from the presence of `errors`), _handle_get_products_skill, and
_get_products (the natural-language handler) -- the latter two duplicated the
stamp inline WITHOUT the errors-derivation, unconditionally forcing
success=True even when the response carried populated `errors`.

This is a DRY violation (CLAUDE.md non-negotiable invariant) that hid a real
behavioral divergence: a get_products response with per-item errors reported
success=True on the A2A wire via the explicit-skill and NL paths, but
success=False via any other path that returns a raw Pydantic model through
_serialize_for_a2a.
"""

from __future__ import annotations

from src.core.schemas import GetProductsResponse
from tests.factories.principal import PrincipalFactory

_MOCK_IDENTITY = PrincipalFactory.make_identity(
    principal_id="test_principal", tenant_id="test_tenant", tenant={"tenant_id": "test_tenant"}, protocol="a2a"
)


def _make_get_products_response(errors=None) -> GetProductsResponse:
    """A real GetProductsResponse -- no MagicMock standing in for the response object.

    A MagicMock's canned .model_dump()/__str__ return values round-trip regardless of
    what _stamp_a2a_protocol_fields actually does with a real Pydantic model, so it
    cannot observe a regression in that behavior. This constructs the same response
    type production actually returns from core_get_products_tool.
    """
    kwargs = {"products": []}
    if errors is not None:
        kwargs["errors"] = errors
    return GetProductsResponse(**kwargs)


class TestSerializeForA2ADerivesSuccessFromErrors:
    """Baseline: the declared single serialization point already gets this right."""


class TestHandleGetProductsSkillDerivesSuccessFromErrors:
    """_handle_get_products_skill duplicated the stamp without errors-derivation."""


class TestNaturalLanguageGetProductsDerivesSuccessFromErrors:
    """_get_products (NL handler) duplicated the stamp without errors-derivation."""
