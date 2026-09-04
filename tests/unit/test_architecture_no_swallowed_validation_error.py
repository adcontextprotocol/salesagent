"""Structural guard: nothing between a request builder and the transport boundary
may catch the ValidationError it raises.

THE RULE. A ``build_*_request`` / ``create_*_request`` call constructs a request DTO from
buyer input. When it raises, the pydantic ``ValidationError`` must travel untouched to the
transport boundary, where ``adcp_error_for`` names it INVALID_REQUEST and attaches the
``field`` and the ``issues``. Any frame in between that catches ``ValidationError``,
``ValueError``, ``Exception`` or ``BaseException`` and does not re-raise takes that
decision away from the boundary, and every observed instance took it in the wrong
direction.

This is the INVERSE of the rule two deleted guards enforced
(``test_architecture_request_construction_boundary.py``,
``test_guards_rest_request_boundary.py``), and it replaces them rather than restoring
them. They required construction INSIDE ``adcp_validation_boundary``. That wrapper is
gone from 46 of its 48 sites, because a bare block was literally
``raise adcp_error_for(e, field=None)`` -- the call the boundary makes one frame later,
off the same exception, to the same effect (measured byte-identical on all three
transports; ``tests/unit/test_validation_error_at_the_boundary.py`` grades it). A guard
demanding a wrapper cannot outlive the wrapper. The HAZARD outlives it, and this is the
hazard.

TWO INSTANCES, BOTH REAL, BOTH FOUND BY HAND ONCE:

* ``creative_helpers.process_and_upload_package_creatives`` wrapped its builder call in
  ``except Exception -> AdCPAdapterError``. A buyer whose inline creative omitted a
  required field was told the SERVER was unavailable and to retry a request that could
  never succeed. (gh-#1299's neighbourhood; the fix that preceded this one added a
  wrapper, which this deletion then removed -- the site needed the handler corrected, not
  the wrapper restored.)
* the ``get_products`` MCP wrapper caught ``ValueError`` and re-raised
  ``AdCPValidationError``. A pydantic ``ValidationError`` IS a ``ValueError``, so once the
  DTO was no longer built inside the wrapper this handler answered a bare
  VALIDATION_ERROR and discarded the ``field`` and ``issues`` the buyer was owed.

Run against the commit before that change, this guard reports exactly those two sites and
nothing else. It would have found what a manual scan of every construction site found,
and it repeats.

WHY THE BUILDER SEAM AND NOT EVERY REQUEST CONSTRUCTION -- measured, not assumed. Scanning
every ``*Request(...)`` / ``.model_validate(...)`` / ``to_*`` coercion (the matcher the
deleted guard used) reports 9 sites under ``src/core/tools`` + ``src/core/helpers``. None
is this disease:

* three are the approval REPLAY path, reconstructing an already-validated request out of
  ``raw_request`` in the database (``CreateMediaBuyRequest(**raw_request_data)``,
  ``Targeting(**targeting_raw)``, ``FormatId.model_validate(fmt)``). A failure there is
  corrupt internal state, not a buyer error, and ``ApprovalResult.failed`` is the right
  answer;
* two build ``FormatId`` from a PRODUCT's stored format list -- server-side data;
* two are the per-creative loop in ``creatives/_sync.py``, whose partial-success contract
  requires one malformed creative to become one ``action=failed`` result rather than
  aborting the request;
* two are ``uow.media_buys.create_from_request(...)``, a repository persistence METHOD
  that merely matches the builder name pattern.

The ninth is the interesting one, and it is not the disease either: ``media_buy_create``'s
``FormatId.model_validate`` re-raises as ``AdCPValidationError(field="packages[i].
format_ids[j]")``. That is the SAME requalification job the two surviving
``adcp_validation_boundary`` sites do -- a model coerced outside its parent request has a
pydantic ``loc`` rooted at its own top, so no later frame can recover the indexed pointer.
It translates in order to say something the boundary could not, which is the one licensed
reason to translate. (Whether that pointer should carry INVALID_REQUEST rather than
VALIDATION_ERROR is a separate question about the CODE, not about the handler, and is not
this guard's business.)

The property separating all nine from the disease is WHERE THE DATA CAME FROM -- the wire,
or our own database -- plus, for the ninth, whether the handler ADDS information. Neither
is structurally decidable: ``CreateMediaBuyRequest(**d)`` looks identical either way.
Shipping the wide rule would therefore need a nine-entry allowlist, which records
violations instead of making them unreachable -- the trade ``_register_tool`` refuses by
construction, and one this guard does not need to make. A BUILDER call carries the
distinction in the artifact: the builders exist to turn buyer parameters into a request
DTO, so a builder call IS buyer input, always. Zero allowlist, and the wide rule's nine
non-instances are not suppressed, they are not matched.

WHY NOT "TRANSPORT MODULES ONLY", the narrower scope offered as a fallback: measured, it
reports zero violations at the commit before the fixes as well as after -- it would have
caught NEITHER instance, because both live in ``src/core/tools`` and
``src/core/helpers``. A green that cannot go red is not a narrower guard, it is no guard.

KNOWN LIMIT, stated rather than papered over: the scan is LEXICAL. A builder called in one
function whose CALLER wraps it in ``except Exception`` is invisible here, and closing that
needs a call graph. The two observed instances were both lexical, and the seam is one
function call wide, so the lexical form covers the shape this disease has actually taken.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "src"

#: The builder naming convention, shared with ``src/core/tools/_announced_shape.py``'s
#: ``_BUILDER_NAME``. Spelled out again rather than imported because this guard must keep
#: grading the tree even if that module's lookup changes shape.
_BUILDER_DEF = re.compile(r"^(_?build_\w+_request|create_\w+_request)$")

#: Handler types that can catch a pydantic ``ValidationError``. ``ValueError`` is here
#: because ``ValidationError`` subclasses it -- the fact that made the ``get_products``
#: handler start swallowing schema rejections the moment the wrapper left.
_CATCHES_VALIDATION_ERROR = frozenset({"ValidationError", "ValueError", "Exception", "BaseException", "<bare>"})


def builder_names(trees: dict[str, ast.AST]) -> frozenset[str]:
    """Every MODULE-LEVEL request builder defined in the scanned tree.

    Module-level is load-bearing, not tidiness: ``MediaBuyRepository.create_from_request``
    matches the name pattern and is a persistence method, not a request builder. Requiring
    a top-level ``def`` excludes it structurally, so the guard needs no name exception for
    it -- and would exclude the next such method without being edited.
    """
    names: set[str] = set()
    for tree in trees.values():
        for node in getattr(tree, "body", []):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _BUILDER_DEF.match(node.name):
                names.add(node.name)
    return frozenset(names)


def _handler_types(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return ["<bare>"]
    return [part.strip() for part in ast.unparse(handler.type).strip("()").split(",")]


def _is_passthrough(handler: ast.ExceptHandler) -> bool:
    """True for ``except ...: raise`` -- the exception continues to the boundary unchanged."""
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Raise) and handler.body[0].exc is None


def _swallowing_types(node: ast.Try) -> list[str]:
    """Which of ``_CATCHES_VALIDATION_ERROR`` this ``try`` actually swallows.

    Python dispatches to the FIRST matching handler, so ORDER decides. An arm that catches
    ``ValidationError`` and re-raises makes every later arm unreachable for it -- which is
    exactly how the ``creative_helpers`` fix works (``except (AdCPSalesAgentError,
    ValidationError): raise`` sits above the ``except Exception`` that used to reclassify
    it). A guard that ignored order would flag that fix and force it to be written as
    something worse.
    """
    for handler in node.handlers:
        types = _handler_types(handler)
        if not set(types) & _CATCHES_VALIDATION_ERROR:
            continue  # cannot match a ValidationError; keep looking
        if _is_passthrough(handler):
            return []  # first match re-raises -- the site is safe
        return [t for t in types if t in _CATCHES_VALIDATION_ERROR]
    return []


def find_swallowed_builder_calls(tree: ast.AST, builders: frozenset[str]) -> list[tuple[int, str, list[str]]]:
    """``(lineno, builder, swallowing handler types)`` for every offending call in ``tree``."""
    offenders: list[tuple[int, str, list[str]]] = []

    def walk(node: ast.AST, swallowed_by: list[str]) -> None:
        if isinstance(node, ast.Try):
            here = _swallowing_types(node)
            for child in node.body:
                walk(child, swallowed_by + here)
            # A construction inside a HANDLER is not protected by that same handler.
            for handler in node.handlers:
                for child in handler.body:
                    walk(child, swallowed_by)
            for child in [*node.orelse, *node.finalbody]:
                walk(child, swallowed_by)
            return
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if name in builders and swallowed_by:
                offenders.append((node.lineno, name, sorted(set(swallowed_by))))
        for child in ast.iter_child_nodes(node):
            walk(child, swallowed_by)

    walk(tree, [])
    return offenders


def _parsed_source_tree() -> dict[str, ast.AST]:
    return {
        str(path.relative_to(REPO_ROOT)): ast.parse(path.read_text(), filename=str(path))
        for path in sorted(SCAN_ROOT.rglob("*.py"))
    }


def test_no_handler_swallows_a_builders_validation_error():
    trees = _parsed_source_tree()
    builders = builder_names(trees)
    assert builders, "no request builders found -- the guard would pass vacuously"

    violations = [
        f"{relpath}:{lineno}: {builder} inside `except {'/'.join(caught)}`"
        for relpath, tree in trees.items()
        for lineno, builder, caught in find_swallowed_builder_calls(tree, builders)
    ]
    assert not violations, (
        "A request builder's pydantic ValidationError is caught before it reaches the "
        "transport boundary. The boundary is what turns it into INVALID_REQUEST carrying "
        "the buyer's field and issues (src/core/exceptions.py::adcp_error_for); a handler "
        "in between answers something else, and both prior instances answered something "
        "strictly worse -- an adapter outage, and a bare VALIDATION_ERROR with no field. "
        "Let it propagate: re-raise it from an arm ABOVE the catch-all "
        "(`except (AdCPSalesAgentError, ValidationError): raise`), or narrow the handler "
        "so it cannot match. Do NOT re-add a wrapper that translates it here. "
        "Violations:\n  " + "\n  ".join(violations)
    )


# ── Meta-tests: the detector itself ─────────────────────────────────────────
#
# A structural guard that cannot be shown to FIRE is indistinguishable from one that is
# broken, and this one ships with an empty violation set -- so its green says nothing
# until these run.

_BUILDERS = frozenset({"build_thing_request"})


def _detect(snippet: str) -> list[tuple[int, str, list[str]]]:
    return find_swallowed_builder_calls(ast.parse(snippet), _BUILDERS)


class TestGuardDetector:
    def test_fires_on_bare_except_exception(self):
        assert _detect("try:\n    r = build_thing_request(x=1)\nexcept Exception:\n    r = None\n")

    def test_fires_on_except_value_error(self):
        """The get_products shape: ValidationError IS a ValueError."""
        assert _detect("try:\n    r = build_thing_request(x=1)\nexcept ValueError as e:\n    raise Other() from e\n")

    def test_fires_on_bare_except(self):
        assert _detect("try:\n    r = build_thing_request(x=1)\nexcept:\n    r = None\n")

    def test_fires_through_an_attribute_call(self):
        assert _detect("try:\n    r = mod.build_thing_request(x=1)\nexcept Exception:\n    r = None\n")

    def test_silent_when_unwrapped(self):
        assert not _detect("r = build_thing_request(x=1)\n")

    def test_silent_when_the_handler_reraises(self):
        assert not _detect("try:\n    r = build_thing_request(x=1)\nexcept Exception:\n    raise\n")

    def test_silent_when_an_earlier_arm_reraises(self):
        """The creative_helpers fix: order decides, and the first match wins."""
        assert not _detect(
            "try:\n"
            "    r = build_thing_request(x=1)\n"
            "except (AdCPSalesAgentError, ValidationError):\n"
            "    raise\n"
            "except Exception as e:\n"
            "    raise AdCPAdapterError() from e\n"
        )

    def test_silent_when_the_handler_cannot_match(self):
        assert not _detect("try:\n    r = build_thing_request(x=1)\nexcept KeyError:\n    r = None\n")

    def test_silent_for_a_non_builder_call(self):
        assert not _detect("try:\n    r = SomeRequest(x=1)\nexcept Exception:\n    r = None\n")

    def test_silent_when_the_call_is_in_the_handler(self):
        """A construction inside a handler is not wrapped BY that handler."""
        assert not _detect("try:\n    f()\nexcept Exception:\n    r = build_thing_request(x=1)\n")


class TestBuilderDiscovery:
    def test_finds_module_level_builders(self):
        tree = ast.parse("def build_thing_request(x):\n    return None\n")
        assert builder_names({"m.py": tree}) == {"build_thing_request"}

    def test_finds_the_underscored_form(self):
        tree = ast.parse("def UpdateMediaBuyRequest(x):\n    return None\n")
        assert builder_names({"m.py": tree}) == {"UpdateMediaBuyRequest"}

    def test_excludes_a_repository_method_of_the_same_shape(self):
        """``MediaBuyRepository.create_from_request`` persists; it builds no request."""
        tree = ast.parse("class MediaBuyRepository:\n    def create_from_request(self, req):\n        return None\n")
        assert builder_names({"m.py": tree}) == frozenset()

    def test_the_live_tree_has_the_builders(self):
        """Against src/ itself, so a rename that breaks discovery reddens here."""
        discovered = builder_names(_parsed_source_tree())

        assert "SyncCreativesRequest" in discovered
        assert "GetProductsRequest" in discovered
        assert "create_from_request" not in discovered
