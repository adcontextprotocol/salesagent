"""AdCP backward-compatibility request normalization.

Translates deprecated field names to current equivalents before validation.
Mirrors the JS adcp-client's normalizeRequestParams() logic.
Shared by all transports (MCP, A2A, REST).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.core.schema_helpers import brand_shorthand_to_domain, is_url_shorthand, to_brand_reference

logger = logging.getLogger(__name__)
V25_SIGNALS: frozenset[str] = frozenset({"brand_manifest", "promoted_offerings", "campaign_ref"})

# Tools where the brand_manifest → brand translation and the brand shorthand
# coercion apply.
_BRAND_TOOLS: frozenset[str] = frozenset({"get_products", "create_media_buy"})


@dataclass
class NormalizationResult:
    """Result of normalizing request parameters."""

    params: dict[str, Any]
    inferred_version: str = "3.0"
    translations_applied: list[str] = field(default_factory=list)


def _translate_brand_manifest(value: Any) -> dict[str, str] | None:
    """Convert brand_manifest (URL string or {url: str}) to BrandReference {domain}.

    Legacy v2.5 compat: silently strip unparseable values (return None). Explicit
    ``brand`` on tool boundaries uses ``to_brand_reference`` instead, which raises
    ``AdCPValidationError(field="brand")`` for the same malformed inputs.

    Returns None if the value cannot be parsed into a valid domain.
    """
    if value is None:
        return None

    url: str | None = None
    if isinstance(value, str):
        if not is_url_shorthand(value):
            return None
        url = value
    elif isinstance(value, dict):
        raw_url = value.get("url")
        if not raw_url or not isinstance(raw_url, str):
            return None
        if not is_url_shorthand(raw_url):
            return None
        url = raw_url
    else:
        return None

    domain = brand_shorthand_to_domain(url)
    if not domain:
        logger.debug("Could not parse domain from brand_manifest url=%r; stripping field", url)
        return None
    return {"domain": domain}


def _normalize_brand(value: Any) -> tuple[Any, bool]:
    """Coerce the explicit ``brand`` shorthand to the BrandReference wire shape.

    The announced shape is the SPEC's shape. ``apply_dto_announced_shape`` copies
    the DTO's declared type onto the tool's ``__annotations__``, and FastMCP reads
    those to build the TypeAdapter — so the DTO is what decides what MCP accepts,
    and a DTO widened past its library parent is how the shorthand used to be
    admitted. That widening is a Liskov violation the type checker objects to, and
    it puts backwards-compatibility tolerance in the announced contract, where it
    does not belong. The tolerance belongs here: this normalizer runs before
    validation on all three transports (MCP ``RequestCompatMiddleware`` before
    ``call_next``, REST ``RestCompatMiddleware`` before FastAPI binds the body,
    A2A's skill dispatcher before any handler), so the shorthand keeps working
    while the model states the spec's type.

    Malformed input is NOT swallowed. ``to_brand_reference`` is the same
    raise-capable funnel every explicit-brand call site already used, so a bad
    brand still surfaces as ``AdCPValidationError(field="brand")`` rather than
    reaching the narrowed model and being reported as a generic type mismatch
    that does not name the field.

    Returns ``(value, changed)``. ``changed`` is False when the caller already sent
    the canonical shape, so a request that needed no help is neither logged as a
    translation nor cause for REST to rewrite a body it did not change.
    """
    brand_ref = to_brand_reference(value)
    if brand_ref is None:
        return value, False
    # mode="json" keeps params JSON-serializable, which both REST's body rewrite
    # (json.dumps) and A2A's idempotency hash (RFC 8785 over this dict) require —
    # a BrandReference instance would break either. exclude_none keeps the
    # unchanged case genuinely unchanged instead of padding it with null fields
    # the buyer never sent.
    normalized = brand_ref.model_dump(mode="json", exclude_none=True)
    return normalized, normalized != value


def _normalize_packages(packages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize deprecated fields inside package dicts.

    Handles:
    - optimization_goal (scalar) → optimization_goals (array)
    - catalog (scalar) → catalogs (array)
    """
    translations: list[str] = []
    result = []
    for pkg in packages:
        pkg = dict(pkg)

        if "optimization_goal" in pkg:
            if "optimization_goals" not in pkg or not pkg["optimization_goals"]:
                pkg["optimization_goals"] = [pkg["optimization_goal"]]
                translations.append("optimization_goal → optimization_goals")
            del pkg["optimization_goal"]

        if "catalog" in pkg:
            if "catalogs" not in pkg or not pkg["catalogs"]:
                pkg["catalogs"] = [pkg["catalog"]]
                translations.append("catalog → catalogs")
            del pkg["catalog"]

        result.append(pkg)
    return result, translations


def _upgrade_creative_format_ids(creatives: Any) -> tuple[Any, bool]:
    """Rewrite a legacy ``format_id`` on each creative into the 3.1 federated shape.

    ``core/format-id.json`` @ 3.1 types the field as ``{agent_url, id}``. A pre-3.1 buyer
    sends a bare string, or a dict with no ``agent_url``; both are shapes the pinned
    ``CreativeAsset`` rejects outright, so this is a genuine wire-compatibility rewrite and
    belongs here rather than on the DTO -- a ``BeforeValidator`` accepting the shorthand would
    make the model announce a shape AdCP does not define.

    The result is dumped straight back to a wire dict. ``upgrade_legacy_format_id`` returns
    OUR ``FormatId`` subclass, and pydantic does not re-validate a model instance that already
    satisfies the annotation, so handing the instance on made A2A the only transport whose
    ``CreativeAsset.format_id`` was a different CLASS. Pydantic v2 equality is class-sensitive,
    so the registry match in ``creatives/_processing`` then found nothing and every generative
    creative was written as a plain static asset with no error.

    Returns ``(creatives, changed)``; ``changed`` is False when every entry already carried the
    canonical shape, so a request that needed no help is not logged as a translation.
    """
    if not isinstance(creatives, list):
        return creatives, False

    from src.core.format_cache import upgrade_legacy_format_id

    result = []
    changed = False
    for creative in creatives:
        if not isinstance(creative, dict) or "format_id" not in creative:
            result.append(creative)
            continue
        upgraded = upgrade_legacy_format_id(creative["format_id"]).model_dump(mode="json")
        changed = changed or upgraded != creative["format_id"]
        result.append({**creative, "format_id": upgraded})
    return result, changed


def _normalize_tool_scoped(tool_name: str, result: dict[str, Any]) -> list[str]:
    """Apply the deprecated-field rewrites that only make sense for one tool.

    A rewrite belongs here when the field it renames exists on some tools and not others, so
    the rule has to consult ``tool_name`` -- ``media_buy_id`` is the pre-1.6 singular on
    get_media_buy_delivery and the spec field on update_media_buy, and applying it everywhere
    would corrupt the second. The top-level rules in the caller need no such test.

    Mutates ``result`` in place and returns the translations applied, matching
    ``_normalize_packages``.
    """
    translations: list[str] = []

    # campaign_ref → ext.buyer_campaign_ref (create_media_buy only)
    # AdCP 3.12 removed the top-level buyer_campaign_ref field from
    # create-media-buy-request; the migration path is the ext extension object.
    if "campaign_ref" in result:
        if tool_name == "create_media_buy":
            ext = result.get("ext")
            if ext is None:
                ext = {}
                result["ext"] = ext
            if isinstance(ext, dict) and "buyer_campaign_ref" not in ext:
                ext["buyer_campaign_ref"] = result["campaign_ref"]
                translations.append("campaign_ref → ext.buyer_campaign_ref")
        del result["campaign_ref"]

    # brand_manifest → brand (get_products, create_media_buy only)
    if "brand_manifest" in result:
        if tool_name in _BRAND_TOOLS and "brand" not in result:
            brand_ref = _translate_brand_manifest(result["brand_manifest"])
            if brand_ref is not None:
                result["brand"] = brand_ref
                translations.append("brand_manifest → brand")
        del result["brand_manifest"]

    # brand shorthand → BrandReference (get_products, create_media_buy only).
    # AFTER the brand_manifest translation above so a brand recovered from the
    # legacy field goes through the same funnel as an explicit one.
    if tool_name in _BRAND_TOOLS and result.get("brand") is not None:
        result["brand"], brand_normalized = _normalize_brand(result["brand"])
        if brand_normalized:
            translations.append("brand shorthand → BrandReference")

    # promoted_offerings → catalogs (get_products)
    if "promoted_offerings" in result:
        if "catalogs" not in result:
            result["catalogs"] = result["promoted_offerings"]
            translations.append("promoted_offerings → catalogs")
        del result["promoted_offerings"]

    # custom_targeting → targeting_overlay (create_media_buy)
    if "custom_targeting" in result:
        if tool_name == "create_media_buy" and "targeting_overlay" not in result:
            result["targeting_overlay"] = result["custom_targeting"]
            translations.append("custom_targeting → targeting_overlay")
        del result["custom_targeting"]

    # updates.packages → packages (update_media_buy)
    if "updates" in result:
        legacy_updates = result["updates"]
        if tool_name == "update_media_buy" and "packages" not in result and isinstance(legacy_updates, dict):
            if "packages" in legacy_updates:
                result["packages"] = legacy_updates["packages"]
                translations.append("updates.packages → packages")
        del result["updates"]

    # media_buy_id (singular) → media_buy_ids (get_media_buy_delivery). The plural is the
    # spec's shape since AdCP 1.6; the singular is the pre-1.6 spelling. Scoped to that one
    # tool because update_media_buy's media_buy_id IS the spec field.
    if tool_name == "get_media_buy_delivery" and "media_buy_id" in result:
        if "media_buy_ids" not in result:
            result["media_buy_ids"] = [result["media_buy_id"]]
            translations.append("media_buy_id → media_buy_ids")
        del result["media_buy_id"]

    # creatives[].format_id shorthand → FormatId (sync_creatives)
    if tool_name == "sync_creatives" and "creatives" in result:
        result["creatives"], format_ids_upgraded = _upgrade_creative_format_ids(result["creatives"])
        if format_ids_upgraded:
            translations.append("creatives[].format_id shorthand → FormatId")

    return translations


def normalize_request_params(
    tool_name: str,
    params: dict[str, Any],
) -> NormalizationResult:
    """Translate deprecated fields to current equivalents.

    Args:
        tool_name: The MCP/A2A tool name (e.g., "get_products", "create_media_buy").
        params: Raw request parameters dict.

    Returns:
        NormalizationResult with normalized params, inferred version, and
        list of translations applied.
    """
    result = dict(params)
    translations: list[str] = []

    # --- Version inference ---
    inferred = "2.5" if V25_SIGNALS & result.keys() else "3.0"

    # --- Top-level translations (all tools) ---

    # account_id (string) → account: {account_id: str}
    if "account_id" in result:
        if "account" not in result:
            result["account"] = {"account_id": result["account_id"]}
            translations.append("account_id → account")
        del result["account_id"]

    # --- Tool-scoped translations ---
    translations.extend(_normalize_tool_scoped(tool_name, result))

    # --- Package-level translations ---
    if "packages" in result and isinstance(result["packages"], list):
        result["packages"], pkg_translations = _normalize_packages(result["packages"])
        translations.extend(pkg_translations)

    if translations:
        logger.info(
            "Normalized %s request (v%s): %s",
            tool_name,
            inferred,
            ", ".join(translations),
        )

    return NormalizationResult(
        params=result,
        inferred_version=inferred,
        translations_applied=translations,
    )


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
