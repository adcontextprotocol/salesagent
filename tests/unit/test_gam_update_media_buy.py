"""Unit tests for GAM adapter update_media_buy method.

Tests that package budget updates are persisted to the database
and that unsupported actions return explicit errors (no silent failures).
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from src.core.schemas import UpdateMediaBuyError, UpdateMediaBuySuccess


def test_update_package_budget_persists_to_database():
    """Test that update_package_budget action actually updates the database."""
    from src.adapters.google_ad_manager import GoogleAdManager

    media_buy_id = "mb_test123"
    package_id = "pkg_test456"
    new_budget = 30000

    # Mock database session and MediaPackage
    mock_package = Mock()
    mock_package.package_id = package_id
    mock_package.package_config = {"budget": 19000, "product_id": "prod_1"}

    # Create a minimal mock adapter
    mock_adapter = Mock(spec=GoogleAdManager)
    mock_adapter.log = Mock()
    mock_adapter.tenant_id = "tenant_test123"  # Add tenant_id for tenant isolation
    mock_adapter._is_admin_principal = Mock(return_value=False)
    mock_adapter._requires_manual_approval = Mock(return_value=False)
    mock_adapter.workflow_manager = Mock()

    with (
        patch("src.core.database.database_session.get_db_session") as mock_db,
        patch("sqlalchemy.orm.attributes.flag_modified") as mock_flag_modified,
    ):
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock the query to return our test package
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_package
        mock_session.scalars.return_value = mock_scalars

        # Call the actual method (bind to real class)
        result = GoogleAdManager.update_media_buy(
            mock_adapter,
            media_buy_id=media_buy_id,
            buyer_ref="buyer_test",
            action="update_package_budget",
            package_id=package_id,
            budget=new_budget,
            today=datetime.now(),
        )

        # Verify flag_modified was called
        mock_flag_modified.assert_called_once_with(mock_package, "package_config")

        # Verify success response
        assert isinstance(result, UpdateMediaBuySuccess)
        assert result.media_buy_id == media_buy_id

        # Verify database was updated
        assert mock_package.package_config["budget"] == float(new_budget)

        # Verify session.commit() was called
        mock_session.commit.assert_called_once()


def test_update_package_budget_returns_error_when_package_not_found():
    """Test that update_package_budget returns error when package doesn't exist."""
    from src.adapters.google_ad_manager import GoogleAdManager

    media_buy_id = "mb_test123"
    package_id = "pkg_nonexistent"
    new_budget = 30000

    # Create a minimal mock adapter
    mock_adapter = Mock(spec=GoogleAdManager)
    mock_adapter.log = Mock()
    mock_adapter.tenant_id = "tenant_test123"  # Add tenant_id for tenant isolation
    mock_adapter._is_admin_principal = Mock(return_value=False)
    mock_adapter._requires_manual_approval = Mock(return_value=False)
    mock_adapter.workflow_manager = Mock()

    with patch("src.core.database.database_session.get_db_session") as mock_db:
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock the query to return None (package not found)
        mock_scalars = Mock()
        mock_scalars.first.return_value = None
        mock_session.scalars.return_value = mock_scalars

        # Call the actual method
        result = GoogleAdManager.update_media_buy(
            mock_adapter,
            media_buy_id=media_buy_id,
            buyer_ref="buyer_test",
            action="update_package_budget",
            package_id=package_id,
            budget=new_budget,
            today=datetime.now(),
        )

        # Verify error response
        assert isinstance(result, UpdateMediaBuyError)
        assert len(result.errors) == 1
        assert result.errors[0].code == "package_not_found"
        assert package_id in result.errors[0].message

        # Verify commit was NOT called (no changes to persist)
        mock_session.commit.assert_not_called()


def test_unsupported_action_returns_explicit_error():
    """Test that unsupported actions return explicit error (no silent success)."""
    from src.adapters.google_ad_manager import GoogleAdManager

    media_buy_id = "mb_test123"

    # Create a minimal mock adapter
    mock_adapter = Mock(spec=GoogleAdManager)
    mock_adapter.log = Mock()
    mock_adapter._is_admin_principal = Mock(return_value=False)
    mock_adapter._requires_manual_approval = Mock(return_value=False)

    # Test an action that doesn't exist
    result = GoogleAdManager.update_media_buy(
        mock_adapter,
        media_buy_id=media_buy_id,
        buyer_ref="buyer_test",
        action="delete_media_buy",  # Not supported
        package_id=None,
        budget=None,
        today=datetime.now(),
    )

    # Verify error response (not success!)
    assert isinstance(result, UpdateMediaBuyError)
    assert len(result.errors) == 1
    assert result.errors[0].code == "unsupported_action"
    assert "delete_media_buy" in result.errors[0].message


def test_pause_resume_actions_return_not_implemented_error():
    """Test that pause/resume actions return not_implemented error."""
    from src.adapters.google_ad_manager import GoogleAdManager

    media_buy_id = "mb_test123"
    package_id = "pkg_test456"

    # Create a minimal mock adapter
    mock_adapter = Mock(spec=GoogleAdManager)
    mock_adapter.log = Mock()
    mock_adapter._is_admin_principal = Mock(return_value=False)
    mock_adapter._requires_manual_approval = Mock(return_value=False)

    # Test all pause/resume actions
    actions = ["pause_package", "resume_package", "pause_media_buy", "resume_media_buy"]

    for action in actions:
        result = GoogleAdManager.update_media_buy(
            mock_adapter,
            media_buy_id=media_buy_id,
            buyer_ref="buyer_test",
            action=action,
            package_id=package_id if "package" in action else None,
            budget=None,
            today=datetime.now(),
        )

        # Verify not_implemented error response
        assert isinstance(result, UpdateMediaBuyError), f"Action {action} should return error"
        assert len(result.errors) == 1
        assert result.errors[0].code == "not_implemented"
        assert action in result.errors[0].message


def test_update_package_budget_rejects_budget_below_delivery():
    """Test that update_package_budget rejects budget less than current spend."""
    from src.adapters.google_ad_manager import GoogleAdManager

    media_buy_id = "mb_test123"
    package_id = "pkg_test456"
    current_spend = 15000.0
    new_budget = 10000  # Less than current spend

    # Mock database session and MediaPackage with delivery metrics
    mock_package = Mock()
    mock_package.package_id = package_id
    mock_package.package_config = {
        "budget": 19000,
        "product_id": "prod_1",
        "delivery_metrics": {"spend": current_spend, "impressions_delivered": 50000},
    }

    # Create a minimal mock adapter
    mock_adapter = Mock(spec=GoogleAdManager)
    mock_adapter.log = Mock()
    mock_adapter.tenant_id = "tenant_test123"
    mock_adapter._is_admin_principal = Mock(return_value=False)
    mock_adapter._requires_manual_approval = Mock(return_value=False)
    mock_adapter.workflow_manager = Mock()

    with patch("src.core.database.database_session.get_db_session") as mock_db:
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock the query to return our test package
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_package
        mock_session.scalars.return_value = mock_scalars

        # Call the actual method
        result = GoogleAdManager.update_media_buy(
            mock_adapter,
            media_buy_id=media_buy_id,
            buyer_ref="buyer_test",
            action="update_package_budget",
            package_id=package_id,
            budget=new_budget,
            today=datetime.now(),
        )

        # Verify error response
        assert isinstance(result, UpdateMediaBuyError)
        assert len(result.errors) == 1
        assert result.errors[0].code == "budget_below_delivery"
        assert str(new_budget) in result.errors[0].message
        assert str(current_spend) in result.errors[0].message

        # Verify commit was NOT called (budget rejected)
        mock_session.commit.assert_not_called()
