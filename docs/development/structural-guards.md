# Structural Guards

Automated architecture enforcement tests that run on every `make quality`.
Each guard uses AST scanning and introspection to detect violations at the
source level — no runtime execution of business logic needed.

## Why These Exist

During the adcp 3.2 → 3.6 migration, several classes of bugs appeared that
shared a common trait: they were invisible at review time and only surfaced
as silent runtime failures. Examples:

- A schema class copied fields from the adcp library instead of inheriting,
  then drifted out of sync when the library updated a field type
- An MCP wrapper accepted a new parameter but forgot to pass it through to
  the shared `_impl` function — callers could set the value but it was silently
  discarded
- A database query filtered an Integer PK column with string values from JSON,
  returning 0 rows instead of raising an error

These failures are difficult to catch in code review because the code _looks_
correct. The guards make these structural invariants machine-checkable.

## Design Principles

**Allowlists shrink, never grow.** Every guard has a set of known violations
(existing code that predates the guard). New code that introduces a violation
fails CI immediately. When an existing violation is fixed, the stale-allowlist
test forces you to remove the entry.

**FIXME comments link to a GitHub issue/PR.** Every allowlisted violation has a
corresponding `# FIXME(#<gh-issue>)` comment at the source location, linking to
a tracked GitHub issue/PR. Use the GitHub number, never a local beads id — beads
ids don't resolve for outside contributors reading the code.

**AST scanning, not runtime execution.** Guards parse Python source with the
`ast` module. They don't import or execute business logic, so they run fast
and can't be affected by runtime state.

**Introspection for type hierarchies.** Where AST alone is insufficient (e.g.,
checking class MRO), guards use `inspect` and `importlib` on the already-imported
modules.

## Guard Inventory

### Pre-existing Guards

| Test File | What It Enforces |
|-----------|-----------------|
| `test_no_toolerror_in_impl.py` | `_impl` functions raise `AdCPSalesAgentError`, never `ToolError` from FastMCP |
| `test_transport_agnostic_impl.py` | `_impl` functions have zero transport imports (no fastmcp, a2a, starlette) |
| `test_impl_resolved_identity.py` | `_impl` functions accept `ResolvedIdentity`, not `Context`/`ToolContext` |

These three guards enforce Critical Pattern #5: shared `_impl` functions are
transport-agnostic. They don't know whether they're called from MCP, A2A, or
a REST endpoint.

### Schema Inheritance Guard (removed)

Deleted in PR #1941. Its subject was the SDK's own classes rather than this repo's
structure, which made it unfixable in principle: to find which SDK types this repo
subclasses it had to enumerate how imports are spelled, and two classes imported under
an `AdCP*` alias instead of `Library*` were invisible to it. Widening the alias key took
its target set from 54 classes to 149 and demanded nine new allowlist entries about
someone else's DTOs.

Measured before removal: a duplicate `media_buy_id: str` on `UpdateMediaBuySuccess` left
the guard green AND changed nothing observable — same annotation, same wire keys. The
same field redeclared as `int` also left the guard green, but failed the alignment suite
in two places.

That backstop is gone: the alignment suite was deleted in full
([docs/design/one-tool-registry.md](../design/one-tool-registry.md)), because a design in
which the DTO IS the pinned model minus a declared omission leaves nothing for it to
compare. Redeclarations are graded instead by
`tests/unit/test_architecture_schema_inheritance.py` against the library parent, which is
the guard this section describes as removed — the section itself is stale, and the guard
is live.

### Boundary Completeness Guard

**File:** `tests/unit/test_architecture_boundary_completeness.py`

**What it enforces:** An `_impl` function may declare only parameters the boundary can
supply — `req`, `identity` and `context_id` — and must accept the first two.

**Why it matters:** Every transport reaches an implementation through
`src/core/tools/_boundary.py`, which calls it as `impl(req=..., identity=..., **extra)`.
`extra` is not open: it carries the transport-derived values the boundary knows how to
obtain, which today is `context_id` alone. A parameter outside that set can never be filled,
so it silently takes its default on every call — the tool accepts something no caller can
send.

#### How it works

It reads the signature of every `TOOLS[...].impl` and compares it to
`BOUNDARY_SUPPLIED_PARAMS`. There is no registry of implementations to maintain and no file
to locate: the registry names them.

#### What it replaced, and why the replacement was necessary

The guard used to scan each `*_raw` and MCP wrapper for the arguments it forwarded, because
there were fifteen wrappers and any one could drop a parameter the others passed. There are
none left, so "does the wrapper forward everything" is answered by construction.

The old form also demonstrated the failure this guard exists to prevent. Its wrapper lookup
returned `None` when it could not find a wrapper, and `None` meant "nothing to check" — so
the day the wrappers were deleted, it went green while grading nothing.

### Query Type Safety Guard

**File:** `tests/unit/test_architecture_query_type_safety.py`

**What it enforces:** Database queries must use Python types matching the
SQLAlchemy column type. Specifically: don't pass string values to Integer PK
columns.

**Why it matters:** When JSON data arrives at the API boundary, IDs are strings
(`"42"`). If these strings are passed directly to `.in_()` or `filter_by()` on
an Integer column, the behavior is database-dependent — PostgreSQL may do an
implicit cast, but some paths return 0 rows silently.

#### How it works

The guard catalogs all models with Integer primary keys:

```python
INTEGER_PK_MODELS = {
    "PricingOption": "id",
    "SyncJob": "sync_id",
    "AuditLog": "log_id",
    # ... 18 total
}
```

It then scans 12 source files for two AST patterns:

1. **`.in_()` on Integer PK columns:** `PricingOption.id.in_(some_list)` — the
   argument type can't be verified statically, so every occurrence is flagged
   for review
2. **String literals in `filter_by()`:** `filter_by(id="42")` — this is always
   a bug

#### Example of what it catches

```python
def _get_pricing_options(pricing_option_ids: list[Any]):
    # pricing_option_ids come from JSON — they're strings like ["42", "99"]
    # PricingOption.id is an Integer column
    stmt = select(PricingOption).where(
        PricingOption.id.in_(pricing_option_ids)  # FLAGGED: strings → Integer column
    )
```

The fix is to cast at the boundary: `[int(x) for x in pricing_option_ids]`.

#### Tests

| Test | What It Checks |
|------|---------------|
| `test_no_in_queries_on_integer_pk_with_wrong_type` | No new `.in_()` calls on Integer PK columns without review |
| `test_no_string_literals_in_filter_by_for_integer_pks` | No `filter_by(id="string")` patterns |
| `test_known_violations_still_exist` | Allowlisted violations haven't been fixed (stale entry detection) |

#### Current known violations (1)

| File | Pattern | Tracked By |
|------|---------|------------|
| `media_buy_delivery.py` | `PricingOption.id.in_(string_list)` | salesagent-mq3n |

### No model_dump() in _impl Guard

**File:** `tests/unit/test_architecture_no_model_dump_in_impl.py`

**What it enforces:** `_impl` functions must not call `.model_dump()` or
`.model_dump_internal()`. Serialization is the transport wrapper's job.

**Why it matters:** When business logic calls `model_dump()`, it takes on
responsibility for serialization format (JSON mode, aliases, exclude rules).
This couples the _impl layer to a specific output format. The transport
wrapper should receive a model object and decide how to serialize it.

#### How it works

The guard scans all `*_impl()` functions under `src/core/tools/` using AST,
looking for method calls where the method name is `model_dump` or
`model_dump_internal`.

#### Tests

| Test | What It Checks |
|------|---------------|
| `test_no_new_model_dump_violations` | No new `.model_dump()` calls beyond the allowlist |
| `test_known_violations_not_stale` | Allowlisted violations haven't been fixed (stale entry detection) |
| `test_violation_count_documented` | Total count matches allowlist (catches both directions) |

#### Current known violations (29)

| File | Count | Primary Use |
|------|-------|-------------|
| `media_buy_update.py` | 23 | `response_data=X.model_dump()` for workflow step storage |
| `media_buy_create.py` | 4 | `raw_request=req.model_dump()` for DB storage + workflow |
| `products.py` | 1 | `filters.model_dump()` in logging |
| `creatives/listing.py` | 1 | `filters.model_dump()` for dict conversion |

20 of the 29 violations are `response_data=response.model_dump(mode="json")`
calls that serialize workflow step responses for DB storage. These should be
replaced with typed repository methods that accept model objects directly.

### Repository Pattern Guard

**File:** `tests/unit/test_architecture_repository_pattern.py`

**What it enforces:** Two invariants:

1. **No `get_db_session()` in business logic.** Functions in `_impl` files must
   not call `get_db_session()` directly — data access belongs in repository classes.
2. **No `session.add()` in integration tests.** Test functions must not construct
   ORM objects inline — use polyfactory-based fixtures instead.

**Why it matters:** When business logic directly opens database sessions, it
becomes impossible to test without a real database, impossible to swap storage
backends, and impossible to enforce consistent transaction boundaries. Similarly,
when tests scatter `session.add()` calls through test bodies, fixture setup is
duplicated, brittle, and hard to maintain.

#### How it works

The guard scans 14 production files and 10 integration test files using AST:

**Invariant 1** finds function definitions that contain `get_db_session()` calls
(both `get_db_session()` and `module.get_db_session()` forms):

```python
# FLAGGED: business logic opens its own session
async def _create_media_buy_impl(req, identity):
    with get_db_session() as session:   # ← violation
        media_buy = MediaBuy(...)
        session.add(media_buy)

# CORRECT: repository encapsulates data access
async def _create_media_buy_impl(req, identity, repo: MediaBuyRepository):
    media_buy = repo.create_from_request(req, identity)
```

**Invariant 2** finds test functions/fixtures that call `session.add()`,
`db_session.add()`, or similar patterns:

```python
# FLAGGED: inline fixture setup
def test_something(integration_db):
    with get_db_session() as session:
        tenant = Tenant(name="test")
        session.add(tenant)             # ← violation

# CORRECT: factory-based fixture
def test_something(integration_db, sample_tenant):
    # sample_tenant created by polyfactory fixture
    pass
```

#### Tests

| Test | What It Checks |
|------|---------------|
| `test_no_new_get_db_session_in_impl` | No new `get_db_session()` calls outside the allowlist |
| `test_allowlist_entries_still_exist` (impl) | Stale allowlist detection for impl violations |
| `test_no_new_session_add_in_tests` | No new `session.add()` calls outside the allowlist |
| `test_allowlist_entries_still_exist` (tests) | Stale allowlist detection for test violations |

#### Current known violations

- **27 `get_db_session()` calls** across 10 production files (media_buy_create, update, delivery, list, products, creatives, task_management, admin blueprints)
- **58 `session.add()` calls** across 10 integration test files

All tracked by `salesagent-qo8a`.

### BDD Step Quality Guards

Five AST-scanning guards enforce step definition quality in `tests/bdd/steps/`.
They prevent the most common LLM-generated BDD anti-patterns.

#### No-Op Then Steps

**File:** `tests/unit/test_architecture_bdd_no_pass_steps.py`

Catches three failure modes in `@then` step functions:
1. **Empty body** — `pass`, ellipsis, or docstring-only
2. **No code** — no assert, call, or raise at all
3. **No-op delegation** — body has zero `assert` statements and only delegates to
   non-assertion helpers (like `_pending(ctx, step)`). Catches any LLM-invented
   placeholder by structure, not by name.

A call counts as "meaningful" only if the function name starts with `assert_`,
`_assert_`, `check_`, `_check_`, `verify_`, `_verify_`, or is `pytest.skip/xfail/fail`,
or is `env.*` (harness method).

**Current known violations:** 41 Then steps in `uc004_delivery.py` using `_pending()`.

#### Trivial Assertions

**File:** `tests/unit/test_architecture_bdd_no_trivial_assertions.py`

Catches `@then` steps that only use bare truthiness checks (`assert x`) without
comparisons (`==`, `!=`, `in`, `not in`, `is`, `isinstance`).

#### No Dict in Registry

**File:** `tests/unit/test_architecture_bdd_no_dict_registry.py`

Catches `@given` steps that store raw dict literals in `ctx["registry_formats"]`
instead of `FormatFactory.build()` objects.

#### No Duplicate Step Bodies

**File:** `tests/unit/test_architecture_bdd_no_duplicate_steps.py`

Catches groups of 3+ step functions with identical normalized bodies (after
stripping docstrings). Threshold of 2 is tolerated for partition/boundary pairs.

#### No Silent Env Degradation

**File:** `tests/unit/test_architecture_bdd_no_silent_env.py`

Catches two "No Quiet Failures" violations:
1. **`ctx.get("env")`** — returns `None` instead of `KeyError` when harness is missing.
   Canonical: `ctx["env"]` (guaranteed by autouse fixture).
2. **`hasattr(env, "method")`** — probes harness at runtime instead of using typed
   protocols. If env lacks a method, xfail the scenario rather than silently skip.

**Current known violations:** 17 `ctx.get("env")` + 22 `hasattr(env, ...)` in `uc004_delivery.py`.

### Single Migration Head Guard

**File:** `tests/unit/test_architecture_single_migration_head.py`

**What it enforces:** The Alembic migration graph must have exactly one head
revision at all times.

**Why it matters:** When two PRs each create a migration branching from the
same parent and both merge to main, the migration DAG forks into multiple
heads. This makes `alembic upgrade head` fail, `alembic downgrade -1`
ambiguous, and `alembic revision` error without `--head`. The problem is
invisible to PR authors because neither has the other's migration locally.

#### How it works

The guard parses every migration file's AST to extract `revision` (string)
and `down_revision` (string, tuple, or None). It handles both `ast.Assign`
and `ast.AnnAssign` styles. It then builds the set of all revisions and the
set of all revisions pointed to by a `down_revision`. Heads are revisions
not pointed to by any other migration. The test asserts exactly one head.

#### Tests

| Test | What It Checks |
|------|---------------|
| `test_single_migration_head` | Exactly one head exists in the migration graph |

#### No allowlist

Zero tolerance. If multiple heads exist, you must create a merge migration
before your PR merges:

```bash
uv run alembic merge -m "Merge migration heads" heads
```

The smoke test in `tests/smoke/test_database_migrations.py` also checks this,
providing coverage in the CI smoke-tests job before unit tests run.

### PR 4 Hook-Relocation Guards (issue #1234)

These guards replaced grep-based pre-commit hooks. Run via `pytest -m arch_guard`
or as part of `make quality`.

| Test File | Replaces Hook | What It Enforces |
|-----------|---------------|------------------|
| `test_architecture_no_tenant_config.py` | `no-tenant-config` | No `tenant.config` / `tenant["config"]` in `src/` |
| `test_architecture_jsontype_columns.py` | `enforce-jsontype` | JSON columns use `JSONType`, not plain `JSON` |
| `test_architecture_no_defensive_rootmodel.py` | `check-rootmodel-access` | No `hasattr(x, "root")` without `# noqa: rootmodel` |
| `test_architecture_import_usage.py` | `check-import-usage` | Tree-wide import usage check for `src/` |
| `test_architecture_query_type_safety.py` | `enforce-sqlalchemy-2-0` (partial) | `test_no_legacy_session_query`, `test_models_use_mapped_not_column` |
| `test_architecture_pre_commit_hook_count.py` | — | Commit-stage hook count ≤12 (D27) |
| `test_architecture_pre_commit_no_additional_deps.py` | — | No `additional_dependencies` in pre-commit config (PR 2) |
| `test_architecture_ci_bdd_shard_manifest.py` | — | BDD CI shards partition suite; matrix matches `SHARD_COUNTS` |
| `test_architecture_repo_invariants.py` | `repo-invariants` (partial) | Self-tests for `.fn()` detection in consolidated hook |

Shared AST helpers live in `tests/unit/_architecture_helpers.py`. Guards use the
`@pytest.mark.arch_guard` marker (distinct from the entity-marker `architecture`).

Each PR 4 guard includes a **known-bad self-test** (inline snippet or tmp fixture)
so a narrowed detector fails CI instead of passing green silently.

CI-only hook enforcement moved to `make quality-ci`: duplication, GAM auth support,
response attribute access, roundtrip tests. See `.pre-commit-coverage-map.yml`.

## Adding a New Guard

1. Create `tests/unit/test_architecture_{name}.py`
2. Use AST scanning (not `inspect.getsource()` — it's banned by lint rules)
3. Include an allowlist for pre-existing violations
4. Include a stale-allowlist test that fails when a violation is fixed but the
   entry remains
5. Add FIXME comments at each violation site: `# FIXME(#<gh-issue>): description` (GitHub issue/PR number, never a beads id)
6. Document the guard in this file

## Symbol subjects and shape subjects

A guard's subject is either a **symbol** — a function, class or constant that
exists in `src/` or the pinned SDK — or a **shape**: a code pattern with no name
to import, like "a bare `except` placed ahead of a specific one".

The rule:

> **If the subject is a symbol, BIND it — import or resolve it in the guard
> module, so a rename fails here. If the subject is a shape, prose is correct;
> there is nothing to import.**

The sorting question is not "does the constant hold an identifier?" It is:

> **If the subject were renamed, does this guard go SILENT or LOUD?**

Bind the silent ones. A string-matching guard whose subject is renamed keeps
passing over a codebase that no longer contains what it scans for — it reports
clean because it finds nothing, which is indistinguishable from finding nothing
wrong. That is the failure mode binding removes: an unresolvable import cannot
be green.

Two things worth knowing before writing one:

- A **module-level** import buys a collection failure, but it aborts the whole
  unit run and masks every other result. For a heavy module, use
  `importlib.import_module` inside the test — a rename still reddens
  `make quality`, as a failure rather than a collection error.
- Prefer **containment over derivation**. Asserting the guard's vocabulary is a
  subset of production's catches production losing a member. Deriving the
  vocabulary FROM production makes the guard track whatever production says,
  which is the opposite of a guard.

This page does not list which guards are which kind. Such a list is prose about
symbols, which is exactly the artifact that goes stale without anything noticing
— the reason the rule above exists.

## Running Guards

```bash
# All guards (part of make quality)
make quality

# Just the architecture guards
uv run pytest tests/unit/test_architecture_*.py tests/unit/test_*impl*.py -v

# Single guard
uv run pytest tests/unit/test_architecture_schema_inheritance.py -v
```

## Relationship to Other Quality Mechanisms

```
Pre-commit hooks               ← catch formatting, route conflicts, star imports
    │
    ▼
Structural guards              ← catch architecture violations with allowlists (THIS FILE)
    │
    ▼
Unit tests (~2950)             ← catch behavior bugs
    │
    ▼
Integration tests (PostgreSQL) ← catch data layer bugs
    │
    ▼
E2E tests (Docker stack)       ← catch deployment/wiring bugs
```

Guards sit between pre-commit hooks (syntactic) and unit tests (behavioral).
They enforce structural properties that are invisible to both.

**ast-grep scan rules** (`.ast-grep/rules/`) provide fast first-line defense at
commit time for simple BDD patterns (`ctx.get("env")`, `hasattr(env, ...)`,
error fabrication). Python AST guards manage the allowlists for existing
violations and handle complex cross-file analysis.
