"""The advertised MCP shape is DERIVED from the SDK request DTO, and stays honest.

Three properties, each of which failed at least once while this was being built:

1. The derivation actually reaches FastMCP. Setting ``__signature__`` alone looks right
   under ``inspect.signature`` and changes nothing, because FastMCP resolves types with
   ``typing.get_type_hints`` (which reads ``__annotations__``).
2. Advertised == accepted. The advertised type is the DTO's, so where this agent accepts
   more than the library (the brand shorthand) the widening is declared ON THE MODEL. If the
   model claims less than the tool implements, FastMCP rejects valid input at the boundary
   before any tool code runs -- that regression happened twice here, 18 scenarios then 16.
3. A DTO field the tool does not accept is never advertised -- with no hand-maintained
   list of exclusions. Absence from the signature IS the statement.
4. An INTERNAL field is never advertised. ``exclude=True`` governed serialization only for a
   long time and the announcement read straight past it, so a field marked internal was still
   published as a request parameter -- on MCP and, through the same DTO, in the REST body.
"""

from __future__ import annotations

import pytest
from adcp.types import ListAccountsRequest as _LibraryListAccountsRequest
from pydantic import BaseModel, Field

from src.core.schemas import GetProductsRequest, UpdatePerformanceIndexRequest
from src.core.tools._announced_shape import (
    derived_signature,
    request_model_for,
)

_LANE_D_TOOLS = ("get_adcp_capabilities", "get_products", "list_creative_formats", "list_creatives")


def _tool(name: str):
    from src.core.tools import capabilities, creative_formats, creatives, products

    return {
        "get_adcp_capabilities": capabilities.get_adcp_capabilities,
        "get_products": products.get_products,
        "list_creative_formats": creative_formats.list_creative_formats,
        "list_creatives": creatives.list_creatives,
    }[name]


#: Every tool whose wrapper builds a request, i.e. every tool the derivation applies to.
_DERIVED_TOOLS = (
    "get_adcp_capabilities",
    "get_products",
    "list_creative_formats",
    "list_creatives",
    "create_media_buy",
    "get_media_buy_delivery",
    "get_media_buys",
    "list_accounts",
    "sync_accounts",
    "update_media_buy",
    "update_performance_index",
)


def _resolve_tool(name: str):
    import sys

    for module in list(sys.modules.values()):
        candidate = getattr(module, name, None)
        if callable(candidate) and getattr(candidate, "__name__", None) == name:
            if request_model_for(candidate) is not None:
                return candidate
    return None


@pytest.mark.parametrize("tool_name", _LANE_D_TOOLS)
def test_every_lane_d_tool_resolves_its_request_dto(tool_name: str) -> None:
    """The tool -> DTO edge is read from the builder the wrapper calls, via bytecode."""
    assert request_model_for(_tool(tool_name)) is not None, (
        f"{tool_name} no longer resolves to a request DTO -- the announced shape silently "
        "falls back to whatever the signature happens to say"
    )


class TestLiveRegistryActuallyCarriesTheDerivation:
    """Graded against the LIVE advertised schema, not against the helpers.

    The rest of this module tests ``derived_signature`` / ``_would_narrow`` directly, which
    a mutation review showed is not enough: turning ``apply_dto_announced_shape`` into a
    no-op, reverting the scope gate, or deleting the never-narrow guard reddened NOTHING,
    because nothing here read what FastMCP actually publishes. These do.

    The oracle is a field whose advertised form genuinely DIFFERS with the derivation on
    and off -- the DTO's description reaches the wire only when it ran.
    """

    @staticmethod
    async def _advertised(tool_name: str) -> dict:
        from src.core import main

        return (await main.mcp.get_tool(tool_name)).parameters["properties"]

    @pytest.mark.asyncio
    async def test_derivation_is_live_for_a_scoped_tool(self) -> None:
        """get_adcp_capabilities.adcp_version must carry the DTO's description.

        Undecorated the wrapper says "Requested AdCP spec version"; the DTO says
        "Release-precision AdCP version ...". Only the derivation puts the DTO's text on
        the wire, so this reddens the moment the mechanism stops running.
        """
        from adcp.types import GetAdcpCapabilitiesRequest

        advertised = await self._advertised("get_adcp_capabilities")
        expected = GetAdcpCapabilitiesRequest.model_fields["adcp_version"].description
        assert expected, "the DTO field lost its description -- pick another oracle field"
        assert advertised["adcp_version"].get("description") == expected, (
            "the advertised adcp_version description is not the DTO's. The derivation is "
            "not reaching the live registry -- check apply_dto_announced_shape is called "
            "in _register_tool and that it sets __annotations__ as well as __signature__."
        )


class TestNarrowingIsGraded:
    """The `accepted` argument to select_request_fields must actually narrow.

    A mutation review found that making select_request_fields IGNORE `accepted` reddened
    nothing in the whole suite: uc018 and uc019 were byte-identical to baseline. The
    narrowing is what stops a callee being handed a DTO field it cannot take -- the
    difference between a dropped key and a TypeError 500 on a spec-conformant payload -- so
    it needs a grader that fails when it stops happening.
    """

    def test_accepted_narrows_the_selection(self) -> None:
        """Fields outside `accepted` must not be forwarded."""
        from src.core.schema_helpers import select_request_fields
        from src.core.schemas import ListCreativesRequest

        bag = {"filters": {"tags": ["q1"]}, "sort": {"direction": "asc"}, "include_assignments": True}
        wide = select_request_fields(ListCreativesRequest, bag, None)
        narrow = select_request_fields(ListCreativesRequest, bag, {"filters"})

        assert set(wide) == {"filters", "sort", "include_assignments"}, (
            f"unnarrowed selection should carry every DTO field present in the bag; got {sorted(wide)}"
        )
        assert set(narrow) == {"filters"}, (
            f"`accepted` must remove what the callee cannot take; got {sorted(narrow)}. If this "
            f"equals the unnarrowed set, select_request_fields is ignoring its third argument "
            f"and every converted call site is handing its callee unaccepted kwargs."
        )

    def test_a_real_call_site_would_break_without_narrowing(self) -> None:
        """The concrete case: GetProductsRequest takes 5 of GetProductsRequest's 20.

        Splatting the unnarrowed selection into it raises TypeError -- which is precisely the
        500-on-a-valid-payload the `accepted` argument exists to prevent. Proven by calling
        it, not by reading the signature.
        """

        import pytest

        from src.core.schema_helpers import (
            accepted_kwargs,
            select_request_fields,
        )

        bag = {"brief": "video", "catalog": {"id": "c1"}, "refine": True}
        # None is the explicit "unbounded" answer -- the only way to get the wide form now
        # that `accepted` is required. That it must be SPELLED is the fix for this defect
        # class: seven of ten production sites had reached the wide form by omission.
        unnarrowed = select_request_fields(GetProductsRequest, bag, None)
        assert "catalog" in unnarrowed, "fixture stale: catalog must be a DTO field for this to grade"
        with pytest.raises(TypeError):
            GetProductsRequest(**unnarrowed)

        narrowed = select_request_fields(GetProductsRequest, bag, accepted_kwargs(GetProductsRequest))
        GetProductsRequest(**narrowed)  # must not raise


class TestDerivationIsAPureFunction:
    """The derivation is ``(signature, DTO) -> signature``: no I/O, no registry, no DB.

    Graded here with a FIXTURE model and a LITERAL expectation, which is the whole point.
    The tests these replace computed their expectation as ``set(model.model_fields) &
    accepted`` -- exactly what production computes -- so both sides moved together and the
    assertion was blind to the rule being wrong; it graded drift, not correctness. A mutation
    review confirmed it: disabling ``_is_injected`` left them fully green.

    Writing the expected parameters out by hand is what makes them able to fail. The fixture
    deliberately contains BOTH exclusion directions, because the rule is an intersection and
    a test that exercises only one half cannot tell an intersection from a union.
    """

    @staticmethod
    def _fixture():
        from pydantic import BaseModel, Field

        class FixtureRequest(BaseModel):
            alpha: str | None = Field(default=None, description="described by the DTO")
            beta: int | None = None
            gamma_unimplemented: bool | None = None  # DTO declares it; the tool does not take it

        from fastmcp.server.context import Context

        def fixture_tool(
            alpha: str = "",
            beta: int = 0,
            legacy_not_in_dto: str = "",
            ctx: Context | None = None,
        ):
            """A tool with one spec param the DTO lacks and one the DTO has."""

        return fixture_tool, FixtureRequest

    def test_derived_parameters_are_exactly_the_intersection(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert sorted(p for p in sig.parameters if p != "ctx") == ["alpha", "beta"], (
            "expected exactly the DTO fields the tool accepts. "
            "gamma_unimplemented is declared by the DTO but not taken by the tool; "
            "legacy_not_in_dto is taken by the tool but not declared by the DTO."
        )

    def test_a_dto_field_the_tool_cannot_take_is_not_derived(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert "gamma_unimplemented" not in sig.parameters, (
            "advertising a field the implementation does not accept offers buyers an input "
            "whose only outcome is an error"
        )

    def test_a_tool_parameter_the_dto_does_not_declare_is_not_derived(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert "legacy_not_in_dto" not in sig.parameters, (
            "a parameter outside the spec must not be advertised; absence from the DTO is "
            "what retires it, with no list of legacy names to maintain"
        )

    def test_the_injected_context_parameter_survives(self) -> None:
        """ctx is not a DTO field but must stay, or FastMCP has nothing to inject.

        Dropping it is not a cosmetic bug: it broke authentication on 79 tests in this lane
        (every call arrived without identity -> AUTH_MISSING) because the annotation arrived
        as a STRING under postponed annotations and the type test missed it.
        """
        fixture_tool, FixtureRequest = self._fixture()
        assert "ctx" in derived_signature(fixture_tool, FixtureRequest).parameters

    def test_the_dto_supplies_the_description(self) -> None:
        fixture_tool, FixtureRequest = self._fixture()
        sig = derived_signature(fixture_tool, FixtureRequest)
        assert "described by the DTO" in str(sig.parameters["alpha"].annotation)


class TestAdvertisedSchemaIsPublished:
    """What FastMCP actually publishes -- a request/response concern, not a pure one.

    Separated from the derivation tests above on purpose: this needs the live registry, so it
    can only assert what a buyer would really receive. Expectations are LITERAL for one tool,
    not recomputed from the model.
    """

    @pytest.mark.asyncio
    async def test_get_adcp_capabilities_publishes_exactly_its_five_fields(self) -> None:
        from src.core import main

        advertised = set((await main.mcp.get_tool("get_adcp_capabilities")).parameters["properties"])
        assert advertised == {"protocols", "context", "adcp_version", "adcp_major_version", "ext"}, (
            f"published shape drifted: {sorted(advertised)}. This is the buyer-visible schema, "
            f"written out rather than recomputed, so it fails when the shape moves for any reason."
        )


class TestAdvertisedTypesAreAccepted:
    """Every TYPE we advertise must be one the implementation actually takes.

    The lane's rule -- advertise (DTO fields) INTERSECT (impl arguments) -- was enforced in the
    NAME dimension only. Names are not the whole shape: adopting the DTO also adopts the DTO's
    TYPES, and a type can widen while the implementation stays narrow. That direction had no
    grader, and it put a live defect in the tree.

    The original instance was update_media_buy.budget, which advertised
    ``Budget | number | null`` while its builder declared ``float | None`` and called
    ``float(budget)`` -- an untyped 500 on the payload our own schema documented. Those cases
    are gone with the field: AdCP 3.1.1 defines no top-level budget on update_media_buy, so
    the field was removed rather than repaired. The rule is now graded on
    update_performance_index.performance_data, a field that does exist.

    Graded behaviorally -- construct the advertised type, call the real builder -- rather than
    by comparing annotations, because an annotation comparison cannot distinguish a real defect
    from a loose one (``typing.Any`` accepts everything; bare ``list`` differs from
    ``list[str]`` only on paper). Of 23 statically-suspicious sites, exactly one broke.
    """

    def test_the_typed_performance_entries_we_advertise_are_accepted(self) -> None:
        """The SECOND instance of this class, which the budget fix alone did not settle.

        update_performance_index advertises performance_data as list[ProductPerformance]
        (the DTO's type), so FastMCP validates the buyer's JSON into MODELS before the call.
        The builder then did ``ProductPerformance(**perf)`` and raised "argument after **
        must be a mapping, not ProductPerformance" -- an untyped 500 on MCP, while A2A and
        REST passed because they hand the builder raw dicts.

        Both this and budget were named in a 27-entry type-divergence ledger. The ledger was
        deleted rather than worked through, which was right -- a type mismatch is a bug, not
        something to record -- but only the entry that had a test got fixed. This is that
        test for the other entry.
        """
        from src.core.schemas import ProductPerformance

        req = UpdatePerformanceIndexRequest("mb_1", [ProductPerformance(product_id="p1", performance_index=1.2)])

        assert len(req.performance_data) == 1
        assert req.performance_data[0].product_id == "p1"

    def test_the_dict_performance_entries_still_work(self) -> None:
        """A2A and REST hand the builder wire dicts; the fix must read both shapes."""

        req = UpdatePerformanceIndexRequest("mb_1", [{"product_id": "p1", "performance_index": 1.2}])

        assert req.performance_data[0].product_id == "p1"

    def test_a_plain_callee_reports_its_keyword_names(self) -> None:
        from src.core.schema_helpers import accepted_kwargs

        def callee(alpha, beta, *, gamma=None): ...

        assert accepted_kwargs(callee) == frozenset({"alpha", "beta", "gamma"})

    def test_var_keyword_means_unbounded_not_the_literal_name(self) -> None:
        """A **kwargs callee accepts every field -- not a field called "kwargs"."""
        from src.core.schema_helpers import accepted_kwargs

        def callee(alpha, **kwargs): ...

        assert accepted_kwargs(callee) is None

    def test_a_patched_mock_accepts_anything_rather_than_nothing(self) -> None:
        """The hazard that used to force import-time capture, now handled by the rule.

        Tests patch transport-module attributes with Mocks, whose signature is
        ``(*args, **kwargs)``. Read as a name list that is empty, a call-time narrowing
        silently dropped EVERY field the buyer sent -- so the two handlers that read at call
        time needed frozensets captured at import, and the other two sites did not have them.
        Reading it as unbounded makes the timing irrelevant.
        """
        from unittest.mock import Mock

        from src.core.schema_helpers import accepted_kwargs

        assert accepted_kwargs(Mock()) is None, (
            "a Mock reported as a bounded empty set would make every narrowed forwarding site "
            "drop the entire payload under test, silently and green"
        )

    def test_selection_through_a_mock_keeps_the_payload(self) -> None:
        """The consequence, at the seam rather than on the primitive."""
        from unittest.mock import Mock

        from src.core.schema_helpers import accepted_kwargs, select_request_fields
        from src.core.schemas import ListCreativesRequest

        bag = {"filters": {"tags": ["q1"]}, "include_assignments": True}
        selected = select_request_fields(ListCreativesRequest, bag, accepted_kwargs(Mock()))

        assert set(selected) == {"filters", "include_assignments"}


class TestARequiredFieldCannotGoUnannounced:
    """A tool may not announce a DTO whose REQUIRED fields it does not declare.

    Such a tool is not merely under-specified, it is unusable: the wrapper never receives the
    field, so the builder cannot populate it and EVERY call raises ValidationError. The
    failure is loud but late -- it lands on a buyer's request, at call time, for a defect that
    is one line at author time.

    All 16 tools were measured clean when this refusal was added, which is the moment to fix
    it in place: the check costs nothing today and the next tool cannot introduce the state.
    Refusal rather than an allowlist, matching _register_tool's treatment of an unresolvable
    DTO -- a list of known-broken tools records a violation; refusing makes it unreachable.
    """

    def test_registration_refuses_a_wrapper_missing_a_required_field(self) -> None:
        import pytest

        from src.core.tools._announced_shape import apply_dto_announced_shape

        def target(): ...

        with pytest.raises(RuntimeError, match="media_buy_id"):
            apply_dto_announced_shape(target, _fixture_wrapper_that_forgot_it)

    def test_a_wrapper_that_declares_it_registers_normally(self) -> None:
        """The refusal must be specific to the defect, not merely strict."""
        from src.core.tools._announced_shape import apply_dto_announced_shape

        def target(): ...

        assert apply_dto_announced_shape(target, _fixture_wrapper_that_declares_it) is True
        assert "media_buy_id" in target.__signature__.parameters

    def test_every_registered_tool_announces_its_required_fields(self) -> None:
        """The live statement, not a fixture: importing main registers all 16 tools.

        Kept as its own test because the two above grade the RULE on a fixture, and this
        grades the TREE. A rule that holds on a fixture while the tree violates it is the
        failure mode a guard-with-an-allowlist would have hidden.
        """
        from src.core import main

        assert main.mcp is not None


class TestDroppedFieldsAreReported:
    """A field the seam does not carry is logged, never dropped in silence.

    Dropping is the right BEHAVIOUR: production runs extra="ignore" so a buyer on a newer
    spec version is tolerated rather than refused (critical pattern #7). Silence is not.
    A buyer who sends a filter that is quietly not applied gets 200 OK and a result set that
    answers a different question than the one asked -- which is how a single parametrized
    test came to fail in three different ways across transports: VALIDATION_ERROR on MCP,
    silently-ignored-with-200 on A2A and REST.
    """

    def test_an_undefined_field_is_logged(self, caplog) -> None:
        import logging

        from src.core.schema_helpers import accepted_kwargs, select_request_fields
        from src.core.schemas import ListCreativesRequest

        with caplog.at_level(logging.INFO, logger="src.core.schema_helpers"):
            selected = select_request_fields(
                ListCreativesRequest,
                {"status": "processing", "include_assignments": True},
                accepted_kwargs(ListCreativesRequest),
            )

        assert "status" not in selected, "a field the DTO does not define must not be forwarded"
        assert any("status" in r.getMessage() for r in caplog.records), (
            "dropping it silently is the defect; the operator must be able to see that a "
            "buyer sent something we did not honour"
        )

    def test_a_carried_field_is_not_logged_as_dropped(self, caplog) -> None:
        """The report must be specific, or it is noise that gets filtered out."""
        import logging

        from src.core.schema_helpers import accepted_kwargs, select_request_fields
        from src.core.schemas import ListCreativesRequest

        with caplog.at_level(logging.INFO, logger="src.core.schema_helpers"):
            select_request_fields(
                ListCreativesRequest, {"include_assignments": True}, accepted_kwargs(ListCreativesRequest)
            )

        assert not any("ignoring" in r.getMessage() for r in caplog.records)


# ── Fixtures for TestARequiredFieldCannotGoUnannounced ────────────────────────
#
# MODULE-LEVEL on purpose. apply_dto_announced_shape no longer accepts an explicit dto=
# (that escape hatch was deleted with its last caller), so a fixture supplies its model the
# way production does: the wrapper CALLS a builder, and builder_for resolves that builder
# from the wrapper's bytecode and looks it up in the wrapper's module. Locals inside a test
# method are invisible to that lookup, so these have to live here -- and grading through the
# real resolution path is the stronger test anyway.


class _FixtureNeedsAnId(BaseModel):
    media_buy_id: str  # required
    note: str | None = None


def _build_fixture_request(media_buy_id: str = "", note: str | None = None) -> _FixtureNeedsAnId:
    return _FixtureNeedsAnId(media_buy_id=media_buy_id, note=note)


def _fixture_wrapper_that_forgot_it(note: str | None = None):
    """Declares the optional field but not the required one."""
    return _build_fixture_request(note=note)


def _fixture_wrapper_that_declares_it(media_buy_id: str = "", note: str | None = None):
    return _build_fixture_request(media_buy_id=media_buy_id, note=note)


class TestAnInternalFieldIsNeverAnnounced:
    """``exclude=True`` means the buyer never sees it, in BOTH directions.

    Until the announcement honoured it, ``exclude=`` said "never reaches a buyer" about
    SERIALIZATION only, so "mark it internal" was advice a reader could follow and still
    publish the field as a request parameter. The four live DTO fields that used to be in
    this state are gone: the marker is no longer how an internal field is kept off a buyer
    surface (docs/design/one-tool-registry.md), and no registered request DTO declares one
    any more --
    that. This test therefore fires against a fixture, which is what keeps it honest: the
    derivation must honour the marker whether or not the tree currently uses it.

    There is deliberately no companion test refusing an ADDED field that IS advertised. The
    added set is derived (``set(model_fields) - library_declared_fields(model)``), so
    declaring the field on the subclass IS the statement that we carry it, and a refusal
    reading that same derivation could never fire. See docs/design/one-tool-registry.md.
    """

    def test_an_internal_field_registers_and_is_not_announced(self) -> None:
        """``exclude=True`` means the buyer never sees it -- in BOTH directions.

        Before this, exclude= governed serialization only and the announcement read straight
        past it, so "mark it internal" was advice a reader could follow and still publish the
        field.
        """
        from src.core.tools._announced_shape import apply_dto_announced_shape

        def target(): ...

        assert apply_dto_announced_shape(target, _fixture_wrapper_with_an_internal_field) is True
        assert "local_only_flag" not in target.__signature__.parameters
        assert "status" in target.__signature__.parameters, "the spec fields must survive"

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "list_accounts.idempotency_key was RESTORED deliberately and temporarily "
            "(salesagent-prkv.65): the UC-011 tolerance scenario builds the model in-process, "
            "so without the field it cannot construct a request and grades nothing. This "
            "assertion is CORRECT and unweakened -- strict=True means it fails the build the "
            "moment the field is removed, forcing this marker to be deleted with it."
        ),
    )
    async def test_a_read_tool_does_not_advertise_an_idempotency_key(self) -> None:
        """The field this ticket removed, pinned through the LIVE registry.

        ``list_accounts`` advertised ``idempotency_key`` and its own comment explained why it
        should not have: account/list-accounts-request.json declares no such property and
        declares ``additionalProperties: true``, so the duty is TOLERANCE -- which the
        boundary already discharges (critical pattern #7, production runs ``extra="ignore"``)
        -- not a declared field. A read is idempotent by construction, so there is no
        at-most-once guarantee for a key to carry.

        Asserted on the registered tool rather than the model, because declaring the field is
        only half of what published it: the wrapper parameter is the other half, and removing
        one without the other leaves it advertised. ``sync_accounts`` is the control -- the
        spec DOES declare the property there, because a sync mutates.
        """
        from src.core import main

        assert "idempotency_key" not in (await main.mcp.get_tool("list_accounts")).parameters["properties"]
        assert "idempotency_key" in (await main.mcp.get_tool("sync_accounts")).parameters["properties"], (
            "the mutation tool must keep the key -- a blanket removal is not the fix"
        )


class TestRestDropsInternalFieldsToo:
    """REST derives its body from the same DTO, so it must read ``exclude=`` the same way.

    A split here is the single-transport hole every derivation in this codebase exists to
    close: MCP would stop advertising an internal field while the REST body went on accepting
    it in the payload.
    """

    def test_a_derived_body_omits_an_internal_field(self) -> None:
        from src.routes._derived_body import derived_body_model

        body = derived_body_model("FixtureBody", _FixtureWithAnInternalField, _fixture_impl_taking_everything)

        assert "local_only_flag" not in body.model_fields
        assert "status" in body.model_fields, "the spec fields must survive"


# ── Fixtures for the two classes above ───────────────────────────────────────
#
# MODULE-LEVEL for the same reason as the fixtures above: builder_for resolves the builder
# from the wrapper's BYTECODE and looks the name up in the wrapper's module, so a builder
# defined inside a test method is invisible to it.
#
# The base is the real library ListAccountsRequest rather than a hand-made stand-in, because
# an internal field has to sit on top of a real spec shape for its exclusion to mean anything
# -- a stand-in in this module would make the fixture wholly local and the tests vacuous.


class _FixtureWithAnInternalField(_LibraryListAccountsRequest):
    local_only_flag: bool | None = Field(default=None, exclude=True)


def _build_internal_request(
    status: str | None = None, local_only_flag: bool | None = None
) -> _FixtureWithAnInternalField:
    return _FixtureWithAnInternalField(status=status, local_only_flag=local_only_flag)


def _fixture_wrapper_with_an_internal_field(status: str | None = None, local_only_flag: bool | None = None):
    return _build_internal_request(status=status, local_only_flag=local_only_flag)


def _fixture_impl_taking_everything(status=None, local_only_flag=None, **kwargs): ...
