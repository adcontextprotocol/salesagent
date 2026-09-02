"""Pinned SDK model lookups used by the harness client.

Lives under ``tests/`` on purpose. ``spec_response_model`` is a response-side
parse-back helper for :mod:`tests.harness.client`; it never had a production
caller, and keeping it in ``src/core/version_compat.py`` meant a production
module carried a test-only export.

The REQUEST-side sibling, ``spec_request_model``, stays in production: the
acceptance seam itself depends on it.
"""

from adcp import types as adcp_types
from pydantic import BaseModel


def spec_response_model(tool_name: str) -> type[BaseModel] | None:
    """The pinned SDK response model for an MCP tool, or None if there isn't one
    single class to parse into.

    `get_products` -> `adcp.types.GetProductsResponse`. Mirrors
    `spec_request_model` above, mechanically, with the same "a miss carries
    information" reading: several tools resolve to a `Union` of outcome
    variants at the SDK level (`create_media_buy` -> immediate success /
    validation-error / async-task variants) rather than one plain
    `BaseModel` subclass — `isinstance(model, type)` is False for those
    (`types.UnionType`, not a class), so this deliberately returns `None`
    for them rather than guessing which union member a given wire dict
    matches. "No model" therefore means "no single pinned class to parse
    the wire body into", not "this tool has no response schema at all".
    """
    model = getattr(adcp_types, "".join(part.title() for part in tool_name.split("_")) + "Response", None)
    return model if isinstance(model, type) and issubclass(model, BaseModel) else None
