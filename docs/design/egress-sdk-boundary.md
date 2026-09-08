# The egress gateway and the SDK boundary

This document describes where the gateway is, what the `adcp` SDK owns, what this
repo implements on top, and which parts of that are temporary.

It is a companion to [Outbound egress: one gateway](../security/outbound-egress.md),
which states the rule for people who need to make a request. This document
is for people changing the gateway, or deciding whether a new concern belongs here
or upstream.

## Contents

- [The module map](#the-module-map)
- [What comes from the SDK](#what-comes-from-the-sdk) — what `adcp` owns and this repo never reimplements
- [Workarounds carried until upstream provides them](#workarounds-carried-until-upstream-provides-them) — two dated workarounds, each with a named retirement condition
- [The validation split: two verdicts, one predicate](#the-validation-split-two-verdicts-one-predicate) — `check_registration` versus `resolve_for_dial`, and the edge cases around them
- [Provenance is carried, not decided](#provenance-is-carried-not-decided) — `UrlProvenance` as a type, not an inference
- [Retry and backoff belong to the gateway](#retry-and-backoff-belong-to-the-gateway)
- [One vocabulary for webhook auth](#one-vocabulary-for-webhook-auth) — `AuthenticationScheme` comes from the spec, not a local choice
- [Address logic is confined to the egress package — enforced two ways](#address-logic-is-confined-to-the-egress-package--enforced-two-ways)
- [A destination is a typed constant, never an environment read with a URL default](#a-destination-is-a-typed-constant-never-an-environment-read-with-a-url-default)
- [Replace a validator without opening a gap](#replace-a-validator-without-opening-a-gap) — ordering rules for deleting or swapping an egress guard
- [Decide where a new concern belongs](#decide-where-a-new-concern-belongs) — the questions to ask, in order
- [Related](#related)

## The module map

```
src/core/security/
  outbound_http.py          the gateway. send / asend. the only public entry point
  egress/
    policy.py               the address and scheme verdicts, and the one predicate they share
    attempts.py             the retry schedule as pure values — no I/O, no httpx
    response.py             OutboundResult — the closed response type consumers read
    destination.py          the typed record of where a URL came from, at construction time
```

Two sibling gateway modules build on this package rather than living in it:
`src/core/utils/mcp_client.py` (MCP connections, pinned through
`guarded_client_factory`) and `src/core/security/webhook_egress.py` (signed
webhook delivery through `asend`).

Each module owns exactly one decision, and the split is deliberate:

- **`attempts.py` has no `httpx` import and does no sleeping.** It is a state
  machine returning retry / success / terminal, which `send` and `asend` drive
  *identically* — one loop definition, so the sync and async paths cannot
  drift apart.
- **`response.py` closes the response type.** `OutboundResult` exposes no
  live `httpx.Response`: a result that leaked the raw response would let call
  sites program against httpx with the import ban still satisfied — true and
  useless at the same time. The closed type is what gives "no raw egress"
  its meaning.
- **`destination.py` is not `UrlProvenance`.** They answer different questions
  at different moments: `UrlProvenance` answers *"who do I blame in this
  refusal"* when a connection attempt fails, and deliberately never carries the
  URL; `VendorConstant` answers *"where in source did this constant come from"*
  when a call site builds a URL, and does carry it. A call site may
  legitimately use both.

## What comes from the SDK

The `adcp` SDK owns address validation and connection pinning. This repo
imports these mechanisms; it never reimplements them:

| From `adcp` | What it owns |
|---|---|
| `signing.resolve_and_validate_host` | resolve once, classify the resolved address |
| `signing.SSRFValidationError` | the SDK's refusal — translated here, never leaked |
| `signing.IpPinnedTransport` / `AsyncIpPinnedTransport` | connecting to the address that was validated |
| `types.*`, `types.generated_poc.*` | the wire schema |
| `canonical_formats` | format identity |
| `webhook_receiver.verify_webhook_hmac` | the AdCP 3.x HMAC fallback verification |
| `types.AuthenticationScheme` | the single webhook auth vocabulary — see [One vocabulary for webhook auth](#one-vocabulary-for-webhook-auth) |

**The single most important consequence:** because the SDK resolves once and
pins that IP into the transport, the address that was validated is the address
the transport connects to. Any code that validates a hostname and then hands
the *hostname* to a client has reintroduced the DNS-rebinding TOCTOU
(time-of-check to time-of-use) vulnerability, however thorough its checks are.
This is why "just add a check here" is not a smaller version of the right fix —
it is a different, broken design.

### One SDK symbol is banned outright

`adcp.webhooks.get_adcp_signed_headers_for_webhook` is on the TID251 ban list.
It discards the body bytes it signs, so its own documented usage — sign, then
send `json=payload` separately — reintroduces the signed-bytes-vs-wire-bytes
divergence. Sign and send through the gateway with the signed byte string instead.

That an SDK ships an unsafe helper is not a contradiction of "the SDK owns
this": the SDK owns address validation and pinning, which is not the same as
every helper in it being safe. Treat the SDK as authoritative where it is the
mechanism, and as a cross-check elsewhere.

## Workarounds carried until upstream provides them

The gateway carries two workarounds, both marked in the source. Neither is a
design position — each is dated and has a named retirement condition.

### Five of the six supplement ranges

```python
# FIXME(adcontextprotocol/adcp-client-python#974): drop this whole
# frozenset (except the CGNAT entry above) once we adopt a release
# that carries these ranges upstream.
```

6to4 relay, AS112-v4, AMT, AS112 direct, and ORCHIDv2 are held here only until
the SDK classifies them. **CGNAT `100.64.0.0/10` stays**, because AdCP 3.1.1
names it explicitly as a range a fetcher MUST reject.

Retirement: adopt the release, delete the five, keep CGNAT, and confirm that
the oracle table in `tests/integration/test_outbound_http.py` still covers the
production set exactly — a completeness test checks both directions, so
removing a range without removing its row fails, and adding a range without
adding a row fails too.

The version bump is deliberately deferred: it is a major version jump, and the
owner's call was that it is not worth the risk for this alone.

### Operator agent connections do not use the SDK client

`creative_agent_registry` and `signals_agent_registry` connect through
`src/core/utils/operator_mcp.py::call_operator_mcp_tool` — a real MCP handshake
that is IP-pinned and redirect-refusing — rather than `adcp.ADCPMultiAgentClient`.

The reason is concrete rather than stylistic: adcp 6.6.0 exposes no transport
injection point, so the SDK client builds its own connection — following
redirects included — and that connection passes through **none** of this
application's egress policy.

Retirement: **adcp-client-python#1004**, which adds the injection point. The
citation is at `src/core/creative_agent_registry.py` and
`src/core/signals_agent_registry.py` where the choice is made, not only here.

## The validation split: two verdicts, one predicate

The gateway is asked two different questions at two different times, so there are
two verdicts:

| | `check_registration` | `resolve_for_dial` |
|---|---|---|
| When | A URL is **stored** (webhook registration) | Something is **about to connect** |
| DNS | None — never resolves | Resolves once, pins the result |
| Catches | A literal `10.0.0.1`, a bad scheme, a blocked hostname | What a name actually points at |
| Cannot catch | What `evil.example.com` resolves to | Nothing it was given a chance to see |
| `allow_private` | **No such parameter** | Test-only override — see [What no override opens](#what-no-override-opens) |

They read the **same** `_blocked_address` predicate, the same hostname
blocklist, and the same scheme rule. That is the point: two independently
maintained copies of "what is a bad address" is the defect this module exists
to prevent, and the reason the registration and connection checks cannot drift
into disagreement.

Registration is DNS-free **on purpose**, and it is worth stating why.

It runs when a buyer hands you a URL and there is no request to attach a refusal
to yet. A registration-time resolution was never binding: DNS moves between
registration and the first connection, so a hostname that is public but
unresolvable must be *accepted* now and re-checked when the gateway actually
connects to the callback. Resolving at storage time is a side effect of storing
data that proves nothing.

The admin route runs the same single validation path that every protocol
surface runs, deliberately giving up registration-time DNS — two gates that can
disagree give the same URL two verdicts, depending on which one answers.
`tests/integration/test_admin_ingest_url_policy.py` pins the decision: it
asserts that the resolver is called **zero** times at registration, so
reinstating resolution has to be a deliberate act with a failing test in front
of it, not an innocent-looking "we should validate earlier" change.

That technique generalizes: when you keep a behavior out on purpose, pin its
absence with a test — an asserted absence makes the decision defend itself.

### Open question: the loopback rescue

`check_registration(url, *, allow_loopback=False)` carries one relaxation: the
`ADCP_TESTING` loopback allowance, threaded in by
`webhook_validator._adcp_testing()`. The settled part is its narrowness, and
the docstring of `_is_rescuable_loopback` (`egress/policy.py`) states it well:
the rescue is a **post-check over the hostname and literal-IP refusal branches
only**, never a flag threaded into `_blocked_address` — a threaded flag rescues
every supplement range and every RFC 1918 address at registration, not only
loopback. It never rescues a scheme refusal.

The unsettled part: the rescue is structurally close to an SSRF trust bypass of
the form "trust whatever hostname an environment variable names" — no helper of
that form, such as `_is_trusted_test_host`, exists here, deliberately. There is
a real distinction — the loopback property is re-derived structurally from the
URL, rather than read from an environment variable — but no commit states that
distinction as a decision. Until that sentence exists, do not widen
`allow_loopback`, and do not "harmonize" it toward a trusted host named by an
environment variable.

A trap for anyone touching the tests: the test cases `blocks_localhost` /
`blocks_127_0_0_1` pin `ADCP_TESTING` off and assert both branches of the
allowance — an autouse `ADCP_TESTING=true` would feed the rescue and make
them test the opposite of what their names claim.

### Stored rows are not re-validated

A related split follows the same reasoning about who is present to fix a
problem: **ingest validates, rehydration does not.** Reading a stored
registration carries the document through the library type with
`model_construct`, nested models included.

At ingest a buyer is present to correct a rejection. A stored row has no buyer,
is delivering *today*, and the delivery path fails closed on its own. Routing
rehydration through the validating model instead stops already-delivering rows
over values that stored data can carry — a short credential, a lowercase scheme
spelling, an unrecognized scheme, a short `token` or malformed `operation_id`,
or an empty `schemes` list.

The one exception is principled: an HMAC registration with no secret still
refuses, because that row never delivered, and delivering it means sending
unsigned payloads to a receiver that is obliged to reject them.

### What no override opens

`ADCP_OUTBOUND_ALLOW_PRIVATE=true` relaxes the SDK's flag classes so tests can
reach their own loopback origin or the compose bridge. It does **not** relax
the supplement set, which `resolve_for_dial` checks unconditionally before the
override applies — those six ranges have no second line of defense, which is
why they are carried at all. The fuller treatment is in
[Outbound egress: the supplement ranges](../security/outbound-egress.md#the-supplement-ranges-and-the-check-no-configuration-relaxes).

### Refusals say nothing

AdCP 3.1.1 `building/by-layer/L1/security.mdx` point 6: a fetcher MUST never
echo the refusal cause back to the party that supplied the URL. A per-cause
message at the buyer surface is a port-scanning oracle.

This is structural, not conventional: `AdCPBlockedUrlError.__init__` is
keyword-only and takes **no `message` parameter**, so a second wording of the
refusal is unrepresentable. The cause is not lost — it goes to the operator's
log. **Do not assert on refusal message text in tests**; assert on the code, and
at most on the presence or value of structured details carried with the error.

The refusal sentence names neither the field nor the URL, which is exactly why
the WARNING log line beside each refusal is essential rather than noise —
the two lines together carry the complete information.

### Exception text never reaches stored or buyer-visible fields

The same disclosure rule extends past refusal messages: never put a caught
exception's text into a persisted or buyer-visible field on an egress path.
An `IpPinnedTransport` `RuntimeError` names both the pinned host and the host
it refused, and a sender's `detail` is written verbatim to
`webhook_delivery_log.error_message` and emitted as an audit warning — so
`detail=str(e)` discloses a destination into durable storage.

Senders use `WebhookDeliveryOutcome.unexpected(exception_type)`
(`src/core/webhooks/delivery.py`) — a named constructor carrying the
exception **type** only. The exception's own message still reaches the
operator in the adjacent log line, which is the right place for it. The
residual risk is accepted knowingly and stated in the docstring: the outcome is
a public frozen dataclass, so a caller can still construct `detail=str(e)` by
hand — the sanitized form is the named and convenient one, not the only
expressible one.

## Provenance is carried, not decided

`UrlProvenance = CounterpartyUrl | OperatorEndpoint` (`outbound_http.py`).
`send`, `asend`, and `validate_url` all take
`provenance: UrlProvenance | None` — whose URL this is, as a **type**, not an
inference from whether some optional string happened to be `None`. A new call
site passes a `UrlProvenance` and chooses the member deliberately, because the
two members produce genuinely different buyer-facing outcomes
(`src/core/helpers/outbound_error_mapping.py`):

- `CounterpartyUrl` re-raises the gateway's own classification unchanged. The
  refusal stays correctable and buyer-facing.
- `OperatorEndpoint` yields `CONFIGURATION_ERROR`, terminal, naming a **role**
  rather than an address — the buyer did not choose that address and cannot
  fix it. Its constructor rejects any name containing `://`, so a URL cannot
  be smuggled through as an operator label.

The field exists because of the opaque refusal: the message says nothing about
the cause on purpose, so `error.field` is the **only** channel that can name
the offending input — without it the error is correctable in name only. And
the gateway cannot compute that path itself: it sees a URL string, never a
request document, and the namespace differs per call site. Hence carried, not
decided.

`_checked_field(provenance, url)` guards the leak direction: `field` is
buyer-visible, so a call site that passes the URL — or anything containing it
— as the field bypasses the opacity that the message maintains. It
**raises** rather than quietly dropping the value, because naming a URL where
a request path belongs is a call-site bug worth surfacing, not one worth
shipping as a silently fieldless envelope. The containment check runs in the
leak direction only: a fixed field constant appearing inside a
buyer-controlled URL must receive the policy verdict, not a manufactured
`ValueError`.

Never fabricate a path. When a URL came from the request document but has no
canonical path, construct `CounterpartyUrl` **without** a field — a
made-up locator such as `creative:{id}.agent_url` names a path that does not
exist in the pinned request schema. And choose the member deliberately, never
by default: a fallback connection path that re-classifies a buyer-supplied URL
as operator configuration on a cache miss turns a correctable refusal into a
terminal one.

The public helper `refusal_field(provenance)` is the one place the
field-or-nothing derivation lives; call sites that raise their own error at
the locator a gateway refusal would have carried (`creative_agent_registry`) read
it from there rather than re-deriving the URL's ownership with a second
`isinstance` check.

## Retry and backoff belong to the gateway

Retry, backoff, and `Retry-After` handling are gateway policy. A new outbound
call site passes `max_attempts` and lets the gateway sleep; a geometric sleep
anywhere else under `src/` fails `make quality`. Anyone tuning backoff edits
`attempts.py`.

The schedule does **not** live where a reader expects. It lives in
`src/core/security/egress/attempts.py` (`_backoff_seconds`, `_wait_seconds`,
`Attempts`); `outbound_http.py` re-exports two of its names as a test-facing
facade with no `src/` consumer. The public gateway surface is
`sleep_backoff(attempts)` and `terminal_client_error_status(exc)`.

Four points are worth knowing:

- **The ordering, and why the obvious form is wrong.** `_wait_seconds`
  returns `max(backoff, min(retry_after, 60.0))`: the ceiling clamps the
  Retry-After **contribution** only, and Retry-After can only lengthen a wait.
  The natural-looking `min(max(backoff, retry_after), CEILING)` applies the
  ceiling to the whole wait, so whenever the geometric wait exceeds the
  ceiling the gateway sleeps **less** than the rule requires — silently, in the
  module that owns the rule, and reachable through the public `max_attempts`
  parameter: the schedule is 1, 2, 4, 8, 16, 32, 64 s, so it crosses a 60 s
  ceiling at seven attempts.
- **The gateway sleeps rather than publishing the number.** A public
  `backoff_seconds()` lets `sleep(backoff_seconds(1))` — or a scaled variant —
  drift invisibly, because the guard's detector follows same-module names
  only. An awaitable that returns nothing leaves a call site nothing to get
  wrong but the attempt index.
- **`Attempts` reifies the loop, not only the decisions.** One loop
  definition serves `send`, `asend`, and the MCP client wrapper — a loop written per
  consumer is where they drift. The abort recorder pins
  `last_retry_after=None`, so a size-cap abort right after a 429 cannot leak
  that attempt's `Retry-After` onto an unrelated failure.
- **The guard bans the class of defect, not one form of it.**
  `tests/unit/test_architecture_no_call_site_backoff.py` resolves the inline
  form, a local-variable binding, and one hop of same-module helper calls,
  because backoff is nearly always assigned to a variable first or hidden
  behind a helper — a detector that reads only the inline sleep argument
  reports almost nothing. Its list is `NON_HTTP_BACKOFF`, pinned at exactly
  three entries — a business-state poll, a SOAP retry, and a database
  connection retry: a fixed taxonomy of correct designs that are genuinely not
  outbound HTTP, not a debt list that is expected to shrink.

`terminal_client_error_status` exists because the obvious
`400 <= status < 500` predicate is wrong for 429: it makes a rate-limited
endpoint log "will not retry" after a single attempt. `ADCP_OUTBOUND_BACKOFF_BASE_SECONDS`
shortens the base for test speed only — it is deliberately absent from
`tox.ini`'s `pass_env` and from both compose files, so a suite-wide value
cannot silently shorten the schedule.

## One vocabulary for webhook auth

The scheme a webhook is signed with comes from `adcp.types.AuthenticationScheme`
— a **spec vocabulary, not a local choice**. Its two members, `Bearer` and
`HMAC-SHA256`, are what AdCP 3.1.1 defines (`_schemas/3.1/enums/auth-scheme.json`
in the pinned `adcp==6.6.0` package, generated from the spec rather than
written here; the spec marks both as legacy, removed in AdCP 4.0). This repo
does not get to add to it — no seller-local members, and no tolerant
case-folding for spellings that exist in the wild: such rows always exist, and
each folded form is a second spelling of one fact, which senders then disagree
about.

The sender (`webhook_egress.py::_headers_for`) matches on the enum members with
`match`/`case`, case-sensitively, and the fall-through raises. That is the
mechanism that keeps the vocabularies aligned: when the spec adds a member and
the pin moves, the first delivery under the new scheme fails loudly at the
unhandled branch — rather than silently falling through to a default and
sending nothing.

Stored rows naming a scheme AdCP 3.1.1 does not define are refused as
`scheme_not_in_spec` until their operator re-registers. That is the intended
outcome, not collateral: a row that cannot be signed correctly must not be
signed incorrectly.

Three sub-rules apply, and the third is a trap worth knowing:

- **Decide on the enum member, never on its text.** `mypy.ini` sets
  `strict_equality`, and a guard
  (`tests/unit/test_architecture_enum_not_compared_to_string.py`) catches what
  mypy structurally cannot — StrEnum-to-string comparisons are legal to mypy,
  because the members *are* strings.
- **A migration writes values read from the enum, not literals.** A hand-typed
  literal is one typo away from persisting a spelling nothing in `src/`
  compares against.
- **Never add an import-time assertion restating enum values.** It puts one fact
  in two places, which is the defect being removed, and it is actively
  dangerous: alembic imports every module under `versions/`, so an import-scope
  `assert` fails `alembic heads` and `alembic upgrade` on any member rename.
  That breaks the migration system to guard a rename that has not happened.

## Address logic is confined to the egress package — enforced two ways

The rule "do not write address classification outside `egress/`" is stated in
Pattern #9 and in the gateway's own docstring. It is also enforced twice — a rule
enforced by prose alone is how a second, independently maintained CIDR range
set appears with no check failing — and it takes two mechanisms because one
mechanism cannot see both forms:

| Form | Caught by |
|---|---|
| `import ipaddress`, `socket.gethostbyname` outside `egress/` | TID251 bans in `ruff-egress.toml`, each carrying its reason |
| A hostname blocklist written as an inline `set`/`frozenset` literal | `tests/unit/test_architecture_no_hostname_blocklist_duplication.py` |

An import ban sees imports. It cannot see a set of hostnames written inline —
the likelier form of this defect — so shipping only the TID251 half leaves the
likelier half unguarded.

The `socket.gethostbyname` ban carries the deeper rule in its message:
resolve-then-check is a TOCTOU pattern the egress package does not use, because
`adcp.signing` pins the resolved IP in one step. So the ban is not merely "don't
duplicate policy" — it is **don't reintroduce the two-step pattern at all**.

**What this means if you are asked to block a new range:** add it to
`_SUPPLEMENT_NETWORKS` in `src/core/security/egress/policy.py`, never at the
call site. Importing `ipaddress` elsewhere under `src/` fails
`make quality-ci` with a message pointing there.

## A destination is a typed constant, never an environment read with a URL default

`VendorConstant` (`src/core/security/egress/destination.py`) is the typed home
for a fixed vendor endpoint. `APPROXIMATED_BASE_URL` and `GOOGLE_TOKEN_URL` are
`VendorConstant` instances.

The pattern it forbids is worth naming, because it looks entirely ordinary:

```python
APPROXIMATED_BASE_URL = os.environ.get("APPROXIMATED_BASE_URL", "https://cloud.approximated.app")
```

That is a **credential-bearing destination, silently redirectable at import time
by one environment variable**. The destination-rewrite guard therefore runs two
detectors: stdlib URL-reassembly calls (`urlunparse`, `urlunsplit`,
`._replace`), and any module-level constant sourced from
`os.environ.get(...)` / `os.getenv(...)` with a URL-like default, anywhere
under `src/` — an environment read with a URL-like default matches none of the
reassembly calls, so the first detector alone would miss it.

Exclusions are **per file with a stated reason**, not a growable allowlist,
and the scanner raises on an exclusion that suppresses nothing. There is one:
`src/app.py`'s CORS `allow_origins` — an *inbound* allowlist with no relation
to the egress gateway, a genuine false positive.
(`creative_agent_registry.py`'s sanctioned `CREATIVE_AGENT_URL` connection
alias sits outside both detectors' scope — it swaps a whole string inside
a function, not a URL part or a module-level environment default — and is
bounded behaviorally by
`tests/unit/test_creative_agent_connection_alias.py`.)

`VendorConstant` is deliberately a single member, not a union. Do not add
sibling members or a `Destination` union alias to make the vocabulary look
symmetrical: the counterpart concepts already live in `UrlProvenance`, and a
parallel type that nothing constructs gives one concept two representations.

## Replace a validator without opening a gap

Two ordering rules apply for anyone deleting or replacing an egress guard:

- **Delete a validator last, after its callers are migrated.** Removing it
  earlier leaves counterparty URLs validated by nothing while its replacement
  is still being wired. And check which sibling you are deleting:
  `WebhookURLValidator` (`src/core/webhook_validator.py`) is a thin wrapper
  over `check_registration` — a caller of the gateway, not a rival validator.
- **An empty allowlist is only honest when a second scan covers what the
  first cannot see.** The raw-egress allowlist is empty, and that is truthful
  only because a second scan — with its own permanently non-empty allowlist —
  covers SDK and MCP client egress. Otherwise "all outbound HTTP goes through
  the gateway" is certified while whole client types still connect to
  counterparty URLs unvalidated.

## Decide where a new concern belongs

Ask these questions in order:

1. **Does the SDK already own it?** Address classification, resolution,
   pinning, and signing do. Import it. If the SDK is wrong, fix it upstream — a local
   copy is how the two go out of step.
2. **Is it a policy the gateway should decide once?** Then it belongs in
   `egress/`, in the module that owns that decision, expressed as a value rather
   than an effect where possible (`attempts.py` is the model: no I/O, a pure
   state machine).
3. **Is it a call-site concern?** Then it is probably not a policy — pass it in.
   If you are about to write address logic at a call site, that is the pattern
   this package exists to remove.

## Related

- [Outbound egress: one gateway](../security/outbound-egress.md) — the rule, and the three enforcement layers
- `CLAUDE.md` Pattern #9 — the same, for agents
