#!/bin/bash
# Analyze creative data structures in production database via fly proxy
#
# Usage:
#   ./scripts/analyze_production_creatives.sh
#
# This script:
# 1. Starts fly proxy to production database (port 15432)
# 2. Runs analysis query
# 3. Cleans up proxy

set -e

echo "=================================="
echo "Production Creative Data Analysis"
echo "=================================="
echo ""

# Check if fly is available
if ! command -v fly &> /dev/null; then
    echo "Error: fly CLI not found. Install with: brew install flyctl"
    exit 1
fi

# Determine app name
APP_NAME="${FLY_APP_NAME:-adcp-sales-agent}"
echo "Using app: $APP_NAME"
echo ""

# Start proxy in background
echo "Starting fly postgres proxy..."
fly proxy 15432:5432 -a "$APP_NAME" &
PROXY_PID=$!

# Wait for proxy to be ready
echo "Waiting for proxy to be ready..."
sleep 3

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up proxy..."
    kill $PROXY_PID 2>/dev/null || true
}
trap cleanup EXIT

# Get database URL from fly
echo "Getting database credentials..."
DB_URL=$(fly postgres connect -a "$APP_NAME" --quiet 2>/dev/null | grep -o 'postgres://[^"]*' | head -1)

if [ -z "$DB_URL" ]; then
    echo "Warning: Could not auto-detect database URL"
    echo "Using default connection to localhost:15432..."
    DB_URL="postgresql://postgres@localhost:15432/postgres"
fi

# Modify URL to use proxy port
DB_URL_PROXY=$(echo "$DB_URL" | sed 's/:5432/:15432/g' | sed 's/@[^:]*:/@localhost:/g')

echo "Connecting via: localhost:15432"
echo ""

# Run analysis query
echo "Running analysis query..."
echo ""

psql "$DB_URL_PROXY" <<'EOSQL'
-- Creative Data Structure Analysis
-- Analyzes creative.data JSONB field to understand structure patterns

\echo '================================================================================';
\echo 'Production Creative Data Structure Analysis';
\echo '================================================================================';
\echo '';

-- Total count
\echo 'Total Creatives:';
SELECT COUNT(*) as total FROM creatives;
\echo '';

-- Sample structure analysis
\echo 'Structure Type Distribution (sample of 50 most recent):';
\echo '';

WITH sample_creatives AS (
    SELECT
        creative_id,
        name,
        format,
        agent_url,
        data,
        created_at
    FROM creatives
    ORDER BY created_at DESC
    LIMIT 50
),
structure_analysis AS (
    SELECT
        creative_id,
        name,
        format,
        agent_url,
        -- Detect structure type
        CASE
            WHEN data ? 'assets' AND jsonb_typeof(data->'assets') = 'object'
                 AND jsonb_object_keys_count(data->'assets') > 0
                THEN 'adcp_v2.4'
            WHEN data ? 'url' OR data ? 'width' OR data ? 'height'
                THEN 'legacy'
            ELSE 'unknown'
        END as structure_type,
        data ? 'assets' as has_assets,
        data ? 'url' as has_url,
        data ? 'width' as has_width,
        data ? 'height' as has_height,
        data ? 'preview_url' as has_preview_url,
        CASE
            WHEN data ? 'assets' AND jsonb_typeof(data->'assets') = 'object'
                THEN jsonb_object_keys_count(data->'assets')
            ELSE 0
        END as assets_count,
        jsonb_object_keys(data) as top_level_fields
    FROM sample_creatives
)
SELECT
    structure_type,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM structure_analysis), 1) as percentage
FROM structure_analysis
GROUP BY structure_type
ORDER BY count DESC;

\echo '';
\echo 'Field Presence in Sample:';
SELECT
    COUNT(*) FILTER (WHERE has_assets) as with_assets_dict,
    COUNT(*) FILTER (WHERE has_url OR has_width) as with_legacy_fields,
    COUNT(*) FILTER (WHERE has_preview_url) as with_preview_url,
    AVG(assets_count) as avg_assets_count
FROM (
    SELECT
        data ? 'assets' AND jsonb_typeof(data->'assets') = 'object' AND jsonb_object_keys_count(data->'assets') > 0 as has_assets,
        data ? 'url' as has_url,
        data ? 'width' as has_width,
        data ? 'preview_url' as has_preview_url,
        CASE
            WHEN data ? 'assets' AND jsonb_typeof(data->'assets') = 'object'
                THEN jsonb_object_keys_count(data->'assets')
            ELSE 0
        END as assets_count
    FROM creatives
    ORDER BY created_at DESC
    LIMIT 50
) sub;

\echo '';
\echo 'Sample AdCP v2.4 Structure (with assets dict):';
SELECT
    creative_id,
    name,
    format,
    jsonb_pretty(data) as data_sample
FROM creatives
WHERE data ? 'assets'
    AND jsonb_typeof(data->'assets') = 'object'
    AND jsonb_object_keys_count(data->'assets') > 0
ORDER BY created_at DESC
LIMIT 1;

\echo '';
\echo 'Sample Legacy Structure (with top-level url/dimensions):';
SELECT
    creative_id,
    name,
    format,
    jsonb_pretty(data) as data_sample
FROM creatives
WHERE (data ? 'url' OR data ? 'width')
    AND NOT (data ? 'assets' AND jsonb_typeof(data->'assets') = 'object')
ORDER BY created_at DESC
LIMIT 1;

\echo '';
\echo 'Top-Level Keys Distribution:';
SELECT
    key,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM creatives LIMIT 50), 1) as percentage
FROM (
    SELECT jsonb_object_keys(data) as key
    FROM creatives
    ORDER BY created_at DESC
    LIMIT 50
) keys
GROUP BY key
ORDER BY count DESC
LIMIT 20;

\echo '';
\echo '================================================================================';
\echo 'Analysis Complete';
\echo '================================================================================';
\echo '';
\echo 'Interpretation:';
\echo '  - adcp_v2.4: Uses assets dict (modern, spec-compliant)';
\echo '  - legacy: Uses top-level url/width/height fields';
\echo '  - unknown: Neither pattern (empty or unusual structure)';
\echo '';
\echo 'Migration Recommendation:';
\echo '  - If 100% adcp_v2.4: Remove _extract_creative_url_and_dimensions()';
\echo '  - If mixed: Keep extraction for backwards compatibility';
\echo '  - If mostly legacy: Create one-time migration script';
\echo '';

-- Helper function for counting object keys
CREATE OR REPLACE FUNCTION jsonb_object_keys_count(j jsonb)
RETURNS int AS $$
    SELECT COUNT(*)::int FROM jsonb_object_keys(j);
$$ LANGUAGE SQL IMMUTABLE;
EOSQL

echo ""
echo "Analysis complete!"
echo ""
echo "To run again: ./scripts/analyze_production_creatives.sh"
