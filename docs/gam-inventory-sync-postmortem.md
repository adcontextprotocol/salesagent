# Post-Mortem: GAM Inventory Sync Cascade Failure

## Executive Summary

On [Date], the GAM inventory sync feature experienced a cascade of 12 interconnected failures following a merge from origin/main. The issues stemmed from an incomplete database schema migration that removed a config column without updating all dependent code. This post-mortem analyzes the root causes and provides actionable recommendations.

## Timeline of Events

1. **Initial Error**: 500 error when clicking "Inventory" link in Admin UI
2. **Root Cause**: Database migration removed `config` column from `tenants` table
3. **Cascade Effect**: Each fix revealed another dependency issue
4. **Resolution**: 12 sequential fixes over approximately 2 hours
5. **Final State**: Successful sync of 10,946 GAM inventory items

## Root Cause Analysis

### Primary Root Cause: Incomplete Schema Migration

The database migration that removed the `config` column from the `tenants` table was not accompanied by:
- Updates to all code references
- Testing against a production-like dataset
- Validation of dependent services

### Contributing Factors

1. **Lack of Integration Tests**: No tests validated the full inventory sync workflow
2. **Type System Gaps**: Mixed use of SQLAlchemy ORM and Pydantic models without clear boundaries
3. **External API Changes**: Google Ad Manager API deprecated methods without version pinning
4. **Database Compatibility**: PostgreSQL vs SQLite differences not properly abstracted
5. **No Pre-merge Validation**: Changes merged without running full test suite

## Technical Issues Encountered

### 1. Database Row Access Pattern (Error #1)
```python
# Problem: PostgreSQL returns tuples by default
row = cursor.fetchone()
tenant = dict(zip([col[0] for col in cursor.description], row))

# Solution: Use DictCursor
cursor_factory=psycopg2.extras.DictCursor
```

### 2. Transaction Management (Error #2)
```python
# Problem: Failed operations left transactions in aborted state
# Solution: Use scoped_session for automatic cleanup
from sqlalchemy.orm import scoped_session
db_session = scoped_session(SessionLocal)
```

### 3. Model Confusion (Error #3)
```python
# Problem: Imported SQLAlchemy model instead of Pydantic
from models import Principal  # SQLAlchemy ORM model

# Solution: Import from correct module
from schemas import Principal  # Pydantic API model
```

### 4. Configuration Access (Error #4)
```python
# Problem: Code still referenced removed config column
adapter_config = tenant.config.get('adapters', {})

# Solution: Access normalized columns
adapter_config = {
    'gam_network_code': tenant.gam_network_code,
    'gam_company_id': tenant.gam_company_id
}
```

### 5. Context Manager Support (Error #5)
```python
# Problem: DatabaseConnection didn't support with statement
# Solution: Add __enter__ and __exit__ methods
def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
    return False
```

### 6. Logging Conflicts (Error #6)
```python
# Problem: 'message' key conflicts with LogRecord internals
logger.error("Error", extra={'message': 'details'})

# Solution: Remove conflicting key
error_dict.pop('message', None)
```

### 7. API Method Deprecation (Error #7)
```python
# Problem: GAM API removed new_filter_statement
downloader.new_filter_statement()

# Solution: Use new StatementBuilder
from googleads import ad_manager
statement_builder = ad_manager.StatementBuilder(version='v202411')
```

### 8. SOAP Object Serialization (Error #8)
```python
# Problem: SUDS objects don't support dictionary access
ad_unit['id']

# Solution: Convert to dictionary first
from zeep.helpers import serialize_object
ad_unit_dict = serialize_object(ad_unit)
```

### 9. Column Length Constraints (Error #9)
```sql
-- Problem: inventory_type VARCHAR(20) too short
-- Solution: Increase to VARCHAR(30)
ALTER TABLE gam_inventory ALTER COLUMN inventory_type TYPE VARCHAR(30);
```

### 10-12. Cascading Config References (Errors #10-12)
Multiple files still referenced `tenant.config` after column removal.

## Lessons Learned

### What Went Wrong

1. **Incomplete Migration Testing**: Migration wasn't tested with full application workflow
2. **Lack of Schema Validation**: No automated checks for schema/code consistency
3. **Missing Integration Tests**: Individual components tested but not full workflows
4. **Poor Error Messages**: Initial errors didn't clearly indicate root cause
5. **No Rollback Plan**: No quick way to revert schema changes

### What Went Right

1. **Systematic Debugging**: Each error provided clear next step
2. **Good Logging**: Detailed logs helped identify issues quickly
3. **Modular Architecture**: Issues were isolated to specific components
4. **Docker Environment**: Easy to rebuild and restart services

## Action Items

### Immediate (Within 1 Week)

1. **Add Integration Tests**
   - [ ] Create test for full inventory sync workflow
   - [ ] Test with both PostgreSQL and SQLite
   - [ ] Include all adapter types

2. **Schema Validation**
   - [ ] Add pre-commit hook to check for removed columns
   - [ ] Create automated schema/code consistency check
   - [ ] Document all schema dependencies

3. **API Version Pinning**
   - [ ] Pin all external library versions in requirements.txt
   - [ ] Create compatibility layer for external APIs
   - [ ] Add deprecation warnings for old methods

### Short Term (Within 1 Month)

4. **Improve Testing Infrastructure**
   - [ ] Set up integration test suite in CI/CD
   - [ ] Create production-like test data
   - [ ] Add performance benchmarks

5. **Error Handling**
   - [ ] Improve error messages with root cause hints
   - [ ] Add automatic rollback for failed operations
   - [ ] Create error recovery procedures

6. **Documentation**
   - [ ] Document all external API dependencies
   - [ ] Create troubleshooting guide
   - [ ] Add architecture decision records (ADRs)

### Long Term (Within 3 Months)

7. **Monitoring and Alerting**
   - [ ] Add schema drift detection
   - [ ] Monitor external API deprecations
   - [ ] Create health check dashboard

8. **Development Process**
   - [ ] Require integration tests for schema changes
   - [ ] Implement progressive rollout for migrations
   - [ ] Create disaster recovery procedures

## Prevention Strategy

### 1. Pre-Merge Checklist
```markdown
- [ ] All tests pass (unit + integration)
- [ ] Schema changes tested with full workflow
- [ ] External API calls verified
- [ ] Both databases tested (PostgreSQL + SQLite)
- [ ] Performance impact assessed
- [ ] Rollback procedure documented
```

### 2. Migration Testing Protocol
```bash
# Required before merging any schema change
./scripts/test_migration.sh --full-workflow
./scripts/test_migration.sh --rollback
./scripts/test_migration.sh --performance
```

### 3. Code Review Requirements
- Schema changes require 2 reviewers
- Must include integration test
- Must update all dependent code
- Must include rollback migration

## Conclusion

This incident revealed systemic issues in our development and testing processes. While the immediate issues were resolved, implementing the prevention strategies outlined above is critical to avoiding similar cascading failures in the future.

The key insight is that database schema changes are high-risk operations that require comprehensive testing beyond unit tests. Integration testing with production-like data and workflows must become standard practice.

## Appendix: Fixed Files

1. `db_config.py` - Added DictCursor support
2. `gam_inventory_service.py` - Fixed session management and imports
3. `models.py` - Removed config column, fixed column lengths
4. `adapters/gam_inventory_discovery.py` - Updated to new GAM API
5. `adapters/gam_error_handling.py` - Fixed logging conflicts
6. `adapters/gam_health_check.py` - Updated tenant access patterns
7. `admin_ui.py` - Fixed template references
8. `alembic/versions/009_fix_inventory_type_length.py` - New migration

Total lines changed: ~500 across 8 files