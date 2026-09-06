# One tool registry: what is left

Companion to [One tool registry](one-tool-registry.md). Every step of that document's
migration order has landed. This one says what still stands between the tree and the design's
own sentence:

> A tool is declared ONCE. Everything else is derived.

The target shape, entire:

```
transport receives bytes
  -> compat middleware                    (legacy wire shapes -> spec shapes)
  -> validate into the row's DTO          (the standard schema, nothing else)
  -> resolve the account the request names
  -> honour the idempotency key it carries
  -> impl(req, identity)
```

Five steps, in that order, identical on every transport. No transport with a step of its own,
and nothing between them. Compatibility is the FIRST step and the only place a shape AdCP
does not define may be seen; after it, everything downstream sees the pinned schema.

## Where the tree is

Steps 6-9 made the SECOND half true. `invoke_tool` is one path and all three transports take
it. What they do BEFORE reaching it is still three different programs.

| Half | Declared once? | Evidence |
|---|---|---|
| request -> implementation | yes | `_boundary.invoke`, one call site per transport |
| bytes -> request | **no** | MCP derives a signature from the DTO; REST derives a body model from the DTO; A2A runs 11 hand-written skill handlers |

R1 is that asymmetry. R2 is the type discipline the seam should have had from the start, and
it deletes R1's worst symptom. R3-R5 are each one thing being done in the wrong place.

---

## R1 — Generate A2A dispatch from the registry

**The defect.** `src/a2a_server/adcp_a2a_server.py` carries 11 `_handle_<tool>_skill` methods
and a `skill_handlers` dict built by `hasattr`. Three live consequences:

* The card advertises 14 skills (`_derived_skills()` reads `TOOLS`, correctly) and dispatches
  11. `list_tasks`, `get_task_status` and `complete_task` are declared `a2a=True`, appear on
  the card, and answer `MethodNotFoundError`. A `hasattr` filter silently overrides a registry
  declaration.
* Each handler coerces its own parameters -- 12 call sites across `to_account_reference`,
  `to_brand_reference`, `coerce_creative_filters`, `upgrade_legacy_format_id`,
  `to_context_object`. MCP and REST run none of them.
* `_coerce_wire_object` (`src/core/schema_helpers.py:66`) returns `None` for anything that is
  not a dict. `{"account": "acct_1"}` -- which `core/account-ref.json` does not permit --
  becomes `None` on A2A and raises on MCP and REST. For the seven tools whose `account` is
  optional the request then proceeds **with no account scope at all**: no authorization
  against that account, and a different idempotency scope. Same bytes, two answers, one
  silent, on the field that decides both.

**The change.** One handler, derived:

```python
async def _handle_skill(self, skill_name: str, parameters: dict, identity) -> Any:
    return await invoke_tool(skill_name, TOOLS[skill_name].validate(parameters), identity)
```

Delete the 11 methods and the `hasattr` filter. A row dispatches because it is in the
registry, not because someone wrote a matching method name.

**What happens to the coercions.** Measured, not assumed. Pydantic already does four of the
five, unaided, on the plain dict a buyer sends:

```
{"account":  {"account_id": "acct_1"}}   -> AccountReference
{"filters":  {"tags": ["promo"]}}        -> CreativeFilters
{"brand":    {"domain": "b.com"}}        -> BrandReference
{"context":  {"conversation_id": "c1"}}  -> ContextObject
```

`to_account_reference`, `coerce_creative_filters`, `to_context_object` and the dict arm of
`to_brand_reference` are therefore doing work the DTO does anyway. They DELETE. They are also
worse than redundant: `_coerce_wire_object` returns `None` for a non-dict, so where pydantic
would raise, A2A silently drops -- which is the finding above.

Two are genuine wire-compatibility REWRITES, accepting a shape the pinned schema does not:

| Rewrite | Input | Result |
|---|---|---|
| `to_brand_reference` | `"Acme"` | `BrandReference(domain="acme")` |
| `upgrade_legacy_format_id` | `"display_300x250"` | `FormatId(agent_url=<default agent>, id=...)` |

**Both belong in the compat layer, and it already exists.** `normalize_request_params`
(`src/core/request_compat.py`) translates deprecated wire shapes into current ones BEFORE
validation, and it is already wired to all three transports -- `mcp_compat_middleware.py:137`,
`rest_compat_middleware.py:58`, `adcp_a2a_server.py:1644`. It already performs exactly this
class of rewrite; `account_id (string) -> account: {account_id}` is one of its existing rules.

So the two rewrites MOVE THERE and stop being A2A-only. They do not belong on the DTO either:
a DTO is the pinned schema, and putting a legacy shorthand in a `BeforeValidator` would make
the model accept a shape AdCP does not define -- the same mistake as declaring a non-spec
field, just spelled as behaviour instead of a field.

The layering the whole design wants:

```
wire bytes -> compat middleware (legacy shapes -> spec shapes) -> DTO (pinned schema) -> boundary -> impl
```

One normalizer, before validation, for every transport. Nothing per-skill and nothing after.
Today a bare-string `brand` is accepted on A2A and `ValidationError` on MCP and REST, which is
what happens when the rewrite lives past the point where all transports converge.

**On protobuf.** Nothing here parses binary protobuf -- there is no `SerializeToString` or
`ParseFromString` anywhere in `src/`. The A2A path is `json_format.MessageToDict` over a
`Struct`, so `parameters` is a plain JSON-shaped dict by the time a handler sees it, and
pydantic can validate it directly. Any handling written for a binary-protobuf assumption is
dead code. The one real Struct artifact is that it has no integer type -- every number arrives
as a double -- and pydantic's non-strict mode already coerces `2.0` to an `int` field.

## R2 — Requests and responses each get one base, and the boundary stops probing

**The defect.** `invoke_tool(tool_name: str, req: Any, identity: Any, **extra: Any) -> Any`.
Because `req` is `Any`, the boundary asks four questions it should already know the answer to:
`getattr(req, "account")`, `getattr(req, "idempotency_key")`, `getattr(result, "status")`,
`"replayed" in model.model_fields`. Each probe is a place where a wrong object passes quietly.

**The change, and why it is not generics.** An earlier draft proposed making `ToolSpec` generic
and casting at the registry literal. That is the wrong shape: it buys a static check and leaves
every probe in place. The right shape is that a request IS a thing with those accessors.

All 14 request DTOs already share `AdcpVersionEnvelope -> AdCPBaseModel -> BaseModel`. Add one
local mixin above the SDK parent declaring the two accessors the boundary needs:

```python
class BuyerRequest(BaseModel):
    """What the boundary may ask any request, whether or not its schema declares it."""

    @property
    def account(self) -> AccountReference | None: return None
    @property
    def idempotency_key(self) -> str | None: return None
```

A DTO whose pinned schema declares the field shadows the property with the real pydantic
field; one that does not inherits `None`. **Nothing is added to the wire** -- a property is not
a model field, so `model_dump`, `model_fields` and the announced shape are untouched, and the
"the DTO is the SDK model, nothing added" rule holds. `req.account` then always works, and
`_spec_declares_idempotency_key` becomes what it always meant: does this DTO override the
property with a real field.

Responses are the same move and it is R3 as well -- see below.

Then `invoke_tool(tool_name: str, req: BuyerRequest, identity: ResolvedIdentity | None) -> AdcpResponse`,
and the four probes become attribute access.

---

## R3 — `replayed` comes from the envelope, because the envelope is a base class

**The defect.** Three of the four keyed tools replay with no `replayed` marker, and
`update_media_buy` is worse than silent: `UpdateMediaBuySubmitted` declares
`replayed: bool = False` while `TaskResultEnvelope._serialize` lacks the pop-and-reset that
`CreateMediaBuyResult._serialize` performs, so a replayed submitted update goes on the wire as
`replayed: false` -- positively asserting a fresh execution to a buyer using the field for
billing reconciliation and exactly-once routing.

**Why it is the same change as R2.** `replayed` is not a per-tool field to be added four times.
It is a field of `core/protocol-envelope.json`, which every pinned response schema composes via
`allOf`, and the SDK ships the class: `adcp.types.ProtocolEnvelope`, carrying `replayed`,
`status`, `task_id`, `message`, `context`, `errors` and the rest.
`GetAdcpCapabilitiesResponse` already inherits it. The other thirteen do not, because the SDK's
codegen dropped the composition for them.

**The change.** Every response model inherits `ProtocolEnvelope`. The envelope has the field, so
the derived models have it -- no per-tool declaration, no `model_fields` probe, no `setattr`
with a `noqa`. The boundary assigns `result.replayed = True` on replay and that is the whole
mechanism. `TaskResultEnvelope`'s duplicated pop-and-reset goes too.

---

## R4 — A failure is an exception; delete the status check

**The defect.** `_boundary._is_error_result` inspects the returned response's protocol status to
decide whether to cache it. It exists for exactly one caller: `media_buy_create.py:3605`, where
an adapter error is wrapped in `CreateMediaBuyResult(status="failed")` and RETURNED. Every other
tool raises.

That check is also inert where it looks most useful: `SyncCreativesResponse.status` and
`SyncAccountsResponse.status` are `Literal["completed"]`, so for two of the four keyed tools it
can never fire. Those tools are protected by the raise, not by the check -- which the docstring
does not say.

**The change.** Make that one site raise the typed `AdCPSalesAgentError` the adapter error
already carries, like every other failure path in the tree. Then:

* `_is_error_result` and `_FAILED_STATUSES` are deleted -- **a return IS a success**, which is
  the only rule the boundary needs;
* rule 3 ("only successful responses are cached") is enforced by control flow rather than by
  inspecting a value;
* `CreateMediaBuyError` stops being a response variant the buyer can receive on a return, which
  is the same shape every other tool already has.

The wire is unchanged: the transports translate a raised `AdCPSalesAgentError` into the same
two-layer envelope they build for every other tool's failures.

---

## R5 — DONE: controller and service

Landed. `_sync_creatives_impl` is now a controller that resolves the caller and delegates to
`sync_creatives`, a service taking an already-resolved caller and doing no auth, no transport
work and no idempotency. `create_media_buy` and `update_media_buy` call the SERVICE.

The borrowed key is gone with it: the nested request carries its own internal
`idempotency_key` (the schema requires one, the service never reads it) rather than the outer
buyer's. `test_nested_creative_sync_borrowed_key.py`, which existed to bless that borrowing,
is deleted -- along with three strict xfails whose own instructions said to remove them the
moment `ListAccountsRequest` stopped declaring a non-spec `idempotency_key`. It has.

The pattern is written up in CLAUDE.md, critical pattern #5: **a controller never calls
another controller.** `sync_creatives` is the one service extracted so far; extract the next
when a second tool needs it, not before.

## R6 — Concurrent same-key requests

**Where the rules come from.** The nine numbered rules cited throughout this document are the
pinned spec's own: `docs/building/by-layer/L1/security.mdx`, section "Idempotency", subsection
"Normative seller behavior", in `github.com/adcontextprotocol/adcp` at the version this repo
pins. The prose is not vendored; read it with
`gh api repos/adcontextprotocol/adcp/contents/docs/building/by-layer/L1/security.mdx --jq '.content' | base64 -d`.
Rule 9 is "Concurrent retries -- first-insert-wins".

**The defect.** Not implemented. The rule requires the attempt row to be written BEFORE the work,
carrying the canonical payload hash (explicitly not a sentinel), so a second concurrent request
observes a row whose response slot is empty and answers `IDEMPOTENCY_IN_FLIGHT`. That code is in
the pinned error enum and appears nowhere in `src/`.

Today the second concurrent `create_media_buy` runs the adapter to completion before the
`media_buys` unique index fires -- the code says so in its own words: "An orphan adapter-side
order may exist." The other three keyed tools have no backstop index at all, so both requests
simply apply.

**The change** is the one already described: write the row with the hash, run, complete the row;
answer `IDEMPOTENCY_IN_FLIGHT` on a collision with an incomplete row. It subsumes
`_raise_degraded_replay_outcome`'s transient branch and closes the adapter double-execution
window.

**Can BDD grade it today? No.** The only scenario row in the tree that names
`IDEMPOTENCY_IN_FLIGHT` is in `BR-UC-028-manage-collection-lists.feature`, which is on the
UNBOUND allowlist (`test_architecture_feature_file_bound.py`) for a tool this seller does not
implement -- so it never executes. There is no concurrency in the BDD harness and none is
needed.

**And it does not need concurrency to be gradable.** The observable state is a row: an
attempt whose payload hash is populated and whose response slot is empty. A Given seeds that
row -- the same shape `seed_cached_success` already provides for the replay case -- and the
When dispatches a second request with the same key. The response is `IDEMPOTENCY_IN_FLIGHT`
whether the first request is genuinely still running or merely recorded as such, because the
seller cannot tell the difference either; that is the whole point of writing the row first.

So the work is: write the attempt row before running, complete it after, answer
`IDEMPOTENCY_IN_FLIGHT` on a collision with an incomplete row -- and one BDD scenario with a
`seed_incomplete_attempt` Given, wired to a bound feature, to grade it on all four
transports.

**Priority: lowest.** It needs concurrent same-key traffic to occur in production, and few
sellers implement it. It is listed because the enum member exists, the gap should be known,
and the grading cost turns out to be one Given.

---

## Order

R1 first: it is the missing half of the thesis. R2 and R3 are one change and can go first if a
buyer is watching, since R3 is a wire-visible falsehood today. R4 is small and deletes code. R5
is independent. R6 last.
