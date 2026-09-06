"""Every response type produces its buyer-facing summary through ``__str__``.

Regression test for PR #339, where an A2A skill read ``response.message`` off a
``CreateMediaBuySuccess`` and got an AttributeError. The AttributeError half of that
story has expired -- ``create-media-buy-response.json`` @ 3.1.1 composes
``core/protocol-envelope.json`` at its root, so ``message`` is a declared field now --
but the fix is still the contract: the summary comes from ``__str__``, and a caller that
reads the unfilled ``message`` field gets None rather than a sentence.
"""

from src.core.schemas import (
    CreateMediaBuySuccess,
    GetProductsResponse,
    SyncCreativeResult,
    SyncCreativesResponse,
)


def test_create_media_buy_response_message_access():
    """``str()`` on a create success is the sentence an A2A skill sends, ``message`` is not."""
    response = CreateMediaBuySuccess.carrier(media_buy_id="mb-12345", packages=[])

    assert str(response) == "Media buy mb-12345 created successfully."
    assert response.message is None


def test_other_response_types():
    """Test that str() pattern works for all response types.

    Verifies that using str(response) is safe for:
    - Responses with __str__() generating messages (GetProductsResponse, SyncCreativesResponse)
    All responses now generate messages via __str__() from domain data.
    """

    # Test GetProductsResponse (generates message via __str__())
    response1 = GetProductsResponse(products=[])
    msg1 = str(response1)
    assert msg1 == "No products matched your requirements."

    # Test SyncCreativesResponse (generates message via __str__() from creatives list)
    response2 = SyncCreativesResponse(
        creatives=[SyncCreativeResult(creative_id="cr-001", internal_status="approved", action="created")],
        dry_run=False,
    )
    msg2 = str(response2)
    assert "1 created" in msg2  # Generated from creatives list
