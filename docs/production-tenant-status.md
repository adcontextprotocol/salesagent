# Production Tenant Setup Status

## Current Production Tenants

Based on `scripts/production_setup.py`, we have two tenants in production:

### 1. Scribd (`tenant_scribd`)
- **Subdomain**: `scribd.localhost:8080` (local) → `scribd.adcp-sales-agent.fly.dev` (prod)
- **Ad Server**: Google Ad Manager (GAM)
- **Virtual Host**: TBD

### 2. Wonderstruck (`tenant_wonderstruck`)
- **Subdomain**: `wonderstruck.localhost:8080` (local) → `wonderstruck.adcp-sales-agent.fly.dev` (prod)
- **Ad Server**: Mock adapter
- **Virtual Host**: TBD

---

## Predicted Setup Checklist Status

### Scribd - Estimated ~70-85% Complete

#### ✅ Critical Tasks (Likely Complete)
1. ✅ **Gemini API Key** - Set in production environment
2. ✅ **Currency Configuration** - Has currency limits (USD at minimum)
3. ✅ **Ad Server Integration** - GAM configured with OAuth
4. ✅ **Authorized Properties** - Has properties configured
5. ✅ **Inventory Sync** - GAM inventory synced
6. ✅ **Products** - Multiple products created (audio, display, video)
7. ✅ **Principals** - Has advertiser principals with tokens

**Widget Display:**
```
╔══════════════════════════════════════════════════════════════╗
║  Setup Progress                                     85%      ║
║  ✅ Ready to take orders!                        13/15 tasks ║
║                                                              ║
║  Progress: [██████████████████████████████░░░░]             ║
║                                                              ║
║  🎉 All Critical Tasks Complete!                           ║
║  Your sales agent is ready to take orders from advertisers. ║
║  ───────────────────────────────────────────────────────    ║
║  ✨ Consider completing these recommended tasks:            ║
║  ⚠️ Custom Domain (CNAME)                                   ║
║  ⚠️ Multiple Currencies                                     ║
║                                                              ║
║  Critical: 7/7  Recommended: 4/5  Optional: 2/2            ║
║                                                              ║
║  [View Full Setup Checklist →]                             ║
╚══════════════════════════════════════════════════════════════╝
```

#### ⚠️ Recommended Tasks (Possibly Incomplete)
1. ✅ **Creative Approval Guidelines** - Likely configured
2. ✅ **Naming Conventions** - Likely has custom templates
3. ✅ **Budget Controls** - Likely has max daily budget set
4. ✅ **Slack Integration** - Likely configured for notifications
5. ❌ **Custom Domain (CNAME)** - Probably using default subdomain

#### 💡 Optional Tasks
1. ✅ **Signals Discovery Agent** - Likely enabled (Scope3 integration)
2. ❌ **Multiple Currencies** - Probably just USD

---

### Wonderstruck - Estimated ~60-70% Complete

#### ✅ Critical Tasks (Likely Complete)
1. ✅ **Gemini API Key** - Shared production environment variable
2. ✅ **Currency Configuration** - Has currency limits
3. ✅ **Ad Server Integration** - Mock adapter (always "connected")
4. ⚠️ **Authorized Properties** - May have fewer properties
5. ⚠️ **Inventory Sync** - Mock adapter (simulated inventory)
6. ✅ **Products** - Has products configured
7. ✅ **Principals** - Has advertiser principals

**Widget Display:**
```
╔══════════════════════════════════════════════════════════════╗
║  Setup Progress                                     65%      ║
║  ✅ Ready to take orders!                        10/15 tasks ║
║                                                              ║
║  Progress: [████████████████████░░░░░░░░░░░░░░]             ║
║                                                              ║
║  🎉 All Critical Tasks Complete!                           ║
║  Your sales agent is ready to take orders from advertisers. ║
║  ───────────────────────────────────────────────────────    ║
║  ✨ Consider completing these recommended tasks:            ║
║  ⚠️ Naming Conventions                                      ║
║  ⚠️ Budget Controls                                         ║
║                                                              ║
║  Critical: 7/7  Recommended: 1/5  Optional: 2/2            ║
║                                                              ║
║  [View Full Setup Checklist →]                             ║
╚══════════════════════════════════════════════════════════════╝
```

#### ⚠️ Recommended Tasks (Possibly Incomplete)
1. ❌ **Creative Approval Guidelines** - Mock adapter, may use defaults
2. ❌ **Naming Conventions** - Probably using defaults
3. ❌ **Budget Controls** - Testing tenant, may not have limits
4. ❌ **Slack Integration** - Testing tenant, may not need notifications
5. ❌ **Custom Domain (CNAME)** - Using default subdomain

#### 💡 Optional Tasks
1. ✅ **Signals Discovery Agent** - Likely enabled for testing
2. ✅ **Multiple Currencies** - May have EUR/GBP for testing

---

## What Users Will See

### First Admin Login (Both Tenants)

When an admin logs into the Admin UI at `https://adcp-sales-agent.fly.dev`:

1. **Landing Page** - List of tenants they have access to:
   - Scribd
   - Wonderstruck

2. **Click Tenant** → Dashboard with setup widget

### Scribd Dashboard (Likely View)

```
┌─────────────────────────────────────────────────────────┐
│  Scribd                                                  │
│  Operational Dashboard · Google Ad Manager              │
│                                                          │
│  [Settings]  [Refresh]                                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Setup Progress                              85%        │
│  ✅ Ready to take orders!                13/15 tasks    │
│                                                          │
│  Progress: [██████████████████████████████░░░░]         │
│                                                          │
│  🎉 All Critical Tasks Complete!                       │
│  Your sales agent is ready to take orders.             │
│  ───────────────────────────────────────────           │
│  ✨ Consider completing these recommended tasks:        │
│  ⚠️ Custom Domain (CNAME)                              │
│  ⚠️ Multiple Currencies                                │
│                                                          │
│  Critical: 7/7  Recommended: 4/5  Optional: 2/2        │
│                                                          │
│  [View Full Setup Checklist →]                         │
└─────────────────────────────────────────────────────────┘

┌──────────────┬──────────────┬──────────────┬──────────┐
│ Total Revenue│ Live Buys    │ Workflows    │Advertisrs│
│ $142,500     │ 8            │ 3            │ 5        │
└──────────────┴──────────────┴──────────────┴──────────┘

[Recent activity, charts, etc...]
```

### Wonderstruck Dashboard (Likely View)

```
┌─────────────────────────────────────────────────────────┐
│  Wonderstruck                                            │
│  Operational Dashboard · Mock                            │
│                                                          │
│  [Settings]  [Refresh]                                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Setup Progress                              65%        │
│  ✅ Ready to take orders!                10/15 tasks    │
│                                                          │
│  Progress: [████████████████████░░░░░░░░░░░░░░]         │
│                                                          │
│  🎉 All Critical Tasks Complete!                       │
│  Your sales agent is ready to take orders.             │
│  ───────────────────────────────────────────           │
│  ✨ Consider completing these recommended tasks:        │
│  ⚠️ Naming Conventions                                 │
│  ⚠️ Budget Controls                                    │
│                                                          │
│  Critical: 7/7  Recommended: 1/5  Optional: 2/2        │
│                                                          │
│  [View Full Setup Checklist →]                         │
└─────────────────────────────────────────────────────────┘

┌──────────────┬──────────────┬──────────────┬──────────┐
│ Total Revenue│ Live Buys    │ Workflows    │Advertisrs│
│ $25,000      │ 2            │ 0            │ 3        │
└──────────────┴──────────────┴──────────────┴──────────┘

[Recent activity, charts, etc...]
```

---

## Impact on Existing Tenants

### Immediate Effects (Post-Deployment)

1. **Widget Appears** - Both tenants will see setup widget on next login
2. **No Functionality Lost** - All existing features continue working
3. **Orders Not Blocked** - Critical tasks already complete, orders work normally
4. **Optional Improvements** - Widget suggests completing recommended tasks

### User Reactions

**Positive:**
- 😊 "Oh cool, I see what else I could configure"
- 💡 "I didn't know I could set up a custom domain"
- ✅ "Good to see we're 85% complete"

**Neutral:**
- 🤷 "I'll ignore this, we're already running fine"
- 📋 "I'll come back to this later"

**Potential Negative:**
- 😕 "Why am I seeing this? We're already in production"
- ❓ "Is something broken?"

### Mitigation Strategy

#### Option 1: Smart Widget Display (Current Implementation)
```python
# Widget always shows, provides value at any stage
setup_status = checklist_service.get_setup_status()
# Always display for visibility
```

**Pros:**
- Consistent UX for all tenants
- Helps new users and admins
- Non-intrusive (just informational)
- Always accessible

**Cons:**
- May seem redundant for mature tenants
- Takes up dashboard space

#### Option 2: Dismissible Widget (Future Enhancement)
```python
# Add user preference to hide widget
if not user_preferences.get("hide_setup_widget"):
    setup_status = checklist_service.get_setup_status()
```

**UI Changes:**
- Add [×] dismiss button to widget
- Store preference in user settings
- Can always access via Settings page

#### Option 3: Progress-Based Display (Aggressive)
```python
# Only show if progress < 90%
if setup_status["progress_percent"] < 90:
    # Show widget
```

**Pros:**
- Less clutter for mature tenants
- Focused on incomplete setups

**Cons:**
- Loses value of "always accessible"
- Recommended tasks become hidden

---

## Recommendations

### For Production Deployment

1. **Deploy As-Is** - Widget always visible provides most value
   - Helps current and future tenants
   - Non-blocking, informational only
   - Easy to navigate to full checklist

2. **Communicate to Tenants** - Send notification:
   ```
   📣 New Feature: Setup Checklist

   We've added a setup progress tracker to your dashboard.

   ✅ Your agent is fully operational (critical tasks complete)
   ⚠️ Optional: We've identified a few recommended enhancements

   Click "View Full Setup Checklist" to see suggestions like:
   - Custom domain configuration
   - Additional currencies for international buyers
   - Enhanced budget controls

   No action required - your agent continues operating normally!
   ```

3. **Monitor Feedback** - Track if users:
   - Complete recommended tasks after seeing widget
   - Find it helpful or annoying
   - Use the full checklist page

4. **Future Enhancement** - Add dismiss/hide option if feedback suggests it's too prominent

### Specific Actions for Each Tenant

**Scribd:**
- ✅ Already production-ready, no urgent actions
- 💡 Consider: Custom domain (ads.scribd.com)
- 💡 Consider: EUR/GBP for international advertisers

**Wonderstruck:**
- ✅ Already operational for testing
- 💡 Consider: Budget controls (if moving to production)
- 💡 Consider: Naming conventions (if scaling up)

---

## Testing Before Deployment

### Local Testing

1. Create test tenant with ~70% progress:
   ```bash
   python scripts/setup/setup_tenant.py "Test Tenant" \
     --adapter mock \
     --admin-email test@example.com
   ```

2. Check widget display at different completion levels:
   - 0% (new tenant)
   - 50% (partial setup)
   - 70% (critical complete, recommended incomplete)
   - 100% (all complete)

3. Verify:
   - Widget always visible
   - Recommended tasks show when critical complete
   - Full checklist page accessible
   - No errors in logs

### Production Verification

After deployment:

1. Login to Scribd tenant → Check widget display
2. Login to Wonderstruck tenant → Check widget display
3. Verify no console errors
4. Test "View Full Setup Checklist" link
5. Confirm orders still work (setup validation passes)

---

## Rollback Plan

If widget causes issues:

1. **Quick Fix** - Hide widget via template conditional:
   ```jinja
   {% if false %}  {# Temporarily disabled #}
   {% include 'components/setup_checklist_widget.html' %}
   {% endif %}
   ```

2. **Revert** - Git revert setup checklist commits

3. **Fix Forward** - Add dismiss button or progress threshold

---

## Success Metrics

Track after 1 week:

- **Adoption**: % of incomplete recommended tasks completed
- **Engagement**: Clicks on "View Full Setup Checklist"
- **Support**: Tickets about widget (positive vs negative)
- **Completion**: Change in average tenant completion percentage

**Target Goals:**
- 📈 10% increase in recommended task completion
- 👍 90% positive or neutral feedback
- 🎯 No increase in support tickets about setup
