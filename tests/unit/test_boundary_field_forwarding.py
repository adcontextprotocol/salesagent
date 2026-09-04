"""Regression test: transport wrappers must forward all AdCP request fields to _impl.

Bug : MCP and A2A wrappers for create_media_buy and update_media_buy
silently dropped buyer_campaign_ref and ext before constructing the request object.
These fields are part of the AdCP spec and must reach _impl via the request object.

Core invariant: Every AdCP-spec field accepted by the wrapper must be included in
the request object passed to _impl. No silent field drops at the transport boundary.
"""

import ast
from pathlib import Path

from src.core.schemas import CreateMediaBuyRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _dict_splat_keys(node: ast.expr) -> set[str]:
    """String keys forwarded by a ``**`` splat of a dict literal.

    Models three spellings, because a matcher that knows only one reports the other two
    as DROPPED FIELDS -- the guard failing on correct code:

    * ``**omit_unset(k=v, ...)`` -- the current idiom. The helper drops unsent values so
      the model's declared default applies instead of being overwritten with a null
      (src/core/tools/_request_defaults.py), and the names it forwards are its keywords.
    * ``**({"k": v} if cond else {})`` -- the older per-field omit-when-absent form.
    * ``**{"k": v}`` -- a plain dict literal.

    A ``**kwargs`` of a runtime-built dict stays unmodellable and is ignored.
    """
    if isinstance(node, ast.Call):
        return {kw.arg for kw in node.keywords if kw.arg is not None}
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if isinstance(node, ast.IfExp):
        return _dict_splat_keys(node.body) | _dict_splat_keys(node.orelse)
    return set()


def _constructor_kwargs_in(fn: ast.AST, request_class: str) -> set[str]:
    kwargs: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and _call_name(node) == request_class:
            for kw in node.keywords:
                if kw.arg is not None:
                    kwargs.add(kw.arg)
                else:
                    # ``**`` splat — model the dict-literal / omit-when-absent form
                    # so a splat-forwarded field is not invisible to the guard.
                    kwargs |= _dict_splat_keys(kw.value)
    return kwargs


def _extract_request_constructor_kwargs(file_path: Path, wrapper_name: str, request_class: str) -> set[str]:
    """Extract keyword arguments a wrapper threads into the request constructor.

    Matches both forms a wrapper may take — the matcher must model every form
    or the guard reports false drops:

    1. Direct construction: ``CreateMediaBuyRequest(brand=..., ...)`` inside
       the wrapper body.
    2. Shared-builder indirection: the wrapper calls a module-local helper
       (e.g. ``CreateMediaBuyRequest(brand=..., ...)``) that itself
       constructs the request class. The wrapper's kwargs to the helper count,
       but ONLY intersected with what the helper actually forwards into the
       constructor — a field dropped at either hop is reported missing.
    """
    source = file_path.read_text()
    tree = ast.parse(source, filename=str(file_path))

    wrapper_node = _find_function(tree, wrapper_name)
    if wrapper_node is None:
        return set()

    # Module-local helpers that construct the request class, with what they forward.
    builder_forwards: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != wrapper_name:
            forwarded = _constructor_kwargs_in(node, request_class)
            if forwarded:
                builder_forwards[node.name] = forwarded

    kwargs = _constructor_kwargs_in(wrapper_node, request_class)
    for node in ast.walk(wrapper_node):
        if not isinstance(node, ast.Call):
            continue
        called = _call_name(node)
        if called in builder_forwards:
            passed = {kw.arg for kw in node.keywords if kw.arg is not None}
            kwargs |= passed & builder_forwards[called]
    return kwargs


def _extract_wrapper_params(file_path: Path, wrapper_name: str) -> set[str]:
    """Extract parameter names from a wrapper function signature.

    KEYWORD-ONLY parameters count. Reading only ``args.args`` made every
    ``def f(*, ...)`` look like it declared nothing, so a keyword-only builder
    silently reported all its fields as missing.
    """
    source = file_path.read_text()
    tree = ast.parse(source, filename=str(file_path))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == wrapper_name:
                return {arg.arg for arg in node.args.args + node.args.kwonlyargs}
    return set()


def _extract_call_kwargs(file_path: Path, caller_name: str, callee_name: str) -> set[str]:
    """Extract keyword arguments passed from caller to callee function.

    Finds calls like `callee_name(foo=foo, bar=bar, ...)` inside the named
    caller function and returns the set of keyword argument names. A ``**`` splat counts
    as forwarding the names inside it -- see :func:`_dict_splat_keys`.
    """
    source = file_path.read_text()
    tree = ast.parse(source, filename=str(file_path))

    caller_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == caller_name:
                caller_node = node
                break

    if caller_node is None:
        return set()

    kwargs = set()
    for node in ast.walk(caller_node):
        if not isinstance(node, ast.Call):
            continue
        called_name = None
        if isinstance(node.func, ast.Name):
            called_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            called_name = node.func.attr
        if called_name != callee_name:
            continue
        for kw in node.keywords:
            if kw.arg is not None:
                kwargs.add(kw.arg)
            else:
                kwargs |= _dict_splat_keys(kw.value)

    return kwargs


# ---------------------------------------------------------------------------
# Tests — create_media_buy
# ---------------------------------------------------------------------------

CREATE_FILE = Path("src/core/tools/media_buy_create.py")

# The checked set is DERIVED from the model, not hand-listed, so a new
# CreateMediaBuyRequest field cannot be silently dropped at the boundary: it is
# required by the guard until it is wired through the wrappers OR explicitly
# excluded below with a reason. idempotency_key is forwarded via the builder's
# omit-when-absent ``**`` splat; account / brand / ... as named kwargs.
_CREATE_NOT_FORWARDED = {
    # Threaded to _impl separately (status notifications), never into the request object.
    "push_notification_config",
    # Optional AdCP negotiation/IO fields the MCP/A2A wrappers do not yet expose.
    # Listed (not omitted) so they are tracked, not silently dropped — wire or
    # confirm-drop each before buyers rely on them.
    "adcp_major_version",
    "adcp_version",
    "advertiser_industry",
    "agency_estimate_number",
    "artifact_webhook",
    "invoice_recipient",
    "io_acceptance",
    "plan_id",
    "proposal_id",
    "total_budget",
}
CREATE_SPEC_FIELDS = set(CreateMediaBuyRequest.model_fields) - _CREATE_NOT_FORWARDED


class TestCreateMediaBuyFieldForwarding:
    """MCP and A2A wrappers must forward all AdCP fields into CreateMediaBuyRequest."""

    def test_mcp_wrapper_constructs_request_with_all_spec_fields(self):
        """MCP create_media_buy must pass all AdCP spec fields to CreateMediaBuyRequest."""
        kwargs = _extract_request_constructor_kwargs(CREATE_FILE, "create_media_buy", "CreateMediaBuyRequest")
        missing = CREATE_SPEC_FIELDS - kwargs
        assert not missing, (
            f"MCP wrapper 'create_media_buy' drops AdCP fields when constructing "
            f"CreateMediaBuyRequest: {sorted(missing)}"
        )

    def test_builder_constructs_request_with_all_spec_fields(self):
        """The BUILDER must pass every AdCP spec field into CreateMediaBuyRequest.

        Moved off create_media_buy_raw, which no longer constructs the request -- it
        receives one. Construction is the builder's job, so that is where dropping a
        field is a defect worth catching.
        """
        kwargs = _extract_request_constructor_kwargs(CREATE_FILE, "CreateMediaBuyRequest", "CreateMediaBuyRequest")
        missing = CREATE_SPEC_FIELDS - kwargs
        assert not missing, (
            f"CreateMediaBuyRequest drops AdCP fields when constructing CreateMediaBuyRequest: {sorted(missing)}"
        )

    def test_mcp_wrapper_accepts_all_spec_fields_as_params(self):
        """MCP create_media_buy must accept all AdCP spec fields as parameters."""
        params = _extract_wrapper_params(CREATE_FILE, "create_media_buy")
        missing = CREATE_SPEC_FIELDS - params
        assert not missing, (
            f"MCP wrapper 'create_media_buy' doesn't accept AdCP fields as parameters: {sorted(missing)}"
        )

    def test_a2a_wrapper_takes_the_built_request_and_no_spec_fields(self):
        """create_media_buy_raw takes the BUILT request, so it declares no spec field.

        The inverse of what this asserted, and for the same reason as its update sibling:
        the wrapper re-listed the request's fields, and now takes the request. The
        obligation -- every spec field must be constructible -- is carried by
        test_builder_accepts_all_spec_fields below, on CreateMediaBuyRequest,
        which is the one place a buyer field can enter.
        """
        params = _extract_wrapper_params(CREATE_FILE, "create_media_buy_raw")
        leaked = CREATE_SPEC_FIELDS & params
        assert not leaked, (
            f"create_media_buy_raw declares spec fields {sorted(leaked)} beside the request. "
            f"They belong on the builder; a second list here is the drift the request shape removed."
        )
        assert "req" in params, "the wrapper must take the built request"

    def test_builder_accepts_all_spec_fields(self):
        """CreateMediaBuyRequest must accept every AdCP spec field."""
        params = _extract_wrapper_params(CREATE_FILE, "CreateMediaBuyRequest")
        missing = CREATE_SPEC_FIELDS - params
        assert not missing, f"CreateMediaBuyRequest doesn't accept AdCP fields as parameters: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Tests — update_media_buy
# ---------------------------------------------------------------------------

UPDATE_FILE = Path("src/core/tools/media_buy_update.py")

# AdCP spec fields that must reach the UpdateMediaBuyRequest via UpdateMediaBuyRequest
UPDATE_SPEC_FIELDS = {
    "media_buy_id",
    "paused",
    "start_time",
    "end_time",
    "packages",
    "push_notification_config",
    "context",
    "reporting_webhook",
    "ext",
}


class TestUpdateMediaBuyFieldForwarding:
    """MCP and A2A update wrappers must forward all AdCP fields through UpdateMediaBuyRequest."""

    def test_mcp_wrapper_accepts_all_spec_fields(self):
        """MCP update_media_buy must accept all AdCP spec fields as parameters."""
        params = _extract_wrapper_params(UPDATE_FILE, "update_media_buy")
        missing = UPDATE_SPEC_FIELDS - params
        assert not missing, (
            f"MCP wrapper 'update_media_buy' doesn't accept AdCP fields as parameters: {sorted(missing)}"
        )

    def test_a2a_wrapper_takes_the_built_request_and_no_spec_fields(self):
        """update_media_buy_raw takes the BUILT request, so it declares no spec field.

        This replaces the inverse assertion -- that the wrapper accept every AdCP field
        as a parameter -- which was correct while the wrapper re-listed the request's
        fields and is false by design now that it takes the request. No obligation is
        lost: "every spec field must be constructible" is carried by
        test_build_update_request_accepts_all_spec_fields below, on the builder, which
        is the one place a buyer field can now enter. Asserting the wrapper is EMPTY of
        them is what stops the two-list drift from being reintroduced.
        """
        params = _extract_wrapper_params(UPDATE_FILE, "update_media_buy_raw")
        leaked = UPDATE_SPEC_FIELDS & params
        assert not leaked, (
            f"update_media_buy_raw declares spec fields {sorted(leaked)} beside the request. "
            f"They belong on UpdateMediaBuyRequest; a second list here is the drift the "
            f"request shape removed."
        )
        assert "req" in params, "the wrapper must take the built request"

    def test_build_update_request_accepts_all_spec_fields(self):
        """UpdateMediaBuyRequest must accept all AdCP spec fields as parameters."""
        params = _extract_wrapper_params(UPDATE_FILE, "UpdateMediaBuyRequest")
        missing = UPDATE_SPEC_FIELDS - params
        assert not missing, f"UpdateMediaBuyRequest doesn't accept AdCP fields as parameters: {sorted(missing)}"

    def test_mcp_wrapper_forwards_all_spec_fields_to_build(self):
        """MCP wrapper must pass all spec fields to UpdateMediaBuyRequest call site."""
        kwargs = _extract_call_kwargs(UPDATE_FILE, "update_media_buy", "UpdateMediaBuyRequest")
        missing = UPDATE_SPEC_FIELDS - kwargs
        assert not missing, (
            f"MCP wrapper 'update_media_buy' doesn't forward AdCP fields to UpdateMediaBuyRequest: {sorted(missing)}"
        )

    def test_a2a_wrapper_does_not_build_the_request_itself(self):
        """update_media_buy_raw RECEIVES the request; it must not construct one.

        This replaces the assertion that the wrapper forward every spec field INTO
        UpdateMediaBuyRequest. That was the obligation while the wrapper owned
        construction; it now takes the built request, and its callers (the REST route
        and the A2A skill handler) build. A wrapper that also built would be a second
        construction path -- the exact thing the request shape removes -- so the
        invariant is that it contains no build call at all.

        The field-completeness obligation is unchanged and still graded, one test below,
        where construction actually happens: UpdateMediaBuyRequest.
        """
        kwargs = _extract_call_kwargs(UPDATE_FILE, "update_media_buy_raw", "UpdateMediaBuyRequest")
        assert not kwargs, (
            f"update_media_buy_raw calls UpdateMediaBuyRequest with {sorted(kwargs)}. "
            f"It takes the built request; building here would restore the second path."
        )

    def test_build_update_request_constructs_with_all_spec_fields(self):
        """UpdateMediaBuyRequest must include all spec fields in UpdateMediaBuyRequest construction."""
        # UpdateMediaBuyRequest uses request_params dict, not direct constructor kwargs.
        # Check that every spec field has a `request_params["field"] = field` assignment.
        source = Path(UPDATE_FILE).read_text()
        tree = ast.parse(source)

        # Find UpdateMediaBuyRequest
        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "UpdateMediaBuyRequest":
                    func_node = node
                    break

        assert func_node is not None, "UpdateMediaBuyRequest function not found"

        # Find all request_params["key"] = ... assignments
        assigned_keys = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "request_params"
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)
                    ):
                        assigned_keys.add(target.slice.value)

        missing = UPDATE_SPEC_FIELDS - assigned_keys
        assert not missing, f"UpdateMediaBuyRequest doesn't include AdCP fields in request_params: {sorted(missing)}"


class TestExtractorModelsBuilderIndirection:
    """Self-tests for the two-hop matcher: a drop at EITHER hop is reported."""

    @staticmethod
    def _extract_from_source(tmp_path, source: str) -> set[str]:
        f = tmp_path / "mod.py"
        f.write_text(source)
        return _extract_request_constructor_kwargs(f, "wrapper", "Req")

    def test_field_dropped_at_wrapper_to_builder_hop_is_missing(self, tmp_path):
        src = (
            "def _build(*, a=None, b=None):\n"
            "    return Req(a=a, b=b)\n"
            "def wrapper(a, b):\n"
            "    return _build(a=a)\n"  # b never passed to the builder
        )
        assert self._extract_from_source(tmp_path, src) == {"a"}

    def test_field_dropped_inside_builder_is_missing(self, tmp_path):
        src = (
            "def _build(*, a=None, b=None):\n"
            "    return Req(a=a)\n"  # builder swallows b
            "def wrapper(a, b):\n"
            "    return _build(a=a, b=b)\n"
        )
        assert self._extract_from_source(tmp_path, src) == {"a"}

    def test_field_threaded_through_both_hops_counts(self, tmp_path):
        src = (
            "def _build(*, a=None, b=None):\n"
            "    return Req(a=a, b=b)\n"
            "def wrapper(a, b):\n"
            "    return _build(a=a, b=b)\n"
        )
        assert self._extract_from_source(tmp_path, src) == {"a", "b"}

    def test_dict_splat_field_is_seen(self, tmp_path):
        # **({"b": b} if ...) forwarding must be visible to the matcher — this is
        # the exact blind spot that let idempotency_key slip the guard.
        src = (
            "def _build(*, a=None, b=None):\n"
            "    return Req(a=a, **({'b': b} if b is not None else {}))\n"
            "def wrapper(a, b):\n"
            "    return _build(a=a, b=b)\n"
        )
        assert self._extract_from_source(tmp_path, src) == {"a", "b"}

    def test_field_passed_but_never_forwarded_is_missing(self, tmp_path):
        # 'c' is passed by the wrapper but neither named nor splatted by the
        # builder — the guard still reports it dropped (no splat false-negative).
        src = (
            "def _build(*, a=None, b=None, c=None):\n"
            "    return Req(a=a, **({'b': b} if b is not None else {}))\n"
            "def wrapper(a, b, c):\n"
            "    return _build(a=a, b=b, c=c)\n"
        )
        assert self._extract_from_source(tmp_path, src) == {"a", "b"}
