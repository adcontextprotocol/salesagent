# Architecture principles

The rules that decide where code belongs in this codebase — and why. The
mechanics of how a request reaches business logic are in
[request-lifecycle.md](request-lifecycle.md); the boundary contract with
canonical examples is Critical Pattern #5 in [CLAUDE.md](../../CLAUDE.md) and
[patterns-reference.md](patterns-reference.md). This document is the layer
above both: six principles, each short enough to apply on sight.

The whole architecture is one symmetry:

```
wire ──► boundary: construct models, resolve identity ──► _impl(models → models) ──► boundary: serialize models ──► wire / DB / egress
```

Models are constructed on the way in, serialized on the way out, and the code
in the middle never touches anything else.

## 1. Logic lives in `_impl` — everything else is infrastructure

**Rule.** Business logic lives in exactly one place: the `_impl` functions
under `src/core/tools/`. Everything before and after them — transports,
identity resolution, error translation, envelope parsing and creation — is
infrastructure. If logic appears outside `_impl`, that placement is the
defect, regardless of whether the logic is correct.

**Illustration.** A budget rule added to the REST handler in
`src/routes/api_v1.py` is logic that the MCP and A2A callers never run. The
same rule inside `_create_media_buy_impl` runs identically for all transports,
because every wrapper calls the same function with the same
`ResolvedIdentity`.

**Consequence.** Adding a transport, or fixing a transport bug, never changes
behavior; changing behavior never touches a transport. Structural guards
enforce the boundary: `_impl` may not import transport machinery
(`tests/unit/test_transport_agnostic_impl.py`), must accept `ResolvedIdentity`
rather than a transport context (`tests/unit/test_impl_resolved_identity.py`),
and every wrapper must forward every `_impl` parameter
(`tests/unit/test_architecture_boundary_completeness.py`). When unsure where a
change goes, use the [placement
table](request-lifecycle.md#where-does-my-change-go) in the request lifecycle.

## 2. Trust the database — never validate on read

**Rule.** The application wrote every row in the database, and the stored
structures are designed so that nothing the application stores can crash it.
Therefore **reads do not validate**: read into Pydantic models and proceed. No
`try/except` around parsing the application's own rows, no fallback branches
for data the write path never produces, no re-checking invariants that the
write path already guaranteed.

**Illustration.** JSON columns are declared with a model —
`JSONType(model=BrandReference)` in `src/core/database/json_type.py` — so the
column type itself materializes a typed model on read and serializes the model
on write. A repository method returns those models directly; the caller does
not first inspect them for well-formedness.

**Consequence.** Defensive re-validation is the instinct most newcomers arrive
with, and in this codebase it is the anti-pattern: it duplicates the write
path's guarantee, buries real bugs under fallbacks, and makes every read site
a policy decision. If a read *does* fail, the defect is on the write path (or
in a migration) — fix it there once, not at every read site. The typed-column
and repository layers plus code review carry this principle, rather than a
single structural guard; one defensive pattern is banned directly by
`tests/unit/test_architecture_no_defensive_rootmodel.py` (no
`hasattr(x, "root")` unwrapping). Bare `JSONType` columns with no model are
legacy; a column you add always declares one.

## 3. Pydantic models everywhere inside business logic

**Rule.** `_impl` receives models, works with models, and returns models —
never dicts. A dict has no schema, so every consumer re-derives the structure,
and none of those derivations can be checked.

**Illustration.** `_create_media_buy_impl` takes a `CreateMediaBuyRequest` and
returns a result model; it never sees the JSON-RPC params, the HTTP body, or a
`kwargs` dict of loose fields.

**Consequence.** The type checker and the schema guards see every field
access. Wrapper signatures must use SDK types rather than `Any`/`dict`
(`tests/unit/test_architecture_wrapper_typed_params.py`), so models arrive
typed at the boundary and stay typed until the boundary serializes them.

## 4. Construction and serialization happen at the boundary — never in `_impl`

**Rule.** This principle is the symmetry at the heart of the design:

- **Inbound**: The boundary constructs the Pydantic request model — the
  compatibility middlewares normalize the wire format and the route/tool
  wrapper parses it
  ([request-lifecycle.md](request-lifecycle.md#backward-compatibility-at-the-boundary)).
- **Outbound, response**: `_impl` returns a response model and stops. It does
  not build the response — the transport converts the model automatically, and
  wire serialization lives in one place (`WireSerializerMixin` in
  `src/core/schemas/_base.py`, enforced by
  `tests/unit/test_architecture_one_wire_serializer_seat.py`).
- **Outbound, database**: `_impl` hands models to repositories; it does not
  build dicts to store. `MediaBuyRepository.create_from_request`
  (`src/core/database/repositories/media_buy.py`) serializes the request at
  the DB boundary for exactly this reason, and `JSONType` serializes model
  values on write.
- **Outbound, external calls**: Egress goes through the egress gateway
  (`src/core/security/outbound_http.py`), which owns the wire-level concerns.

**Illustration.** A `model_dump()` inside `_impl` signals the violation: it
means business logic is deciding a wire or storage format. The guard
`tests/unit/test_architecture_no_model_dump_in_impl.py` bans the call outright
— its allowlist is empty.

**Consequence.** Serialization decisions (aliases, exclusions, spec-pinned
nullable fields) are made once, at boundaries that every transport shares, instead
of being re-decided per call site. Repositories are the only DB writers
(`tests/unit/test_architecture_repository_pattern.py`).

## 5. Errors: typed raises inside, envelopes at the boundary

**Rule.** `_impl` signals failure by raising a typed `AdCPError` subclass
(`src/core/exceptions.py`) — and nothing else. The boundary translator builds
the buyer-facing envelope; the raise site never authors it.

**Illustration.** A validation failure raises `AdCPValidationError`; the
boundary runs `build_two_layer_error_envelope()` (`src/core/exceptions.py`)
and emits the transport's error format — REST envelope + HTTP status, MCP
`isError` tool error, A2A failed Task — all through `record_boundary_error`.

**Consequence.** The error class *is* the wire code's identity, so a new error
condition is a new subclass, not a string. Guards enforce both sides of the
boundary: no `ToolError` in `_impl`
(`tests/unit/test_no_toolerror_in_impl.py`), no `Error(code=...)` construction
in business logic
(`tests/unit/test_architecture_no_error_construction_in_impl.py`), no
`error_code=` kwarg bypassing the hierarchy
(`tests/unit/test_architecture_no_error_code_kwarg_in_impl.py`), and every
boundary must call the two-layer envelope builder
(`tests/unit/test_architecture_error_envelope_two_layer.py`).

## 6. The consequence for tests — derived, not decreed

Because of principle 1, logic exists in exactly one transport-agnostic place.
BDD therefore verifies **logic**, and Given/When/Then steps are
transport-independent by construction: the same scenario text runs against
every transport. It follows that response and error assertions must go through
**transport-independent helpers** — `assert_envelope_shape()`
(`tests/helpers/envelope_assertions.py`) against `result.wire_error_envelope`
for error paths, and `wire_response` or the typed payload for success paths
(policy: [tests/CLAUDE.md](../../tests/CLAUDE.md) § "Error Verification
Policy").

A test that reaches for a transport's own representation — parsing an HTTP
body by hand, unpacking a Task artifact inline — steps outside what the
scenario verifies: it tests one transport's framing, which the scenario never
claimed to specify. Guards enforce the discipline
(`tests/unit/test_architecture_bdd_wire_discipline.py`,
`tests/unit/test_architecture_bdd_no_direct_call_impl.py`).

BDD assertions that reconstruct the error class (`isinstance`, `.error_code`)
are legacy and are being removed; write assertions with the
transport-independent wire helpers instead.

## Planned convergence: one request DTO, one error code table (PR #1721)

PR #1721 is **in flight, not merged**. It refines the following details; the
six preceding principles are already the rule. Do not write code against the
constructs it removes:

- **`CODE_TABLE` becomes the sole authority** for a buyer-facing `message`,
  `suggestion`, and `recovery`. `AdCPError` has no `message` parameter, so no
  raise site can author buyer-facing text; provenance-bearing text goes to
  `internal_detail`, which is server-log only.
- **An error's `details` is a declared class**, not a free-form dict —
  `AdCPError` is generic in its detail type.
- **Error verification converges on exactly one mechanism.** The `IMPL`
  pseudo-transport, `synthesized_error_envelope`, and the `ImplDispatcher` are
  removed: all three compute an envelope from the same in-memory exception
  that the assertion then reads, so a regression in the production boundary
  translator cannot change the result. Error-path tests run on a wire
  transport.
- **Request parsing converges on a single request data transfer object
  (DTO)**, with errors raised and conversions performed at the boundary.

If you are choosing between "raise with a hand-written message" and "pick the
right typed error and let the table supply the text", choose the latter — it
is correct today and remains correct after #1721 lands.
