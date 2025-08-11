"""
Builder classes for constructing complex test objects.

These builders provide fluent interfaces for creating test data.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import json


class RequestBuilder:
    """Builder for constructing API request objects."""
    
    def __init__(self):
        """Initialize request builder."""
        self.data = {}
        self.headers = {}
        
    def with_auth(self, token: str):
        """Add authentication."""
        self.headers["x-adcp-auth"] = token
        return self
    
    def with_tenant(self, tenant_id: str):
        """Add tenant context."""
        self.headers["x-tenant-id"] = tenant_id
        return self
    
    def with_data(self, **kwargs):
        """Add request data."""
        self.data.update(kwargs)
        return self
    
    def with_media_buy(
        self,
        product_ids: List[str] = None,
        total_budget: float = 5000.0,
        flight_start_date: str = None,
        flight_end_date: str = None,
        **kwargs
    ):
        """Add media buy data."""
        self.data.update({
            "product_ids": product_ids or [f"prod_{uuid.uuid4().hex[:8]}"],
            "total_budget": total_budget,
            "flight_start_date": flight_start_date or datetime.now(timezone.utc).date().isoformat(),
            "flight_end_date": flight_end_date or (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat(),
            **kwargs
        })
        return self
    
    def with_creative(
        self,
        format_id: str = "display_300x250",
        content: Dict = None,
        **kwargs
    ):
        """Add creative data."""
        default_content = {
            "headline": "Test Ad",
            "body": "Test ad content",
            "image_url": "https://example.com/image.jpg",
            "click_url": "https://example.com/landing"
        }
        
        self.data.update({
            "format_id": format_id,
            "content": content or default_content,
            **kwargs
        })
        return self
    
    def with_targeting(self, targeting: Dict):
        """Add targeting overlay."""
        self.data["targeting_overlay"] = targeting
        return self
    
    def build(self) -> Dict:
        """Build the request object."""
        return {
            "headers": self.headers,
            "data": self.data
        }
    
    def build_json(self) -> str:
        """Build as JSON string."""
        return json.dumps(self.build())


class ResponseBuilder:
    """Builder for constructing API response objects."""
    
    def __init__(self):
        """Initialize response builder."""
        self.data = {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.status_code = 200
        
    def with_success(self, success: bool = True):
        """Set success status."""
        self.data["success"] = success
        if not success:
            self.status_code = 400
        return self
    
    def with_error(self, error: str, code: int = 400):
        """Add error response."""
        self.data["success"] = False
        self.data["error"] = error
        self.status_code = code
        return self
    
    def with_data(self, **kwargs):
        """Add response data."""
        self.data.update(kwargs)
        return self
    
    def with_media_buy(self, media_buy_id: str = None, **kwargs):
        """Add media buy response data."""
        self.data.update({
            "media_buy_id": media_buy_id or f"mb_{uuid.uuid4().hex[:8]}",
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
        return self
    
    def with_creative(self, creative_id: str = None, **kwargs):
        """Add creative response data."""
        self.data.update({
            "creative_id": creative_id or f"creative_{uuid.uuid4().hex[:8]}",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
        return self
    
    def with_products(self, products: List[Dict] = None):
        """Add products list."""
        if products is None:
            products = [
                {
                    "product_id": f"prod_{i}",
                    "name": f"Product {i}",
                    "formats": ["display_300x250"],
                    "min_cpm": 5.0
                }
                for i in range(3)
            ]
        self.data["products"] = products
        return self
    
    def with_status_code(self, code: int):
        """Set HTTP status code."""
        self.status_code = code
        return self
    
    def build(self) -> Dict:
        """Build the response object."""
        return {
            "data": self.data,
            "status_code": self.status_code
        }
    
    def build_json(self) -> str:
        """Build as JSON string."""
        return json.dumps(self.data)


class TargetingBuilder:
    """Builder for constructing targeting specifications."""
    
    def __init__(self):
        """Initialize targeting builder."""
        self.targeting = {}
        
    def with_geo(
        self,
        countries: List[str] = None,
        regions: List[str] = None,
        cities: List[str] = None,
        zip_codes: List[str] = None
    ):
        """Add geographic targeting."""
        if countries:
            self.targeting["geo_country_any_of"] = countries
        if regions:
            self.targeting["geo_region_any_of"] = regions
        if cities:
            self.targeting["geo_city_any_of"] = cities
        if zip_codes:
            self.targeting["geo_zip_any_of"] = zip_codes
        return self
    
    def with_demographics(
        self,
        age_ranges: List[str] = None,
        genders: List[str] = None,
        income_ranges: List[str] = None
    ):
        """Add demographic targeting."""
        if age_ranges:
            self.targeting["demo_age_range_any_of"] = age_ranges
        if genders:
            self.targeting["demo_gender_any_of"] = genders
        if income_ranges:
            self.targeting["demo_income_range_any_of"] = income_ranges
        return self
    
    def with_devices(
        self,
        types: List[str] = None,
        os: List[str] = None,
        browsers: List[str] = None
    ):
        """Add device targeting."""
        if types:
            self.targeting["device_type_any_of"] = types
        if os:
            self.targeting["device_os_any_of"] = os
        if browsers:
            self.targeting["browser_any_of"] = browsers
        return self
    
    def with_content(
        self,
        categories: List[str] = None,
        keywords: List[str] = None,
        topics: List[str] = None
    ):
        """Add content targeting."""
        if categories:
            self.targeting["content_category_any_of"] = categories
        if keywords:
            self.targeting["content_keyword_any_of"] = keywords
        if topics:
            self.targeting["content_topic_any_of"] = topics
        return self
    
    def with_signals(self, signals: List[str]):
        """Add AEE signals."""
        self.targeting["signals"] = signals
        return self
    
    def with_custom(self, key: str, value: Any):
        """Add custom targeting dimension."""
        self.targeting[key] = value
        return self
    
    def build(self) -> Dict:
        """Build the targeting object."""
        return self.targeting
    
    def build_minimal(self) -> Dict:
        """Build minimal targeting for testing."""
        return {
            "geo_country_any_of": ["US"],
            "device_type_any_of": ["desktop", "mobile"]
        }
    
    def build_comprehensive(self) -> Dict:
        """Build comprehensive targeting for testing."""
        return {
            "geo_country_any_of": ["US", "CA"],
            "geo_region_any_of": ["CA", "NY", "TX"],
            "demo_age_range_any_of": ["25-34", "35-44"],
            "demo_gender_any_of": ["all"],
            "device_type_any_of": ["desktop", "mobile", "tablet"],
            "device_os_any_of": ["ios", "android", "windows"],
            "browser_any_of": ["chrome", "safari", "firefox"],
            "content_category_any_of": ["news", "sports", "entertainment"],
            "daypart_timezone": "America/New_York",
            "daypart_days_any_of": ["mon", "tue", "wed", "thu", "fri"],
            "daypart_hours_any_of": list(range(9, 18)),  # 9am-5pm
            "frequency_cap_impressions": 3,
            "frequency_cap_period": "day",
            "viewability": 0.7,
            "brand_safety_sensitive_categories_none_of": ["adult", "violence"],
            "signals": ["auto_intenders_q1_2025", "sports_enthusiasts"]
        }


class TestDataBuilder:
    """Builder for complete test scenarios."""
    
    def __init__(self):
        """Initialize test data builder."""
        self.tenant = None
        self.principal = None
        self.products = []
        self.media_buys = []
        self.creatives = []
        
    def with_tenant(self, **kwargs):
        """Add tenant."""
        from .factories import TenantFactory
        self.tenant = TenantFactory.create(**kwargs)
        return self
    
    def with_principal(self, **kwargs):
        """Add principal."""
        from .factories import PrincipalFactory
        if self.tenant:
            kwargs["tenant_id"] = self.tenant["tenant_id"]
        self.principal = PrincipalFactory.create(**kwargs)
        return self
    
    def with_products(self, count: int = 3, **kwargs):
        """Add products."""
        from .factories import ProductFactory
        if self.tenant:
            kwargs["tenant_id"] = self.tenant["tenant_id"]
        self.products = [ProductFactory.create(**kwargs) for _ in range(count)]
        return self
    
    def with_media_buy(self, **kwargs):
        """Add media buy."""
        from .factories import MediaBuyFactory
        if self.tenant:
            kwargs["tenant_id"] = self.tenant["tenant_id"]
        if self.principal:
            kwargs["principal_id"] = self.principal["principal_id"]
        self.media_buys.append(MediaBuyFactory.create(**kwargs))
        return self
    
    def with_creatives(self, count: int = 2, **kwargs):
        """Add creatives."""
        from .factories import CreativeFactory
        if self.tenant:
            kwargs["tenant_id"] = self.tenant["tenant_id"]
        if self.principal:
            kwargs["principal_id"] = self.principal["principal_id"]
        self.creatives = [CreativeFactory.create(**kwargs) for _ in range(count)]
        return self
    
    def build(self) -> Dict:
        """Build complete test scenario."""
        return {
            "tenant": self.tenant,
            "principal": self.principal,
            "products": self.products,
            "media_buys": self.media_buys,
            "creatives": self.creatives
        }
    
    def build_complete_scenario(self) -> Dict:
        """Build a complete test scenario with all entities."""
        return (
            self.with_tenant(name="Test Publisher")
            .with_principal(name="Test Advertiser")
            .with_products(count=3)
            .with_media_buy(total_budget=10000.0)
            .with_creatives(count=2)
            .build()
        )