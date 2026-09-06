"""Reduce a parameter bag to the fields this seller's schema declares.

THE POLICY. A field our models do not declare never reaches an implementation. In development
it is a hard rejection, so a spec field we have not implemented is loud rather than silent; in
production it is dropped, so a newer buyer is served instead of refused.

WHERE IT RUNS. ``ToolSpec.validate`` -- the one seam every transport passes a parameter bag
through. It ran in the MCP middleware alone before, which is why the same bytes had three
meanings: dropped on MCP, rejected on A2A/REST inside an ``additionalProperties: false``
object, and KEPT and passed to the implementation inside one that allows extras. The last of
those also reached the idempotency digest, so a retry carrying an unknown key inside ``ext``
was answered IDEMPOTENCY_CONFLICT instead of being replayed.

WHY A SCHEMA WALK AND NOT ``model_config``. Two other approaches were built and thrown away.
Walking the DATA against the model tree meant reimplementing union resolution, ``RootModel``
unwrapping and ``dict[K, V]`` detection -- pydantic's job -- and it deleted every
``account.account_id`` and every creative asset on its first run. Setting ``extra`` on the 255
reachable SDK classes made pydantic's ``__eq__`` time-dependent (``__pydantic_extra__`` is
``{}`` under ``allow`` and ``None`` under ``ignore``), so a model built before the change
compared unequal to a field-identical one built after, and tests failed by import order. The
schema is the thing that actually defines the accepted shape, so walking it needs neither.

A FREE-FORM CONTAINER KEEPS ITS CONTENTS. An object that declares no properties -- ``ext``,
``context`` -- is the schema's shape for "arbitrary data lives here". There is nothing
undeclared to remove, only contents to lose.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
            elif allows_additional and not props:
                # A free-form container: the schema declares no properties here, so there is
                # nothing undeclared to remove -- only contents to lose. This is `ext` and
                # `context`, the shape AdCP uses for "arbitrary data lives here".
                result[k] = v
            # else: the object declares a shape and this key is not part of it. Dropped,
            # whatever `additionalProperties` says: the spec decides what a buyer MAY SEND,
            # this seller decides what it PROCESSES.
        return result

    # Array: recurse into items
    if isinstance(value, list) and "items" in schema:
        items_schema = schema["items"]
        return [_strip_node(item, items_schema, defs) for item in value]

    # Primitives (str, int, float, bool, None): pass through
    return value
