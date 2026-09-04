"""Characterization tests for (MED-01/MED-05/CON-05/LR-01).

Guard the behavior of the generic ``then_boundary_handling_result`` step on the
DELIVERY domain path so that relocating that logic out of the generic
``then_payload`` module into ``uc004_delivery`` (via a boundary-handler registry)
preserves behavior exactly.

Importing ``uc004_delivery`` ensures its registered delivery handler is active
after the refactor (no-op before it). These call the real generic step with a
crafted ctx; they pass on the pre-refactor code and must keep passing after.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.exceptions import AdCPError

# Importing the domain module registers its boundary handler post-refactor.
from tests.bdd.steps.domain import uc004_delivery  # noqa: F401
from tests.bdd.steps.generic.then_payload import then_boundary_handling_result

DELIVERY_FIELD = "reporting_dimensions"  # a delivery-domain boundary field


# ctx key for a payload produced WITHOUT dispatching, which is what these
# unit tests do: they drive a Then directly to exercise its assertion logic.
def _delivery_response(deliveries):
    return SimpleNamespace(media_buy_deliveries=deliveries)


def test_valid_delivery_boundary_with_deliveries_passes():
    ctx = {"self_dispatched_response": _delivery_response([SimpleNamespace(media_buy_id="mb1")])}
    then_boundary_handling_result(ctx, DELIVERY_FIELD, "valid")  # no raise


def test_valid_delivery_boundary_empty_deliveries_raises():
    ctx = {"self_dispatched_response": _delivery_response([])}
    with pytest.raises(AssertionError):
        then_boundary_handling_result(ctx, DELIVERY_FIELD, "valid")


def test_invalid_delivery_boundary_with_error_passes():
    ctx = {"error": AdCPError("bad reporting_dimensions")}
    then_boundary_handling_result(ctx, DELIVERY_FIELD, "invalid")  # no raise


def test_invalid_delivery_boundary_without_error_raises():
    ctx = {"self_dispatched_response": _delivery_response([SimpleNamespace(media_buy_id="mb1")])}
    with pytest.raises(AssertionError):
        then_boundary_handling_result(ctx, DELIVERY_FIELD, "invalid")
