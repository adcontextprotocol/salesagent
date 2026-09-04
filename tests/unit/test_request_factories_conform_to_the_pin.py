"""Every request factory's baseline validates against the tool's PINNED schema.

Why this exists, and why it is not a guard on the models: the factories are the
one place a test payload is written by hand, so they are the one place a
non-conformant baseline can enter the suite. A baseline that our DTO accepts is
graded against the WEAKER of two contracts whenever the DTO is wider than the pin
-- and it has been, measurably: ``GetProductsRequest.buying_mode`` is
``str | None`` here while the pin requires the enum, so a factory written against
the DTO alone could omit it and nothing would notice.

This does not check the models. It checks that the thing we hand a seller is a
thing the spec would accept.
"""

from __future__ import annotations

import glob
import json
import os

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

import tests.factories.request as request_factories
from src.core.tools.registry import TOOLS

_PINNED = glob.glob(".venv/lib/*/site-packages/adcp/_schemas/3.1")

#: Tools whose pinned request schema is not named ``<tool>-request.json``.
_SCHEMA_NAME = {
    "get_task": "tasks-get-request.json",
    "list_tasks": "tasks-list-request.json",
}

#: Tools the pin declares NO request schema for, with the reason. Not a skip:
#: a row here is a claim that the spec is silent, and it fails if the spec speaks.
_NO_PINNED_SCHEMA = {
    "complete_task": (
        "adcp 6.6.0 / spec 3.1 ships no complete-task request schema -- the only "
        "'complet*' file in the tree is enums/completion-source.json. We implement "
        "the tool; the pin does not describe its request."
    ),
}


def _schema_path(tool: str) -> str | None:
    name = _SCHEMA_NAME.get(tool, tool.replace("_", "-") + "-request.json")
    hits = [f for f in glob.glob(_PINNED[0] + "/**/*.json", recursive=True) if os.path.basename(f) == name]
    return hits[0] if hits else None


def _registry() -> Registry:
    """Resolves the relative ``$ref``s the pinned schemas use between files.

    ``core/version-envelope.json`` alone is referenced by most request schemas
    through ``allOf``, so without a retriever every validation raises Unresolvable
    rather than reporting on the payload.
    """

    def retrieve(uri: str) -> Resource:
        base = os.path.basename(uri)
        hits = [f for f in glob.glob(_PINNED[0] + "/**/*.json", recursive=True) if os.path.basename(f) == base]
        if not hits:
            raise LookupError(uri)
        return Resource.from_contents(json.load(open(hits[0])), default_specification=DRAFT7)

    return Registry(retrieve=retrieve)


def _factory(tool: str):
    return getattr(request_factories, "".join(p.title() for p in tool.split("_")) + "RequestFactory")


@pytest.mark.skipif(not _PINNED, reason="pinned schema tree not installed")
@pytest.mark.parametrize("tool", sorted(t for t in TOOLS if t not in _NO_PINNED_SCHEMA))
def test_the_baseline_validates_against_the_pinned_request_schema(tool: str) -> None:
    path = _schema_path(tool)
    assert path is not None, (
        f"{tool}: no pinned request schema found. Either it is named something this "
        f"test does not expect (add a _SCHEMA_NAME row) or the pin does not declare "
        f"one (add a _NO_PINNED_SCHEMA row with the reason). Silence is not an option."
    )
    errors = list(jsonschema.Draft7Validator(json.load(open(path)), registry=_registry()).iter_errors(_factory(tool).payload()))
    assert not errors, f"{tool} baseline is not conformant: " + "; ".join(e.message for e in errors[:3])


@pytest.mark.skipif(not _PINNED, reason="pinned schema tree not installed")
@pytest.mark.parametrize("tool", sorted(_NO_PINNED_SCHEMA))
def test_a_tool_recorded_as_unpinned_really_has_no_schema(tool: str) -> None:
    """The absence rows are claims about the pin, so they are checked too.

    If a bump adds the schema this row denies, the row is stale and the baseline
    has been ungraded ever since. That is exactly the drift an unchecked skip
    hides.
    """
    assert _schema_path(tool) is None, (
        f"{tool}: the pin now declares a request schema, so _NO_PINNED_SCHEMA is "
        f"stale. Delete the row -- the baseline can be graded."
    )


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_every_registered_tool_has_a_factory_bound_to_the_registry_dto(tool: str) -> None:
    """The factory builds the SAME class the tool dispatches with.

    Identity, not name: ``CompleteTaskRequest`` and ``CompleteTaskRequestLocal``
    differ by three required fields, and a factory bound to the wrong one produces
    a baseline the tool rejects, surfacing as a ValidationError in the caller's
    setup rather than at the boundary under test.
    """
    assert _factory(tool)._meta.model is TOOLS[tool].dto
