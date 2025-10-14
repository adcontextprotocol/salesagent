# Format Discovery UX Improvements

## Current Problems

### 1. **No Agent Attribution**
Formats from all creative agents are flattened into one list. Can't tell:
- Which agent provided which format
- If format is from default AdCP agent vs custom agent
- Priority/trust level of format source

### 2. **No Size/Dimension Display**
Format cards don't show:
- Dimensions (300×250, 728×90)
- Aspect ratio
- File size requirements
- Duration (for video)

### 3. **Limited Filtering**
Only search by text. Missing:
- Filter by size/dimensions
- Filter by category (IAB standard, generative, custom)
- Filter by agent source
- Filter by format type (display/video/native/audio)

### 4. **No Size-Based Discovery**
Can't answer: "Show me all formats that work with 300×250"

### 5. **No Inventory Integration**
GAM workflow is broken:
- "Select Ad Units" fails (inventory-list endpoint)
- Can't analyze inventory sizes
- Can't suggest compatible formats based on ad units

## Proposed Solutions

### Solution 1: Agent-Grouped Display

**Current:**
```
Display
├─ display_300x250_image
├─ display_300x250_generative
├─ display_728x90_image
```

**Proposed:**
```
AdCP Standard Agent (creative.adcontextprotocol.org)
├─ Display (3 formats)
│  ├─ 300×250 - Medium Rectangle [display_300x250_image]
│  ├─ 728×90 - Leaderboard [display_728x90_image]
├─ Video (2 formats)
│  ├─ 640×480 - Instream [video_640x480_instream]

Custom Agency Agent (agency.example.com)  🔒 Premium
├─ Display (2 formats)
│  ├─ 300×600 - Half Page [display_300x600_agency_premium]
```

### Solution 2: Rich Format Cards

**Current Card:**
```
┌──────────────────────────────┐
│ Display 300x250 Image        │
│ Standard display format      │
└──────────────────────────────┘
```

**Proposed Card:**
```
┌──────────────────────────────┐
│ ✓ Display 300×250 Image      │ ← Selected state
│ 300×250 • IAB Standard       │ ← Dimensions • Category
│ Static Image • 150KB max     │ ← Type • Size limit
│                              │
│ 🌐 AdCP Standard Agent       │ ← Agent source
│ 🎨 AI-Powered variant        │ ← Tags
└──────────────────────────────┘
```

### Solution 3: Advanced Filtering

**Filter Bar:**
```
┌─────────────────────────────────────────────────────────────┐
│ Search: [_________________________]  🔍                     │
│                                                             │
│ Agent:      [All ▼] [AdCP Standard] [Custom]               │
│ Format:     [All ▼] [Display] [Video] [Native] [Audio]     │
│ Size:       [All ▼] [300×250] [728×90] [1×1] [Custom...]   │
│ Category:   [All ▼] [IAB Standard] [Generative] [Custom]   │
│ Capability: [All ▼] [Static] [Animated] [Interactive]      │
│                                                             │
│ Showing 12 of 47 formats                    [Clear Filters]│
└─────────────────────────────────────────────────────────────┘
```

### Solution 4: Size-Based Recommendations

**"Smart Select by Inventory" Flow:**

1. **User clicks "Analyze Inventory"**
2. System queries GAM for selected ad units
3. Extracts unique sizes: `[300×250, 728×90, 1×1]`
4. Shows recommendation screen:

```
Inventory Analysis

Your selected ad units support these sizes:

┌─────────────────────────────────────────────────────────────┐
│ 300×250 (15 ad units)                                       │
│ Recommended formats:                                        │
│ ☑ display_300x250_image          (Required - IAB standard) │
│ ☑ display_300x250_generative     (Expand reach - AI)       │
│ ☐ video_300x250_instream        (Optional - video)         │
├─────────────────────────────────────────────────────────────┤
│ 728×90 (8 ad units)                                         │
│ Recommended formats:                                        │
│ ☑ display_728x90_image          (Required - IAB standard)  │
├─────────────────────────────────────────────────────────────┤
│ 1×1 (5 ad units) - Native Indicator                        │
│ ⚠️ Native size requires format selection:                   │
│ ☑ native_in_feed_image          (Static native)            │
│ ☑ native_in_feed_video          (Video native)             │
│ ☐ native_content_recommendation (Sidebar widget)           │
└─────────────────────────────────────────────────────────────┘

[Select All Recommended] [Customize Selection]
```

### Solution 5: Format Details Panel

**Click format card → Side panel opens:**

```
┌─────────────────────────────────────────────────────────────┐
│ Display 300×250 - Medium Rectangle                     [×]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Format ID: display_300x250_image                            │
│ Agent: AdCP Standard (creative.adcontextprotocol.org)       │
│                                                             │
│ Specifications:                                             │
│ • Dimensions: 300×250 pixels                                │
│ • Type: Static Display                                      │
│ • Category: IAB Standard                                    │
│ • File Formats: JPG, PNG, GIF                               │
│ • Max File Size: 150 KB                                     │
│ • Animation: Up to 30 seconds                               │
│                                                             │
│ Required Assets:                                            │
│ • image_asset (300×250, JPG/PNG)                            │
│ • click_url (Landing page URL)                              │
│                                                             │
│ Compatible With:                                            │
│ • GAM Ad Units: 300×250 sizes                               │
│ • Placements: Display, Content                              │
│                                                             │
│ [Preview Sample] [View Schema] [Add to Product]            │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Data Model Enhancement (30 min)
**Goal:** Preserve agent source in format data

```python
# Current: Flattens agent info
for agent_url, formats in data.agents.items():
    formats.forEach(fmt => {
        allFormats.push(fmt);  # ❌ Lost agent_url!
    });

# Proposed: Keep agent info
for agent_url, formats in data.agents.items():
    formats.forEach(fmt => {
        allFormats.push({
            ...fmt,
            agent_url: agent_url,
            agent_name: getAgentName(agent_url),  # "AdCP Standard"
            is_standard: isStandardAgent(agent_url)
        });
    });
```

### Phase 2: Rich Format Cards (1 hour)
**Goal:** Display dimensions, category, agent

```javascript
function renderFormatCard(format) {
    // Extract dimensions
    const dims = extractDimensions(format);  // "300×250"

    // Determine category badge
    const categoryBadge = format.category === 'generative'
        ? '<span class="badge badge-ai">🎨 AI-Generated</span>'
        : '<span class="badge badge-iab">IAB Standard</span>';

    return `
        <div class="format-card ${isSelected ? 'selected' : ''}">
            <div class="format-header">
                <h4>${format.name}</h4>
                ${isSelected ? '<span class="check">✓</span>' : ''}
            </div>

            <div class="format-meta">
                <span class="dimensions">${dims}</span>
                <span class="separator">•</span>
                <span class="type">${format.type}</span>
            </div>

            ${categoryBadge}

            <div class="format-agent">
                <small>🌐 ${format.agent_name}</small>
            </div>
        </div>
    `;
}
```

### Phase 3: Multi-Level Grouping (1.5 hours)
**Goal:** Group by agent first, then by type

```javascript
function displayFormatsGrouped(formats) {
    // Group by agent
    const byAgent = groupBy(formats, 'agent_url');

    let html = '';
    for (const [agentUrl, agentFormats] of Object.entries(byAgent)) {
        const agentName = agentFormats[0].agent_name;
        const isStandard = agentFormats[0].is_standard;

        html += `
            <div class="agent-section ${isStandard ? 'standard' : 'custom'}">
                <h3>
                    ${agentName}
                    ${isStandard ? '<span class="badge">Official</span>' : '<span class="badge premium">Custom</span>'}
                </h3>

                ${renderFormatsByType(agentFormats)}
            </div>
        `;
    }

    return html;
}

function renderFormatsByType(formats) {
    const byType = groupBy(formats, 'type');

    let html = '';
    for (const [type, typeFormats] of Object.entries(byType)) {
        html += `
            <details open>
                <summary>${capitalize(type)} (${typeFormats.length})</summary>
                <div class="format-grid">
                    ${typeFormats.map(renderFormatCard).join('')}
                </div>
            </details>
        `;
    }

    return html;
}
```

### Phase 4: Advanced Filters (2 hours)
**Goal:** Filter by size, agent, category, type

```javascript
const filters = {
    agent: 'all',      // 'all', 'standard', agent_url
    type: 'all',       // 'all', 'display', 'video', 'native'
    size: 'all',       // 'all', '300x250', '728x90', etc.
    category: 'all',   // 'all', 'iab', 'generative', 'custom'
    search: ''
};

function applyFilters(formats, filters) {
    return formats.filter(fmt => {
        // Agent filter
        if (filters.agent !== 'all') {
            if (filters.agent === 'standard' && !fmt.is_standard) return false;
            if (filters.agent !== 'standard' && fmt.agent_url !== filters.agent) return false;
        }

        // Type filter
        if (filters.type !== 'all' && fmt.type !== filters.type) return false;

        // Size filter
        if (filters.size !== 'all') {
            const dims = extractDimensions(fmt);
            if (dims !== filters.size) return false;
        }

        // Category filter
        if (filters.category !== 'all' && fmt.category !== filters.category) return false;

        // Search filter
        if (filters.search) {
            const searchLower = filters.search.toLowerCase();
            return (
                fmt.format_id.toLowerCase().includes(searchLower) ||
                fmt.name.toLowerCase().includes(searchLower) ||
                (fmt.description || '').toLowerCase().includes(searchLower) ||
                extractDimensions(fmt).includes(searchLower)
            );
        }

        return true;
    });
}
```

### Phase 5: Size Extraction Helper (30 min)
**Goal:** Extract dimensions from format metadata

```javascript
function extractDimensions(format) {
    // Check format_id first
    const idMatch = format.format_id.match(/(\d+)x(\d+)/);
    if (idMatch) {
        return `${idMatch[1]}×${idMatch[2]}`;
    }

    // Check requirements object
    if (format.requirements) {
        const { width, height } = format.requirements;
        if (width && height) {
            return `${width}×${height}`;
        }
    }

    // Check for native indicator
    if (format.type === 'native' || format.format_id.includes('native')) {
        return '1×1 (Native)';
    }

    return null;
}
```

## Benefits

1. **Agent Transparency**: Users see where formats come from
2. **Better Discovery**: Filter by size, see compatible formats
3. **Size Visibility**: Dimensions prominently displayed
4. **Smart Selection**: Inventory analysis suggests formats
5. **Organized Display**: Grouped by agent, then type
6. **Rich Context**: Category badges, agent attribution
7. **Search Improvements**: Search by dimensions (e.g., "300x250")

## Next Steps

1. ✅ Document the approach (this file)
2. ⏳ Implement data model changes (preserve agent_url)
3. ⏳ Implement rich format cards with dimensions
4. ⏳ Implement agent grouping
5. ⏳ Implement advanced filters
6. ⏳ Fix inventory-list endpoint error
7. ⏳ Implement inventory analysis flow

## Related Work

- **Size Mapping System** (see `format-size-mapping-proposal.md`)
- **Inventory Integration** (fix GAM ad unit selection)
- **Format Schema Validation** (ensure dimensions in schema)
