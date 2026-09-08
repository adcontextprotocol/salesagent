"""The one refusal contract for "asked for HMAC-SHA256, supplied no credentials".

Two protocol surfaces register a ``push_notification_config`` and neither goes
through the other: ``create_media_buy`` (tool path, graded in
``tests/integration/test_webhook_hmac_credentials_ingest_refusal.py``) and the
A2A-native ``setTaskPushNotificationConfig`` handler (graded in
``tests/unit/test_a2a_push_config_credential_refusal.py``, which calls
``PushNotificationConfigUoW.upsert`` directly). They emit through different
machinery — an ``AdCPValidationError`` translated by the tool boundary vs an
``InvalidParamsError`` carrying the envelope in ``data`` — but the envelope the
buyer reads is ONE contract, so it is asserted from one place here.

The second assertion in :func:`assert_credentials_refusal_envelope` is not
decoration. The A2A handler wraps its repository call in
``except ValueError as e: raise _invalid_params_from_ssrf_error(e)``
(``src/a2a_server/adcp_a2a_server.py``), and that helper hardcodes
``field="push_notification_config.url"`` plus the https SSRF suggestion. A
credential precondition that raises ``ValueError`` from inside the repository
would therefore be re-enveloped as a URL problem — telling the buyer to fix a
URL that is fine. "It refused" is not enough; it has to refuse about the right
field.
"""

from __future__ import annotations

from tests.helpers.envelope_assertions import assert_envelope_shape

# JSONPath-lite path into the buyer's request document. Written as a literal,
# not derived from production: ``error.field`` (``core/error.json`` @3.1.1) is a
# fact about the document the BUYER sent, and
# ``push_notification_config.authentication.credentials`` is where AdCP 3.1.1
# puts the legacy shared secret (``core/push-notification-config.json`` →
# ``Authentication.credentials``).
CREDENTIALS_FIELD = "push_notification_config.authentication.credentials"

# The registration URL gate's field path and its buyer-facing suggestion wording.
# Present here only as the WRONG answer — see the module docstring.
_URL_FIELD = "push_notification_config.url"

# The tail of that path, for the surfaces that do not (yet) qualify it with the
# same prefix: the admin registration form calls the same gate with
# ``field_prefix="webhook"``. Unifying the absolute prefixes is gh-#1895 and is
# deliberately not done here, so surfaces are compared on the part that says
# WHICH INPUT the caller must fix.
CREDENTIALS_FIELD_SUFFIX = "authentication.credentials"

# One character under the pinned ``credentials`` ``minLength: 32``
# (AdCP 3.1.1, ``dist/schemas/3.1.1/core/push-notification-config.json``). A
# BOUNDARY value, spelled once: a 5-character secret would also be refused by a
# hand-written "looks too short" rule that has nothing to do with the pin, so
# only 31 proves the pinned minimum is what refused it.
SHORT_CREDENTIAL = "s" * 31


def assert_admin_flash_refuses_the_credential(queued: list[tuple[str, str]], *, secret: str) -> None:
    """The ADMIN surface's half of the same contract, asserted from the same place.

    ``src/admin/blueprints/principals.py`` answers an operator in flashes, not in
    AdCP envelopes, so the two shapes cannot be compared byte-for-byte — but the
    VERDICT is one contract, and it is stated here so the admin grader and the
    cross-surface equivalence pin cannot drift on what "refused the credential"
    means.

    Three halves, none decoration:

    * refused at all, because accepting a registration the seller has already
      decided it will never sign is the accept-then-never-deliver defect;
    * naming the credential, because the sibling gate one field over refuses
      URLs and an operator sent to fix a URL that is fine has been misdirected;
    * not echoing the secret, because the flash is rendered back into the page.
    """
    assert len(queued) == 1, f"expected exactly one flash, got {queued}"
    category, message = queued[0]
    assert category == "error", (
        f"a shared secret shorter than the pinned minimum must be refused at ingest, not stored; flash was {queued[0]}"
    )
    assert CREDENTIALS_FIELD_SUFFIX in message, (
        f"the refusal must name {CREDENTIALS_FIELD_SUFFIX!r} so the operator fixes the secret and not "
        f"the URL; got {message!r}"
    )
    assert secret not in message, f"the flash echoed the operator's shared secret back: {message!r}"


def assert_credentials_refusal_envelope(envelope: dict, *, surface: str) -> None:
    """Assert the wire envelope refuses the CREDENTIAL, correctably, by name.

    ``VALIDATION_ERROR`` / ``recovery="correctable"`` matches the sibling gate
    this one sits beside — ``reject_unsafe_webhook_registration_url``
    (``src/core/webhook_validator.py``) raises ``AdCPValidationError``, whose
    ``_default_error_code`` is ``VALIDATION_ERROR``. The AdCP spec is silent on
    what a seller does with an HMAC registration carrying no secret, so the
    sibling gate is the authority for the SHAPE (source hierarchy: schema
    silent → production authoritative).

    ``correctable`` rather than ``terminal`` because the buyer is the only party
    who can supply the secret, and supplying it makes the identical request
    succeed.
    """
    assert_envelope_shape(
        envelope,
        "VALIDATION_ERROR",
        recovery="correctable",
        field=CREDENTIALS_FIELD,
    )
    _assert_not_mislabelled_as_a_url_refusal(envelope, surface=surface)


def _assert_not_mislabelled_as_a_url_refusal(envelope: dict, *, surface: str) -> None:
    """Fail if the refusal was re-enveloped as the URL/SSRF refusal.

    Checked on BOTH envelope layers for the same reason ``field`` is: the
    two-layer envelope's ``adcp_error`` and ``errors[0]`` are read by different
    storyboard steps in the wild, so a mislabel on either one reaches a buyer.
    """
    from src.core.webhook_validator import webhook_ssrf_suggestion

    ssrf_suggestion = webhook_ssrf_suggestion()
    for layer, body in (("adcp_error", envelope["adcp_error"]), ("errors[0]", envelope["errors"][0])):
        assert body.get("field") != _URL_FIELD, (
            f"{surface}: {layer}.field is {_URL_FIELD!r} — a missing HMAC credential was "
            f"re-enveloped as a URL refusal, sending the buyer to fix a URL that is fine"
        )
        assert body.get("suggestion") != ssrf_suggestion, (
            f"{surface}: {layer}.suggestion carries the SSRF/https wording {ssrf_suggestion!r} — "
            f"the buyer needs to add a shared secret, not change their URL scheme"
        )
