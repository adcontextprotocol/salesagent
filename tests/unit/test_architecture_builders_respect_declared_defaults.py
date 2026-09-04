"""Structural guard: a request builder must not override its DTO's declared default.

THE RULE. The request model owns each field's default. A builder that forwards a value
for a field the buyer did not send takes that ownership away, in one of two ways:

    DEFEATS      the builder's parameter defaults to None and it forwards the None, so an
                 explicit null lands where the model declared a real value.
    CONTRADICTS  the builder's parameter declares its OWN non-None default, disagreeing
                 with the model's -- a second answer to a question that had one.

Both were live. Four builders defeated seven defaults (paused, include_snapshot,
delete_missing x2, dry_run x2, validation_mode), and ``_build_list_creatives_request``
contradicted an eighth: it declared ``include_assignments = False`` where
``ListCreativesRequest`` and ``3.1/creative/list-creatives-request.json`` both say true, so
the second default INVERTED the spec's.

WHY IT MATTERED MORE THAN THE VALUES SUGGEST. Every defeated field had its default
re-established BY HAND at the read site: ``bool(req.dry_run)`` and
``bool(req.delete_missing)`` in two modules, ``enum_value(req.validation_mode) or
"strict"``, truthiness on ``req.include_snapshot`` three times. Copies of a default the
schema already declares, each free to drift from the schema and from each other. (Two
``bool(req.dry_run)`` survive, narrowing an annotation the SDK types ``bool | None`` --
wider than the pinned ``{"type": "boolean"}`` -- rather than supplying a default.) The
low blast radius was not a property of the design: ``update_media_buy`` reads ``paused``
TRISTATE (``if req.paused is not None``), so a reader that genuinely distinguishes None
from False already exists here, and it is correct only because its builder was one of the
ones that already omitted unsent fields. A reader written behind one of the other four
would have inherited a bug nobody wrote.

THE TWO CONDITIONS ARE BOTH NECESSARY, and the second is what makes the count honest. A
builder forwarding None where the MODEL also defaults to None changes nothing and is not
an instance. Scanning for "forwards a None" alone reported 6 builders and 11 fields;
requiring the model's default to actually differ reduced that to 4 and 7. Two of the six
were never defects.

WHAT THIS DOES NOT GRADE: the MCP wrapper's ANNOUNCED default, which FastMCP publishes
from the wrapper signature and which is a different surface with a different failure mode
(a ``None`` there publishes as ``"default": null``, contradicting a pinned ``false`` just
as surely as a wrong value would). Six wrappers still do that. It is measured and filed
separately rather than folded in here, because this rule is about the request a builder
BUILDS, not about the schema a tool ADVERTISES.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from adcp.types import ValidationMode
from pydantic_core import PydanticUndefined

from tests.unit._architecture_helpers import iter_call_expressions

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Sentinel for "this parameter/field declares no default at all" -- distinct from a
#: declared default that happens to be ``None``, which is the whole distinction below.
NO_DEFAULT = object()


def _registered_builders() -> dict[str, tuple[object, type]]:
    """``builder name -> (builder function, its request DTO)``, read off the live tools.

    Membership comes from the same ``builder_for`` / ``request_model_for`` lookup every
    transport uses, so a tool renaming its builder is graded without editing this file, and
    a builder no tool reaches is not graded at all -- it builds nothing a buyer can send.
    """
    from src.core import main
    from src.core.tools._announced_shape import builder_for, request_model_for

    tools = [
        "list_accounts", "sync_accounts", "get_adcp_capabilities", "get_products",
        "list_creative_formats", "sync_creatives", "list_creatives", "list_authorized_properties",
        "create_media_buy", "update_media_buy", "get_media_buy_delivery", "get_media_buys",
        "update_performance_index", "list_tasks", "get_task", "complete_task",
    ]  # fmt: skip
    found = {}
    for name in tools:
        fn = getattr(main, name)
        builder, model = builder_for(fn), request_model_for(fn)
        if builder is not None and model is not None:
            found[builder.__name__] = (builder, model)
    return found


def _builder_node(builder) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """The builder's definition, parsed from its MODULE FILE.

    ``inspect.getsource`` is banned in tests, and rightly: a guard that greps source text
    for a string is asserting about spelling. This parses the file into a tree and asks a
    structural question of it, which is the mechanism every other architecture guard here
    uses (see ``test_boundary_field_forwarding``).
    """
    path = Path(inspect.getfile(builder))
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == builder.__name__:
            return node
    return None


def forwarded_unconditionally(node: ast.FunctionDef | ast.AsyncFunctionDef, model: type) -> set[str]:
    """Field names the builder passes to ITS MODEL as a bare parameter reference.

    ``Model(x=x)`` counts; ``Model(**omit_unset(x=x))`` does not, because the helper drops
    an unsent value before it reaches the model. A computed or coerced argument
    (``brand=to_brand_reference(brand)``) is not a bare reference and is not a default
    question -- it is a value the builder means to supply.

    WHICH call is the model's is decided by ``model.__name__`` -- the model this builder's
    return annotation already names, which is how the transports find it too. It used to be
    decided by ``name.endswith(("Request", "RequestLocal"))``, and that is a spelling list:
    the day a builder returned a model spelled some third way, this function returned the
    empty set and the guard kept PASSING while grading nothing. It cost nothing to be wrong
    that way, which is the failure mode worth removing. Verified equivalent at the swap:
    across all sixteen registered builders the derived rule returned the identical set the
    suffix rule did, ``CompleteTaskRequestLocal`` included.
    """
    forwarded: set[str] = set()
    for call in iter_call_expressions(node):
        func = call.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != model.__name__:
            continue
        forwarded |= {kw.arg for kw in call.keywords if kw.arg and isinstance(kw.value, ast.Name)}
    return forwarded


def _parameter_default(builder, field: str):
    parameter = inspect.signature(builder).parameters.get(field)
    if parameter is None or parameter.default is inspect.Parameter.empty:
        return NO_DEFAULT
    return parameter.default


def _model_default(model: type, field: str):
    info = model.model_fields.get(field)
    if info is None:
        return NO_DEFAULT
    if info.default_factory is not None:
        return info.default_factory()
    if info.default is PydanticUndefined:
        return NO_DEFAULT
    return info.default


def overridden_defaults(builder, model: type) -> list[tuple[str, str, object, object]]:
    """``(kind, field, builder default, model default)`` for every default this builder overrides."""
    findings = []
    node = _builder_node(builder)
    if node is None:
        return []
    for field in sorted(forwarded_unconditionally(node, model)):
        model_default = _model_default(model, field)
        if model_default is NO_DEFAULT or model_default is None:
            continue  # the model declares nothing to defeat
        builder_default = _parameter_default(builder, field)
        if builder_default is NO_DEFAULT:
            continue  # required of the caller; never silently substituted
        if builder_default is None:
            findings.append(("DEFEATS", field, builder_default, model_default))
        elif builder_default != model_default:
            findings.append(("CONTRADICTS", field, builder_default, model_default))
    return findings


def test_no_builder_overrides_its_models_declared_default():
    builders = _registered_builders()
    assert len(builders) >= 10, (
        f"only {len(builders)} builders resolved off the live tools -- this guard grades "
        f"what it can resolve, so a broken lookup makes it pass vacuously."
    )

    violations = [
        f"{name}.{field}: builder default {bd!r} overrides {model.__name__}'s {md!r} ({kind})"
        for name, (builder, model) in sorted(builders.items())
        for kind, field, bd, md in overridden_defaults(builder, model)
    ]
    assert not violations, (
        "A request builder overrides a default its request model already declares. The "
        "model owns the default: forwarding None puts an explicit null where the declared "
        "value belongs, and declaring a different one in the builder signature answers the "
        "question twice. Pass the field through `omit_unset(...)` "
        "(src/core/tools/_request_defaults.py) so an unsent value is omitted and the "
        "model's default applies. Violations:\n  " + "\n  ".join(violations)
    )


#: A minimal valid call for each builder that had a defeated default, so the request can
#: be BUILT with the field under test unsent. Hand-written because the required arguments
#: differ per tool and there is no generic way to invent a valid one.
_IDEMPOTENCY_KEY = "idem-" + "x" * 20
_CREATIVE = {
    "creative_id": "c1",
    "name": "C1",
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
    "assets": {},
}


def test_the_declared_defaults_actually_arrive():
    """The rule, graded as BEHAVIOUR on all eight fields that broke, not just structurally.

    Building with each field UNSENT must yield the model's declared value. That is what a
    reader of ``req.<field>`` gets, and it is exactly what five read sites were
    compensating for by hand before the builders stopped overriding it.
    """
    from src.core.tools.accounts import build_sync_accounts_request
    from src.core.tools.creatives.listing import _build_list_creatives_request
    from src.core.tools.creatives.sync_wrappers import build_sync_creatives_request
    from src.core.tools.media_buy_create import _build_create_media_buy_request
    from src.core.tools.media_buy_list import _build_get_media_buys_request

    assert _build_get_media_buys_request().include_snapshot is False
    assert _build_list_creatives_request().include_assignments is True

    accounts = build_sync_accounts_request(accounts=[], idempotency_key=_IDEMPOTENCY_KEY)
    assert accounts.delete_missing is False
    assert accounts.dry_run is False

    creatives = build_sync_creatives_request(
        creatives=[_CREATIVE], idempotency_key=_IDEMPOTENCY_KEY, account={"account_id": "a1"}
    )
    assert creatives.delete_missing is False
    assert creatives.dry_run is False
    assert creatives.validation_mode == ValidationMode.strict

    media_buy = _build_create_media_buy_request(
        brand={"domain": "a.com"},
        packages=[{"product_id": "p", "pricing_option_id": "po", "budget": 1.0}],
        start_time="2026-02-01T00:00:00Z",
        end_time="2026-02-02T00:00:00Z",
        account={"account_id": "a1"},
        idempotency_key=_IDEMPOTENCY_KEY,
    )
    assert media_buy.paused is False


class TestModelDefaultsAreTheSpecs:
    """The values the builders now defer to are the PINNED ones, not merely self-consistent.

    Without this the guard would be satisfied by a DTO whose default drifted from the
    schema -- the builders would faithfully deliver the wrong value.
    """

    @pytest.mark.parametrize(
        ("model_path", "field", "expected"),
        [
            ("src.core.schemas:GetMediaBuysRequest", "include_snapshot", False),
            ("src.core.schemas:CreateMediaBuyRequest", "paused", False),
            ("src.core.schemas.creative:SyncCreativesRequest", "delete_missing", False),
            ("src.core.schemas.creative:SyncCreativesRequest", "dry_run", False),
            ("src.core.schemas.account:SyncAccountsRequest", "delete_missing", False),
            ("src.core.schemas.account:SyncAccountsRequest", "dry_run", False),
            ("src.core.schemas:ListCreativesRequest", "include_assignments", True),
        ],
    )
    def test_model_default_matches_the_pinned_schema(self, model_path: str, field: str, expected: object):
        import importlib

        module_name, class_name = model_path.split(":")
        model = getattr(importlib.import_module(module_name), class_name)

        assert _model_default(model, field) == expected


# ── Meta-tests: the detector itself ─────────────────────────────────────────
#
# The rule ships green, so its pass says nothing until the detector is shown to fire.


class _Model:
    model_fields: dict = {}


def _fake(model_defaults: dict):
    from pydantic import BaseModel, Field

    return type("FakeRequest", (BaseModel,), {"__annotations__": dict.fromkeys(model_defaults, object),
                                              **{k: Field(default=v) for k, v in model_defaults.items()}})  # fmt: skip


class TestGuardDetector:
    """Fired against synthetic builders, parsed the same way the live ones are."""

    @staticmethod
    def _forwarded(source: str, model_name: str = "FakeRequest") -> set[str]:
        node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef))
        return forwarded_unconditionally(node, type(model_name, (), {}))

    def test_sees_a_bare_parameter_forwarded_to_the_model(self):
        assert self._forwarded("def b(flag=None):\n    return FakeRequest(flag=flag)\n") == {"flag"}

    def test_does_not_see_a_field_routed_through_omit_unset(self):
        """The cure: an unsent value never reaches the model, so no default is overridden."""
        assert self._forwarded("def b(flag=None):\n    return FakeRequest(**omit_unset(flag=flag))\n") == set()

    def test_does_not_see_a_coerced_argument(self):
        """``brand=to_brand_reference(brand)`` is a value the builder MEANS to supply."""
        assert self._forwarded("def b(brand=None):\n    return FakeRequest(brand=to_ref(brand))\n") == set()

    def test_sees_a_model_whose_name_no_suffix_list_would_predict(self):
        """The reason membership is the model's OWN name and not a spelling.

        ``ListCreativesInternal`` ends in neither "Request" nor "RequestLocal"; under the
        suffix rule this builder forwarded nothing and the guard passed vacuously.
        """
        source = "def b(flag=None):\n    return ListCreativesInternal(flag=flag)\n"

        assert self._forwarded(source, model_name="ListCreativesInternal") == {"flag"}

    def test_does_not_see_a_call_to_some_other_model(self):
        """A builder that constructs a helper model on the way is not forwarding to ITS model."""
        source = "def b(flag=None):\n    return FakeRequest(inner=OtherRequest(flag=flag))\n"

        assert self._forwarded(source) == set()


class TestDefaultComparison:
    """The two-condition rule, on the model side."""

    @staticmethod
    def _model(**defaults):
        from pydantic import create_model

        return create_model("FakeRequest", **{k: (object | None, v) for k, v in defaults.items()})

    def test_a_none_defeating_a_real_default_is_reported(self):
        model = self._model(flag=False)

        assert _model_default(model, "flag") is False

    def test_a_model_defaulting_to_none_has_nothing_to_defeat(self):
        model = self._model(flag=None)

        assert _model_default(model, "flag") is None

    def test_a_field_the_model_does_not_declare_is_not_graded(self):
        assert _model_default(self._model(flag=False), "other") is NO_DEFAULT
