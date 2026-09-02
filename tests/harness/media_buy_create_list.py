"""MediaBuyCreateListEnv — composite env for the post-create get_media_buys poll.

The UC-019 storyboard scenario polls get_media_buys for a buy the SAME scenario
just created, so it needs both tools in one environment and one identity. That is
what the graded storyboard step does too: AdCP 3.1.1
``dist/compliance/3.1.1/domains/media-buy/scenarios/available_actions.yaml`` →
phase ``read_persisted_buy_actions`` → step ``get_created_buy_available_actions``
sends ``media_buy_ids: ["$context.<id captured from create_media_buy>"]`` and
validates the response against ``media-buy/get-media-buys-response.json``.

Shape mirrors ``MediaBuyDualEnv`` (create + update): extend ``MediaBuyCreateEnv``
and route by request type. The get_media_buys dispatch itself is inherited from
``MediaBuyListDispatchMixin`` rather than re-implemented, so this env and
``MediaBuyListEnv`` grade the same tool through the same code.

REST is intentionally NOT routed: UC-019 is a ``_NO_REST_UC`` (get_media_buys has
no REST route, tests/bdd/conftest.py:2885-2895), so the create and list REST
bodies never both apply in one scenario and wiring an ungraded second REST path
would be speculative. The inherited create REST dispatch is left untouched.

GH #1900
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.schemas._base import GetMediaBuysRequest
from tests.harness.media_buy_create import MediaBuyCreateEnv
from tests.harness.media_buy_list import MediaBuyListDispatchMixin


def _is_list_request(kwargs: dict[str, Any]) -> bool:
    return isinstance(kwargs.get("req"), GetMediaBuysRequest)


class MediaBuyCreateListEnv(MediaBuyListDispatchMixin, MediaBuyCreateEnv):
    """create_media_buy env that also dispatches get_media_buys.

    A ``req=GetMediaBuysRequest(...)`` kwarg routes to the list path; anything
    else falls through to the inherited create path. ``req=`` is a free
    discriminator because the dispatchers this env actually uses —
    ``_run_a2a_handler`` and ``_run_mcp_client`` (MediaBuyListDispatchMixin.call_mcp
    and MediaBuyCreateEnv.call_mcp both route through the latter) — already flatten
    a request model into the flat skill/tool parameters those wrappers accept.
    Not ``_run_mcp_wrapper``: it is deprecated, no env here calls it, and unlike
    ``_run_mcp_client`` it never stashes the real MCP wire.

    No extra patches: get_media_buys is a pure DB read with no external services,
    and the inherited create patches target the create module only.
    """

    def call_impl(self, **kwargs: Any) -> Any:
        if _is_list_request(kwargs):
            return self._call_list_impl(**kwargs)
        return super().call_impl(**kwargs)

    def call_a2a(self, **kwargs: Any) -> Any:
        if _is_list_request(kwargs):
            return self._call_list_a2a(**kwargs)
        return super().call_a2a(**kwargs)

    def call_mcp(self, **kwargs: Any) -> Any:
        if _is_list_request(kwargs):
            return self._call_list_mcp(**kwargs)
        return super().call_mcp(**kwargs)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Refuse to build a REST body for a list request; delegate everything else.

        ``get_media_buys`` has no REST route — ``src/routes/api_v1.py`` routes
        create, update and delivery for media buys, nothing for the list. Without this
        the inherited create builder handles the call: it is create-shaped, so it dies
        inside ``_restore_creative_ids`` reading a ``packages`` attribute the list
        request does not have, and the test grades a different call than it names.

        Scope, precisely: this refuses the ``req=GetMediaBuysRequest(...)`` arm, keyed
        on the same ``_is_list_request`` discriminator ``call_impl``/``call_a2a``/
        ``call_mcp`` use. A flat-kwargs call still routes to create here exactly as it
        does on every other transport of this env — consistent, not a REST-specific
        mis-dispatch, and deliberately left alone.

        The refusal is declared HERE, per env, and deliberately not derived from the
        route table. The two staleness failures are not symmetric: a route DELETED
        while deriving means the REST arm silently stops being graded and the suite
        stays green, whereas a route ADDED while declaring means the first REST call
        fails at this line — which is the line that must change anyway, since the list
        mixin's body builder is flat-kwargs-only and could not dispatch correctly on
        its own.

        ``pytest.fail`` and not ``NotImplementedError`` or ``AssertionError``, because
        this refusal has to survive two launderers to be loud at all:
        ``tests/bdd/conftest.py`` converts a ``NotImplementedError`` raised in a call
        phase into a skip + xfail — the silent matrix-shrink this exists to prevent —
        and ``RestDispatcher.dispatch`` wraps the whole dispatch, this builder
        included, in ``except Exception`` and returns the refusal as an error-shaped
        result indistinguishable from a production error response. ``Failed`` derives
        from ``BaseException`` and is not a ``NotImplementedError``, so neither can
        eat it. Do not "simplify" the dialect.
        """
        if _is_list_request(kwargs):
            pytest.fail(
                f"{type(self).__name__} cannot build a REST body for a get_media_buys request: "
                "the tool has no REST route. Dispatch it on A2A or MCP, or add the route "
                "and a list body builder here together.",
                pytrace=False,
            )
        # super(), not an explicit parent call: MediaBuyCreateUpdateListEnv resolves
        # this through MediaBuyDualEnv's stateful create/update routing, which naming
        # a parent directly would bypass.
        return super().build_rest_body(**kwargs)
