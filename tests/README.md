# AdCP Sales Agent test suite

> For AI agent instructions, see [`CLAUDE.md`](CLAUDE.md) in this directory.

## Test suites

Each suite maps to a tox environment:

| Suite | Directory | tox env | Needs Docker? | Count |
|-------|-----------|---------|---------------|-------|
| Unit | `tests/unit/` | `unit` | No | ~4100 |
| Integration | `tests/integration/` | `integration` | Postgres only | ~1770 |
| BDD | `tests/bdd/` | `bdd` | Postgres only | ~820 |
| E2E | `tests/e2e/` | `e2e` | Full stack | ~80 |
| Admin | `tests/admin/` | `admin` | Full stack | ~4 |

## Run tests

```bash
# Quick quality check (format + lint + typecheck + unit tests)
make quality

# Full suite — starts Docker, runs all 5 suites in parallel, tears down
./run_all_tests.sh

# Individual suites via tox
tox -e unit
tox -e integration
tox -e bdd
tox -e integration -- -k test_name    # Pass pytest args after --

# Single integration test with auto-DB
scripts/run-test.sh tests/integration/test_foo.py -x

# Entity-scoped (runs across unit + integration + e2e + admin)
make test-entity ENTITY=delivery

# Coverage report
make test-cov
```

Test results are saved as JSON in `test-results/<ddmmyy_HHmm>/` (last 10 runs kept).

## Test architecture

### Harness system (`tests/harness/`)

The test harness provides domain-specific environments that manage mocks, database sessions,
identity, and multi-transport dispatch. Each environment is a context manager:

```python
from tests.harness import DeliveryPollEnv
from tests.factories import TenantFactory, PrincipalFactory, MediaBuyFactory

with DeliveryPollEnv(tenant_id="t1", principal_id="p1") as env:
    tenant = TenantFactory(tenant_id="t1")
    principal = PrincipalFactory(tenant=tenant, principal_id="p1")
    buy = MediaBuyFactory(tenant=tenant, principal=principal)

    env.set_adapter_response(buy.media_buy_id, impressions=5000)
    result = env.call_impl(media_buy_ids=[buy.media_buy_id])
    assert result.deliveries[0].impressions == 5000
```

Environments auto-patch external dependencies, bind database sessions to factories,
and support dispatching through the three transports (A2A, MCP, REST), in-process or over real HTTP.

See [`CLAUDE.md`](CLAUDE.md) for the full environment table and API reference.

### Factory system (`tests/factories/`)

Create all test data through [factory-boy](https://factoryboy.readthedocs.io/) factories:

```python
from tests.factories import TenantFactory, PrincipalFactory, MediaBuyFactory

tenant = TenantFactory(tenant_id="t1")
principal = PrincipalFactory(tenant=tenant)
buy = MediaBuyFactory(tenant=tenant, principal=principal)
identity = PrincipalFactory.make_identity(tenant_id="t1", principal_id="p1")
```

ORM factories live in `tests/factories/` (core, principal, product, media_buy, creative,
metrics, webhook). Pydantic model factories (Format, FormatId) are also available.

### BDD tests (`tests/bdd/`)

Behavioral tests derived from AdCP requirements using pytest-bdd. The feature
files in `tests/bdd/features/` are generated from the AdCP spec — do not edit
them by hand.

Step definitions live in two layers:

- **`steps/generic/`** — Reusable steps shared across use cases
- **`steps/domain/`** — Use-case-specific steps

Every scenario is automatically parametrized across the three transports
(A2A, MCP, REST) unless tagged with a specific one (`@rest`, `@mcp`, `@a2a`).

### Obligation tests

Tests tagged with `Covers: <obligation-id>` verify behavioral contracts. The
obligation documents that those ids refer to are generated reports and are not
committed — a generated report kept in the tree drifts from its generator — so
no structural guard checks the tags against the documents. The tags record
provenance; do not add more. See [`CLAUDE.md`](CLAUDE.md) for the rules that
bind a tagged test.

## Structural guards

AST-scanning tests in `tests/unit/` enforce architecture invariants on every
`make quality` run. See [Structural guards](../docs/development/structural-guards.md)
for the full list. The following guards matter most when writing tests:

- **Repository pattern** — no `get_db_session()` or `session.add()` outside repositories
- **BDD no-op steps** — Then steps must assert, not delegate to no-ops
- **BDD trivial assertions** — Then steps must compare values, not just check truthiness
- **BDD no dict registry** — Given steps must use factories, not raw dicts

## Markers

Tests carry the following markers:

- `@pytest.mark.requires_db` — needs PostgreSQL (integration, BDD)
- **Entity markers** (auto-applied by filename): `delivery`, `creative`, `product`,
  `media_buy`, `tenant`, `auth`, `adapter`, `inventory`, `schema`, `admin`,
  `architecture`, `targeting`, `transport`, `workflow`, `policy`, `agent`, `infra`

## Coverage

Coverage is collected per-suite and combined automatically:

- HTML report: `htmlcov/index.html` (open with `make test-cov`)
- JSON report: `coverage.json`
- Per-entity thresholds: `tests/coverage_scopes.yaml`
