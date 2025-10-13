"""Unit tests for CreativeReview model and related functionality."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.core.database.models import Creative, CreativeReview, Tenant
from src.core.database.queries import (
    get_ai_review_stats,
    get_creative_reviews,
)


@pytest.mark.requires_db
def test_creative_review_model_creation(db_session):
    """Test creating a CreativeReview record."""
    # Create tenant
    tenant = Tenant(
        tenant_id="test_tenant",
        name="Test Tenant",
        subdomain="test",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    # Create creative
    creative_id = f"creative_{uuid.uuid4().hex[:8]}"
    creative = Creative(
        creative_id=creative_id,
        tenant_id="test_tenant",
        principal_id="test_principal",
        name="Test Creative",
        format="display_300x250",
        status="pending",
        data={},
    )
    db_session.add(creative)
    db_session.commit()

    # Create review
    review_id = f"review_{uuid.uuid4().hex[:8]}"
    review = CreativeReview(
        review_id=review_id,
        creative_id=creative_id,
        tenant_id="test_tenant",
        reviewed_at=datetime.now(UTC),
        review_type="ai",
        ai_decision="approve",
        confidence_score=0.95,
        policy_triggered="auto_approve",
        reason="Creative meets all criteria",
        human_override=False,
        final_decision="approved",
    )
    db_session.add(review)
    db_session.commit()

    # Query back
    stmt = select(CreativeReview).filter_by(review_id=review_id)
    retrieved_review = db_session.scalars(stmt).first()

    assert retrieved_review is not None
    assert retrieved_review.creative_id == creative_id
    assert retrieved_review.review_type == "ai"
    assert retrieved_review.confidence_score == 0.95
    assert retrieved_review.final_decision == "approved"


@pytest.mark.requires_db
def test_creative_review_relationship(db_session):
    """Test Creative.reviews relationship."""
    # Create tenant
    tenant = Tenant(
        tenant_id="test_tenant2",
        name="Test Tenant 2",
        subdomain="test2",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    # Create creative
    creative_id = f"creative_{uuid.uuid4().hex[:8]}"
    creative = Creative(
        creative_id=creative_id,
        tenant_id="test_tenant2",
        principal_id="test_principal",
        name="Test Creative",
        format="display_300x250",
        status="pending",
        data={},
    )
    db_session.add(creative)
    db_session.commit()

    # Create multiple reviews
    for i in range(3):
        review = CreativeReview(
            review_id=f"review_{uuid.uuid4().hex[:8]}",
            creative_id=creative_id,
            tenant_id="test_tenant2",
            reviewed_at=datetime.now(UTC),
            review_type="ai" if i < 2 else "human",
            ai_decision="approve" if i < 2 else None,
            confidence_score=0.9 - (i * 0.1) if i < 2 else None,
            policy_triggered="auto_approve" if i < 2 else None,
            reason=f"Review {i}",
            human_override=i == 2,
            final_decision="approved",
        )
        db_session.add(review)

    db_session.commit()

    # Query creative with reviews
    stmt = select(Creative).filter_by(creative_id=creative_id)
    retrieved_creative = db_session.scalars(stmt).first()

    assert retrieved_creative is not None
    assert len(retrieved_creative.reviews) == 3
    assert sum(1 for r in retrieved_creative.reviews if r.review_type == "ai") == 2
    assert sum(1 for r in retrieved_creative.reviews if r.review_type == "human") == 1


@pytest.mark.requires_db
def test_get_creative_reviews_query(db_session):
    """Test get_creative_reviews helper function."""
    # Create tenant
    tenant = Tenant(
        tenant_id="test_tenant3",
        name="Test Tenant 3",
        subdomain="test3",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    # Create creative
    creative_id = f"creative_{uuid.uuid4().hex[:8]}"
    creative = Creative(
        creative_id=creative_id,
        tenant_id="test_tenant3",
        principal_id="test_principal",
        name="Test Creative",
        format="display_300x250",
        status="pending",
        data={},
    )
    db_session.add(creative)
    db_session.commit()

    # Create reviews with different timestamps
    for i in range(3):
        review = CreativeReview(
            review_id=f"review_{uuid.uuid4().hex[:8]}",
            creative_id=creative_id,
            tenant_id="test_tenant3",
            reviewed_at=datetime.now(UTC),
            review_type="ai",
            ai_decision="approve",
            confidence_score=0.9,
            policy_triggered="auto_approve",
            reason=f"Review {i}",
            human_override=False,
            final_decision="approved",
        )
        db_session.add(review)

    db_session.commit()

    # Test query helper
    reviews = get_creative_reviews(db_session, creative_id)
    assert len(reviews) == 3
    assert all(r.creative_id == creative_id for r in reviews)


@pytest.mark.requires_db
def test_get_ai_review_stats_empty(db_session):
    """Test get_ai_review_stats with no data."""
    stats = get_ai_review_stats(db_session, "nonexistent_tenant", days=30)

    assert stats["total_reviews"] == 0
    assert stats["auto_approved"] == 0
    assert stats["auto_rejected"] == 0
    assert stats["required_human"] == 0
    assert stats["human_overrides"] == 0
    assert stats["override_rate"] == 0.0
    assert stats["avg_confidence"] == 0.0
    assert stats["approval_rate"] == 0.0
    assert stats["policy_breakdown"] == {}


@pytest.mark.requires_db
def test_human_override_detection(db_session):
    """Test detection of human overrides."""
    # Create tenant
    tenant = Tenant(
        tenant_id="test_tenant4",
        name="Test Tenant 4",
        subdomain="test4",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    # Create creative
    creative_id = f"creative_{uuid.uuid4().hex[:8]}"
    creative = Creative(
        creative_id=creative_id,
        tenant_id="test_tenant4",
        principal_id="test_principal",
        name="Test Creative",
        format="display_300x250",
        status="pending",
        data={},
    )
    db_session.add(creative)
    db_session.commit()

    # AI review: reject
    ai_review = CreativeReview(
        review_id=f"review_{uuid.uuid4().hex[:8]}",
        creative_id=creative_id,
        tenant_id="test_tenant4",
        reviewed_at=datetime.now(UTC),
        review_type="ai",
        ai_decision="reject",
        confidence_score=0.95,
        policy_triggered="auto_reject",
        reason="Violates policy",
        human_override=False,
        final_decision="rejected",
    )
    db_session.add(ai_review)
    db_session.commit()

    # Human review: override to approve
    human_review = CreativeReview(
        review_id=f"review_{uuid.uuid4().hex[:8]}",
        creative_id=creative_id,
        tenant_id="test_tenant4",
        reviewed_at=datetime.now(UTC),
        review_type="human",
        ai_decision=None,
        confidence_score=None,
        policy_triggered=None,
        reason="Override: actually acceptable",
        human_override=True,
        final_decision="approved",
    )
    db_session.add(human_review)
    db_session.commit()

    # Query reviews
    reviews = get_creative_reviews(db_session, creative_id)

    assert len(reviews) == 2
    ai_reviews = [r for r in reviews if r.review_type == "ai"]
    human_reviews = [r for r in reviews if r.review_type == "human"]

    assert len(ai_reviews) == 1
    assert ai_reviews[0].final_decision == "rejected"
    assert not ai_reviews[0].human_override

    assert len(human_reviews) == 1
    assert human_reviews[0].final_decision == "approved"
    assert human_reviews[0].human_override
