"""Test creative snippet validation.

Tests that the Creative schema properly validates snippet content and rejects
malformed/invalid snippets like plain text strings.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.core.schemas import Creative, FormatId


def test_valid_html_snippet_accepted():
    """Valid HTML snippet should be accepted."""
    creative = Creative(
        creative_id="test-1",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="display_300x250"),
        content_uri="<script>/* Snippet-based creative */</script>",  # HTML placeholder for snippet creatives
        snippet="<script>console.log('ad');</script>",
        snippet_type="html",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert creative.snippet == "<script>console.log('ad');</script>"


def test_valid_javascript_snippet_accepted():
    """Valid JavaScript snippet should be accepted."""
    creative = Creative(
        creative_id="test-2",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="display_300x250"),
        content_uri="<script>/* Snippet-based creative */</script>",
        snippet="function loadAd() { document.write('ad'); }",
        snippet_type="javascript",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert "function loadAd" in creative.snippet


def test_valid_vast_xml_accepted():
    """Valid VAST XML snippet should be accepted."""
    vast_xml = """
    <VAST version="3.0">
        <Ad><Creative></Creative></Ad>
    </VAST>
    """
    creative = Creative(
        creative_id="test-3",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="video_pre_roll"),
        content_uri="<script>/* Snippet-based creative */</script>",
        snippet=vast_xml,
        snippet_type="vast_xml",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert "<VAST" in creative.snippet


def test_valid_vast_url_accepted():
    """Valid VAST URL snippet should be accepted."""
    creative = Creative(
        creative_id="test-4",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="video_pre_roll"),
        content_uri="<script>/* Snippet-based creative */</script>",
        snippet="https://adserver.com/vast.xml?id=123",
        snippet_type="vast_url",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert creative.snippet.startswith("https://")


def test_plain_text_snippet_rejected():
    """Plain text strings should be rejected as invalid snippets."""
    with pytest.raises(ValidationError) as exc_info:
        Creative(
            creative_id="test-5",
            name="Test Creative",
            format=FormatId(agent_url="https://example.com", id="display_300x250"),
            content_uri="<script>/* Snippet-based creative */</script>",
            snippet="Wonderstruck",  # Invalid: plain text
            snippet_type="html",
            principal_id="test-principal",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    error_msg = str(exc_info.value)
    assert "does not appear to contain valid HTML/JS/VAST code" in error_msg


def test_short_snippet_rejected():
    """Snippets that are too short should be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Creative(
            creative_id="test-6",
            name="Test Creative",
            format=FormatId(agent_url="https://example.com", id="display_300x250"),
            content_uri="<script>/* Snippet-based creative */</script>",
            snippet="<div>",  # Too short
            snippet_type="html",
            principal_id="test-principal",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    error_msg = str(exc_info.value)
    assert "too short" in error_msg


def test_vast_xml_type_mismatch_rejected():
    """VAST XML snippet_type without VAST tags should be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Creative(
            creative_id="test-7",
            name="Test Creative",
            format=FormatId(agent_url="https://example.com", id="video_pre_roll"),
            content_uri="<script>/* Snippet-based creative */</script>",
            snippet="<script>console.log('not vast');</script>",
            snippet_type="vast_xml",  # Type says VAST but content isn't
            principal_id="test-principal",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    error_msg = str(exc_info.value)
    assert "does not contain <VAST> tag" in error_msg


def test_vast_url_type_mismatch_rejected():
    """VAST URL snippet_type without URL should be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Creative(
            creative_id="test-8",
            name="Test Creative",
            format=FormatId(agent_url="https://example.com", id="video_pre_roll"),
            content_uri="<script>/* Snippet-based creative */</script>",
            snippet="<VAST>...</VAST>",  # XML not URL
            snippet_type="vast_url",
            principal_id="test-principal",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    error_msg = str(exc_info.value)
    assert "is not a URL" in error_msg


def test_snippet_with_iframe_accepted():
    """Snippet containing iframe should be accepted."""
    creative = Creative(
        creative_id="test-9",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="display_300x250"),
        content_uri="<script>/* Snippet-based creative */</script>",
        snippet='<iframe src="https://ads.example.com/creative.html"></iframe>',
        snippet_type="html",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert "<iframe" in creative.snippet


def test_snippet_with_url_accepted():
    """Snippet containing URL should be accepted (even without tags)."""
    creative = Creative(
        creative_id="test-10",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="display_300x250"),
        content_uri="<script>/* Snippet-based creative */</script>",
        snippet="https://adserver.example.com/serve?id=12345&format=display",
        snippet_type="html",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert creative.snippet.startswith("https://")


def test_no_snippet_is_valid():
    """Creatives without snippets should be valid (media-based creatives)."""
    creative = Creative(
        creative_id="test-11",
        name="Test Creative",
        format=FormatId(agent_url="https://example.com", id="display_300x250"),
        content_uri="https://example.com/creative.jpg",
        principal_id="test-principal",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert creative.snippet is None
