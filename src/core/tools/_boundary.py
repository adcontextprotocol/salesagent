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
payload replays it verbatim, different payload is IDEMPOTENCY_CONFLICT. The digest is
``canonical_request_hash``, which strips the spec's closed exclusion list
(``idempotency_key``, ``context``, ``governance_context``), so a key never hashes itself and
two requests differing only in field order are the same request.

Errors are never saved. Most implementations raise, and a raise never reaches the save --
but ``create_media_buy`` RETURNS a failure for an adapter rejection, so the save also checks
the protocol status the response carries.

Idempotency is scoped to (agent, account, key) per the spec, with no tool dimension.
"""

from __future__ import annotations

import inspect
import logging
import typing
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from src.core.idempotency_canonical import canonical_request_hash
from src.core.idempotency_replay import cache_success, lookup_cached_replay, maybe_evict_expired
from src.core.resolved_identity import ResolvedIdentity

logger = logging.getLogger(__name__)


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


def _is_task_envelope(model: type[BaseModel]) -> bool:
    """Whether this response model wraps a domain response in a protocol status.

    ``CreateMediaBuyResult`` and its siblings declare ``status`` beside ``response``; a plain
    response like ``SyncCreativesResponse`` declares neither. The distinction decides what
    goes INTO the cache and what comes back out, and it is read off the model so the two
    directions cannot disagree.

    A class that is not a Pydantic model declares no fields and so is not an envelope. That
    is not only a type guard: this runs on the success path of every keyed request, so a
    raise here would lose the answer to work that already happened.
    """
    return (
        isinstance(model, type) and issubclass(model, BaseModel) and {"status", "response"} <= set(model.model_fields)
    )


def _cacheable_body(result: Any) -> Any:
    """The part of ``result`` the cache stores: the domain response, never the wrapper.

    ``IdempotencyAttemptRepository.record_success`` documents the stored shape as
    ``{"status": <protocol task status>, "response": <model dump>}`` -- the protocol status
    beside the domain response, because a pending buy's ``submitted`` is not a valid DOMAIN
    status and cannot ride inside the payload. Handing it the wrapper instead would store the
    status twice, in two vocabularies.
    """
    return result.response if _is_task_envelope(type(result)) else result


def _deserializer_for(impl: Callable[..., Any]) -> Callable[[dict[str, Any]], Any | None]:
    """Turn a stored envelope back into a typed response, or None if it no longer validates.

    The exact inverse of :func:`_cacheable_body`: a task envelope is rebuilt from the stored
    protocol status plus the stored domain response; a plain response is the stored response.

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
            if _is_task_envelope(model):
                result = model.model_validate({"status": envelope["status"], "response": envelope["response"]})
            else:
                result = model.model_validate(envelope["response"])
        except Exception:
            logger.warning("Cached %s envelope failed validation — treating as a miss", model.__name__, exc_info=True)
            return None
        if "replayed" in model.model_fields:
            # setattr, not attribute assignment: which model this is, is a per-row fact, so
            # no statically-known type declares the field.
            setattr(result, "replayed", True)  # noqa: B010
        return result

    return deserialize


#: Protocol task statuses that mean the work did NOT succeed, from the pinned
#: ``GeneratedTaskStatus`` enum. An ALLOWLIST of cacheable statuses would be the safer shape
#: if the enum's membership were the only risk, but it is not: a status the spec adds later
#: is far more likely to be another non-terminal or another failure than a new success, and
#: an allowlist would silently stop caching it. Naming the failures makes the omission loud.
_FAILED_STATUSES: frozenset[str] = frozenset({"failed", "rejected", "canceled", "unknown"})


def _is_error_result(result: Any) -> bool:
    """Whether this response reports that the work did not succeed.

    AdCP security.mdx#idempotency rule 3: an error is never cached, so a retry after one
    re-executes rather than replaying the failure forever. An implementation that RAISES
    never reaches the save, which covers most of them -- but ``create_media_buy`` returns a
    ``CreateMediaBuyResult`` carrying ``status="failed"`` for an adapter rejection, and that
    is a returned error, not a success.

    Read off the protocol status the envelope already carries. A response with no ``status``
    is not a task envelope at all and cannot report failure this way; if its work failed, it
    raised.
    """
    return getattr(result, "status", None) in _FAILED_STATUSES


async def _run(impl: Callable[..., Any], /, **kwargs: Any) -> Any:
    """Call an implementation, awaiting it only if it is a coroutine function.

    Six of the fourteen are plain ``def``.
    """
    result = impl(**kwargs)
    return await result if inspect.isawaitable(result) else result


def _keyed_scope(req: Any, identity: ResolvedIdentity | None) -> tuple[str, str, str | None, str] | None:
    """``(tenant_id, principal_id, account_id, idempotency_key)`` when this request is cacheable.

    None whenever any part is absent: a request whose schema declares no key, one carrying
    none, or an identity that resolved no tenant or principal, has no (agent, account, key)
    scope to be cached under. A DTO that declares no ``idempotency_key`` cannot carry one --
    every request model is the pinned schema and nothing else.
    """
    key = getattr(req, "idempotency_key", None)
    if not key or identity is None:
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
    if _is_error_result(result):
        return result

    cache_success(
        tenant_id=tenant_id,
        principal_id=principal_id,
        account_id=account_id,
        tool_name=tool_name,
        idempotency_key=key,
        response_model=_cacheable_body(result),
        # The result's OWN protocol status, not a constant. A create awaiting human approval
        # is ``submitted``, and storing it as completed would make the replay reconstruct the
        # wrong response variant -- the buyer would see a success where the original answer
        # was a pending task. A response with no status is not a task envelope; it succeeded
        # by having returned at all.
        protocol_status=getattr(result, "status", None) or "completed",
        payload_hash=request_hash,
    )
    maybe_evict_expired(tenant_id)
    return result
