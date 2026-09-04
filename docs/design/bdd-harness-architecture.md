# BDD harness architecture

> Companion to [one-tool-registry.md](one-tool-registry.md). That document makes the
> production boundary derive from one declaration; this one makes the test vocabulary
> derive from the same place. Neither is useful without the other: a harness that
> hand-writes what a tool accepts is a second declaration, which is the defect the
> registry exists to delete.

## The rule

**A scenario names a state, a tool, and an outcome. Everything else is derived.**

The setup comes from a fixed set of state primitives. The action is one dispatch. The
payload is a named factory baseline plus the fields the scenario overrides. The response
is graded against the response schema of the tool that was called, resolved rather than
named. Nothing in a feature file states a transport, a schema filename, or a field the
implementation does not read.

## What exists today, measured at c20672203

The harness is in better shape than the Gherkin. `tests/harness/client.py:753` already
publishes the whole action vocabulary in one signature:

```python
def call(self, tool: str, payload: dict, transport: Transport, *, identity=...) -> TransportResult
```

Both dispatch entry points — `env.call_via` (`_base.py:592`) and `AdCPTestClient.call` —
converge on a single ctx writer, `tests/bdd/steps/generic/_dispatch.py:69`. Seven
transports are implemented, including live MCP and live A2A, which have **zero callers**.

The Gherkin does not use any of that.

| | Given | When |
|---|---|---|
| lines | 4917 | 2807 |
| distinct verbatim | 2470 | 1470 |
| distinct after normalizing values, placeholders, numbers | 1974 | 1216 |
| used exactly once | 75% | 77% |

Normalizing collapses only 20%, so the variety is **wording**, not parameters.

## The cost, measured

**Nearly half the corpus never executes.** 20 of 50 feature files are loaded by no test
module — BR-UC-001, 007, 008, 009, 012–017, 020–025, 027, 028, 030, 032. Of 4963 Given
lines, 2297 (46%) live in those files, 471 more are dormant in loaded features, and
**2195 (44%) actually run**.

Vocabulary density tracks executability exactly: 0.59 distinct sentences per line in the
never-loaded half against 0.43 in the loaded half. **The invented phrasing is concentrated
precisely where nothing ever forced two sentences to meet the same implementation.** This
is the root cause of the vocabulary problem, not a separate one.

Second-order evidence of the same thing: **89 ctx keys are written and never read**
anywhere under `tests/`. `given_seller_supports_attribution` and
`given_seller_no_attribution` set opposite flags that nothing reads — those scenarios
cannot be grading the distinction they name.

## The target vocabulary

### Given — roughly 32 state primitives

Thirty primitives cover 4479 of 4963 lines (90%); two more absorb most of the residue.
The five largest, with the lines each subsumes:

| | lines | primitive |
|---|---|---|
| P01 | 533 | the Buyer is authenticated as principal "P" on tenant "T" |
| P06 | 500 | the tenant setting S is V |
| P10 | 423 | the principal "P" owns media buy "M" with status "S" |
| P08 | 356 | an account "A" exists for brand/operator "B" status "S" |
| P05 | 276 | a tenant "T" exists and is resolvable |

The collapses are proven at the implementation, not the wording. `"the Buyer is
authenticated with a valid principal_id"` (234 uses) and `"the Buyer Agent has an
authenticated connection"` (118) have **byte-identical AST bodies**. Three tenant steps
across two modules reduce to one normalized body whose distinguishing flags are never
read. Two delivery sentences that read as *opposites* both call
`given_adapter_has_data_all(ctx)`.

### When — one primitive, two modifiers, three events

**2548 of 2807 When lines (90.8%) are one operation: dispatch tool T with payload P.**
Stripped of payload, they collapse to 397 verb+tool stems naming 49 tools, written with
**28 different verbs** — sends 1216, invokes 390, requests 233, syncs 194, calls 145,
submits 113, and 22 more.

Only two things reach the seam that are not payload:

- **M1, identity override** — the single non-payload parameter of `call_via`. Four values,
  all already implemented: absent, anonymous, invalid token, a second principal.
- **M2, verbatim body** — a payload the local model would reject never reaches production,
  so the scenario grades the model instead of the seller. `_call_raw` is the negative-path
  seam; 418 of 1038 bound lines already take it.

`dry_run`, `idempotency_key` and `adcp_version` are **AdCP request fields, not call
manner** — they belong in the payload. Repetition and concurrency are the primitive
invoked twice, not a third sentence form.

Three genuine non-dispatch events remain, 25 lines total: an admin UI action (Flask test
client, reaches no dispatch seam), a seller-initiated outbound webhook, and clock
advancement.

### Payload — baseline plus delta, never a JSON body

Measured across the 2807 When lines: **48% name no payload at all**, 30% carry an inline
scalar, 12% an outline placeholder, and **3% a data table**. The payload is built by
preceding Given steps and the When merely fires it — which is why the Given corpus is
1.75× the size of the When corpus.

So the human-readable payload vocabulary is a **Given** problem. It is already primitives
P12/P13/P14 — `a valid create_media_buy request` (175 lines), `a valid update_media_buy
request with:` (259), `the request field X is Y` (246). Those 246 field-delta lines are
reaching by hand for the shape this design adopts:

**a named factory baseline, plus the fields the scenario overrides** — where the baseline
name and the overridden field/value are what appear in the `Examples` columns. A full JSON
body does not fit a table cell; `create_media_buy` + `end_time` + `<value>` does.

### Then — resolved, never named

`then_schema.py:41` already has `the response should be schema-valid against {schema_file}`.
The filename is a second place stating which tool the scenario exercises, and it can drift
from the When. After the registry, the tool determines its response schema, so the schema
is **resolved from the tool that was actually called**. A scenario that changes its tool
cannot keep grading the old schema.

## What gets deleted

- **`Transport.IMPL`** — 41 occurrences across 20 files, plus 8 bare `"impl"` ids. `impl`
  calls `_impl` directly, cannot exercise the transport boundary, and was measured at
  ~zero unique passing coverage. [bdd-drop-impl.md](bdd-drop-impl.md) removed it from the
  BDD default set and explicitly deferred deleting the machinery; this is that deletion.
- **Transport-pinned sentences** — 73 lines naming a transport (`via A2A`, `the MCP tool`).
  Scenarios are parametrized over a2a/mcp/rest, so a pinned sentence either lies (the body
  ignores it) or defeats the parametrization. Only 5 of 73 are bound. **This is a Gherkin
  GENERATION defect** — fixing the feature files alone regresses on the next generation
  pass. Transport belongs to the parametrization, never to the sentence.
- **234 When lines that are Then obligations phrased as actions** — "the system validates
  the pricing option", "the response is received", "the seller assembles totals at boundary
  X". The four bound ones call `normalize_request_params` directly with no wire and no
  transport: a unit test wearing Gherkin.
- **The five duplication clusters** with drift already found: identity plumbing (14 copies;
  two xfails blame production for step bugs), request-side `push_notification_config` (9
  builders; one sentence is `@given` in one file and `@when` in another), HMAC assertion
  (BDD is the sole holdout, carrying the exact `X-ADCP-`/`X-AdCP-` drift the shared
  helper's docstring warns about), datatable coercion (case-sensitive vs `.lower()` header
  detection 100 lines apart in one file), `pricing_option_id` derivation (7 copies, 5 in
  `src/` — production duplication this design does not touch, filed separately).

## What gets added

**One dependency slot that is already paid for.** `factory-boy>=3.3.0` is in
`pyproject.toml:89`; `tests/factories/` holds 34 factories and **not one is a request
factory** — every one is an ORM or response/value-object factory. The baselines currently
hand-written under `tests/bdd/steps/generic/` move there. That is not new machinery; it is
putting existing code in the house that exists for it.

**Generation is deferred, not ruled out.** A prior scout ruled out polyfactory on two
failures. One was **our own defect**: `UpdateMediaBuyRequest` "never builds" because we
widened `end_time` to `datetime | None` and then validate that it must be aware — the SDK
types it `AwareDatetime | None`. Against the SDK models this design prescribes, four of six
request models build **50/50**, and `UpdateMediaBuyRequest` goes 0/50 → 38/50. The residual
failure is one nested constrained `EmailStr` at
`account.root.brand.data_subject_contestation.email`. Re-evaluate on the post-boundary
tree; do not re-litigate on the old numbers.

## Zero guards

Same rule as the registry design, for the same reason. A scenario expressed in resolved
primitives cannot name a transport, cannot name a schema file, and cannot carry a field the
tool does not declare — those states are unrepresentable rather than forbidden. Do not add
a test asserting the vocabulary is used correctly; the vocabulary is the enforcement.

## Migration order

Each step leaves the tree green and is independently revertible.

1. **Decide the 20 never-loaded feature files.** Wire them or delete them. Migrating 2297
   lines of vocabulary that no test module loads is the largest available waste, and the
   answer changes the size of every step below. This is the first question, not a cleanup.
2. **Delete `Transport.IMPL`**, and fix the generator rule that emits transport-pinned
   sentences. Both are deletions with no vocabulary dependency.
3. **Add request factories** to `tests/factories/`, absorbing the three fallback baseline
   vocabularies and the `cpm-standard` label that leaks as an id at ~20 sites.
4. **Build the ~32 Given primitives and the one When primitive**, with the two modifiers
   and three events. Give each of the five duplication clusters its single owner as part
   of this — they are the same work seen from the implementation side.
5. **Make response grading automatic**, resolved from the tool rather than named by the
   scenario.
6. **Migrate**, once. Per scenario the question is "which states does this need, with which
   parameters" — not "how do I reword this sentence". Split by shape: the 671
   validation-shaped scenarios are candidates for generated properties rather than hand
   migration; the rest are logic and get thinner, because payload and grading are both
   derived by then.

Steps 1–2 can start immediately and depend on nothing. Steps 3–5 depend on the boundary
work landing. Step 6 depends on all of them, and doing it earlier means opening every
scenario twice.
