# Setup Checklist UX Flow

## User Experience States

### State 1: Fresh Tenant (0% Complete)

**Dashboard View:**
```
╔══════════════════════════════════════════════════════════════╗
║  Setup Progress                                      0%      ║
║  Complete setup to start taking orders          0/15 tasks  ║
║                                                              ║
║  Progress: [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]              ║
║                                                              ║
║  🚨 CRITICAL TASKS                                          ║
║  ❌ Currency Configuration                                   ║
║     At least one currency must be configured                ║
║     [Configure →]                                           ║
║                                                              ║
║  ❌ Ad Server Integration                                    ║
║     Connect to your ad server (GAM, Kevel, or Mock)         ║
║     [Configure →]                                           ║
║                                                              ║
║  ❌ Authorized Properties                                    ║
║     Configure properties with addagents.json                ║
║     [Configure →]                                           ║
║                                                              ║
║  Critical: 0/7  Recommended: 0/5  Optional: 0/2            ║
║                                                              ║
║  [View Full Setup Checklist →]                             ║
╚══════════════════════════════════════════════════════════════╝
```

**Behavior:**
- Widget prominently displayed at top of dashboard
- Shows first 3 incomplete critical tasks
- Each task has direct action link to configuration page
- Users can click "View Full Setup Checklist" for complete view

---

### State 2: Partial Setup (50% Complete - Some Critical Tasks Remain)

**Dashboard View:**
```
╔══════════════════════════════════════════════════════════════╗
║  Setup Progress                                     50%      ║
║  Complete setup to start taking orders          8/15 tasks  ║
║                                                              ║
║  Progress: [████████████████░░░░░░░░░░░░░░░░░]             ║
║                                                              ║
║  🚨 CRITICAL TASKS                                          ║
║  ❌ Products                                                 ║
║     Create at least one advertising product                 ║
║     [Configure →]                                           ║
║                                                              ║
║  ❌ Advertisers (Principals)                                ║
║     Create principals for advertisers who will buy          ║
║     [Configure →]                                           ║
║                                                              ║
║  Critical: 5/7  Recommended: 3/5  Optional: 0/2            ║
║                                                              ║
║  [View Full Setup Checklist →]                             ║
╚══════════════════════════════════════════════════════════════╝
```

**Behavior:**
- Progress bar shows visual progress
- Only incomplete critical tasks shown
- Widget remains prominent until critical tasks complete

---

### State 3: Critical Complete (70% Complete - Recommended Tasks Remain)

**Dashboard View:**
```
╔══════════════════════════════════════════════════════════════╗
║  Setup Progress                                     70%      ║
║  ✅ Ready to take orders!                        11/15 tasks ║
║                                                              ║
║  Progress: [██████████████████████████░░░░░░░░]             ║
║                                                              ║
║  🎉 All Critical Tasks Complete!                           ║
║  Your sales agent is ready to take orders from advertisers. ║
║  ───────────────────────────────────────────────────────    ║
║  ✨ Consider completing these recommended tasks:            ║
║  ⚠️ Naming Conventions                                      ║
║  ⚠️ Budget Controls                                         ║
║                                                              ║
║  Critical: 7/7  Recommended: 2/5  Optional: 2/2            ║
║                                                              ║
║  [View Full Setup Checklist →]                             ║
╚══════════════════════════════════════════════════════════════╝
```

**Behavior:**
- ✅ **Widget still visible** - Users can see recommended tasks
- Shows success state for critical completion
- Lists 2-3 incomplete recommended tasks as suggestions
- Users can still access full checklist via button
- Widget provides ongoing value even after orders are enabled

---

### State 4: 100% Complete (All Tasks Done)

**Dashboard View:**
```
╔══════════════════════════════════════════════════════════════╗
║  Setup Progress                                    100%      ║
║  ✅ Ready to take orders!                        15/15 tasks ║
║                                                              ║
║  Progress: [████████████████████████████████████████████]   ║
║                                                              ║
║  🎉 All Critical Tasks Complete!                           ║
║  Your sales agent is ready to take orders from advertisers. ║
║                                                              ║
║  Critical: 7/7  Recommended: 5/5  Optional: 2/2            ║
║                                                              ║
║  [View Full Setup Checklist →]                             ║
╚══════════════════════════════════════════════════════════════╝
```

**Behavior:**
- Widget remains visible even at 100%
- Shows completion success state
- Quick stats show perfect scores
- Full checklist link always available

---

## Full Checklist Page

Accessible at `/tenant/{id}/setup-checklist` at any time.

**Features:**
- Complete view of all 15 tasks
- Organized by priority (Critical → Recommended → Optional)
- Each task shows:
  - ✅/❌/⚠️ status icon
  - Task name and description
  - Current status details
  - Action button (if incomplete)
- Priority "Next Steps" section at top
- Success banner when critical complete

**Page Layout:**
```
┌─────────────────────────────────────────────────────┐
│  ← Back to Dashboard                                │
│                                                      │
│  ┌─────────────── Setup Checklist ───────────────┐ │
│  │              Progress: 70%                      │ │
│  │           11 of 15 tasks complete               │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─────────────── Next Steps ────────────────────┐ │
│  │ 1. Products: Create at least one product       │ │
│  │ 2. Principals: Create advertiser principals    │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  🚨 CRITICAL TASKS (Required)                       │
│  ┌─────────────────────────────────────────────┐   │
│  │ ✅ Gemini API Key                            │   │
│  │    GEMINI_API_KEY configured                 │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ ❌ Products                                  │   │
│  │    Create at least one advertising product   │   │
│  │    No products created                       │   │
│  │    [Configure]                               │   │
│  └─────────────────────────────────────────────┘   │
│  ...                                                │
│                                                      │
│  ⚠️ RECOMMENDED TASKS                               │
│  [Similar card layout]                              │
│                                                      │
│  💡 OPTIONAL ENHANCEMENTS                           │
│  [Similar card layout]                              │
└─────────────────────────────────────────────────────┘
```

---

## Error Messages

### Attempting Order with Incomplete Setup

When user (or their agent) tries to create a media buy before completing critical tasks:

```
Error: Setup incomplete. Please complete the following required tasks:

  - Products: Create at least one advertising product
  - Principals: Create principals for advertisers who will buy inventory

Visit the setup checklist at /tenant/acme_corp/setup-checklist for details.
```

**Behavior:**
- Clear, actionable error message
- Lists specific incomplete tasks
- Provides direct link to checklist
- Only blocks if critical tasks incomplete (not recommended/optional)

---

## Key Design Decisions

### Why Widget Stays Visible After Critical Complete

1. **Recommended Tasks Matter** - Budget controls, naming conventions, etc. improve operations
2. **Easy Access** - Users don't need to hunt for the checklist page
3. **Progress Motivation** - Seeing 70% → 100% encourages completion
4. **No Hidden Features** - Users aware of optional enhancements

### Why Not Auto-Hide at 100%

1. **Reference Value** - Users may want to revisit what's configured
2. **New Team Members** - Useful for onboarding new admins
3. **Consistency** - Widget location stays stable
4. **Minimal Intrusion** - Compact widget doesn't clutter dashboard
5. **Quick Access** - Always one click to full checklist

### Alternative: Collapsible Widget

Future enhancement could make widget collapsible:
- Collapsed state shows just "Setup: 100% ✓ [Expand]"
- User preference persisted in local storage
- Default: expanded until 100%, then collapsed

---

## Task Priority Classification

### Critical (Blocks Orders)
- Currency Configuration
- Ad Server Integration
- Authorized Properties
- Inventory Sync
- Products
- Principals
- ~~Gemini API Key~~ (Recommended, not blocking)

### Recommended (Best Practices)
- Gemini API Key (AI features)
- Creative Approval Guidelines
- Naming Conventions
- Budget Controls
- Slack Integration
- Tenant CNAME (Custom Domain)

### Optional (Nice-to-Have)
- Signals Discovery Agent (AXE)
- Multiple Currencies

---

## Mobile Considerations

Widget is responsive and collapses gracefully:
- Progress bar remains visible
- Quick stats stack vertically
- Action buttons remain accessible
- Full checklist page scrolls smoothly

---

## Accessibility

- Semantic HTML with proper headings
- ARIA labels for progress indicators
- Keyboard navigation for all actions
- High contrast color schemes
- Screen reader friendly task descriptions

---

## Analytics Tracking (Future)

Potential metrics to track:
- Time to complete each task
- Most commonly skipped recommended tasks
- Average setup time (0% → ready for orders)
- Correlation between setup completion and order volume
- Common drop-off points in setup flow
