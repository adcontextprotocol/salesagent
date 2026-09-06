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

# FIXME(#1388): GetProductsResponse, Product have local subclasses; import from src.core.schemas.
from adcp import CreativeFilters, GetProductsResponse, Product

# FIXME(#1388): ProductFilters has a local subclass; import from src.core.schemas.
from adcp.types import (
    BrandReference,
    ContextObject,
    PushNotificationConfig,
    ReportingWebhook,
)
from pydantic import BaseModel

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

    Returns ``None`` for non-dict unexpected types. That fallback is why the ``to_*``
    coercion helpers are gone: on A2A it turned a request naming an account the pinned
    ``core/account-ref.json`` does not permit into a request with NO account scope --
    no authorization against that account, and a different idempotency scope -- where
    MCP and REST raised on the same bytes. The one surviving caller,
    ``to_push_notification_config``, is reached through
    ``require_push_notification_config``, which raises on a missing config rather than
    proceeding without one.
    """
    if value is None or isinstance(value, model_cls):
        return value
    if isinstance(value, dict):
        with adcp_validation_boundary(context=context, field_prefix=field_prefix):
            # model_validate handles plain models and RootModels alike
            # (AccountReference is a RootModel — field-unpacking would break it).
            return model_cls.model_validate(value)
    return None  # Fallback for unexpected types


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
    "require_push_notification_config",
    "to_push_notification_config",
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
