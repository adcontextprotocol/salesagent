# AEE (Ad Effectiveness Engine) Integration Guide

## Overview

The AdCP:Buy platform supports integration with Ad Effectiveness Engine (AEE) signals through managed-only targeting dimensions. This allows the orchestrator to leverage AEE insights for campaign optimization without exposing internal signals to external principals.

## Targeting Access Levels

### 1. Overlay Access
These dimensions can be set by principals via the public API:
- Geographic: country, region, metro, city, postal
- Device: type, make, OS, browser
- Content: category, language, rating
- Media: type (video, display, native, etc.)
- Audience: third-party segments
- Time: dayparting
- Frequency: capping rules

### 2. Managed-Only Access
These dimensions are ONLY settable by the orchestrator/AEE:
- **key_value_pairs**: Generic key-value targeting for AEE signals
- **aee_segment**: AEE-computed audience segments
- **aee_score**: Effectiveness scores
- **aee_context**: Contextual signals

### 3. Both (Hybrid Access)
- **custom**: Platform-specific targeting (some fields overlay, some managed)

## AEE Signal Implementation

### Key-Value Pairs

The primary mechanism for AEE integration is the `key_value_pairs` field in targeting:

```json
{
  "targeting_overlay": {
    "geo_country_any_of": ["US"],
    "device_type_any_of": ["mobile", "desktop"],
    "key_value_pairs": {
      "aee_segment": "high_value_pet_owner",
      "aee_score": "0.85",
      "aee_recency": "7d",
      "aee_frequency": "high",
      "aee_context": "shopping_intent"
    }
  }
}
```

### Platform Mapping

#### Google Ad Manager
- Maps to GAM's custom key-value targeting
- Appears in line items as custom criteria
- Can be used for reporting and optimization

```javascript
// GAM sees:
customTargeting: {
  "aee_segment": "high_value_pet_owner",
  "aee_score": "0.85"
}
```

#### Kevel
- Maps to Kevel's CustomTargeting expressions
- Uses UserDB for user-level signals

```javascript
// Kevel sees:
CustomTargeting: "$user.aee_segment CONTAINS \"high_value_pet_owner\" AND $user.aee_score CONTAINS \"0.85\""
```

#### Triton Digital
- Maps to custom audience attributes
- Integrates with station-level targeting

## Validation and Security

### API Validation

The system prevents principals from setting managed-only dimensions:

```python
# This will fail with validation error:
create_media_buy({
  "targeting_overlay": {
    "geo_country_any_of": ["US"],  # ✓ OK - overlay access
    "key_value_pairs": {           # ✗ ERROR - managed-only
      "custom_key": "value"
    }
  }
})

# Error: "Targeting validation failed: key_value_pairs is managed-only and cannot be set via overlay"
```

### Orchestrator Usage

The orchestrator CAN set managed-only dimensions:

```python
# Orchestrator adds AEE signals to existing targeting
targeting = media_buy.targeting_overlay
targeting.key_value_pairs = {
    "aee_segment": compute_segment(principal, campaign),
    "aee_score": calculate_effectiveness_score(historical_data),
    "aee_context": determine_context(campaign_type)
}
update_media_buy(media_buy_id, targeting_overlay=targeting)
```

## Best Practices

### 1. Signal Naming Convention
Use consistent prefixes for AEE signals:
- `aee_*` for AEE-computed values
- `ml_*` for machine learning predictions
- `rt_*` for real-time signals

### 2. Value Formatting
- Scores: Use decimal strings ("0.85")
- Segments: Use underscore_separated names
- Timestamps: Use ISO format or relative ("7d", "24h")

### 3. Signal Documentation
Document all AEE signals in use:

| Signal | Description | Values | Update Frequency |
|--------|-------------|--------|------------------|
| aee_segment | Computed audience segment | high_value, medium_value, low_value | Daily |
| aee_score | Effectiveness prediction | 0.0-1.0 | Hourly |
| aee_recency | Last interaction | 1d, 7d, 30d | Real-time |

### 4. Gradual Rollout
1. Start with one signal (e.g., aee_segment)
2. Monitor performance impact
3. Add additional signals incrementally
4. A/B test signal combinations

## Monitoring and Reporting

### Signal Performance
Track which AEE signals drive performance:

```sql
-- Analyze performance by AEE segment
SELECT 
  json_extract(targeting, '$.key_value_pairs.aee_segment') as segment,
  AVG(ctr) as avg_ctr,
  AVG(conversion_rate) as avg_cvr,
  COUNT(*) as impressions
FROM delivery_data
WHERE json_extract(targeting, '$.key_value_pairs.aee_segment') IS NOT NULL
GROUP BY segment
ORDER BY avg_cvr DESC;
```

### Signal Coverage
Monitor how many campaigns use AEE signals:

```sql
-- Coverage metrics
SELECT 
  COUNT(CASE WHEN key_value_pairs IS NOT NULL THEN 1 END) as with_aee,
  COUNT(*) as total,
  COUNT(CASE WHEN key_value_pairs IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) as coverage_pct
FROM media_buys
WHERE status = 'active';
```

## Future Enhancements

### 1. Dynamic Signal Updates
- Real-time signal updates during flight
- Automatic optimization based on performance

### 2. Signal Marketplace
- Publishers can offer proprietary signals
- Revenue sharing for high-value signals

### 3. Cross-Platform Intelligence
- Learn from GAM performance to optimize Kevel
- Unified AEE scoring across platforms

### 4. Privacy-Preserving Signals
- Differential privacy for sensitive segments
- Cohort-based targeting for privacy compliance