"""
Mock objects for testing.

These mocks simulate external dependencies and services.
"""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock
from datetime import datetime, timezone
import uuid


class MockDatabase:
    """Mock database connection for testing."""
    
    def __init__(self):
        """Initialize mock database."""
        self.data = {}
        self.execute_history = []
        self.committed = False
        self.rolled_back = False
        
    def execute(self, query: str, params: tuple = None):
        """Mock execute method."""
        self.execute_history.append((query, params))
        return MockCursor(self.data)
    
    def commit(self):
        """Mock commit method."""
        self.committed = True
    
    def rollback(self):
        """Mock rollback method."""
        self.rolled_back = True
        
    def close(self):
        """Mock close method."""
        pass
    
    def set_query_result(self, query_pattern: str, result: Any):
        """Set result for a query pattern."""
        self.data[query_pattern] = result
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


class MockCursor:
    """Mock database cursor."""
    
    def __init__(self, data: Dict = None):
        """Initialize mock cursor."""
        self.data = data or {}
        self.rowcount = 0
        self.lastrowid = None
        self._result = None
        
    def fetchone(self):
        """Mock fetchone method."""
        if self._result and len(self._result) > 0:
            return self._result[0] if isinstance(self._result, list) else self._result
        return None
    
    def fetchall(self):
        """Mock fetchall method."""
        return self._result if isinstance(self._result, list) else [self._result] if self._result else []
    
    def set_result(self, result):
        """Set the result for fetch operations."""
        self._result = result
        self.rowcount = len(result) if isinstance(result, list) else 1 if result else 0
        return self


class MockAdapter:
    """Mock ad server adapter for testing."""
    
    def __init__(self, principal=None, dry_run=False):
        """Initialize mock adapter."""
        self.principal = principal
        self.dry_run = dry_run
        self.api_calls = []
        self.created_items = []
        self.updated_items = []
        
    def create_media_buy(self, request):
        """Mock create media buy."""
        buy_id = f"mock_buy_{uuid.uuid4().hex[:8]}"
        self.api_calls.append(("create_media_buy", request))
        
        if self.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "api_calls": [
                    {
                        "method": "POST",
                        "endpoint": "/api/campaigns",
                        "payload": request.dict()
                    }
                ]
            }
        
        self.created_items.append(buy_id)
        return {
            "success": True,
            "media_buy_id": buy_id,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_media_buy_status(self, media_buy_id: str):
        """Mock get media buy status."""
        self.api_calls.append(("get_media_buy_status", media_buy_id))
        
        return {
            "media_buy_id": media_buy_id,
            "status": "active",
            "impressions": 150000,
            "clicks": 1500,
            "spend": 1500.0,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def update_media_buy(self, media_buy_id: str, updates: Dict):
        """Mock update media buy."""
        self.api_calls.append(("update_media_buy", media_buy_id, updates))
        self.updated_items.append(media_buy_id)
        
        return {
            "success": True,
            "media_buy_id": media_buy_id,
            "updated": True
        }
    
    def pause_media_buy(self, media_buy_id: str):
        """Mock pause media buy."""
        self.api_calls.append(("pause_media_buy", media_buy_id))
        
        return {
            "success": True,
            "media_buy_id": media_buy_id,
            "status": "paused"
        }
    
    def get_reporting(self, media_buy_id: str, start_date=None, end_date=None):
        """Mock get reporting."""
        self.api_calls.append(("get_reporting", media_buy_id, start_date, end_date))
        
        return {
            "media_buy_id": media_buy_id,
            "metrics": {
                "impressions": 250000,
                "clicks": 2500,
                "ctr": 0.01,
                "spend": 2500.0,
                "conversions": 50
            },
            "period": {
                "start": start_date,
                "end": end_date
            }
        }


class MockGeminiService:
    """Mock Gemini AI service for testing."""
    
    def __init__(self):
        """Initialize mock Gemini service."""
        self.api_calls = []
        self.responses = {}
        
    def generate_content(self, prompt: str, **kwargs):
        """Mock content generation."""
        self.api_calls.append(("generate_content", prompt, kwargs))
        
        # Return predefined response or default
        if prompt in self.responses:
            return MockGeminiResponse(self.responses[prompt])
        
        # Default response based on prompt content
        if "product" in prompt.lower():
            return MockGeminiResponse({
                "name": "AI Generated Product",
                "description": "This is an AI generated product description",
                "formats": ["display_300x250", "display_728x90"],
                "targeting": {
                    "geo_country": ["US"],
                    "device_type": ["desktop", "mobile"]
                },
                "pricing": {
                    "min_cpm": 5.0,
                    "recommended_cpm": 10.0
                }
            })
        
        return MockGeminiResponse("Generated content for: " + prompt[:50])
    
    def set_response(self, prompt_pattern: str, response: Any):
        """Set a specific response for a prompt pattern."""
        self.responses[prompt_pattern] = response


class MockGeminiResponse:
    """Mock Gemini API response."""
    
    def __init__(self, content):
        """Initialize mock response."""
        self.content = content
        
    @property
    def text(self):
        """Get text content."""
        if isinstance(self.content, dict):
            return json.dumps(self.content)
        return str(self.content)
    
    @property
    def parts(self):
        """Get response parts."""
        return [{"text": self.text}]


class MockOAuthProvider:
    """Mock OAuth provider for testing."""
    
    def __init__(self):
        """Initialize mock OAuth provider."""
        self.authorized_users = {
            "test@example.com": {
                "email": "test@example.com",
                "name": "Test User",
                "picture": "https://example.com/photo.jpg"
            },
            "admin@example.com": {
                "email": "admin@example.com",
                "name": "Admin User",
                "picture": "https://example.com/admin.jpg"
            }
        }
        self.auth_calls = []
        
    def authorize_redirect(self, redirect_uri: str, **kwargs):
        """Mock authorize redirect."""
        self.auth_calls.append(("authorize_redirect", redirect_uri, kwargs))
        response = Mock()
        response.location = f"https://oauth.provider.com/auth?redirect_uri={redirect_uri}"
        response.status_code = 302
        return response
    
    def authorize_access_token(self):
        """Mock authorize access token."""
        self.auth_calls.append(("authorize_access_token",))
        return {
            "access_token": f"mock_token_{uuid.uuid4().hex[:8]}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "userinfo": self.get_current_user()
        }
    
    def get_current_user(self):
        """Get current user info."""
        # Return first authorized user by default
        return list(self.authorized_users.values())[0]
    
    def set_current_user(self, email: str):
        """Set the current user for testing."""
        if email in self.authorized_users:
            self.current_user_email = email
            return self.authorized_users[email]
        return None
    
    def add_user(self, email: str, name: str = None):
        """Add an authorized user."""
        self.authorized_users[email] = {
            "email": email,
            "name": name or f"User {email.split('@')[0]}",
            "picture": f"https://example.com/{email.split('@')[0]}.jpg"
        }


class MockHTTPRequest:
    """Mock HTTP request for testing."""
    
    def __init__(self, headers: Dict = None, json_data: Dict = None, form_data: Dict = None):
        """Initialize mock request."""
        self.headers = headers or {}
        self.json = json_data
        self.form = form_data
        self.args = {}
        self.method = "GET"
        self.path = "/"
        
    def get_json(self):
        """Get JSON data."""
        return self.json
    
    def get_header(self, name: str, default=None):
        """Get header value."""
        return self.headers.get(name, default)


class MockHTTPResponse:
    """Mock HTTP response for testing."""
    
    def __init__(self, data: Any = None, status_code: int = 200, headers: Dict = None):
        """Initialize mock response."""
        self.data = data
        self.status_code = status_code
        self.headers = headers or {}
        
    @property
    def json(self):
        """Get JSON data."""
        if isinstance(self.data, str):
            return json.loads(self.data)
        return self.data
    
    @property
    def text(self):
        """Get text data."""
        if isinstance(self.data, dict):
            return json.dumps(self.data)
        return str(self.data)