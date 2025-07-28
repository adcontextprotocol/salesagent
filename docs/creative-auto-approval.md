# Creative Auto-Approval Configuration

## Overview

The AdCP:Buy platform supports configurable auto-approval for creative formats. This allows standard, low-risk formats to bypass human review while maintaining oversight for complex or high-risk formats.

## Configuration

### Basic Setup

In your `config.json`, configure the creative engine with auto-approval formats:

```json
{
  "creative_engine": {
    "adapter": "mock_creative_engine",
    "human_review_required": true,
    "auto_approve_formats": [
      "display_320x50",
      "display_728x90",
      "display_300x250",
      "display_160x600",
      "native_standard"
    ]
  }
}
```

### Configuration Options

- **`human_review_required`**: Global setting for human review requirement
  - `true`: Creatives require review unless format is in auto-approve list
  - `false`: All creatives are auto-approved unless explicitly configured

- **`auto_approve_formats`**: Array of format IDs that bypass human review
  - Standard display banners are good candidates
  - Avoid rich media, video, or interactive formats

## Auto-Approval Logic

The system uses the following logic to determine creative approval:

1. **Format in auto-approve list**: Creative is immediately approved
2. **Format NOT in list + human review required**: Creative goes to pending review
3. **Format NOT in list + human review NOT required**: Creative is auto-approved

## Recommended Auto-Approve Formats

### Display Formats
- `display_320x50` - Mobile banner
- `display_728x90` - Leaderboard
- `display_300x250` - Medium rectangle
- `display_160x600` - Wide skyscraper
- `display_970x90` - Super leaderboard
- `display_320x100` - Large mobile banner

### Native Formats
- `native_standard` - Standard native ad
- `native_content_card` - Content recommendation

### Audio Formats (Simple)
- `audio_15s` - 15-second audio spot
- `audio_30s` - 30-second audio spot

## Formats Requiring Review

These formats should typically require human review:

### Rich Media
- `rich_media_expandable`
- `rich_media_interstitial`
- `html5_interactive`
- `rich_media_pushdown`

### Video
- `video_16x9`
- `video_vertical`
- `video_outstream`
- `video_rewarded`

### Special Formats
- `dooh_digital_billboard`
- `custom_takeover`
- `page_skin`

## Benefits

1. **Faster Time to Market**: Standard formats go live immediately
2. **Reduced Workload**: Admin team focuses on complex creatives
3. **Consistency**: Standard formats have predictable behavior
4. **Flexibility**: Easy to adjust auto-approve list as needed

## Security Considerations

- Auto-approval does NOT bypass:
  - Principal authentication
  - Format validation
  - Content URI verification
  - Ad server compatibility checks

- Admins can still:
  - Review all creatives (including auto-approved)
  - Revoke approval status
  - Update auto-approve lists

## Monitoring

Track auto-approval effectiveness:

```sql
-- Count of auto-approved vs manually reviewed
SELECT 
  CASE 
    WHEN status = 'approved' AND detail LIKE '%auto-approved%' THEN 'Auto'
    ELSE 'Manual'
  END as approval_type,
  COUNT(*) as count
FROM creative_statuses
GROUP BY approval_type;

-- Formats most commonly auto-approved
SELECT 
  format_id,
  COUNT(*) as auto_approved_count
FROM creatives c
JOIN creative_statuses cs ON c.creative_id = cs.creative_id
WHERE cs.status = 'approved' 
  AND cs.detail LIKE '%auto-approved%'
GROUP BY format_id
ORDER BY auto_approved_count DESC;
```

## Best Practices

1. **Start Conservative**: Begin with basic display formats only
2. **Monitor Quality**: Track any issues with auto-approved creatives
3. **Regular Reviews**: Audit auto-approve list quarterly
4. **Document Changes**: Log when and why formats are added/removed
5. **Partner Feedback**: Adjust based on advertiser satisfaction

## Migration Path

To enable auto-approval in an existing system:

1. Identify most common creative formats
2. Review historical approval rates
3. Select formats with >95% approval rate
4. Add to auto-approve list
5. Monitor for 30 days
6. Expand list based on results