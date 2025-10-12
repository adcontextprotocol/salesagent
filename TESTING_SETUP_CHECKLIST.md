# Testing Setup Checklist System

## Services Running

All containers are up and healthy:

- **Admin UI**: http://localhost:8001
- **MCP Server**: http://localhost:8090 (port 8080 in container)
- **A2A Server**: http://localhost:8094 (port 8091 in container)
- **PostgreSQL**: localhost:5442

## Test Scenarios

### 1. Fresh Tenant (0% Complete)

**Create new test tenant:**
```bash
docker exec -it hartford-adcp-server-1 python scripts/setup/setup_tenant.py "Test Publisher" \
  --adapter mock \
  --admin-email test@example.com
```

**Expected Widget:**
```
Setup Progress: ~15%
Complete setup to start taking orders (2/15 tasks)

🚨 CRITICAL TASKS
❌ Currency Configuration
❌ Authorized Properties
❌ Inventory Sync
❌ Products
❌ Principals

Critical: 2/7  Recommended: 0/5  Optional: 0/2
```

**Test:**
1. Go to http://localhost:8001
2. Login with `test@example.com`
3. Click on "Test Publisher" tenant
4. See setup widget with critical tasks highlighted
5. Click "View Full Setup Checklist" → See full page

---

### 2. Partially Complete Tenant (50%)

**Complete some tasks:**
```bash
# Add currency
docker exec -it hartford-adcp-server-1 python -c "
from src.core.database.database_session import get_db_session
from src.core.database.models import CurrencyLimit

with get_db_session() as session:
    currency = CurrencyLimit(
        tenant_id='test_publisher',
        currency_code='USD',
        min_package_budget=0.0,
        max_daily_package_spend=10000.0
    )
    session.add(currency)
    session.commit()
    print('✅ Currency added')
"

# Add product via Admin UI:
# - Go to Products section
# - Click "Create Product"
# - Fill in basic info
```

**Expected Widget:**
```
Setup Progress: ~50%
Complete setup to start taking orders (8/15 tasks)

🚨 CRITICAL TASKS
❌ Principals (remaining)
[Other tasks completed]

Critical: 6/7  Recommended: 2/5  Optional: 0/2
```

---

### 3. Critical Complete (70% - Ready for Orders)

**Complete remaining critical tasks:**
```bash
# Add principal via Admin UI:
# - Go to Settings → Advertisers
# - Click "Add Principal"
# - Fill in advertiser name
```

**Expected Widget:**
```
Setup Progress: 70%
✅ Ready to take orders! (11/15 tasks)

🎉 All Critical Tasks Complete!
Your sales agent is ready to take orders.
─────────────────────────────────────
✨ Consider completing these recommended tasks:
⚠️ Naming Conventions
⚠️ Budget Controls

Critical: 7/7  Recommended: 2/5  Optional: 2/2
```

**Key Test:**
- Widget shows SUCCESS state
- Shows preview of 2 incomplete recommended tasks
- Full checklist link still available
- Try creating media buy → Should work (no setup validation error)

---

### 4. 100% Complete (All Tasks)

**Complete all recommended tasks:**
```bash
# Via Admin UI Settings:
# - Set naming conventions
# - Set max daily budget
# - Configure Slack webhook
# - Set up custom domain
```

**Expected Widget:**
```
Setup Progress: 100%
✅ Ready to take orders! (15/15 tasks)

🎉 All Critical Tasks Complete!
Your sales agent is ready to take orders.

Critical: 7/7  Recommended: 5/5  Optional: 2/2
```

**Key Test:**
- Widget STILL visible (not hidden)
- Shows perfect completion stats
- No incomplete task preview
- Full checklist shows all ✅

---

## Manual UI Testing

### Dashboard Widget Tests

1. **Widget Visibility**
   - [ ] Widget appears on tenant dashboard
   - [ ] Purple gradient background displays correctly
   - [ ] Progress bar animates smoothly
   - [ ] Quick stats show correct counts

2. **Critical Tasks Section**
   - [ ] Shows max 3 incomplete critical tasks
   - [ ] Each task has Configure button
   - [ ] Button links to correct settings page
   - [ ] Task descriptions are clear

3. **Success State (Critical Complete)**
   - [ ] Shows 🎉 success message
   - [ ] Shows recommended tasks preview (if < 100%)
   - [ ] Preview shows 2 tasks max
   - [ ] Border separator displays correctly

4. **Full Checklist Link**
   - [ ] Button visible at bottom
   - [ ] Hover state changes opacity
   - [ ] Click navigates to `/tenant/{id}/setup-checklist`

### Full Checklist Page Tests

1. **Page Layout**
   - [ ] Back to Dashboard link works
   - [ ] Progress circle shows percentage
   - [ ] Status text matches completion

2. **Next Steps Section** (if critical incomplete)
   - [ ] Shows max 3 priority items
   - [ ] All items are critical tasks
   - [ ] Numbered list format

3. **Task Sections**
   - [ ] Critical section shows all 7 tasks
   - [ ] Recommended section shows all 5 tasks
   - [ ] Optional section shows all 2 tasks
   - [ ] Each section has priority badge

4. **Task Cards**
   - [ ] Complete tasks: green background, ✅ icon
   - [ ] Incomplete tasks: red background, ❌ icon
   - [ ] Configure buttons visible for incomplete
   - [ ] Buttons link to correct pages
   - [ ] Task details show (e.g., "3 currencies configured")

5. **Success Banner** (when critical complete)
   - [ ] Green gradient banner displays
   - [ ] "Ready to take orders!" message
   - [ ] Positioned above task sections

### Action Links Tests

Test each action URL leads to correct page:

| Task | Expected URL | Test |
|------|-------------|------|
| Currency Configuration | `/tenant/{id}/settings#business-rules` | [ ] |
| Ad Server Integration | `/tenant/{id}/settings#adserver` | [ ] |
| Authorized Properties | `/tenant/{id}/authorized-properties` | [ ] |
| Inventory Sync | `/tenant/{id}/settings#inventory` | [ ] |
| Products | `/tenant/{id}/products` | [ ] |
| Principals | `/tenant/{id}/settings#advertisers` | [ ] |
| Creative Approval | `/tenant/{id}/settings#business-rules` | [ ] |
| Naming Conventions | `/tenant/{id}/settings#business-rules` | [ ] |
| Budget Controls | `/tenant/{id}/settings#business-rules` | [ ] |
| Slack Integration | `/tenant/{id}/settings#integrations` | [ ] |
| Custom Domain | `/tenant/{id}/settings#account` | [ ] |

---

## API Testing (Setup Validation)

### Test Setup Incomplete Blocking

**Create tenant without principals:**
```bash
docker exec -it hartford-adcp-server-1 python -c "
from src.services.setup_checklist_service import validate_setup_complete, SetupIncompleteError

try:
    validate_setup_complete('test_publisher')
    print('❌ Should have raised error!')
except SetupIncompleteError as e:
    print('✅ Setup validation blocked correctly')
    print('Missing tasks:', [t['name'] for t in e.missing_tasks])
"
```

### Test Media Buy Creation Blocking

**Try to create media buy without complete setup:**
```bash
# This should fail with clear error message
curl -X POST http://localhost:8090/mcp/ \
  -H "Content-Type: application/json" \
  -H "x-adcp-auth: [your-test-token]" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "create_media_buy",
      "arguments": {
        "promoted_offering": "Test Campaign",
        "product_ids": ["prod_1"],
        "total_budget": 5000,
        "start_date": "2025-11-01",
        "end_date": "2025-11-30"
      }
    }
  }'

# Expected error:
# {
#   "error": {
#     "message": "Setup incomplete. Please complete the following required tasks:\n\n  - Principals: Create principals for advertisers\n\nVisit /tenant/test_publisher/setup-checklist for details."
#   }
# }
```

### Test Media Buy Creation Success (Complete Setup)

After completing all critical tasks, same API call should succeed.

---

## Browser Testing

Test in multiple browsers:
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari

Check:
- [ ] Layout renders correctly
- [ ] Colors and gradients display properly
- [ ] Buttons are clickable
- [ ] Links navigate correctly
- [ ] No console errors

---

## Mobile Responsive Testing

1. Open http://localhost:8001 on mobile device or DevTools mobile view
2. Check:
   - [ ] Widget stacks vertically
   - [ ] Progress bar visible
   - [ ] Task cards readable
   - [ ] Buttons tappable
   - [ ] Full checklist page scrolls smoothly

---

## Performance Testing

1. **Load Time**
   - [ ] Dashboard loads in < 2 seconds
   - [ ] Setup checklist service doesn't slow down dashboard
   - [ ] Database queries are efficient (check logs)

2. **Error Handling**
   - [ ] If tenant not found, shows friendly error
   - [ ] If database error, falls back gracefully (widget doesn't show)
   - [ ] No crashes or 500 errors

---

## Logging & Monitoring

Check logs for:
```bash
# Admin UI logs
docker-compose logs admin-ui | grep -i "setup\|checklist"

# Should see:
# - "Loading setup checklist for tenant: test_publisher"
# - No errors or warnings
```

---

## Test Checklist Summary

| Feature | Status |
|---------|--------|
| Widget displays on dashboard | [ ] |
| Shows correct completion % | [ ] |
| Critical tasks highlighted | [ ] |
| Success state for critical complete | [ ] |
| Recommended tasks preview | [ ] |
| Full checklist page accessible | [ ] |
| All action links work | [ ] |
| Setup validation blocks orders | [ ] |
| Widget stays visible at 100% | [ ] |
| Mobile responsive | [ ] |
| No console errors | [ ] |
| No database errors | [ ] |

---

## Known Issues / Edge Cases

Document any issues found during testing:

1. **Issue**:
   - **Repro**:
   - **Expected**:
   - **Actual**:
   - **Severity**:

---

## Sign-Off

- [ ] All critical features tested
- [ ] No blocking bugs found
- [ ] Ready for production deployment

**Tested By**: _______________
**Date**: _______________
**Notes**: _______________
