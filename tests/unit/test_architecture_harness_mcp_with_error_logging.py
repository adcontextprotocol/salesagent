"""Guard: harness MCP dispatch must route tool calls through with_error_logging.

A harness env method that invokes a production MCP tool wrapper DIRECTLY
(``update_media_buy(ctx=...)`` / ``create_media_buy(ctx=...)`` via asyncio.run)
bypasses the production boundary decorator that real MCP registration applies
(src/core/main.py: ``mcp.tool()(with_error_logging(fn))``). On error the raw
AdCPError propagates instead of an AdCPToolError carrying the two-layer wire
envelope, so McpDispatcher cannot capture ``wire_error_envelope`` — the MCP
error path can't be asserted at the wire layer.

This is invisible to ``make quality`` (no BDD) and was the #1417 bug
(update path) — see also the wider disease class in #1417.

Disease shape (AST-detectable): inside a tests/harness function, a call
``<tool>(ctx=...)`` where ``<tool>`` is a known MCP tool wrapper, in a function
that does NOT reference ``with_error_logging``. The fix wraps first:
``with_error_logging(update_media_buy)`` then calls the wrapped callable — which
has no direct ``<tool>(ctx=...)`` call, so it is compliant.

AST guard → positive + negative meta-tests suffice (no regex-slip case).

Allowlist shrinks as #1417 migrates the remaining sites.

"""

import ast
from pathlib import Path

from tests.unit._architecture_helpers import assert_violations_match_allowlist, iter_call_expressions

_HARNESS_DIR = Path(__file__).resolve().parents[1] / "harness"

# Production MCP tool wrappers that must be invoked through with_error_logging.
_MCP_TOOLS = {"create_media_buy", "update_media_buy"}

# Known-deferred violations (#1417). (relative_path, enclosing_function).
# Each entry has a FIXME at the source site. Allowlist only shrinks.
# media_buy_create.py:call_mcp was fixed when the harness MCP path moved to
# _run_mcp_client (no direct create_media_buy(ctx=...) call) — entry removed.
_KNOWN_VIOLATIONS: set[tuple[str, str]] = set()


def _enclosing_funcs_with_direct_tool_call(source: str) -> set[str]:
    """Names of functions that call a known MCP tool directly as ``tool(ctx=...)``."""
    tree = ast.parse(source)
    bad: set[str] = set()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in iter_call_expressions(func):
            callee = call.func
            if (
                isinstance(callee, ast.Name)
                and callee.id in _MCP_TOOLS
                and any(kw.arg == "ctx" for kw in call.keywords)
            ):
                bad.add(func.name)
                break
    return bad


def _func_references_with_error_logging(source: str, func_name: str) -> bool:
    tree = ast.parse(source)
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) and func.name == func_name:
            for node in ast.walk(func):
                if isinstance(node, ast.Name) and node.id == "with_error_logging":
                    return True
    return False


def _scan_violations() -> set[tuple[str, str]]:
    """Every (file, function) that calls an MCP tool directly without with_error_logging."""
    violations: set[tuple[str, str]] = set()
    for py_file in _HARNESS_DIR.glob("*.py"):
        source = py_file.read_text()
        for func_name in _enclosing_funcs_with_direct_tool_call(source):
            if not _func_references_with_error_logging(source, func_name):
                violations.add((py_file.name, func_name))
    return violations


def test_no_unguarded_direct_mcp_tool_calls():
    """No harness function may call an MCP tool directly without with_error_logging."""
    violations = _scan_violations()
    new = violations - _KNOWN_VIOLATIONS
    assert new == set(), (
        f"New unguarded direct MCP tool call(s) in tests/harness: {sorted(new)}. "
        f"Wrap the tool with with_error_logging(...) before invoking so the MCP error "
        f"path surfaces the wire envelope . Do NOT add to the allowlist."
    )


def test_known_violations_not_stale():
    """Allowlist only shrinks — a fixed site must be removed from _KNOWN_VIOLATIONS."""
    assert_violations_match_allowlist(
        _scan_violations(),
        _KNOWN_VIOLATIONS,
        fix_hint=(
            "Wrap the tool with with_error_logging(...) before invoking so the MCP error "
            "path surfaces the wire envelope ."
        ),
    )


def _func_references_name(source: str, func_name: str, name: str) -> bool:
    tree = ast.parse(source)
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) and func.name == func_name:
            for node in ast.walk(func):
                if isinstance(node, ast.Attribute) and node.attr == name:
                    return True
                if isinstance(node, ast.Name) and node.id == name:
                    return True
    return False


def test_migrated_update_site_is_guarded():
    """The #1417 fix: media_buy_dual update MCP path must run the guarded pipeline.

    Since the adcp 6.6 merge the update path mirrors the create path: it routes
    through ``_run_mcp_client`` (the real FastMCP Client pipeline, whose server
    registration applies ``with_error_logging`` in src/core/main.py) instead of
    wrapping the tool inline. Pin that routing plus the absence of a direct
    ``update_media_buy(ctx=...)`` call.
    """
    source = (_HARNESS_DIR / "media_buy_dual.py").read_text()
    tree = ast.parse(source)
    funcs = [
        f
        for f in ast.walk(tree)
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == "_call_update_mcp"
    ]
    assert funcs, "_call_update_mcp disappeared from media_buy_dual.py"
    explicit_wrap = _func_references_with_error_logging(source, "_call_update_mcp")
    real_pipeline = _func_references_name(source, "_call_update_mcp", "_run_mcp_client")
    assert explicit_wrap or real_pipeline, (
        "_call_update_mcp must either route through _run_mcp_client (production-registered "
        "with_error_logging) or wrap the tool with with_error_logging inline (the #1417 fix regressed)."
    )
    # And it must not appear as a direct-call violation.
    assert ("media_buy_dual.py", "_call_update_mcp") not in _scan_violations()


# --- Meta-tests: verify the guard logic itself ---

_BAD_SNIPPET = """
def call_mcp(self, **kwargs):
    tool_result = aio.run(create_media_buy(ctx=mock_ctx, **kwargs))
    return tool_result
"""

_GOOD_SNIPPET = """
def _call_update_mcp(self, **kwargs):
    wrapped = with_error_logging(update_media_buy)
    tool_result = asyncio.run(wrapped(ctx=mock_ctx, **kwargs))
    return tool_result
"""


def test_guard_positive_catches_direct_call():
    """Meta: a direct tool(ctx=...) call with no with_error_logging is flagged."""
    bad = _enclosing_funcs_with_direct_tool_call(_BAD_SNIPPET)
    assert "call_mcp" in bad
    assert not _func_references_with_error_logging(_BAD_SNIPPET, "call_mcp")


def test_guard_negative_accepts_wrapped_call():
    """Meta: wrapping with with_error_logging before calling is compliant."""
    # No direct create/update tool(ctx=...) call — the wrapped callable is invoked instead.
    assert _enclosing_funcs_with_direct_tool_call(_GOOD_SNIPPET) == set()
    assert _func_references_with_error_logging(_GOOD_SNIPPET, "_call_update_mcp")


# ---------------------------------------------------------------------------
# The deprecated wrapper path, ratcheted to zero.
#
# ``_run_mcp_wrapper`` calls the UNDECORATED module function, so
# ``with_error_logging`` — applied at registration time in ``src/core/main.py``
# — never runs: no ``AdCPToolError`` is raised, nothing is stashed, and the
# dispatcher captures ``None`` for both the error envelope and the success
# response while the env goes on declaring ``has_wire=True``.
#
# The guard above cannot see this. Its detector matches a literal
# ``tool(ctx=...)`` call, and these envs pass the tool by reference, so widening
# ``_MCP_TOOLS`` measures nothing (verified by running its own algorithm).
# This scan is the one that does.
#
# The wrapper itself is deliberately NOT deleted: ``test_account_mcp_context_bypass``
# monkeypatches ``AccountListEnv.call_mcp`` onto it at runtime to grade the
# wrapper's own ctx-bypass defect, and ``test_harness_base`` pins that
# ``BaseTestEnv`` still exposes it. That patch lives in ``tests/integration/``,
# outside this scan directory, so it is excluded by location rather than by
# exemption.
# What must stay at zero is harness ENVS routing their real dispatch through it.
# ---------------------------------------------------------------------------

_RUN_MCP_WRAPPER_CALLERS: set[tuple[str, str]] = set()


def _wrapper_references(source: str) -> set[str]:
    """Enclosing-function names that MENTION ``_run_mcp_wrapper``, however spelled.

    Reference position, not only ``call.func``: an alias (``f = self._run_mcp_wrapper``),
    a ``functools.partial(self._run_mcp_wrapper, ...)`` and a class-body-level
    binding all reach the deprecated path while never appearing as the callee of
    a call expression. Matching the attribute itself closes those; a scan that
    only looked at call sites would ratchet a regression it could not see.

    ``getattr(self, "_run_mcp_wrapper")`` is matched too, via the string
    constant, since that is the one spelling with no ``Attribute`` node at all.
    """
    tree = ast.parse(source)
    named: set[str] = set()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute) and node.attr == "_run_mcp_wrapper":
                named.add(func.name)
            elif isinstance(node, ast.Constant) and node.value == "_run_mcp_wrapper":
                named.add(func.name)
    # Module- and class-body level references sit outside any function.
    body_level = any(
        (isinstance(n, ast.Attribute) and n.attr == "_run_mcp_wrapper")
        or (isinstance(n, ast.Constant) and n.value == "_run_mcp_wrapper")
        for n in ast.walk(tree)
    )
    if body_level and not named:
        named.add("<module>")
    return named


def _run_mcp_wrapper_call_sites() -> set[tuple[str, str]]:
    """(relative_path, enclosing_function) for every ``_run_mcp_wrapper`` reference."""
    sites: set[tuple[str, str]] = set()
    for path in sorted(_HARNESS_DIR.rglob("*.py")):
        # Env modules only. ``tests/harness/test_harness_base.py`` legitimately
        # NAMES the attribute to pin that ``BaseTestEnv`` still exposes it — an
        # assertion about the wrapper, not a dispatch through it. Matching
        # references rather than calls (see above) is what makes this exclusion
        # necessary, and scoping by module purpose is more honest than
        # allowlisting the one test by name, which would go stale silently.
        if path.name.startswith("test_"):
            continue
        for func_name in _wrapper_references(path.read_text(encoding="utf-8")):
            sites.add((str(path.relative_to(_HARNESS_DIR.parent)), func_name))
    return sites


def test_no_harness_env_dispatches_through_the_deprecated_wrapper():
    """Every harness env reaches MCP through ``_run_mcp_client``, never the raw wrapper."""
    assert_violations_match_allowlist(
        _run_mcp_wrapper_call_sites(),
        _RUN_MCP_WRAPPER_CALLERS,
        fix_hint=(
            "Fix: call self._run_mcp_client('<tool_name>', <ResponseModel>, **kwargs) instead. "
            "_run_mcp_wrapper bypasses with_error_logging, so the dispatcher captures no wire "
            "envelope and no wire response, while the env still declares has_wire=True."
        ),
    )


_WRAPPER_POSITIVE = """
class SomeEnv:
    def call_mcp(self, **kwargs):
        return self._run_mcp_wrapper(some_tool, SomeResponse, **kwargs)
"""

_WRAPPER_ALIASED = """
class SomeEnv:
    def call_mcp(self, **kwargs):
        run = self._run_mcp_wrapper
        return run(some_tool, SomeResponse, **kwargs)
"""

_WRAPPER_GETATTR = """
class SomeEnv:
    def call_mcp(self, **kwargs):
        return getattr(self, "_run_mcp_wrapper")(some_tool, SomeResponse, **kwargs)
"""

_WRAPPER_NEGATIVE = """
class SomeEnv:
    def call_mcp(self, **kwargs):
        return self._run_mcp_client("some_tool", SomeResponse, **kwargs)
"""


def test_wrapper_detector_catches_a_direct_call():
    assert _wrapper_references(_WRAPPER_POSITIVE) == {"call_mcp"}


def test_wrapper_detector_catches_an_alias_that_never_appears_as_a_callee():
    """The realistic regression is a copied call; these are the ways around it."""
    assert _wrapper_references(_WRAPPER_ALIASED) == {"call_mcp"}


def test_wrapper_detector_catches_a_getattr_spelling():
    assert _wrapper_references(_WRAPPER_GETATTR) == {"call_mcp"}


def test_wrapper_detector_accepts_the_client_path():
    assert _wrapper_references(_WRAPPER_NEGATIVE) == set()
