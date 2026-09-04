"""Brand string shorthand coercion for get_products and create_media_buy (#1324)."""

import pytest

from src.core.exceptions import AdCPSalesAgentError, build_two_layer_error_envelope
from src.core.schema_helpers import (
    brand_shorthand_to_domain,
    is_url_shorthand,
    to_brand_reference,
)
from tests.helpers import assert_envelope_shape
from tests.helpers.capture_wrapper_req import capture_req_via_wrapper


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://acme.com", True),
        ("//cdn.example.com", True),
        ("acme.com", False),
        ("ACME.COM", False),
    ],
)
def test_is_url_shorthand(value: str, expected: bool) -> None:
    assert is_url_shorthand(value) is expected


@pytest.mark.parametrize(
    ("shorthand", "expected_domain"),
    [
        ("https://test.example", "test.example"),
        ("http://test.example/path", "test.example"),
        ("acme.com", "acme.com"),
        ("ACME.COM", "acme.com"),
    ],
)
def test_brand_shorthand_to_domain(shorthand: str, expected_domain: str) -> None:
    assert brand_shorthand_to_domain(shorthand) == expected_domain


def test_to_brand_reference_string_url_shorthand() -> None:
    ref = to_brand_reference("https://test.example")
    assert ref is not None
    assert ref.domain == "test.example"


def test_to_brand_reference_dict_form_unchanged() -> None:
    ref = to_brand_reference({"domain": "test.example"})
    assert ref is not None
    assert ref.domain == "test.example"


@pytest.mark.parametrize(
    "malformed_url",
    [
        "https://[",
        "http://[::1",
    ],
)
def test_brand_shorthand_to_domain_malformed_url_non_raising(malformed_url: str) -> None:
    """Malformed URL shorthands must not raise (graceful degradation for brand_manifest)."""
    assert brand_shorthand_to_domain(malformed_url) == ""


def test_to_brand_reference_malformed_url_raises_invalid_request() -> None:
    """An unparseable URL is a schema-constraint failure -> INVALID_REQUEST.

    Graded on the built envelope, not on ``pytest.raises`` alone: this used to
    assert ``AdCPValidationError``, which ``AdCPInvalidRequestError`` SUBCLASSES,
    so it passed for either code and could never have caught the wrong one
    (salesagent-prkv.37).
    """
    with pytest.raises(AdCPSalesAgentError) as exc_info:
        to_brand_reference("https://[")
    assert exc_info.value.field == "brand"
    assert_envelope_shape(build_two_layer_error_envelope(exc_info.value), "INVALID_REQUEST", recovery="correctable")


@pytest.mark.parametrize(
    "invalid_brand",
    [
        "acme.com/products",
        "my_brand.com",
        "https://münchen.de",
    ],
)
def test_to_brand_reference_invalid_domain_raises_invalid_request(invalid_brand: str) -> None:
    """Path, underscore and IDN all fail BrandReference.domain's PATTERN.

    A pattern is a schema constraint, which the pinned enum
    (adcp 6.6.0, _schemas/3.1/enums/error-code.json) assigns to INVALID_REQUEST
    rather than VALIDATION_ERROR ("beyond schema validation"). Asserted on the
    envelope for the same reason as above.
    """
    with pytest.raises(AdCPSalesAgentError) as exc_info:
        to_brand_reference(invalid_brand)
    assert exc_info.value.field == "brand"
    assert_envelope_shape(build_two_layer_error_envelope(exc_info.value), "INVALID_REQUEST", recovery="correctable")


def test_dict_uppercase_domain_normalized_like_string() -> None:
    ref = to_brand_reference({"domain": "ACME.COM"})
    assert ref is not None
    assert ref.domain == "acme.com"


def test_dict_url_domain_normalized_like_string() -> None:
    from_dict = to_brand_reference({"domain": "https://acme.com"})
    from_string = to_brand_reference("https://acme.com")
    assert from_dict is not None and from_string is not None
    assert from_dict.domain == from_string.domain == "acme.com"


def test_to_brand_reference_dict_preserves_governance_fields() -> None:
    """Dict path must preserve all BrandReference fields, not pluck domain/brand_id only."""
    ref = to_brand_reference(
        {
            "domain": "ACME.COM",
            "industries": ["automotive"],
            "data_subject_contestation": {"email": "dpo@acme.com"},
            "brand_kit_override": {"colors": {"primary": "#003366"}},
        }
    )
    assert ref is not None
    assert ref.domain == "acme.com"
    assert ref.industries == ["automotive"]
    assert ref.data_subject_contestation is not None
    assert ref.data_subject_contestation.email == "dpo@acme.com"
    assert ref.brand_kit_override is not None
    assert ref.brand_kit_override.colors is not None
    assert ref.brand_kit_override.colors.primary == "#003366"


def test_to_brand_reference_unexpected_type_raises_invalid_request() -> None:
    """A brand that is neither string, dict nor BrandReference is a type violation."""
    with pytest.raises(AdCPSalesAgentError) as exc_info:
        to_brand_reference(123)  # type: ignore[arg-type]
    assert exc_info.value.field == "brand"
    assert_envelope_shape(build_two_layer_error_envelope(exc_info.value), "INVALID_REQUEST", recovery="correctable")


@pytest.mark.parametrize(
    "invalid_brand",
    [
        {},
        {"domain": 123},
        {"brand_id": "x"},
        {"domain": "acme.com", "industries": "not-a-list"},
    ],
)
def test_to_brand_reference_dict_rejects_raise_invalid_request(invalid_brand: dict) -> None:
    """Dict-branch rejects (missing/non-string domain; malformed governance fields).

    All four rows are schema constraints -- a missing required field or a wrong
    JSON type -- so all four are INVALID_REQUEST. Two reach it by the explicit
    raise and two by pydantic through ``adcp_validation_boundary``; the envelope
    assertion holds them to the same answer regardless of which path ran.
    """
    with pytest.raises(AdCPSalesAgentError) as exc_info:
        to_brand_reference(invalid_brand)
    assert exc_info.value.field == "brand"
    assert_envelope_shape(build_two_layer_error_envelope(exc_info.value), "INVALID_REQUEST", recovery="correctable")


def _minimal_create_media_buy_kwargs() -> dict:
    from tests.helpers.adcp_factories import create_test_media_buy_request_dict

    req_dict = create_test_media_buy_request_dict()
    return {
        "packages": req_dict["packages"],
        "start_time": req_dict["start_time"],
        "end_time": req_dict["end_time"],
        "po_number": req_dict.get("po_number"),
        "reporting_webhook": None,
        "context": None,
        "ext": None,
        # The factory's account, not an explicit None: create-media-buy-request.json lists
        # account in /required, so None no longer builds. This helper is about the BRAND
        # shorthand, so it takes the spec-conformant default like every other field here.
        "account": req_dict["account"],
        "idempotency_key": req_dict["idempotency_key"],
        # Required keyword-only on this branch's builder (AdCP 3.1.1 pause-on-create param).
        "paused": None,
    }


@pytest.mark.parametrize(
    ("brand_input", "expected_domain"),
    [
        ("acme.com", "acme.com"),
        ("ACME.COM", "acme.com"),
        ("https://test.example", "test.example"),
        ("http://acme.com/path", "acme.com"),
        ({"domain": "acme.com"}, "acme.com"),
        ({"domain": "ACME.COM"}, "acme.com"),
        ({"domain": "https://acme.com"}, "acme.com"),
    ],
)
@pytest.mark.parametrize(
    "invalid_brand",
    ["https://[", "acme.com/products", "my_brand.com", "https://münchen.de"],
)
def _capture_req_via_create_media_buy(brand):
    """Run the real MCP create_media_buy wrapper with `brand`; return the req handed to the impl."""
    from src.core.schemas import CreateMediaBuyResult
    from src.core.schemas._base import CreateMediaBuySuccess
    from src.core.tools.media_buy_create import create_media_buy
    from tests.helpers.adcp_factories import create_test_media_buy_request_dict

    req_dict = create_test_media_buy_request_dict(brand={"domain": "placeholder.com"})
    stub = CreateMediaBuyResult(
        response=CreateMediaBuySuccess.carrier(media_buy_id="mb_test", buyer_ref="buyer-1", packages=[]),
        status="completed",
    )
    return capture_req_via_wrapper(
        impl_patch_target="src.core.tools.media_buy_create._create_media_buy_impl",
        wrapper=create_media_buy,
        stub_response=stub,
        wrapper_kwargs={
            "brand": brand,
            "packages": req_dict["packages"],
            "start_time": req_dict["start_time"],
            "end_time": req_dict["end_time"],
            "idempotency_key": req_dict["idempotency_key"],
            "account": req_dict["account"],
        },
    )
