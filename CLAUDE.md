# Prebid Sales Agent development guide

## 🤖 For Claude (AI assistant)

This guide surfaces the repository-specific rules for the Prebid Sales Agent codebase (maintained under Prebid.org). The 9 critical patterns and the structural guards that enforce them are non-negotiable; the § Documentation list at the end says where the depth lives.

**Never push directly to main.** Commits and PR titles use Conventional Commits prefixes — `feat` / `fix` / `docs` / `refactor` / `perf` / `chore` — enforced by `.github/workflows/pr-title-check.yml`; release-please builds the changelog from them, so an unprefixed commit ships undocumented.

### Common task patterns
- **Adding a new AdCP tool**: Extend library schema → Add `_impl()` function → Add MCP wrapper → Add A2A raw function → Add tests
- **Fixing a route issue**: Check for conflicts with `grep -r "@.*route.*your/path"` → Use `url_for()` in Python, `scriptRoot` in JavaScript
- **Modifying schemas**: Verify against AdCP spec → Update Pydantic model → Run `pytest tests/unit/test_adcp_contract.py`
- **Database changes**: Reach the data through a repository inside a Unit of Work → Use `JSONType` for JSON columns → Create migration with `alembic revision`
- **Any feature or bug fix**: TDD — the failing test comes first, and every change is gated by `make quality` (full cycles in `.claude/rules/workflows/tdd-workflow.md` and `bug-reporting.md`)
- **Refactorings**: additionally run `tox -e integration` and verify imports with `uv run python -c "from module import thing"` — pre-commit hooks can't catch import errors

### Key files to know
- `src/core/main.py` — MCP server and tool registration
- `src/core/tools/` — tool `_impl()` business logic, MCP wrappers, and A2A raw functions (package)
- `src/core/schemas/` — Pydantic models, AdCP-compliant (package)
- `src/adapters/base.py` — adapter interface
- `src/adapters/gam/` — GAM implementation
- `tests/unit/test_adcp_contract.py` — schema compliance tests

### DRY (Don't Repeat Yourself) — a non-negotiable invariant

**DRY is a correctness requirement, equivalent to type safety or test integrity — not "premature optimization," and not "refactoring beyond what was asked."**

- If you write a block of logic that is structurally similar to an existing block (same pattern, different variables), you **MUST** extract a shared helper function
- If you are asked to refactor duplicated code, that is a **bug fix**, not an "improvement"
- **NEVER** cite "avoid over-engineering" or "keep it simple" to justify leaving duplicated logic in place
- Duplicated code is a defect. It means the next person who fixes a bug in one copy misses the other copy. This is not theoretical — it has caused real bugs in this codebase
- **Enforced by:** `check_code_duplication.py` in `make quality` (pylint R0801, ratcheting baseline in `.duplication-baseline`)

**What DRY is NOT:**
- It is not an excuse to create deep abstraction hierarchies for one-time code
- It is not about collapsing two genuinely different operations that happen to look similar today
- It applies when the same **logical operation** is repeated with only parameter substitution
- A worked example of extracting the shared pattern: [patterns-reference.md §8](docs/development/patterns-reference.md)

### Structural guards (automated architecture enforcement)
AST-scanning tests enforce architecture invariants on every `make quality` run. New violations fail the build immediately.

**The following table is a representative subset, not the full set.** There are over 70 guard tests (73 `tests/unit/test_architecture_*.py`, plus a handful of boundary guards like `test_transport_agnostic_impl.py` and `test_impl_resolved_identity.py`); for the complete list, run `ls tests/unit/test_architecture_*.py`. See [docs/development/structural-guards.md](docs/development/structural-guards.md) for design rationale (its written inventory covers only a subset).

| Guard | Enforces | Test file |
|-------|----------|-----------|
| Schema inheritance | Redeclarations are inherited unless changed or weakened | `test_architecture_schema_inheritance.py` |
| No ToolError in _impl | `_impl` raises AdCPError, never ToolError | `test_no_toolerror_in_impl.py` |
| Transport-agnostic _impl | `_impl` has zero transport imports | `test_transport_agnostic_impl.py` |
| ResolvedIdentity in _impl | `_impl` accepts ResolvedIdentity, not Context | `test_impl_resolved_identity.py` |
| Boundary completeness | MCP/A2A wrappers pass all _impl parameters | `test_architecture_boundary_completeness.py` |
| Query type safety | DB queries use types matching column definitions | `test_architecture_query_type_safety.py` |
| No model_dump in _impl | `_impl` returns model objects, never calls `.model_dump()` | `test_architecture_no_model_dump_in_impl.py` |
| No direct DB access | No `get_db_session()` or `session.add()` anywhere outside repositories/UoW/infrastructure | `test_architecture_repository_pattern.py` |
| Migration completeness | Every migration has non-empty `upgrade()` and `downgrade()` | `test_architecture_migration_completeness.py` |
| No raw MediaPackage select | All MediaPackage access goes through repository, not raw `select()` | `test_architecture_no_raw_media_package_select.py` |
| No import-time filesystem I/O | `src/` and `scripts/` modules touch no files while being imported | `test_architecture_no_import_time_fs_io.py` |
| No raw select outside repos | All ORM model queries go through repositories, not raw `select()` | `test_architecture_no_raw_select.py` |
| No raw egress | All outbound HTTP goes through `src/core/security/outbound_http.py`; the gateway modules bind their imports privately so re-export is an ImportError | `ruff-egress.toml` (TID251 over `src/` + `scripts/`, `--ignore-noqa`, in `make quality-ci`) + `test_ruff_egress_bans.py` |
| No destination rewrite | Nothing under `src/` rebuilds a URL or swaps its netloc/scheme ahead of the gateway | `test_architecture_no_destination_rewrite.py` |
| BDD no-op Then steps | Then steps must assert, not delegate to `_pending()`-like no-ops | `test_architecture_bdd_no_pass_steps.py` |
| BDD assertion reachability | A Then must not be able to RETURN without executing a meaningful assertion — presence is not enough | `test_architecture_bdd_no_trivial_assertions.py` |
| BDD no dict registry | Given steps must use factories, not raw dicts | `test_architecture_bdd_no_dict_registry.py` |
| BDD no duplicate steps | No 3+ step functions with identical bodies | `test_architecture_bdd_no_duplicate_steps.py` |
| BDD no silent env | No `ctx.get("env")` or `hasattr(env, ...)` in step functions | `test_architecture_bdd_no_silent_env.py` |
| Code duplication (DRY) | Duplicate block count in src/ and tests/ cannot increase | `check_code_duplication.py` (make quality) |
| Workflow tenant isolation | WorkflowRepository queries join DBContext for tenant scoping | `test_architecture_workflow_tenant_isolation.py` |
| No split mock assertions | Tests use `assert_called_once_with()`, not `assert_called_once()` + `call_args` | `test_architecture_weak_mock_assertions.py` |
| Single migration head | Alembic migration graph has exactly one head | `test_architecture_single_migration_head.py` |
| Pre-commit no additional_deps | No `additional_dependencies` in `.pre-commit-config.yaml` (ADR-001) | `test_architecture_pre_commit_no_additional_deps.py` |
| Pre-commit hook count | Commit-stage hooks stay within D27 ceiling (≤12) | `test_architecture_pre_commit_hook_count.py` |
| No tenant.config access | Per-field tenant columns, not legacy `tenant.config` | `test_architecture_no_tenant_config.py` |
| JSONType columns | JSON DB columns use `JSONType`, not plain `JSON` | `test_architecture_jsontype_columns.py` |
| No defensive RootModel | No `hasattr(x, "root")` without `# noqa: rootmodel` | `test_architecture_no_defensive_rootmodel.py` |
| Import usage in src/ | Classes/functions used in `src/` must be imported | `test_architecture_import_usage.py` |

**Rules for guards:**
- Allowlists can only shrink — never add new violations, fix them instead
- Every allowlisted violation has a `# FIXME(#<gh-issue>)` comment at the source location — reference a GitHub issue/PR number, never a local beads id (beads ids don't resolve for outside contributors)
- When you fix a violation, remove it from the allowlist (the stale-entry test reminds you)

---

## AdCP spec version

This project targets AdCP spec **3.1.1** via the `adcp==6.6.0` Python SDK. See
[docs/adcp-spec-version.md](docs/adcp-spec-version.md) for the version mapping
and bump procedure. The CI guard at `tests/unit/test_adcp_spec_version.py`
fails on pin drift.

### Spec-grounding gate (MANDATORY before implementing protocol behavior)

**Any change to AdCP/protocol BEHAVIOR** — a tool's request/response contract, error emission, idempotency, governance, or capabilities — **must cite, before code is written, the authoritative spec section + version that mandates it, plus the conformance storyboard step that grades it** (or note "ungraded"). Record the citation in the PR description and/or the planning note.

- **Which version is authoritative:** the version the repo currently PINS — *unless* there is active work to comply with a different target version (a bump/migration in flight), in which case that TARGET version is the pin. Confirm which applies first.
- **Where the spec lives** (`github.com/adcontextprotocol/adcp`): the written spec at `dist/docs/<version>/building/implementation/*.mdx`; the graded, executable contract at `dist/compliance/<version>/*.yaml`. The installed `adcp` SDK — codes, types, even reference implementations such as `adcp.server.idempotency` — is a CROSS-CHECK, **not** the authority; it can diverge from the spec.
- **Why:** grounding protocol behavior in downstream artifacts (an internal contract item, or the mere existence of an SDK error code) instead of the spec text + storyboard produces features built inverse to the spec. The spec is the contract; everything else is derived.
- **Enforcement:** reviewers reject protocol-behavior changes that don't cite the spec; this complements the pin-drift guard above. Background: [docs/adcp-spec-version.md](docs/adcp-spec-version.md).

---

## 🚨 Critical architecture patterns

### 1. AdCP schema: extend library schemas
**MANDATORY**: Use `adcp` library schemas via inheritance, never duplicate.

```python
from adcp.types import Product as LibraryProduct  # Library* alias convention

class Product(LibraryProduct):
    """Extends library Product with internal-only fields."""
    implementation_config: dict[str, Any] | None = Field(default=None, exclude=True)
```

**Rules:**
- Import library types with `Library*` alias: `from adcp.types import X as LibraryX`
- Extend with inheritance — don't copy fields from the parent class
- Only redeclare parent fields when needed for nested serialization (Pattern #4)
- Mark internal-only fields with `exclude=True`
- Run `pytest tests/unit/test_adcp_contract.py` before commit
- **Enforced by:** `tests/unit/test_pydantic_schema_alignment.py` — declared fields and
  model_dump survival graded against the PINNED SCHEMA — and by
  `tests/unit/test_architecture_schema_inheritance.py`, which grades redeclarations
  against the library parent.
- The inheritance guard's REDEFINITION rule decides membership by walking the live
  MRO and testing `__module__`, so it never consults how an import is written and has
  no import form to miss. The companion `test_all_library_types_have_local_subclass`
  is alias-keyed, and is the one place where an import written in an unexpected form
  goes unexamined.
- A redeclaration needs an allowlist row unless it is **neither changed nor weakened**:
  same annotation (or a subclass), nullability not added, `is_required()` not relaxed,
  metadata a superset, no default introduced. A redeclaration that keeps the parent's
  type but is *weaker* — dropping a `Ge` or a `MinLen`, going required→optional — needs
  a row NAMING the weakened axis. Do not widen the admission rule to make it pass: a
  hand-written row names itself and can be audited, whereas a derived rule that admits a
  widening is invisible and permanent.

### 2. Flask: prevent route conflicts
**Pre-commit hook detects duplicate routes** — run it manually: `uv run python .pre-commit-hooks/check_route_conflicts.py`

When adding routes: search existing first (`grep -r "@.*route.*your/path"`), and deprecate properly with early return, not comments.

### 3. Database: repository pattern + ORM-first
The database is PostgreSQL, in every environment including tests.

**ORM-first access (MANDATORY):**
- All DB reads and writes go through SQLAlchemy ORM models via repository classes
- Never construct ORM models with raw kwargs scattered in `_impl` functions — use model factory methods or repository `create_from_*()` methods
- Never pass `json.dumps()` to `JSONType` columns — the column type handles serialization
- Use SQLAlchemy relationships and cascading — they exist to manage parent/child persistence atomically
- Use `JSONType` for all JSON columns (not plain `JSON`)
- Inside a repository, use SQLAlchemy 2.0 patterns: `select()` + `scalars()`, never `query()`
- Outside a repository, `select()` on an ORM model is banned. It bypasses tenant scoping and the business rules the repository owns
- Cast IDs at the boundary: JSON gives you strings, but Integer primary-key columns need `int` values. Write `int(x)` before passing to `.in_()` or `filter_by()`
- All tests require PostgreSQL: `./run_all_tests.sh` runs Docker + tox (JSON reports in `test-results/`)
- **Exception:** Bulk imports and complex reporting queries may use Core SQL/raw SQL for performance. Regular CRUD operations are never an exception.
- **Enforced by:** `test_architecture_query_type_safety.py`, `test_architecture_repository_pattern.py`, `test_architecture_no_raw_select.py`

**Unit of Work:**
```python
# The UoW owns the session: it opens one on entry, commits on a clean exit,
# and rolls back if the block raises. Repositories hang off it.
with MediaBuyUoW(identity.tenant_id) as uow:
    media_buy = uow.media_buys.get_by_id(req.media_buy_id)
```

`BaseUoW` and the per-domain classes live in `src/core/database/repositories/uow.py`. A UoW
is how an `_impl` gets a repository — it is the only sanctioned place a session is created,
which is what keeps `get_db_session()` out of business logic.

`uow.session` raises a `DeprecationWarning`. If a repository has no method for the data you
need, add one; do not reach past it to the raw session.

See [patterns-reference.md](docs/development/patterns-reference.md) §§1–2 for both patterns in full — canonical repository files, worked correct/wrong examples, and how to add a repository.

### 4. Pydantic: explicit nested serialization
Parent models must override `model_dump()` to serialize nested children:

```python
class GetCreativesResponse(AdCPBaseModel):
    creatives: list[Creative]

    def model_dump(self, **kwargs):
        result = super().model_dump(**kwargs)
        if "creatives" in result and self.creatives:
            result["creatives"] = [c.model_dump(**kwargs) for c in self.creatives]
        return result
```

**Why**: Pydantic doesn't auto-call custom `model_dump()` on nested models.

### 5. Transport boundary: layer separation
All tools have two layers with strict responsibilities: **transport wrappers** (MCP, A2A, REST) and **business logic** (`_impl` functions).

**Rules for `_impl` functions:**
- Accept `ResolvedIdentity`, never `Context`, `ToolContext`, or raw headers
- Raise `AdCPError` subclasses, never `ToolError` (that's transport-specific)
- Zero imports from `fastmcp`, `a2a`, `starlette`, or `fastapi`
- No auth extraction or tenant resolution — that's the wrapper's job

**Rules for transport wrappers:**
- Call `resolve_identity()` to create `ResolvedIdentity` before calling `_impl`
- Forward **every** `_impl` parameter — don't silently drop any
- Catch `AdCPError` and translate to transport-appropriate error format

**Enforced by:** `test_transport_agnostic_impl.py`, `test_impl_resolved_identity.py`, `test_no_toolerror_in_impl.py`, `test_architecture_boundary_completeness.py`

Worked wrapper/`_impl` examples: `.claude/rules/patterns/mcp-patterns.md` and [patterns-reference.md §6](docs/development/patterns-reference.md).

### 6. JavaScript: use request.script_root
**All JavaScript must support reverse-proxy deployments:**

```javascript
const scriptRoot = '{{ request.script_root }}' || '';  // for example, '/admin' or ''
const apiUrl = scriptRoot + '/api/endpoint';
fetch(apiUrl, { credentials: 'same-origin' });
```

Never hardcode `/api/endpoint` — it breaks behind an nginx prefix.

### 7. Schema validation: environment-based
- **Production**: `ENVIRONMENT=production` → `extra="ignore"` (forward compatible)
- **Development/CI**: Default → `extra="forbid"` (strict validation)

### 8. Test fixtures: factory-based, not inline
**MANDATORY for new integration tests:** Use `factory-boy` factories for test data, not inline `session.add()` boilerplate.

**Rules:**
- Shared fixtures (tenant, principal, products) defined once in `conftest.py` using factories
- Test-specific data uses factory overrides, not copy-pasted setup blocks
- Factories live in `tests/factories/` — ORM factories and Pydantic schema factories
- Never `session.add()` in test bodies — use factories or fixtures that use factories
- Never call `get_db_session()` in test bodies — test data setup belongs in factory fixtures
- **DO NOT match pre-existing broken patterns.** If the test file you're adding to already uses
  `get_db_session()` or `session.add()`, those are pre-existing debt in the allowlist. Your new
  code must use factories regardless. The structural guard (`test_architecture_repository_pattern.py`)
  catches new violations immediately at `make quality`. Pre-existing violations are allowlisted
  and tracked with FIXME comments — they shrink over time, never grow.

Worked correct/wrong examples: [patterns-reference.md §5](docs/development/patterns-reference.md) and `tests/CLAUDE.md` § Factory system.

### 9. Outbound HTTP: the application implements no SSRF protection

**Every outbound request goes through `src/core/security/outbound_http.py` (`send` / `asend`).**

Do not add URL validation, private-IP checks, metadata blocklists, resolve-then-check, or
redirect re-validation anywhere else. If you find yourself writing `ipaddress`,
`socket.gethostbyname`, or a hostname blocklist in `src/`, stop — that logic is owned elsewhere.

```python
from src.core.security.outbound_http import asend

result = await asend(url, json=payload)
```

`ruff-egress.toml`, run by `make quality-ci`, fails the build on a raw HTTP client or a
hand-written address check. A `# noqa` does not silence it.

- **The rule, what it refuses, and how to add a call:** [docs/security/outbound-egress.md](docs/security/outbound-egress.md)
- **What the `adcp` SDK owns and what this repo carries:** [docs/design/egress-sdk-boundary.md](docs/design/egress-sdk-boundary.md)

---

## Project overview

The Prebid Sales Agent is a Python application with the following components:
- **MCP Server**: FastMCP tools for AI agents (via nginx at `/mcp/`)
- **Admin UI**: Google OAuth secured interface (via nginx at `/admin/` or `/tenant/<name>`)
- **A2A Server**: python-a2a agent-to-agent communication (via nginx at `/a2a`)
- **Multi-Tenant**: Database-backed isolation with subdomain routing
- **PostgreSQL**: Production-ready with Docker deployment
- All services are accessed through the nginx proxy at **http://localhost:8000**

---

## Common operations

### Running locally
Migrations run automatically on container startup. The local-run walkthrough, access points, and
test login are in [docs/quickstart.md](docs/quickstart.md); MCP client usage and the
`uvx adcp ... list_tools` smoke test are in `.claude/rules/patterns/mcp-patterns.md`.

### Testing
Test orchestration uses **tox** (with tox-uv): `uv tool install tox --with tox-uv`.
The full command reference — quick checks, full suite, manual Docker lifecycle,
coverage, targeted runs — is `.claude/rules/patterns/testing-patterns.md`. The essentials:

```bash
make quality              # Format + lint + typecheck + unit tests (before every commit)
tox -e integration        # Real-PostgreSQL integration tests (after refactorings)
./run_all_tests.sh        # Full suite: Docker up → all suites via tox -p → Docker down
scripts/run-test.sh tests/integration/test_foo.py -x   # One test, iterating (starts agent-db Postgres)
```

Reports: `test-results/<ddmmyy_HHmm>/*.json` (last 10 runs kept). Coverage: `htmlcov/index.html`.
**Pre-commit hooks can't catch import errors** — you must run tests for refactorings!

### Database migrations
```bash
uv run python scripts/ops/migrate.py            # Run migrations locally
uv run alembic revision -m "description"        # Create migration

# In Docker (migrations run automatically, but can be run manually):
docker compose exec admin-ui python scripts/ops/migrate.py
```

**Never modify existing migrations after commit!**

### Tenant setup dependencies
```
Tenant → CurrencyLimit (USD required for budget validation)
      → PropertyTag ("all_inventory" required for property_tags references)
      → Products (require BOTH)
```

---

## Testing guidelines

Test organization (unit/integration/e2e/admin/bdd/ui suites and what each needs), database fixtures,
quality rules (max 10 mocks per file, roundtrip test for `apply_testing_hooks()`), entity markers, and the
infrastructure decision tree are in `.claude/rules/patterns/testing-patterns.md` — read it before writing
or running tests. Test authoring with the harness (environments, factories, wire assertions): `tests/CLAUDE.md`.

### Error verification
**New error-path tests must assert on the wire envelope, not reconstructed exceptions.**
The test harness reconstructs `AdCPError` from wire responses, but this reconstruction is lossy.
Use `assert_envelope_shape(result.wire_error_envelope, code, recovery=...)` as the primary authority.
See `tests/CLAUDE.md` § "Error Verification Policy" for the full policy and helpers.

### Minimal code discipline

You are a lazy senior developer. Lazy means efficient, not careless. The best code is the code never written.

Before writing any code, stop at the first rung that holds:

1. Does this need to be built at all? (YAGNI)
2. Does it already exist in this codebase? Reuse the helper, utility, or pattern that's already here — don't rewrite it.
3. Does the standard library already do this? Use it.
4. Does a built-in platform feature cover it? Use it.
5. Does an already-installed dependency solve it? Use it.
6. Can this be one line? Make it one line.

Only then: write the minimum code that works. The ladder runs after you understand the problem, not instead of it: read the task and the code it touches, trace the real flow end to end, then climb.

Bug fix = root cause, not symptom: a report names a symptom. Grep every caller of the function you touch and fix the shared function once — one guard there is a smaller diff than one per caller, and patching only the path the ticket names leaves a sibling caller still broken.

Follow these rules:

- No abstractions that weren't explicitly requested. Caveat: allow shared helpers and existing architecture abstractions.
- No new dependency if it can be avoided.
- No boilerplate nobody asked for.
- Deletion over addition. Boring over clever. Fewest files possible.
- Shortest working diff wins, but only once you understand the problem. The smallest change in the wrong place isn't lazy, it's a second bug.
- Question complex requests: "Do you actually need X, or does Y cover it?"
- Pick the edge-case-correct option when two stdlib approaches are the same size — lazy means less code, not the flimsier algorithm.
- Mark deliberate simplifications that cut a real corner with a known ceiling (global lock, O(n²) scan, naive heuristic): comment naming the ceiling and upgrade path.
- Not lazy about: understanding the problem (read it fully and trace the real flow before picking a rung — a small diff you don't understand is laziness dressed up as efficiency), input validation at trust boundaries, error handling that prevents data loss, security, accessibility, the calibration real hardware needs (the platform is never the spec ideal: a clock drifts, a sensor reads off), anything explicitly requested. Lazy code without its check is unfinished: non-trivial logic leaves ONE runnable check behind, the smallest thing that fails if the logic breaks (an assert-based demo/self-check or one small test file; fewer frameworks, fewer fixtures). Trivial one-liners need no test.

### Test integrity policy — ZERO TOLERANCE

**This is non-negotiable. Every rule below is a HARD STOP.**

1. **NEVER skip, ignore, deselect, or exclude failing tests.** Do not use `--ignore`, `-k "not test_name"`, `--deselect`, `pytest.mark.skip`, or `pytest.mark.xfail` to work around failures.
2. **NEVER rationalize failures.** Do not classify failures as "pre-existing", "infrastructure issue", "misplaced test", "needs a running server", or "was deselected in the full run". A failing test is a failing test — fix it or report it to the user as a blocker.
3. **Start the right infrastructure.** If a test needs Docker (integration, e2e, admin), start Docker. The tooling exists — the decision tree in `.claude/rules/patterns/testing-patterns.md` § Test Integrity says which command starts what. When in doubt, `./run_all_tests.sh`.
4. **If infrastructure is broken, STOP.** Do not skip tests and report success. Tell the user the infrastructure is broken and either fix it or ask the user to fix it.
5. **Test results are saved as JSON** in `test-results/<ddmmyy_HHmm>/`. Review these instead of re-running the full suite. Background processes may crash and lose output — the JSON reports are the resilient record.

## Configuration

Local secrets live in `.env.secrets` (required for a working stack: Gemini, Google OAuth, GAM OAuth,
super-admin emails, Approximated). Every variable is documented in
[docs/deployment/environment-variables.md](docs/deployment/environment-variables.md) — read it before
touching credentials or auth configuration.

### Database schema
- **Core**: tenants, principals, products, media_buys, creatives, audit_logs
- **Workflow**: workflow_steps, object_workflow_mapping (human-in-the-loop approvals)
- **Note**: there are no `tasks` or `human_tasks` tables in the schema — don't reference them

## Adapter support

Adapters are registered in `src/adapters/__init__.py` and selected per tenant.
Registry keys: `gam`/`google_ad_manager`, `broadstreet`, `kevel`, `triton`/`triton_digital`, `mock`.
Maturity varies — GAM is by far the most complete. (`creative_engine` in the
registry is a creative-processing base class, not an ad-server adapter.)
The Broadstreet integration lives at `src/adapters/broadstreet/`.

### GAM adapter
**Supported pricing**: CPM, VCPM, CPC, FLAT_RATE

- Automatic line item type selection based on pricing + guarantees
- FLAT_RATE → SPONSORSHIP with CPD translation
- VCPM → STANDARD only (GAM requirement); compatibility matrix in `docs/adapters/`

### Mock adapter
**Supported**: all AdCP pricing models (CPM, VCPM, CPCV, CPP, CPC, CPV, FLAT_RATE) and all
currencies, with simulated metrics. Used for testing and development.

## Documentation

Rules files for day-to-day work (read the one matching your task before starting):
- `.claude/rules/patterns/code-patterns.md` — writing code: SQLAlchemy 2.0 form, JSONType, absolute imports, no quiet failures, code style, mypy/type checking
- `.claude/rules/patterns/testing-patterns.md` — running and writing tests: tox commands, suite organization, fixtures, quality rules, full test-integrity policy, infrastructure decision tree
- `.claude/rules/patterns/mcp-patterns.md` — MCP/A2A work: client usage, CLI testing, transport-boundary examples, access points
- `.claude/rules/workflows/` — TDD cycle, quality gates, beads workflow, bug reporting, session completion
- `tests/CLAUDE.md` — authoring tests with the harness: environments, factories, wire-envelope assertions

Detailed documentation lives in `/docs`:
- `development/engineering-standards.md` — the standards this codebase holds code to; read before writing a change
- `development/architecture-principles.md` — the governing principles behind the layering
- `development/architecture.md` — system architecture
- `development/request-lifecycle.md` — how a request reaches business logic
- `development/patterns-reference.md` — repository, Unit of Work, harness, and boundary patterns in full
- `development/structural-guards.md` — structural-guard design and inventory
- `development/GETTING_STARTED.md` — initial setup guide
- `development/README.md` — the map of development documentation
- `adapters/creating-an-adapter.md` — building an ad server adapter
- `development/e2e-testing.md` — end-to-end testing
- `development/troubleshooting.md` — common issues
- `security.md` — security guidelines
- `security/outbound-egress.md` — outbound HTTP and SSRF
- `quickstart.md` — local run walkthrough
- `deployment/` — deployment guides (including `environment-variables.md`)
- `adapters/` — adapter-specific documentation

Test examples live in `/tests`; adapter implementations in `/src/adapters`. File issues on the GitHub repository.

## Language and register

### Banned words and phrases (do not use, ever)
"load-bearing," "hand-waving," "reflexive hedging," "honest framing,"
"the unlock," "constellation," "oracle" (as metaphor), "surface area,"
"north star," "the real question," "table stakes," "prose" (use "text"
or "writing" instead).

### Banned sentence patterns
- Do NOT lead a sentence with what something is not before saying what
  it is. Never write "It's not X. It's Y." — write "It's Y" and add the
  contrast only if it's genuinely needed.
- Do NOT invent metaphors, aphorisms, or "strategic" framings on the
  spot (for example, "this is where a VP smells hand-waving"). If a
  metaphor isn't already a well-known one, don't use it.
- Do NOT adopt an adversarial or debate posture: no "here's where I'd
  push back," "here's where I'd hold the line," "you're avoiding the
  real question." State agreement or disagreement plainly.
- Do NOT dress up uncertainty with elaborate hedging paragraphs. If
  unsure, say "I'm not sure" once and move on.

### Concision without cryptic density
"Be concise" does not mean "compress into fewer, denser words." It
means: cut sentences that don't add information. Keep normal sentence
structure and common words. A concise answer should be easier to read
fast, not harder.

### Register
Write like a plain technical answer — the register of a good Stack
Overflow answer or internal doc, not a keynote or a LinkedIn post.
No forced cleverness. If a plainer word exists, use it.
