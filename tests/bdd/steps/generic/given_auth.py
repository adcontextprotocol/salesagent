"""Given steps for authentication and tenant context.

These steps set up the authentication state in ``ctx`` that When/Then steps
rely on. They are generic across all use cases — any scenario that needs
an authenticated buyer, a missing tenant, or a sandbox account can reuse them.
"""

from __future__ import annotations

from pytest_bdd import given, parsers

from tests.bdd.steps.generic._account_resolution import ensure_tenant_principal

# ── Authenticated / tenant-present paths ────────────────────────────


@given("a valid tenant context exists")
@given("the Buyer has tenant context")
def given_buyer_has_tenant_context(ctx: dict) -> None:
    """Buyer has valid tenant context (happy path)."""
    ctx["has_tenant"] = True
    ctx.setdefault("tenant_id", "test_tenant")


@given("the Buyer has tenant context via MCP session")
def given_buyer_has_tenant_context_mcp(ctx: dict) -> None:
    """Buyer has tenant context via MCP session."""
    ctx["has_tenant"] = True
    ctx["transport"] = "mcp"
    ctx.setdefault("tenant_id", "test_tenant")


# ── Missing-auth / missing-tenant paths ─────────────────────────────


@given("the Buyer has no authentication credentials")
@given("the request has no valid authentication")
def given_buyer_no_auth(ctx: dict) -> None:
    """Buyer has no authentication credentials at all.

    ``identity=None`` plumbs through every dispatcher as a token-less request,
    so the REAL transport auth gates run (A2A ``on_message_send`` no-token
    gate, REST ``_require_auth_dep``, MCP boundary) — nothing is simulated
    (#1417). ``dispatch_identity`` is the key the uc002 full-create
    dispatch reads to override its default authenticated identity.
    """
    ctx["has_auth"] = False
    ctx["identity"] = None
    ctx["dispatch_identity"] = None


@given("no hostname-based tenant resolution is possible")
def given_no_hostname_tenant(ctx: dict) -> None:
    """No tenant can be resolved from hostname."""
    ctx["hostname_tenant"] = None


@given("no tenant can be resolved from the request context")
def given_no_tenant_resolved(ctx: dict) -> None:
    """No tenant can be resolved from any source (MCP path)."""
    ctx["has_tenant"] = False
    ctx["identity"] = None


# ── Sandbox / production account ─────────────────────────────────────


def _seed_account_for_principal(ctx: dict, *, sandbox: bool) -> None:
    """Seed an Account with the given sandbox flag, reachable by the scenario principal.

    Writes the Account and AgentAccountAccess rows and commits them, so the
    identity resolves to an account carrying that flag.

    Seeds rather than setting a request field because the scenarios using this
    Given do not send one; the account reaches the tool through the principal.
    A scenario that means "send account X on the request" wants a different
    Given — ``account`` IS a request field (optional on get_media_buys and
    get_products, REQUIRED on create_media_buy and update_media_buy).
    """
    from tests.factories.account import AccountFactory, AgentAccountAccessFactory

    env = ctx["env"]
    account = AccountFactory(tenant=ctx["tenant"], sandbox=sandbox)
    AgentAccountAccessFactory(tenant=ctx["tenant"], principal=ctx["principal"], account=account)
    env._commit_factory_data()
    ctx["sandbox"] = sandbox
    ctx["account"] = account
    ctx.setdefault("tenant_id", "sandbox_tenant" if sandbox else "prod_tenant")


@given("the request targets a sandbox account")
def given_sandbox_account(ctx: dict) -> None:
    """Seed a sandbox account for the principal (the token infers the account)."""
    _seed_account_for_principal(ctx, sandbox=True)


@given("the request targets a production account")
def given_production_account(ctx: dict) -> None:
    """Seed a production (non-sandbox) account for the principal."""
    _seed_account_for_principal(ctx, sandbox=False)


@given("the Buyer is authenticated")
@given(parsers.parse('the Buyer is authenticated as principal "{principal_id}" on tenant "{tenant_id}"'))
@given("the Buyer is authenticated with a valid principal_id")
@given("the Buyer Agent has an authenticated connection")
@given(parsers.parse("the Buyer Agent has an authenticated connection via {transport}"))
def given_buyer_authenticated(
    ctx: dict,
    transport: str | None = None,
    principal_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """P01 — a buyer with a valid identity. THE authentication setup, 381 feature lines.

    Five sentences, one function, ONE body. The collapse is proven at the
    implementation, not at the wording: every spelling registered here was
    measured to normalize (``ast.dump`` with attributes stripped) to exactly the
    two statements below, so they are interchangeable by construction rather
    than by anyone judging them similar. ``the Buyer is authenticated with a
    valid principal_id`` (234 feature lines) and ``the Buyer Agent has an
    authenticated connection`` (118) were two functions in
    ``steps/domain/uc011_accounts.py`` with byte-identical bodies, saying the
    same thing in different words because nothing forced them to meet.

    ``the Buyer is authenticated`` is the CANONICAL spelling — the one a feature
    file should be written in when the scenario carries no principal/tenant data
    of its own. The other three sentences are legacy spellings kept so the ~295
    feature lines still using them keep resolving; pytest-bdd matches on text, so
    deleting a spelling breaks every scenario that uses it.

    ``principal_id``/``tenant_id`` are the P01 parameters: when a scenario names
    who it authenticates as, the env is re-pointed FIRST and
    ``ensure_tenant_principal`` then seeds exactly that pair (the factories read
    the env's ids), so the named identity is the one that reaches the wire. When
    the sentence names neither — every one of the 381 lines today — both are
    ``None``, nothing is switched, and the body is byte-for-byte the collapsed
    one. This is deliberately NOT the same step as
    ``uc003_ext_error_scenarios.given_buyer_authenticated_as`` (``... as
    principal "P"``, no tenant): that one has a DIFFERENT normalized body
    (``authenticate_env_as`` — a principal switch with no tenant/principal
    seeding), so it is not P01 however similar it reads, and it is left alone.

    ``transport`` is parsed and DISCARDED, and that is not an oversight in this
    function: ``pytest_generate_tests`` parametrizes every scenario over
    a2a/mcp/rest, so a sentence naming one either lies or defeats the
    parametrization. The 29 feature lines that say "via <transport>" are a
    Gherkin-generation defect; the parameter is accepted so they keep resolving
    until the generator stops emitting them, and ignored so they cannot pin.
    """
    env = ctx["env"]
    named = tenant_id is not None or principal_id is not None

    # REFUSE rather than silently seed nothing. ensure_tenant_principal returns
    # early when ctx already holds a tenant, so naming a principal/tenant AFTER a
    # Background has authenticated would re-point the env at the named pair and
    # seed nothing for it -- _resolve_auth_token then finds no Principal row and
    # returns None, and the scenario runs UNAUTHENTICATED while its own sentence
    # says otherwise. That is the quiet failure this repo forbids, and it is worse
    # than a crash: the scenario still reports a result, just not the one it names.
    #
    # No caller hits this today (all 381 lines pass neither parameter), which is
    # exactly why it is worth failing loudly now -- the first scenario to use the
    # parameterized spelling would otherwise inherit a silent no-op.
    if named and "tenant" in ctx:
        raise AssertionError(
            f"this scenario already authenticated before naming principal={principal_id!r} "
            f"tenant={tenant_id!r}, so the named pair would be switched to but never seeded, "
            f"and the request would go out unauthenticated. Name the identity in the FIRST "
            f"authentication step of the scenario (or its Background), not in a later one."
        )

    if tenant_id is not None:
        env.switch_tenant(tenant_id)
    if principal_id is not None:
        env.switch_principal(principal_id)
    ctx["has_auth"] = True
    ensure_tenant_principal(ctx, env)
