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

from src.core.tools._announced_shape import (
    derived_signature,
)

# The hand-written tool lists that stood here -- _LANE_D_TOOLS, _DERIVED_TOOLS, and the
# _tool()/_resolve_tool() helpers that mapped a name to a wrapper -- are gone with the
# wrappers. TOOLS is the list, and the test they fed
# (test_every_lane_d_tool_resolves_its_request_dto) asserted that request_model_for finds a
# DTO for each -- which now reads TOOLS on both sides and so cannot fail.


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


class TestEveryRegisteredToolAnnouncesItsRequiredFields:
    """The live statement: every registered tool advertises the fields its DTO requires."""

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


# ── Fixtures ─────────────────────────────────────────────────────────────────
#
# A tool's DTO comes from its REGISTRY ROW, looked up by the tool's name, so a fixture
# supplies its model by substituting a row rather than by being wired to a builder. One
# source function serves them all: only its ``__name__`` is read.


class _FixtureRequiredButInternal(BaseModel):
    """A required field the buyer is never shown -- the contradiction under test."""

    media_buy_id: str = Field(..., exclude=True)
    note: str | None = None


class _FixtureRequiredAndAnnounced(BaseModel):
    media_buy_id: str
    note: str | None = None


def _fixture_named_for_the_row(note: str | None = None):
    """Named for the row substituted around it; the body is never called."""


_fixture_named_for_the_row.__name__ = "list_accounts"


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

    @pytest.mark.asyncio
    # Graduated: the field is gone, and this marker's own instruction was to delete it
    # the moment it was. The UC-011 step that needed it dispatches a literal payload.
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


class _FixtureWithAnInternalField(_LibraryListAccountsRequest):
    local_only_flag: bool | None = Field(default=None, exclude=True)


def _fixture_impl_taking_everything(status=None, local_only_flag=None, **kwargs): ...
