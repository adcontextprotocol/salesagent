# AI Creative Summary Feature

## Overview

When Gemini API is configured and a creative is uploaded/synced, the system should automatically generate a concise summary of what the creative is about. This summary is displayed on the Creative Management page without needing to click preview.

## Implementation Locations

### 1. Generate Summary During AI Review

**File**: `src/admin/blueprints/creatives.py`
**Function**: `ai_review_creative()` (line ~675)

When AI reviews a creative, generate both:
- `ai_review_reasoning` (approve/reject reasoning) - **already exists**
- `ai_summary` (description of creative content) - **needs to be added**

**Prompt Example**:
```python
summary_prompt = f"""
Provide a brief 1-2 sentence summary of this creative.
Describe what product/service is being advertised and the key visual/messaging elements.

Creative URL: {creative.data.get('url')}
Format: {creative.format}
"""

# Call Gemini to generate summary
summary = gemini_client.generate_content(summary_prompt)

# Store in creative.data
creative.data['ai_summary'] = summary.text
```

### 2. Generate Summary During sync_creatives

**File**: `src/core/main.py`
**Function**: `_sync_creatives_impl()` (line ~1394)

When creatives are synced via AdCP, check approval mode:
- If `approval_mode == 'ai-powered'` and Gemini key exists
- Generate AI summary for each creative
- Store in `creative.data['ai_summary']`

**Implementation Pattern**:
```python
# In _sync_creatives_impl(), after creating/updating creative records

if tenant.approval_mode == 'ai-powered' and tenant.gemini_api_key:
    from src.services.ai_review_service import generate_creative_summary

    for creative in new_creatives:
        try:
            summary = generate_creative_summary(
                creative_url=creative.data.get('url'),
                creative_format=creative.format,
                gemini_key=tenant.gemini_api_key
            )
            creative.data['ai_summary'] = summary
            db_session.commit()
        except Exception as e:
            logger.warning(f"Failed to generate AI summary for {creative.creative_id}: {e}")
            # Continue without summary - non-critical feature
```

### 3. Create AI Review Service (Recommended)

**New File**: `src/services/ai_review_service.py`

Centralize all Gemini AI logic:

```python
"""AI-powered creative review and analysis service."""

import google.generativeai as genai

def generate_creative_summary(creative_url: str, creative_format: str, gemini_key: str) -> str:
    """Generate a concise summary of what a creative is about.

    Args:
        creative_url: URL to the creative asset
        creative_format: Format type (display_300x250, video_15s, etc.)
        gemini_key: Gemini API key

    Returns:
        1-2 sentence summary of the creative
    """
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Analyze this advertising creative and provide a brief 1-2 sentence summary.
    Focus on: What product/service is being advertised? What are the key visual or messaging elements?

    Creative URL: {creative_url}
    Format: {creative_format}

    Be concise and descriptive. Example: "A display ad for Nike running shoes featuring an athlete in motion against a vibrant orange background with the tagline 'Just Do It'."
    """

    response = model.generate_content(prompt)
    return response.text.strip()


def review_creative_with_criteria(
    creative_url: str,
    creative_format: str,
    review_criteria: str,
    promoted_offering: str | None,
    gemini_key: str
) -> tuple[str, str]:
    """Review a creative against defined criteria.

    Returns:
        Tuple of (decision, reasoning) where decision is "approved" or "rejected"
    """
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    Review this advertising creative based on the criteria below.

    Creative URL: {creative_url}
    Format: {creative_format}
    {f"Promoted Offering: {promoted_offering}" if promoted_offering else ""}

    REVIEW CRITERIA:
    {review_criteria}

    INSTRUCTIONS:
    1. Carefully review the creative against each criterion
    2. Decide: APPROVE or REJECT
    3. Explain your reasoning in 2-3 sentences

    Respond in this exact format:
    DECISION: [APPROVE or REJECT]
    REASONING: [Your explanation]
    """

    response = model.generate_content(prompt)
    text = response.text.strip()

    # Parse response
    decision_line = [line for line in text.split('\n') if line.startswith('DECISION:')][0]
    reasoning_line = [line for line in text.split('\n') if line.startswith('REASONING:')][0]

    decision = 'approved' if 'APPROVE' in decision_line.upper() else 'rejected'
    reasoning = reasoning_line.replace('REASONING:', '').strip()

    return decision, reasoning
```

## Display in UI

**File**: `templates/creative_management.html` (lines 94-100)

Already implemented! The template checks for `creative.data.get('ai_summary')` and displays it:

```html
<!-- AI Creative Summary (if available) -->
{% if creative.data.get('ai_summary') %}
<div style="margin-bottom: 1rem; padding: 1rem; background: #f0fdf4; border-left: 4px solid #10b981; border-radius: 4px;">
    <div style="font-weight: 600; color: #047857; margin-bottom: 0.5rem;">🤖 AI Summary</div>
    <div style="color: #374151; font-size: 0.9rem; line-height: 1.5;">{{ creative.data.get('ai_summary') }}</div>
</div>
{% endif %}
```

## User Experience Flow

1. **User uploads creative** → `sync_creatives` endpoint
2. **Check approval mode**:
   - If `ai-powered`: Generate summary + review → Show summary immediately
   - If `auto-approve`: Generate summary only (no review) → Approve + show summary
   - If `require-human`: Don't generate summary (optional) → Pending status
3. **Display in UI**: Green box with 🤖 emoji showing summary
4. **User can click "View Preview"**: Modal opens with full creative preview

## Benefits

- **Quick scanning**: See what creatives are about without clicking
- **Context at-a-glance**: Understand creative content before reviewing
- **AI transparency**: Shows what AI "sees" in the creative
- **Non-blocking**: Summary generation failure doesn't block creative sync

## Testing

1. Set `approval_mode = 'ai-powered'` in tenant settings
2. Configure Gemini API key in General Settings → AI Services
3. Upload/sync a creative with a clear image URL
4. Verify AI summary appears in green box on Creative Management page
5. Check that summary is stored in `creatives.data['ai_summary']` in database

## Future Enhancements

- **Vision API**: Use Gemini Vision to analyze image/video content directly
- **Multi-language**: Detect creative language and summarize accordingly
- **Brand detection**: Identify brands/logos in creative
- **Sentiment analysis**: Detect tone/emotion of creative
- **Compliance check**: Flag potential regulatory issues
