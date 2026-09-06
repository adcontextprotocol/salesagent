"""FastMCP middleware for AdCP backward-compatibility normalization.

Translates deprecated field names, strips unknown fields, and converts FastMCP
TypeAdapter validation failures into AdCP envelopes in every environment. In
production, it first retries structural failures after schema-aware deep stripping.
Runs after MCPAuthMiddleware.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams
from pydantic import ValidationError

from src.core.exceptions import adcp_error_for
from src.core.tool_error_logging import _translate_to_tool_error, record_boundary_error

logger = logging.getLogger(__name__)


class RequestCompatMiddleware(Middleware):
    """Normalize, strip, and provide forward-compatible fallback for MCP tools.

    Three-stage pipeline:
    2. Strip fields not in the tool's JSON Schema via strip_unknown_params()
    3. If TypeAdapter rejects the arguments, always translate and record the
       failure as an AdCP validation envelope. In production only, first deep-
       strip schema-unknown nested fields and retry when that changes the input.
       This lets our Pydantic models (with extra='ignore') remain the validation
       gate for forward-compatible fields while preserving typed failures in dev.

    The fallback only catches TypeAdapter ValidationErrors (structural type
    mismatches). Business logic errors from the tool function propagate normally.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next,
    ) -> ToolResult:
        arguments = context.message.arguments
        if not arguments:
            return await call_next(context)

        tool_name = context.message.name
        normalized, modified = await self._prepared_arguments(context, tool_name, dict(arguments))

        if modified:
            new_message = CallToolRequestParams(
                name=tool_name,
                arguments=normalized,
            )
            context = context.copy(message=new_message)

        # Step 3: Dispatch — with production fallback on TypeAdapter rejection
        try:
            return await call_next(context)
        except Exception as exc:
            if not self._is_typeadapter_validation_error(exc):
                raise

            if self._should_retry(exc):
                # Deep-strip unknown fields at every nesting level using the tool's
                # JSON Schema. TypeAdapter rejects unknown fields in objects with
                # additionalProperties: false. Our Pydantic models (extra='ignore')
                # would accept them — stripping bridges the gap.
                tool_schema = await self._get_tool_schema(context, tool_name)
                if tool_schema is not None:
                    stripped = deep_strip_to_schema(normalized, tool_schema)
                    if stripped != normalized:
                        logger.warning(
                            "TypeAdapter rejected %s — retrying with deep-stripped arguments "
                            "(production forward-compat): %s",
                            tool_name,
                            _summarize_error(exc),
                        )
                        stripped_message = CallToolRequestParams(
                            name=tool_name,
                            arguments=stripped,
                        )
                        stripped_context = context.copy(message=stripped_message)
                        try:
                            return await call_next(stripped_context)
                        except Exception as retry_exc:
                            if not self._is_typeadapter_validation_error(retry_exc):
                                raise
                            exc = retry_exc

            # Convert ONCE. The raw exception still goes to
            # _translate_to_tool_error so the emitted AdCPToolError keeps it as
            # __cause__; the converted result rides alongside it so the translator
            # does not repeat the mapping.
            typed = adcp_error_for(exc)
            tenant_id = None
            principal_id = None
            if context.fastmcp_context is not None:
                try:
                    identity = await context.fastmcp_context.get_state("identity")
                    if identity is not None:
                        tenant_id = identity.tenant_id
                        principal_id = identity.principal_id
                except Exception:
                    logger.debug("Could not read MCP identity for validation error logging", exc_info=True)
            record_boundary_error(
                "mcp",
                tool_name,
                typed,
                tenant_id=tenant_id,
                principal_id=principal_id,
            )
            _translate_to_tool_error(exc, typed=typed)

    async def _prepared_arguments(
        self,
        context: MiddlewareContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Pipeline steps 1-2: translate deprecated names, then strip unknown fields.

        Returns ``(arguments, modified)``; the caller rebuilds the message only when
        something actually changed. Extracted from ``on_call_tool`` so that method
        stays inside the statement ceiling the complexity ratchet enforces — the
        dispatch-and-recover half (step 3) is a different job from preparing the
        payload, and reads better apart from it.
        """
        modified = False

        # Strip unknown fields (schema-aware, production only)
        # In dev mode, unknown fields reach TypeAdapter and fail loudly —
        # this is how we detect that the seller agent doesn't support a
        # field the spec requires. In production, strip silently to avoid
        # rejecting callers using newer schema versions.
        from src.core.config import is_production

        if is_production():
            known_params = await self._get_known_params(context, tool_name)
            if known_params is not None:
                arguments, stripped = strip_unknown_params(arguments, known_params)
                if stripped:
                    modified = True
                    logger.warning(
                        "Stripped unknown fields from %s: %s",
                        tool_name,
                        ", ".join(stripped),
                    )

        return arguments, modified

    @staticmethod
    def _should_retry(exc: Exception) -> bool:
        """Determine if the exception is a TypeAdapter structural error worth retrying.

        Only retries in production mode. Only retries Pydantic ValidationErrors
        that come from FastMCP's TypeAdapter (not from our business logic).

        FastMCP's TypeAdapter raises raw pydantic.ValidationError with title
        "call[tool_name]". Business logic ValidationErrors (from model construction
        inside _impl) have the model class name (e.g. "CreateMediaBuyRequest").
        """
        from src.core.config import is_production

        return is_production() and RequestCompatMiddleware._is_typeadapter_validation_error(exc)

    @staticmethod
    def _is_typeadapter_validation_error(exc: Exception) -> bool:
        """Return True for FastMCP TypeAdapter validation failures."""
        return isinstance(exc, ValidationError) and exc.title.startswith("call[")

    async def _get_tool_schema(
        self,
        context: MiddlewareContext,
        tool_name: str,
    ) -> dict[str, Any] | None:
        """Look up tool's full JSON Schema for deep stripping.

        Returns None if lookup fails (defensive — skip stripping).
        """
        try:
            fastmcp_ctx = context.fastmcp_context
            if fastmcp_ctx is None:
                return None
            server = fastmcp_ctx.fastmcp
            tool = await server.get_tool(tool_name)
            if tool is None:
                return None
            return tool.parameters
        except Exception:
            logger.debug("Could not look up schema for %s, skipping deep strip", tool_name)
            return None

    async def _get_known_params(
        self,
        context: MiddlewareContext,
        tool_name: str,
    ) -> set[str] | None:
        """Look up tool's declared parameter names from its JSON Schema.

        Returns None if lookup fails (defensive — skip stripping).
        """
        try:
            fastmcp_ctx = context.fastmcp_context
            if fastmcp_ctx is None:
                return None
            server = fastmcp_ctx.fastmcp
            tool = await server.get_tool(tool_name)
            if tool is None:
                return None
            return set(tool.parameters.get("properties", {}).keys())
        except Exception:
            logger.debug("Could not look up params for %s, skipping strip", tool_name)
            return None


def _summarize_error(exc: Exception) -> str:
    """Extract a short summary from a validation error for logging."""
    text = str(exc)
    # Take first line or first 150 chars
    first_line = text.split("\n")[0]
    return first_line[:150] if len(first_line) > 150 else first_line


def strip_unknown_params(
    params: dict[str, Any],
    known_params: set[str],
) -> tuple[dict[str, Any], list[str]]:
    """Remove fields not in known_params set.

    Args:
        params: Request parameters dict (already normalized).
        known_params: Set of parameter names the tool function accepts.
            Typically from tool.parameters["properties"].keys().

    Returns:
        Tuple of (cleaned dict with only known keys, sorted list of stripped key names).
    """
    unknown = params.keys() - known_params
    if not unknown:
        return params, []
    cleaned = {k: v for k, v in params.items() if k in known_params}
    return cleaned, sorted(unknown)


def deep_strip_to_schema(
    value: Any,
    schema: dict[str, Any],
    defs: dict[str, Any] | None = None,
) -> Any:
    """Recursively strip fields not declared in a JSON Schema.

    Walks the value alongside its JSON Schema and removes unknown properties
    at every nesting level where additionalProperties is false. This lets
    TypeAdapter accept the cleaned arguments, deferring real validation to
    our Pydantic models (which use extra='ignore' in production).

    Args:
        value: The argument value (dict, list, or primitive).
        schema: JSON Schema for this value (from tool.parameters or a nested property).
        defs: The $defs dict from the root schema (for resolving $ref).

    Returns:
        Cleaned value with unknown properties removed at strict levels.
    """
    if defs is None:
        defs = schema.get("$defs", {})

    return _strip_node(value, schema, defs)


def _resolve_ref(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Resolve a $ref pointer to its definition."""
    ref = schema.get("$ref", "")
    # Handle #/$defs/Name format
    parts = ref.rsplit("/", 1)
    if len(parts) == 2:
        def_name = parts[1]
        if def_name in defs:
            return defs[def_name]
    return schema


def _strip_node(value: Any, schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    """Recursive worker for deep_strip_to_schema."""
    # Follow $ref
    if "$ref" in schema:
        schema = _resolve_ref(schema, defs)

    # anyOf / oneOf: strip against each variant, pick best match
    for union_key in ("anyOf", "oneOf"):
        if union_key in schema:
            variants = schema[union_key]
            # Filter out null-type variants (e.g., {"type": "null"} in Optional fields)
            real_variants = [v for v in variants if v.get("type") != "null"]
            if not real_variants:
                return value
            # Strip against each variant, pick the one whose declared properties
            # match the most input keys. This avoids variants with
            # additionalProperties: true inflating the score via unknown fields.
            best_result = value
            best_score = -1
            for variant in real_variants:
                try:
                    resolved = variant
                    if "$ref" in resolved:
                        resolved = _resolve_ref(resolved, defs)
                    candidate = _strip_node(value, variant, defs)
                    # Score by how many input keys match declared properties
                    declared = set(resolved.get("properties", {}).keys())
                    score = len(declared & value.keys()) if isinstance(value, dict) else 0
                    if score > best_score:
                        best_score = score
                        best_result = candidate
                except Exception:
                    logger.debug("Schema candidate matching failed", exc_info=True)
                    continue
            return best_result

    # allOf: value must satisfy ALL schemas. Merge declared properties from
    # all members and strip against the union of known fields.
    if "allOf" in schema:
        merged_props: dict[str, Any] = {}
        allows_additional = True
        for member in schema["allOf"]:
            resolved = member
            if "$ref" in resolved:
                resolved = _resolve_ref(resolved, defs)
            merged_props.update(resolved.get("properties", {}))
            if resolved.get("additionalProperties") is False:
                allows_additional = False
        merged_schema = {
            "type": "object",
            "properties": merged_props,
            "additionalProperties": allows_additional,
        }
        return _strip_node(value, merged_schema, defs)

    # Object: strip unknown properties, recurse into known ones
    if isinstance(value, dict):
        props = schema.get("properties", {})
        allows_additional = schema.get("additionalProperties", True)
        result = {}
        for k, v in value.items():
            if k in props:
                result[k] = _strip_node(v, props[k], defs)
            elif allows_additional:
                result[k] = v
            # else: field is unknown and additionalProperties is false — strip it
        return result

    # Array: recurse into items
    if isinstance(value, list) and "items" in schema:
        items_schema = schema["items"]
        return [_strip_node(item, items_schema, defs) for item in value]

    # Primitives (str, int, float, bool, None): pass through
    return value
