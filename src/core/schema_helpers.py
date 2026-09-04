"""Helper functions for working with generated schemas.

This module provides convenience functions for constructing complex generated schemas
without losing type safety. Unlike adapters (which wrap schemas in dict[str, Any]),
these helpers work directly with the generated Pydantic models.

Philosophy:
- Generated schemas are the source of truth (always in sync with AdCP spec)
- Helpers make construction easier without sacrificing type safety
- Custom logic (validators, conversions) lives here, not in wrapper classes
"""

import inspect
import logging
from collections.abc import Collection, Mapping
from typing import Any
from urllib.parse import urlparse

# FIXME(#1388): GetProductsResponse, Product have local subclasses; import from src.core.schemas.
from adcp import CreativeFilters, GetProductsResponse, Product

# FIXME(#1388): ProductFilters has a local subclass; import from src.core.schemas.
from adcp.types import (
    AccountReference,
    BrandReference,
    ContextObject,
    ProductFilters,
    PropertyListReference,
    PushNotificationConfig,
    ReportingWebhook,
)
from pydantic import BaseModel, ValidationError

from src.core.errors.details import ValidationDetails
from src.core.exceptions import AdCPInvalidRequestError
from src.core.schemas.product import GetProductsRequest
from src.core.validation_helpers import adcp_validation_boundary

logger = logging.getLogger(__name__)


def _coerce_wire_object[ModelT: BaseModel](
    value: Any,
    model_cls: type[ModelT],
    context: str,
    field_prefix: str | None = None,
) -> ModelT | None:
    """Shared dict → typed-model coercion with the boundary BUILT IN.

    Single home for the ``to_*`` helpers' isinstance ladder. The internal
    ``adcp_validation_boundary`` means a malformed wire dict rejects as a
    typed ``AdCPValidationError`` (message + field + top-level suggestion)
    from EVERY call site — callers cannot forget the boundary
    (#1417; mirrors ``coerce_creative_filters``).

    Returns ``None`` for non-dict unexpected types, preserving the helpers'
    long-standing fallback behavior.
    """
    if value is None or isinstance(value, model_cls):
        return value
    if isinstance(value, dict):
        with adcp_validation_boundary(context=context, field_prefix=field_prefix):
            # model_validate handles plain models and RootModels alike
            # (AccountReference is a RootModel — field-unpacking would break it).
            return model_cls.model_validate(value)
    return None  # Fallback for unexpected types


def to_context_object(context: dict[str, Any] | ContextObject | None) -> ContextObject | None:
    """Convert dict context to ContextObject for adcp 2.12.0+ compatibility."""
    return _coerce_wire_object(context, ContextObject, "context value")


def to_reporting_webhook(webhook: dict[str, Any] | ReportingWebhook | None) -> ReportingWebhook | None:
    """Convert dict to ReportingWebhook for adcp type compatibility."""
    return _coerce_wire_object(webhook, ReportingWebhook, "reporting_webhook value")


def to_push_notification_config(
    config: dict[str, Any] | PushNotificationConfig | None,
    *,
    field_prefix: str = "push_notification_config",
) -> PushNotificationConfig | None:
    """Convert dict to PushNotificationConfig for adcp type compatibility.

    ``field_prefix`` defaults HERE rather than at the call sites: five callers
    each remembering the same string literal is the remembered-call shape this
    epic exists to delete, and the sixth caller is where the divergence comes
    back. A refusal from this funnel therefore names
    ``push_notification_config.authentication.credentials`` — the path into the
    document the buyer actually sent — which is what FastMCP already emits (it
    validates the whole argument model, so its pydantic loc carries the parameter
    name) and what the registration gate raises. This converges REST and A2A onto
    the spelling MCP and the ingest gate already use; it is not a third one.

    Scope note: the broader prefix inconsistency across every field this
    validator reports is gh-#1895 and stays open — this narrows exactly one
    helper's one field.
    """
    return _coerce_wire_object(
        config,
        PushNotificationConfig,
        "push_notification_config value",
        field_prefix=field_prefix,
    )


def require_push_notification_config(
    config: dict[str, Any] | PushNotificationConfig,
    *,
    field_prefix: str = "push_notification_config",
) -> PushNotificationConfig:
    """:func:`to_push_notification_config` for a caller that HAS a config.

    Same funnel, same refusals, same field paths -- the only difference is that
    ``None`` is not in the domain, so the result is not ``| None`` and a caller
    has nothing to narrow.

    The optional version exists because some callers legitimately hold "maybe a
    config"; the trouble was that callers who did NOT then had to prove the
    absence away, and two of them did it with a bare ``assert``. Under
    ``python -O`` an assert is deleted, so a function annotated as never
    returning ``None`` returned it. Stating the requirement in the SIGNATURE is
    what removes the narrowing rather than making it survive an interpreter
    flag.
    """
    coerced = to_push_notification_config(config, field_prefix=field_prefix)
    if coerced is None:
        # Unreachable via the annotated domain; a runtime guard rather than an
        # assert so it cannot be optimised away, and so a caller that passed
        # ``None`` through an ``Any`` gets a named failure instead of one
        # deferred to whatever first dereferences the result.
        raise ValueError(f"{field_prefix} is required but resolved to None")
    return coerced


def is_url_shorthand(value: str) -> bool:
    """Return True when a string looks like a URL (scheme or protocol-relative)."""
    return "://" in value or value.startswith("//")


def brand_shorthand_to_domain(value: str) -> str:
    """Normalize AdCP v3 brand string shorthand to a domain hostname.

    Storyboard runners may send ``https://test.example``; ``BrandReference.domain``
    expects a hostname (no scheme/path) per the adcp library pattern.

    Returns empty string when a URL-shaped value cannot be parsed into a hostname
    (malformed IPv6, etc.) so legacy ``brand_manifest`` middleware can silently
    strip the field. Callers on the explicit ``brand`` path must use
    ``to_brand_reference`` / ``_coerce_domain_or_raise`` instead — those raise
    ``AdCPInvalidRequestError(field="brand")`` rather than dropping the brand.
    """
    value = value.strip()
    if not value:
        return value
    if is_url_shorthand(value):
        try:
            parsed = urlparse(value if "://" in value else f"https:{value}")
        except ValueError:
            return ""
        if parsed.hostname:
            return parsed.hostname.lower()
        return ""
    return value.lower()


def _coerce_domain_or_raise(raw: str) -> str:
    """Normalize brand shorthand and validate against BrandReference.domain pattern.

    Used for explicit ``brand`` on tool boundaries — malformed input must surface
    as ``INVALID_REQUEST / field="brand"``, not be coerced to missing brand
    (which would mis-route ``require_brand`` policy to an authorization error).

    INVALID_REQUEST, not VALIDATION_ERROR. Both failures below are the domain
    failing ``BrandReference.domain``'s lowercase-hostname PATTERN — a path, an
    underscore, an IDN host, an unparseable URL. The pinned enum
    (adcp 6.6.0, _schemas/3.1/enums/error-code.json) splits these on exactly that
    axis: INVALID_REQUEST is "malformed, missing required fields, or violates
    schema constraints"; VALIDATION_ERROR is "invalid field values or violates
    business rules BEYOND schema validation". A pattern is a schema constraint,
    so this is the first. VALIDATION_ERROR stays correct for the other kind — a
    well-formed value that does not resolve (an unknown format id) or that a
    seller policy refuses.

    Raises:
        AdCPInvalidRequestError: when the value cannot be normalized to a valid
            hostname (empty parse, path/underscore/IDN/pattern mismatch). Always
            tagged ``field="brand"`` so wire envelopes name the request field.
    """
    domain = brand_shorthand_to_domain(raw)
    if not domain:
        raise AdCPInvalidRequestError(
            details=ValidationDetails(rejected_value=str(raw)),
            field="brand",
        )
    try:
        BrandReference(domain=domain)
    except ValidationError as e:
        raise AdCPInvalidRequestError(
            details=ValidationDetails(rejected_value=domain),
            field="brand",
        ) from e
    return domain


def to_brand_reference(brand: dict[str, Any] | BrandReference | str | None) -> BrandReference | None:
    """Convert dict/string brand to BrandReference for adcp 3.6.0 compatibility.

    String and dict ``domain`` values share one normalize-then-validate funnel so
    ``"ACME.COM"`` / ``{"domain":"ACME.COM"}`` / URL-in-domain are equivalent.

    Args:
        brand: Brand as dict, string domain shorthand, BrandReference, or None

    Returns:
        BrandReference or None

    Raises:
        AdCPInvalidRequestError: when an explicit brand cannot be coerced to a
            valid ``BrandReference`` (tagged ``field="brand"``). See
            ``_coerce_domain_or_raise`` for why this is INVALID_REQUEST and not
            VALIDATION_ERROR.
    """
    if brand is None:
        return None
    if isinstance(brand, BrandReference):
        return brand
    # Raise-capable coercion routes through the internal boundary (like
    # ``coerce_creative_filters``/``_coerce_wire_object``) so a malformed brand
    # rejects as a typed error with field + top-level suggestion from every call
    # site — no hand-rolled ValidationError translation (#1417). The boundary
    # only remaps pydantic ValidationError (which ``adcp_error_for`` already
    # grades INVALID_REQUEST, same schema-constraint reasoning); the explicit
    # raises below are typed already and pass through it untouched.
    with adcp_validation_boundary(context="brand", field="brand"):
        if isinstance(brand, str):
            return BrandReference(domain=_coerce_domain_or_raise(brand))
        if isinstance(brand, dict):
            domain_raw = brand.get("domain")
            if not isinstance(domain_raw, str):
                # Wrong JSON type for a declared string field — a schema
                # constraint, so INVALID_REQUEST like the pattern failures.
                raise AdCPInvalidRequestError(
                    field="brand",
                )
            allowed = BrandReference.model_fields.keys()
            ref_data = {key: value for key, value in brand.items() if key in allowed}
            ref_data["domain"] = _coerce_domain_or_raise(domain_raw)
            return BrandReference(**ref_data)
        # brand is neither a string, a dict, nor a BrandReference — again a type
        # violation of the declared shape, not a refused value.
        raise AdCPInvalidRequestError(
            details=ValidationDetails(received_type=type(brand).__name__),
            field="brand",
        )


def to_account_reference(account: dict[str, Any] | AccountReference | None) -> AccountReference | None:
    """Convert dict to AccountReference for adcp compatibility."""
    return _coerce_wire_object(account, AccountReference, "account value")


def to_property_list_reference(
    property_list: dict[str, Any] | PropertyListReference | None,
) -> PropertyListReference | None:
    """Convert dict to PropertyListReference for adcp compatibility."""
    return _coerce_wire_object(property_list, PropertyListReference, "property_list value")


def coerce_creative_filters(filters: dict[str, Any] | CreativeFilters | None) -> CreativeFilters | None:
    """Coerce a raw list_creatives filters value into a typed CreativeFilters.

    Single source of truth for the dict -> CreativeFilters boundary so REST and
    A2A coerce identically (the MCP transport coerces via FastMCP's TypeAdapter on
    the tool signature).

    A malformed filter (e.g. ``concept_ids`` with an empty array, violating the
    schema's ``minItems: 1``) is raised as a *typed* ``AdCPValidationError`` carrying
    a recovery suggestion, so every transport surfaces the spec's two-layer
    ``VALIDATION_ERROR`` envelope (with a suggestion, per POST-F3). Constructing the
    model directly instead (as the ``to_*`` converters above do, via ``Model(**dict)``)
    surfaces a raw pydantic ``ValidationError`` that ``adcp_error_for``
    flattens into a suggestion-less envelope.

    Args:
        filters: Filters as a wire dict, an already-typed CreativeFilters, or None.

    Returns:
        CreativeFilters or None (when no filter was supplied).

    Raises:
        AdCPValidationError: when ``filters`` is a dict that fails CreativeFilters validation.
    """
    if filters is None or isinstance(filters, CreativeFilters):
        return filters
    return CreativeFilters.model_validate(filters)


def create_get_products_request(
    brief: str = "",
    brand: dict[str, Any] | BrandReference | str | None = None,
    filters: dict[str, Any] | ProductFilters | None = None,
    property_list: dict[str, Any] | PropertyListReference | None = None,
    context: dict[str, Any] | ContextObject | None = None,
) -> GetProductsRequest:
    """Create GetProductsRequest aligned with adcp v3.6.0 spec.

    Args:
        brief: Natural language description of campaign requirements
        brand: Brand reference per adcp 3.6.0 (BrandReference or dict with domain field).
               Example: BrandReference(domain="acme.com") or {"domain": "acme.com"}
        filters: Structured filters for product discovery (dict or ProductFilters)
        property_list: Property list reference for filtering by buyer's property list
        context: Application-level context (dict or ContextObject)

    Returns:
        GetProductsRequest

    Examples:
        >>> req = create_get_products_request(
        ...     brand=BrandReference(domain="acme.com"),
        ...     brief="Display ads"
        ... )
    """
    # Handle filters - can be dict, ProductFilters, or None
    filters_obj: ProductFilters | None = None
    if filters is not None:
        if isinstance(filters, ProductFilters):
            filters_obj = filters
        elif isinstance(filters, dict):
            filters_obj = ProductFilters(**filters)

    return GetProductsRequest(  # type: ignore[call-arg]
        brand=to_brand_reference(brand),
        brief=brief or None,
        filters=filters_obj,
        property_list=to_property_list_reference(property_list),
        context=to_context_object(context),
    )


# Re-export commonly used generated types for convenience


def accepted_kwargs(callee: Any) -> frozenset[str] | None:
    """The keyword names ``callee`` accepts, or ``None`` when it accepts any.

    The INTERSECT half of the rule, expressed ONCE. It used to be re-derived at every
    forwarding site in four different spellings -- import-time frozensets, call-time
    ``inspect.signature(...).parameters``, and simply omitted -- which is how the rule came
    to be enforced at some boundaries and not others.

    ``None`` means UNBOUNDED, and it is a real answer rather than a failure: a callee
    declaring ``**kwargs`` genuinely accepts every keyword, so the intersection is the
    identity and the DTO alone decides.

    That semantics also dissolves a hazard that used to need per-site mitigation. Tests patch
    transport-module attributes with ``Mock``s, whose signature is ``(*args, **kwargs)``.
    Read as a NAME LIST that is the empty set, so a call-time read silently dropped every
    field the buyer sent -- the two import-time frozensets existed only to dodge that, and
    only two of the four signature-reading sites had them. Read as ``**kwargs``, a Mock
    correctly reports "accepts anything", so timing stops mattering and the frozensets are
    unnecessary. The hazard was a property of the RULE, so the cure belongs with the rule.
    """
    try:
        parameters = inspect.signature(callee).parameters
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return None
    return frozenset(
        name
        for name, p in parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    )


def select_request_fields(
    model: type[BaseModel],
    source: BaseModel | Mapping[str, Any],
    accepted: "Collection[str] | None",
) -> dict[str, Any]:
    """The DTO's fields, out of a transport's raw bag, narrowed to what the callee accepts.

    ONE rule, everywhere: the request DTO is the vocabulary, and ``accepted`` (the callee's
    parameter names, when it takes fewer) removes what is declared but NOT IMPLEMENTED. So
    the set a transport forwards is ``DTO fields INTERSECT _impl arguments`` -- which is the
    same set the MCP tool advertises (see ``tools/_announced_shape.py``). Announcement and
    acceptance cannot drift because they are computed from the same two artifacts.

    Two consequences worth stating, because both replaced earlier machinery:

    * There is no plumbing denylist. ``ctx``/``identity``/``self``/``req`` are not DTO
      fields, so buyer input can never be selected into them. A previous signature-keyed
      selector needed an explicit denylist precisely because it keyed off the wrong
      artifact; keying off the DTO makes the exclusion structural.
    * A key the DTO does not declare is simply not forwarded -- no allowlist, no ledger.
      Non-spec input stops at the boundary instead of being quietly honoured.

    ``accepted`` is REQUIRED, and deliberately has no default. It defaulted to ``None`` once,
    which made the UNNARROWED form the easiest to write and left seven of ten sites silently
    taking it -- forwarding fields the callee had no parameter for, whose only outcome is a
    ``TypeError`` on a spec-conformant payload. Pass ``accepted_kwargs(callee)``; it returns
    ``None`` for a genuinely unbounded callee, so the unnarrowed case is still expressible but
    must now be DERIVED rather than defaulted into. This mirrors ``_register_tool``, which
    refuses to register a tool whose DTO cannot be resolved instead of falling back quietly.

    The version envelope flows like any other field. Every DTO inherits it from the SDK
    request model, so ``adcp_version`` and ``adcp_major_version`` are ordinary declared
    fields rather than something the boundary negotiates away.
    ``None`` values are dropped so the model's own defaults apply.
    """
    values = source.model_dump(exclude_none=True) if isinstance(source, BaseModel) else source
    names = set(model.model_fields)
    # INTERNAL fields are not buyer input. ``exclude=True`` is how this codebase says "never
    # reaches a buyer", and the other two derivations of the same rule already honour it:
    # ``derived_signature`` drops such a field from the MCP announcement and
    # ``derived_body_model`` from the REST body. This was the third derivation and the only
    # one that did not, so an internal field a builder happened to accept was settable over
    # A2A alone -- one transport quietly wider than the other two, which is the exact
    # single-transport hole these derivations exist to close.
    names -= {name for name, field in model.model_fields.items() if field.exclude}
    if accepted is not None:
        names &= set(accepted)
    selected = {name: value for name, value in values.items() if name in names and value is not None}

    # Say what we did not carry. Dropping is the right BEHAVIOUR -- production runs
    # extra="ignore" so a buyer on a newer spec version is tolerated rather than refused
    # (critical pattern #7) -- but doing it in silence is not: a filter the buyer asked for
    # that is quietly not applied returns 200 OK having done something other than what was
    # asked. Measured instance: list_creatives with the retired flat `status` answered
    # VALIDATION_ERROR on MCP and 200-with-the-filter-ignored on A2A and REST.
    #
    # This does not close the transport divergence itself (MCP's refusal is structural --
    # FastMCP cannot accept a keyword the tool never advertised), only the silence on the
    # other two. See salesagent-prkv.26.
    dropped = sorted(k for k in values if k not in names)
    if dropped:
        logger.info(
            "%s: ignoring %d field(s) it does not define: %s",
            model.__name__,
            len(dropped),
            ", ".join(dropped),
        )
    return selected


__all__ = [
    "accepted_kwargs",
    "is_url_shorthand",
    "brand_shorthand_to_domain",
    "to_account_reference",
    "to_brand_reference",
    "to_context_object",
    "to_property_list_reference",
    "require_push_notification_config",
    "to_push_notification_config",
    "to_reporting_webhook",
    "coerce_creative_filters",
    "create_get_products_request",
    "select_request_fields",
    # Re-export types for type hints
    "BrandReference",
    "CreativeFilters",
    "GetProductsRequest",
    "GetProductsResponse",
    "Product",
    "ContextObject",
    "ReportingWebhook",
]
