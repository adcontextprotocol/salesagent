# Design spike — repo-wide secure outbound egress (#1589)

Status: **spike complete, epic not yet executed.**
Branch `feat/secure-outbound-fetch` carries throwaway proof-of-concept code that
validated the seam. It is evidence, not the deliverable — see "Disposition of
spike code".

---

## 1. What the ticket assumed, and what is actually true

The handoff for #1589 framed this as "write a wrapper that owns SSRF policy and
migrate 14 call sites". Three of those premises are wrong.

| Handoff premise | Verified reality |
|---|---|
| We must implement SSRF policy (private IPs, metadata, redirects, rebinding) | The pinned `adcp==6.6.0` SDK **already ships all of it** as public API. We implement none of it. |
| 14 egress call sites | **17.** Missing: `src/services/protocol_webhook_service.py` (buyer-supplied URL, long-lived `requests.Session`), `src/adapters/broadstreet/client.py`. `context_manager.py` / `retry_utils.py` reference exception types only — no egress. |
| Confirm the spec "does not mandate accepting arbitrary buyer URLs" | The spec goes much further: it **mandates a 6-point check** that fetchers MUST apply. |

Also stale: CLAUDE.md says the repo targets spec 3.1.0-beta.3 via `adcp==5.7.0`.
It targets **3.1.1 via `adcp==6.6.0`** (`docs/adcp-spec-version.md`,
`tests/unit/test_adcp_spec_version.py:5`). CLAUDE.md needs correcting.

## 2. Spec grounding (satisfies the CLAUDE.md spec-grounding gate)

Authoritative: **AdCP 3.1.1**, the pinned version.
Source: `docs/building/by-layer/L1/security.mdx`, §"Webhook URL
validation (SSRF)" (docs dir tops out at 3.1.0; 3.1.1 is a patch release).

> Before any outbound fetch to a counterparty-controlled URL, fetchers MUST:
> 1. Reject non-HTTPS URLs in production.
> 2. Resolve the hostname and reject reserved ranges — incl. RFC 6598 CGNAT
>    `100.64.0.0/10`, `169.254.169.254`, IPv4-mapped `::ffff:0:0/96`, …
> 3. **Pin the connection to the validated IP** (DNS-rebinding defence;
>    "re-resolving DNS without pinning is not sufficient").
> 4. **Refuse to follow redirects.**
> 5. Cap response size and timeouts.
> 6. **Do not echo fetch errors** to the agent that supplied the URL.

Applies to `push_notification_config.url`, `accounts[].notification_configs[].url`,
collection-list `webhook_url`, TMP provider `endpoint`, `adagents.json`
`authoritative_location`, `reporting_bucket.setup_instructions`.

Two normative constraints that bound the design:

- **No domain allowlist.** The URL contract is "unconstrained beyond
  `format: uri`". Buyer URLs are buyer-supplied by design.
- **No port allowlist by default.** §"Destination port: permissive by default":
  *"SDKs that ship a `DEFAULT_ALLOWED_PORTS` constant MUST default it to 'no
  restriction' and surface `{443, 8443}` as an opt-in profile, never as a
  default."* Hardened mode is operator policy, not protocol.

Conformance storyboard: **ungraded.** No storyboard step exercises SSRF
rejection; this is a security obligation from the L1 prose, not a wire contract.
BDD coverage is therefore ours to design (see EPIC-6), not derivable from a
generated feature.

## 3. The architecture decision

**The application implements no SSRF protection, ever.** Not private-IP
classification, not a metadata blocklist, not resolve-then-check, not redirect
re-validation. Every one of those belongs to a maintained library.

The split:

| Concern | Owner |
|---|---|
| Response state machine — status, redirects, 1xx, decompression, TLS, pooling | `httpx` |
| Address validation, cloud-metadata blocking, resolve-once + **IP pinning** | `adcp.signing` |
| Requiring TLS; what counts as retryable; backoff | one module, `src/core/security/outbound_http.py` |
| Anything else | nobody — call sites just send |

Rationale: SSRF has recurred in this codebase because policy lived at call sites,
so each new outbound call shipped without it. Centralising *our own* copy of the
policy would only move the recurrence. Deleting our copy entirely, and routing
every call through one seam backed by a maintained library, is what makes the
recurrence structurally impossible — enforced by an AST guard.

Redirect refusal (spec point 4) comes free: `httpx.Client` defaults
`follow_redirects=False`. We comply by not writing code. **Do not set it True.**

## 4. Verified SDK capability inventory (`adcp==6.6.0`)

All public, all probed against a live corpus during the spike:

| Spec point | SDK surface | Verified |
|---|---|---|
| 1 scheme | `resolve_and_validate_host` — http/https allowlist | `ftp://`, `file://` rejected |
| 2 ranges | `ipaddress` flags + `BLOCKED_METADATA_IPS` | v4-mapped, NAT64, 6to4, zoned link-local, IMDS, IMDSv2, Oracle, Alibaba all blocked |
| 3 pinning | `build_ip_pinned_transport` / `build_async_ip_pinned_transport` | resolve-once → pinned httpcore backend; TLS SNI preserved |
| 5 timeouts | httpx | — |
| ports | `DEFAULT_ALLOWED_PORTS={443,8443}`, `allowed_ports=None` default | spec-conformant: opt-in, not default |
| escape hatch | `allow_private=True` | unblocks loopback; metadata stays blocked unconditionally |

### Two gaps the SDK does not close

1. **CGNAT `100.64.0.0/10` was accepted** — spec-mandated block. Root cause:
   Python's `is_private` is `False` for RFC 6598 (shared, not private, address
   space), and the SDK classifies via `ipaddress` flags.
   **Fixed upstream:** issue
   [adcontextprotocol/adcp-client-python#973](https://github.com/adcontextprotocol/adcp-client-python/issues/973),
   PR [#974](https://github.com/adcontextprotocol/adcp-client-python/pull/974)
   (also adds `192.88.99.0/24`, RFC 7526 6to4 relay anycast). Red/green proven;
   5874 SDK tests green.
   *Until #974 releases and we bump the pin, CGNAT remains reachable.* We do
   **not** compensate in salesagent — that would reintroduce the exact
   application-level SSRF logic this decision forbids.
2. **HTTPS is not enforced** — the SDK permits plain `http` by design (it is a
   transport validator, not a transport policy). Requiring TLS is the one policy
   the seam legitimately owns.

## 5. Constraint discovered: pinning is per-destination

`build_ip_pinned_transport(uri)` resolves **at construction** and is
single-host-scoped — the docstring is explicit that reusing it for another host
bypasses the pin.

Consequence: **there is no long-lived shared client.** This kills
`ProtocolWebhookService._session` (a module-lived `requests.Session`) and the
`atexit`/shutdown hook in `src/app.py:103` that closes it. That is a real
behavioural change (loss of cross-destination connection pooling) and needs to be
called out in the PR, not slipped in.

## 6. The larger defect the spike surfaced

SSRF was a symptom. The actual duplication:

**Four independent implementations of "POST a signed webhook with retry and
backoff"** — `src/core/webhook_delivery.py`, `src/services/webhook_delivery_service.py`,
`src/services/protocol_webhook_service.py`, `src/services/order_approval_service.py`.
Each re-derives: retry count, exponential backoff, 4xx-terminal / 5xx-retry
classification, timeout handling, auth-header construction.

A seam that only hands back an HTTP *client* leaves all four copies in place and
adds a fifth thing to get wrong per site. The seam must therefore be a **send
function** that owns transport + retry + classification, so call sites keep only
what is genuinely theirs (metrics, DB delivery records, circuit breaker).

Spike measurement of the collapse, on two sites actually converted:
`webhook_delivery_service.py` **−52/+12**; `webhook_delivery.py` **−156/+~70**
(the remainder is genuine bookkeeping, not transport).

This is a DRY-invariant fix per CLAUDE.md, i.e. a correctness requirement.

## 7. Target seam

`src/core/security/outbound_http.py`, sole public surface:

```python
send(url, *, method="POST", json=None, params=None, headers=None,
     content=None, timeout=10.0, max_attempts=3) -> OutboundResult
async asend(...)  -> OutboundResult          # same policy, same failure modes
```

- `OutboundResult` — `.response`, `.status_code`, `.json()`, `.attempts`, `.duration_seconds`
- `OutboundError` — marker base, so a call site that only logs writes one `except`
  - `OutboundRequestBlocked(OutboundError, AdCPInvalidRequestError)` — scheme or
    address refused. Terminal; never retried; message never names a resolved IP
    and never distinguishes unresolvable-from-rejected (spec point 6).
  - `OutboundDeliveryFailed(OutboundError, AdCPServiceUnavailableError)` —
    reachable but undelivered. Carries `.attempts`, `.last_status`.

Both are `AdCPError` subclasses, so the transport boundary translates them to the
wire envelope like any other typed failure (CLAUDE.md pattern #5). Call sites do
not build clients and do not classify transport errors.

Env flags, both default off (guarded posture):
`ADCP_OUTBOUND_ALLOW_PRIVATE`, `ADCP_OUTBOUND_ALLOW_INSECURE`.

`max_attempts=1` is how a non-idempotent or vendor call opts out of retry.

## 8. Call-site inventory (17), by threat model

Not equal. The PR must say so rather than implying every line was a vulnerability.

**Counterparty-supplied URL — the actual SSRF surface (6):**
`src/core/webhook_delivery.py`, `src/services/webhook_delivery_service.py`,
`src/services/protocol_webhook_service.py`, `src/services/order_approval_service.py`,
`src/core/creative_agent_registry.py`, `src/core/property_list_resolver.py`
*(already validates via `check_url_ssrf`, but with no pinning)*

**Operator-configured vendor endpoint (9):** `src/adapters/base_workflow.py`,
`gam_reporting_service.py`, `kevel.py`, `mock_ad_server.py`, `triton_digital.py`,
`xandr.py`, `broadstreet/client.py`, plus admin `settings.py`, `tenants.py`

**Operator OAuth to Google (1):** `src/admin/blueprints/auth.py`

**Also in scope (1):** `src/core/retry_utils.py` — `aiohttp` exception types only;
remove the dependency if nothing else uses it.

Adapter/OAuth sites route through the seam for uniformity and guard-cleanliness,
not because they were exploitable.

## 9. To delete

- `src/core/security/url_validator.py` — hand-rolled, weaker than the SDK
  (misses CGNAT, IPv4-multicast; `socket.gethostbyname` returns one IPv4 so
  multi-A-record and IPv6-only hosts go unchecked; no pinning)
- `WebhookURLValidator` in `src/core/webhook_validator.py`
  (keep `validate_webhook_task_type` — unrelated)
- the pre-flight `check_url_ssrf` call in `property_list_resolver.py`
- `tests/unit/test_ssrf_url_validator.py` (294 lines testing deleted code —
  replaced by seam tests, EPIC-6)

Note `requests.Session.request` defaults `allow_redirects=True`, so
`webhook_delivery.py` and `protocol_webhook_service.py` today validate the URL and
then follow a 302 to an internal address unchecked. Migration closes that.

## 10. Disposition of spike code

Uncommitted on `feat/secure-outbound-fetch`: the seam module plus two converted
call sites, no tests, no guard. It proved the design and produced the measurements
above.

**Recommendation: reset the branch to base and re-deliver through the epic.**
The spike has no tests, converted 2 of 17 sites, and would otherwise merge as a
half-migration — the exact residual state this epic exists to avoid.
Preserve this note; discard the diff.

## 11. Epic shape

Sequenced so nothing lands half-migrated. Full breakdown, per-issue acceptance
criteria and test strategy go in the beads epic.

| # | Issue | Gate |
|---|---|---|
| 1 | Seam module + unit tests (scheme, address, retry, error taxonomy, no-redirect) | seam green in isolation |
| 2 | Bump `adcp` pin once #974 releases; assert CGNAT blocked | pin guard + regression test |
| 3 | Migrate the 6 counterparty sites; delete `url_validator.py` + `WebhookURLValidator` | integration green |
| 4 | Migrate the 9 operator sites + OAuth; drop `aiohttp` | integration green |
| 5 | `ProtocolWebhookService` session removal + `src/app.py` shutdown-hook change | explicit perf note in PR |
| 6 | BDD coverage for the ungraded obligation, across all four transports | scenarios wired, not dormant |
| 7 | AST guard banning `httpx`/`requests`/`urlopen` outside the seam — **empty allowlist** | guard self-test proves it can fail |
| 8 | CLAUDE.md: record the decision; fix the stale 3.1.0-beta.3 / adcp 5.7.0 line | — |

Issue 7 is the load-bearing one. A PR that migrates every call site but ships no
guard has not solved #1589.
