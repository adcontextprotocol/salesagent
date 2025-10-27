# Database Resilience Features

## Overview

The AdCP Sales Agent has been enhanced with comprehensive database resilience features to prevent cascading failures when the database becomes slow or unresponsive.

## Problem

When a PostgreSQL database hangs or becomes slow:
- Application threads block waiting for queries
- Connection pool exhausts
- HTTP requests timeout (resulting in 502 errors)
- System becomes unresponsive even after database recovers
- Cascading failures across all services

## Solution

### 1. Query-Level Timeouts

**PostgreSQL Statement Timeout**: Every query has a hard timeout at the database level.

```python
# Configuration via environment variables
DATABASE_QUERY_TIMEOUT=30  # Default: 30 seconds
DATABASE_CONNECT_TIMEOUT=10  # Default: 10 seconds
DATABASE_POOL_TIMEOUT=30  # Default: 30 seconds
```

**How it works:**
- Sets PostgreSQL `statement_timeout` parameter on every connection using SQLAlchemy event listeners
- Compatible with both direct PostgreSQL and PgBouncer (PgBouncer doesn't support startup parameters)
- Database automatically terminates queries exceeding the timeout
- Raises `OperationalError` in Python code
- No application code can bypass this timeout

### 2. Connection Pool Management

**Optimized Pool Settings**:

**Direct PostgreSQL**:
```python
pool_size=10           # Base connections always available
max_overflow=20        # Additional connections when needed
pool_timeout=30        # Wait time for connection from pool
pool_recycle=3600      # Recycle connections after 1 hour
pool_pre_ping=True     # Test connections before use
```

**PgBouncer** (automatically detected via port 6543 or `USE_PGBOUNCER=true`):
```python
pool_size=2            # Small pool - PgBouncer handles pooling
max_overflow=5         # Limited overflow
pool_timeout=30        # Wait time for connection from pool
pool_recycle=300       # 5 minutes - shorter since PgBouncer manages connections
pool_pre_ping=False    # Disabled - can cause issues with transaction pooling
```

**Benefits:**
- Prevents connection leaks
- Detects stale connections (direct PostgreSQL only)
- Limits total connections to prevent overwhelming database
- PgBouncer-optimized settings reduce overhead when using connection pooler

### 3. Circuit Breaker Pattern

**Fail-Fast Protection**: When database is unhealthy, fail immediately instead of waiting.

```python
# After database error, system fails fast for 10 seconds
if not _is_healthy:
    if time_since_check < 10:
        raise RuntimeError("Database unhealthy - failing fast")
```

**How it works:**
1. Database connection error occurs
2. System marks database as unhealthy
3. For next 10 seconds, all database requests fail immediately
4. After 10 seconds, system allows retry attempt
5. If retry succeeds, circuit closes and normal operation resumes

**Benefits:**
- Prevents thread exhaustion
- Allows quick recovery
- Reduces load on struggling database
- Provides clear error messages

### 4. Health Check API

**Database Health Monitoring**:
```python
from src.core.database.database_session import check_database_health

healthy, message = check_database_health(force=True)
# Returns: (True, "healthy") or (False, "Database unhealthy: ...")
```

**Features:**
- Lightweight `SELECT 1` query
- 60-second cache to prevent health check spam
- Reports connection errors with details
- Can be integrated into `/health` endpoints

### 5. Connection Pool Monitoring

**Real-time Pool Statistics**:
```python
from src.core.database.database_session import get_pool_status

status = get_pool_status()
# Returns: {
#   "size": 10,
#   "checked_in": 8,
#   "checked_out": 2,
#   "overflow": 0,
#   "total_connections": 10
# }
```

**Use cases:**
- Monitor connection usage
- Detect connection leaks
- Capacity planning
- Alert on pool exhaustion

## Configuration

### Environment Variables

```bash
# Query timeout (seconds) - how long a single query can run
DATABASE_QUERY_TIMEOUT=30

# Connection timeout (seconds) - how long to wait for initial connection
DATABASE_CONNECT_TIMEOUT=10

# Pool timeout (seconds) - how long to wait for connection from pool
DATABASE_POOL_TIMEOUT=30
```

### Recommended Settings

**Development:**
```bash
DATABASE_QUERY_TIMEOUT=10   # Catch slow queries quickly
DATABASE_CONNECT_TIMEOUT=5
DATABASE_POOL_TIMEOUT=10
```

**Production:**
```bash
DATABASE_QUERY_TIMEOUT=30   # Allow complex queries to complete
DATABASE_CONNECT_TIMEOUT=10
DATABASE_POOL_TIMEOUT=30
```

**High-Load Production:**
```bash
DATABASE_QUERY_TIMEOUT=60   # Long-running reports may need more time
DATABASE_CONNECT_TIMEOUT=15
DATABASE_POOL_TIMEOUT=45
```

## Testing

Run the resilience tests:
```bash
# All database resilience tests
uv run pytest tests/integration/test_database_timeouts.py -v

# Specific tests
uv run pytest tests/integration/test_database_timeouts.py::test_circuit_breaker_fail_fast -v
uv run pytest tests/integration/test_database_timeouts.py::test_statement_timeout_enforced -v
```

## Monitoring

### Metrics to Track

1. **Database Health**: Check `check_database_health()` regularly
2. **Pool Status**: Monitor `get_pool_status()` for exhaustion
3. **Query Timeouts**: Count `OperationalError` with "statement timeout"
4. **Circuit Breaker Trips**: Count "failing fast" errors

### Alerting Thresholds

- **Critical**: Circuit breaker open for >60 seconds
- **Warning**: Pool utilization >80% (checked_out / size)
- **Warning**: >10 query timeouts per minute
- **Info**: Database health check fails

## Troubleshooting

### Database Hanging (Original Issue)

**Symptoms:**
- 502 Bad Gateway errors
- Slow API responses
- Connection pool exhaustion

**Resolution:**
1. Check database health: `check_database_health(force=True)`
2. Monitor pool status: `get_pool_status()`
3. Review query timeouts in logs
4. Identify slow queries with `pg_stat_statements`
5. Consider increasing timeouts temporarily

### Circuit Breaker Tripping Frequently

**Symptoms:**
- "Database unhealthy - failing fast" errors
- Intermittent 503 errors
- Works when retrying after 10 seconds

**Resolution:**
1. Check database server health
2. Review database logs for connection issues
3. Check network connectivity
4. Consider increasing `DATABASE_CONNECT_TIMEOUT`
5. Investigate slow queries causing timeouts

### Connection Pool Exhaustion

**Symptoms:**
- "Pool timeout" errors
- Increasing response times
- Many checked-out connections

**Resolution:**
1. Check for connection leaks (not closing sessions)
2. Review long-running transactions
3. Consider increasing `pool_size` or `max_overflow`
4. Add connection pool monitoring

### PgBouncer Compatibility Issues

**Symptoms:**
- "unsupported startup parameter in options: statement_timeout" error
- Connection failures when using PgBouncer
- Application works with direct PostgreSQL but fails with PgBouncer

**Resolution:**
This issue has been fixed in the codebase. The application now:
1. Automatically detects PgBouncer connections (port 6543 or `USE_PGBOUNCER=true`)
2. Uses SQLAlchemy event listeners to set `statement_timeout` after connection
3. Avoids passing startup parameters that PgBouncer doesn't support
4. Uses PgBouncer-optimized pool settings (smaller pool, no pre-ping)

**Manual Override:**
If PgBouncer isn't auto-detected, set: `USE_PGBOUNCER=true`

## Implementation Details

### Files Modified

- `src/core/database/database_session.py` - Core resilience features
- `tests/integration/test_database_timeouts.py` - Comprehensive tests

### Key Functions

- `get_db_session()` - Enhanced with circuit breaker
- `check_database_health()` - Health monitoring
- `get_pool_status()` - Pool statistics
- `execute_with_retry()` - Automatic retry logic

## Future Improvements

1. **Metrics Export**: Prometheus/StatsD integration
2. **Adaptive Timeouts**: Adjust based on query patterns
3. **Query Logging**: Track slow queries automatically
4. **Connection Pooling**: Per-service pool isolation
5. **Read Replicas**: Distribute read load

## References

- PostgreSQL Statement Timeout: https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-STATEMENT-TIMEOUT
- SQLAlchemy Connection Pooling: https://docs.sqlalchemy.org/en/20/core/pooling.html
- Circuit Breaker Pattern: https://martinfowler.com/bliki/CircuitBreaker.html
