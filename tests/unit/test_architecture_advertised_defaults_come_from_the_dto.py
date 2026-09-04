"""Structural guard: an MCP tool's ADVERTISED default is its DTO field's default.

THE RULE. FastMCP builds the published ``inputSchema`` from the wrapper's signature, so
whatever default sits there is what a buyer reads before sending anything. The DTO field
already declares that value. Two places, one fact.

They disagreed. Seven parameters advertised ``"default": null`` for fields their pinned
schema declares with a real value -- ``sync_accounts.delete_missing`` / ``dry_run``,
``sync_creatives.validation_mode``, ``create_media_buy.paused``,
``get_media_buy_delivery.include_package_daily_breakdown`` / ``include_window_breakdown``,
``list_tasks.include_history`` -- so production behaved like the spec while the advertised
contract said the opposite. Six MORE wrappers restated their DTO's value correctly, which
is the same defect in its harmless state: one refactor from disagreeing. Both are gone;
``derived_signature`` takes the default from the DTO the way it already takes the
annotation, and the six restatements were deleted rather than left to rot.

THE LIMIT, and it is deliberate. A DTO field defaulting to ``None`` declares UNSET, not a
value, so there is nothing for the announcement to own and the wrapper keeps what it wrote.
Two live parameters rely on that: ``get_products.brief`` advertises ``""`` and
``complete_task.status`` advertises ``"completed"`` where both DTOs declare ``None``, and
the pinned ``get-products-request.json`` gives ``brief`` no ``default`` at all. Deriving
there would have REPLACED two working advertised defaults with null -- a wrapper supplying
a value its model does not describe is a real question, and a different one from this rule.
They are asserted below so the limit stays measured rather than assumed.

PIN-ANCHORED, because "the wrapper agrees with the DTO" is satisfiable by a DTO that has
drifted from the spec while the wrapper faithfully publishes the drift. Where the pinned
schema declares a default, the DTO's must equal it, so the chain runs
pin -> DTO -> advertised rather than merely DTO -> advertised.

Ships with ZERO violations and no allowlist. Against the tree before the fix it reports
exactly the seven.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_core import PydanticUndefined

REPO_ROOT = Path(__file__).resolve().parents[2]


#: Every tool the server registers. Read off ``src.core.main`` rather than hand-listed, so
#: a tool added tomorrow is graded the day it is registered.
def _registered_tools() -> dict[str, Any]:
    from src.core import main
    from src.core.tools._announced_shape import request_model_for

    published = {tool.name: tool for tool in asyncio.run(main.mcp.list_tools())}
    resolved = {}
    for name, tool in published.items():
        fn = getattr(main, name, None)
        model = request_model_for(fn) if fn is not None else None
        if model is not None:
            resolved[name] = (tool, model)
    return resolved


def _declared_default(model: type, field: str) -> Any:
    info = model.model_fields.get(field)
    if info is None:
        return PydanticUndefined
    if info.default_factory is not None:
        return info.default_factory()
    return info.default


def _json_value(value: Any) -> Any:
    """The value as it appears in a published JSON schema (enums serialize to their value)."""
    return getattr(value, "value", value)


def advertised_default_mismatches(registered: dict[str, Any]) -> list[str]:
    """``tool.field`` rows where the published default is not the DTO's declared one."""
    mismatches = []
    for name, (tool, model) in sorted(registered.items()):
        properties = (tool.parameters or {}).get("properties", {})
        for field, schema in sorted(properties.items()):
            declared = _declared_default(model, field)
            if declared is PydanticUndefined or declared is None:
                # The model declares no value for the announcement to own -- see the
                # module docstring's LIMIT, which the test below pins.
                continue
            published = schema.get("default", "<no default published>")
            if published != _json_value(declared):
                mismatches.append(
                    f"{name}.{field}: advertised {json.dumps(published, default=str)} "
                    f"but {model.__name__} declares {declared!r}"
                )
    return mismatches


class TestTheDtoDefaultsAreThePinnedOnes:
    """pin -> DTO -> advertised. Without this the chain could be DTO -> advertised alone.

    A DTO whose default drifted from the spec would satisfy the rule above while every
    transport faithfully published the drift, so the values the announcement now derives
    are anchored to the pinned schemas that declare them.
    """

    PINNED = [
        ("account/sync-accounts-request.json", "src.core.schemas.account:SyncAccountsRequest", "delete_missing"),
        ("account/sync-accounts-request.json", "src.core.schemas.account:SyncAccountsRequest", "dry_run"),
        ("creative/sync-creatives-request.json", "src.core.schemas.creative:SyncCreativesRequest", "validation_mode"),
        ("media-buy/create-media-buy-request.json", "src.core.schemas:CreateMediaBuyRequest", "paused"),
        (
            "media-buy/get-media-buy-delivery-request.json",
            "src.core.schemas:GetMediaBuyDeliveryRequest",
            "include_window_breakdown",
        ),
        (
            "media-buy/get-media-buy-delivery-request.json",
            "src.core.schemas:GetMediaBuyDeliveryRequest",
            "include_package_daily_breakdown",
        ),
        ("protocol/list-tasks-request.json", "adcp.types:ListTasksRequest", "include_history"),
    ]

    @pytest.mark.parametrize(("schema_rel", "model_path", "field"), PINNED)
    def test_dto_default_matches_the_pin(self, schema_rel: str, model_path: str, field: str):
        import importlib

        from tests.helpers.adcp_pinned_schema import schema_root

        schema = json.loads((schema_root() / schema_rel).read_text())
        pinned = schema["properties"][field]["default"]

        module_name, class_name = model_path.split(":")
        model = getattr(importlib.import_module(module_name), class_name)

        assert _json_value(_declared_default(model, field)) == pinned


# ── Meta-tests: the detector itself ─────────────────────────────────────────
#
# The rule ships green, so its pass says nothing until the detector is shown to fire.


class _FakeTool:
    def __init__(self, properties: dict):
        self.parameters = {"properties": properties}


def _fake_model(**defaults):
    from pydantic import create_model

    return create_model("FakeRequest", **{k: (object | None, v) for k, v in defaults.items()})


class TestGuardDetector:
    def test_fires_when_the_advertised_default_is_null_and_the_dto_declares_a_value(self):
        """The literal shape of the bug: published null, model says False."""
        registered = {"t": (_FakeTool({"flag": {"default": None}}), _fake_model(flag=False))}

        assert advertised_default_mismatches(registered)

    def test_fires_when_the_advertised_default_is_simply_wrong(self):
        registered = {"t": (_FakeTool({"flag": {"default": True}}), _fake_model(flag=False))}

        assert advertised_default_mismatches(registered)

    def test_silent_when_they_agree(self):
        registered = {"t": (_FakeTool({"flag": {"default": False}}), _fake_model(flag=False))}

        assert advertised_default_mismatches(registered) == []

    def test_silent_when_the_model_declares_none(self):
        """The LIMIT: unset is not a value, so the wrapper's own default stands."""
        registered = {"t": (_FakeTool({"flag": {"default": ""}}), _fake_model(flag=None))}

        assert advertised_default_mismatches(registered) == []

    def test_an_enum_default_compares_by_its_json_value(self):
        """``ValidationMode.strict`` publishes as ``"strict"``; comparing the enum would misfire."""
        from adcp.types import ValidationMode

        registered = {"t": (_FakeTool({"mode": {"default": "strict"}}), _fake_model(mode=ValidationMode.strict))}

        assert advertised_default_mismatches(registered) == []

    def test_fires_when_no_default_is_published_at_all(self):
        registered = {"t": (_FakeTool({"flag": {"type": "boolean"}}), _fake_model(flag=False))}

        assert advertised_default_mismatches(registered)
