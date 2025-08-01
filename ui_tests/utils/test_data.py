import random
import string
from datetime import datetime, timedelta
from typing import Dict, List

class TestDataGenerator:
    """Generate test data for UI tests."""
    
    @staticmethod
    def generate_tenant_name() -> str:
        """Generate unique tenant name."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"Test Publisher {timestamp}"
    
    @staticmethod
    def generate_subdomain() -> str:
        """Generate unique subdomain."""
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"test-{random_suffix}"
    
    @staticmethod
    def generate_principal_data() -> Dict[str, str]:
        """Generate principal (advertiser) test data."""
        random_id = ''.join(random.choices(string.digits, k=8))
        return {
            "name": f"Test Advertiser {random_id}",
            "email": f"advertiser{random_id}@test.com",
            "platform_mappings": {
                "google_ad_manager": f"advertiser_{random_id}",
                "mock": f"mock_advertiser_{random_id}"
            }
        }
    
    @staticmethod
    def generate_product_data() -> Dict[str, any]:
        """Generate product test data."""
        random_id = ''.join(random.choices(string.digits, k=6))
        return {
            "name": f"Test Product {random_id}",
            "description": f"Test product description for automated testing",
            "type": "guaranteed",
            "min_spend": 1000.0,
            "max_spend": 10000.0,
            "countries": ["US", "CA"],
            "formats": ["display_300x250", "display_728x90"],
            "targeting_dimensions": {
                "geo": ["city", "region", "country"],
                "device": ["device_type", "os"],
                "audience": ["age", "gender"]
            }
        }
    
    @staticmethod
    def generate_media_buy_data() -> Dict[str, any]:
        """Generate media buy test data."""
        start_date = datetime.now() + timedelta(days=7)
        end_date = start_date + timedelta(days=30)
        
        return {
            "budget": random.randint(5000, 20000),
            "flight_start": start_date.strftime("%Y-%m-%d"),
            "flight_end": end_date.strftime("%Y-%m-%d"),
            "targeting": {
                "geo": {
                    "countries": ["US"],
                    "regions": ["CA", "NY"]
                },
                "device": {
                    "device_types": ["mobile", "desktop"]
                }
            }
        }
    
    @staticmethod
    def generate_creative_data(format_type: str = "display_300x250") -> Dict[str, str]:
        """Generate creative test data."""
        random_id = ''.join(random.choices(string.digits, k=6))
        return {
            "name": f"Test Creative {random_id}",
            "format": format_type,
            "url": f"https://example.com/creative_{random_id}.jpg",
            "click_url": f"https://example.com/landing_{random_id}",
            "alt_text": f"Test creative alt text {random_id}"
        }

class TestConstants:
    """Constants used in UI tests."""
    
    # Timeouts
    DEFAULT_TIMEOUT = 30000  # 30 seconds
    SHORT_TIMEOUT = 5000     # 5 seconds
    LONG_TIMEOUT = 60000     # 60 seconds
    
    # Test environment
    DEFAULT_BASE_URL = "http://localhost:8001"
    DEFAULT_MCP_URL = "http://localhost:8080"
    
    # Test data
    BILLING_PLANS = ["basic", "standard", "enterprise"]
    ADAPTER_TYPES = ["google_ad_manager", "mock", "kevel", "triton_digital"]
    CREATIVE_FORMATS = [
        "display_300x250",
        "display_728x90", 
        "display_970x250",
        "video_instream",
        "video_outstream",
        "audio_companion"
    ]
    
    # Expected messages
    SUCCESS_MESSAGES = {
        "tenant_created": "successfully created",
        "product_created": "Product created successfully",
        "media_buy_created": "Media buy created successfully",
        "creative_approved": "Creative approved",
        "task_completed": "Task completed successfully"
    }
    
    ERROR_MESSAGES = {
        "auth_failed": "Authentication failed",
        "permission_denied": "Permission denied",
        "invalid_data": "Invalid data provided",
        "duplicate_entry": "already exists"
    }