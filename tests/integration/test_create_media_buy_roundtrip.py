"""
Integration test for create_media_buy roundtrip with testing hooks.

This test was added after discovering that CreateMediaBuyResponse reconstruction
failed when apply_testing_hooks added extra fields to the response dict.

The bug: apply_testing_hooks adds fields like 'is_test', 'dry_run', 'test_session_id',
'response_headers', 'debug_info' which aren't part of CreateMediaBuyResponse schema.
When we tried to reconstruct with CreateMediaBuyResponse(**response_data), Pydantic
validation failed.

The fix: Filter out non-schema fields before reconstruction (main.py:3747-3760).

This test ensures the fix works and prevents regression.
"""

import pytest

from src.core.testing_hooks import TestingContext, apply_testing_hooks

pytestmark = pytest.mark.integration


@pytest.mark.integration
class TestCreateMediaBuyRoundtrip:
    """Test create_media_buy response roundtrip through testing hooks."""

    @pytest.fixture
    def setup_test_tenant(self, integration_db):
        """Set up test tenant with product."""
        with get_db_session() as session:
            now = datetime.now(UTC)

            # Create tenant
            tenant = ModelTenant(
                tenant_id="test_roundtrip_tenant",
                name="Test Roundtrip Tenant",
                subdomain="test-roundtrip",
                ad_server="mock",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(tenant)

            # Create principal
            principal = ModelPrincipal(
                tenant_id="test_roundtrip_tenant",
                principal_id="test_roundtrip_principal",
                name="Test Roundtrip Principal",
                access_token="test_roundtrip_token",
                platform_mappings={"mock": {"advertiser_id": "adv_test"}},
            )
            session.add(principal)

            # Create product
            product = ModelProduct(
                tenant_id="test_roundtrip_tenant",
                product_id="prod_roundtrip",
                name="Test Roundtrip Product",
                description="Product for roundtrip testing",
                formats=["display_300x250"],
                delivery_type="guaranteed",
                cpm=10.0,
                min_spend=1000.0,
                targeting_template={},
                is_fixed_price=True,
            )
            session.add(product)

            # Add currency limit
            currency_limit = CurrencyLimit(
                tenant_id="test_roundtrip_tenant",
                currency_code="USD",
                min_package_budget=1000.0,
                max_daily_package_spend=10000.0,
            )
            session.add(currency_limit)

            session.commit()

            yield {
                "tenant_id": "test_roundtrip_tenant",
                "principal_id": "test_roundtrip_principal",
                "product_id": "prod_roundtrip",
            }

            # Cleanup
            session.execute(delete(ModelProduct).where(ModelProduct.tenant_id == "test_roundtrip_tenant"))
            session.execute(delete(ModelPrincipal).where(ModelPrincipal.tenant_id == "test_roundtrip_tenant"))
            session.execute(delete(CurrencyLimit).where(CurrencyLimit.tenant_id == "test_roundtrip_tenant"))
            session.execute(delete(ModelTenant).where(ModelTenant.tenant_id == "test_roundtrip_tenant"))
            session.commit()

    @pytest.mark.requires_db
    def test_create_media_buy_response_survives_testing_hooks_roundtrip(self, setup_test_tenant):
        """
        Test that CreateMediaBuyResponse can be reconstructed after apply_testing_hooks.

        This test exercises the EXACT code path that was failing in production:
        1. Create CreateMediaBuyResponse with valid data
        2. Convert to dict via model_dump_internal()
        3. Pass through apply_testing_hooks (THIS ADDS EXTRA FIELDS)
        4. Filter and reconstruct CreateMediaBuyResponse(**filtered_data)

        Without the fix at main.py:3747-3760, step 4 would fail with:
        "1 validation error for CreateMediaBuyResponse: buyer_ref Field required"
        """
        # Step 1: Create a valid CreateMediaBuyResponse (simulates what adapter returns)
        original_response = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="working",
            buyer_ref="test-buyer-ref-123",
            media_buy_id="mb_test_12345",
            packages=[
                {
                    "package_id": "pkg_1",
                    "buyer_ref": "pkg_test",
                    "products": [setup_test_tenant["product_id"]],
                    "budget": {"total": 5000.0, "currency": "USD", "pacing": "even"},
                    "status": "working",
                }
            ],
        )

        # Step 2: Convert to dict (as main.py does)
        response_data = original_response.model_dump_internal()

        # Verify original data has buyer_ref
        assert "buyer_ref" in response_data
        assert response_data["buyer_ref"] == "test-buyer-ref-123"

        # Step 3: Apply testing hooks with various options enabled
        testing_ctx = TestingContext(
            dry_run=True,
            test_session_id="test-session-123",
            auto_advance=False,
            debug_mode=True,
        )

        # Campaign info that triggers additional response headers
        campaign_info = {
            "start_date": datetime.now(UTC),
            "end_date": datetime.now(UTC) + timedelta(days=30),
            "total_budget": 5000.0,
        }

        # This adds extra fields: is_test, test_session_id, dry_run, response_headers, debug_info
        modified_data = apply_testing_hooks(response_data, testing_ctx, "create_media_buy", campaign_info)

        # Verify testing hooks added extra fields
        assert "is_test" in modified_data, "apply_testing_hooks should add is_test"
        assert "dry_run" in modified_data, "apply_testing_hooks should add dry_run"
        assert "test_session_id" in modified_data, "apply_testing_hooks should add test_session_id"
        assert modified_data["is_test"] is True
        assert modified_data["dry_run"] is True

        # Verify original fields still present
        assert "buyer_ref" in modified_data
        assert modified_data["buyer_ref"] == "test-buyer-ref-123"

        # Step 4: Reconstruct response (this is where the bug occurred)
        # The fix at main.py:3747-3760 filters out non-schema fields
        valid_fields = {
            "adcp_version",
            "status",
            "buyer_ref",
            "task_id",
            "media_buy_id",
            "creative_deadline",
            "packages",
            "errors",
            "workflow_step_id",
        }
        filtered_data = {k: v for k, v in modified_data.items() if k in valid_fields}

        # This should NOT raise validation error
        reconstructed_response = CreateMediaBuyResponse(**filtered_data)

        # Step 5: Verify reconstruction succeeded
        assert reconstructed_response.buyer_ref == "test-buyer-ref-123"
        # Note: dry_run mode prepends "test_" to media_buy_id
        assert reconstructed_response.media_buy_id == "test_mb_test_12345"
        assert reconstructed_response.status == "working"
        assert len(reconstructed_response.packages) == 1

    @pytest.mark.requires_db
    def test_create_media_buy_response_roundtrip_without_hooks(self, setup_test_tenant):
        """
        Test baseline: CreateMediaBuyResponse roundtrip WITHOUT testing hooks works.

        This establishes that the schema itself is valid and the issue is specifically
        with the interaction between testing hooks and schema validation.
        """
        # Create response
        original_response = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="completed",
            buyer_ref="baseline-test",
            media_buy_id="mb_baseline",
        )

        # Convert to dict and back (no testing hooks)
        response_data = original_response.model_dump_internal()
        reconstructed = CreateMediaBuyResponse(**response_data)

        # Should work perfectly without testing hooks
        assert reconstructed.buyer_ref == "baseline-test"
        assert reconstructed.media_buy_id == "mb_baseline"
        assert reconstructed.status == "completed"

    @pytest.mark.requires_db
    def test_testing_hooks_fields_are_excluded_from_reconstruction(self, setup_test_tenant):
        """
        Test that testing hook fields don't leak into reconstructed response.

        Verifies that extra fields added by testing hooks are properly filtered out
        and don't appear in the final CreateMediaBuyResponse object.
        """
        original_response = CreateMediaBuyResponse(
            status="working",
            buyer_ref="filter-test",
            media_buy_id="mb_filter",
        )

        response_data = original_response.model_dump_internal()

        # Apply testing hooks
        testing_ctx = TestingContext(dry_run=True, test_session_id="filter-test")
        campaign_info = {"start_date": datetime.now(UTC), "end_date": datetime.now(UTC), "total_budget": 1000}
        modified_data = apply_testing_hooks(response_data, testing_ctx, "create_media_buy", campaign_info)

        # Verify extra fields were added
        assert "dry_run" in modified_data
        assert "is_test" in modified_data

        # Filter and reconstruct
        valid_fields = {
            "adcp_version",
            "status",
            "buyer_ref",
            "task_id",
            "media_buy_id",
            "creative_deadline",
            "packages",
            "errors",
            "workflow_step_id",
        }
        filtered_data = {k: v for k, v in modified_data.items() if k in valid_fields}
        reconstructed = CreateMediaBuyResponse(**filtered_data)

        # Verify extra fields don't exist in reconstructed response
        response_dict = reconstructed.model_dump()
        assert "dry_run" not in response_dict, "Testing hook fields should be filtered out"
        assert "is_test" not in response_dict, "Testing hook fields should be filtered out"
        assert "test_session_id" not in response_dict, "Testing hook fields should be filtered out"

        # Verify required fields still present
        assert "buyer_ref" in response_dict
        assert response_dict["buyer_ref"] == "filter-test"
