"""``tool -> its response schema``, derived rather than written down.

A BDD scenario names the TOOL and, where the schema branches, the branch. It
never names a schema file: a filename in a feature file is a second spelling of
"which tool is this scenario exercising", and the two drift.

Everything here is derived from two live sources — the tool registry and the
pinned SDK's own module layout — so a tool cannot be graded against the wrong
contract by anyone forgetting to update a table.
"""

from __future__ import annotations

import typing

from adcp import types as adcp_types
from pydantic import BaseModel

from src.core.tools.registry import TOOLS
from tests.helpers.pinned_schema import load, validator_for


def _camel(tool: str) -> str:
    return "".join(part.title() for part in tool.split("_"))


def _category(tool: str) -> str | None:
    """The schema's directory, read off the SDK response type's module path.

    ``GetProductsResponse`` lives in ``adcp.types.generated_poc.media_buy.…``,
    and its schema in ``media-buy/``. This is not decoration: two DIFFERENT
    schemas share the basename ``list-creative-formats-response.json`` (one
    under ``creative/``, one under ``media-buy/``), so a bare filename is
    genuinely ambiguous and the loader refuses it rather than guessing.

    A response type that is a UNION of outcome branches has no ``__module__`` of
    its own; the branches do, and they agree, so the first is read.

    Returns ``None`` for a tool the SDK does not type at all — the app-owned
    schemas in ``schemas/`` are found by bare filename, which is unambiguous
    there.
    """
    model = getattr(adcp_types, _camel(tool) + "Response", None)
    if model is None:
        return None
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        branches = [arg for arg in typing.get_args(model) if isinstance(arg, type)]
        model = branches[0] if branches else None
    module = getattr(model, "__module__", "") or ""
    if ".generated_poc." not in module:
        return None
    return module.split(".")[-2].replace("_", "-")


def response_schema_ref(tool: str) -> str:
    """The schema ref for *tool*'s response, category-qualified where one exists.

    REGISTRY MEMBERSHIP IS REQUIRED, and the failure is the point. A tool this
    seller has not built cannot be dispatched, so no response exists to grade —
    a scenario naming one is not a scenario that could pass. Resolving its schema
    anyway would let such a scenario look gradeable while exercising nothing,
    which is how a whole use case quietly stops counting.

    ``activate_signal``, ``build_creative``, ``preview_creative`` and the ``si_*``
    session tools all have pinned schemas and no implementation. Raising here
    names them, one scenario at a time, and that count IS the scale of what is
    left to build.
    """
    if tool not in TOOLS:
        raise KeyError(
            f"{tool!r} is not a registered tool, so nothing can dispatch it and no "
            f"response exists to grade. The registry (src/core/tools/registry.py) "
            f"holds: {sorted(TOOLS)}"
        )
    filename = tool.replace("_", "-") + "-response.json"
    category = _category(tool)
    return f"{category}/{filename}" if category else filename


def branch_names(tool: str) -> list[str]:
    """The ``oneOf`` branch words a scenario may name, e.g. success/error/submitted.

    Read from the schema's own branch titles: ``CreateMediaBuySuccess`` under
    ``create-media-buy-response.json`` yields ``"success"``. Empty for a tool
    whose response is one shape.
    """
    schema = load(response_schema_ref(tool))
    prefix = _camel(tool)
    words = []
    for branch in schema.get("oneOf") or schema.get("anyOf") or []:
        title = branch.get("title", "")
        words.append((title[len(prefix) :] if title.startswith(prefix) else title).lower())
    return [w for w in words if w]


def response_validator(tool: str, branch: str | None = None):
    """A validator for *tool*'s response, narrowed to one branch if named.

    A branchless tool with a branch named, or a branching tool with none, is an
    error rather than a silent full-document check: "compliant with the
    create_media_buy spec" would pass against the ERROR branch when the scenario
    meant success, which grades the opposite of what it says.
    """
    ref = response_schema_ref(tool)
    available = branch_names(tool)

    if branch is None:
        if available:
            raise ValueError(
                f"{tool} responds in one of {available} — name the branch, e.g. "
                f'"the response is compliant with the {tool} {available[0]} spec". '
                f"Validating against the whole oneOf would pass on any branch, "
                f"including the one the scenario is asserting did NOT happen."
            )
        return validator_for(ref)

    if branch not in available:
        raise ValueError(
            f"{tool} has no {branch!r} response branch. "
            f"{'Available: ' + str(available) if available else 'It responds in one shape — drop the branch word.'}"
        )

    schema = load(ref)
    for candidate in schema.get("oneOf") or schema.get("anyOf") or []:
        title = candidate.get("title", "")
        if (title[len(_camel(tool)) :] if title.startswith(_camel(tool)) else title).lower() == branch:
            return validator_for(f"{ref}#/oneOf/{(schema.get('oneOf') or []).index(candidate)}")
    raise ValueError(f"{tool}: branch {branch!r} vanished between listing and lookup")
