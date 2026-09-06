# One tool registry: what is left

Companion to [One tool registry](one-tool-registry.md). Every step of that document's
migration order has landed. This one says what still stands between the tree and the design's
own sentence:

> A tool is declared ONCE. Everything else is derived.

The target shape, entire:

```
transport receives bytes
  -> compat middleware                    (legacy wire shapes -> spec shapes)   [ABSENT]
  -> validate into the row's DTO          (the standard schema, nothing else)
  -> resolve the account the request names
  -> honour the idempotency key it carries
  -> impl(req, identity)
```

Five steps, in that order, identical on every transport. No transport with a step of its own,
and nothing between them. Compatibility is the FIRST step and the only place a shape AdCP
does not define may be seen; after it, everything downstream sees the pinned schema.

The compat step is ABSENT rather than misplaced: it was deleted whole (613044223) because it
had become a rewrite running in three different places, and it comes back as one designed
layer or not at all -- prebid/salesagent#2218 carries the eleven rules it held. The other four
steps run, in that order, on every transport.

## Where the tree is

Steps 6-9 made the SECOND half true. `invoke_tool` is one path and all three transports take
it. What they do BEFORE reaching it is still three different programs.

| Half | Declared once? | Evidence |
|---|---|---|
| request -> implementation | yes | `_boundary.invoke`, one call site per transport |
| bytes -> request | yes | all three derive the accepted shape from the row's DTO |

That asymmetry was R1, and it is closed. R2 is the type discipline the seam should have had
from the start. R3-R5 were each one thing being done in the wrong place. R1, R3 and R5 are
done; R2 and R4 are not.

---

## R1 — DONE: generate A2A dispatch from the registry

Landed. `_dispatch_skill` is the whole of A2A's request path: validate the parameter bag into
the row's DTO, call `invoke_tool`, serialize. The `message` half of the response seam landed
with it -- see the response-half section below for what remains.

**The defect, as it stood.** `src/a2a_server/adcp_a2a_server.py` carried 11
`_handle_<tool>_skill` methods and a `skill_handlers` dict built by `hasattr`. Three live
consequences:

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

`to_account_reference`, `coerce_creative_filters`, `to_context_object` and the dict branch of
`to_brand_reference` are therefore doing work the DTO does anyway. They DELETE. They are also
worse than redundant: `_coerce_wire_object` returns `None` for a non-dict, so where pydantic
would raise, A2A silently drops -- which is the finding above.

Two are genuine wire-compatibility REWRITES, accepting a shape the pinned schema does not:

| Rewrite | Input | Result |
|---|---|---|
| `to_brand_reference` | `"Acme"` | `BrandReference(domain="acme")` |
| `upgrade_legacy_format_id` | `"display_300x250"` | `FormatId(agent_url=<default agent>, id=...)` |

**Both were deleted with the rest of the compat layer.** `normalize_request_params` and
`RestCompatMiddleware` are gone (613044223), as is the v2 response compat (66cf2e979). The
eleven rules they carried are recorded on prebid/salesagent#2218 so the replacement is
designed rather than reconstructed. Compat returns as ONE layer, before validation, for every
transport -- or not at all. It does not belong on the DTO either: a DTO is the pinned schema,
and putting a legacy shorthand in a `BeforeValidator` would make the model accept a shape AdCP
does not define, which is the same mistake as declaring a non-spec field, spelled as behaviour
instead of a field.

The layering the whole design wants:

```
wire bytes -> compat middleware (legacy shapes -> spec shapes) -> DTO (pinned schema) -> boundary -> impl
```

One layer, before validation, for every transport. Nothing per-skill and nothing after. The
per-skill rewrites were what made a bare-string `brand` acceptable on A2A and a
`ValidationError` on MCP and REST -- the same bytes, two answers, because the rewrite lived
past the point where the transports converge.

**On protobuf.** Nothing here parses binary protobuf -- there is no `SerializeToString` or
`ParseFromString` anywhere in `src/`. The A2A path is `json_format.MessageToDict` over a
`Struct`, so `parameters` is a plain JSON-shaped dict by the time a handler sees it, and
pydantic can validate it directly. Any handling written for a binary-protobuf assumption is
dead code. The one real Struct artifact is that it has no integer type -- every number arrives
as a double -- and pydantic's non-strict mode already coerces `2.0` to an `int` field.

## R2 — DONE: the boundary stops probing

**The defect.** `invoke_tool(tool_name: str, req: Any, identity: Any = None, **extra: Any) -> Any`.
Because `req` is `Any`, the boundary asks three questions it should already know the answer to:
`getattr(req, "account")` (:233), `getattr(req, "idempotency_key")` (:207) and
`getattr(result, "status")` (:187, :273). Each probe is a place where a wrong object passes
quietly.

There were four. `"replayed" in model.model_fields` went with R3, which is the evidence that
this works: once every response inherited `ProtocolEnvelope`, the probe became an assignment
and `_response_model_for` could be typed `type[ProtocolEnvelope]`. The three above are the same
move on the REQUEST side, which R3 did not touch.

**What landed, and why it is not the `BuyerRequest` mixin this section proposed.** The plan
called for a local base declaring `account` and `idempotency_key` as PROPERTIES returning None,
on the reading that a DTO whose schema declares the field would shadow the property with a real
pydantic field. Measured on the pinned pydantic, the shadowing runs the other way:

```
class D(BuyerRequest):  account: str | None = None
d = D(account="acct-1")
    d.__dict__["account"]  ->  "acct-1"       # the value IS stored
    d.model_dump()         ->  {"account": "acct-1"}
    d.account              ->  None            # the PROPERTY wins
```

Following it would have made `req.account` None for all ten tools that declare an account and
`req.idempotency_key` None for all four that declare a key -- no authorization against the
named account, no replay, and nothing failing. That is the defect class this whole document
exists to remove, so the design is recorded as REJECTED rather than left to be rediscovered.

What landed instead keeps the conditional, because the conditional is real, and moves WHERE the
question is asked. `_declared(req, name)` consults `type(req).model_fields` -- the DECLARATION
-- and then reads the attribute. `getattr(req, name, None)` asked the INSTANCE and answered
None for anything lacking the attribute, including an object that is not a request at all,
which then ran unscoped. A non-model now raises here instead.

The signatures are typed: `invoke_tool(tool_name: str, req: BaseModel, identity:
ResolvedIdentity | None = None, **extra) -> ProtocolEnvelope`. `getattr(result, "status")` is
gone outright -- a response IS a `ProtocolEnvelope`, so `result.status` is attribute access,
which is R3's dividend arriving on the request side.

**The response side is already done, by R3.** Every response model inherits `ProtocolEnvelope`
rather than a hand-written mixin, because the SDK ships that class and the pinned schemas
compose it. Same principle either way: the boundary says `result.replayed = True` because a
response IS a thing with that attribute, not because it probed for one. `to_wire` is typed
`ProtocolEnvelope` for the same reason. Only the request half is left.

### The response half of R1: DONE -- one body, three wrappers

`src/core/tools/_wire.py::to_wire` is the only place a response model becomes a body. MCP puts
the result in `ToolResult.structured_content`, A2A in an artifact `DataPart`, REST returns it
as the HTTP body. Those containers are the only thing that legitimately differs; what goes
inside is the same bytes.

What it replaced, and what each row cost:

| | MCP | A2A | REST |
|---|---|---|---|
| body | three separate `model_dump(mode="json")` calls | | |
| human summary | `str(response)` -> `ToolResult.content`, OUTSIDE the body | `str(response)` -> `["message"]`, INSIDE the body | nothing |
| adds | -- | `["success"]`, a key no pinned response schema of ours declares | -- |
| version compat | -- | per-handler, and DEAD (it stamped first, then passed a dict to a function whose dict branch is a no-op) | inline |
| top-level shape | `ToolResult` | DataPart | bare dict |

Only the last row was ever per-transport. `message` became a declared field the implementation
fills, so all three emit it -- REST had emitted none. `success` was deleted rather than moved:
measured across the whole pinned 3.1 tree, only three response schemas declare a `success`
property and none is one of our fourteen, and it had no consumers. Version compat went with the
rest of v2 compat.

That also removed the harness exception the stamping had forced.
`strip_a2a_protocol_fields` popped `message` and `success` off an A2A body before validating
it, justified as "neither is declared on any response model" -- true of `message` until it
became a field, after which the harness was stripping a real envelope field before looking at
it, so nothing graded that A2A's `message` matches REST's.

`test_architecture_one_wire_body.py` holds the line: each transport's response path must call
`to_wire`, must not serialize the response itself, and must not assign into the body
afterwards.

**`__str__` is gone too.** 23 methods across `src/core/schemas/` each produced one English
sentence from fields the buyer already had, and each transport decided separately what to do
with it. The summary is now the `message` field, set by the implementation --
`sync_creatives` had been building a richer one and discarding it. The SDK's own
`model_summary()` is NOT the producer and is not used: its lookup is
`_RESPONSE_MESSAGE_REGISTRY.get(self.__class__.__name__)`, an exact class-name match that
subclassing defeats, and its fallback is `f"{cls.__name__} response"` -- worse than our text on
nine of fourteen.

### DONE: required-and-nullable retention is derived, not declared

With one seam and one body, a reply's field set, types and shape all follow from the SDK class
the implementation returned, so they cannot drift. One property does not follow: retention of a
field the pin lists in `required` while typing it nullable. The SDK base serializes
`exclude_none=True` unconditionally, which drops the key, and `AlwaysIncludeFieldsMixin` puts it
back -- but only for a class that OPTS IN by naming `_PINNED_SCHEMA_REF`.

Measured across the fourteen registered tools' pinned response schemas, excluding the shared
`error.json` and envelope subtrees we never construct, there are exactly three such fields:

| Site | Model | Retained |
|---|---|---|
| `create-media-buy-response.json#/oneOf/0` -> `confirmed_at` | `CreateMediaBuySuccess` | yes |
| `get-media-buys-response.json .media_buys[]` -> `confirmed_at` | `GetMediaBuysMediaBuy` | yes |
| `get-task-status-response.json .result` (nests the create response) | `GetTaskStatusResponse.result: AdcpAsyncResponseData \| None` | **no** |

Two of three adopt. The third is the SDK's own type with no ref and no retention. A fourth
site, added by a spec bump, drops silently with nothing red -- which is the same
declare-versus-derive defect R3 removed from the envelope, one level down.

**Landed, and simpler than this section proposed.** The retained set is read off the model's own
`model_fields` -- a field it declares required whose type admits `None` -- so nothing names a
schema at all. `_PINNED_SCHEMA_REF` is deleted along with `required_nullable_fields` and its
150 lines of `$ref` / `allOf` / JSON-pointer walking; `_pinned_fields.py` keeps only
`revision_minimum`, which has a live production caller.

Measured across the 416 models reachable from a response, the derived rule reproduces the old
result exactly on every adopter, and it cannot name the wrong schema, which the string could --
two of the four adopters named a ref that derived nothing at all, and those two have dropped
the mixin. Exactly three models declare a required-and-nullable field:
`CreateMediaBuySuccess.confirmed_at` and `GetMediaBuysMediaBuy.confirmed_at`, both retained,
and `DiscriminatorItem.value` from `core/error.json`, which this seller never constructs.

One exception stays, and it is subtractive: `_INTERNAL_ONLY_FIELDS` / `exclude=True` strip our
internal fields (`workflow_step_id`) from every protocol response. The other used to be
`apply_version_compat`, which was ADDITIVE -- it appended three properties the pinned schema
does not define -- and is deleted.

---

## R3 — DONE: type the protocol envelope on every response

**The defect was not one field.** It was the whole envelope, and it was missing from exactly
the tools that need it.

Every response model now inherits `adcp.types.ProtocolEnvelope`, so all eleven fields are typed
on all fourteen. `_response_model_for` is annotated `type[ProtocolEnvelope] | None` and the
boundary assigns `result.replayed = True` outright; the `model_fields` probe, the `setattr`
and its `noqa` are gone. `CompletedTaskStatusMixin` went with them: it hand-declared
`status: Literal["completed"]` on four models, and the SDK parent already declares that field
AND fills it through its own `_normalize_legacy_status` before-validator, so removing the mixin
changed no construction site. `test_architecture_dto_adds_no_field.py` grades that every
registered tool keeps the base, so the annotation cannot quietly become a lie again.

The rest of this section is the measurement that motivated the change, kept because it names
what to look for if a response model ever loses the base.

`core/protocol-envelope.json` declares eleven fields -- `status`, `task_id`, `message`,
`context`, `context_id`, `timestamp`, `adcp_error`, `governance_context`, `payload`,
`push_notification_config`, `replayed` -- and every pinned response schema composes it with
`allOf`. Measured across our fourteen response models, how many of the eleven are TYPED:

```
get_products, get_media_buys, list_creatives, list_accounts,
list_creative_formats, list_tasks, get_task_status,
get_media_buy_delivery, get_adcp_capabilities .................. 11/11
complete_task ...................................................  3/11
create_media_buy, sync_accounts, sync_creatives ..................  2/11
update_media_buy .................................................  1/11
```

The five short rows are `complete_task` plus **the four keyed tools** -- the only four that can
ever need `replayed`. And three of them (`create_media_buy`, `update_media_buy`,
`sync_accounts`) run `extra="forbid"` in dev and CI, so on those the field cannot even ride as
an extra: setting it raises, and in production `extra="ignore"` drops it silently.

That is why the bug this section opened with exists at all. `CreateMediaBuyResult` works around
the gap with a locally declared `replayed` plus a pop-and-reset in its own serializer;
`UpdateMediaBuySubmitted` declares the field without the pop, so a replayed submitted update
goes out as `replayed: false` -- positively asserting a fresh execution. Two hand-rolled
answers to a field that should have arrived with the envelope.

**Upstream, for context, not as a blocker.** The Python SDK's generated success branches drop
the whole composition. Measured against `adcp==6.6.0`: 19 of the 24 `*SuccessResponse` aliases
do not inherit `ProtocolEnvelope`. The five that do are the ones whose response schema has no
`oneOf`, so the alias resolves to the root class and picks the base up from the root `allOf`.
Filed as adcontextprotocol/adcp-client-python#1136.

We do not wait for that. `adcp.types.ProtocolEnvelope` is exported and correct; only the
generated branches fail to inherit it.

**The change.** Our response models inherit `ProtocolEnvelope`, so all eleven fields are typed
on all fourteen -- nine already are, by a route that happens to work. Then:

* `replayed` is `bool | None`, absent unless set, matching the TS shape and the schema's own
  "set to false (or omitted) when the request was executed fresh";
* the boundary assigns it on replay, which is the spec's rule 4 -- "the seller injects
  `replayed: true` ... at response time", the idempotency layer being the only thing that knows;
* `CreateMediaBuyResult.replayed` and `TaskResultEnvelope`'s pop-and-reset are deleted, being
  the per-class workarounds for the missing base;
* `_deserializer_for`'s `"replayed" in model.model_fields` probe and its `setattr` with a
  `noqa` go with them: the field is always there, so it is always assignable.

A typed field is not the same as a serialized one. The reason the earlier draft of this
section said "a model has no business declaring the field" was the `replayed: false` bug -- but
that came from a NON-OPTIONAL field with a `False` default that always serializes, not from
declaring it. TS declares it and the SDK's store still injects it; those are compatible, and
the combination is what we want: typed so a buyer and a type checker can see it, absent unless
the idempotency layer sets it.


## R4 — DONE: a failure is an exception; the status check is deleted

**The defect.** `_boundary._is_error_result` inspects the returned response's protocol status to
decide whether to cache it. It exists for exactly one caller: `media_buy_create.py:3605`, where
an adapter error is wrapped in `CreateMediaBuyResult(status="failed")` and RETURNED. Every other
tool raises.

No other tool can reach it. `sync_creatives` and `sync_accounts` type `status` as the eight-member
`TaskStatus` and default it to `completed`; nothing in either implementation ever sets a failed
value, because both raise. So for three of the four keyed tools the check is unreachable in
practice, and they are protected by the raise rather than by the check -- which the docstring
does not say. (This paragraph used to argue the check *cannot* fire on those two because their
status was `Literal["completed"]`. That was true only while a local mixin declared it; the
mixin is deleted and the field is the SDK's `TaskStatus` now. The conclusion is unchanged, the
reason is weaker: unreachable by behaviour, not by type.)

**What landed.** That one site raises `AdCPAdapterError` now, like every other failure path in
the tree. Then:

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

**Deferred, and filed: prebid/salesagent#2217.** It needs concurrent same-key traffic to occur
in production and few sellers implement rule 9 at all, so it waits behind R1-R4. The issue
carries the scenario shape, so whoever picks it up writes the Given first.

---

## R7 — DONE: forward compatibility was one transport's private fix for a gap in the models

**Landed.** `ToolSpec.validate` reduces a parameter bag to the fields the schema declares, at
every nesting depth, before the DTO sees it -- rejected in development, dropped in production,
on all three transports. `deep_strip_to_schema` moved to `src/core/schemas/_accepted_shape.py`
and is called from the one seam every transport passes through; the schema is derived from the
row's DTO rather than stored on the row. One rule changed: an unknown key is kept only where
the object declares NO properties (`ext`, `context` -- AdCP's shape for "arbitrary data lives
here"), not wherever `additionalProperties` allows it.

Two other mechanisms were built and thrown away, and `_accepted_shape.py` records why: a
`model_validator` walking the data against the model tree deleted every `account.account_id`
and every creative asset on its first run, and setting `extra` on the 255 reachable SDK classes
made pydantic's `__eq__` time-dependent.

**The defect, as it stood.** `RequestCompatMiddleware` deep-stripped request fields absent from
the tool's JSON Schema, in production only (`src/core/mcp_compat_middleware.py`). A2A and REST
stripped nothing. Its own docstring says why it exists: FastMCP's `TypeAdapter` validates the
announced signature BEFORE our model does and rejects unknown fields, so "stripping bridges
the gap".

That reads like an MCP-local concern. It is not, because the gap it bridges is real on the
other two transports as well -- they just fail differently. Our DTO carries
`extra="ignore"` in production, but the NESTED models are the SDK's and carry three different
modes:

```
GetProductsRequest    extra=ignore     (ours)
BrandReference        extra=forbid
ProductFilters        extra=allow
ExtensionObject       extra=allow      (the `ext` field on all four keyed tools)
```

So in production, one payload with an unknown field has three fates by nesting level, times
two by transport:

| unknown field at | MCP | A2A / REST |
|---|---|---|
| top level | stripped, then ignored | ignored |
| inside a `forbid` model (`brand`) | stripped, accepted | **REJECTED** |
| inside an `allow` model (`ext`, `filters`) | stripped, accepted | **kept, and it reaches `_impl`** |

**The `allow` row breaks a documented boundary invariant.** `_boundary`'s module docstring
states that equivalence is over the request as this seller understands it, because "a field the
pinned schema does not define is dropped by `extra="ignore"` before hashing, so it cannot
distinguish two requests either. That is deliberate." Measured on `sync_accounts`, a keyed
tool, in production:

```
unknown field at top level     -> hash unchanged   (invariant holds)
unknown field inside `ext`     -> hash DIFFERS     (invariant fails)
```

A buyer who retries with the same `idempotency_key` and an unknown field inside `ext` is
answered `IDEMPOTENCY_CONFLICT` instead of being replayed -- on A2A and REST only, because on
MCP the field was stripped before it could reach the digest.

**So the fix is not "make the other two strip".** Three transports running the same stripping
would still leave the models disagreeing with each other, and would leave the boundary
docstring describing behaviour the models do not have. The question to settle is what the
seller's forward-compatibility policy IS -- tolerate-and-drop is what the docstring assumes and
what `extra="ignore"` implements -- and then to make the models express it, so no transport has
to compensate and the hashing invariant is true by construction rather than at one nesting
level.

Whether MCP still needs its stripping after that is a separate and much smaller question: it
depends only on whether FastMCP's `TypeAdapter` rejects before our model runs, which is a
genuine property of that transport.

**A note on scope.** The nested modes come from the SDK, so expressing the policy may mean
overriding `model_config` on our own DTOs, or an upstream issue, or both -- the same shape as
adcontextprotocol/adcp-client-python#1136 and #1137. Measure before choosing.

---

## Order

R1, R2, R3, R4, R5 and R7 are done.

What remains:

1. **Required-and-nullable retention** as a generic rule off `model_fields` (the section under
   R1). Deletes `_PINNED_SCHEMA_REF`, `_pinned_fields.py`, `AlwaysIncludeFieldsMixin` and two
   adopters that derive nothing.
2. **R6**, behind prebid/salesagent#2217. It needs concurrent same-key traffic to occur in
   production and few sellers implement rule 9 at all.

Beyond this document: the creative pipeline carries five fields AdCP 3.1.1 does not define on
`core/creative-asset.json` -- `snippet`, `snippet_type`, `template_variables`, `duration`,
`variants` -- with 231 production references. They were built against AdCP v1.3 (a205d9309)
and never migrated when the repo moved to 3.1.1 (c7acbbd6e); `git log -S snippet --
src/core/schemas/` is empty. They survived only because the SDK's nested models were
`extra="allow"`, which R7 has now closed.
