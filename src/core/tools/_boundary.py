"""The one path from a validated request to a response.

Every transport enters here. MCP, A2A and REST differ in how a request ARRIVES and how a
response is written back; between those two points there is one sequence, and this is it:
resolve the account the request names, honour the idempotency key it carries, run the
implementation.

## Why these two things live here and not in an implementation

Both are properties of the REQUEST rather than of the work. ``account`` names whose
inventory the caller is acting on; ``idempotency_key`` says "if you have already done this,
do not do it again". Neither is a step in creating a media buy or syncing a creative, and an
implementation that performs them has to be TOLD it is being called by a buyer -- which is
how the previous arrangement went wrong in three ways at once:

* ``request_hash`` was computed by each transport and threaded down. The generated MCP
  registration calls the implementation directly, so it stopped computing one, and replay
  silently disabled itself on that transport. A value every caller must remember to supply
  is a value some caller will forget.
* the hash was taken over raw wire bytes when a transport threaded them and over the model
  otherwise, making "the same request" a per-transport answer.
* an in-process call -- ``create_media_buy`` uploading its inline creatives through
  ``_sync_creatives_impl`` -- inherited the outer request's key and had to be kept out of
  the cache by withholding the hash. Nothing internal passes through here, so that whole
  category is gone rather than guarded.

## The idempotency rule, entire

Save a non-error response that carried a key. On a later request with the same key: same
payload replays it verbatim, different payload is IDEMPOTENCY_CONFLICT. Errors are never
saved, which needs no enforcement here -- an implementation that raises never reaches the
save. The digest is ``canonical_request_hash``, which strips the spec's closed exclusion
list (``idempotency_key``, ``context``, ``governance_context``), so a key never hashes
itself and two requests differing only in field order are the same request.

Idempotency is scoped to (agent, account, key) per the spec, with no tool dimension.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from src.core.idempotency_canonical import canonical_request_hash
from src.core.idempotency_replay import cache_success, lookup_cached_replay, maybe_evict_expired
from src.core.resolved_identity import ResolvedIdentity
from src.core.tools._announced_shape import sdk_grounding


def _response_model_for(impl: Callable[..., Any]) -> type[BaseModel] | None:
    """The model an implementation returns, read off its annotation.

    Derived rather than declared: a registry row says which DTO a tool ACCEPTS, and the
    implementation's own signature already says what it returns. Storing the response type
    a second time would be a second declaration that can disagree with the function.

    ``None`` when the callable has no readable annotations, rather than a raise: the only
    consequence is that a cached envelope cannot be revived, so the request executes fresh --
    the same degradation a stale envelope already gets. Raising here would turn a callable
    ``get_type_hints`` cannot read into a failed request.
    """
    try:
        hints = typing.get_type_hints(impl)
    except Exception:
        return None
    annotation = hints.get("return")
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _deserializer_for(impl: Callable[..., Any]) -> Callable[[dict[str, Any]], Any | None]:
    """Turn a stored envelope back into a typed response, or None if it no longer validates.

    None means "treat as a miss": a stored envelope that stopped validating -- because the
    response model changed between the deploy that wrote it and the one replaying it, inside
    the TTL window -- must fall through to fresh execution rather than fail a request.

    A model that declares the spec's ``replayed`` marker gets it set here, which is the only
    place that can: the marker says "you are seeing a stored answer", so it is a property of
    the REPLAY and never of the stored body. Read off the model rather than listed per tool.
    """
    model = _response_model_for(impl)

    def deserialize(envelope: dict[str, Any]) -> Any | None:
        if model is None:
            return None
        try:
            result = model.model_validate(envelope)
        except Exception:
            return None
        if "replayed" in model.model_fields:
            # setattr, not attribute assignment: which model this is, is a per-row fact, so
            # no statically-known type declares the field.
            setattr(result, "replayed", True)  # noqa: B010
        return result

    return deserialize


async def _run(impl: Callable[..., Any], /, **kwargs: Any) -> Any:
    """Call an implementation, awaiting it only if it is a coroutine function.

    Six of the fourteen are plain ``def``.
    """
    result = impl(**kwargs)
    return await result if inspect.isawaitable(result) else result


def _spec_declares_idempotency_key(model: type[BaseModel]) -> bool:
    """Whether the PINNED SCHEMA gives this tool an idempotency key, not merely our DTO.

    The distinction is real and this repo has an instance of it: ``ListAccountsRequest``
    declares ``idempotency_key`` while ``account/list-accounts-request.json`` does not -- a
    temporary field kept so a BDD scenario stays constructible, documented as "not a spec
    field" at its declaration. A read has no at-most-once guarantee for a key to carry, so
    honouring that field would turn every ``list_accounts`` call into a cache write.

    Answered by asking the SDK ancestor the DTO inherits its vocabulary from, so a field we
    added ourselves cannot enrol a tool in idempotency. ``sync_accounts`` is the contrast:
    its parent declares the key because a sync mutates.
    """
    parent = sdk_grounding(model)
    return parent is not None and "idempotency_key" in parent.model_fields


def _keyed_scope(req: Any, identity: ResolvedIdentity | None) -> tuple[str, str, str | None, str] | None:
    """``(tenant_id, principal_id, account_id, idempotency_key)`` when this request is cacheable.

    None whenever any part is absent: a request the spec gives no key, a request carrying
    none, or an identity that resolved no tenant or principal, has no (agent, account, key)
    scope to be cached under.
    """
    key = getattr(req, "idempotency_key", None)
    if not key or identity is None:
        return None
    if not _spec_declares_idempotency_key(type(req)):
        return None
    if identity.tenant_id is None or identity.principal_id is None:
        return None
    return identity.tenant_id, identity.principal_id, identity.account_id, key


async def invoke_tool(tool_name: str, req: Any, identity: Any = None, **extra: Any) -> Any:
    """Run the registry's tool named ``tool_name``.

    The form every transport calls. A transport names the TOOL and hands over the request it
    validated; which function runs is the registry's answer, not the caller's, so no transport
    can reach a different implementation than the others.
    """
    from src.core.tools.registry import TOOLS

    return await invoke(tool_name, TOOLS[tool_name].impl, req, identity, **extra)


async def invoke(tool_name: str, impl: Callable[..., Any], req: Any, identity: Any = None, **extra: Any) -> Any:
    """Run ``tool_name`` for a request that arrived over a transport.

    ``extra`` carries anything a particular implementation declares beyond req/identity
    (``context_id``), forwarded untouched.
    """
    account = getattr(req, "account", None)
    if account is not None and identity is not None:
        from src.core.transport_helpers import enrich_identity_with_account

        identity = enrich_identity_with_account(identity, account)

    scope = _keyed_scope(req, identity)
    if scope is None:
        return await _run(impl, req=req, identity=identity, **extra)

    tenant_id, principal_id, account_id, key = scope
    request_hash = canonical_request_hash(req)

    replay = lookup_cached_replay(
        tenant_id=tenant_id,
        principal_id=principal_id,
        account_id=account_id,
        idempotency_key=key,
        request_hash=request_hash,
        deserialize=_deserializer_for(impl),
    )
    if replay is not None:
        return replay

    result = await _run(impl, req=req, identity=identity, **extra)

    cache_success(
        tenant_id=tenant_id,
        principal_id=principal_id,
        account_id=account_id,
        tool_name=tool_name,
        idempotency_key=key,
        response_model=result,
        protocol_status="completed",
        payload_hash=request_hash,
    )
    maybe_evict_expired(tenant_id)
    return result
