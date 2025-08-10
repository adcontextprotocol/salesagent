"""
Unit tests for A2A protocol implementation.

These tests ensure the A2A facade correctly handles requests and generates
appropriate responses without echoing user input.
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from a2a_facade import A2AFacade
from task_executor import TaskExecutor, TaskStatus, TaskResult

class TestA2AMessageSend:
    """Test the message/send endpoint specifically."""
    
    @pytest.fixture
    def mock_executor(self):
        """Create a mock TaskExecutor."""
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
            data={"products": [
                {"name": "Sports Video Premium", "formats": ["video_16x9"]},
                {"name": "Sports Display Standard", "formats": ["display_300x250"]}
            ]}
        ))
        return executor
    
    @pytest.fixture
    def a2a_facade(self, mock_executor):
        """Create A2A facade with mock executor."""
        facade = A2AFacade()
        facade.executor = mock_executor
        return facade
    
    @pytest.mark.asyncio
    async def test_message_send_does_not_echo_user_input(self, a2a_facade):
        """Verify the agent doesn't just echo back the user's message."""
        user_message = "I'm looking for sports inventory"
        
        result = await a2a_facade._execute_task(
            method="message/send",
            params={
                "message": {
                    "contextId": "ctx_test",
                    "kind": "message",
                    "messageId": "user_msg_1",
                    "parts": [{"kind": "text", "text": user_message}],
                    "role": "user"
                }
            },
            principal_id="test_principal"
        )
        
        # Assert the response is NOT the same as the input
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        assert result["parts"][0]["text"] != user_message
        assert "products" in result["parts"][0]["text"].lower() or \
               "inventory" in result["parts"][0]["text"].lower()
    
    @pytest.mark.asyncio
    async def test_message_send_calls_get_products_for_inventory_query(self, a2a_facade):
        """Verify inventory queries trigger get_products."""
        result = await a2a_facade._execute_task(
            method="message/send",
            params={
                "message": {
                    "parts": [{"kind": "text", "text": "Show me sports inventory"}],
                    "role": "user"
                }
            },
            principal_id="test_principal"
        )
        
        # Verify get_products was called
        a2a_facade.executor.get_products.assert_called_once()
        
        # Verify response mentions products found
        response_text = result["parts"][0]["text"]
        assert "found" in response_text.lower()
        assert "Sports Video Premium" in response_text or "products" in response_text.lower()
    
    @pytest.mark.asyncio
    async def test_message_send_stores_conversation_history(self, a2a_facade):
        """Verify both user and agent messages are stored."""
        await a2a_facade._execute_task(
            method="message/send",
            params={
                "content": "Test message",
                "context_id": "ctx_123"
            },
            principal_id="test_principal"
        )
        
        # Should be called twice: once for user message, once for agent response
        assert a2a_facade.executor.send_message.call_count == 2
        
        # Check the calls
        calls = a2a_facade.executor.send_message.call_args_list
        
        # First call should store user message
        assert calls[0][1]["principal_id"] == "test_principal"
        assert calls[0][1]["content"] == "Test message"
        assert calls[0][1]["metadata"]["role"] == "user"
        
        # Second call should store agent response
        assert calls[1][1]["principal_id"] == "agent"
        assert calls[1][1]["metadata"]["role"] == "agent"
        assert calls[1][1]["content"] != "Test message"  # Not an echo
    
    @pytest.mark.asyncio
    async def test_message_send_handles_a2a_inspector_format(self, a2a_facade):
        """Test the nested message format from A2A Inspector."""
        result = await a2a_facade._execute_task(
            method="message/send",
            params={
                "configuration": {
                    "acceptedOutputModes": ["text/plain"]
                },
                "message": {
                    "contextId": "ctx_5c5705f4",
                    "kind": "message",
                    "messageId": "msg-1754764161386-4eyjbfsbe",
                    "parts": [
                        {
                            "kind": "text",
                            "text": "I'm looking for sports inventory"
                        }
                    ],
                    "role": "user"
                }
            },
            principal_id="test_principal"
        )
        
        # Verify correct response structure
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        assert result["contextId"] == "ctx_5c5705f4"
        
        # Verify it's not an echo
        assert result["parts"][0]["text"] != "I'm looking for sports inventory"
        
        # Verify intelligent response
        response_text = result["parts"][0]["text"].lower()
        assert any(word in response_text for word in ["products", "inventory", "found", "options"])
    
    @pytest.mark.asyncio
    async def test_message_send_provides_helpful_default_response(self, a2a_facade):
        """Test that generic queries get helpful responses."""
        result = await a2a_facade._execute_task(
            method="message/send",
            params={
                "content": "Hello, what can you do?"
            },
            principal_id="test_principal"
        )
        
        response_text = result["parts"][0]["text"].lower()
        
        # Should mention capabilities
        assert any(word in response_text for word in ["help", "inventory", "media buy", "campaign"])
        
        # Should NOT echo "Hello, what can you do?"
        assert "hello, what can you do?" not in response_text


class TestA2AProtocolCompliance:
    """Test overall A2A protocol compliance."""
    
    @pytest.mark.asyncio
    async def test_agent_card_format(self):
        """Verify Agent Card has correct structure."""
        facade = A2AFacade()
        card = facade._get_agent_card()
        
        # Required fields
        assert card["protocolVersion"] == "2024-10-18"
        assert card["name"] == "AdCP Sales Agent"
        assert "description" in card
        assert "capabilities" in card
        assert "actions" in card
        
        # Verify actions include our methods
        action_ids = [a["id"] for a in card["actions"]]
        assert "get_products" in action_ids
        assert "create_media_buy" in action_ids
        assert "submit_creatives" in action_ids
    
    @pytest.mark.asyncio  
    async def test_jsonrpc_error_response_format(self):
        """Test that errors follow JSON-RPC 2.0 format."""
        facade = A2AFacade()
        
        # Test with invalid method
        result = await facade._execute_task(
            method="invalid_method",
            params={},
            principal_id="test"
        )
        
        # Should return error (not raise exception)
        assert "error" in result or result is None


class TestA2ATaskExecutorIntegration:
    """Test the integration between A2A facade and TaskExecutor."""
    
    @pytest.mark.asyncio
    async def test_get_products_response_format(self):
        """Verify get_products returns correct A2A format."""
        mock_executor = Mock(spec=TaskExecutor)
        mock_executor.get_products = AsyncMock(return_value=TaskResult(
            status=TaskStatus.COMPLETED,
            data={"products": [{"name": "Test Product"}]}
        ))
        
        facade = A2AFacade()
        facade.executor = mock_executor
        
        result = await facade._execute_task(
            method="get_products",
            params={"brief": "test"},
            principal_id="test"
        )
        
        # Should have A2A Task structure
        assert result["kind"] == "task"
        assert result["status"]["state"] == "completed"
        assert "artifact" in result
        assert result["artifact"]["products"] == [{"name": "Test Product"}]
    
    @pytest.mark.asyncio
    async def test_error_handling_returns_failed_task(self):
        """Verify errors return failed Task objects."""
        mock_executor = Mock(spec=TaskExecutor) 
        mock_executor.get_products = AsyncMock(side_effect=Exception("Database error"))
        
        facade = A2AFacade()
        facade.executor = mock_executor
        
        result = await facade._execute_task(
            method="get_products",
            params={},
            principal_id="test"
        )
        
        # Should return failed task (not raise)
        assert result["kind"] == "task"
        assert result["status"]["state"] == "failed"
        assert "Database error" in str(result.get("status", {}).get("error", ""))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])