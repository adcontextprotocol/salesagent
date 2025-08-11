# Fixture Usage Guide

## Overview

The AdCP Sales Agent test suite provides a comprehensive set of fixtures and mocks to make testing easier and more maintainable. This guide explains how to use these fixtures effectively.

## Fixture Organization

```
tests/fixtures/
├── __init__.py         # Main fixture module
├── factories.py        # Object factories
├── mocks.py           # Mock services
├── builders.py        # Complex object builders
└── data/              # JSON test data
    ├── sample_products.json
    └── sample_creatives.json
```

## Factory Classes

### TenantFactory

Creates test tenant objects with default or custom data.

```python
def test_with_tenant(tenant_factory):
    # Create with defaults
    tenant = tenant_factory.create()
    
    # Create with custom data
    tenant = tenant_factory.create(
        name="Custom Publisher",
        subdomain="custom",
        config={"features": {"max_daily_budget": 50000}}
    )
    
    # Create multiple tenants
    tenants = tenant_factory.create_batch(5)
```

### PrincipalFactory

Creates test principal (advertiser) objects.

```python
def test_with_principal(principal_factory, sample_tenant):
    # Create principal for tenant
    principal = principal_factory.create(
        tenant_id=sample_tenant["tenant_id"],
        name="Test Advertiser"
    )
    
    # Create with tenant
    tenant, principal = principal_factory.create_with_tenant()
```

### ProductFactory

Creates test product objects.

```python
def test_with_products(product_factory, sample_tenant):
    # Create display product
    product = product_factory.create(
        tenant_id=sample_tenant["tenant_id"],
        formats=["display_300x250", "display_728x90"]
    )
    
    # Create video product
    video = product_factory.create_video_product(
        tenant_id=sample_tenant["tenant_id"]
    )
```

### MediaBuyFactory

Creates test media buy objects.

```python
def test_with_media_buy(media_buy_factory, sample_tenant, sample_principal):
    # Create draft media buy
    buy = media_buy_factory.create(
        tenant_id=sample_tenant["tenant_id"],
        principal_id=sample_principal["principal_id"],
        total_budget=10000.0
    )
    
    # Create active media buy
    active_buy = media_buy_factory.create_active(
        tenant_id=sample_tenant["tenant_id"],
        principal_id=sample_principal["principal_id"]
    )
```

### CreativeFactory

Creates test creative objects.

```python
def test_with_creatives(creative_factory, sample_tenant, sample_principal):
    # Create pending creative
    creative = creative_factory.create(
        tenant_id=sample_tenant["tenant_id"],
        principal_id=sample_principal["principal_id"],
        format_id="display_300x250"
    )
    
    # Create approved creative
    approved = creative_factory.create_approved()
    
    # Create video creative
    video = creative_factory.create_video_creative()
```

## Mock Objects

### MockDatabase

Simulates database operations without a real database.

```python
def test_with_mock_db(mock_db):
    # Set query results
    mock_db.set_query_result(
        "SELECT * FROM tenants WHERE tenant_id = ?",
        [{"tenant_id": "test", "name": "Test Tenant"}]
    )
    
    # Execute query
    cursor = mock_db.execute("SELECT * FROM tenants WHERE tenant_id = ?", ("test",))
    result = cursor.fetchone()
    
    # Check execution history
    assert len(mock_db.execute_history) == 1
    assert mock_db.committed
```

### MockAdapter

Simulates ad server adapter operations.

```python
def test_with_mock_adapter(mock_adapter):
    # Create media buy
    response = mock_adapter.create_media_buy(request)
    assert response["success"]
    assert "media_buy_id" in response
    
    # Check API calls
    assert len(mock_adapter.api_calls) == 1
    assert mock_adapter.api_calls[0][0] == "create_media_buy"
    
    # Test dry-run mode
    dry_adapter = MockAdapter(dry_run=True)
    response = dry_adapter.create_media_buy(request)
    assert response["dry_run"]
    assert "api_calls" in response
```

### MockGeminiService

Simulates Google Gemini AI service.

```python
def test_with_mock_gemini(mock_gemini):
    # Set specific response
    mock_gemini.set_response(
        "Generate product description",
        {"description": "AI generated description"}
    )
    
    # Generate content
    response = mock_gemini.generate_content("Generate product description")
    assert "AI generated" in response.text
    
    # Check API calls
    assert len(mock_gemini.api_calls) == 1
```

### MockOAuthProvider

Simulates OAuth authentication provider.

```python
def test_with_mock_oauth(mock_oauth):
    # Add authorized user
    mock_oauth.add_user("test@example.com", "Test User")
    
    # Set current user
    mock_oauth.set_current_user("test@example.com")
    
    # Authorize
    token_data = mock_oauth.authorize_access_token()
    assert token_data["userinfo"]["email"] == "test@example.com"
```

## Builder Classes

### RequestBuilder

Builds API request objects fluently.

```python
def test_with_request_builder(request_builder):
    request = (request_builder
        .with_auth("test_token")
        .with_tenant("test_tenant")
        .with_media_buy(
            product_ids=["prod_1", "prod_2"],
            total_budget=5000.0
        )
        .with_targeting({
            "geo_country_any_of": ["US"],
            "device_type_any_of": ["desktop"]
        })
        .build()
    )
    
    assert request["headers"]["x-adcp-auth"] == "test_token"
    assert request["data"]["total_budget"] == 5000.0
```

### ResponseBuilder

Builds API response objects.

```python
def test_with_response_builder(response_builder):
    response = (response_builder
        .with_success()
        .with_media_buy("mb_123")
        .with_data(impressions=1000, clicks=50)
        .build()
    )
    
    assert response["data"]["success"]
    assert response["data"]["media_buy_id"] == "mb_123"
    assert response["status_code"] == 200
```

### TargetingBuilder

Builds targeting specifications.

```python
def test_with_targeting_builder(targeting_builder):
    # Build custom targeting
    targeting = (targeting_builder
        .with_geo(countries=["US", "CA"])
        .with_demographics(age_ranges=["25-34", "35-44"])
        .with_devices(types=["desktop", "mobile"])
        .with_signals(["auto_intenders_q1_2025"])
        .build()
    )
    
    # Use preset targeting
    minimal = targeting_builder.build_minimal()
    comprehensive = targeting_builder.build_comprehensive()
```

## Fixture Usage in Tests

### Unit Tests

```python
import pytest
from unittest.mock import patch

class TestMediaBuyCreation:
    def test_create_media_buy_success(
        self, 
        mock_adapter,
        sample_tenant,
        sample_principal,
        request_builder
    ):
        """Test successful media buy creation."""
        # Build request
        request = (request_builder
            .with_auth(sample_principal["access_token"])
            .with_media_buy(total_budget=10000.0)
            .build()
        )
        
        # Execute
        response = mock_adapter.create_media_buy(request["data"])
        
        # Assert
        assert response["success"]
        assert "media_buy_id" in response
```

### Integration Tests

```python
class TestDatabaseOperations:
    def test_tenant_creation(self, db_session, tenant_factory):
        """Test creating tenant in database."""
        # Create tenant data
        tenant_data = tenant_factory.create()
        
        # Insert into database
        db_session.execute(
            "INSERT INTO tenants (...) VALUES (...)",
            tenant_data
        )
        db_session.commit()
        
        # Verify
        cursor = db_session.execute(
            "SELECT * FROM tenants WHERE tenant_id = ?",
            (tenant_data["tenant_id"],)
        )
        result = cursor.fetchone()
        assert result is not None
```

### Flask Tests

```python
class TestAdminUI:
    def test_authenticated_access(
        self,
        authenticated_client,
        mock_db_with_data
    ):
        """Test authenticated access to admin pages."""
        response = authenticated_client.get("/")
        assert response.status_code == 200
    
    def test_tenant_admin_access(
        self,
        flask_client,
        tenant_admin_session,
        sample_tenant
    ):
        """Test tenant admin access."""
        with flask_client.session_transaction() as sess:
            sess.update(tenant_admin_session)
        
        response = flask_client.get(f"/tenant/{sample_tenant['tenant_id']}")
        assert response.status_code == 200
```

## Loading Test Data

### From JSON Files

```python
def test_with_json_data(load_fixture_json):
    """Test using JSON fixture data."""
    products = load_fixture_json("sample_products.json")
    
    assert "run_of_site" in products
    assert products["run_of_site"]["min_cpm"] == 5.0
```

### From Fixture Path

```python
def test_with_fixture_path(fixture_data_path):
    """Test accessing fixture files directly."""
    import json
    
    creative_file = fixture_data_path / "sample_creatives.json"
    with open(creative_file) as f:
        creatives = json.load(f)
    
    assert "display_300x250" in creatives
```

## Complete Test Scenarios

### Using TestDataBuilder

```python
from tests.fixtures.builders import TestDataBuilder

def test_complete_scenario():
    """Test complete campaign workflow."""
    # Build complete test scenario
    scenario = (TestDataBuilder()
        .with_tenant(name="Test Publisher")
        .with_principal(name="Test Advertiser")
        .with_products(count=3)
        .with_media_buy(total_budget=10000.0)
        .with_creatives(count=2)
        .build()
    )
    
    # Use scenario data
    tenant = scenario["tenant"]
    principal = scenario["principal"]
    products = scenario["products"]
    media_buy = scenario["media_buys"][0]
    creatives = scenario["creatives"]
    
    # Test with complete data...
```

## Performance Testing

### Using Benchmark Fixture

```python
def test_performance(benchmark, large_dataset):
    """Test operation performance."""
    # Benchmark automatically measures time
    result = expensive_operation(large_dataset)
    
    assert result
    # Time will be printed and test marked as slow if > 5s
```

## Best Practices

### 1. Use Appropriate Fixtures

- **Unit Tests**: Use mocks and factories
- **Integration Tests**: Use test database and builders
- **E2E Tests**: Use complete scenarios

### 2. Keep Fixtures Focused

```python
# Good - focused fixture
@pytest.fixture
def active_media_buy(media_buy_factory, sample_tenant):
    return media_buy_factory.create_active(
        tenant_id=sample_tenant["tenant_id"]
    )

# Bad - doing too much
@pytest.fixture
def everything():
    # Creates tenant, principal, products, media buys, creatives...
    pass
```

### 3. Use Factory Defaults

```python
# Good - use defaults where possible
tenant = tenant_factory.create()

# Only override what's needed
tenant = tenant_factory.create(billing_plan="premium")
```

### 4. Mock External Dependencies

```python
@patch('requests.post')
def test_external_api(mock_post, mock_adapter):
    """Always mock external API calls."""
    mock_post.return_value.json.return_value = {"status": "ok"}
    
    # Test without making real API calls
    result = mock_adapter.create_media_buy(request)
    assert result["success"]
```

### 5. Clean Up Resources

```python
@pytest.fixture
def temp_file():
    """Fixture that cleans up after itself."""
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False) as f:
        path = f.name
    
    yield path
    
    # Cleanup
    os.unlink(path)
```

## Common Patterns

### Testing with Multiple Fixtures

```python
def test_complex_workflow(
    mock_db_with_data,
    mock_adapter,
    mock_gemini,
    request_builder,
    response_builder
):
    """Combine multiple fixtures for complex tests."""
    # All fixtures are available and ready to use
    pass
```

### Parametrized Tests with Fixtures

```python
@pytest.mark.parametrize("budget,expected", [
    (1000, "standard"),
    (5000, "premium"),
    (10000, "enterprise")
])
def test_budget_tiers(media_buy_factory, budget, expected):
    """Test different budget tiers."""
    buy = media_buy_factory.create(total_budget=budget)
    tier = calculate_tier(buy)
    assert tier == expected
```

### Fixture Inheritance

```python
@pytest.fixture
def premium_tenant(tenant_factory):
    """Specialized tenant fixture."""
    return tenant_factory.create(billing_plan="premium")

@pytest.fixture
def premium_principal(principal_factory, premium_tenant):
    """Principal for premium tenant."""
    return principal_factory.create(
        tenant_id=premium_tenant["tenant_id"]
    )
```

## Troubleshooting

### Fixture Not Found

```python
# Error: fixture 'sample_tenant' not found

# Solution: Import from conftest or add to local conftest
# tests/conftest.py already provides common fixtures
```

### Fixture Scope Issues

```python
# Error: ScopeMismatch

# Solution: Match fixture scopes
@pytest.fixture(scope="session")  # Long-lived
@pytest.fixture(scope="module")   # Per-module
@pytest.fixture(scope="class")    # Per-class
@pytest.fixture(scope="function") # Default, per-test
```

### Mock Not Working

```python
# Ensure mocking the right import
@patch('module.actual_import_path')  # Not where it's defined

# For module-level imports, mock before import
with patch('module.function'):
    from module import something
```

## Advanced Usage

### Custom Fixture Plugins

Create reusable fixture plugins for specific test scenarios:

```python
# tests/fixtures/plugins/gam_plugin.py
import pytest

@pytest.fixture
def gam_setup(mock_adapter):
    """Complete GAM test setup."""
    mock_adapter.platform = "google_ad_manager"
    # Configure for GAM testing...
    return mock_adapter
```

### Dynamic Fixtures

Generate fixtures based on test parameters:

```python
def pytest_generate_tests(metafunc):
    """Generate test cases dynamically."""
    if "product_type" in metafunc.fixturenames:
        metafunc.parametrize(
            "product_type",
            ["display", "video", "native", "audio"]
        )
```

This comprehensive fixture system provides everything needed for effective testing of the AdCP Sales Agent!