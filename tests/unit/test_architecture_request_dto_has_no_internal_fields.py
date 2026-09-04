"""Structural guard: a registered tool's request DTO declares no ``exclude=True`` field.

THE RULE. ``exclude=True`` is a SERIALIZATION control -- pydantic's way of saying "do not
write this out". This repo has been using it on REQUEST models to control what a transport
ACCEPTS, because all three announced-shape derivations happen to drop excluded fields:
``derived_signature`` for MCP (``src/core/tools/_announced_shape.py:300``),
``derived_body_model`` for REST (``src/routes/_derived_body.py:115``) and
``select_request_fields`` for A2A (``src/core/schema_helpers.py:429``). So one marker means
two different things, and the second meaning holds only for as long as three separate
derivations keep honouring it.

That coincidence has already produced a bug of the shape it invites: ``exclude=True``
survived a nested ``model_dump`` and deleted a buyer's ``creative_ids`` from a request,
producing a cross-principal acceptance. The marker means "do not send this back"; it
silently also meant "do not accept this".

The fix is not a better marker. The request DTO is the buyer-facing shape with no
qualification, so an internal field belongs on an EXTENDED model
(``ListCreativesInternal(ListCreativesRequest)``, without the marker) that internal callers
name, or nowhere at all. See ``docs/design/one-tool-registry.md``, "Decisions this forces,
and the answers".

SCOPE, and it is exact: the TOP-LEVEL registered tool DTO's own ``model_fields``. Nested
request models are deliberately not graded here -- ``PackageRequest`` (nested in
``CreateMediaBuyRequest.packages``) carries nine excluded fields, and the narrowing of
``create_media_buy`` has to touch that model anyway. This is a scope, not an allowlist:
nothing is named, so a nested model cannot be forgotten back into scope, and a top-level
field cannot be excused out of it.

MEMBERSHIP IS DERIVED, and that is the point. The tools come from the live FastMCP registry
(``main.mcp.list_tools()``) and each DTO from ``request_model_for``, the same lookup every
transport uses. A hand-written list of tool or class names would grade that something was
RECORDED, never that it was CORRECT -- guards written that way in this repo have twice
covered 10 or 11 of 14 items with every test green.

Against the tree at ``3caab554c`` this reports exactly four:
``GetProductsRequest.product_selectors``, ``ListCreativesRequest.format``,
``ListCreativesRequest.page`` and ``UpdateMediaBuyRequest.today``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

#: Tools registered by ``src/core/main.py`` today. The floor exists because this guard
#: grades what it can RESOLVE: a lookup that silently returns nothing would leave it
#: passing while grading zero DTOs, which is worse than not having it.
MINIMUM_REGISTERED_TOOLS = 16


def _registered_dtos() -> dict[str, type[BaseModel]]:
    """``tool name -> its request DTO``, read off the live registry.

    Names come from the FastMCP instance rather than a list here, so a tool added tomorrow
    is graded the day it is registered; the DTO comes from ``request_model_for``, so this
    file cannot disagree with the transports about which model a tool announces.

    ``getattr(main, name)`` is the UNDECORATED tool function. The registered object is the
    ``with_error_logging`` wrapper, whose own bytecode names no builder -- reading the DTO
    off that would report every tool as having none.
    """
    from src.core import main
    from src.core.tools._announced_shape import request_model_for

    resolved: dict[str, type[BaseModel]] = {}
    for tool in asyncio.run(main.mcp.list_tools()):
        fn = getattr(main, tool.name, None)
        model = request_model_for(fn) if fn is not None else None
        if model is not None:
            resolved[tool.name] = model
    return resolved


def internal_request_fields(dtos: dict[str, Any]) -> list[str]:
    """``Tool -> Class.field`` rows for every excluded field a request DTO DECLARES.

    ``model_fields`` is the top-level declaration, so nested models are out of scope by
    construction. ``field.exclude`` is ``bool | None``: an explicit ``exclude=False`` is a
    field that is not internal, so truthiness is the question, not "is set".
    """
    rows = []
    for name, model in sorted(dtos.items()):
        for field, info in sorted(model.model_fields.items()):
            if info.exclude:
                rows.append(f"{name}: {model.__name__}.{field}")
    return rows


def test_the_registry_resolved_every_tools_dto():
    """Guard the guard: a broken lookup must fail here, not pass everything below."""
    from src.core import main

    published = {tool.name for tool in asyncio.run(main.mcp.list_tools())}
    resolved = _registered_dtos()

    assert len(published) >= MINIMUM_REGISTERED_TOOLS, (
        f"only {len(published)} tools came back from the FastMCP registry, expected at least "
        f"{MINIMUM_REGISTERED_TOOLS} — the derivation is broken, so every assertion built on "
        f"it would pass vacuously"
    )
    assert published == set(resolved), (
        f"no request DTO resolved for {sorted(published - set(resolved))}. _register_tool "
        f"refuses a tool whose DTO cannot be resolved, so either the builder edge broke or "
        f"this guard is reading the wrong function off src.core.main"
    )


def test_no_registered_request_dto_declares_an_internal_field():
    offenders = internal_request_fields(_registered_dtos())

    assert not offenders, (
        "A registered tool's request DTO declares an internal (exclude=True) field. "
        "exclude=True is a SERIALIZATION control; it keeps the field off all three "
        "announced shapes only because derived_signature, derived_body_model and "
        "select_request_fields each happen to honour it — three separate coincidences, and "
        "the same marker has already deleted a buyer's field out of a nested request. The "
        "request DTO is the buyer-facing shape with no qualification.\n"
        "Fix each by either (a) moving the field onto an extended model — "
        "`class XInternal(XRequest)` declaring it WITHOUT exclude=True — and typing the "
        "builder, the raw wrapper and the _impl to that model, or (b) deleting the field if "
        "nothing reads it. Do not delete the marker in place: that widens an internal field "
        "onto the REST and A2A wire. See docs/design/one-tool-registry.md, 'Decisions this "
        "forces, and the answers'.\n"
        "Violations:\n  " + "\n  ".join(offenders)
    )


# ── Meta-test: the detector itself ──────────────────────────────────────────
#
# Once the four violations are fixed the rule ships green, and a green rule says nothing
# until the detector has been shown to fire.


class TestGuardDetector:
    @staticmethod
    def _model(**field_kwargs: Any) -> type[BaseModel]:
        from pydantic import Field, create_model

        return create_model(
            "FakeRequest",
            **{name: (str | None, Field(default=None, **kwargs)) for name, kwargs in field_kwargs.items()},
        )

    def test_fires_on_an_excluded_top_level_field(self):
        """The literal shape of the bug: an internal field declared on the request model."""
        assert internal_request_fields({"t": self._model(internal_thing={"exclude": True})}) == [
            "t: FakeRequest.internal_thing"
        ]

    @pytest.mark.parametrize("marker", [{}, {"exclude": False}])
    def test_silent_on_a_buyer_field(self, marker: dict):
        """No marker and an explicit exclude=False are both 'this is buyer input'."""
        assert internal_request_fields({"t": self._model(brief=marker)}) == []

    def test_silent_on_a_nested_models_excluded_field(self):
        """The scope is the top-level DTO's own fields — nested models are excluded by
        construction rather than by an allowlist entry that could be forgotten."""
        from pydantic import Field, create_model

        nested = create_model("FakeNested", tenant_id=(str | None, Field(default=None, exclude=True)))
        parent = create_model("FakeRequest", packages=(list[nested] | None, None))  # type: ignore[valid-type]

        assert internal_request_fields({"t": parent}) == []
