"""The perturbation seam the request factories exist to provide.

``payload()`` applies overrides AFTER the model dump. That ordering is the whole
reason the seam is usable for negative-path tests, and it is exactly the kind of
detail a later "simplification" to ``cls.build(**overrides).model_dump()`` would
quietly undo — at which point every test grading a REJECTED value would start
raising in its own setup instead of at the boundary under test, and the failure
would look like a broken test rather than a broken helper.

These grade the HELPER's contract, which is ours and can only be checked here.

Whether the baseline is spec-conformant is a different question and is no longer
asked statically. The suite that asked it argued that our DTOs were the weaker of
the two contracts — that the pin required ``account`` and ``idempotency_key``
where our models did not, and that ``idempotency_key`` was a bare ``str`` so
``"test-key-1"`` constructed fine. All three were measured false: the DTOs are
SDK-generated from the schema, they carry the identical required sets, and
``"test-key-1"`` is rejected for being under 16 characters. What remained was a
static hunt for a local subclass that widens its SDK parent, and BDD grades that
on the wire.

The one structural property worth keeping became a REFUSAL rather than a test:
``_register_tool`` will not register a tool whose DTO does not descend from
``AdcpVersionEnvelope``, because a DTO that does not is a DTO from a parallel
hierarchy (salesagent-fdkub).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.factories.request import OMIT, CreateMediaBuyRequestFactory, request_factories_by_tool


def test_an_override_may_carry_a_value_the_dto_would_reject() -> None:
    """The point of the seam: perturb to an INVALID value without setup raising.

    ``start_time`` is a typed ``StartTiming`` on the DTO, so routing this through
    the constructor raises — which is what the post-dump ordering avoids.
    """
    with pytest.raises(ValidationError):
        CreateMediaBuyRequestFactory.build(start_time="not-a-timestamp")

    payload = CreateMediaBuyRequestFactory.payload(start_time="not-a-timestamp")

    assert payload["start_time"] == "not-a-timestamp"


def test_perturbing_one_field_leaves_every_other_field_at_the_baseline() -> None:
    """One bad field means exactly one — nothing else may shift underneath it."""
    baseline = CreateMediaBuyRequestFactory.payload()
    perturbed = CreateMediaBuyRequestFactory.payload(
        brand={"domain": "other.example"},
        idempotency_key=baseline["idempotency_key"],
    )

    differing = {key for key in baseline.keys() | perturbed.keys() if baseline.get(key) != perturbed.get(key)}

    assert differing == {"brand"}, f"expected only 'brand' to differ, got {sorted(differing)}"


def test_omit_deletes_the_key_rather_than_nulling_it() -> None:
    """Grading a MISSING required field needs absence, which ``None`` cannot express.

    The baseline dump already drops nulls, so ``account=None`` would leave the
    default in place — the request would still carry an account.
    """
    assert "account" in CreateMediaBuyRequestFactory.payload()
    assert "account" not in CreateMediaBuyRequestFactory.payload(account=OMIT)

    #: ``None`` sends an explicit ``null``, which is a DIFFERENT perturbation from
    #: absence — a schema may accept a missing optional and still reject a null in
    #: its place — so it must stay expressible rather than being folded into OMIT.
    nulled = CreateMediaBuyRequestFactory.payload(account=None)
    assert "account" in nulled and nulled["account"] is None


def test_omitting_an_absent_key_is_not_an_error() -> None:
    """A caller should not have to know whether the baseline carries an optional field."""
    assert "po_number" not in CreateMediaBuyRequestFactory.payload(po_number=OMIT)


@pytest.mark.parametrize("tool_name", sorted(request_factories_by_tool()))
def test_each_baseline_is_independent(tool_name: str) -> None:
    """Two calls must not share mutable state — a step that mutates one payload
    would otherwise poison every later scenario in the process."""
    factory_class = request_factories_by_tool()[tool_name]
    first, second = factory_class.payload(), factory_class.payload()

    first["injected"] = "mutation"

    assert "injected" not in second


def test_idempotency_keys_are_fresh_per_call() -> None:
    """A REUSED key replays the original response instead of creating a new buy, so
    the default must not be stable; a replay test opts in by passing its own."""
    keys = {CreateMediaBuyRequestFactory.payload()["idempotency_key"] for _ in range(5)}

    assert len(keys) == 5, f"expected 5 distinct keys, got {sorted(keys)}"
