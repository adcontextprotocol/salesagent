# Handoff — merging `main` into `feat/rfc9421-request-signing`

**Branch:** `merge/main-into-rfc9421` (worktree `/srv/ws/salesagent/a3-merge-main`)
**Not** fast-forwarded onto `feat/rfc9421-request-signing` — the suite is not yet green.
**State:** 18 commits, tree clean. **3 failures left, all `[e2e_rest]`, all in one scenario file.**

Last full in-network run: `sa-e80d3f9d` → `test-results/innet_040926_1206/`.

| suite | result |
|---|---|
| unit | 7735 passed, 0 failed |
| integration | 3510 passed, 0 failed |
| bdd_inprocess | 2444 passed, 0 failed, 5930 xfailed |
| bdd_e2e | 586 passed, **3 failed**, 2023 xfailed |
| e2e | 161 passed, 0 failed |
| admin | 138 passed, 0 failed |
| ui | 5 passed, 0 failed |
| security-audit gate | OK |

Down from ~21. Everything below §2 is done and verified; §2 is all that is left.

---

## 1. Merge status

Five upstream PRs merged in dependency order (#2091, #1941, #1858, #1802, #2141), one
merge commit each with a resolution ledger. Zero merge-created test losses, proven by
bare node-id comparison against both parents.

**`origin/main` has since moved 5 commits ahead of the merge base** — it was an ancestor
when the merge was made and is not one now. Decide whether to pull those in before the
fast-forward:

```bash
git log --oneline $(git merge-base origin/main HEAD)..origin/main
```

**Central design decision** (owner-approved): the RFC 9421 arm was wired *into* the egress
seam rather than kept as a second boundary in front of it. `outbound_http.py` shipped with
a `sign:` hook that had zero callers; that hook is what signing now uses.

---

## 2. THE ONLY REMAINING WORK — 3 uc004 `[e2e_rest]` failures

```
tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_bearer_token_webhook_authentication[e2e_rest]
tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_hmacsha256_signed_webhook_payload[e2e_rest]
tests/bdd/test_uc004_deliver_media_buy_metrics.py::test_rfc_9421_signed_webhook_payload_when_no_authentication_block_is_registered[e2e_rest]
```

All three fail identically: `AssertionError: No webhook POST was made` — the capture
service received nothing. All three pass on a2a/mcp/rest in-process.

**These are a MERGE REGRESSION, not an uncharted gap.** All three carry
`# Graduated e2e_rest (salesagent-n78j0.13 / .1.4)` comments in `tests/bdd/conftest.py`
— they were passing on e2e_rest before this merge and #1802's egress seam broke them.

### What is measured (do not re-derive)

* The three that fail all seed AUTH MATERIAL: bearer credential, HMAC credential, or a
  provisioned 9421 signing key. The sibling `@T-UC-004-webhook-notification-type`
  registers no auth block and no key, delivers UNSIGNED, and **passes** on e2e_rest.
  Auth material is the only axis that separates pass from fail.
* Schemes are CANONICAL (`"HMAC-SHA256"`, `"Bearer"` — `_canonical_scheme` refuses
  anything not in the pinned enum), so this is **not** the `scheme_not_in_spec` refusal
  that explained the `test_webhook_signing_boundary` failures (§4 below). Credentials are
  32 chars, so it is not `credentials_too_short` either.

### One hypothesis KILLED — do not spend time on it

`_persist_webhook_config_if_needed` is called behind
`if getattr(env, "_session", None) is not None:` at four Given sites, which looks exactly
like the silent-env skip the BDD guard forbids. **It is not the cause.** `_set_active_webhook`'s
own docstring records that `BaseTestEnv` binds `_session` to the LIVE server's database
when `e2e_config` is present (`_base.py` :1198-1212), and the PASSING notification-type
scenario goes through the same guarded call. The row is written where the server reads it.

### The live candidate, and how to settle it

`protocol_webhook_service._deliver`'s own docstring names the mechanism: a tenant that CAN
sign but whose material cannot be honestly resolved **raises out of
`delivery_signer_for_tenant` before `adeliver_webhook` is called at all** — "there is no
plain body to fall back to because none was ever serialized" — and the caller books it as
an `unexpected` outcome with zero attempts. Zero attempts is exactly zero POSTs.

`given_tenant_publishes_signing_key` mints through `env.provision_webhook_signing_key(monkeypatch)`,
and a monkeypatched KEK in the RUNNER process is not the KEK the server container holds
(`docker-compose.e2e.yml`'s `ADCP_SIGNING_DEV_KEK`) — see `tests/e2e/test_signing_key_kek_mismatch_e2e.py`,
which exists because that mismatch is real. That covers the 9421 row directly. Whether it
also covers the bearer/HMAC rows (which provision no key) is the open question — the seam
is handed `signer=delivery_signer_for_tenant(tenant_id)` UNCONDITIONALLY on every arm, so a
raise there kills a legacy delivery too.

**Settle it by reading the SERVER's log, not by reasoning.** The refusal/raise is logged by
the container, not by the runner, so the pytest output cannot show it:

```bash
cassini run ci tests/bdd/test_uc004_deliver_media_buy_metrics.py -k "webhook_bearer or webhook_hmac or webhook_9421"
# then, on the box, the app container's stderr for that run:
#   "Unexpected error sending webhook for task ..."   -> the signer raised (KEK mismatch)
#   "Refusing to send webhook ... [<reason>]"          -> refused_auth, and <reason> names which
```

If it is the signer raise, the fix is in the Given (provision through a path the server can
resolve, as `tests/e2e/_signing_e2e.py` does) — **not** in production, which is behaving as
designed and fail-closed.

---

## 3. What was done this session

Four commits, each verified before the next.

### `b2453c063` — posture declared through the writer that owns it

Replaced the two hand-rolled posture pokes the previous handoff flagged as "may be lying".
**The previous handoff's diagnosis was wrong and its prescribed fix does not work.** It
proposed `SigningConfig.verifier_enabled=False` everywhere on the grounds that a declared
`supported: false` under-declares an agent-level fact. It does not: the pinned
signed-requests storyboard gates all 28 negative vectors on `request_signing.supported: true`
alone, so a seller advertising `false` is OUTSIDE the rule (security.mdx :1465 routes it to
log-and-alarm). The `agent_level_posture` warning is about the DEFAULT for a tenant that
declared nothing — a different case.

What was actually wrong: both pokes reimplemented `BaseTestEnv.declare_request_signing(bucket="unsupported")`
badly — bare `{"supported": false}` with no derived `identity.brand_json_url`, skipping
`ensure_declarable_identity_host`. A single-label `virtual_host` derives `http://`, which
REFUSES the whole declaration and silently returns every operation to the `supported`
bucket. A declaration that fails open is worse than none.

**Two levers, and the split is measured:**

* `tests/bdd/conftest.py` `@egress` routes → `declare_request_signing`. Those scenarios carry
  **15 e2e_rest params**, 5 of which register webhook credentials, and that server is a
  separate process — a config patch in the runner cannot reach its verifier, but the
  declaration can (the writer uses the env's own session, bound to the live server's DB).
* `tests/integration/test_webhook_hmac_credentials_ingest_refusal.py` → new
  `inbound_verifier_disabled` (`tests/helpers/signing.py`), autouse. Every transport that
  module dispatches on is in-process. It **cannot** use the declaration:
  `ensure_declarable_identity_host` assigns the shared constant `SIGNING_AGENT_HOST` and
  `virtual_host` is uniquely indexed, so the one test that opens three envs dies on a
  `UniqueViolation`.

Each helper's docstring names the other and says why it is not usable there.

### `0cfe0ae8e` — wire-presence from the declaration, not the transport enum

Closes `test_no_step_module_keys_behavior_on_transport_impl`; `tests/bdd/steps/` no longer
names `Transport.IMPL`. `_wire_body` now delegates to `_wire_or_none` — the positive
`TransportResult.has_wire` predicate that was sitting in that module UNCALLED, waiting for
this caller.

The old guard had two defects in one expression: it inferred wire-presence from transport
IDENTITY, and a ctx carrying the IMPL member with no `TransportResult` reached the
serializer with no dispatcher having declared anything — GH #1744's hole in a second
spelling. Contract tests moved with it and got stronger; `TestUnsetTransportIsNotImpl`
became `TestNoDeclarationIsNotADeclaredAbsence` and gained
`test_a_transport_key_alone_does_not_buy_the_fallback`.

`Transport.IMPL` itself still exists (69 refs, mostly integration suites that legitimately
dispatch it). The enum's own deletion is the remainder of salesagent-a1-uc004/1210.

### `0464a9504` — the delivery-report sender must carry `idempotency_key`

**The previous handoff's §4 "contradiction" (status 200 + `captured == 0`) does not
reproduce** — the test it was observed on passes; commit `8cc1ccb9d` landed after the
observation. Measuring the four that remained gave two ordinary causes.

1. **Production gap, fixed in production.** The three senders disagreed:
   `protocol_webhook_service` merged the key at the seam call, `order_approval_service` put
   it in the payload upstream, `webhook_delivery_service` passed the payload UNTOUCHED
   behind a comment asserting a "dispatch-level value" does not belong in a request body.
   The pin says otherwise: `docs/building/by-layer/L3/webhooks.mdx` @ v3.1.1 :195 ("Every
   webhook payload carries a required `idempotency_key`") and :253, which names THIS
   sender's events ("For delivery-report data events such as `scheduled`, `final`,
   `delayed`, and `adjusted` … dedupe the transport event with `idempotency_key`"). Graded
   by `dist/compliance/3.1.1/universal/webhook-emission.yaml` step `idempotency_key_presence`.
   `tenant_id` is routing and stays off the body; the key is part of the document.

2. **Production right, test re-graded.** `AuthenticationScheme` @ v3.1.1 is exactly
   `["Bearer", "HMAC-SHA256"]`, and #1802's seam answers a stored `hmac-sha256`/`bearer`/
   `basic` row with `refused_auth`/`scheme_not_in_spec` before serializing. Three rows
   asserting the opposite moved to
   `test_a_scheme_outside_the_pinned_enum_is_refused_not_downgraded`, which grades the
   refusal on three axes (zero captures, `delivered is False`, the refusal announced naming
   the scheme) — each alone vacuous, together ruling out the silent downgrade.

Plus three missed sites of classes already fixed: the retired dict passed where a typed
`WebhookTaskContext` was expected (`test_signing_capability_honesty`); an expected
`SignalsAgent` leaving `tenant_id` at its default, which is the field `config_for` reads to
SELECT THE SIGNING KEY; and an allowlist that went stale and empty when both uc011 bypasses
were extracted into `_self_dispatch_list`.

### `637071300` — the invoice-recipient scenario xpassed on a refusal it does not grade

`T-UC-003-ext-t` XPASSED on `[mcp]` alone. Not a graduation — the xpass was vacuous. The
scenario asked only for "fails / VALIDATION_ERROR / has a suggestion", and on MCP an
unrelated refusal arrives: `update_media_buy` types its parameters, so the spec-defined
`invoice_recipient` field is rejected as an "Unexpected keyword argument" before any
authorization check runs.

The field is NOT over-specified against the pin — it is a top-level property of
`update-media-buy-request.json` @ v3.1.1, so refusing it for its shape is itself the gap.
Per the xpass-graduation protocol the scenario was corrected first:
`And the suggestion should contain "authorized"` pins the refusal to BR-RULE-214's own
POST-F3, which a schema-shape rejection cannot say. All three transports now xfail on the
real gap; the ledger entry is unchanged.

---

## 4. Tooling — read this, it will save you hours

### Use cassini. Do not grind locally.

```bash
cd /srv/ws/salesagent/a3-merge-main
cassini run --fail-if-running     # detached; all 7 suites on the box
cassini status sa-<id>            # reconciles + prints the per-suite table
```

`cassini status` blocks for a while on a running job — give it a `timeout` and re-poll
rather than assuming it hung.

### Local DB

```bash
.claude/skills/agent-db/agent-db.sh up > /tmp/a3db.env   # then `source /tmp/a3db.env`
```

Shell state does not persist between tool calls; sourcing a file is what makes it repeatable.

### Traps that cost real time

- **BDD locally: run serial** (`-n 0`). xdist deadlocks on a single agent-db. `-p no:xdist`
  does NOT work — it breaks `tests/bdd/scenario_liveness.py`'s hook registration.
- **`tests/integration/test_creative_agent_live.py` errors locally** (20 of them) — it needs
  the full stack. Clean on cassini. Not real.
- **`run_all_tests.sh` leaves `test-results/` root-owned**, which breaks its own JSON report
  extraction and local BDD runs. Script bug still unfixed.
- **`--showlocals` (`-l`) is the fastest diagnostic here**, and `--lf` after a long suite
  re-runs only the failures in seconds.
- A failure that reproduces in isolation is a different animal from one that only appears in
  the full run. Two of the five integration failures passed under `--lf`; both were
  order-dependent (see the signing-provider cache note in memory).

---

## 5. Recommended order

1. §2 — the three `[e2e_rest]` rows. Read the SERVER's log; do not reason from the runner's.
2. `cassini run`, confirm green.
3. Decide on the 5 new `origin/main` commits (§1).
4. **Only then** fast-forward `feat/rfc9421-request-signing` to this branch.

Do not fast-forward while red — it buries the remaining work in a branch that looks finished.
