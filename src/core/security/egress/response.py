"""The closed outbound-response shape every egress-seam consumer reads.

Before this: ``OutboundResult`` held a ``response: httpx.Response`` field
alongside a private ``_body: bytes`` -- the body bytes were already captured
but never surfaced, so the TID251 raw-egress import ban was satisfied while
four call sites still reached through ``OutboundResult.response`` to program
directly against ``httpx.Response`` (triage F8/R5). The seam had to poke
``response._content = body`` (``_attach_body``, a private-attribute write on
a third-party object) purely to keep that reach-through's ``.text``/``.json()``
working on a streamed-then-closed body. Closing the type over
``http_status``/``headers``/``content``/``attempts``/``duration_seconds`` is
what makes "a caller holding an httpx type" unconstructible; nothing here
imports httpx at all.

``text`` replicates ``httpx.Response.text``'s decode rule -- Content-Type
header's charset param, if Python knows the codec, else UTF-8, decoded with
``errors="replace"`` -- using the SAME stdlib primitives httpx itself uses
(``email.message.Message.get_content_charset``, ``codecs.lookup``) rather than
importing httpx's own private ``_parse_content_type_charset``/
``_is_known_encoding``. Verified against the installed httpx source
(``httpx/_models.py``, ``httpx/_decoders.py``): httpx's ``TextDecoder`` is
``codecs.getincrementaldecoder(encoding)(errors="replace")``, which for a
single already-complete chunk (as ``content`` always is here -- the seam has
already accumulated the full streamed body before building this type) is
exactly ``content.decode(encoding, errors="replace")``.
"""

from __future__ import annotations

import codecs
import email.message
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _text_encoding(headers: Mapping[str, str]) -> str:
    """The encoding ``httpx.Response.text`` would pick, replicated stdlib-only.

    Priority: the Content-Type header's ``charset`` parameter, if it names a
    codec ``codecs.lookup`` actually knows; ``"utf-8"`` otherwise. Both steps
    mirror httpx's own (already stdlib-only) implementation exactly, so the
    two real consumers that read ``.text`` (``triton_digital.py``,
    ``creative_agent_registry.py``) see byte-identical decoding to what they
    got through ``response.text`` before this type closed.
    """
    content_type = headers.get("content-type")
    encoding: str | None = None
    if content_type is not None:
        msg = email.message.Message()
        msg["content-type"] = content_type
        encoding = msg.get_content_charset(failobj=None)
    if encoding is not None:
        try:
            codecs.lookup(encoding)
        except LookupError:
            encoding = None
    return encoding or "utf-8"


@dataclass(frozen=True)
class OutboundResult:
    """A delivered response, plus what it cost to get it. No httpx type anywhere.

    ``http_status`` is the ONE name this seam gives an HTTP status. It used to
    carry a different one on each of the three types that pass it along, with a
    rename hop at every junction; the field is spelled identically on
    :class:`~src.core.security.egress.policy.OutboundError` and on
    ``WebhookDeliveryOutcome`` so nothing has to be renamed in transit. It is
    deliberately NOT httpx's own spelling: the seam adopting its own vocabulary
    is the same move as not returning httpx's types.

    Two hops survive, both at a boundary that owns a pre-existing external name
    and maps to it exactly once — the buyer-visible ``details`` key, in
    ``OutboundDeliveryFailed.__init__``, and the
    ``WebhookDeliveryLog.http_status_code`` column, at the delivery repository.
    """

    http_status: int
    headers: Mapping[str, str]
    content: bytes
    attempts: int
    duration_seconds: float

    @property
    def text(self) -> str:
        if not self.content:
            return ""
        return self.content.decode(_text_encoding(self.headers), errors="replace")

    def json(self) -> Any:
        """Decode the body as JSON.

        Raises ``json.JSONDecodeError`` on a non-JSON body. That is
        deliberately *outside* the ``except OutboundError`` contract: a body
        that does not parse is the call site's business, not a transport
        failure.
        """
        return json.loads(self.content)
