"""Error-boundary behavior that has no other grader in this suite.

This module is deliberately narrow. Everything it once asserted about a code's
``message`` / ``recovery`` / ``suggestion`` is gone: all three are read-only
properties over ``CODE_TABLE`` (``src/core/errors/codes.py``), so pinning them
per exception class copies the pinned table into a second place instead of
grading production. What remains is the behavior that lives in *code* rather
than in the table, and that nothing else in the suite exercises:

- ``handle_tool_error`` — the body of ``@app.exception_handler(ToolError)``
  wired at ``src/app.py``. A typed ``AdCPToolError`` forwards its envelope and
  its ``status_code``; a plain ``ToolError`` is rebuilt from a synthetic error
  whose code is resolved through ``_CODE_BY_VALUE`` — falling back to
  ``INTERNAL_ERROR`` when the wire string is unrecognized — and whose HTTP
  status follows from that code's ``CODE_TABLE`` entry.
- ``AdCPSalesAgentError.status_code`` — a read-only function of the wire code,
  read from ``CODE_TABLE``. What is graded is that one code cannot be answered
  with two statuses, and that the answer does not move with the import set.
- ``extract_error_info`` on its NON-typed branches — the plain-``ToolError``
  argument shapes, the ``is_error_code`` heuristic that chooses between them,
  and the non-``ToolError`` fallthrough.
- ``_coerce_recovery`` — membership validation of a wire ``recovery`` string.
- ``adcp_error_for``'s type mapping (``ValueError`` → VALIDATION_ERROR / 400,
  ``PermissionError`` → PERMISSION_DENIED / 403) at each of the three
  boundaries that call it.
- ``_translate_to_tool_error``'s plain-``ToolError`` passthrough, which must
  stay ahead of the pre-converted ``typed`` short-circuit.
- The HTTP ``status_code`` roundtrip through REST. ``CODE_TABLE`` now carries
  the status, so the value itself is a table read — what is NOT a table read is
  whether it survives the handler stack and lands on the response, which is what
  driving each exception through REST grades.

The final section carries the translation paths origin/main graded here and this
branch had no equivalent for — a TYPED error crossing MCP and A2A, the A2A
dispatcher's two envelope branches, and the app actually having the ToolError
handler registered. They are kept, not dropped, but re-grounded: origin/main
wrote them against the retired constructor (a positional ``message``, a
``recovery=`` override) and against per-class statuses that no longer exist, so
every expectation there is derived from the code — ``_code`` and ``CODE_TABLE``
— rather than transcribed from the branch that wrote it. What is asserted is
that production PRODUCED the value, never what the pinned table says it means.
"""

from __future__ import annotations

import copy
import inspect
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.core.errors.codes import CODE_TABLE, Recovery
from src.core.exceptions import (
    AdCPAdapterError,
    AdCPAuthenticationError,
    AdCPAuthorizationError,
    AdCPBudgetExhaustedError,
    AdCPBudgetTooLowError,
    AdCPConflictError,
    AdCPGoneError,
    AdCPMediaBuyNotFoundError,
    AdCPNotFoundError,
    AdCPRateLimitError,
    AdCPSalesAgentError,
    AdCPServiceUnavailableError,
    AdCPValidationError,
    build_two_layer_error_envelope,
)
from src.core.tool_error_logging import (
    _CODE_BY_VALUE,
    AdCPToolError,
    _coerce_recovery,
    _translate_to_tool_error,
    extract_error_info,
    handle_tool_error,
    with_error_logging,
)
from tests.helpers import assert_envelope_shape
from tests.helpers.capture_wrapper_req import registry_impl


def _capabilities_response(side_effect: Exception):
    """Drive ``POST /api/v1/capabilities`` with ``side_effect`` raised inside the tool.

    The single patch site for every REST case below. The route is the thinnest
    endpoint in the app — one call, one ``model_dump`` — so what it grades is the
    exception-handler stack registered in ``src/app.py``, not the capabilities tool.
    """
    from starlette.testclient import TestClient

    from src.app import app
    from src.core.auth_context import _resolve_auth_dep

    # The route's identity dependency reads the tenant out of Postgres, and the
    # handler stack under test never looks at it. Overriding the dependency is
    # FastAPI's own seam for that, so no part of identity resolution has to be
    # faked to reach the exception handlers.
    app.dependency_overrides[_resolve_auth_dep] = lambda: None
    try:
        with registry_impl("get_adcp_capabilities", AsyncMock(side_effect=side_effect)):
            client = TestClient(app, raise_server_exceptions=False)
            return client.post("/api/v1/capabilities", json={})
    finally:
        app.dependency_overrides.pop(_resolve_auth_dep, None)


# ---------------------------------------------------------------------------
# handle_tool_error — the body of @app.exception_handler(ToolError)
# ---------------------------------------------------------------------------


class TestHandleToolError:
    """``handle_tool_error`` is the whole ToolError REST boundary.

    ``src/app.py`` registers ``@app.exception_handler(ToolError)`` and delegates
    to this function, so every branch here is live on the wire: an MCP-wrapped
    tool invoked from a REST route raises ``AdCPToolError`` and lands in the
    typed branch, while legacy code that raises ``ToolError`` directly lands in
    the reconstruction branch.
    """

    def test_adcp_tool_error_forwards_envelope_and_status(self):
        """The typed branch forwards the carried envelope and the source status verbatim."""
        source = AdCPMediaBuyNotFoundError()
        envelope = build_two_layer_error_envelope(source)

        response = handle_tool_error(AdCPToolError(envelope, status_code=source.status_code))

        assert response.status_code == source.status_code == 404
        assert json.loads(response.body) == envelope

    def test_adcp_tool_error_envelope_is_not_aliased_into_the_response(self):
        """The defensive ``dict()`` copy leaves the exception's own envelope untouched.

        The envelope dict is owned by the ``AdCPToolError`` instance, which the
        audit log and activity feed may still be holding. Handing it to the
        serializer by reference makes the response and the exception the same
        object; this pins that they are not.
        """
        source = AdCPAdapterError()
        tool_error = AdCPToolError(build_two_layer_error_envelope(source), status_code=source.status_code)
        before = copy.deepcopy(tool_error.envelope)

        response = handle_tool_error(tool_error)

        assert tool_error.envelope == before
        assert json.loads(response.body) == before

    def test_plain_tool_error_with_known_code_uses_the_status_map(self):
        """``ToolError("VALIDATION_ERROR", ...)`` resolves 400 through the code lookup.

        Legacy paths construct ``ToolError`` directly and carry no typed source
        that owns ``status_code``, so resolving the wire string against
        ``_CODE_BY_VALUE`` is the only thing standing between a 4xx condition and
        a 500 response.
        """
        response = handle_tool_error(ToolError("VALIDATION_ERROR", "missing required field"))

        assert response.status_code == 400
        assert_envelope_shape(json.loads(response.body), "VALIDATION_ERROR", recovery="correctable")

    def test_plain_tool_error_with_unknown_code_becomes_internal_error_500(self):
        """An unrecognized wire code resolves to INTERNAL_ERROR at 500 — a named fallback.

        The code is not passed through: an unvalidated string from a legacy
        raise site would reach the buyer as an error code the pinned table
        cannot classify.
        """
        response = handle_tool_error(ToolError("WEIRD_LEGACY_CODE", "what is this"))

        assert response.status_code == 500
        assert_envelope_shape(json.loads(response.body), "INTERNAL_ERROR", recovery="transient")

    def test_single_arg_tool_error_becomes_internal_error_500(self):
        """``ToolError("unstructured failure")`` carries no code at all, so it is a 500."""
        response = handle_tool_error(ToolError("unstructured failure"))

        assert response.status_code == 500
        assert_envelope_shape(json.loads(response.body), "INTERNAL_ERROR", recovery="transient")


class TestStatusIsAFunctionOfTheWireCode:
    """One wire code, one HTTP status — with nowhere left to say otherwise.

    ``status_code`` used to be a per-class ``_default_status_code`` slot, and the
    plain-``ToolError`` boundary reconstructed a code → status table by walking
    ``AdCPSalesAgentError.__subclasses__()`` and letting the highest status win.
    Both halves were wrong in the same way. A subclass could redeclare its
    ``_code`` and keep a status that belonged to its parent's code —
    ``SimulationError`` emitted INVALID_REQUEST carrying ``AdCPNotFoundError``'s
    404 — and because ``__subclasses__()`` only sees classes already imported,
    the table answered INVALID_REQUEST 400 or 404 depending on which modules the
    process had imported first (salesagent-pssfi).

    The status is now read from ``CODE_TABLE`` by code. These tests grade the
    two properties that fix bought: no code has two statuses, and no status
    depends on the import set.
    """

    def test_no_subclass_can_shadow_the_derived_status(self):
        """Every class in the hierarchy resolves ``status_code`` to the ONE property.

        The check is structural — ``getattr_static`` on the live class set, so a
        subclass added later is graded the moment it exists — rather than
        instantiating each class and comparing numbers: several classes take
        required constructor arguments (``SetupIncompleteError``), and a
        value-comparison test would be reporting on whichever of them a given
        worker's import set happened to have loaded. What must stay impossible is
        not a wrong number but a second place to put one, which is exactly what
        the old ``_default_status_code`` slot was: writable, inheritable, and
        free to belong to a different code than the class's own.
        """
        derived = AdCPSalesAgentError.__dict__["status_code"]
        walked = list(AdCPSalesAgentError.iter_concrete_subclasses())

        # Non-vacuity: an empty walk would satisfy every assertion below.
        assert walked, "no concrete AdCPSalesAgentError subclass was walked — the check is vacuous"

        shadowed = [
            f"  {cls.__name__} defines its own status_code ({inspect.getattr_static(cls, 'status_code')!r})"
            for cls in walked
            if inspect.getattr_static(cls, "status_code", derived) is not derived
        ]
        assert not shadowed, (
            "these classes override the code-derived HTTP status, so one wire code can again be "
            "answered two ways:\n" + "\n".join(shadowed)
        )

    def test_the_derived_status_is_the_table_entry(self):
        """The property reads ``CODE_TABLE``, so a class's code decides its status.

        Paired with the shadowing check above: that one says there is exactly one
        place the status can come from, this one says what that place is. Uses
        the base class with a named code, which is the only construction that
        can vary the code independently of the class.
        """
        error = AdCPSalesAgentError(error_code=AdCPAdapterError._code)

        assert error.status_code == CODE_TABLE[AdCPAdapterError._code].status == 503

    def test_two_classes_sharing_a_code_are_answered_identically(self):
        """SERVICE_UNAVAILABLE is emitted by four classes and answered one way.

        A real collision, not a constructed one: ``AdCPAdapterError`` declared
        502 and ``AdCPServiceUnavailableError`` 503 while both put
        SERVICE_UNAVAILABLE on the wire, so one failure told the buyer two
        different things. The buyer reads the code, so the code decides: 503.
        """
        assert AdCPAdapterError._code == AdCPServiceUnavailableError._code

        assert AdCPAdapterError().status_code == AdCPServiceUnavailableError().status_code == 503

    def test_simulation_error_is_answered_as_the_bad_request_it_is(self):
        """``SimulationError`` emits INVALID_REQUEST, so it is a 400 — not its parent's 404.

        Graded through REST rather than off the attribute: the 404 the buyer
        used to get came out of the response, and that is where it has to stop.
        """
        from src.core.strategy import SimulationError

        response = _capabilities_response(SimulationError())

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "INVALID_REQUEST", recovery="correctable")

    def test_status_does_not_move_with_the_import_set(self):
        """The same code resolves to the same status under a narrow and a wide import.

        This is the literal regression, so it is graded on the literal path: a
        plain ``ToolError("INVALID_REQUEST")`` through ``handle_tool_error``,
        which is what a legacy raise site puts in front of a buyer. It has to run
        out-of-process twice — the defect was that the answer depended on which
        modules had been imported, and a test sharing this session's interpreter
        has already imported everything. The wide leg imports
        ``src.core.strategy`` first, whose ``SimulationError`` used to raise the
        derived table's INVALID_REQUEST entry from 400 to 404; the narrow leg
        does not. They used to disagree.
        """
        resolve = (
            "from fastmcp.exceptions import ToolError;"
            "from src.core.tool_error_logging import handle_tool_error;"
            "print(handle_tool_error(ToolError('INVALID_REQUEST', 'bad')).status_code)"
        )
        legs = ("", "import src.core.strategy;")

        answers = [
            subprocess.run(
                [sys.executable, "-c", leg + resolve],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path(__file__).resolve().parents[2],
            ).stdout.strip()
            for leg in legs
        ]

        assert answers == ["400", "400"], f"INVALID_REQUEST resolved differently per import set: {answers}"

    def test_a_caller_cannot_name_a_status_that_contradicts_the_code(self):
        """There is no ``status_code=`` parameter, so no raise site can override it.

        The old constructor took one, which is how a boundary could hand a code
        one status while the class that owned the code declared another.
        """
        with pytest.raises(TypeError):
            AdCPValidationError(status_code=500)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# extract_error_info — the branches that do NOT read a typed exception
# ---------------------------------------------------------------------------


class TestExtractErrorInfoUntypedBranches:
    """``extract_error_info`` parses plain ``ToolError`` argument shapes.

    The typed branches read ``AdCPToolError.envelope`` / ``AdCPSalesAgentError``
    attributes and are graded wherever those errors cross a boundary. These
    branches exist only for code that raises ``ToolError`` directly, and the
    heuristic that routes between them is graded nowhere else.
    """

    def test_three_arg_tool_error_reads_recovery_from_the_third_arg(self):
        """``ToolError(code, message, recovery)`` yields all three."""
        code, message, recovery = extract_error_info(ToolError("SERVICE_UNAVAILABLE", "GAM down", "transient"))

        assert (code, message, recovery) == ("SERVICE_UNAVAILABLE", "GAM down", Recovery.TRANSIENT)

    def test_two_arg_tool_error_has_no_recovery(self):
        """``ToolError(code, message)`` yields ``None`` recovery — nothing to invent it from."""
        code, message, recovery = extract_error_info(ToolError("VALIDATION_ERROR", "bad field"))

        assert (code, message, recovery) == ("VALIDATION_ERROR", "bad field", None)

    def test_first_arg_that_is_not_code_shaped_falls_to_the_single_arg_branch(self):
        """The ``is_error_code`` heuristic rejects a first arg with spaces or lowercase.

        Without it, a two-arg ``ToolError`` whose first argument is prose would
        put that prose on the wire as an error code.
        """
        error = ToolError("not a code at all", "second arg")

        code, message, recovery = extract_error_info(error)

        assert code == "TOOL_ERROR"
        assert message == str(error)
        assert recovery is None

    def test_single_arg_tool_error_reports_tool_error(self):
        """``ToolError("message")`` has no code, so the placeholder TOOL_ERROR stands in."""
        code, message, recovery = extract_error_info(ToolError("something failed"))

        assert (code, message, recovery) == ("TOOL_ERROR", "something failed", None)

    def test_non_tool_error_reports_its_type_name(self):
        """An arbitrary exception reports its class name and ``str()``, with no recovery."""
        code, message, recovery = extract_error_info(RuntimeError("unexpected"))

        assert (code, message, recovery) == ("RuntimeError", "unexpected", None)


class TestCoerceRecovery:
    """``_coerce_recovery`` is the membership check on an untrusted recovery string.

    ``extract_error_info`` advertises ``Recovery | None``, but both the envelope
    branch and the legacy ToolError branch read a value typed ``str | None`` on
    the wire. The enum is the validator; anything outside it becomes ``None``
    rather than silently escaping the type contract.
    """

    def test_known_wire_string_becomes_the_enum_member(self):
        assert _coerce_recovery("transient") is Recovery.TRANSIENT

    def test_unknown_wire_string_becomes_none(self):
        assert _coerce_recovery("mostly_harmless") is None

    def test_non_string_becomes_none(self):
        assert _coerce_recovery(object()) is None

    def test_unknown_recovery_arg_reaches_none_through_extract_error_info(self):
        """The legacy ToolError path cannot smuggle an off-vocabulary recovery through."""
        code, _message, recovery = extract_error_info(ToolError("VALIDATION_ERROR", "bad", "mostly_harmless"))

        assert code == "VALIDATION_ERROR"
        assert recovery is None


# ---------------------------------------------------------------------------
# _translate_to_tool_error — passthrough ordering at the MCP boundary
# ---------------------------------------------------------------------------


class TestTranslateToToolErrorPassthrough:
    """A ``ToolError`` reaching the MCP translator is already in wire shape.

    The passthrough is keyed on the RAW error and must stay ahead of the
    ``typed`` short-circuit: a caller that pre-converted still hands over the
    original exception, and re-wrapping it would bury an envelope inside an
    envelope.
    """

    def test_plain_tool_error_is_reraised_unchanged(self):
        error = ToolError("EXISTING_CODE", "existing message")

        with pytest.raises(ToolError) as exc_info:
            _translate_to_tool_error(error)

        assert exc_info.value is error

    def test_passthrough_wins_over_a_supplied_typed_conversion(self):
        """Passing ``typed=`` does not divert a ToolError into the wrapping branch."""
        error = ToolError("EXISTING_CODE", "existing message")

        with pytest.raises(ToolError) as exc_info:
            _translate_to_tool_error(error, typed=AdCPValidationError())

        assert exc_info.value is error

    def test_adcp_tool_error_is_reraised_unchanged(self):
        """``AdCPToolError`` is a ``ToolError``, so it passes through rather than double-wrapping."""
        error = AdCPToolError(build_two_layer_error_envelope(AdCPValidationError()), status_code=400)

        with pytest.raises(AdCPToolError) as exc_info:
            _translate_to_tool_error(error)

        assert exc_info.value is error


# ---------------------------------------------------------------------------
# adcp_error_for's type mapping, at every boundary that calls it
# ---------------------------------------------------------------------------


class TestAdcpErrorForAtEveryBoundary:
    """``ValueError`` and ``PermissionError`` get the same wire shape on all three transports.

    ``adcp_error_for`` is the single source of truth for the mapping, but each
    boundary reaches it by its own route — MCP through
    ``_translate_to_tool_error``, REST through the registered exception
    handlers, A2A through ``_build_error_envelope`` — so a boundary that stops
    calling it fails here and only here.
    """

    def test_mcp_boundary_maps_value_error_to_validation_error(self):
        def failing_tool():
            raise ValueError("invalid input shape")

        with pytest.raises(ToolError) as exc_info:
            with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "VALIDATION_ERROR", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 400

    def test_mcp_boundary_maps_permission_error_to_permission_denied(self):
        def failing_tool():
            raise PermissionError("access denied")

        with pytest.raises(ToolError) as exc_info:
            with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "PERMISSION_DENIED", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_async_mcp_boundary_maps_value_error_to_validation_error(self):
        """The async wrapper shares ``_handle_tool_exception``, so it must land identically."""

        async def failing_tool():
            raise ValueError("invalid input shape")

        with pytest.raises(ToolError) as exc_info:
            await with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "VALIDATION_ERROR", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 400

    def test_rest_boundary_maps_value_error_to_400(self):
        """Without the REST ``ValueError`` handler this is a bare 500, unlike MCP and A2A."""
        response = _capabilities_response(ValueError("invalid input shape"))

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "VALIDATION_ERROR", recovery="correctable")

    def test_rest_boundary_maps_permission_error_to_403(self):
        response = _capabilities_response(PermissionError("access denied"))

        assert response.status_code == 403
        assert_envelope_shape(response.json(), "PERMISSION_DENIED", recovery="correctable")

    def test_a2a_boundary_maps_value_error_to_validation_error(self):
        """``_build_failed_skill_result`` is the A2A dispatcher's only failure carrier."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("get_products", ValueError("invalid input shape"))

        assert result["success"] is False
        assert result["skill"] == "get_products"
        assert_envelope_shape(result["error_envelope"], "VALIDATION_ERROR", recovery="correctable")

    def test_a2a_boundary_maps_permission_error_to_permission_denied(self):
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("get_products", PermissionError("access denied"))

        assert result["success"] is False
        assert_envelope_shape(result["error_envelope"], "PERMISSION_DENIED", recovery="correctable")


# ---------------------------------------------------------------------------
# HTTP status is the one graded value CODE_TABLE does not own
# ---------------------------------------------------------------------------


class TestRestStatusCodeRoundtrip:
    """Each typed class's ``status_code`` must survive the REST boundary.

    ``CODE_TABLE`` now owns the status alongside ``message``, ``recovery`` and
    ``suggestion``, so the expected numbers below are not an independent
    declaration of what each class means — that is graded by
    :class:`TestStatusIsAFunctionOfTheWireCode`. What these rows grade is the
    delivery: the status is a read-only property with no instance state behind
    it, and only driving the exception through the handler stack proves the
    property is what the response is built from.
    """

    @pytest.mark.parametrize(
        ("exc_cls", "expected_status"),
        [
            # The first three rows are origin/main's per-status REST methods
            # (400 / 404 / 409 / 503), folded into the parametrize rather than
            # kept as four near-identical methods — the duplication this table
            # exists to prevent.
            (AdCPValidationError, 400),
            (AdCPMediaBuyNotFoundError, 404),
            (AdCPNotFoundError, 404),
            (AdCPConflictError, 409),
            (AdCPGoneError, 410),
            (AdCPServiceUnavailableError, 503),
            (AdCPRateLimitError, 429),
            # 503, not the 502 this class used to declare: it emits
            # SERVICE_UNAVAILABLE, and the code owns the status.
            (AdCPAdapterError, 503),
        ],
        ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
    )
    def test_status_code_reaches_the_response(self, exc_cls: type[AdCPSalesAgentError], expected_status: int):
        """A new typed subclass is one parametrize row, not one method."""
        response = _capabilities_response(exc_cls())

        assert response.status_code == expected_status
        # Read back through the class rather than a transcribed literal: what is
        # graded is that THIS exception produced the response, not what the
        # pinned table says its code means.
        assert response.json()["errors"][0]["code"] == str(exc_cls._code)

    def test_budget_exhausted_reaches_422(self):
        """422 is carried by several classes; ``AdCPBudgetExhaustedError`` is the
        one whose recovery is ``terminal``, so it also pins that a terminal
        classification does not get downgraded on the way out.
        """
        response = _capabilities_response(AdCPBudgetExhaustedError())

        assert response.status_code == 422
        assert_envelope_shape(response.json(), "BUDGET_EXHAUSTED", recovery="terminal")


# ---------------------------------------------------------------------------
# Translation paths origin/main graded here, re-grounded on the merged code
#
# Everything below came in from origin/main (#1802 / #1858). Each one covers a
# boundary this branch's rewrite left ungraded, so none of them is dropped. What
# IS dropped from each is the part the merged production makes unstateable:
#   * a positional ``message`` and a ``recovery=`` override — the constructor is
#     keyword-only and message-free, and recovery is a read-only CODE_TABLE
#     property, so ``AdCPValidationError("bad field", recovery="terminal")`` is
#     now a TypeError, not a weaker assertion;
#   * per-class HTTP statuses — ``AdCPAdapterError`` answers 503, not the 502
#     origin/main asserted, because the status belongs to SERVICE_UNAVAILABLE;
#   * ``to_dict()`` and ``AdCPError("...")`` — the method is gone and the name is
#     an alias for the abstract base, which cannot be constructed without a code;
#   * ``ToolError("AUTH_REQUIRED")`` — that code is not in the merged CODE_TABLE.
#     PERMISSION_DENIED is the code the merged mapping actually emits for the
#     condition, and 403 is still the status being graded.
# Expectations are read off ``_code`` / ``CODE_TABLE`` wherever a literal would
# only be restating the table; the literals that remain (400/404/correctable/…)
# are the ones origin/main asserted and the merged table confirms.
# ---------------------------------------------------------------------------


def _synthetic_tool_error(source: AdCPSalesAgentError) -> AdCPToolError:
    """Wrap a typed error as the ``AdCPToolError`` a REST route catches defensively."""
    return AdCPToolError(build_two_layer_error_envelope(source), status_code=source.status_code)


class TestExtractErrorInfoTypedBranches:
    """``extract_error_info`` on the two branches that READ a typed error.

    :class:`TestExtractErrorInfoUntypedBranches` grades the plain-``ToolError``
    parsing; these are the branches ahead of it. origin/main graded them one
    method per class with the message each raise site passed in — a shape the
    message-free constructor deletes. Kept as one table over the same classes,
    with the expectation taken from the class's own ``_code`` and that code's
    table entry: what is graded is that the extractor reports the exception's
    derived values rather than inventing, defaulting, or dropping one.
    """

    _CLASSES = [
        AdCPValidationError,
        AdCPNotFoundError,
        AdCPAdapterError,
        AdCPGoneError,
        AdCPServiceUnavailableError,
        AdCPRateLimitError,
        AdCPConflictError,
        AdCPBudgetExhaustedError,
    ]

    @pytest.mark.parametrize("exc_cls", _CLASSES, ids=lambda cls: cls.__name__)
    def test_typed_error_reports_its_derived_code_message_and_recovery(
        self, exc_cls: type[AdCPSalesAgentError]
    ) -> None:
        error = exc_cls()
        entry = CODE_TABLE[exc_cls._code]

        code, message, recovery = extract_error_info(error)

        assert code == exc_cls._code
        assert message == entry.message
        assert recovery is entry.recovery

    def test_the_typed_table_is_not_empty(self):
        """Non-vacuity: an empty parametrize would make every row above pass by absence."""
        assert len(self._CLASSES) == 8

    def test_adcp_tool_error_is_read_from_its_envelope_not_its_args(self):
        """``AdCPToolError`` is checked BEFORE ``AdCPSalesAgentError`` and reads the envelope.

        It is a ``ToolError``, so if the envelope branch were removed the legacy
        arg-parsing branch would answer instead — with the placeholder
        ``TOOL_ERROR`` rather than the code the envelope carries.
        """
        source = AdCPMediaBuyNotFoundError()

        code, message, recovery = extract_error_info(_synthetic_tool_error(source))

        assert code == source.error_code == "MEDIA_BUY_NOT_FOUND"
        assert message == source.message
        assert recovery is source.recovery


class TestMCPBoundaryTypedErrorTranslation:
    """A TYPED error crossing ``with_error_logging`` becomes a wire envelope.

    :class:`TestAdcpErrorForAtEveryBoundary` grades the UNTYPED inputs at this
    boundary (``ValueError`` / ``PermissionError``), and
    :class:`TestRestStatusCodeRoundtrip` drives typed errors through REST. This
    is the one origin/main covered that neither of those does: the typed error
    that skips ``adcp_error_for``'s wrapping entirely, on the MCP transport.
    """

    @pytest.mark.parametrize(
        ("exc_cls", "expected_code", "expected_recovery"),
        [
            (AdCPValidationError, "VALIDATION_ERROR", "correctable"),
            (AdCPAdapterError, "SERVICE_UNAVAILABLE", "transient"),
            (AdCPBudgetExhaustedError, "BUDGET_EXHAUSTED", "terminal"),
        ],
        ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
    )
    def test_typed_error_becomes_a_tool_error_carrying_the_envelope(
        self, exc_cls: type[AdCPSalesAgentError], expected_code: str, expected_recovery: str
    ) -> None:
        """One row per recovery classification, so a collapse to a constant fails here."""

        def failing_tool():
            raise exc_cls()

        with pytest.raises(ToolError) as exc_info:
            with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, expected_code, check_mcp_tool_error=True, recovery=expected_recovery)
        assert exc_info.value.status_code == CODE_TABLE[exc_cls._code].status

    @pytest.mark.asyncio
    async def test_async_typed_error_lands_identically(self):
        """The async wrapper shares ``_handle_tool_exception``; it must not diverge."""

        async def failing_tool():
            raise AdCPValidationError()

        with pytest.raises(ToolError) as exc_info:
            await with_error_logging(failing_tool)()

        assert_envelope_shape(exc_info.value, "VALIDATION_ERROR", check_mcp_tool_error=True, recovery="correctable")
        assert exc_info.value.status_code == 400


class TestA2AExplicitSkillReraise:
    """``_handle_explicit_skill``'s except-clause: what reaches the outer dispatcher.

    Handler-internal, by design — the wire-level A2A envelope is graded in
    ``tests/integration/test_a2a_error_responses.py``. What is graded here is
    the branch that decides WHICH exception the dispatcher gets to wrap: a typed
    error is re-raised as the identical object, an untyped one is replaced by
    the ``adcp_error_for`` normalization, and an ``A2AError`` never enters the
    normalizing clause at all.

    ``get_products`` is used because it is in ``DISCOVERY_SKILLS``, so ``identity``
    may be ``None`` — which also keeps ``record_boundary_error`` off its
    tenant-scoped sinks, leaving this a unit test with no database.
    """

    @pytest.mark.asyncio
    async def test_typed_error_is_reraised_as_the_same_object(self):
        """``normalized is e`` takes the bare ``raise``: no re-wrap, no new instance.

        Identity, not equality: re-wrapping a typed error would rebuild it from
        ``adcp_error_for``, discarding the ``details`` / ``issues`` / ``field``
        the raise site attached and that the envelope carries to the buyer.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()
        raised = AdCPValidationError(field="packages[0].budget")

        async def mock_skill(skill_name, parameters, identity):
            raise raised

        with patch.object(handler, "_dispatch_skill", mock_skill):
            with pytest.raises(AdCPValidationError) as exc_info:
                await handler._handle_explicit_skill("get_products", {}, None)

        assert exc_info.value is raised
        assert exc_info.value.field == "packages[0].budget"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("raised", "expected_cls"),
        [
            (ValueError("invalid input shape"), AdCPValidationError),
            (PermissionError("access denied"), AdCPAuthorizationError),
        ],
        ids=["ValueError", "PermissionError"],
    )
    async def test_untyped_error_is_replaced_by_its_normalization(
        self, raised: Exception, expected_cls: type[AdCPSalesAgentError]
    ) -> None:
        """A2A applies the same ``adcp_error_for`` mapping MCP and REST do."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()

        async def mock_skill(skill_name, parameters, identity):
            raise raised

        with patch.object(handler, "_dispatch_skill", mock_skill):
            with pytest.raises(expected_cls) as exc_info:
                await handler._handle_explicit_skill("get_products", {}, None)

        assert exc_info.value.error_code == expected_cls._code
        assert exc_info.value.__cause__ is raised

    @pytest.mark.asyncio
    async def test_a2a_error_passes_through_untouched(self):
        """``except A2AError`` sits ahead of the normalizing clause and re-raises as-is."""
        from a2a.types import MethodNotFoundError

        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler()
        raised = MethodNotFoundError(message="not found")

        async def mock_skill(skill_name, parameters, identity):
            raise raised

        with patch.object(handler, "_dispatch_skill", mock_skill):
            with pytest.raises(MethodNotFoundError) as exc_info:
                await handler._handle_explicit_skill("get_products", {}, None)

        assert exc_info.value is raised


class TestA2ADispatcherFailedSkillResult:
    """``_build_failed_skill_result`` gives every failure ONE envelope shape.

    :class:`TestAdcpErrorForAtEveryBoundary` drives its untyped inputs; these are
    the typed branch, the arbitrary-exception fallthrough, and the parity between
    them. Storyboard runners read ``adcp_error.code`` and ``errors[0].code`` off
    whichever branch produced the failure, so a branch that populated one key
    differently would be invisible to every per-branch test and visible only
    here.
    """

    def test_typed_error_keeps_its_own_code(self):
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("get_products", AdCPValidationError())

        assert result["success"] is False
        assert result["skill"] == "get_products"
        assert_envelope_shape(result["error_envelope"], "VALIDATION_ERROR", recovery="correctable")

    def test_arbitrary_exception_becomes_internal_error(self):
        """A ``RuntimeError`` is answered INTERNAL_ERROR — and NOT with its own text.

        origin/main asserted the RuntimeError's message reached the buyer
        verbatim. That is the leak ``adcp_error_for`` closes deliberately: an
        untyped exception's string has no provenance guarantee, so the code's
        table sentence is what goes on the wire and the original is logged
        server-side. Asserting the absence is the whole point of the row.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        result = AdCPRequestHandler._build_failed_skill_result("get_products", RuntimeError("db://user:pw@host"))

        envelope = result["error_envelope"]
        assert result["success"] is False
        # The CLASSIFICATION, which a change to adcp_error_for could break. The absence
        # check that stood here -- "db://user:pw@host" not in the dump -- could not: message
        # is a read-only property returning CODE_TABLE[code].message and __init__ takes no
        # message parameter, so the raw text has no path into buyer-facing text. It asserted
        # that a string this test invented is missing from a table this test did not write.
        assert_envelope_shape(envelope, "INTERNAL_ERROR", recovery="transient")

    def test_both_branches_produce_the_same_envelope_shape(self):
        """Same keys, and every key both branches share is populated in both.

        Key-set equality alone would pass if one branch nulled a value the other
        fills, which is exactly how a ``recovery`` regression would hide.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        typed = AdCPRequestHandler._build_failed_skill_result("s", AdCPValidationError())
        untyped = AdCPRequestHandler._build_failed_skill_result("s", RuntimeError("boom"))

        assert set(typed) == set(untyped)
        assert set(typed["error_envelope"]) == set(untyped["error_envelope"])
        assert set(typed["error_envelope"]["adcp_error"]) == set(untyped["error_envelope"]["adcp_error"])
        assert set(typed["error_envelope"]["errors"][0]) == set(untyped["error_envelope"]["errors"][0])

        for branch in (typed, untyped):
            envelope = branch["error_envelope"]
            assert envelope["adcp_error"]["code"]
            assert envelope["adcp_error"]["recovery"]
            assert envelope["errors"][0]["code"]
            assert envelope["errors"][0]["message"]
            assert envelope["errors"][0]["recovery"]


class TestHandleToolErrorStatusForTypedSources:
    """A ``ToolError`` built from a typed error answers with THAT error's status.

    ``TestHandleToolError`` grades the two branches; this grades the range the
    typed branch has to carry. Before the source's ``status_code`` was forwarded,
    every defensively-caught ``ToolError`` was a 500, so a buyer's 4xx came back
    as a server fault. One row per status band, so a collapse to any single
    number fails.
    """

    @pytest.mark.parametrize(
        ("source_cls", "expected_status"),
        [
            (AdCPValidationError, 400),
            (AdCPAuthenticationError, 401),
            (AdCPAuthorizationError, 403),
            (AdCPMediaBuyNotFoundError, 404),
            (AdCPBudgetTooLowError, 422),
            # 503: origin/main's row said 502, which was this class's old
            # per-class declaration. It emits SERVICE_UNAVAILABLE, so 503.
            (AdCPAdapterError, 503),
        ],
        ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
    )
    def test_source_status_is_forwarded(self, source_cls: type[AdCPSalesAgentError], expected_status: int) -> None:
        source = source_cls()
        response = handle_tool_error(_synthetic_tool_error(source))

        assert response.status_code == expected_status
        assert json.loads(response.body)["errors"][0]["code"] == str(source_cls._code)

    @pytest.mark.parametrize(
        ("wire_code", "expected_status"),
        [
            ("VALIDATION_ERROR", 400),
            # origin/main's row was ToolError("AUTH_REQUIRED") -> 403. That code
            # is not in the merged CODE_TABLE; PERMISSION_DENIED is the one the
            # merged mapping emits for a refused caller, and 403 is unchanged.
            ("PERMISSION_DENIED", 403),
            ("MEDIA_BUY_NOT_FOUND", 404),
            ("SERVICE_UNAVAILABLE", 503),
        ],
    )
    def test_plain_tool_error_resolves_its_wire_code_to_a_status(self, wire_code: str, expected_status: int) -> None:
        """The legacy raise site carries no typed source, so the code is all there is.

        Without the lookup every one of these is a 500 — the fallback is only
        correct for a code the table does not know.
        """
        response = handle_tool_error(ToolError(wire_code, "legacy raise site"))

        assert response.status_code == expected_status
        assert json.loads(response.body)["errors"][0]["code"] == wire_code


class TestSynthesizedRestEnvelopeFollowsItsCode:
    """A rebuilt envelope's recovery comes from the CODE, never from the wire input.

    A plain ``ToolError`` can carry a third positional ``recovery`` that
    CONTRADICTS its code, and ``extract_error_info`` still reports that value for
    its logging consumers. The rebuild must not use it: the buyer decodes an
    unknown code by reading ``recovery``, so an envelope pairing
    SERVICE_UNAVAILABLE with ``terminal`` tells them not to retry something the
    pin classifies as retryable.

    The contradiction is what makes this a grader — with a two-arg ``ToolError``
    the extractor returns ``None`` and both answers coincide, so the test could
    not fail.
    """

    def test_a_contradicting_recovery_on_the_wire_is_not_propagated(self):
        response = handle_tool_error(ToolError("SERVICE_UNAVAILABLE", "upstream is down", "terminal"))

        body = json.loads(response.body)
        # Read back through the table for the code the fallback actually
        # resolved, rather than restating a literal: this fails if the envelope
        # ever starts sourcing recovery from anywhere but the code again.
        expected = str(CODE_TABLE[_CODE_BY_VALUE[body["adcp_error"]["code"]]].recovery)

        assert expected == "transient", "the fixture no longer contradicts the code; it grades nothing"
        assert_envelope_shape(body, "SERVICE_UNAVAILABLE", recovery=expected)
        assert response.status_code == 503


class TestToolErrorHandlerIsRegisteredOnTheApp:
    """``handle_tool_error`` is only reachable because ``src/app.py`` registers it.

    Every other test in this module calls the function directly. This is the one
    that fails if the ``@app.exception_handler(ToolError)`` registration is
    dropped — at which point a ``ToolError`` escaping a route becomes an
    unhandled 500 with no envelope at all, and no direct-call test notices.
    """

    def test_adcp_tool_error_reaches_the_wire_through_the_app(self):
        source = AdCPMediaBuyNotFoundError()

        response = _capabilities_response(_synthetic_tool_error(source))

        assert response.status_code == 404
        assert_envelope_shape(response.json(), "MEDIA_BUY_NOT_FOUND", recovery="correctable")

    def test_plain_tool_error_reaches_the_wire_through_the_app(self):
        response = _capabilities_response(ToolError("VALIDATION_ERROR", "missing field"))

        assert response.status_code == 400
        assert_envelope_shape(response.json(), "VALIDATION_ERROR", recovery="correctable")

    def test_request_validation_error_is_not_shadowed_by_the_value_error_handler(self):
        """FastAPI's own 422 body for a malformed request must survive our handler.

        The REST boundary registers a ``ValueError`` handler so an
        application-raised ``ValueError`` gets the AdCP envelope instead of a
        bare 500. If ``RequestValidationError`` were a ``ValueError``, that
        handler would swallow FastAPI's request-body 422 as well — a structural
        fact about the framework, so it is pinned structurally.
        """
        from fastapi.exceptions import RequestValidationError

        assert not issubclass(RequestValidationError, ValueError)
