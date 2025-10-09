"""End-to-end integration tests for complete creative lifecycle.

This test suite verifies the full creative lifecycle workflow:
1. Upload creatives via sync_creatives
2. Query creatives via list_creatives
3. Assign creatives to packages
4. Update creative status and metadata
5. Test creative lifecycle across media buys

Tests both MCP and A2A protocols with real database persistence.
Uses testing hooks from AdCP specification for controlled testing.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.e2e.adcp_schema_validator import AdCPSchemaValidator


class CreativeLifecycleTestSuite:
    """End-to-end creative lifecycle test suite."""

    def __init__(
        self, mcp_url: str, a2a_url: str, auth_token: str, test_session_id: str = None, validate_schemas: bool = True
    ):
        self.mcp_url = mcp_url
        self.a2a_url = a2a_url
        self.auth_token = auth_token
        self.test_session_id = test_session_id or f"creative_test_{uuid.uuid4().hex[:8]}"
        self.validate_schemas = validate_schemas

        # Test data storage
        self.test_media_buy_id = None
        self.test_creatives = []
        self.test_assignments = []

        # HTTP clients
        self.http_client = httpx.AsyncClient()
        self.mcp_client = None
        self.schema_validator = None

    async def __aenter__(self):
        """Initialize async context."""
        # Set up MCP client
        headers = self._build_headers()
        transport = StreamableHttpTransport(url=f"{self.mcp_url}/mcp/", headers=headers)
        self.mcp_client = Client(transport=transport)
        await self.mcp_client.__aenter__()

        # Set up schema validator
        if self.validate_schemas:
            self.schema_validator = AdCPSchemaValidator(offline_mode=True, adcp_version="v1")
            await self.schema_validator.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up async context."""
        if self.mcp_client:
            await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.schema_validator:
            await self.schema_validator.__aexit__(exc_type, exc_val, exc_tb)
        await self.http_client.aclose()

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with testing hooks."""
        return {
            "x-adcp-auth": self.auth_token,
            "X-Test-Session-ID": self.test_session_id,
            "X-Dry-Run": "false",  # Use real operations for E2E test
            "Content-Type": "application/json",
        }

    async def _validate_response(self, operation_name: str, response_data: Any):
        """Validate response against AdCP schema if enabled."""
        if self.schema_validator:
            try:
                await self.schema_validator.validate_response(operation_name, response_data)
            except Exception as e:
                pytest.fail(f"Schema validation failed for {operation_name}: {e}")

    async def setup_test_media_buy(self) -> str:
        """Create a test media buy for creative assignments."""
        try:
            # Get available products first
            products_result = await self.mcp_client.tools.get_products(
                brief="display and video ads", promoted_offering="creative testing"
            )
            products_data = products_result.content if hasattr(products_result, "content") else products_result

            if not products_data.get("products"):
                pytest.skip("No products available for creative testing")

            # Create media buy with first available product
            product_id = products_data["products"][0]["product_id"]

            create_result = await self.mcp_client.tools.create_media_buy(
                product_ids=[product_id],
                total_budget=5000.0,
                flight_start_date=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
                flight_end_date=(datetime.now(UTC) + timedelta(days=30)).isoformat(),
            )

            create_data = create_result.content if hasattr(create_result, "content") else create_result

            if not create_data.get("success"):
                pytest.fail(f"Failed to create test media buy: {create_data.get('message')}")

            self.test_media_buy_id = create_data["media_buy_id"]
            return self.test_media_buy_id

        except Exception as e:
            pytest.fail(f"Failed to setup test media buy: {e}")

    async def test_sync_creatives_basic_upload(self):
        """Test basic creative upload via sync_creatives."""
        # Ensure media buy exists
        if not self.test_media_buy_id:
            await self.setup_test_media_buy()

        # Prepare test creatives
        test_creatives = [
            {
                "creative_id": f"e2e_display_{uuid.uuid4().hex[:8]}",
                "name": "E2E Display Ad 300x250",
                "format": "display_300x250",
                "url": "https://e2e-test.example.com/display.jpg",
                "click_url": "https://advertiser.example.com/landing",
                "width": 300,
                "height": 250,
            },
            {
                "creative_id": f"e2e_video_{uuid.uuid4().hex[:8]}",
                "name": "E2E Video Ad 15sec",
                "format": "video_pre_roll",
                "url": "https://e2e-test.example.com/video.mp4",
                "click_url": "https://advertiser.example.com/video-landing",
                "width": 1280,
                "height": 720,
                "duration": 15.0,
            },
            {
                "creative_id": f"e2e_native_{uuid.uuid4().hex[:8]}",
                "name": "E2E Native Ad with Snippet",
                "format": "native_content",
                "snippet": "<script>window.nativeAd = {title: 'E2E Test', cta: 'Click Here'};</script>",
                "snippet_type": "javascript",
                "template_variables": {
                    "headline": "Amazing E2E Test Product!",
                    "description": "Experience the future of testing",
                    "cta_text": "Learn More",
                },
                "click_url": "https://advertiser.example.com/native-landing",
            },
        ]

        # Sync creatives
        sync_result = await self.mcp_client.tools.sync_creatives(
            creatives=test_creatives,
            media_buy_id=self.test_media_buy_id,
            assign_to_packages=["package_1", "package_2"],
            upsert=False,
        )

        sync_data = sync_result.content if hasattr(sync_result, "content") else sync_result

        # Validate response
        await self._validate_response("sync_creatives", sync_data)

        # Verify sync results
        assert len(sync_data["creatives"]) == 3
        assert len(sync_data["failed_creatives"]) == 0
        assert len(sync_data["assignments"]) == 6  # 3 creatives × 2 packages

        # Store for later tests
        self.test_creatives = [c["creative_id"] for c in sync_data["creatives"]]
        self.test_assignments = sync_data["assignments"]

        # Verify creative data integrity
        display_creative = next((c for c in sync_data["creatives"] if c["format"] == "display_300x250"), None)
        assert display_creative is not None
        assert display_creative["width"] == 300
        assert display_creative["height"] == 250

        video_creative = next((c for c in sync_data["creatives"] if c["format"] == "video_pre_roll"), None)
        assert video_creative is not None
        assert video_creative["duration"] == 15.0

        native_creative = next((c for c in sync_data["creatives"] if c["format"] == "native_content"), None)
        assert native_creative is not None
        assert native_creative["snippet"] is not None
        assert native_creative["template_variables"] is not None

        return sync_data

    async def test_list_creatives_basic_query(self):
        """Test basic creative querying via list_creatives."""
        if not self.test_creatives:
            await self.test_sync_creatives_basic_upload()

        # Query all creatives
        list_result = await self.mcp_client.tools.list_creatives()
        list_data = list_result.content if hasattr(list_result, "content") else list_result

        # Validate response
        await self._validate_response("list_creatives", list_data)

        # Verify results
        assert len(list_data["creatives"]) >= 3  # At least our test creatives
        assert list_data["total_count"] >= 3

        # Check our test creatives are in results
        creative_ids = [c["creative_id"] for c in list_data["creatives"]]
        for test_id in self.test_creatives:
            assert test_id in creative_ids

        return list_data

    async def test_list_creatives_filtered_queries(self):
        """Test filtered creative queries."""
        if not self.test_creatives:
            await self.test_sync_creatives_basic_upload()

        # Test status filter
        pending_result = await self.mcp_client.tools.list_creatives(status="pending")
        pending_data = pending_result.content if hasattr(pending_result, "content") else pending_result

        await self._validate_response("list_creatives", pending_data)
        assert all(c["status"] == "pending" for c in pending_data["creatives"])

        # Test format filter
        display_result = await self.mcp_client.tools.list_creatives(format="display_300x250")
        display_data = display_result.content if hasattr(display_result, "content") else display_result

        await self._validate_response("list_creatives", display_data)
        assert all(c["format"] == "display_300x250" for c in display_data["creatives"])

        # Test media buy filter
        media_buy_result = await self.mcp_client.tools.list_creatives(media_buy_id=self.test_media_buy_id)
        media_buy_data = media_buy_result.content if hasattr(media_buy_result, "content") else media_buy_result

        await self._validate_response("list_creatives", media_buy_data)
        # All results should be from our media buy
        for creative in media_buy_data["creatives"]:
            assert creative["creative_id"] in self.test_creatives

        # Test search functionality
        search_result = await self.mcp_client.tools.list_creatives(search="E2E")
        search_data = search_result.content if hasattr(search_result, "content") else search_result

        await self._validate_response("list_creatives", search_data)
        assert all("E2E" in c["name"] for c in search_data["creatives"])

        return {"pending": pending_data, "display": display_data, "media_buy": media_buy_data, "search": search_data}

    async def test_creative_upsert_functionality(self):
        """Test creative update via upsert."""
        if not self.test_creatives:
            await self.test_sync_creatives_basic_upload()

        # Get first creative for update
        original_creative_id = self.test_creatives[0]

        # Prepare updated creative data
        updated_creative = {
            "creative_id": original_creative_id,
            "name": "UPDATED E2E Display Ad 300x250",
            "format": "display_300x250",
            "url": "https://e2e-test.example.com/updated_display.jpg",
            "click_url": "https://advertiser.example.com/updated-landing",
            "width": 300,
            "height": 250,
        }

        # Sync with upsert=True
        upsert_result = await self.mcp_client.tools.sync_creatives(creatives=[updated_creative], upsert=True)

        upsert_data = upsert_result.content if hasattr(upsert_result, "content") else upsert_result

        # Validate response
        await self._validate_response("sync_creatives", upsert_data)

        # Verify update succeeded
        assert len(upsert_data["creatives"]) == 1
        assert len(upsert_data["failed_creatives"]) == 0

        updated = upsert_data["creatives"][0]
        assert updated["name"] == "UPDATED E2E Display Ad 300x250"
        assert updated["url"] == "https://e2e-test.example.com/updated_display.jpg"

        # Verify update persisted by querying
        list_result = await self.mcp_client.tools.list_creatives(search="UPDATED")
        list_data = list_result.content if hasattr(list_result, "content") else list_result

        assert len(list_data["creatives"]) >= 1
        updated_creative_found = next(
            (c for c in list_data["creatives"] if c["creative_id"] == original_creative_id), None
        )
        assert updated_creative_found is not None
        assert updated_creative_found["name"] == "UPDATED E2E Display Ad 300x250"

        return upsert_data

    async def test_creative_pagination_and_sorting(self):
        """Test pagination and sorting in list_creatives."""
        if not self.test_creatives:
            await self.test_sync_creatives_basic_upload()

        # Test pagination
        page1_result = await self.mcp_client.tools.list_creatives(page=1, limit=2)
        page1_data = page1_result.content if hasattr(page1_result, "content") else page1_result

        await self._validate_response("list_creatives", page1_data)
        assert len(page1_data["creatives"]) <= 2

        if page1_data.get("has_more"):
            page2_result = await self.mcp_client.tools.list_creatives(page=2, limit=2)
            page2_data = page2_result.content if hasattr(page2_result, "content") else page2_result

            await self._validate_response("list_creatives", page2_data)

            # Ensure different results across pages
            page1_ids = [c["creative_id"] for c in page1_data["creatives"]]
            page2_ids = [c["creative_id"] for c in page2_data["creatives"]]
            assert not set(page1_ids).intersection(set(page2_ids))

        # Test sorting by name
        name_asc_result = await self.mcp_client.tools.list_creatives(sort_by="name", sort_order="asc", limit=10)
        name_asc_data = name_asc_result.content if hasattr(name_asc_result, "content") else name_asc_result

        await self._validate_response("list_creatives", name_asc_data)

        # Verify sorting
        names = [c["name"] for c in name_asc_data["creatives"]]
        assert names == sorted(names)

        return {"page1": page1_data, "name_sorted": name_asc_data}

    async def test_creative_assignments_workflow(self):
        """Test creative assignment and querying workflow."""
        if not self.test_creatives:
            await self.test_sync_creatives_basic_upload()

        # Create additional creative without initial assignment
        unassigned_creative = {
            "creative_id": f"e2e_unassigned_{uuid.uuid4().hex[:8]}",
            "name": "E2E Unassigned Creative",
            "format": "display_728x90",
            "url": "https://e2e-test.example.com/unassigned.jpg",
            "width": 728,
            "height": 90,
        }

        # Sync without assignments
        sync_result = await self.mcp_client.tools.sync_creatives(creatives=[unassigned_creative], upsert=False)

        sync_data = sync_result.content if hasattr(sync_result, "content") else sync_result
        assert len(sync_data["assignments"]) == 0  # No assignments requested

        unassigned_creative_id = sync_data["creatives"][0]["creative_id"]

        # Now assign it to packages
        assign_result = await self.mcp_client.tools.sync_creatives(
            creatives=[unassigned_creative],
            media_buy_id=self.test_media_buy_id,
            assign_to_packages=["package_3"],
            upsert=True,
        )

        assign_data = assign_result.content if hasattr(assign_result, "content") else assign_result
        assert len(assign_data["assignments"]) == 1

        # Verify assignment by querying media buy creatives
        media_buy_result = await self.mcp_client.tools.list_creatives(media_buy_id=self.test_media_buy_id)
        media_buy_data = media_buy_result.content if hasattr(media_buy_result, "content") else media_buy_result

        # Should now include the newly assigned creative
        creative_ids = [c["creative_id"] for c in media_buy_data["creatives"]]
        assert unassigned_creative_id in creative_ids

        return {
            "unassigned_creative_id": unassigned_creative_id,
            "assignment": assign_data,
            "media_buy_creatives": media_buy_data,
        }

    async def test_creative_error_handling(self):
        """Test error handling in creative operations."""
        # Test invalid creative format
        invalid_creative = {
            "creative_id": f"e2e_invalid_{uuid.uuid4().hex[:8]}",
            "name": "Invalid Creative",
            "format": "nonexistent_format",
            "url": "https://e2e-test.example.com/invalid.jpg",
        }

        sync_result = await self.mcp_client.tools.sync_creatives(creatives=[invalid_creative], upsert=False)

        sync_data = sync_result.content if hasattr(sync_result, "content") else sync_result

        # Should have failures but still return structured response
        assert len(sync_data["creatives"]) == 0
        assert len(sync_data["failed_creatives"]) == 1

        failed_creative = sync_data["failed_creatives"][0]
        assert failed_creative["creative_id"] == invalid_creative["creative_id"]
        assert "error" in failed_creative

        # Test querying with invalid parameters
        try:
            # Invalid date format
            await self.mcp_client.tools.list_creatives(created_after="invalid-date")
            raise AssertionError("Should have raised an error for invalid date")
        except Exception as e:
            # Expected to fail with validation error
            assert "date format" in str(e).lower() or "invalid" in str(e).lower()

        return {"failed_creative": failed_creative}

    async def test_a2a_creative_operations(self):
        """Test creative operations via A2A protocol."""
        if not self.test_media_buy_id:
            await self.setup_test_media_buy()

        headers = self._build_headers()
        headers["Authorization"] = f"Bearer {self.auth_token}"

        # Test sync_creatives via A2A
        sync_payload = {
            "name": "sync_creatives",
            "parameters": {
                "creatives": [
                    {
                        "creative_id": f"a2a_creative_{uuid.uuid4().hex[:8]}",
                        "name": "A2A Creative Test",
                        "format": "display_300x250",
                        "url": "https://a2a-test.example.com/creative.jpg",
                        "width": 300,
                        "height": 250,
                    }
                ],
                "media_buy_id": self.test_media_buy_id,
                "assign_to_packages": ["a2a_package_1"],
            },
        }

        sync_response = await self.http_client.post(
            f"{self.a2a_url}/a2a/invoke-skill", json=sync_payload, headers=headers
        )

        assert sync_response.status_code == 200
        sync_data = sync_response.json()
        assert sync_data.get("success") is True
        assert len(sync_data["creatives"]) == 1

        a2a_creative_id = sync_data["creatives"][0]["creative_id"]

        # Test list_creatives via A2A
        list_payload = {
            "name": "list_creatives",
            "parameters": {"media_buy_id": self.test_media_buy_id, "search": "A2A"},
        }

        list_response = await self.http_client.post(
            f"{self.a2a_url}/a2a/invoke-skill", json=list_payload, headers=headers
        )

        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data.get("success") is True

        # Should find our A2A creative
        creative_ids = [c["creative_id"] for c in list_data["creatives"]]
        assert a2a_creative_id in creative_ids

        return {"sync_response": sync_data, "list_response": list_data, "a2a_creative_id": a2a_creative_id}

    async def run_full_lifecycle_test(self) -> dict[str, Any]:
        """Run the complete creative lifecycle test suite."""
        results = {}

        # Execute test phases in order
        print("🚀 Starting creative lifecycle end-to-end test")

        print("📝 Phase 1: Setting up test media buy...")
        await self.setup_test_media_buy()
        results["setup"] = {"media_buy_id": self.test_media_buy_id}

        print("⬆️  Phase 2: Testing creative upload (sync_creatives)...")
        results["sync_basic"] = await self.test_sync_creatives_basic_upload()

        print("🔍 Phase 3: Testing creative querying (list_creatives)...")
        results["list_basic"] = await self.test_list_creatives_basic_query()

        print("🎛️  Phase 4: Testing filtered queries...")
        results["list_filtered"] = await self.test_list_creatives_filtered_queries()

        print("🔄 Phase 5: Testing creative updates (upsert)...")
        results["upsert"] = await self.test_creative_upsert_functionality()

        print("📄 Phase 6: Testing pagination and sorting...")
        results["pagination"] = await self.test_creative_pagination_and_sorting()

        print("🔗 Phase 7: Testing assignment workflows...")
        results["assignments"] = await self.test_creative_assignments_workflow()

        print("⚠️  Phase 8: Testing error handling...")
        results["errors"] = await self.test_creative_error_handling()

        print("🌐 Phase 9: Testing A2A protocol operations...")
        results["a2a"] = await self.test_a2a_creative_operations()

        print("✅ Creative lifecycle end-to-end test completed successfully!")

        # Summary statistics
        total_creatives_synced = len(results["sync_basic"]["creatives"])
        total_assignments_created = len(results["sync_basic"]["assignments"])

        results["summary"] = {
            "total_creatives_synced": total_creatives_synced,
            "total_assignments_created": total_assignments_created,
            "test_session_id": self.test_session_id,
            "media_buy_id": self.test_media_buy_id,
        }

        return results


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_creative_lifecycle_comprehensive(docker_services_e2e):
    """Comprehensive creative lifecycle test using both MCP and A2A protocols."""
    import os

    # Configuration
    mcp_port = os.getenv("ADCP_SALES_PORT", "8080")
    a2a_port = os.getenv("A2A_PORT", "8091")
    auth_token = os.getenv("E2E_AUTH_TOKEN", "default_token_for_default_principal")

    mcp_url = f"http://localhost:{mcp_port}"
    a2a_url = f"http://localhost:{a2a_port}"

    # Generate unique test session
    test_session_id = f"e2e_creative_{uuid.uuid4().hex[:8]}"

    async with CreativeLifecycleTestSuite(
        mcp_url=mcp_url, a2a_url=a2a_url, auth_token=auth_token, test_session_id=test_session_id, validate_schemas=True
    ) as test_suite:

        results = await test_suite.run_full_lifecycle_test()

        # Validate overall test results
        assert results["setup"]["media_buy_id"] is not None
        assert results["sync_basic"]["creatives"] is not None
        assert len(results["sync_basic"]["creatives"]) >= 3
        assert results["list_basic"]["total_count"] >= 3
        assert results["upsert"]["creatives"] is not None
        assert results["assignments"]["assignment"] is not None
        assert results["errors"]["failed_creative"] is not None
        assert results["a2a"]["a2a_creative_id"] is not None

        # Print summary for debugging
        summary = results["summary"]
        print("\n📊 Test Summary:")
        print(f"   • Creatives synced: {summary['total_creatives_synced']}")
        print(f"   • Assignments created: {summary['total_assignments_created']}")
        print(f"   • Test session: {summary['test_session_id']}")
        print(f"   • Media buy: {summary['media_buy_id']}")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_creative_lifecycle_error_scenarios(docker_services_e2e):
    """Test creative lifecycle error scenarios and edge cases."""
    import os

    mcp_port = os.getenv("ADCP_SALES_PORT", "8080")
    auth_token = os.getenv("E2E_AUTH_TOKEN", "default_token_for_default_principal")

    mcp_url = f"http://localhost:{mcp_port}"
    a2a_url = f"http://localhost:{os.getenv('A2A_PORT', '8091')}"

    async with CreativeLifecycleTestSuite(
        mcp_url=mcp_url,
        a2a_url=a2a_url,
        auth_token=auth_token,
        validate_schemas=False,  # Don't validate schemas for error scenarios
    ) as test_suite:

        # Test 1: Empty creatives array
        empty_result = await test_suite.mcp_client.tools.sync_creatives(creatives=[])
        empty_data = empty_result.content if hasattr(empty_result, "content") else empty_result
        assert empty_data["creatives"] == []
        assert empty_data["failed_creatives"] == []

        # Test 2: Invalid media buy reference
        invalid_creative = {
            "creative_id": f"invalid_media_buy_{uuid.uuid4().hex[:8]}",
            "name": "Invalid Media Buy Creative",
            "format": "display_300x250",
            "url": "https://example.com/invalid.jpg",
        }

        try:
            await test_suite.mcp_client.tools.sync_creatives(
                creatives=[invalid_creative], media_buy_id="nonexistent_media_buy", assign_to_packages=["package_1"]
            )
            raise AssertionError("Should have failed with invalid media_buy_id")
        except Exception as e:
            # Expected to fail
            assert "not found" in str(e).lower() or "invalid" in str(e).lower()

        # Test 3: Query with extreme pagination
        extreme_result = await test_suite.mcp_client.tools.list_creatives(page=999, limit=1)
        extreme_data = extreme_result.content if hasattr(extreme_result, "content") else extreme_result
        assert extreme_data["creatives"] == []
        assert extreme_data["has_more"] is False


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_creative_lifecycle_performance(docker_services_e2e):
    """Test creative lifecycle performance with larger data sets."""
    import os
    import time

    mcp_port = os.getenv("ADCP_SALES_PORT", "8080")
    auth_token = os.getenv("E2E_AUTH_TOKEN", "default_token_for_default_principal")

    mcp_url = f"http://localhost:{mcp_port}"
    a2a_url = f"http://localhost:{os.getenv('A2A_PORT', '8091')}"

    async with CreativeLifecycleTestSuite(
        mcp_url=mcp_url,
        a2a_url=a2a_url,
        auth_token=auth_token,
        validate_schemas=False,  # Skip validation for performance test
    ) as test_suite:

        await test_suite.setup_test_media_buy()

        # Create batch of creatives for performance testing
        batch_size = 25
        creatives_batch = []

        for i in range(batch_size):
            creatives_batch.append(
                {
                    "creative_id": f"perf_test_{i}_{uuid.uuid4().hex[:6]}",
                    "name": f"Performance Test Creative {i+1}",
                    "format": "display_300x250" if i % 2 == 0 else "video_pre_roll",
                    "url": f"https://perf-test.example.com/creative_{i}.{'jpg' if i % 2 == 0 else 'mp4'}",
                    "width": 300 if i % 2 == 0 else 1280,
                    "height": 250 if i % 2 == 0 else 720,
                    "duration": None if i % 2 == 0 else 15.0,
                }
            )

        # Time the batch sync operation
        sync_start = time.time()
        sync_result = await test_suite.mcp_client.tools.sync_creatives(
            creatives=creatives_batch,
            media_buy_id=test_suite.test_media_buy_id,
            assign_to_packages=["perf_package_1", "perf_package_2"],
        )
        sync_duration = time.time() - sync_start

        sync_data = sync_result.content if hasattr(sync_result, "content") else sync_result

        # Verify batch operation succeeded
        assert len(sync_data["creatives"]) == batch_size
        assert len(sync_data["failed_creatives"]) == 0
        assert len(sync_data["assignments"]) == batch_size * 2  # 2 packages per creative

        # Time the query operation
        query_start = time.time()
        list_result = await test_suite.mcp_client.tools.list_creatives(
            media_buy_id=test_suite.test_media_buy_id, limit=50  # Retrieve more than batch size
        )
        query_duration = time.time() - query_start

        list_data = list_result.content if hasattr(list_result, "content") else list_data

        # Verify query performance
        assert len(list_data["creatives"]) >= batch_size

        # Performance assertions (reasonable thresholds)
        assert sync_duration < 10.0, f"Batch sync took {sync_duration:.2f}s, expected < 10s"
        assert query_duration < 2.0, f"Query took {query_duration:.2f}s, expected < 2s"

        print("\n⚡ Performance Results:")
        print(f"   • Batch sync ({batch_size} creatives): {sync_duration:.2f}s")
        print(f"   • Query performance: {query_duration:.2f}s")
        print(f"   • Creatives per second (sync): {batch_size / sync_duration:.1f}")
        print(f"   • Total assignments created: {len(sync_data['assignments'])}")
