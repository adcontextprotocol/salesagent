"""Per-tenant AdCP capability declarations (#1592 T1a).

The store behind ``tenants.capability_declarations``: the blocks an operator may
declare and have echoed on ``get_adcp_capabilities``.

STRICT policy (KonstantinMirin's decision, 2026-07-27). A capability posture may be
declared -- and therefore emitted -- ONLY when the implementation backs it. So this
model carries fields for *business facts* the response merely echoes, and has NO
field at all for a *behavioral posture* production does not implement. Naming an
unbacked block is a deployment fault, not a buyer error: it raises
``AdCPConfigurationError`` -> ``CONFIGURATION_ERROR`` (recovery ``terminal``),
naming the block and the issue that will implement it.

Why "no field" rather than "a field we validate": a field that exists but is always
rejected still tempts the next implementer to relax the check. The absence is the
enforcement.

Shape follows ``IdempotencyPosture`` (src/core/idempotency_policy.py): a typed
model whose ``validate_backing()`` raises ``AdCPConfigurationError`` rather than
silently clamping or emitting a non-conformant response.
"""

from collections.abc import Collection, Iterable
from enum import Enum
from typing import Any

from adcp.types.generated_poc.enums.specialism import AdcpSpecialism
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import ExperimentalFeature, SupportedProtocol

# `Measurement` is aliased `LibraryMeasurementDeclaration`, NOT the conventional
# `LibraryMeasurement`: the SDK has TWO distinct `Measurement` types, and
# `src/core/schemas/_base.py:95` already binds `LibraryMeasurement` to the
# product-level one (`adcp.types.Measurement`), whose local subclass is `Measurement`
# (_base.py:1364). The schema-inheritance guard keys its Library*-alias map on the
# un-prefixed name across ALL schema modules, so reusing the alias made it demand that
# the product-level `Measurement` inherit the capabilities-response type. Aliasing to
# match THIS module's subclass keeps the guard checking the right pair. Do not
# "simplify" it back to `LibraryMeasurement`.
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import (
    Measurement as LibraryMeasurementDeclaration,
)
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import TrustedMatch as LibraryTrustedMatch
from pydantic import BaseModel, ConfigDict, ValidationError

from src.core.errors.details import ConfigurationDetails

# Blocks the AdCP schema defines but this deployment does NOT back, mapped to the
# GitHub issue that will implement them. Declaring one is rejected by name so the
# operator gets an actionable error instead of pydantic's generic "extra fields
# not permitted". Every entry here is a promise we would otherwise make to buyers
# and could not keep.
#
# RFC 9421 message signing (#1291) gates the whole signing family: request_signing
# and webhook_signing directly, identity because its brand_json_url/key_origins
# subfields exist only to anchor signing keys, and
# content_standards.supports_webhook_delivery / reporting_delivery_methods /
# offline_delivery_protocols because the schema's must_equal_when rule forces
# webhook_signing.supported=true the moment any of them is declared.
_UNBACKED_BLOCKS: dict[str, str] = {
    "request_signing": "#1291 (RFC 9421 request signing is not implemented)",
    "webhook_signing": "#1291 (RFC 9421 webhook signing is not implemented)",
    "identity": "#1291 (identity.brand_json_url/key_origins anchor signing keys we do not publish)",
    "content_standards": "#1291 (supports_webhook_delivery forces webhook_signing.supported=true)",
    "reporting_delivery_methods": "#1291 (declaring [webhook] forces webhook_signing.supported=true)",
    "offline_delivery_protocols": "#1291 (no offline report delivery is implemented)",
}


# The protocols a tenant may CLAIM. Derivation rule, applied uniformly: a protocol
# is backed iff every tool in its conformance bundle
# (`dist/compliance/3.1.1/protocols/<p>/index.yaml#required_tools`) is implemented
# in src/. Verified at v3.1.1:
#   media_buy   -> [get_products, create_media_buy]  : both implemented.
#   measurement -> NO protocol bundle exists (only brand, creative, governance,
#                  media-buy, signals, sponsored-intelligence), and
#                  #/properties/supported_protocols scopes 3.1 measurement to
#                  "get_adcp_capabilities catalog discovery" -- so the claim commits
#                  us to nothing beyond the catalog this batch implements.
# Deliberately ABSENT, same rule, opposite answer -- this is what keeps STRICT honest:
#   brand    -> [get_brand_identity] : ZERO hits in src/  -> #1724.
#   creative -> generative creative unimplemented         -> #1724.
#   signals     -> BACKED, but NOT by a get_signals tool. That justification was wrong:
#                  src/core/tools/signals.py was unreachable from every transport -- never
#                  registered on MCP, no REST route, no A2A skill -- because #826
#                  ("remove signals tools", 2025-12-09) removed the registration and left
#                  the implementation behind. The file is deleted.
#                  What actually backs the protocol is the signals-AGENT integration:
#                  src/services/dynamic_products.py queries signals agents to generate
#                  product variants (reachable through get_products), and
#                  src/admin/blueprints/signals_agents.py manages them. Still graded by the
#                  `signal-owned` accept scenario, which needs it as the parent protocol.
#                  NOTE the failure mode this row demonstrates: backing was checked by
#                  "does an implementation file exist" rather than "can a buyer reach it".
_BACKED_PROTOCOLS: frozenset[SupportedProtocol] = frozenset(
    {SupportedProtocol.media_buy, SupportedProtocol.measurement, SupportedProtocol.signals}
)

# What every response advertises before any declaration is applied. Lives HERE rather
# than in the tools layer because ``validate_backing`` must reason about the EMITTED
# protocol set (defaults unioned with the declaration) to check specialism roll-up --
# and a schema importing from src/core/tools would invert the layering.
# ``capabilities.py`` imports these as its single source for both the no-tenant and
# tenant-resolved constructions.
DEFAULT_SUPPORTED_PROTOCOLS: list[SupportedProtocol] = [SupportedProtocol.media_buy]
DEFAULT_SPECIALISMS: list[AdcpSpecialism] = [AdcpSpecialism.sales_non_guaranteed]

# The specialisms a tenant may CLAIM, hand-maintained with a per-entry justification.
#
# Deliberately NOT derived from `specialisms/<id>/index.yaml#required_tools`: that
# derivation would REJECT `sales-non-guaranteed`, which production already emits
# unconditionally (`_DEFAULT_SPECIALISMS`, capabilities.py) -- its bundle requires
# `sync_governance`, which has zero implementations here, plus 15 scenarios. Deriving
# would therefore regress the wire for every tenant. That pre-existing inconsistency is
# recorded, not "fixed" here; changing the default is a separate, wire-visible decision.
#
# Each entry states the bundle requirement and why this deployment meets it:
_BACKED_SPECIALISMS: dict[AdcpSpecialism, SupportedProtocol] = {
    # required_tools [sync_governance, get_products, create_media_buy], 15 scenarios.
    # PRE-EXISTING and unconditional -- see the note above. Kept so a tenant redeclaring
    # the default is not rejected for stating what we already advertise.
    AdcpSpecialism.sales_non_guaranteed: SupportedProtocol.media_buy,
    # required_tools [get_signals] ONLY, and requires_scenarios: 0. `get_signals` is
    # implemented (src/core/tools/signals.py). This is the one specialism a tenant can
    # declare that genuinely CHANGES the wire, which is what makes its accept scenario
    # non-vacuous rather than an echo of the default.
    AdcpSpecialism.signal_owned: SupportedProtocol.signals,
}


# The type parameter is VALUE-restricted (not bounded), which is what makes mixing the two
# branches a type error: passing protocols against the specialism backing map now fails with
# `Value of type variable "_Declared" cannot be "StrEnum"`, which `Iterable[Any]` silently
# accepted. Restricting here also means mypy.ini needs no new disallow_any_explicit entry
# for this module (#1721 review F7).
def _reject_unbacked[Declared: (SupportedProtocol, AdcpSpecialism)](
    claimed: Iterable[Declared],
    backed: Collection[Declared],
    *,
    field: str,
    noun: str,
    tracked_by: str | None = None,
) -> None:
    """Raise ``AdCPConfigurationError`` if ``claimed`` contains a value ``backed``
    does not cover.

    Shared shape for the ``supported_protocols`` and ``specialisms`` platform-backing
    checks (#1721 M1 / D1 -- was duplicated verbatim). ``backed`` may be
    a frozenset (protocols) or a dict keyed by the claimed enum (specialisms) --
    ``in`` and iteration both work identically for either.
    """
    from src.core.exceptions import AdCPConfigurationError

    unbacked = sorted({v.value for v in claimed if v not in backed})
    if not unbacked:
        return
    raise AdCPConfigurationError(
        # The axis name was IN THE KEY (f"unbacked_{field}"), so no single read
        # found it. It is a value now, like every other capability refusal.
        details=ConfigurationDetails(
            capability=field,
            rejected_value=unbacked,
            accepted_values=sorted(b.value for b in backed),
            tracked_by=tracked_by,
        ),
    )


# Declaring a block whose surface is x-status:experimental obliges the agent to list
# the feature id: "Sellers that implement any experimental surface MUST list its
# feature id here" (#/properties/experimental_features). The ids are therefore
# DERIVED from the declared blocks, not echoed from operator config -- a bare echo
# would let a tenant declare the block while omitting the id the spec requires.
_EXPERIMENTAL_FEATURE_BY_BLOCK: dict[str, str] = {
    "measurement": "measurement.core",
    "trusted_match": "trusted_match.core",
}


class MeasurementDeclaration(LibraryMeasurementDeclaration):
    """The tenant's measurement vendor/metric catalog.

    ``extra="forbid"`` is RESTATED because the library type is ``extra="ignore"``:
    inherited as-is, an operator's typo'd key would be silently dropped and their
    declaration would never reach the wire with no indication why. Metric field
    constraints (id pattern, 1..64 length, ``minItems``, ``Accreditation`` shape)
    ride the SDK unchanged.

    Declarable under STRICT: the catalog is a tenant business fact the response
    echoes. At 3.1 the measurement protocol is scoped to catalog discovery via
    ``get_adcp_capabilities``, so echoing it promises nothing further.
    """

    model_config = ConfigDict(extra="forbid")


class TrustedMatchDeclaration(LibraryTrustedMatch):
    """The tenant's deployed TMP surfaces.

    Extends the library type (Pattern #1) so the closed surface enum, uniqueItems
    and minItems come from the SDK rather than being restated here. Presence of the
    object is itself the signal that TMP infrastructure is deployed, which is a
    tenant-side operational fact -- not a protocol behavior this codebase has to
    implement -- so it is declarable under STRICT.
    """


def _union_sorted[EnumMember: Enum](defaults: list[EnumMember], declared: list[EnumMember] | None) -> list[EnumMember]:
    """Defaults unioned with a declaration, sorted by enum value.

    One body for the specialisms and supported_protocols emissions, which were
    the same set-union-then-sort expressed twice with a different lambda -- two
    copies of a rule ("declared ADDS to defaults, never replaces") that must not
    be able to diverge, because a divergence emits a self-inconsistent wire.
    """
    return sorted(set(defaults) | set(declared or []), key=lambda m: m.value)


class CapabilityDeclarations(BaseModel):
    """Implementation-backed capability blocks for one tenant.

    ``extra="forbid"`` is unconditional -- deliberately NOT
    ``get_pydantic_extra_mode()``. That helper relaxes to ``ignore`` in production
    for forward compatibility at the BUYER boundary, which is right for inbound
    requests and wrong here: this is operator configuration, and silently dropping
    a block an operator wrote means their declaration never reaches the wire with
    no indication why.
    """

    model_config = ConfigDict(extra="forbid")

    trusted_match: TrustedMatchDeclaration | None = None
    measurement: MeasurementDeclaration | None = None
    supported_protocols: list[SupportedProtocol] | None = None
    specialisms: list[AdcpSpecialism] | None = None

    @classmethod
    def from_tenant(cls, declared: Any) -> "CapabilityDeclarations":
        """Parse a tenant's stored declarations; an EMPTY instance when nothing is declared.

        Returns an empty declaration rather than ``None`` so callers can read it
        unconditionally. Every emission site had to write
        ``declarations.x if declarations else <default>``, which put the
        undeclared-tenant default in five places instead of one -- and each
        ternary was a chance to pick a different default than the emitted-union
        rules on this class already define. An empty instance answers every one
        of them correctly: the unions fall back to the defaults, and the optional
        blocks are None.

        The emitted wire for an undeclared tenant is unchanged (pre-#1592
        behavior), which is what every tenant that never declared anything must
        keep seeing.

        READ SIDE ONLY. Nothing here writes ``capability_declarations`` — the
        column is populated out of band (fixtures, operator SQL), which is why
        the undeclared-tenant path is the one every scenario actually exercises
        and why "operator declares X, then a buyer sees X" cannot be graded end
        to end today. The write seam is #1856; when it lands, the round trip
        becomes gradeable and the defaults above stop being the only covered branch.
        """
        from src.core.exceptions import AdCPConfigurationError

        if not declared:
            return cls()
        if not isinstance(declared, dict):
            raise AdCPConfigurationError(
                details=ConfigurationDetails(received_type=type(declared).__name__),
            )

        # Name unbacked blocks explicitly, before pydantic's generic extra-field
        # error, so the operator learns WHICH promise they cannot keep and where
        # the work is tracked.
        for block in sorted(_UNBACKED_BLOCKS):
            if block in declared:
                raise AdCPConfigurationError(
                    details=ConfigurationDetails(block=block, tracked_by=_UNBACKED_BLOCKS[block]),
                )

        # ValidationError only -- never a broad `except Exception`, which would
        # flatten any typed AdCPSalesAgentError raised from a nested validator into a
        # generic CONFIGURATION_ERROR and lose its code
        # (guard: test_architecture_no_error_flattening).
        try:
            parsed = cls.model_validate(declared)
        except ValidationError as exc:
            raise AdCPConfigurationError(
                internal_detail=exc,
                details=ConfigurationDetails(capability="capability_declarations", rejected_value=sorted(declared)),
            ) from exc

        parsed.validate_backing()
        return parsed

    def validate_backing(self) -> None:
        """Cross-field and platform-backing rules the JSON Schema cannot express.

        Rule ORDER is load-bearing: spec cross-field coherence runs BEFORE platform
        backing, so when the signing family lands under #1291 an identity rejection
        still names ``brand_json_url`` rather than being pre-empted by a backing
        error. No rule lands here without a scenario that executes it.
        """
        from src.core.exceptions import AdCPConfigurationError

        # Platform backing: a tenant may only claim protocols/specialisms this
        # deployment actually serves. Advertising an unserved one is the exact
        # over-promise STRICT exists to prevent -- the buyer would route traffic
        # for a domain we cannot answer. `creative-generative` is the specialisms
        # scenario's case -- nothing implements generative creative, and the AAO
        # runner grades the claim.
        _reject_unbacked(
            self.supported_protocols or [],
            _BACKED_PROTOCOLS,
            field="supported_protocols",
            noun="required tool surface",
        )
        _reject_unbacked(
            self.specialisms or [],
            _BACKED_SPECIALISMS,
            field="specialisms",
            noun="tools the specialism's conformance bundle requires",
            tracked_by="Generative creative is tracked by #1724.",
        )

        # Roll-up coherence: "the runner rejects a specialism claim whose parent
        # protocol is missing" (#/properties/specialisms). Checked against the
        # EMITTED protocol set, not the declared one, because the defaults are
        # unioned in -- a tenant declaring only `signal-owned` still gets media_buy.
        emitted_protocols = set(self.emitted_supported_protocols(DEFAULT_SUPPORTED_PROTOCOLS))
        orphaned = sorted(
            f"{s.value} (needs {_BACKED_SPECIALISMS[s].value})"
            for s in (self.specialisms or [])
            if s in _BACKED_SPECIALISMS and _BACKED_SPECIALISMS[s] not in emitted_protocols
        )
        if orphaned:
            raise AdCPConfigurationError(
                details=ConfigurationDetails(
                    capability="specialisms",
                    rejected_value=orphaned,
                    accepted_values=sorted(p.value for p in emitted_protocols),
                ),
            )

    def emitted_specialisms(self, defaults: list[AdcpSpecialism]) -> list[AdcpSpecialism]:
        """Defaults UNIONED with the declaration -- same rule as protocols."""
        return _union_sorted(defaults, self.specialisms)

    def emitted_supported_protocols(self, defaults: list[SupportedProtocol]) -> list[SupportedProtocol]:
        """Defaults UNIONED with the declaration -- never replaced.

        Replacing would drop ``media_buy`` and leave the unconditionally-emitted
        ``sales-non-guaranteed`` specialism without its parent protocol, which the
        spec forbids: #/properties/specialisms -- "the runner rejects a specialism
        claim whose parent protocol is missing"
        (``specialisms/sales-non-guaranteed/index.yaml#protocol`` -> ``media-buy``).
        A replacing semantics would therefore emit a self-inconsistent wire.
        """
        return _union_sorted(defaults, self.supported_protocols)

    def emitted_experimental_features(self) -> list[ExperimentalFeature] | None:
        """Feature ids DERIVED from the declared experimental blocks.

        Derivation, not echo. ``#/properties/experimental_features`` obliges an
        agent implementing an experimental surface to list its id, so the ids
        follow from which blocks were declared -- a tenant cannot declare
        ``measurement`` and omit ``measurement.core``, and cannot invent an id for
        a block it did not declare.

        There is deliberately NO declarable ``experimental_features`` field. The
        one scenario that would grade an operator-supplied list
        (``T-UC-010-v31-experimental-features``) demands ``brand.rights_lifecycle``
        -- an unbacked surface re-homed to #1724 -- so a declarable half would ship
        with no grader, which this codebase does not allow.
        """
        ids = sorted(
            feature_id
            for block, feature_id in _EXPERIMENTAL_FEATURE_BY_BLOCK.items()
            if getattr(self, block) is not None
        )
        return [ExperimentalFeature(root=i) for i in ids] or None


# Every key in the table must name a real declarable block. With the previous
# `getattr(self, block, None)` a key that no longer matched a field simply read as
# "not declared", so renaming a block would silently stop emitting its experimental
# feature id -- a wire regression with nothing to fail. Checked at import so the
# mismatch is a startup error, not a quietly shorter list on a buyer's response.
_UNKNOWN_BLOCKS = sorted(set(_EXPERIMENTAL_FEATURE_BY_BLOCK) - set(CapabilityDeclarations.model_fields))
if _UNKNOWN_BLOCKS:
    raise RuntimeError(
        f"_EXPERIMENTAL_FEATURE_BY_BLOCK names blocks that are not fields of "
        f"CapabilityDeclarations: {_UNKNOWN_BLOCKS}. Their experimental feature ids would "
        f"never be emitted."
    )
