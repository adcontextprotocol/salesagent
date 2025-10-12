# Setup Checklist System

## Overview

The setup checklist system helps new Sales Agent users understand what configuration is required before they can take their first order. It provides:

- **Visual progress tracking** - Dashboard widget showing % completion
- **Categorized tasks** - Critical (required), Recommended, and Optional
- **Actionable guidance** - Direct links to configuration pages
- **Validation** - Blocks orders until critical tasks complete

## Components

### 1. SetupChecklistService (`src/services/setup_checklist_service.py`)

Core service that checks tenant configuration status:

```python
from src.services.setup_checklist_service import SetupChecklistService

service = SetupChecklistService(tenant_id)
status = service.get_setup_status()

# Returns:
# {
#   "progress_percent": 60,
#   "completed_count": 9,
#   "total_count": 15,
#   "ready_for_orders": False,
#   "critical": [...],      # Required tasks
#   "recommended": [...],   # Best practices
#   "optional": [...]       # Nice-to-have
# }
```

### 2. Dashboard Widget (`templates/components/setup_checklist_widget.html`)

Appears on tenant dashboard when setup is incomplete:
- Shows progress percentage
- Lists incomplete critical tasks with action links
- Displays success state when all critical tasks complete
- Auto-hides when 100% complete

### 3. Full Checklist Page (`templates/setup_checklist.html`)

Comprehensive view at `/tenant/{id}/setup-checklist`:
- All tasks organized by priority
- Visual indicators (✅/❌/⚠️)
- Detailed descriptions and action buttons
- Priority "Next Steps" section

### 4. Create Media Buy Validation (`src/core/main.py`)

Prevents orders until setup is complete:

```python
# In _create_media_buy_impl():
if not testing_ctx.dry_run and not testing_ctx.test_session_id:
    try:
        validate_setup_complete(tenant["tenant_id"])
    except SetupIncompleteError as e:
        # Return helpful error with missing tasks
        raise ToolError(f"Setup incomplete: {e.missing_tasks}")
```

## Critical Tasks (Required Before Orders)

1. **Gemini API Key** - `GEMINI_API_KEY` environment variable (RECOMMENDED)
   - Required for: AI creative analysis, product recommendations
   - How to fix: Add to `.env.secrets` file
   - Note: While recommended for AI features, not strictly blocking for basic operations

2. **Currency Configuration** - At least one currency (USD/EUR/GBP)
   - Required for: Media buy creation
   - How to fix: Settings → Business Rules → Currency Limits

3. **Ad Server Integration** - Connected adapter (GAM/Kevel/Mock)
   - Required for: Order submission to ad server
   - How to fix: Settings → Ad Server → Select & Configure

4. **Authorized Properties** - Properties with `addagents.json` verification
   - Required for: Property targeting validation
   - How to fix: Inventory → Authorized Properties → Add Property

5. **Inventory Sync** - Ad units imported from ad server
   - Required for: Product-to-inventory mapping
   - How to fix: Settings → Inventory → Sync Inventory

6. **Products** - At least one advertising product
   - Required for: Creating media buys
   - How to fix: Products → Create Product

7. **Principals** - At least one advertiser with API token
   - Required for: API access to create orders
   - How to fix: Settings → Advertisers → Create Principal

## Recommended Tasks

1. **Creative Approval Guidelines** - Auto-approval rules
   - Settings → Business Rules → Approval Workflow

2. **Naming Conventions** - Order/line item templates
   - Settings → Business Rules → Naming Templates

3. **Budget Controls** - Maximum daily budget limits
   - Settings → Business Rules → Budget Limits

4. **Slack Integration** - Webhook for notifications
   - Settings → Integrations → Slack Webhook

5. **Tenant CNAME** - Custom domain configuration
   - Settings → Account → Virtual Host
   - Configure custom subdomain or domain (e.g., ads.publisher.com)

## Optional Tasks

1. **Signals Discovery Agent** - AXE signals for targeting
   - Settings → Integrations → Signals Agent

2. **Multiple Currencies** - EUR, GBP for international buyers
   - Settings → Business Rules → Currency Limits

## Integration Points

### Admin UI Routes (`src/admin/blueprints/tenants.py`)

```python
@tenants_bp.route("/<tenant_id>")
def dashboard(tenant_id):
    # Get setup status for widget
    checklist_service = SetupChecklistService(tenant_id)
    status = checklist_service.get_setup_status()
    if status["progress_percent"] < 100:
        setup_status = status  # Show widget

@tenants_bp.route("/<tenant_id>/setup-checklist")
def setup_checklist(tenant_id):
    # Show full checklist page
    checklist_service = SetupChecklistService(tenant_id)
    setup_status = checklist_service.get_setup_status()
```

### MCP Tool Validation

```python
# In create_media_buy tool:
if not testing_ctx.dry_run:
    validate_setup_complete(tenant_id)
    # Raises SetupIncompleteError if incomplete
```

## Testing

Comprehensive unit tests in `tests/unit/test_setup_checklist_service.py`:

```bash
# Run with PostgreSQL
./run_all_tests.sh ci

# Tests cover:
# - Minimal tenant (all tasks incomplete)
# - Complete tenant (all tasks complete)
# - Partial setup (some tasks complete)
# - Progress calculation
# - Action URL generation
# - Validation functions
```

### Test Fixtures

```python
@pytest.fixture
def setup_minimal_tenant(db_session, test_tenant_id):
    """Incomplete setup - 0% progress."""

@pytest.fixture
def setup_complete_tenant(db_session, test_tenant_id):
    """Complete setup - 100% progress, ready for orders."""
```

## Usage Examples

### Check Setup Status

```python
from src.services.setup_checklist_service import SetupChecklistService

service = SetupChecklistService("acme_corp")
status = service.get_setup_status()

print(f"Progress: {status['progress_percent']}%")
print(f"Ready: {status['ready_for_orders']}")

for task in status['critical']:
    if not task['is_complete']:
        print(f"TODO: {task['name']} - {task['action_url']}")
```

### Get Next Steps

```python
next_steps = service.get_next_steps()
# Returns top 3 prioritized actions:
# [
#   {"title": "Currency Configuration",
#    "description": "...",
#    "action_url": "...",
#    "priority": "critical"},
#   ...
# ]
```

### Validate Before Operations

```python
from src.services.setup_checklist_service import validate_setup_complete, SetupIncompleteError

try:
    validate_setup_complete(tenant_id)
    # Proceed with operation
except SetupIncompleteError as e:
    print(f"Cannot proceed: {e.message}")
    for task in e.missing_tasks:
        print(f"- {task['name']}")
```

## UI Flow

### New Tenant Experience

1. **Tenant Created** → Setup script creates tenant with minimal config
2. **First Login** → Dashboard shows prominent setup widget (0% complete)
3. **Click "View Full Checklist"** → See all tasks with descriptions
4. **Complete Tasks** → Widget updates progress in real-time
5. **All Critical Complete** → Widget shows success message, then hides
6. **Attempt Order** → If incomplete, clear error with task list

### Error Messages

When attempting to create order with incomplete setup:

```
Setup incomplete. Please complete the following required tasks:

  - Currency Configuration: At least one currency must be configured
  - Products: Create at least one advertising product
  - Principals: Create principals for advertisers

Visit the setup checklist at /tenant/acme_corp/setup-checklist for details.
```

## Future Enhancements

Potential improvements:

1. **Guided Setup Wizard** - Step-by-step onboarding flow
2. **Setup Time Estimates** - "5 min remaining"
3. **Auto-Detection** - Suggest values based on OAuth tokens
4. **Task Dependencies** - Gray out tasks until prerequisites complete
5. **Setup Templates** - Quick-start configs for common scenarios
6. **Progress Persistence** - Track when tasks were completed
7. **Team Notifications** - Alert admins about incomplete setups

## Architecture Decisions

### Why Database Query-Based (Not Cached)

- **Real-time accuracy** - Always reflects current state
- **Simple implementation** - No cache invalidation needed
- **Low query cost** - Counts are fast with indexes
- **Infrequent access** - Only shown during initial setup

### Why Skip for Testing

- **Testing flexibility** - Don't require full setup for tests
- **Fast iteration** - Tests run without setup overhead
- **Explicit opt-in** - Testing context clearly marks test runs

### Why Three Priority Levels

- **Critical** - Blocks orders, must complete
- **Recommended** - Best practices, strong encouragement
- **Optional** - Nice-to-have, no pressure

## Related Documentation

- **Setup Guide**: `docs/SETUP.md`
- **Admin UI**: `docs/admin-ui-guide.md`
- **Testing**: `docs/testing/`
- **Database Models**: `src/core/database/models.py`
