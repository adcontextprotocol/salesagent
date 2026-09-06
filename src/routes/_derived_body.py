"""Generate a REST request body from the DTO and the implementation's signature.

REST is the third place a request shape is written down, and until now it was written by
hand: a ``*Body`` class per route, maintained beside the DTO and the ``_impl`` signature it
is supposed to mirror. That is a drift vector with teeth -- a REST buyer can only send a
field the body declares, so a field missing here is not a validation error, it is a
parameter that silently does nothing. ``ListCreativesBody`` had no ``sort``, and a
spec-shaped REST payload sorted correctly on MCP and A2A and quietly did not on REST.

The body is now DERIVED from the same two artifacts the MCP announcement uses:

    fields = DTO.model_fields  INTERSECT  impl signature

so REST and MCP advertise the same set by construction, and ``e2e_rest`` -- which is real
HTTP against this route, with no schema of its own -- inherits it for free. A2A needs no
schema at all: it consumes the parameter bag wholesale through the request seam.

Version-envelope fields are added back explicitly. They are NOT request data -- the DTO
selection strips them by design -- but they are part of the announced request shape, so the
body must carry them. Naming them here separates envelope from payload, which the
hand-written classes did not.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from pydantic import BaseModel, create_model

from src.core.schema_helpers import accepted_kwargs, select_request_fields
from src.core.schemas._base import SalesAgentBaseModel
from src.core.tools._announced_shape import request_seam_for

#: Carried so the route can negotiate, never forwarded as request data.
_ENVELOPE_FIELDS: dict[str, tuple[Any, Any]] = {"adcp_version": (str | None, None)}


class DerivedBodyEnvelope(BaseModel):
    """Type-checker-visible mirror of ``_ENVELOPE_FIELDS``.

    ``derived_body_model`` builds its classes at runtime, so their names are variables and
    cannot be used as annotations. Route modules declare TYPE_CHECKING-only stand-ins that
    inherit this plus the DTO. Keep the two in step: a field added to ``_ENVELOPE_FIELDS``
    belongs here too, or the checker will not know the derived bodies carry it.
    """

    adcp_version: str | None = None


def _stamp_derivation(
    model: type[BaseModel],
    *,
    dto: type[BaseModel],
    impl: Callable[..., Any],
    extra_fields: frozenset[str],
    path_fields: frozenset[str],
) -> None:
    """Record on the generated class HOW it was derived, for the guards to grade.

    - ``__derived_from_dto__`` marks the body as DERIVED. The completeness guard asserts
      hand-written bodies do not LAG their raw wrapper; a derived body deliberately
      declares LESS -- it drops the wrapper's non-spec parameters, which is the point --
      so it is graded by the intersection rule instead.
    - ``__derived_extra_fields__`` / ``__derived_path_fields__`` are the two DELIBERATE
      departures from "DTO fields INTERSECT impl parameters", recorded so the guard can
      grade them rather than being widened to tolerate any difference. An undeclared
      extra field, or a silently dropped one, still fails.
    - ``__derived_callee__`` is the callee the field set was derived AGAINST, so the guard
      reads the pairing off the body instead of keeping a hand-maintained {Body: callee}
      list -- which goes stale the moment a wrapper's shape changes, exactly what happened
      when the wrappers moved from flat parameters to taking the built request.

    Stamped through one loop rather than four attribute assignments: mypy cannot know a
    ``create_model()`` class carries these names, and the four-assignment spelling needed
    four ``# type: ignore[attr-defined]`` -- four claims to audit, and four sites for the
    next mark to be added to inconsistently, instead of one function that owns the record.
    """
    for attribute, value in (
        ("__derived_from_dto__", (dto, impl)),
        ("__derived_extra_fields__", extra_fields),
        ("__derived_path_fields__", path_fields),
        ("__derived_callee__", impl),
    ):
        setattr(model, attribute, value)


def derived_body_model(
    name: str,
    dto: type[BaseModel],
    impl: Callable[..., Any],
    *,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
    path_fields: frozenset[str] = frozenset(),
) -> type[BaseModel]:
    """A request body carrying exactly ``DTO fields INTERSECT impl parameters``.

    ``extra_fields`` is for values the ROUTE needs that are not request data -- keep it
    empty unless a route genuinely reads something the DTO does not describe.

    ROUTES DO NOT CALL THIS. They call ``derived_body_model_for``, which reads the pair off
    the tool; passing a hand-written ``(dto, impl)`` is what that exists to remove. The
    explicit form remains because a TEST fixture has a model and a callee but no registered
    tool to read them from.
    """
    # ONE definition of "what the impl accepts", shared with the forwarding seam and the MCP
    # derivation, rather than a third independent signature read. It also gets the two cases a
    # bare `set(inspect.signature(impl).parameters)` got wrong: a **kwargs impl (which accepts
    # every field, not the literal name "kwargs") and a patched Mock (which accepts anything,
    # not nothing).
    accepted = accepted_kwargs(impl)
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, field in dto.model_fields.items():
        if accepted is not None and field_name not in accepted:
            continue  # declared by the spec, not implemented here -- so not accepted
        if field.exclude:
            # INTERNAL, exactly as on MCP (``derived_signature``). Without this the two
            # transports disagree about what an ``exclude=True`` field means: MCP would drop
            # it from the advertised shape while REST kept accepting it in the body, which is
            # the single-transport hole every derivation here exists to close.
            continue
        if field_name in path_fields:
            # Carried in the URL, so it is not a BODY field. Declaring it here would make a
            # REST caller send the same value twice -- and since requiredness is preserved,
            # a required path field would become a required body field, rejecting the
            # spec-legal request that puts it only in the path.
            continue
        # field.annotation is Optional[type] on the pydantic side: a field declared with no
        # annotation at all reads back None, which is not a type and cannot take `| None`.
        annotation: Any = Any if field.annotation is None else field.annotation
        if field.is_required():
            # REQUIREDNESS IS PART OF THE SHAPE. Every field used to be rewritten to
            # ``annotation | None`` with a None default, which made the REST body accept a
            # request omitting a field the schema lists in /required -- and then hand the
            # wrapper a None for it. The buyer got a rejection from somewhere deeper, or no
            # rejection at all, while mcp and a2a rejected the same request up front.
            fields[field_name] = (annotation, ...)
        else:
            fields[field_name] = (annotation if _is_optional(annotation) else annotation | None, None)

    fields.update(_ENVELOPE_FIELDS)
    fields.update(extra_fields or {})
    # create_model's overloads cannot express "a mapping of field name -> (type, default)"
    # splatted as keywords, so the precise dict type never matches one. The values are
    # already the (annotation, default) pairs it documents.
    model = create_model(name, __base__=SalesAgentBaseModel, **cast(dict[str, Any], fields))
    _stamp_derivation(
        model,
        dto=dto,
        impl=impl,
        extra_fields=frozenset(extra_fields or ()),
        path_fields=frozenset(path_fields),
    )
    return model


def derived_body_model_for(
    tool: Callable[..., Any],
    *,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
    path_fields: frozenset[str] = frozenset(),
) -> type[BaseModel]:
    """The REST body for ``tool``, with the DTO and the builder READ OFF THE TOOL.

    The route names the TOOL and nothing else. Every ``*Body`` used to name its DTO and its
    builder by hand -- thirteen routes each writing out a pair that ``request_seam_for``
    already answers -- and a hand-written pair is a place to name a different model or a
    different builder than the tool uses. That is not hypothetical: the pair moved once
    already, when the raw wrappers stopped taking flat parameters and started taking the
    built request, and every call site had to be edited to say "the BUILDER, not the raw
    wrapper". Read from the tool, there is nothing left at the call site to be wrong.

    The CLASS NAME is derived too, for the same reason: it is the tool's name in Pascal case
    plus ``Body``, so a renamed tool cannot leave a body advertising the old operation's name
    in the OpenAPI schema.

    ``extra_fields`` and ``path_fields`` stay explicit. They are the two things the tool does
    NOT know -- a value this ROUTE needs that is not request data, and which field this
    ROUTE carries in the URL -- so they are properties of the route, not of the tool, and
    ``derived_body_model`` already grades them as declared departures.
    """
    dto, builder = request_seam_for(tool)
    name = "".join(part.title() for part in tool.__name__.split("_")) + "Body"
    return derived_body_model(name, dto, builder, extra_fields=extra_fields, path_fields=path_fields)


def derived_payload(body: BaseModel, *, coerce: Mapping[str, Callable[[Any], Any]] | None = None) -> dict[str, Any]:
    """The request data ``body`` carries, selected by the derivation the body RECORDS.

    A derived body ALREADY is ``DTO fields INTERSECT impl parameters``, so a route that
    re-states that intersection is asserting a guarantee the generator made two hundred
    lines earlier. Seven routes did, each naming the DTO and the callee a second time --
    and a restatement is a place to disagree. Pass a different DTO, or read the callee
    from a module attribute a test has patched, and the route selects a SUBSET of what the
    body accepted; the buyer's field is bound by FastAPI, dropped here, and the request
    succeeds having done something other than what was asked. That is the same silent-no-op
    disease this module exists to remove from the body classes, one layer down.

    The pair is read from ``__derived_from_dto__``, which ``derived_body_model`` stamped at
    derivation time, so selection and declaration cannot disagree -- there is nothing left
    at the call site to disagree with.

    ``coerce`` maps a field name to the ``to_*`` converter that field needs, and exists so
    that a route needing conversions does not have to hand-list the FORWARDED SET to get
    them. Six routes did exactly that -- naming each field on its way to the builder
    because two or three of them wanted ``to_account_reference`` or ``to_context_object``
    -- and ``get_media_buy_delivery`` is what that costs: it named nine of the eleven
    fields its body declares and silently dropped ``include_window_breakdown`` and
    ``time_granularity``, which FastAPI accepted and the OpenAPI schema advertised.
    Separating the two concerns is the fix: the SET is derived, the
    CONVERSION is declared per field, and a field added to the DTO tomorrow is forwarded
    without anyone editing the route.

    A converter runs only for a key the selection actually produced. ``select_request_fields``
    has already dropped ``None`` values so the model's own defaults apply, and calling a
    ``to_*`` helper on an absent field would put an explicit ``None`` back -- reviving the
    defaulting bug ``_build_get_media_buy_delivery_request`` documents in its own body.
    """
    derivation = getattr(type(body), "__derived_from_dto__", None)
    if derivation is None:
        raise TypeError(
            f"{type(body).__name__} did not come from derived_body_model, so it records no "
            f"derivation to select by. A hand-written body must call select_request_fields "
            f"with the (DTO, callee) pair it is maintained against."
        )
    dto, impl = derivation
    # ATTRIBUTE VALUES, not ``model_dump()``. Handing ``select_request_fields`` the model
    # makes it dump, and a dump applies ``exclude=True`` all the way DOWN -- so a nested
    # field marked internal for SERIALIZATION is silently deleted from the buyer's REQUEST.
    # ``PackageRequest.creative_ids`` is exactly that: exclude=True to keep it out of
    # responses, and unmistakably buyer input on the way in. Dumping it away made
    # create_media_buy accept a package whose creative reference had ceased to exist, so
    # there was nothing left to reject -- including cross-principal references, which is a
    # SECURITY failure and is how this was found.
    #
    # Reading attributes keeps nested models TYPED, which is what the hand-written routes
    # passed before they were converted. ``select_request_fields`` treats a Mapping the same
    # way it treats a dumped model -- same name filter, same None-dropping -- so only the
    # nested loss goes away. The DTO's own top-level ``exclude=True`` fields are still
    # dropped, by the name filter, where that decision is deliberate.
    # ``getattr(..., None)``: a body built with ``model_construct`` (tests, and any caller
    # that skips validation) leaves unset fields with no attribute at all, and an unset
    # field is exactly what the selector drops next.
    values = {name: getattr(body, name, None) for name in type(body).model_fields}
    payload = select_request_fields(dto, values, accepted_kwargs(impl))
    for name, converter in (coerce or {}).items():
        if name in payload:
            payload[name] = converter(payload[name])
    return payload


def _is_optional(annotation: Any) -> bool:
    return type(None) in getattr(annotation, "__args__", ())
