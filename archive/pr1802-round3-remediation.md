# PR #1802 round-3 remediation plan

This document is the frozen scope authority for the remediation epic
`salesagent-jdq72` (round 3 of the human review of PR #1802,
`feat/secure-outbound-fetch`). Every `plan-lane-execute`, `structural-change`,
`structural-guard`, `task-fix`, and `task-single` lane in the epic grades its
design and its fidelity against this document, not against the raw design
notes under `.claude/notes/pr1802-r3/` — those are untracked working material.
If this document and a note disagree, this document wins; if a later
"Alterations" section and earlier text disagree, the Alterations section wins.

Context, fixed by the epic and not renegotiable here:

- All findings were independently re-verified against head `8e7393e63` after
  two merges from `main`. 20 of 22 hold; #12 (log forgery) was fixed in
  `38addadd5`; F3 was moot (covered by issue #2109). Four one-liners landed in
  `558ec9e73`.
- The lane numbering and formula routing below is the epic's and is FIXED.
- Lanes 2 and 3 compose into one hole the review filed separately: a failed
  `__enter__` on a `LocalOriginMixin` env leaks
  `ADCP_OUTBOUND_ALLOW_PRIVATE=true` for the rest of the xdist worker
  (lane 2), and that hatch opens all six supplement ranges rather than the
  loopback and RFC 1918 classes its only users need (lane 3). Either fix alone
  narrows the window; both together close it. They land together.

| Lane | Findings | Formula |
|---|---|---|
| 1. Egress gate | 2a, 2b, F1, F2 | structural-change |
| 2. Harness enter lifecycle | 3, 8, 11-mixin | plan-lane-execute |
| 3. Egress policy: supplement ranges outside the hatch | 5 | plan-lane-execute |
| 4. Two vacuous Then steps | 9 (severity) | task-fix |
| 5. Then-step reachability guard | 9 (enforcement) | structural-guard |
| 6. Dead breaker verdict | 10 | structural-change |
| 7. create-kwargs builders | 4b | structural-change |
| 8. Prose drift | 11 | task-single |
| 9. Diagnostic accessor conversions | 9 (residue) | task-single |

---

## Lane 1: egress gate

**Formula:** structural-change. **Closes findings:** 2a, 2b, F1, F2.

### The root

The gate's authority is split between ruff — which owns suppression semantics
and path resolution — and hand-written mirrors of ruff's semantics inside
`tests/unit/test_ruff_egress_bans.py`: a noqa regex, enumerated path lists,
and an enumerated scan set. Every one of the four holes is a place where a
mirror diverged from the thing it mirrors. The test proves soundness of listed
entries and calls it completeness; non-vacuity was made executable, but
completeness stayed prose. The fix retires the mirrors: ruff's own
`--ignore-noqa` diagnostic set becomes the authority on what is suppressed,
and the ban table's obligations are derived from the sanctioned importers
instead of hand-listed.

Corrections to the reviewer's account — load-bearing, a lane executed against
the reviewer's framing does the wrong work:

- The suggested `select RUF100` remedy closes nothing: a blanket noqa
  suppressing a live TID251 counts as *used*, so RUF100 stays silent
  (executed probe).
- "Match all three noqa forms" undercounts. `# noqa:TID251` (no space) and
  `# flake8: noqa` are forms four and five; enumerating spellings is the same
  disease as enumerating paths. `--ignore-noqa` retires the enumeration.
- 2b is one entry short: `fastmcp.Client(url)` infers an un-pinned
  `StreamableHttpTransport` from a bare URL (verified at runtime) — the review
  banned the transports but not the constructor that manufactures one.
- F1 is two entries short: `httpx2` and `httpcore2` are installed (transitive
  via `genai-prices`) and importable; `httpx2` is one character from the
  banned spelling.
- F2 as reviewed does not work: naively appending `scripts/` misses the named
  exemplar, because ruff's directory walk honors `.gitignore`, whose
  `sync_*.py` rule (`.gitignore:60`) with an `ops/`-blind negation (`:61`)
  hides the git-tracked `scripts/ops/sync_all_tenants.py`.
  `--no-respect-gitignore` plus the negation repair is required.

### The change-set

Five edits. Nothing new is invented: the mechanism reuses ruff itself, the
existing closed-set constants, and the existing case (a) parametrization.

**1. `--ignore-noqa` becomes the authority (closes 2a).** In
`tests/unit/test_ruff_egress_bans.py`, add one helper,
`_suppressed_violation_sites(code)`, that runs
`ruff check --config ruff-egress.toml --ignore-noqa --no-respect-gitignore
--output-format concise` over `_SCAN_DIRS` and returns every
`(relpath, lineno)` where *code* fires absent ALL suppressions — every
spelling ruff honors is visible by construction. Re-found cases (c) and (d)
on that set V, uniformly for `TID251` and `ANN401` (one parametrized
implementation, per the DRY invariant):

- Case (d), closed set: `{file for file, _ in V} == recorded_constant`
  (`SEAM_FILES` / `ANY_EXEMPT_FILES` unchanged as file sets). Strictly
  stronger than before: it catches an unlisted exemption of any spelling and
  independently catches a raw violation even if the Makefile gate line were
  reverted.
- Case (c), liveness plus no-spelling-drift, per file:
  `count(V ∩ file) == count(marker_lines(file))` and every marker line ∈ V.
  The `_marker_lines` regex is kept only to locate canonical markers; its
  incompleteness is harmless — an unseen suppression still appears in V and
  breaks the count equality, and a dead marker is a marker line ∉ V.

`_NOQA_MARKER` survives only as the canonical spelling that
`test_every_recorded_seam_file_carries_a_line_scoped_noqa` (`:279-287`)
requires. `--ignore-noqa` does not bypass `[lint.per-file-ignores]`, so the
ANN401 negated-glob scoping at `ruff-egress.toml:36-37` is unaffected.

**2. Re-export bans, derived not hand-listed (closes 2b plus the missed
`Client` hole).** In `ruff-egress.toml`, after the module bans (`:44`), add
six banned-api lines (all verified firing, including via aliased attribute
access `oh.httpx`):

- `"src.core.security.outbound_http.httpx"` — re-export of the seam's own
  import.
- `"src.core.security.egress.policy.ipaddress"` — re-export of the egress
  package's import.
- `"src.core.utils.mcp_client.StreamableHttpTransport"` — re-export of the
  MCP seam's transport import.
- `"fastmcp.Client"`, `"fastmcp.client.Client"`,
  `"fastmcp.client.client.Client"` — `Client(url)` infers an un-pinned
  transport; the seam passes `transport=` only.

In `src/core/utils/mcp_client.py:33`, the seam's own
`from fastmcp.client import Client` gains a line-scoped
`# noqa: TID251 - the MCP seam; only constructed with transport=, never a
URL (GH #1589)`. This is a live exemption (strip it → TID251 fires at `:33`);
`mcp_client.py`'s expected V-count goes 1 → 2. `SEAM_FILES` is unchanged
(file-granular).

In `test_ruff_egress_bans.py`: extend `_SYMBOL_BAN_PATHS` (`:85-102`) so case
(a) proves the new entries fire (add the seam path per re-exported name, and
`"Client": ("fastmcp", "fastmcp.client", "fastmcp.client.client")`), and add
the derivation test `test_every_seam_reexport_path_is_banned`: for every
TID251-suppressed import site in V, the dotted path `<module>.<name>` of each
binding must be in the parsed banned-api table. A fourth seam file (or a
second import in an existing one) fails here until its re-export path is
banned — completeness is executable, not prose. (`_import_bindings_at` is
~10 lines of `ast.walk` over `Import`/`ImportFrom` at that line; sites under
`scripts/` are excluded — scripts are not importable as `src.`-style modules.)

**3. The missing modules (closes F1 plus two the reviewer missed).** In
`ruff-egress.toml`, five module ban lines: `httpcore`, `urllib3`,
`http.client`, `httpx2`, `httpcore2` — each with a message pointing at
`src/core/security/outbound_http.py` (GH #1589). `_MODULE_BANS`
(`test_ruff_egress_bans.py:79`) gains the same five names; case (a) proves
each fires in all three spellings (15 new positive params). Recorded
non-additions, as one dated comment block in the toml: `websockets` (not
HTTP-shaped, no feature uses it), bare `socket` / `asyncio.open_connection`
(raw TCP is not an honest-mistake path to HTTP), `ftplib`/`smtplib`/
`xmlrpc.client` (xmlrpc rides http.client, which is banned). Zero imports of
the five newly banned modules exist under `src/` or `scripts/` — the lines
start green.

**4. Scan set: `scripts/` in, gitignore out of the loop (closes F2).**

- `Makefile:18` →
  `uv run ruff check --config ruff-egress.toml --no-respect-gitignore src/ scripts/`.
- `.gitignore:61`: `!scripts/sync_*.py` → `!scripts/**/sync_*.py`. A tracked
  file invisible to tooling is its own defect; fix it AND keep
  `--no-respect-gitignore` so a future gitignore edit cannot silently re-open
  the walk.
- `test_ruff_egress_bans.py`: `_SCAN_DIRS = ("src/", "scripts/")`, used by
  `_suppressed_violation_sites`. This makes the unit test, not the Makefile
  line, the authority on the scan set. Add one positive-case probe under
  `_SYNTHETIC_SCRIPTS_PATH = "scripts/_synthetic_egress_probe.py"` (one
  param — banned-api entries are not path-scoped).
- The two live `scripts/` sites each get a line-scoped, liveness-proven noqa,
  recorded in a new shrink-only constant `SCRIPT_EXEMPT_FILES` (NOT
  `SEAM_FILES`, which is a floor meaning "sanctioned seam"; these mean "debt,
  retire me"): `scripts/dev/gen_test_tls.py:39` (`import ipaddress` —
  builds certificate IP SANs, not address classification) and
  `scripts/ops/sync_all_tenants.py:11` (`import requests` — ops-plane
  self-call to a hardcoded loopback URL; the seam's policy refuses loopback
  by design, so routing it through the seam would be wrong, not safer;
  migration to an in-process invocation is a follow-up). Case (d)'s closed
  set becomes `SEAM_FILES | SCRIPT_EXEMPT_FILES` for TID251.

On the ratchet constraint: these two entries are not allowlist growth.
Before, the entire `scripts/` tree was an unscanned, unbounded implicit
exemption; after, it is scanned with exactly two recorded, line-scoped,
liveness-proven exceptions. The true exempt surface shrinks from "all of
scripts/" to two lines.

`alembic/`: verified zero violations under this config and zero `src/`
imports of it. Decision recorded: not extended — `ipaddress` has legitimate
migration uses (CIDR columns) and extending invites false positives. The
`ruff-egress.toml` header names `alembic/` as deliberately out of scope,
replacing the "src/ ONLY" self-disclosure at `:4` with the new scope
statement.

**5. Deliberately NOT changed.** No import hook, no socket guard, no runtime
check anywhere outside the seam — CLAUDE.md pattern 9 forbids a second
runtime egress mechanism, and the threat model is honest drift, not an
adversarial author (an author writing `importlib.import_module("httpx")` is
evading the gate, and no in-repo gate survives its own author). The
dynamic-import residual is accepted and named in the config header. No
RUF100, no expanded noqa regex — the regex authority is retired, not
extended. `SEAM_FILES` stays a file-set floor; `ANY_EXEMPT_FILES` untouched
(its 2a-class hole closes for free under the uniform mechanism).

### The deletion list

- `test_ruff_egress_bans.py`: `_strip_one_noqa`,
  `_assert_rule_fires_on_line`, `_NOQA_STRIP_RE`, and the 28-subprocess
  strip-and-rerun loop (replaced by the single `--ignore-noqa` run).
- `ruff-egress.toml:4`: the "src/ ONLY" scope self-disclosure (replaced by
  the new scope statement naming `scripts/` in and `alembic/` deliberately
  out).
- `.gitignore:61`: the `!scripts/sync_*.py` negation (replaced by
  `!scripts/**/sync_*.py`).
- The false contract prose at `test_ruff_egress_bans.py:22-23` ("a new
  exemption fails until recorded here") is made true by the mechanism, not
  deleted.

### Grading

Each row was executed as a probe or follows mechanically from one. Measured
anchors: `--ignore-noqa` over `src/` reveals exactly 28 errors (3 TID251 +
25 ANN401, all five suppression spellings included); the F2 probe goes 1 → 2
errors under `--no-respect-gitignore`.

| Mutation | Reddened by |
|---|---|
| `# ruff: noqa: TID251` + `import httpx` in a new `src/` file | case (d): file appears in V, not in `SEAM_FILES` |
| Same via bare `# noqa`, `# noqa:TID251`, or `# flake8: noqa` | same — V is spelling-blind by construction |
| Second suppressed import in a seam file, any spelling, no canonical marker | case (c) count equality: V-count 2 ≠ marker-count 1 |
| Dead noqa (canonical marker on a non-violating line) | case (c): marker line ∉ V |
| `from src.core.security.outbound_http import httpx` at a call site | Makefile gate + case (a) param |
| Delete any seam re-export ban line from the toml | case (a) param fails AND `test_every_seam_reexport_path_is_banned` fails |
| Fourth seam file (new noqa'd import) without banning its re-export path | derivation test: path not in banned-api |
| `from fastmcp import Client` at a call site / delete a `Client` ban line | gate fires / case (a) param fails |
| Remove `mcp_client.py:33`'s noqa without removing `Client` | the gate itself reddens; re-add it dead → case (c) |
| Delete the `httpcore` (or urllib3/http.client/httpx2/httpcore2) ban line | case (a) params fail |
| Revert `Makefile:18` to `src/`-only | any `scripts/` violation still lands in the test's V (`_SCAN_DIRS` is independent) → case (d) |
| Drop `scripts/` from `_SCAN_DIRS` | both `SCRIPT_EXEMPT_FILES` entries vanish from V → case (d) fails on missing |
| Re-hide `sync_all_tenants.py` via gitignore | `--no-respect-gitignore` in both the Makefile line and the helper makes the walk indifferent (measured: 1 → 2 errors) |
| Break/delete `ruff-egress.toml` | existing `test_clean_snippet_yields_no_tid251` returncode assertion (`:196-199`), unchanged |

### Boundary

This lane touches `ruff-egress.toml`, `test_ruff_egress_bans.py`,
`Makefile:18`, `.gitignore:61`, `src/core/utils/mcp_client.py:33` (one noqa
comment), and the two `scripts/` noqa lines. It must NOT touch
`src/core/security/egress/policy.py` (lane 3), any harness file (lane 2), or
add any runtime enforcement. It changes no verdict the egress policy
produces — only what the lint sees.

---

## Lane 2: harness enter lifecycle

**Formula:** plan-lane-execute. **Closes findings:** 3, 8, and the mixin half
of 11 (the `FastBackoffMixin` extraction proposed by the prose-drift note is
routed here and superseded — see the note on the two designs below).

### The root

The partial-enter unwind guard protects a lexical region, not the env's
acquisition set. `try/except BaseException: self._unwind_partial_enter()`
sits inside `BaseTestEnv.__enter__`'s body, so cooperative
`super().__enter__()` chains place every subclass's setup — before or after
the super call — outside the guard by construction. Three absences make
"acquire, then maybe leak" the path of least resistance: no seam (the only
way to add setup is an unguarded `__enter__` override), no registration API
(the base's guarded list `self._patchers` exists and is released on both
paths, but holds only patch objects, is undocumented, and its release logic
is written twice — so four independent teardown registries grew), and no
oracle (nothing grades the guarantee, so the guard comment at
`_base.py:1291-1299` claims coverage the code does not have). Finding #8 is
not a second defect: it is the newest instance of the same absence.

Probed severity, worse than either finding names: with
`BaseTestEnv.__enter__` forced to raise, `ProtocolWebhookEnv` leaks all
three of `LocalOriginMixin`'s pre-super resources — `SSL_CERT_FILE`, a
running TLS origin server, and `ADCP_OUTBOUND_ALLOW_PRIVATE=true`. A failed
enter leaves the private-range egress hatch OPEN for every later test on
that xdist worker. This composes with lane 3: lane 2 stops the leak, lane 3
narrows what the leaked hatch can open; both together close the hole.

Corrections to the reviewer's account — load-bearing:

- Folding the fast-backoff patch into `LocalOriginMixin` (one reading of the
  review's "hoist into the mixin's guarded list") breaks the suite:
  `CircuitBreakerEnv` is also a `LocalOriginMixin` env, mocks
  `outbound_http.time.sleep`, and its tests grade sleep MAGNITUDES against
  the hard-coded `BR_RULE_029_BASE_DELAYS = (1.0, 2.0, 4.0)`
  (`tests/helpers/backoff_assertions.py:20`). Roughly 15
  `assert_backoff_schedule` / `call_count` sites across
  `test_webhook_delivery.py`, `test_delivery_webhook_behavioral.py`, and
  `uc004_delivery.py` would redden. The backoff speed-up stays an opt-in
  mixin composed by the two webhook envs ONLY.
- The bare `self._fast_backoff.stop()` in the webhook envs' `__exit__`
  `finally` is NOT a live fault: `__exit__` runs only after a completed
  `__enter__`, whose first statement is a constructor that cannot fail. It
  is a convention divergence, live only when a second pre-super resource is
  added. The design removes the pattern rather than patching the read.
- The proposed single `_enter_extras()` hook is one hook short:
  `LocalOriginMixin`'s origin must exist before `_configure_mocks` runs
  (`CircuitBreakerEnv._configure_mocks` programs `self.origin`), while
  `MediaBuyDualEnv`'s patchers need the entered base. Pre and post hooks are
  the minimum.
- The review undercounts the copies: the full census is four independent
  teardown registries (`_patchers`, the mixin's name tuple,
  `_update_patchers`, the bare webhook attributes) plus `EgressHatchMixin`
  already using the base list correctly — which is the strongest argument
  that the list, generalized, is the fix.

One additional exposure neither finding names: `_base.py:1280-1286` acquires
`self._e2e_engine` and `self._session` BEFORE the `try` opens at `:1300`; a
`SASession(bind=engine)` failure leaks the engine's pool. The fix covers it
for free by moving step 1 inside the `try`.

**On the two mixin designs.** The prose-drift note proposes
`FastBackoffMixin` in `tests/harness/_mixins.py` with its own
`__enter__`/`__exit__`; the harness-lifecycle note proposes
`FastOutboundBackoffMixin` in `tests/harness/egress.py` built on the new
`_enter_pre` hook, and states that it subsumes the other proposal. The epic
routes the mixin to this lane: the harness-lifecycle shape is the one to
build. A hand-rolled `__enter__`/`__exit__` on the mixin would violate this
lane's own structural test (item 7 below).

### The change-set

One sentence: the base owns the only `__enter__`, runs subclass setup through
two hooks inside its guard, and every acquired resource registers one cleanup
in one list that both release paths share.

**1. Generalize the guarded list (`tests/harness/_base.py`).** Replace
`self._patchers: list[Any]` (`:451`) with
`self._enter_cleanups: list[tuple[str, Callable[[], None]]]`; add
`_guard(label, cleanup)` (append) and `_release_entered(errors)` (reverse
iteration, per-cleanup try/except appending into `errors` when given, then
clear). `_unwind_partial_enter` collapses to `self._release_entered(None)`
plus the existing unconditional factory unbind (kept: the binding is the one
GLOBAL that must not survive even a cleanup bug). `__exit__` steps 2 and 3
collapse to `self._release_entered(errors)`; step 1 (`_rest_client`) and the
`self.mock.clear()` / `_identity_cache.clear()` tail stay. The
`ExceptionGroup` behavior (`_base.py:1401-1405`) is preserved.

**2. Base-only `__enter__` with two hooks.** The nested-env assertion stays
before the `try` (it must not unwind the OUTER env's factories). Inside the
`try`: `self._enter_pre()`; step 1 (engine/session/factory binding, moved
inside the `try`, registered via `self._guard("db", self._release_db)` — a
new method spelling the factory-unbind/session-close/engine-dispose sequence
once); step 2 (`EXTERNAL_PATCHES`, each registered
`self._guard(f"patch:{name}", patcher.stop)`); `self._configure_mocks()`;
step 3 (e2e seeding); `self._enter_post()`. On `BaseException`:
`self._unwind_partial_enter(); raise`. `_enter_pre` runs inside the guard
before database setup; `_enter_post` after mocks are configured. The guard
comment's coverage claim becomes true; the "350 further errors" / "became
443" drift resolves to one number stated once, on `_guard`'s docstring.

**3. Site collapses:**

- `LocalOriginMixin` (`_mixins.py:477`): delete `__enter__` and `__exit__`
  entirely; move the body to `_enter_pre` — e2e branch registers the capture
  key (no teardown); otherwise start the `SSL_CERT_FILE` patch, the local
  origin context, and the `egress_hatch_env(private=True)` patch, each
  followed immediately by `self._guard(...)`. LIFO release preserves the
  order (hatches → origin → ssl). A failure between starts releases the
  earlier starts.
- New `FastOutboundBackoffMixin` in `tests/harness/egress.py`: one owner for
  the constant, the patch, and the comment.
  `FAST_BACKOFF_BASE_SECONDS = "0.01"`; `_enter_pre` starts
  `patch.dict(os.environ, {_BACKOFF_BASE_ENV: ...})` and registers
  `self._guard("fast_backoff", backoff.stop)`. The env-var name is imported
  from `src.core.security.egress.attempts` (`_BACKOFF_BASE_ENV`,
  `attempts.py:36`), not re-spelled — the mixin cannot misspell a name it
  never spells (precedent: the harness patches
  `egress.attempts.random.uniform`; `test_outbound_http.py:1874` imports the
  module directly). The docstring takes the accurate conditional wording
  from `order_approval_webhook.py:47-57` once; the stale copy at
  `protocol_webhook.py:65-68` dies with its code. Composition rule, stated
  in the docstring: only the two webhook envs compose this mixin; any env
  whose tests observe the seam's sleep (the delivery envs mocking
  `outbound_http.time.sleep` and grading magnitudes) must NOT.
- `OrderApprovalWebhookEnv`: delete `__enter__`/`__exit__` and the
  module-level `_FAST_BACKOFF_BASE_SECONDS` with its comment; class line
  becomes
  `class OrderApprovalWebhookEnv(FastOutboundBackoffMixin, LocalOriginMixin, IntegrationEnv)`.
- `ProtocolWebhookEnv`: same class-line change; delete
  `__enter__`/`__exit__`/constant. The `_service` reset survives as an
  `_enter_pre` that sets `self._service = None` and registers a cleanup
  restoring it to `None`.
- `MediaBuyDualEnv` (`media_buy_dual.py:64`): delete
  `__enter__`/`__exit__`/`_update_patchers`. Use the sibling precedent
  (`media_buy_create.py:465-469`):
  `EXTERNAL_PATCHES = {**MediaBuyCreateEnv.EXTERNAL_PATCHES, **_UPDATE_PATCHES}`
  and `_configure_mocks` calling `super()._configure_mocks()` then
  `self._configure_update_mocks()`. No hook needed; the base starts, guards,
  and configures the update patches. The swallow-all
  `except Exception: pass` teardown retires in favor of the base's error
  collection. (Verified: `_UPDATE_PATCHES` keys do not collide with the
  create set and none are async.)
- `CircuitBreakerEnv` (`delivery_circuit_breaker.py:97`): delete
  `__enter__`/`__exit__`; `_enter_post` attaches the log handler and
  registers `self._guard("log_capture", lambda: logger.removeHandler(...))`.
- `AdminAccountEnv` (`admin_accounts.py:110`): not a `BaseTestEnv`; keeps
  its own `__enter__` but wraps the body in
  `try/except BaseException: self.__exit__(None, None, None); raise` —
  its `__exit__` is verified None-safe.
- `EgressHatchMixin.set_egress_hatches` (`egress.py:76-78`): switch
  `self._patchers.append(patcher)` to
  `self._guard("egress_hatches", patcher.stop)`; drop the
  `_patchers: list` annotation. Mid-test registration keeps working.

**4. Follow-through:** the two existing assertions on the internal list shape
(`tests/harness/test_harness_base.py:91-105`, `len(env._patchers) == 2`)
update to the renamed list — a rename follow-through, not a weakening; the
behavior they grade is re-asserted.

Sequencing, each step landing green: (1) `_base.py` registry + hooks + moved
`try`; (2) migrate `LocalOriginMixin` and `EgressHatchMixin`; (3) add
`FastOutboundBackoffMixin` and collapse the two webhook envs; (4) collapse
`MediaBuyDualEnv` and `CircuitBreakerEnv`; (5) guard `AdminAccountEnv`;
(6) add the oracle tests and update the two renamed-list assertions.
Verification: `make quality`, then `tox -e integration`, then the standing
full-suite gate.

### The deletion list

- `_mixins.py`: `LocalOriginMixin.__enter__`, `LocalOriginMixin.__exit__`,
  its name-tuple `getattr` teardown loop (`:515-523`), and the "One real
  failure became 443" amplifier comment.
- `order_approval_webhook.py`: `__enter__` (`:78`), `__exit__` (`:89`
  region), module-level `_FAST_BACKOFF_BASE_SECONDS` and its ~10-line
  comment (`:48-57`).
- `protocol_webhook.py`: `__enter__` (`:108`), `__exit__` (`:122` region),
  the constant, and the stale comment block (`:65-68`) — the false "takes
  effect only once this call site has actually been migrated ... ~3s of real
  waiting today" claim dies with its file.
- `media_buy_dual.py`: `__enter__` (`:64`), `__exit__`, `_update_patchers`,
  and the swallow-all `except Exception: pass` teardown loop.
- `delivery_circuit_breaker.py`: `__enter__` (`:97`), `__exit__`.
- `_base.py`: the false coverage claim in the guard comment
  (`:1291-1299`) and the duplicated "350 further errors" measurement (one
  statement survives, on `_guard`).
- `egress.py`: the `_patchers: list` annotation on `EgressHatchMixin`.

### Grading

Seven new tests in `tests/harness/test_harness_base.py` (DB-free; the
`get_engine` + `ALL_FACTORIES` patching recipe at `:317` is the template),
each named with the mutation that reddens it:

1. `test_enter_post_failure_unwinds_everything` — reddens if the
   `except BaseException` clause or `_unwind_partial_enter()` call is
   deleted, or `_release_entered`'s loop body is gutted.
2. `test_enter_pre_partial_failure_releases_earlier_resources` — reddens if
   `_enter_pre()` moves above the `try`.
3. `test_local_origin_mixin_unwinds_on_base_failure` — asserts
   `SSL_CERT_FILE` and `ADCP_OUTBOUND_ALLOW_PRIVATE` are absent from
   `os.environ` after a failed enter and the origin context exited; the
   oracle for the leaked-open-hatch exposure. Reddens if any of the three
   `_guard` registrations reverts to a bare `.start()`.
4. `test_fast_backoff_mixin_unwinds_on_failed_enter` — asserts
   `ADCP_OUTBOUND_BACKOFF_BASE_SECONDS` is absent after a failed enter (the
   exact probe that fails at head). Reddens if the mixin's registration is
   dropped or either env regrows a hand-rolled patcher.
5. `test_admin_env_failed_enter_releases_client` — reddens if
   `AdminAccountEnv`'s try/except is deleted.
6. `test_fast_backoff_is_observed_at_the_seam` — with
   `attempts.random.uniform` pinned to 0, asserts
   `attempts._backoff_seconds(1) == 0.01` inside an entered mixin env. No
   wall clock; grades the whole chain mixin → seam. Reddens if the imported
   env-var name is replaced by a misspelled literal, the patch is dropped,
   or the seam stops reading the knob. Closes the silent-slowness residual
   without a timing assertion.
7. `test_harness_envs_define_no_enter_exit` (structural, AST) — scans
   `tests/harness/*.py` excluding `test_*.py`; `def __enter__` /
   `def __exit__` may appear only on `BaseTestEnv` (`_base.py`) and
   `AdminAccountEnv` (`admin_accounts.py`). A frozen role declaration, not a
   violations allowlist: every current violation is fixed in the same
   change, and the set can only shrink. A new env overriding `__enter__` by
   hand fails `make quality` before any leak exists.

Named honestly: "a hook acquired a resource and never registered it" has no
general oracle; tests 3 and 4 pin the known resource families individually,
and an AST rule pairing each `.start()` with a `_guard` call would be a
pattern DSL, rejected per the repo's library-not-framework stance on guards.

DRY ratchet: the change deletes four hand-rolled acquire/teardown copies and
adds zero; the duplication baseline can only improve; no guard allowlist
grows.

### Boundary

This lane owns every `__enter__`/`__exit__` in `tests/harness/` and the new
mixin, including the mixin's docstring — the single surviving home of the
fast-backoff comment. It must NOT: change any egress verdict or hatch
semantics (`egress_hatch_env` and the `ADCP_OUTBOUND_ALLOW_PRIVATE` surface
stay a single boolean — lane 3 owns the verdict); compose
`FastOutboundBackoffMixin` into any delivery env (the ~15 magnitude
assertions above); touch the prose-only header sites 1, 3, 4, and 5 that
lane 8 owns; or touch `ruff-egress.toml` or its test (lane 1).

---

## Lane 3: egress policy — supplement ranges outside the hatch

**Formula:** plan-lane-execute. **Closes finding:** 5.

### The root

The hatch is coarser than its use. `EgressPolicy.resolve_for_dial` guards the
six `_SUPPLEMENT_NETWORKS` ranges with
`if not allow_private and _blocked_address(...)`
(`src/core/security/egress/policy.py:323`). The supplement set exists
BECAUSE `adcp.signing.resolve_and_validate_host` does not classify those
ranges — so when `ADCP_OUTBOUND_ALLOW_PRIVATE=true` opens the hatch, the SDK
passes them and line 323 skips the only check that knows them: refused
becomes accepted, with no test asserting the verdict in either direction.
The repo already names this shape as a fault on the other verdict — the
`_is_rescuable_loopback` docstring (`policy.py:178-182`) rejects a flag that
"would also rescue every supplement range". Measured against every user of
the hatch in the tree (in-process suites dialing loopback fixtures; the e2e
compose stack dialing RFC 1918 bridge addresses), no user needs a supplement
range. The grading gap is the symptom; the fault is that the supplement set —
carried precisely because it has no other line of defence — is reachable by
the hatch at all. The design closes the hole rather than pinning it as
intended.

Corrections to the reviewer's account — load-bearing:

- The hatch is WIDER than reviewed: `allow_private=True` relaxes every SDK
  flag, so multicast, `240/4`, non-metadata link-local, and `0.0.0.0` open
  too (observed in the verified verdict table). That half is SDK behavior
  the seam delegates by design (CLAUDE.md pattern 9) and stays out of scope;
  the supplement set is the half this repo owns.
- The reviewer's hedge "the e2e bridge network may need exactly that" is
  refuted: Docker bridge networks allocate from RFC 1918 pools, which the
  SDK's `is_private` flag classifies and the hatch opens independently of
  the supplement check. The reviewer's alternative — pin
  accepted-under-the-hatch as intended — would grade a behavior no user
  needs and the module's own registration-side docstring names as the fault
  to avoid.

Registration is unaffected by construction: `check_registration` takes no
`allow_private` parameter; its column of the verdict table is fully graded
(`tests/integration/test_outbound_http.py:1233` covers all six supplement
rows; `test_webhook_url_ingest_refusal.py:265` pins CGNAT with the hatch env
set open).

### The change-set

**1. `src/core/security/egress/policy.py`.** Extract
`_in_supplement_range(ip)` from `_blocked_address` (`:134-154`) — the
docstring states why the split exists: the SDK re-checks the flag half
itself under `allow_private`, while the supplement half is the seam's own
and no posture relaxes it. `_blocked_address` calls the helper so the
predicate stays spelled once. Replace `:323-325` with an unconditional
supplement check ahead of the hatch-guarded one:

```python
ip_obj = ipaddress.ip_address(ip)
if _in_supplement_range(ip_obj):
    logger.warning("Outbound request refused by address policy: matched the supplement range set")
    raise OutboundRequestBlocked(field=field)
if not allow_private and _blocked_address(ip_obj):
    logger.warning("Outbound request refused by address policy: address is in a blocked range")
    raise OutboundRequestBlocked(field=field)
```

State the contract at the definitions: the `_SUPPLEMENT_NETWORKS` comment
block (`:35-43`) adds that the set sits outside the
`ADCP_OUTBOUND_ALLOW_PRIVATE` hatch — both verdicts refuse it under every
posture; the `resolve_for_dial` docstring (`:292-311`) states what
`allow_private` opens (the SDK's flag classes, for loopback and
compose-bridge test origins) and what it never opens (the supplement set and
the SDK's pre-hatch metadata check). `check_registration` needs no change —
its verdict is byte-identical.

Safety, verified: no existing test asserts the old behavior in either
direction; no production caller passes `allow_private` except from the env
flag (`outbound_http.py:725,755,849,910`); the change stays inside the
egress package, so the TID251 bans and the no-destination-rewrite guard are
untouched.

**2. `tests/integration/test_outbound_http.py`.** Add the hatch-open twin
beside `test_a_supplement_range_is_refused_at_dial` (`:1248`):
`test_a_supplement_range_stays_refused_with_the_private_hatch_open`,
parametrized over `_SUPPLEMENT_RANGE_URLS`, with
`set_flags(monkeypatch, private=True)` and `assert dial_refused(url)`.
`dial_refused` goes through `validate_url`, which refuses before any
connection — no socket in either the green or the red state. The docstring
mirrors `test_cloud_metadata_stays_refused_with_the_private_hatch_open`:
metadata immunity is the SDK's pre-hatch check, this immunity is the seam's.

**3. Completeness pin.** The verdict rows stay hand-stated — the file's own
design comment (`:1102-1107`) mandates it: a row derived from production
vanishes together with the CIDR a mutation deletes. Add the converse guard,
`test_the_supplement_oracle_table_covers_the_production_set_exactly`: import
`_SUPPLEMENT_NETWORKS`, map each `_SUPPLEMENT_RANGE_URLS` row to its IP, and
assert every production range has exactly one graded row and vice versa
(membership, not derivation — no verdict is computed from the production
set). Extend the section-12 mutation comment (`:1102-1117`) with the new
rows.

**4. Optional, recommended.** With the fix, a supplement address is a third
refusal cause immune to the hatch — gradeable over `e2e_rest`, where the
stack's posture is permanently open. Add `https://100.64.0.1` as an example
row to both hatch-open scenario outlines in
`tests/bdd/features/local-egress-ssrf-refusal.feature` (`:107-118`,
`:119-130`); the refusal fires before any connection, so no packet leaves
the stack. If taken, update the `docker-compose.e2e.yml:96-133` comment's
"can NEVER be graded in-network" sentence to except the supplement subset,
and the pin-test prose
(`test_architecture_no_outbound_insecure_hatch.py:158-160`) to name both
immunities.

### The deletion list

This lane deletes no file, constant, table, or allowlist entry — it is a
behavior-narrowing lane. The one removal is the `not allow_private and`
condition ahead of the supplement half of the dial check
(`policy.py:323`), replaced by the unconditional check above.

### Grading

| Mutation | Reddens |
|---|---|
| Revert the fix (restore `not allow_private and` before the supplement check) | `test_a_supplement_range_stays_refused_with_the_private_hatch_open`, all six rows |
| Make `_in_supplement_range` return `False` | same six rows, plus the hatch-closed dial rows (`:1248`) and registration rows (`:1233`) — the extraction feeds both verdicts, so one edit reddens all three surfaces |
| Delete any range from `_SUPPLEMENT_NETWORKS` | four tests: registration row, hatch-closed dial row, hatch-open row, completeness pin (confirmed possible: every representative has all six stdlib flags `False` on Python 3.12, so nothing else refuses it) |
| Add a range without a test row | completeness pin (`covered == _SUPPLEMENT_NETWORKS` fails) |
| Delete a row from `_SUPPLEMENT_RANGE_URLS` | completeness pin (count assertion fails) |
| Skip the supplement check for IPv6 only | the `orchidv2` row (`2001:20::1`) in the hatch-open test |
| Thread `allow_private` into `check_registration` | `test_webhook_url_ingest_refusal.py:265` plus `test_the_loopback_allowance_rescues_nothing_but_loopback` (`:1373`) |

Deliberately not graded (SDK-owned, delegated per CLAUDE.md pattern 9): the
exact flag set `allow_private=True` relaxes. Metadata immunity under the
open hatch is already graded at `test_outbound_http.py:338`.

### Boundary

This lane touches `policy.py`, `test_outbound_http.py`, and (optionally) the
BDD feature, compose comment, and pin-test prose. It must NOT: add a new
knob or change the single-boolean surface of `egress_hatch_env` /
`set_flags`; touch `check_registration`; touch harness lifecycle code
(lane 2); or touch the lint gate (lane 1). It composes with lane 2: lane 2
stops a failed enter from leaking the hatch open, this lane narrows what an
open hatch opens; they land together.

---

## Lane 4: two vacuous Then steps

**Formula:** task-fix. **Closes:** the severity core of finding 9.

### The root

Two Then steps in `tests/bdd/steps/domain/uc011_accounts.py` read the payload
leniently and guard it with `if resp is not None:` with nothing after the
suite — when the dispatch errors, the step passes having graded nothing.
Corrections to the reviewer's framing, load-bearing: finding #9's real size
is these 2 vacuous steps, not 45 accessor swaps. None of the 45 swaps in
commit `20174533b` introduced vacuity — every swapped site either hand-guards
or hard-dereferences, so `None` still fails the test. Both vacuous sites
predate the PR: at merge-base `1d93e3721` they already read
`ctx.get("response")` behind an unguarded `if`. The swap's fault is
migrating the vacuity verbatim when the raising reader was one token away.
And 72 is the wrong denominator: 8 of the module's `payload_or_none` sites
are legitimate lenient reads (6 error-variant graders asserting `is None` at
`:1071, :1190, :1203, :1228, :1239, :2817-2818`; 2 branch selectors with
both paths graded at `:970` and `:2182`) that a blanket rename would break.

### The change-set

In `tests/bdd/steps/domain/uc011_accounts.py`:

1. `then_no_dry_run_include` (`:1797`) → `require_payload(ctx)`. Its
   error-variant twin `then_no_dry_run_field` (`:1218`) already grades the
   error path under its own step text, so this step's `None` case is a
   dispatch failure, not a variant.
2. `then_context_identical` (`:2222`) → mirror its sibling
   `then_context_matches` (`:2182`): grade the success path, and grade or
   `xfail` the error path explicitly. If a feature-file audit shows the step
   text binds only in success scenarios, `require_payload` is the simpler
   correct form. (The audit is the executor's one open decision in this
   lane.)
3. Add `require_payload` to the import at `:19` (which pulls only
   `error_envelope_or_none, payload_or_none` at head).

### The deletion list

The two unguarded `if resp is not None:` fall-through guards at `:1797` and
`:2222`. Nothing else — this lane fixes two steps and touches no other site.

### Grading

Vacuity is demonstrated empirically at head with zero edits: calling both
step functions directly with the ctx a Then sees after a raised dispatch
(`{"error": RuntimeError(...), "sent_context": {...}}`, no
`TransportResult`) — both PASS. `require_payload` on the same ctx raises
`AssertionError` naming the recorded error. That is the before/after in one
run. Reddening mutation for the fixed steps: make the context-echo dispatch
fail (or make `sync_accounts` return the error variant in a success
scenario) — at head "the context is identical to what was sent" stays
green; after the fix it fails.

### Boundary

Only the two steps named above. NOT the ~61 diagnostic-quality sites
(lane 9), NOT the guard (lane 5), NOT the 8 legitimate lenient sites, NOT
any other module's fall-through candidates (lane 5 triages those). This
lane lands before lane 5, so the generalized guard starts green on uc011's
two known violations.

---

## Lane 5: Then-step reachability guard

**Formula:** structural-guard. **Closes:** the enforcement half of
finding 9.

### The root

The reader-choice rule ("a step that genuinely REQUIRES a payload calls
`require_payload`") lives only in prose — docstrings and a commit message —
and prose does not grade, so a bulk edit weakened 45 graders and nothing
went red. The enforcement gap that matters is narrower than the prose rule:
a Then step that can RETURN without executing any assertion — an assertion
nested in an `if` with no `else` is the hole — passes vacuously on a failed
dispatch.

**Rejected design, recorded.** The bdd-grader-strength note prescribed a new
module, `test_architecture_bdd_payload_reader_choice.py`, with three AST
checks (inline dereference of `payload_or_none(...)`; a bound name never
tested against `None`; ungraded fall-through). Rejected by the epic: the
real defect is two vacuous steps, not 45 sites; ~61 of the flagged sites
already fail on `None`; and the first two checks encode a style preference
rather than a false green. The one check that catches the bug —
reachability of an assertion on every path — is a one-sentence
generalization of a guard the repo already owns, and this lane carries it
there instead.

### The change-set

Generalize `tests/unit/test_architecture_bdd_no_trivial_assertions.py`. At
head it checks that a Then step *contains* a meaningful assertion (compares
values, not just truthiness). Add one check: the step function must not be
able to *return without executing one* — a function body where every
assertion is nested inside a conditional whose other path reaches the
function's end unasserted is a violation.

Implementation guidance, carried from the note's reachability analysis:
compute reachability on the statement list that contains the `If`, recursing
into nested suites, so a following `assert`, `raise`, or `pytest.xfail` at
any depth on the fall-through path counts as covering it. The note's
prototype over-flagged nested guards (it missed an `assert` following a
nested `if`), so the refined rule must recurse before flagging, and the
cross-module candidate list below needs per-site triage with the refined
rule, not bulk conversion.

Sites the check is expected to redden at head, per the note's census
(triage each; fix true positives in the same change):

- `uc011_accounts.py:1797` and `:2222` — fixed by lane 4, which lands
  first.
- `uc019_query_media_buys.py:1547`, `uc002_nfr.py:100`,
  `uc004_delivery.py:1536, :2219, :3595`,
  `uc026_package_media_buy.py:2299`, `generic/then_error.py:217` —
  fall-through candidates; several are steps named "no error for X", whose
  whole claim dies silently when the payload is absent.

**No allowlist.** Per the ratchet rule, every true violation the check finds
is fixed in the same change.

### The deletion list

Nothing is deleted: this is a guard-generalization lane. It qualifies as a
lane that deletes nothing because its change is additive enforcement inside
an existing guard module — the violations it surfaces are fixed at their
sites (edits, not deletions of files or allowlist entries), and it ships
with no allowlist to shrink.

### Grading

- At head, the generalized check reports the census above; after the site
  fixes it reports zero.
- The check's own liveness, in the style of `test_ruff_egress_bans.py`'s
  self-proving rules: a self-test feeds the checker a scratch step
  containing an assertion nested in an `if` with no `else` and asserts the
  checker names it. Reintroducing a fall-through anywhere under
  `tests/bdd/steps/` reddens `make quality`.
- The existing contains-an-assertion check keeps its current coverage
  unchanged; the generalization only adds failures, never removes one.

### Boundary

Only `test_architecture_bdd_no_trivial_assertions.py` plus the step sites
its new check truly reddens (after false-positive triage). NOT the
accessor-choice rule (dropped as style), NOT lane 4's two steps (already
fixed when this lands), NOT the diagnostic conversions (lane 9), NOT a new
guard module.

---

## Lane 6: dead breaker verdict

**Formula:** structural-change. **Closes finding:** 10.

### The root

`drive_breaker_transition` (`tests/harness/_mixins.py:826`) returns a bool
that its only call site stores as `ctx["cb_can_attempt"]`
(`tests/bdd/steps/domain/uc004_delivery.py:1008`) — a key with zero readers
(grep is decisive: a dict-key read requires the literal). The adjacent
`ctx["circuit_result"]` (`:1010`) is likewise write-only. Two docstrings
contradict the code and each other: `_mixins.py:832-837` claims "one
consumer, `then_single_probe` ... still asserts on it" (false — that step
was rewritten to grade the probe on the endpoint), and
`uc004_delivery.py:1977` says `cb_can_attempt` is "a key no step in this
module writes" while `:1008` in the same module writes it. The breaker
scenarios still grade the transition through production reads —
`then_circuit_transition` (`:1955`) asserts `env.get_breaker_state()`, and
`then_single_probe` grades HALF_OPEN admission on the endpoint — so the
bool duplicates weakly what those Thens grade strongly. A reader for the
bool would re-add the exact pattern two docstrings already reject ("a
gate's internal opinion of itself"). The resolution is deletion, not a
consumer.

### The change-set

One commit:

1. `_mixins.py`: `drive_breaker_transition` → `-> None`; the body calls
   `can_attempt()` for its side effect and discards the result. Rewrite the
   docstring: drop the "ACKNOWLEDGED RESIDUE" paragraph, keep "observe the
   resulting state via `breaker_snapshot`".
2. `uc004_delivery.py:1008`: drop the assignment —
   `env.drive_breaker_transition(endpoint_key)` bare. KEEP the call: it
   drives OPEN → HALF_OPEN, which `then_circuit_transition` grades.
3. `uc004_delivery.py:1010`: drop the dead `ctx["circuit_result"]`
   assignment the same way, keeping the `env.call_send()` call — it has
   breaker side effects the scenario depends on.
4. The `:1977` docstring claim becomes true once the `:1008` write is gone;
   no edit there. Neither guard set changes: both
   (`test_architecture_bdd_wire_discipline.py:462`,
   `test_architecture_bdd_breaker_scenarios_graded_live.py:95`) pin the
   method NAME, which survives, and exact-match sets fail on removal, so
   leaving them untouched is verified by the guards themselves.

### The deletion list

- The `bool` return of `drive_breaker_transition` (signature becomes
  `-> None`).
- The "ACKNOWLEDGED RESIDUE" paragraph and the false one-consumer claim in
  the `_mixins.py:832-837` docstring.
- The `ctx["cb_can_attempt"]` assignment at `uc004_delivery.py:1008`.
- The `ctx["circuit_result"]` assignment at `uc004_delivery.py:1010`.

### Grading

- Deadness at head: grep shows zero readers of `ctx["cb_can_attempt"]`; the
  mutation "return `not can_attempt()`" reddens nothing — that IS the
  finding. The fix removes the mutant's surface entirely.
- Liveness of what remains (why deletion is safe): mutate production so
  `can_attempt()` never leaves OPEN → `then_circuit_transition('half-open')`
  fails on the state read; mutate HALF_OPEN to admit two probes →
  `then_single_probe` fails on `delivered == 1`. Both observations survive
  the deletion untouched, and
  `test_architecture_bdd_breaker_scenarios_graded_live` keeps them wired.
  (These mutations were reasoned from the step bodies and guard, not run.)
- No assertion goes missing: the only fact the bool could uniquely carry —
  "`can_attempt` said yes at the When's own call" — is graded transitively
  by the state Then and the probe Then, each strictly stronger.

### Boundary

Only `_mixins.py`'s `drive_breaker_transition` and the two assignment lines
in `uc004_delivery.py`. NOT the two guard sets (verified untouched by their
own exact-match construction), NOT any breaker Then step, NOT the optional
dead-ctx-key check (a follow-up, prototyped before adoption, not this lane).

---

## Lane 7: create-kwargs builders

**Formula:** structural-change. **Closes finding:** 4b.

### The root

Three forces, in order of weight. First, nothing reddens when you copy:
measured at head, pylint R0801 with the repo's settings
(`pyproject.toml:239-244`, `min-similarity-lines = 6`,
`ignore-signatures = true`) reports ZERO hits across the four files —
the drift itself breaks every contiguous run at 3-4 comparable lines, so
copy-then-drift (the harmful variant) slides under the tool built to catch
duplication, and `check_code_duplication.py` inherits the blindness.
Second, incomplete extraction: commit `cc76f6018` created the signed test
with its local `_create_kwargs`; the next commit `2c0da66ed` extracted
`minimal_create_kwargs` onto the env for the files it was adding and never
retired the seed. Third, discoverability: `MediaBuyCreateEnv` exposes no
kwargs builder, so the url_ingest author hand-rolled with a third date
spelling, while the HMAC sibling found the shared factory and documented
the choice.

Corrections to the reviewer's framing — load-bearing:

- "Two hand-rolled builders drifted from the canonical one" undersells the
  signed file: its copy is not a drifted descendant — it is the canonical
  builder's PARENT, left behind by the extraction one commit later. The fix
  is deletion, not re-alignment.
- The implied single canonical builder is actually two, paired by env:
  `create_test_media_buy_request_dict` (`tests/helpers/adcp_factories.py:594`)
  for `MediaBuyCreateEnv` files, `minimal_create_kwargs`
  (`tests/harness/webhook_registration.py:215`) for
  `MediaBuyPushRegistrationEnv` files. Collapsing both files onto either
  one alone trades drift for a mismatched env.
- The disease predates the PR: `main` carries six more local
  `_create_kwargs` builders and five sibling `pricing_option_id` spellings —
  all follow-up scope, listed under Boundary.

### The change-set

**Change A — the signed test collapses onto the env method it holds.**
`tests/integration/test_webhook_registration_reaches_delivery_signed.py`:
delete `_pricing_option_id` (`:91-103`; sole caller is `_create_kwargs`, and
the env method inlines the identical derivation) and `_create_kwargs`
(`:105-119`); `:130` and `:342` become
`kwargs = env.minimal_create_kwargs(product, pricing_option)`; remove the
then-unused `import uuid` and `from datetime import UTC, datetime,
timedelta` (`:40-41`). The one divergence adjudicated explicitly: the
`fo99-2-` idempotency prefix is dropped in favor of the env's `fo99-` —
uniqueness (the load-bearing property, per the env docstring) comes from
`uuid4().hex`, and nothing reads the prefix back. If the lane tag must be
kept, `**overrides` carries it without a copy, but the default is to drop
it.

**Change B — url_ingest routes through the shared factory, like its
sibling.** `tests/integration/test_webhook_url_ingest_refusal.py`: replace
the `_create_kwargs` body (`:223-235`) with a delegation to
`create_test_media_buy_request_dict(product_ids=[product.product_id],
pricing_option_id="cpm_usd_fixed", total_budget=5000.0,
brand={"domain": "webhook-ingest.example.com"},
po_number=f"WEBHOOK-INGEST-{uuid.uuid4().hex[:8]}")`, with a docstring
saying everything except the webhook config under test comes from the
shared builder so the refusal is the only possible error. Add the factory
import at `:78`. `uuid` stays (used at `:417`); `datetime`/`UTC`/`timedelta`
stay (fixture at `:347-348`). Deliberate divergences (`brand.domain`,
`po_number` — the file's labels) are carried as explicit kwargs; accidental
ones (the `Z`-spelled 30-to-60-day window, the missing `idempotency_key`)
die into factory defaults — behavior-neutral, because all three uses
(`:260`, `:287`, `:315`) grade an ingest refusal at the registration gate
and the field-pinning assertion catches any kwargs that stop being
"otherwise valid".

**Change C (recommended, severable) — the env method stops being a fourth
spelling.** `minimal_create_kwargs` (`webhook_registration.py:215`)
delegates to `create_test_media_buy_request_dict`, passing `start_time` and
`idempotency_key` explicitly so the delegation is byte-for-byte
behavior-preserving for the three files dispatching through it. Layering is
clean (`tests/harness/_mixins.py:38` already imports from `tests.helpers`).
The method STAYS on the env — its job, translating this env's seeded ORM
objects into factory kwargs, is env knowledge, and the env is where the two
sibling files found it. Changes A and B close the finding without C.

### The deletion list

- `test_webhook_registration_reaches_delivery_signed.py`:
  `_pricing_option_id` (`:91-103`), `_create_kwargs` (`:105-119`),
  `import uuid` and `from datetime import UTC, datetime, timedelta`
  (`:40-41`), and the `fo99-2-` lane prefix.
- `test_webhook_url_ingest_refusal.py`: the hand-rolled `_create_kwargs`
  body (`:223-235`), including its third date spelling
  (`strftime("%Y-%m-%dT%H:%M:%SZ")`, `now+30d`/`now+60d`) and its
  accidental `idempotency_key` omission.
- With change C: the hand-spelled dict body of `minimal_create_kwargs`
  (replaced by factory delegation; signature, docstring, and behavior
  unchanged).

### Grading

Non-vacuity of the collapse — each file carries an assertion that fails
loudly if the swapped kwargs stop producing the dispatch it grades:

- Signed test: `_assert_delivered_signed` (`:82-88`) requires
  `env.delivery_attempts == 1` and
  `assert_signature_verifies_over_wire_body(env.last_delivery,
  STRONG_SECRET)`; a create failing on the swapped kwargs produces zero
  deliveries and a named failure. The whitespace case keeps its own two
  oracles (`refusal.value.field == "push_notification_config.url"`,
  `env.persisted_config_rows() == []`, `:352-364`). The swapped kwargs are
  dispatch-proven: `row_identity:107` and `both_seats:244` already create
  real buys with `env.minimal_create_kwargs` against the same env and
  seeding chain.
- url_ingest: `_assert_refused_at_ingest(result, _PNC_FIELD, ...,
  code=_REGISTRATION_GATE_CODE)` pins `VALIDATION_ERROR` / `correctable` /
  the exact `field` on both envelope layers, plus
  `_assert_no_push_config_persisted` — "otherwise valid" is asserted, not
  assumed. The factory route is dispatch-proven by the HMAC sibling
  (`test_webhook_hmac_credentials_ingest_refusal.py:133`) on the same env.

Measured ratchet facts, carried: R0801 reports zero hits on these files at
head (the blocks were never counted), so `.duplication-baseline`
(`src 31 / tests 71`) neither blocks the defect nor drops when it is fixed;
the fix must not grow it (`make quality` confirms). What stops the fourth
copy: after A-C, every create-kwargs producer in the webhook suite routes
through one of two documented builders and the discoverable env method
delegates to the factory — the next author's path of least resistance is
the correct one. A structural guard flagging dict-literal builders is
recorded as a follow-up (needs a 6-entry shrink-only allowlist, so not this
PR). Lowering `min-similarity-lines` is rejected: it re-fires R0801 across
the tree and grows the baseline.

Verification:
`scripts/run-test.sh tests/integration/test_webhook_url_ingest_refusal.py
tests/integration/test_webhook_registration_reaches_delivery_signed.py
tests/integration/test_webhook_registration_row_identity_and_legacy_stash.py
tests/integration/test_webhook_refusal_reaches_both_seats.py -x`, then
`make quality`. The last two files ride along because change C touches
their builder.

### Boundary

Only the two test files plus (change C) `webhook_registration.py`. NOT the
six pre-existing local builders on `main`
(`test_idempotency_wire_matrix.py:35`, `test_idempotency_race.py:464`,
`test_idempotency_rate_limit.py:189`,
`test_media_buy_revision_producer_agreement.py:95`,
`test_create_media_buy_status_wire.py:51`,
`test_create_media_buy_pending_approval_wire.py:38`), NOT the five sibling
`pricing_option_id` spellings, NOT a new AST guard — all filed follow-ups.

---

## Lane 8: prose drift

**Formula:** task-single. **Closes finding:** 11 (its prose half; the mixin
half is lane 2's).

### The root

The harness prose dates itself against a finished migration. Ground truth,
traced at head: `ProtocolWebhookService`, `_send_approval_webhook`, and
`deliver_webhook_with_retry` all deliver exclusively through
`webhook_egress` → `outbound_http`; zero `asyncio.sleep`, zero
`2**attempt`, zero raw clients remain in the services. The env knob the
comments hedge about is live: `attempts.py:36` defines `_BACKOFF_BASE_ENV`
and `:110` reads it at call time, so the harness `patch.dict` takes effect —
the opposite of what `protocol_webhook.py:65-68` tells a reader. Every
"today" in these comments describes the pre-PR world; every "after the
migration" describes the merged head. Nothing executable referenced the old
transport (the envs patch almost nothing; the transports are graded by real
sockets), so nothing could fail when it disappeared — the prose was the
only unversioned copy of that knowledge, and the fix is to stop making
claims a test cannot see. This is a documentation fix; the migration is
complete and no follow-up migration issue is needed.

Correction carried: the true sibling count is 5 stale sites in 4 files —
the reviewer named 3 in 2, missing `delivery_webhook.py:9-11` and the
`LocalOriginMixin` docstring at `_mixins.py:428-432`.

**Disagreement between notes, resolved by the epic routing:** the
prose-drift note's Part B (a `FastBackoffMixin` in `_mixins.py` with its own
`__enter__`/`__exit__`) is superseded by lane 2's `FastOutboundBackoffMixin`
in `egress.py` built on the `_enter_pre` hook. Lane 8 carries no mixin work
and no lifecycle code. Site 2 of the stale-prose census
(`protocol_webhook.py:65-68`) dies with lane 2's code deletion; the
corrected conditional wording survives once, on the mixin docstring lane 2
writes.

### The change-set

Rewrite four sites to state what the env grades, not when:

- Site 1, `tests/harness/protocol_webhook.py:6-9` (and site 3,
  `tests/harness/order_approval_webhook.py:5-8`, identically with `send`):
  "Mocked: nothing. There is no ``EXTERNAL_PATCHES`` entry on purpose — the
  whole point of this env is that the transport is not substituted: the
  assertions grade ``src.core.security.outbound_http.asend`` putting real
  bytes on a real socket, indifferent to how the seam is implemented."
- Site 4, `tests/harness/delivery_webhook.py:9-11`: "Nothing about the
  outbound transport is patched. That is the point: the tests grade the
  bytes ``src.core.security.outbound_http.send`` puts on the socket, not
  which client library puts them there."
- Site 5, `tests/harness/_mixins.py:428-432`: keep the design-history
  rationale, shifted to past tense so it reads as stable history: "An
  origin that actually serves HTTP is neutral to that choice: it answered
  ``requests.post`` before the migration and answers
  ``outbound_http.send`` now, and the assertions — how many requests
  arrived, with which headers, carrying which bytes — mean the same thing
  under both. That is why this landed before the migration rather than
  with it."

Adjacent but NOT stale, inspected and left as is:
`order_approval_webhook.py:53-56` (conditional phrasing, true as written;
dissolves under lane 2 anyway), `src/services/protocol_webhook_service.py:231`
and `src/core/webhook_delivery.py:139` (past-tense history, correctly
dated), and the other harness "today"s (`client.py:7`, `signals.py:9`,
`transport.py:243`, `webhook_registration.py`, `_mixins.py:837`,
`protocol_webhook.py:132`) — they date themselves against other facts and
are out of scope for #11.

### The deletion list

The four stale claims themselves: "assertions grade
`requests.Session.post` today and `...asend` after the migration" (site 1);
"assertions grade `httpx.Client` today and `...send` after the migration"
(site 3); "the same tests grade `requests.post` today and `...send` after
the migration" (site 4); "it answers `requests.post` today and `send()`
tomorrow ... this lands before the migration and not with it" (site 5,
reworded to past tense rather than removed). Site 2's stale block is
deleted by lane 2, not this lane. No file, constant, or allowlist entry is
deleted — this is a prose lane, and that is the whole of its case.

### Grading

Prose has no direct test; the claims the new wording makes are backed by
named executable gates, and that is the grading standard here:

- M1 (migration regression): reintroduce `httpx.Client(...).post` in
  `order_approval_service.py` → TID251 fires in `make quality-ci`, and
  `tests/unit/test_order_approval_service.py:215` (already repointed to the
  seam) fails. The timeless "assertions grade the seam" wording is backed
  by a gate, not by phrasing.
- The env-knob claim ("the seam reads the knob at call time") is graded by
  `tests/integration/test_outbound_http.py:200` (sets 0.001 and grades
  magnitudes) and the malformed-value WARN case at `:586-604`; the
  misspelling direction is closed structurally by lane 2's imported
  `_BACKOFF_BASE_ENV` and its seam-observation test.
- The no-dead-patch check was performed directly: every patch these envs
  hold intercepts something live at head (knob read at
  `attempts.py:110`; `sleep` executed at `outbound_http.py:877`).

### Boundary

Prose only, four sites, all under `tests/harness/`. NOT site 2 (lane 2
deletes it with its code), NOT any `__enter__`/`__exit__` or mixin code
(lane 2), NOT the out-of-scope "today"s listed above, NOT any production
file, and no follow-up migration issue is filed.

---

## Lane 9: diagnostic accessor conversions

**Formula:** task-single. **Closes:** the residue of finding 9.

### The root

The per-module accessor swap in commit `20174533b` left ~61 sites in
`uc011_accounts.py` — and the whole of `uc019_query_media_buys.py` (0
raising / 9 lenient) — reading the payload through `payload_or_none` where
the function's own logic requires a payload. These sites are NOT vacuous:
22 hand-guard with `assert resp is not None` (re-implementing
`require_payload` with a weaker message — a DRY violation), and ~39
dereference unguarded, failing as an anonymous
`AttributeError: 'NoneType' object has no attribute 'accounts'` with no
hint that the dispatch errored. The same commit applied the split correctly
per-site everywhere else (uc002 15/5, uc004 43/9, uc006 47/18) and
uniformly wrongly in uc011 and uc019 — the signature of a mechanical
per-module substitution. The rule: a `payload_or_none(ctx)` call is
justified only when the caller tests the result against `None`; every other
reader takes `require_payload(ctx)`, and an inline dereference IS a
requirement.

### The change-set

One mechanical commit in `tests/bdd/steps/domain/uc011_accounts.py`, no
behavior change to any green test:

1. Convert the ~61 diagnostic-quality lines to `require_payload(ctx)`: the
   22 hand-rolled `assert resp is not None, "Expected a response"` guards
   drop their assert (`require_payload` subsumes it with a message naming
   the recorded error); the ~25 unguarded assignment lines convert
   directly; the 14 inline `payload_or_none(ctx).accounts[0]` lines become
   `ctx.get("last_account") or require_payload(ctx).accounts[0]`.
2. Keep `payload_or_none` for the 8 legitimate sites: the 6 error-variant
   graders (`:1071, :1190, :1203, :1228, :1239, :2817-2818`, asserting
   `is None`) and the 2 both-paths-graded branch selectors (`:970`,
   `:2182`).
3. Apply the same per-site triage to the cross-module no-`None`-test
   sites: `uc019_query_media_buys.py:2235` and
   `uc006_sync_creatives.py:1943`, plus uc019's remaining wholesale-swapped
   readers.

### The deletion list

The 22 hand-rolled `assert resp is not None` guard lines in
`uc011_accounts.py` (subsumed by `require_payload`). No file, constant,
table, or allowlist entry is deleted beyond those lines.

### Grading

The honest statement, carried from the note: no new red appears, because
these sites already fail on `None` — the conversion changes the failure's
face, not its existence. The demonstrating mutation: make the dispatch
error → at head an anonymous `AttributeError` from `NoneType`; after, an
`AssertionError` naming the recorded error ("no TransportResult in ctx
because the dispatch RAISED: ... assert on the error instead"). The DRY
gain at the 22 hand-guarded sites is graded by the duplication baseline: 22
copies of the same guard collapse into the helper, and the baseline's
auto-lower pockets any decrease.

### Boundary

NOT the two vacuous steps (lane 4), NOT the fall-through sites (lane 5
triages those with the refined reachability rule), NOT the 8 legitimate
lenient sites, NOT any guard file. This lane is diagnostic quality and DRY
only; the guard that would police the accessor choice was rejected (see
lane 5), so these conversions are enforced by review, not by a test.

---

## Alterations

None recorded. A change to any lane's scope after this document is frozen
must be appended here as a dated entry; the entry wins over the earlier
text it amends.
