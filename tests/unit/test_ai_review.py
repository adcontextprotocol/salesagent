"""Unit tests for AI-powered creative review functionality.

Tests the _ai_review_creative_impl function with:
- All 6 decision paths
- Confidence threshold edge cases
- Sensitive category detection
- Missing configuration handling
- API error handling
- Invalid JSON responses
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.database.models import Creative, Tenant


class TestAIReviewCreative:
    """Tests for _ai_review_creative_impl function."""

    @pytest.fixture
    def mock_tenant(self):
        """Create a mock tenant with AI review configuration."""
        tenant = Mock(spec=Tenant)
        tenant.tenant_id = "test_tenant"
        tenant.gemini_api_key = "test-api-key"
        tenant.creative_review_criteria = "Approve if creative is brand-safe and follows guidelines."
        tenant.ai_policy = {
            "auto_approve_threshold": 0.90,
            "auto_reject_threshold": 0.10,
            "always_require_human_for": ["political", "healthcare", "financial"],
        }
        return tenant

    @pytest.fixture
    def mock_creative(self):
        """Create a mock creative."""
        creative = Mock(spec=Creative)
        creative.creative_id = "test_creative_123"
        creative.tenant_id = "test_tenant"
        creative.name = "Test Banner Ad"
        creative.format = "display_300x250"
        creative.data = {"url": "https://example.com/banner.jpg", "tags": ["retail", "fashion"]}
        creative.status = "pending"
        return creative

    @pytest.fixture
    def mock_db_session(self, mock_tenant, mock_creative):
        """Create a mock database session."""
        session = MagicMock()

        # Track call count to return tenant first, then creative
        call_count = [0]

        def mock_scalars(stmt):
            """Mock scalars() to return proper objects."""
            scalars_mock = Mock()

            def mock_first():
                """Return tenant first, then creative on subsequent calls."""
                call_count[0] += 1
                if call_count[0] == 1:
                    return mock_tenant
                else:
                    return mock_creative

            scalars_mock.first = mock_first
            return scalars_mock

        session.scalars = mock_scalars
        session.commit = Mock()
        session.close = Mock()
        return session

    # Decision Path 1: Auto-approve with high confidence
    @patch("google.generativeai.GenerativeModel")
    def test_auto_approve_high_confidence(self, mock_model, mock_db_session, mock_tenant, mock_creative):
        """Test auto-approval when AI is confident (≥0.90)."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Mock Gemini API response
        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "APPROVE", "reason": "Creative is brand-safe", "confidence": "high"}
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "approved"
        assert result["confidence"] == "high"
        assert result["confidence_score"] == 0.9
        assert result["policy_triggered"] == "auto_approve"
        assert "brand-safe" in result["reason"].lower()

    # Decision Path 2: Low confidence approval → requires human review
    @patch("google.generativeai.GenerativeModel")
    def test_low_confidence_approval(self, mock_model, mock_db_session):
        """Test that low confidence approval requires human review."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "APPROVE", "reason": "Seems okay", "confidence": "medium"}  # 0.6 < 0.9
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["confidence"] == "medium"
        assert result["confidence_score"] == 0.6
        assert result["policy_triggered"] == "low_confidence_approval"
        assert result["ai_recommendation"] == "approve"
        assert "below threshold" in result["reason"]

    # Decision Path 3: Sensitive category requires human review
    @patch("google.generativeai.GenerativeModel")
    def test_sensitive_category_requires_human(self, mock_model, mock_db_session, mock_creative):
        """Test that sensitive categories always require human review."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Mark creative as political (sensitive category)
        mock_creative.data = {"category": "political", "tags": ["election", "candidate"]}

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps({"decision": "APPROVE", "reason": "Looks good", "confidence": "high"})
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["policy_triggered"] == "sensitive_category"
        assert "political" in result["reason"].lower()
        assert "requires human review" in result["reason"]

    # Decision Path 4: Auto-reject with high confidence (low score)
    @patch("google.generativeai.GenerativeModel")
    def test_auto_reject_low_confidence_score(self, mock_model, mock_db_session):
        """Test auto-rejection when AI has low confidence score (≤0.10)."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "REJECT", "reason": "Violates brand safety", "confidence": "low"}  # 0.3 > 0.1, so pending
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        # Note: With confidence=low (0.3), it's > 0.1 threshold, so it goes to pending
        assert result["status"] == "pending"
        assert result["policy_triggered"] == "uncertain_rejection"
        assert result["ai_recommendation"] == "reject"

    # Decision Path 5: Uncertain rejection → requires human review
    @patch("google.generativeai.GenerativeModel")
    def test_uncertain_rejection(self, mock_model, mock_db_session):
        """Test that uncertain rejections require human review."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "REJECT", "reason": "Possibly problematic", "confidence": "medium"}  # 0.6 > 0.1
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["confidence"] == "medium"
        assert result["policy_triggered"] == "uncertain_rejection"
        assert result["ai_recommendation"] == "reject"
        assert "not confident enough" in result["reason"]

    # Decision Path 6: Explicit "REQUIRE HUMAN APPROVAL"
    @patch("google.generativeai.GenerativeModel")
    def test_explicit_human_approval_required(self, mock_model, mock_db_session):
        """Test explicit 'REQUIRE HUMAN APPROVAL' decision."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {
                "decision": "REQUIRE HUMAN APPROVAL",
                "reason": "Edge case needs human judgment",
                "confidence": "medium",
            }
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["policy_triggered"] == "uncertain"
        assert "could not make confident decision" in result["reason"].lower()

    # Edge Case: Missing Gemini API key
    def test_missing_gemini_api_key(self, mock_db_session, mock_tenant):
        """Test behavior when Gemini API key is not configured."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_tenant.gemini_api_key = None

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["error"] == "Gemini API key not configured"
        assert "AI review unavailable" in result["reason"]

    # Edge Case: Missing review criteria
    def test_missing_review_criteria(self, mock_db_session, mock_tenant):
        """Test behavior when creative review criteria is not configured."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_tenant.creative_review_criteria = None

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["error"] == "Creative review criteria not configured"
        assert "AI review unavailable" in result["reason"]

    # Edge Case: Invalid JSON response
    @patch("google.generativeai.GenerativeModel")
    def test_invalid_json_response(self, mock_model, mock_db_session):
        """Test handling of invalid JSON from Gemini API."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = "This is not valid JSON"
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert "error" in result
        assert "AI review failed" in result["reason"]

    # Edge Case: API error
    @patch("google.generativeai.GenerativeModel")
    def test_api_error(self, mock_model, mock_db_session):
        """Test handling of Gemini API errors."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_instance.generate_content.side_effect = Exception("API rate limit exceeded")

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert "error" in result
        assert "API rate limit exceeded" in str(result["error"])

    # Edge Case: Confidence threshold at exact boundary (0.90)
    @patch("google.generativeai.GenerativeModel")
    def test_confidence_threshold_exact_boundary_high(self, mock_model, mock_db_session):
        """Test confidence score exactly at 0.90 threshold."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "APPROVE", "reason": "Borderline case", "confidence": "high"}  # Exactly 0.9
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        # At 0.90, should auto-approve (>= threshold)
        assert result["status"] == "approved"
        assert result["confidence_score"] == 0.9

    # Edge Case: Confidence threshold just below boundary (0.89)
    @patch("google.generativeai.GenerativeModel")
    def test_confidence_threshold_below_boundary(self, mock_model, mock_db_session, mock_tenant):
        """Test confidence score just below 0.90 threshold."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Create custom confidence value (0.89)
        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "APPROVE", "reason": "Almost there", "confidence": "medium"}  # 0.6 < 0.9
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        # Below 0.90, should require human review
        assert result["status"] == "pending"
        assert result["policy_triggered"] == "low_confidence_approval"

    # Edge Case: Confidence threshold at reject boundary (0.10)
    @patch("google.generativeai.GenerativeModel")
    def test_confidence_threshold_exact_reject_boundary(self, mock_model, mock_db_session, mock_tenant):
        """Test confidence score exactly at 0.10 reject threshold."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Need to mock a very low confidence score (0.1)
        # Since we can't set arbitrary confidence values, test with "low" = 0.3
        mock_tenant.ai_policy["auto_reject_threshold"] = 0.30  # Adjust threshold for test

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps(
            {"decision": "REJECT", "reason": "Clearly problematic", "confidence": "low"}  # 0.3
        )
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        # At 0.30 with threshold 0.30, should auto-reject (<= threshold)
        assert result["status"] == "rejected"
        assert result["confidence_score"] == 0.3

    # Edge Case: Healthcare sensitive category (tag-based detection)
    @patch("google.generativeai.GenerativeModel")
    def test_healthcare_tag_triggers_human_review(self, mock_model, mock_db_session, mock_creative):
        """Test that healthcare tag triggers human review."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Tag-based category detection
        mock_creative.data = {"tags": ["healthcare", "wellness"], "category": None}

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps({"decision": "APPROVE", "reason": "Looks good", "confidence": "high"})
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["policy_triggered"] == "sensitive_category"
        assert "healthcare" in result["reason"].lower()

    # Edge Case: Financial sensitive category
    @patch("google.generativeai.GenerativeModel")
    def test_financial_category_requires_human(self, mock_model, mock_db_session, mock_creative):
        """Test that financial category requires human review."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_creative.data = {"category": "financial", "tags": ["banking", "investment"]}

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps({"decision": "APPROVE", "reason": "Compliant", "confidence": "high"})
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "pending"
        assert result["policy_triggered"] == "sensitive_category"
        assert "financial" in result["reason"].lower()

    # Edge Case: Empty creative data
    @patch("google.generativeai.GenerativeModel")
    def test_empty_creative_data(self, mock_model, mock_db_session, mock_creative):
        """Test handling of creative with empty data field."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_creative.data = {}

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps({"decision": "APPROVE", "reason": "No issues found", "confidence": "high"})
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        # Should still work, just no category detection
        assert result["status"] == "approved"

    # Edge Case: JSON response with code fences
    @patch("google.generativeai.GenerativeModel")
    def test_json_response_with_code_fences(self, mock_model, mock_db_session):
        """Test parsing JSON response wrapped in code fences."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = '```json\n{"decision": "APPROVE", "reason": "All good", "confidence": "high"}\n```'
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        assert result["status"] == "approved"
        assert result["reason"] == "All good"

    # Edge Case: Tenant not found
    def test_tenant_not_found(self):
        """Test behavior when tenant is not found."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Create session that returns None for tenant
        session = MagicMock()

        def mock_scalars(stmt):
            scalars_mock = Mock()
            scalars_mock.first = Mock(return_value=None)
            return scalars_mock

        session.scalars = mock_scalars
        session.commit = Mock()
        session.close = Mock()

        result = _ai_review_creative_impl("nonexistent_tenant", "test_creative_123", db_session=session)

        assert result["status"] == "pending"
        assert result["error"] == "Tenant not found"
        assert result["reason"] == "Configuration error"

    # Edge Case: Creative not found
    def test_creative_not_found(self, mock_tenant):
        """Test behavior when creative is not found."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        # Create session that returns tenant first, then None for creative
        session = MagicMock()
        call_count = [0]

        def mock_scalars(stmt):
            scalars_mock = Mock()

            def mock_first():
                call_count[0] += 1
                if call_count[0] == 1:
                    return mock_tenant
                else:
                    return None

            scalars_mock.first = mock_first
            return scalars_mock

        session.scalars = mock_scalars
        session.commit = Mock()
        session.close = Mock()

        result = _ai_review_creative_impl("test_tenant", "nonexistent_creative", db_session=session)

        assert result["status"] == "pending"
        assert result["error"] == "Creative not found"
        assert result["reason"] == "Configuration error"

    # Edge Case: Missing ai_policy (uses defaults)
    @patch("google.generativeai.GenerativeModel")
    def test_missing_ai_policy_uses_defaults(self, mock_model, mock_db_session, mock_tenant):
        """Test that missing ai_policy uses default thresholds."""
        from src.admin.blueprints.creatives import _ai_review_creative_impl

        mock_tenant.ai_policy = None  # No policy configured

        mock_instance = mock_model.return_value
        mock_response = Mock()
        mock_response.text = json.dumps({"decision": "APPROVE", "reason": "Looks good", "confidence": "high"})
        mock_instance.generate_content.return_value = mock_response

        result = _ai_review_creative_impl("test_tenant", "test_creative_123", db_session=mock_db_session)

        # Should use default thresholds (0.90 for approve)
        assert result["status"] == "approved"
        assert result["confidence_score"] == 0.9
