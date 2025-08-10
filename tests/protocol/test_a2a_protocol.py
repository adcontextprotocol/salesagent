#!/usr/bin/env python
"""
Comprehensive A2A Protocol Test Suite

Consolidates all A2A protocol tests including:
- Unit tests for facade and response formats
- Integration tests for full conversations
- Structured data validation
- A2A Inspector format compatibility
"""

import httpx
import json
import pytest
from typing import Dict, Any, List
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock


class TestA2AProtocolUnit:
    """Unit tests for A2A protocol implementation."""
    
    @pytest.fixture
    def mock_executor(self):
        """Create a mock TaskExecutor."""
        from task_executor import TaskExecutor, TaskStatus, TaskResult
        
        executor = Mock(spec=TaskExecutor)
        executor.send_message = Mock(return_value={
            "kind": "message",
            "messageId": "test_msg_id",
            "role": "agent",
            "parts": [{"kind": "text", "text": "response"}],
            "contextId": "test_ctx",
            "timestamp": datetime.utcnow().isoformat()
        })
        executor.get_products = AsyncMock(return_value=TaskResult(
            status=TaskStatus.COMPLETED,
            task_id="task_123",
            data={"products": [
                {"product_id": "prod_001", "name": "Sports Video Premium", "formats": ["video_16x9"]},
                {"product_id": "prod_002", "name": "Sports Display Standard", "formats": ["display_300x250"]}
            ]}
        ))
        return executor
    
    @pytest.mark.asyncio
    async def test_message_send_no_echo(self, mock_executor):
        """Verify the agent doesn't echo user input."""
        from a2a_facade import A2AFacade
        
        facade = A2AFacade()
        facade.executor = mock_executor
        
        result = await facade._execute_task(
            method="message/send",
            params={
                "message": {
                    "contextId": "ctx_test",
                    "parts": [{"kind": "text", "text": "Show me sports inventory"}],
                    "role": "user"
                }
            },
            principal_id="test_principal"
        )
        
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        # Should have both text and data parts for inventory query
        assert len(result["parts"]) >= 1
        assert result["parts"][0]["text"] != "Show me sports inventory"
    
    @pytest.mark.asyncio
    async def test_task_response_format(self, mock_executor):
        """Verify task responses have correct A2A format."""
        from a2a_facade import A2AFacade
        
        facade = A2AFacade()
        facade.executor = mock_executor
        
        result = await facade._execute_task(
            method="get_products",
            params={"brief": "sports"},
            principal_id="test_principal"
        )
        
        assert result["kind"] == "task"
        assert "id" in result
        assert "status" in result
        assert result["status"]["state"] == "completed"
        assert "artifact" in result
        assert "products" in result["artifact"]


class TestA2AProtocolIntegration:
    """Integration tests for A2A protocol."""
    
    def setup_method(self):
        """Set up test environment."""
        self.base_url = "http://localhost:8190/rpc"
        self.headers = {
            "Content-Type": "application/json",
            "x-adcp-auth": "test_token_123"
        }
    
    def make_request(self, method: str, params: Dict[str, Any]) -> Dict:
        """Make an A2A JSON-RPC request."""
        request = {
            "id": f"test_{method}_{datetime.now().timestamp()}",
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        response = httpx.post(self.base_url, json=request, headers=self.headers, timeout=5.0)
        return response.json() if response.status_code == 200 else None
    
    @pytest.mark.integration
    def test_full_conversation_flow(self):
        """Test a complete conversation flow."""
        context_id = f"ctx_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 1. Send initial message
        response = self.make_request("message/send", {
            "message": {
                "contextId": context_id,
                "parts": [{"kind": "text", "text": "I need sports advertising inventory"}],
                "role": "user"
            }
        })
        
        assert response is not None
        result = response.get("result", {})
        assert result.get("kind") == "message"
        assert result.get("role") == "agent"
        
        # Check for structured data in response
        parts = result.get("parts", [])
        has_data = any(p.get("kind") == "data" for p in parts)
        assert has_data, "Should include structured product data"
        
        # 2. Get products directly
        response = self.make_request("get_products", {
            "brief": "sports video ads"
        })
        
        assert response is not None
        result = response.get("result", {})
        assert result.get("kind") == "task"
        assert result.get("status", {}).get("state") == "completed"
        assert "products" in result.get("artifact", {})
    
    @pytest.mark.integration
    def test_a2a_inspector_format(self):
        """Test A2A Inspector specific message format."""
        response = self.make_request("message/send", {
            "configuration": {
                "acceptedOutputModes": ["text/plain", "application/json"]
            },
            "message": {
                "contextId": "ctx_inspector_test",
                "kind": "message",
                "messageId": "msg-inspector-test",
                "parts": [
                    {
                        "kind": "text",
                        "text": "Show me display advertising options"
                    }
                ],
                "role": "user"
            }
        })
        
        assert response is not None
        result = response.get("result", {})
        
        # Validate response structure
        assert result.get("kind") == "message"
        assert result.get("role") == "agent"
        assert result.get("contextId") == "ctx_inspector_test"
        
        # Should have multiple parts including data
        parts = result.get("parts", [])
        part_kinds = [p.get("kind") for p in parts]
        assert "text" in part_kinds
        assert "data" in part_kinds


class TestA2AStructuredData:
    """Tests for structured data responses in A2A protocol."""
    
    def setup_method(self):
        """Set up test environment."""
        self.base_url = "http://localhost:8190/rpc"
        self.headers = {
            "Content-Type": "application/json",
            "x-adcp-auth": "test_token_123"
        }
    
    def validate_product_structure(self, product: Dict) -> List[str]:
        """Validate a product has required AdCP fields."""
        required_fields = ["product_id", "name", "formats"]
        missing = [f for f in required_fields if f not in product]
        return missing
    
    @pytest.mark.integration
    def test_products_have_full_data(self):
        """Test that product responses include all AdCP fields."""
        request = {
            "id": "test_products_full",
            "jsonrpc": "2.0",
            "method": "get_products",
            "params": {"brief": "video ads"}
        }
        
        response = httpx.post(self.base_url, json=request, headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        result = data.get("result", {})
        
        # Check Task structure
        assert result.get("kind") == "task"
        assert result.get("status", {}).get("state") == "completed"
        
        # Check products
        products = result.get("artifact", {}).get("products", [])
        assert len(products) > 0, "Should return at least one product"
        
        # Validate first product structure
        missing = self.validate_product_structure(products[0])
        assert len(missing) == 0, f"Product missing fields: {missing}"
    
    @pytest.mark.integration
    def test_message_send_includes_data(self):
        """Test that message/send includes structured data for entity queries."""
        request = {
            "id": "test_message_data",
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "parts": [{"kind": "text", "text": "What video inventory do you have?"}],
                    "role": "user"
                }
            }
        }
        
        response = httpx.post(self.base_url, json=request, headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        result = data.get("result", {})
        
        # Check message structure
        assert result.get("kind") == "message"
        assert result.get("role") == "agent"
        
        # Should have data part with products
        parts = result.get("parts", [])
        data_parts = [p for p in parts if p.get("kind") == "data"]
        assert len(data_parts) > 0, "Should include data part for inventory query"
        
        # Validate data content
        data_content = data_parts[0].get("data", {})
        assert "products" in data_content or "type" in data_content


if __name__ == "__main__":
    # Run tests with different markers
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "unit":
        pytest.main([__file__, "-v", "-m", "not integration"])
    elif len(sys.argv) > 1 and sys.argv[1] == "integration":
        pytest.main([__file__, "-v", "-m", "integration"])
    else:
        pytest.main([__file__, "-v"])