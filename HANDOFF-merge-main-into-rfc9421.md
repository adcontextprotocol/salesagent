# Handoff — merging `main` into `feat/rfc9421-request-signing`

**Branch:** `merge/main-into-rfc9421` (worktree `/srv/ws/salesagent/a3-merge-main`)
**Not** fast-forwarded onto `feat/rfc9421-request-signing`.
**State:** 21 commits, tree clean. The 3 `[e2e_rest]` failures are FIXED and
mutation-verified. **A different blocker took their place: the 8-worker in-network gate
now WEDGES.** See §0.

| suite | last known result |
|---|---|
| unit | 7490 passed, 0 failed (local) |
| integration | 0 failed (local, in the combined 5935-passed run) |
| bdd_inprocess | 0 failed (local) |
| **bdd_e2e** | **589 passed, 0 failed** — in-network, single-server, local (was 586 / 3) |
| e2e / admin / ui | last green at `sa-e80d3f9d` / `test-results/innet_040926_1206/` |

---

## 0. THE BLOCKER — the full gate wedges, reproducibly

`cassini run` no longer completes. Twice in a row, on a DIFFERENT per-worker server
each time (`server-gw7`, then `server-gw4`), one of the eight servers goes UNHEALTHY
and the run sits quiet until killed. Both wedged at the identical point — the server's
last line is a failed delivery to a capture endpoint programmed to answer 500:

```
httpx  POST https://webhooks.adcp.test:8443/webhook/<key> "HTTP/1.1 500 Internal Server Error"
protocol_webhook_service  ERROR  Webhook for task mb_001 delivery did not succeed within the attempt budget
<silence; healthcheck fails from here on>
```

**This is a latent hang that §3's fix EXPOSED, not one it introduced.** Before the fix
no delivery ever left the server over e2e_rest (that was the bug), so the retry-ladder
and circuit-breaker paths were never entered in the per-worker stack at all. They are
entered now, and one of them does not return. The same fix exposed a second latent
vacuity the same way (`T-UC-004-webhook-ssrf-blocked`, §3) — that one is fixed; this
one is not.

It did NOT reproduce locally: a full single-server in-network `bdd_e2e` ran clean in
5m41s (589 passed). It needs the 8-worker `E2E_PER_WORKER` shape.

Leads, in the order worth trying:

1. **Which scenario.** The suspects are the retry/breaker family, which are exactly the
   scenarios that moved from xfail to XPASS once deliveries became real (16 -> 17
   xpassed): `test_persistent_webhook_failures_open_circuit_breaker`,
   `test_successful_retry_records_delivery`,
   `test_circuit_breaker_closes_after_successful_recovery_probes`. Run that family alone
   under `E2E_PER_WORKER=1` and watch `docker ps` for an unhealthy server.
2. **Is the event loop blocked?** The healthcheck stops answering, which is the
   signature of a SYNC sleep on the loop rather than of a crash (a crash restarts, a
   loop keeps logging). `WebhookDeliveryService._deliver_with_backoff` sleeps with
   `time.sleep`; establish whether the admin trigger route reaches it on a thread or on
   the loop.
3. **Not the intervals.** Both were checked and are innocent: the server's
   `DELIVERY_WEBHOOK_INTERVAL` is unset and defaults to 3600s (the batch seen in the log
   is the STARTUP one, not a 5s loop — the `"5"` at docker-compose.e2e.yml :613 belongs
   to the `tests` runner, not the server), and
   `ADCP_WEBHOOK_BREAKER_TIMEOUT_SECONDS` is 5.

Do not "fix" this by reverting §3. The three legs it repairs are graded, mutation-
verified behaviour; the hang is a real defect that was simply unreachable while they
were broken.

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

## 2. The three `[e2e_rest]` failures — SOLVED

Root-caused by driving the in-network stack locally and reading the SERVER's log (the
runner cannot see why a delivery did not happen). It said
`Cannot trigger report: No reporting_webhook configured for mb-001` — the delivery never
started. Three defects in a chain, each hidden by the one before it; see commit
`868f9c06b` for the full account. Verified by mutation on all three legs (wrong-but-
present bearer token, dropped 9421 signing arm, wrong legacy HMAC secret — each turns
its leg RED). Note the server holds the module in memory: a mutation needs a container
restart, and the first attempt without one survived and proved only that.

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

1. §0 — the wedge. It is the only thing between this branch and a green gate.
2. `cassini run`, confirm green.
3. Consider graduating the e2e_rest scenarios that now xpass (16 -> 17), ONE AT A TIME
   under `.claude/rules/workflows/xpass-graduation.md`. Deliberately not done in §3's
   change; several of them only xpass because deliveries became observable, which is
   exactly the situation that protocol exists to inspect rather than rubber-stamp.
4. Decide on the 5 new `origin/main` commits (§1).
5. **Only then** fast-forward `feat/rfc9421-request-signing` to this branch.

Do not fast-forward while red — it buries the remaining work in a branch that looks finished.
