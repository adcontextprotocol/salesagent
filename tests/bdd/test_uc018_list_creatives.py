"""BDD scenarios + steps for UC-018: list_creatives library queries.

Binds the UC-018 feature; several scenarios are wired (the rest xfail at the
conftest harness fixture):

- ``T-UC-018-storyboard-list-all-creatives-after-sync`` (#1405): after the buyer
  syncs creatives across formats, ``list_creatives`` with no filters returns the
  account's library — schema-valid against ``list-creatives-response.json``, each
  entry exposing ``creative_id``, ``name``, ``format_id``, ``status``. Source
  obligation: adcp ``protocols/creative/index.yaml`` · ``list_all``.
- ``T-UC-018-storyboard-filter-by-concept-id`` (#1407): ``filters.concept_ids``
  scopes results to a concept; each returned creative exposes ``concept_id`` and
  ``concept_name``. Source: adcp ``creative/list-creatives-request.json`` +
  ``core/creative-filters.json`` (concept_ids) and ``list-creatives-response.json``
  (concept_id/concept_name).

The first two are pinned at v3.1-04f59d2d5 (adcp 3.1.0-beta.3).

- ``T-UC-018-inv-034-1-holds`` / ``T-UC-018-inv-034-1-violated`` (#1503):
  BR-RULE-034 cross-principal isolation — an AdCP normative MUST (v3.1-04f59d2d5:
  accounts-and-security.mdx §Data Isolation; building/by-layer/L1/security.mdx §Agent
  and Account Isolation), ungraded by any conformance storyboard,
  so these two scenarios are its only executable guard. Two principals in one tenant
  each own creatives; a buyer authenticated as one sees exactly its own library (holds)
  and never the other's (counter). Enforced in production by
  ``CreativeRepository.get_by_principal``'s ``principal_id`` filter — dropping it
  leaks the co-tenant principal's rows and fails these scenarios. principal_id is
  ``Field(exclude=True)`` (never on the wire), so ownership is verified by matching
  returned creative_ids to the seeded per-principal id sets. See the section comment
  above those steps for the full spec citation.

Wired to real production across all wire transports (auto-parametrized; UC-018
-> CreativeListEnv via conftest ``_detect_uc`` / ``_harness_env``). The repo
sunsets the IMPL pseudo-transport in BDD, so the scenario runs on a2a/mcp/rest
(plus e2e_rest in-network: this branch's ``RestE2EDispatcher`` stashes the
success-path ``wire_response``, so the isolation Then steps assert real HTTP
bytes there too). Each transport returns the same typed response, and
the Then steps validate its production JSON serialization
(``model_dump(mode="json", exclude_none=True)`` — the same NestedModelSerializerMixin
path that produces the on-the-wire bytes); the parametrization still exercises
each dispatch path end to end (a broken transport surfaces as a missing/errored
response).

**Why steps live here (not in steps/domain/ + pytest_plugins):** pytest-bdd 8
resolves step definitions only from the scenario's own module, conftest, or
registered plugins — importing them does not register them. So a step defined
here is reachable only from this module's scenarios.

Note what that is NOT a licence for. The generic ``schema-valid against <file>``
and ``authenticated as principal`` phrasings are owned by
``tests/bdd/steps/generic/``. Re-registering either sentence here would not
"keep the blast radius small" — it would give one Gherkin sentence two meanings,
with the local, usually weaker, definition silently winning for this file while
every other suite kept the generic one. That is the defect
``test_architecture_bdd_no_shadowed_steps.py`` now fails on, and it is exactly
how UC-005 ended up grading ``isinstance(formats, list)`` under a sentence that
promises full pinned-schema validation.

A step belongs inline only when its SENTENCE is specific to this scenario. When
the behaviour is genuinely UC-018-specific, give it its own wording rather than
narrowing a shared one. The reusable, non-step schema validator lives in
``tests.helpers.pinned_schema``.

The "synced" creatives are seeded via ``CreativeFactory`` rather than a live
``sync_creatives`` call: ``CreativeListEnv`` mocks only the audit logger (it has
none of sync's creative-agent / preview-generation patches), and the obligation
under test is ``list_all`` — the listing contract, not the sync path. The
creatives land in the same DB row shape sync would persist, so the listing query
is exercised faithfully.

**Corrupt-blob coercion reconciliation (#1508):** ``list_creatives`` drops a corrupt
``tags``/``assets`` blob value to absent, and collapses a stored empty ``tags`` list to
omission (both conformant at 3.1.1 — the schema permits ``[]`` and absent for ``tags``,
``{}`` and absent for ``assets``, ``null`` for neither). So whoever wires the dormant
all-13-fields boundary graders (``BR-UC-018-list-creatives.feature:292``, ``:312``, ``:549``,
``:575``) must assert value-when-present, not key-presence-of-13 — a creative with empty or
absent tags legitimately omits the key. (``:403``, the ``BR-RULE-148`` tags-AND-semantics
scenario, is separately dormant but seeds a non-empty ``tags`` value by construction, so this
empty/omission caveat doesn't apply there.) The coercion itself is graded on real wire bytes
across a2a/mcp/rest in ``tests/integration/test_list_creatives_concept_filter.py``.
"""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.steps._outcome_helpers import require_payload, wire_field
from tests.bdd.steps.generic._auth import authenticate_env_as
from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.helpers.envelope_assertions import assert_envelope_shape

# Three genuinely-different formats (display / video / audio) for the "three
# different formats" precondition. All three are in the standard format registry:
# the A2A path round-trips format_id through a string and re-validates it against
# known formats, so an unregistered id would be rejected on that transport.
_SYNCED_FORMATS = ("display_300x250", "video_640x480", "audio_30s")

# Bind the UC-018 feature. The wired scenarios are @list-after-sync (#1405),
# @concept-id (#1407), and the @BR-RULE-034 isolation invariants (#1503); the
# remaining scenarios xfail fast at the conftest _harness_env fixture. Whole-feature
# binding via scenarios() is the repo convention the CI shard-splitter requires
# (scripts/ci/shard_split.py).
scenarios("features/BR-UC-018-list-creatives.feature")


def _seed_creative(
    tenant: Any,
    principal: Any,
    fmt: str | None = None,
    *,
    concept_id: str | None = None,
    concept_name: str | None = None,
    **overrides: Any,
) -> Any:
    """Seed one approved creative owned by *principal*, optionally concept-tagged.

    The single place this module assembles a creative: the ``approved`` trait
    supplies ``status="approved"`` and CreativeFactory's realistic default ``assets``
    (which already satisfy the repository's ``data["assets"] IS NOT NULL`` guard — an
    empty ``{"assets": {}}`` is unnecessary). When a concept is given, its
    ``concept_id`` / ``concept_name`` are layered onto those realistic assets in this
    one merge site. Replaces the per-seeder ``status=`` + ``data={"assets": {}}``
    hand-rolls with a single factory idiom.
    """
    from tests.factories import CreativeFactory
    from tests.factories.creative_asset import build_assets, image_spec

    kwargs: dict[str, Any] = {"tenant": tenant, "principal": principal}
    if "status" not in overrides:
        kwargs["approved"] = True
    if fmt is not None:
        kwargs["format"] = fmt
    # Overrides for the #1721 lane-D rows: an explicit name (the repository maps the
    # ``tags`` filter onto Creative.name.contains, so a "tag" IS a name substring),
    # a non-approved status, and an explicit created_at so ordering assertions have
    # distinct, deterministic sort keys instead of 60 rows sharing one server_default
    # timestamp. Layered here rather than in a second seeder so this stays the one
    # place the module assembles a creative.
    for key in ("name", "status", "created_at"):
        if key in overrides:
            kwargs[key] = overrides.pop(key)
    if overrides:
        raise TypeError(f"_seed_creative got unexpected overrides: {sorted(overrides)}")
    if concept_id or concept_name:
        data: dict[str, Any] = {"assets": build_assets(image_spec("banner"))}
        if concept_id:
            data["concept_id"] = concept_id
        if concept_name:
            data["concept_name"] = concept_name
        kwargs["data"] = data
    return CreativeFactory(**kwargs)


# ── Given ────────────────────────────────────────────────────────────


def _get_or_create_tenant_and_principal(env: Any) -> tuple[Any, Any]:
    """Idempotently seed the env's tenant + principal (shared e2e_rest DB).

    Rationale on ``get_or_create`` (jdy1-M3, #1418): a prior e2e_rest scenario's
    rows survive in the live-server DB, so plain factory inserts UniqueViolate.
    """
    from src.core.database.models import Principal, Tenant
    from tests.factories import PrincipalFactory, TenantFactory
    from tests.factories.core import get_or_create

    tenant = get_or_create(
        env,
        Tenant,
        {"tenant_id": env._tenant_id},
        lambda: TenantFactory(tenant_id=env._tenant_id),
    )
    principal = get_or_create(
        env,
        Principal,
        {"tenant_id": env._tenant_id, "principal_id": env._principal_id},
        lambda: PrincipalFactory(tenant=tenant, principal_id=env._principal_id),
    )
    return tenant, principal


# 'the Buyer is authenticated as principal "{principal_id}"' is NOT registered here.
# This module used to declare it, which meant the sentence had two definitions — this
# one and the identical parser in steps/domain/uc003_ext_error_scenarios.py (registered
# globally via conftest pytest_plugins). UC-018 silently got the local one and every
# other feature got the plugin one; the two bodies differed only by a ctx["has_auth"]
# flag, so the divergence was invisible until someone diffed them. Deleted so the
# sentence has one meaning. Both call the same authenticate_env_as helper, and the
# extra has_auth flag is read only by a UC-003 step, so nothing here changes.


@given("the buyer recently synced three creatives in three different formats via sync_creatives")
def given_recently_synced_three_creatives(ctx: dict) -> None:
    """Seed three approved creatives (one per format) owned by the authenticated buyer.

    Seeded via CreativeFactory rather than a live sync_creatives call — see the
    module docstring. Records the synced creative_ids for the Then steps.
    """
    env = ctx["env"]
    tenant, principal = _get_or_create_tenant_and_principal(env)
    synced_ids = [_seed_creative(tenant, principal, fmt).creative_id for fmt in _SYNCED_FORMATS]
    ctx["tenant"] = tenant
    ctx["principal"] = principal
    ctx["synced_creative_ids"] = synced_ids


# ── When ─────────────────────────────────────────────────────────────


@when("the Buyer Agent sends list_creatives with no filters for the same account")
def when_list_creatives_no_filters(ctx: dict) -> None:
    """Dispatch list_creatives with no filters through the scenario's transport.

    Reuses the canonical generic dispatch helper (``env.call_via`` + ctx stash of
    ``response`` / ``wire_response`` / ``error``) rather than re-implementing it.
    No filter kwargs are passed, so the listing runs unfiltered; a missing
    transport raises in ``_call_via`` (loud guard — there is no IMPL fallback).
    """
    from tests.bdd.steps.generic.when_request import _call_via

    _call_via(ctx, ctx.get("transport"))


# ── Then ─────────────────────────────────────────────────────────────


def _serialized_response(ctx: dict) -> dict[str, Any]:
    """Serialize the typed response through the production serializer (JSON mode).

    list_creatives returns the same typed payload on every transport, so each
    transport's Then steps assert on the same serialized document. ``mode="json"``
    drives ``NestedModelSerializerMixin`` — the same serializer that produces the
    on-the-wire bytes (format_id -> {agent_url, id}, datetimes -> ISO strings).
    ``exclude_none`` omits unset optional fields (format_summary, status_summary,
    sandbox, errors, ext, context), matching the buyer-visible REST wire and the
    AdCP contract, which type those fields only when present (a literal ``null``
    is not a valid array/object/boolean).

    The 4-transport parametrization still exercises each dispatch path end to end:
    a broken transport surfaces as a missing/errored dispatch payload here.
    """
    return require_payload(ctx).model_dump(mode="json", exclude_none=True)


@then("the creatives array should include each of the synced creatives")
def then_creatives_include_synced(ctx: dict) -> None:
    """Assert every creative_id seeded by the Given is present in the library."""
    expected = set(ctx["synced_creative_ids"])
    returned = {entry["creative_id"] for entry in _serialized_response(ctx)["creatives"]}
    missing = expected - returned
    assert not missing, (
        f"synced creatives missing from the list_creatives library: {sorted(missing)}; "
        f"returned creative_ids: {sorted(returned)}"
    )


@then("each creative entry should expose creative_id, name, format_id, and status")
def then_each_creative_exposes_core_fields(ctx: dict) -> None:
    """Assert every entry carries the four core fields, format_id as a {agent_url, id} object."""
    creatives = _serialized_response(ctx)["creatives"]
    assert creatives, "list_creatives returned an empty creatives array"
    for entry in creatives:
        for field in ("creative_id", "name", "format_id", "status"):
            assert field in entry, f"creative entry missing {field!r}: {entry}"
            assert entry[field] not in (None, "", {}), f"creative entry has empty {field!r}: {entry}"
        # v3.1 federation contract: format_id is an object carrying agent_url + id.
        fid = entry["format_id"]
        assert isinstance(fid, dict) and fid.get("agent_url") and fid.get("id"), (
            f"format_id must be an object with agent_url and id, got: {fid!r}"
        )


# ── @concept-id storyboard scenario (#1407) ─────────────────────────────
#
# v3.1 ADDED filters.concept_ids (array of concept-id strings, minItems 1).
# Concepts group related creatives across sizes and formats; each returned
# creative exposes concept_id and concept_name. Source obligation: adcp
# creative/list-creatives-request.json + core/creative-filters.json (concept_ids)
# and creative/list-creatives-response.json (creatives[].concept_id/concept_name),
# pin v3.1-04f59d2d5. The concept identifier/name live on the creative's JSON data
# blob (no native sync_creatives field in adcp 5.7.0 — concepts originate from
# external creative-management systems), so they are seeded directly.

# Human-readable label paired with the target concept_id, asserted non-empty by
# the Then step. Two registered formats give the concept creatives genuinely
# different sizes/formats (the point of a concept); the A2A path re-validates
# format_id against the registry, so unregistered ids would be rejected there.
_CONCEPT_NAME = "Summer 2026 Campaign"
_CONCEPT_FORMATS = ("display_300x250", "video_640x480")
_DECOY_CONCEPT_ID = "concept_winter_2025"


@given(
    parsers.parse(
        'the authenticated principal has creatives grouped under concept "{concept_id}" '
        "and other creatives under different concepts"
    )
)
def given_creatives_grouped_under_concept(ctx: dict, concept_id: str) -> None:
    """Seed concept-tagged creatives plus decoys so the filter is falsifiable.

    Under the target concept: two approved creatives in two formats (concepts span
    sizes/formats). Decoys: one under a different concept, one with no concept at
    all. A broken filter that returned the whole library would surface a decoy
    whose concept_id != the requested one (or is absent), failing the Then steps.

    Seeded via ``_seed_creative`` rather than a live sync (CreativeListEnv has no
    sync patches; the obligation under test is the listing/filter contract). The
    helper supplies the factory's realistic default ``assets`` (the repository drops
    rows whose ``data["assets"]`` IS NULL) and layers the concept fields on top.
    """
    env = ctx["env"]
    tenant, principal = _get_or_create_tenant_and_principal(env)

    in_concept_ids = [
        _seed_creative(tenant, principal, fmt, concept_id=concept_id, concept_name=_CONCEPT_NAME).creative_id
        for fmt in _CONCEPT_FORMATS
    ]

    # Decoy under a different concept.
    _seed_creative(
        tenant,
        principal,
        _CONCEPT_FORMATS[0],
        concept_id=_DECOY_CONCEPT_ID,
        concept_name="Winter 2025 Campaign",
    )
    # Decoy with no concept at all.
    _seed_creative(tenant, principal, _CONCEPT_FORMATS[0])

    ctx["tenant"] = tenant
    ctx["principal"] = principal
    ctx["concept_id"] = concept_id
    ctx["in_concept_creative_ids"] = in_concept_ids


@when(parsers.re(r"the Buyer Agent sends list_creatives with filters\.concept_ids \[(?P<concept_list>.+)\]"))
def when_list_creatives_concept_ids(ctx: dict, concept_list: str) -> None:
    """Dispatch list_creatives with a structured filters.concept_ids filter.

    Parses the bracketed concept-id list from the step text and dispatches the
    structured filter through the scenario's transport via the canonical helper.
    The filter travels as a JSON dict (built through CreativeFilters so minItems/
    field validation runs); each wire transport coerces it back to CreativeFilters
    server-side (FastMCP TypeAdapter / A2A skill / REST body), so a dict is the one
    shape that works uniformly across a2a/mcp/rest (IMPL is sunsetted in BDD).
    """
    import re

    from adcp import CreativeFilters

    from tests.bdd.steps.generic.when_request import _call_via

    concept_ids = re.findall(r'"([^"]+)"', concept_list)
    assert concept_ids, f"no concept ids parsed from {concept_list!r}"
    ctx["requested_concept_ids"] = concept_ids
    filters = CreativeFilters(concept_ids=concept_ids).model_dump(mode="json", exclude_none=True)
    _call_via(ctx, ctx.get("transport"), filters=filters)


def _wire_creatives(ctx: dict) -> list[dict[str, Any]]:
    """Return the creatives array as the buyer sees it on the wire.

    Delegates to the canonical :func:`wire_field` guard (GH #1744 collapsed the
    private guard clone this used to carry, and #1858 replaced its last
    remnant). The guard branches on the DECLARATION the dispatcher made
    (``TransportResult.has_wire``) and raises when a declared wire was not
    captured, so the concept-field assertions read the actual on-the-wire bytes
    rather than a re-serialization. This function used to key on transport
    IDENTITY (``transport not in (None, Transport.IMPL)``), which is the
    spelling the shared helper replaced across the suite: a lookup against an
    enum member reclassifies every result the day that member moves, and it made
    this the last site free to drift from the guard the others share.
    """
    return wire_field(ctx, "creatives")


@then(parsers.parse('the creatives array should only include creatives belonging to concept "{concept_id}"'))
def then_only_creatives_in_concept(ctx: dict, concept_id: str) -> None:
    """Assert every returned creative belongs to the requested concept (and the set is non-empty)."""
    creatives = _wire_creatives(ctx)
    assert creatives, f"list_creatives returned no creatives for concept {concept_id!r}"
    offenders = [
        {"creative_id": entry.get("creative_id"), "concept_id": entry.get("concept_id")}
        for entry in creatives
        if entry.get("concept_id") != concept_id
    ]
    assert not offenders, f"concept_ids filter leaked creatives outside concept {concept_id!r}: {offenders}"
    # Falsifiability anchor: the seeded in-concept creatives are exactly what comes back.
    returned_ids = {entry["creative_id"] for entry in creatives}
    assert returned_ids == set(ctx["in_concept_creative_ids"]), (
        f"expected exactly the in-concept creatives {sorted(ctx['in_concept_creative_ids'])}, "
        f"got {sorted(returned_ids)}"
    )


@then(parsers.parse('each returned creative should carry concept_id "{concept_id}" and a concept_name'))
def then_each_creative_carries_concept(ctx: dict, concept_id: str) -> None:
    """Assert each returned creative exposes concept_id (== requested) and a non-empty concept_name."""
    creatives = _wire_creatives(ctx)
    assert creatives, "list_creatives returned an empty creatives array"
    for entry in creatives:
        assert entry.get("concept_id") == concept_id, (
            f"creative {entry.get('creative_id')!r} concept_id mismatch: {entry}"
        )
        assert entry.get("concept_name"), f"creative {entry.get('creative_id')!r} missing concept_name: {entry}"


# ── @BR-RULE-034 cross-principal isolation scenarios (#1503) ────────────
#
# BR-RULE-034 (P0): list_creatives is principal-scoped — a buyer sees only its own
# creatives, never another principal's, even within the same tenant.
#
# Spec ground (Spec-Grounding Gate): this is an AdCP normative MUST, pinned at
# v3.1-04f59d2d5 — docs/media-buy/advanced-topics/accounts-and-security.mdx §Data
# Isolation (L33-37): a created object is "permanently associated with the account",
# and for any later read "the server MUST verify that the agent has access to that
# account", else it "MUST return a permission denied error". The deeper normative
# reference is docs/building/by-layer/L1/security.mdx §Agent and Account Isolation
# (L159), incl. §"Client-side isolation: cross-principal tool-call confusion" (L229).
# (At the pin the superseded 2.5.3 principals-and-security.mdx was renamed to
# accounts-and-security.mdx; the source docs/ paths resolve at the pin — the built
# dist/docs/3.1.0-beta.3/ tree is only on later commits.) It is ungraded-by-storyboard:
# no conformance storyboard grades multi-principal isolation (universal/security.yaml
# grades authentication, not authenticated isolation), so these two scenarios are the
# ONLY executable guard of that MUST.
#
# Enforcement site: CreativeRepository.get_by_principal's ``principal_id=principal_id``
# filter (src/core/database/repositories/creative.py). Dropping that filter leaks
# the co-tenant principal's rows and fails both scenarios below (INV-1 holds asserts
# an exact-set match; INV-1 counter asserts zero overlap with the other principal).
#
# principal_id is ``Field(exclude=True)`` on the Creative schema, so it never appears
# on the buyer-facing wire. Ownership is therefore verified by matching each returned
# creative_id against the per-principal id sets recorded at seed time — CreativeFactory
# assigns a globally-unique creative_id per row, so the two principals' id sets are
# disjoint and the isolation assertion is well-formed. Assertions read
# the real serialized bytes on a2a/mcp/rest via _wire_creatives (which reads the
# dispatcher's own wire declaration through wire_field),
# satisfying the "actual wire bytes" constraint.

_ISOLATION_CREATIVES_KEY = "isolation_creatives_by_principal"


@given(parsers.parse('principal "{principal_id}" has {count:d} creatives'))
@given(parsers.parse('principal "{principal_id}" has {count:d} creatives in the same tenant'))
def given_principal_has_n_creatives(ctx: dict, principal_id: str, count: int) -> None:
    """Seed *count* approved creatives owned by *principal_id* under a fresh tenant.

    Both isolation scenarios seed two principals in ONE tenant — the scenario's
    requirement. WHICH tenant is env plumbing: each scenario gets its own
    uniquely-named tenant (created on the first seed, reused via ctx on the
    second) and the env is re-pointed at it with ``switch_tenant``. Over
    e2e_rest the live-server DB is shared across scenarios, and the sibling
    UC-018 Givens seed creatives for this same buyer — under a shared tenant
    those survivors would leak into the unfiltered list and break the
    exact-count / set-equality assertions (and re-seeding the same
    tenant/principal rows would UniqueViolate). A fresh tenant per scenario
    keeps every assertion at full strength on all transports. Records each
    principal's creative_ids so the Then steps can attribute ownership
    (principal_id is off-wire — see the section comment).

    Two ``@given`` phrasings map to this one body: ``parsers.parse`` requires a
    whole-string match, so the "in the same tenant" variant needs its own decorator.
    """
    from uuid import uuid4

    from tests.factories import PrincipalFactory, TenantFactory

    env = ctx["env"]
    tenant = ctx.get("tenant")
    if tenant is None:
        tenant_id = f"uc018_iso_{uuid4().hex[:8]}"
        tenant = TenantFactory(tenant_id=tenant_id)
        env.switch_tenant(tenant_id)
        ctx["tenant"] = tenant
    principal = PrincipalFactory(tenant=tenant, principal_id=principal_id)
    seeded: dict[str, list[str]] = ctx.setdefault(_ISOLATION_CREATIVES_KEY, {})
    seeded[principal_id] = [_seed_creative(tenant, principal).creative_id for _ in range(count)]


@when(parsers.parse('the Buyer Agent authenticated as "{principal_id}" sends a list_creatives request'))
def when_authenticated_principal_lists_creatives(ctx: dict, principal_id: str) -> None:
    """Authenticate as *principal_id* and dispatch an unfiltered list_creatives.

    Re-authenticates via the shared ``authenticate_env_as`` helper (which clears the
    identity cache) AFTER the seed steps committed the principals, so the next identity
    build resolves the principal's real token from the DB rather than the tokenless
    identity cached during Background (which ran before any principal row existed). On
    MCP/A2A this exercises the full header -> token -> DB-lookup auth chain; REST resolves
    identity via a FastAPI dependency override. Reuses the canonical generic dispatch
    helper (``_call_via`` stashes response / wire_response / error on ctx).
    """
    from tests.bdd.steps.generic.when_request import _call_via

    authenticate_env_as(ctx, principal_id)
    _call_via(ctx, ctx.get("transport"))


def _returned_creative_ids(ctx: dict) -> set[str]:
    """The set of creative_ids in the wire response.

    Ownership is id-based: principal_id is ``Field(exclude=True)`` and never on the
    wire, so a returned creative's owner is identified by which seeded id set its
    creative_id came from.
    """
    return {entry["creative_id"] for entry in _wire_creatives(ctx)}


@then(parsers.parse("the response contains exactly {count:d} creatives"))
def then_response_contains_exactly_n_creatives(ctx: dict, count: int) -> None:
    """Assert the wire response carries exactly *count* creatives (all fit on page 1)."""
    creatives = _wire_creatives(ctx)
    assert len(creatives) == count, (
        f"expected exactly {count} creatives, got {len(creatives)}: "
        f"{sorted(entry.get('creative_id') for entry in creatives)}"
    )


@then(parsers.parse('all creatives belong to principal "{principal_id}"'))
def then_all_creatives_belong_to(ctx: dict, principal_id: str) -> None:
    """Assert the returned creatives are exactly the ones this principal seeded."""
    owned = set(ctx[_ISOLATION_CREATIVES_KEY][principal_id])
    returned = _returned_creative_ids(ctx)
    assert returned, "list_creatives returned an empty creatives array"
    strangers = returned - owned
    assert not strangers, f"creatives not owned by {principal_id!r} leaked into the response: {sorted(strangers)}"
    # Falsifiability anchor: an unscoped query returns MORE than the owner's library.
    assert returned == owned, f"expected exactly {principal_id!r}'s creatives {sorted(owned)}, got {sorted(returned)}"


@then(parsers.parse('none of the returned creatives belong to principal "{principal_id}"'))
def then_none_belong_to(ctx: dict, principal_id: str) -> None:
    """Assert no returned creative belongs to the co-tenant principal (isolation counter)."""
    returned = _returned_creative_ids(ctx)
    assert returned, "isolation counter is vacuous on an empty response (list_creatives returned no creatives)"
    leaked = returned & set(ctx[_ISOLATION_CREATIVES_KEY][principal_id])
    assert not leaked, (
        f"cross-principal leak: creatives owned by {principal_id!r} appeared in the response: {sorted(leaked)}"
    )


# ── #1721 lane D: rows whose behavior the transport-seam conversion can delete ──
#
# converts _handle_list_creatives_skill (and the other handlers this
# PR opened) to build the typed request through the shared build_*_request seam, and
# moves the MCP structured->flat sort/pagination coercion into
# ListCreativesRequest. Two families of behavior are silently deletable by
# that conversion, and both were ungraded — the whole UC-018 partition/boundary set
# xfailed fast at the conftest harness gate:
#
#  1. media_buy_id + media_buy_ids merge/dedup. ListCreativesRequest declares NEITHER
#     key (they live on CreativeFilters, adcp 3.1.1 core/creative-filters.json), so
#     the plan's literal prescription — build_X_request(**select_request_fields(
#     ListCreativesRequest, bag)) — drops both. The merge lives in the builder
#     (listing.py:151-156) and the DB join in CreativeRepository.get_by_principal.
#
#  2. The flat-path silent coercions: sort_order outside {asc, desc} -> "desc"
#     (listing.py:126-130) and sort_by outside the field_mapping -> "created_date"
#     (:161-178). If the moved coercion writes the structured Sort object straight
#     onto ListCreativesRequest instead of landing ahead of the flat path, the SDK
#     Sort enum REJECTS those values and the buyer gets a wire error where they used
#     to get a silently-coerced ordering.
#
# Rows in these three outlines that grade behavior this lane does not implement
# (the fields[] projection, max_results/PaginationRequest, assignment_count sorting,
# tag AND/OR semantics) are parked per-row in tests/bdd/conftest.py _SELECTIVE_XFAIL,
# each citing #1721 — per-ROW, so the rows this PR's behavior change touches execute
# while the untouched siblings stay declared rather than silently green.
#
# Spec ground: adcp v3.1.1 dist/schemas/3.1.1/core/creative-filters.json declares
# media_buy_ids (array) with no singular sibling, and
# dist/schemas/3.1.1/creative/list-creatives-request.json carries filters/sort/
# pagination. The singular media_buy_id is this agent's documented backward-compat
# flat param, which is exactly why nothing on the request model protects it.

#: The two media buys whose creatives the merge row expects back, plus a decoy the
#: request never names. Literal ids because the scenario names them literally.
_MERGE_MEDIA_BUY_IDS = ("mb1", "mb2")
_DECOY_MEDIA_BUY_ID = "mb3"

#: Row count for the pagination/sorting boundary outline ("60 approved creatives"),
#: and the default page size the reader applies when no pagination is requested.
_PAGINATION_SEED_COUNT = 60
_DEFAULT_PAGE_SIZE = 50


def _seed_media_buy(tenant: Any, principal: Any, media_buy_id: str) -> Any:
    """Seed one media buy with a literal id, via the factory."""
    from tests.factories import MediaBuyFactory

    return MediaBuyFactory(tenant=tenant, principal=principal, media_buy_id=media_buy_id)


def _assign(tenant: Any, creative: Any, media_buy: Any) -> Any:
    """Attach *creative* to *media_buy*; the media_buy_ids filter joins on this row."""
    from tests.factories import CreativeAssignmentFactory

    return CreativeAssignmentFactory(creative=creative, media_buy=media_buy)


@given("the authenticated principal has creatives with various tags, statuses, and media buy associations")
def given_creatives_with_tags_statuses_and_media_buys(ctx: dict) -> None:
    """Seed the filter-semantics fixture: creatives under mb1, mb2 and a decoy buy.

    The merge row's falsifiability comes from the decoys. One creative sits under
    ``mb3``, which the request never names, and one is unassigned entirely; a filter
    that collapsed to "no media_buy filter at all" (the shape a dropped
    media_buy_id/media_buy_ids produces) returns all four and fails the exact-set
    assertion. A filter that honoured only ONE of the two keys returns one creative
    and fails it too.

    Tags travel as name substrings because that is what the repository's ``tags``
    filter actually does (``Creative.name.contains(tag)``,
    CreativeRepository.get_by_principal), and statuses vary so the parked
    status-filter rows have real data behind them when they are wired.
    """
    env = ctx["env"]
    tenant, principal = _get_or_create_tenant_and_principal(env)

    mb1, mb2 = (_seed_media_buy(tenant, principal, mb_id) for mb_id in _MERGE_MEDIA_BUY_IDS)
    decoy_buy = _seed_media_buy(tenant, principal, _DECOY_MEDIA_BUY_ID)

    in_mb1 = _seed_creative(tenant, principal, name="nike q1 launch")
    in_mb2 = _seed_creative(tenant, principal, name="nike brand anthem")
    in_decoy_buy = _seed_creative(tenant, principal, name="adidas q1 retargeting")
    _assign(tenant, in_mb1, mb1)
    _assign(tenant, in_mb2, mb2)
    _assign(tenant, in_decoy_buy, decoy_buy)

    # Unassigned, and rejected — a creative no media_buy filter can reach.
    _seed_creative(tenant, principal, name="nike rejected cut", status="rejected")

    ctx["tenant"] = tenant
    ctx["principal"] = principal
    ctx["expected_merged_creative_ids"] = {in_mb1.creative_id, in_mb2.creative_id}


@given("the authenticated principal has 3 approved creatives with full data")
def given_three_approved_creatives_with_full_data(ctx: dict) -> None:
    """Seed 3 approved creatives that DO carry package assignments in the database.

    The assignments are the point: ``include_assignments false`` is only falsifiable
    against creatives that have assignment rows to leak. Without them the Then would
    pass over an empty library and grade nothing.
    """
    env = ctx["env"]
    tenant, principal = _get_or_create_tenant_and_principal(env)
    media_buy = _seed_media_buy(tenant, principal, _MERGE_MEDIA_BUY_IDS[0])

    creatives = [_seed_creative(tenant, principal, name=f"full data creative {i}") for i in range(3)]
    for creative in creatives:
        _assign(tenant, creative, media_buy)

    ctx["tenant"] = tenant
    ctx["principal"] = principal
    ctx["seeded_creative_ids"] = [creative.creative_id for creative in creatives]


@given(parsers.parse("the authenticated principal has {count:d} approved creatives"))
def given_n_approved_creatives(ctx: dict, count: int) -> None:
    """Seed *count* approved creatives with strictly decreasing created_at.

    Each row is one minute older than the previous, so "sorted by created_date
    descending" has a single correct answer and the ordering assertions below can
    compare an exact id sequence rather than "is it sorted by something".
    Names are alphabetically ordered the SAME way, so a step that silently sorted by
    name instead of created_date would still have to explain the coercion rows.
    """
    from datetime import UTC, datetime, timedelta

    env = ctx["env"]
    tenant, principal = _get_or_create_tenant_and_principal(env)

    newest = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    seeded = [
        _seed_creative(
            tenant,
            principal,
            name=f"paged creative {index:03d}",
            created_at=newest - timedelta(minutes=index),
        )
        for index in range(count)
    ]

    ctx["tenant"] = tenant
    ctx["principal"] = principal
    # Newest first — the reader's documented default ordering (created_date desc).
    ctx["creative_ids_newest_first"] = [creative.creative_id for creative in seeded]


# ── When ─────────────────────────────────────────────────────────────


@when(
    parsers.parse(
        'the Buyer Agent sends a list_creatives request with singular media_buy_id "{singular}" '
        'and plural media_buy_ids ["{plural}"]'
    )
)
def when_list_creatives_singular_and_plural_media_buy_ids(ctx: dict, singular: str, plural: str) -> None:
    """Dispatch with BOTH the singular backward-compat key and the plural array."""
    dispatch_request(ctx, media_buy_id=singular, media_buy_ids=[plural])


@when("the Buyer Agent sends a list_creatives request with include_assignments false")
def when_list_creatives_without_assignments(ctx: dict) -> None:
    """Dispatch with the projection flag the A2A handler enumerates by hand today."""
    dispatch_request(ctx, include_assignments=False)


@when(parsers.parse('the Buyer Agent sends a list_creatives request with sort direction "{direction}"'))
def when_list_creatives_with_sort_direction(ctx: dict, direction: str) -> None:
    """Dispatch with the SPEC's structured sort object.

    ``sort`` is an object with ``field`` and ``direction``, each a closed enum
    (list-creatives-request.json -> enums/creative-sort-field.json, enums/sort-direction.json).
    The flat ``sort_order`` this replaces is not in AdCP 3.1.1 at all, and a value outside
    the enum is a VALIDATION_ERROR rather than something silently coerced.
    """
    dispatch_request(ctx, sort={"direction": direction})


@when(parsers.parse('the Buyer Agent sends a list_creatives request with sort field "{field}"'))
def when_list_creatives_with_sort_field(ctx: dict, field: str) -> None:
    """Dispatch with the spec's structured sort object, naming the field."""
    dispatch_request(ctx, sort={"field": field})


@when(parsers.parse("the Buyer Agent sends a list_creatives request with pagination max_results {value}"))
def when_list_creatives_with_pagination(ctx: dict, value: str) -> None:
    """Dispatch with the SPEC's pagination object.

    ``pagination.max_results`` is an integer with minimum 1 and maximum 100
    (core/pagination-request.json). The flat ``limit``/``page`` this replaces are not in
    AdCP 3.1.1, so the old rows asserting a 1000-item code cap were grading behaviour the
    spec does not define. A non-integer or out-of-range value is a VALIDATION_ERROR.
    """
    raw = value.strip().strip('"')
    try:
        parsed: object = int(raw)
    except ValueError:
        parsed = raw  # deliberately non-integer, so the boundary can reject it
    dispatch_request(ctx, pagination={"max_results": parsed})


@when(
    parsers.parse(
        "the Buyer Agent sends a list_creatives request with structured filters with "
        'media_buy_ids ["{first}", "{second}"]'
    )
)
def when_list_creatives_with_filter_media_buy_ids(ctx: dict, first: str, second: str) -> None:
    """Dispatch with ``filters.media_buy_ids`` -- where AdCP 3.1.1 puts it.

    The flat singular ``media_buy_id`` + plural ``media_buy_ids`` pair this replaces exists
    nowhere in the spec: ListCreativesRequest declares neither, and CreativeFilters declares
    only the plural. The merge-the-singular-into-the-plural behaviour the old row graded was
    therefore never a spec obligation.
    """
    dispatch_request(ctx, filters={"media_buy_ids": [first, second]})


# ── Then ─────────────────────────────────────────────────────────────


def _wire_creative_ids(ctx: dict) -> list[str]:
    """The creative_ids the buyer received, in wire order."""
    return [entry["creative_id"] for entry in _wire_creatives(ctx)]


@then("creatives for both mb1 and mb2 returned (deduplicated)")
def then_merged_media_buy_creatives(ctx: dict) -> None:
    """Exactly the union of mb1's and mb2's creatives — no decoys, no duplicates.

    Three distinct regressions fail here, which is why the assertion is an exact SET
    plus a length check rather than a containment check:
      - the singular media_buy_id dropped  -> only mb2's creative comes back;
      - the plural media_buy_ids dropped   -> only mb1's;
      - both dropped (the shape a bare select_request_fields(ListCreativesRequest,
        bag) produces, since neither key is declared on that model) -> the whole
        library including the decoy-buy and unassigned creatives.
    """
    returned = _wire_creative_ids(ctx)
    assert set(returned) == ctx["expected_merged_creative_ids"], (
        f"expected exactly the mb1+mb2 creatives {sorted(ctx['expected_merged_creative_ids'])}, got {sorted(returned)}"
    )
    assert len(returned) == len(ctx["expected_merged_creative_ids"]), (
        f"media_buy_id/media_buy_ids merge emitted duplicate rows: {returned}"
    )


@then("assignment data excluded from creatives")
def then_assignments_excluded(ctx: dict) -> None:
    """No creative on the wire carries assignment data, though every seeded creative
    has a CreativeAssignment row in the database."""
    creatives = _wire_creatives(ctx)
    assert {entry["creative_id"] for entry in creatives} == set(ctx["seeded_creative_ids"]), (
        f"expected the 3 seeded creatives {sorted(ctx['seeded_creative_ids'])}, "
        f"got {sorted(entry['creative_id'] for entry in creatives)}"
    )
    leaked = [entry["creative_id"] for entry in creatives if entry.get("assignments") is not None]
    assert leaked == [], f"include_assignments=false still emitted assignment data for: {leaked}"


def _assert_wire_order(ctx: dict, expected_newest_first: bool) -> None:
    """Assert the returned page is the expected slice of the seeded created_at order."""
    ordered = ctx["creative_ids_newest_first"]
    if not expected_newest_first:
        ordered = list(reversed(ordered))
    expected = ordered[:_DEFAULT_PAGE_SIZE]
    assert _wire_creative_ids(ctx) == expected, (
        f"expected the first {_DEFAULT_PAGE_SIZE} creatives "
        f"{'newest' if expected_newest_first else 'oldest'}-first, got a different sequence"
    )


@then("creatives sorted descending")
def then_creatives_sorted_descending(ctx: dict) -> None:
    _assert_wire_order(ctx, expected_newest_first=True)


@then("creatives sorted ascending")
def then_creatives_sorted_ascending(ctx: dict) -> None:
    _assert_wire_order(ctx, expected_newest_first=False)


def then_creatives_sorted_by_default_after_coercion(ctx: dict) -> None:
    """Both silent coercions land on the SAME observable: the default created_date-desc
    ordering, with no wire error.

      - sort_order="random" is not a member of the AdCP sort-direction enum; the agent
        coerces it to "desc" (listing.py:126-130) rather than rejecting the request.
      - sort_by="unknown_field" is outside the builder's field_mapping; the agent
        coerces it to "created_date" (:161-178), direction defaulting to desc.

    A coercion is only observable as an ORDERING plus the ABSENCE of an error, so the
    exact newest-first sequence pins both halves: ``_wire_creatives`` raises loudly if
    the dispatch produced an error envelope instead of a response, and the sequence
    discriminates against the other candidate coercion targets (name-desc and
    status-desc both yield a different order over this fixture).

    One body, two rows: the two coercions differ in WHICH input is out of range, not in
    what the buyer is supposed to receive — writing them as two identical functions
    would be the duplication the repo's DRY invariant forbids.
    """
    _assert_wire_order(ctx, expected_newest_first=True)


@then(parsers.parse('error "{code}" with suggestion'))
def then_error_code_with_suggestion(ctx: dict, code: str) -> None:
    """The spec's closed enums make an out-of-enum sort value an ERROR, not a coercion.

    Registered HERE because pytest-bdd resolves Then steps per MODULE: uc019 implements the
    identical text, but a step defined in another module does not bind these scenarios, and
    an unbound Then does not fail -- it raises StepDefinitionNotFoundError, which the
    non-strict auto-xfail swallows (conftest.py:164) with a reason containing no "production
    gap", so the dormancy classifier does not catch it either. Four rows that were PASSING
    went silently dormant that way when this outline was rewritten onto the spec vocabulary,
    and the NET xfail count went DOWN at the same time because new rows were passing -- so
    the aggregate hid it. Per-row disposition is the only honest check.
    """
    envelope = ctx["result"].wire_error_envelope
    assert envelope is not None, (
        f"expected the wire to carry a {code} envelope; got none. An out-of-enum sort value "
        f"or an out-of-range pagination.max_results violates a SCHEMA CONSTRAINT under "
        f"pinned 3.1.1, so it must be refused rather than silently coerced."
    )
    # The code no longer differs by transport, so the row's code is asserted as written.
    # An out-of-enum sort value, or pagination.max_results above the schema's maximum of
    # 100, violates a SCHEMA CONSTRAINT -- which pinned 3.1.1 assigns to INVALID_REQUEST
    # ("violates schema constraints"), not VALIDATION_ERROR ("beyond schema validation").
    # This step used to downgrade the expectation to VALIDATION_ERROR on mcp and a2a,
    # because only REST reached the spec-correct code (its body is derived from the DTO,
    # so the failure was attributed at the schema layer while the others raised from the
    # typed boundary first). That exception was recorded as shrinking to nothing once the
    # transports agreed. They now do -- adcp_error_for maps a pydantic ValidationError to
    # AdCPInvalidRequestError -- so it is gone rather than left to rot into a downgrade
    # that hides a future regression.
    assert_envelope_shape(envelope, code, recovery="correctable")
    assert envelope["errors"][0].get("suggestion"), (
        f"the {code} envelope must carry a recovery suggestion: {envelope['errors'][0]}"
    )


@then("creatives sorted by assignment_count")
def then_creatives_sorted_by_assignment_count(ctx: dict) -> None:
    """assignment_count is the last member of creative-sort-field.json -- an enum boundary.

    Asserts the wire order is actually BY assignment_count, not merely that the request
    succeeded: a sort field that is accepted and then ignored looks identical to one that
    works, and that is exactly what an enum-boundary row exists to catch.
    """
    creatives = _wire_creatives(ctx)
    assert creatives, "no creatives on the wire to check the sort of"
    counts = [len(entry.get("assignments") or []) for entry in creatives]

    # NON-VACUITY FIRST. Every seeded creative here has zero assignments, so a bare
    # `counts == sorted(counts, reverse=True)` compares [0, 0, 0, ...] to itself and passes
    # no matter what order the seller returned -- including when the sort field is ignored
    # entirely, which is the state today (CreativeRepository.get_by_principal maps only
    # name/status/created_at). A row that cannot fail is worse than no row: it turned a real
    # production gap into an XPASS and would have retired its own xfail entry.
    assert len(set(counts)) > 1, (
        "cannot grade assignment_count ordering: every creative on the wire has the same "
        f"assignment count ({counts}). Seed creatives with DIFFERING assignment counts "
        "before asserting an order, or this passes while the sort field is ignored."
    )
    assert counts == sorted(counts, reverse=True), (
        f"expected creatives ordered by assignment_count descending, got {counts}"
    )
