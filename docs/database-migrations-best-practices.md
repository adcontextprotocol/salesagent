# Alembic Migration Best Practices

## Problem: Multiple Migration Heads

When multiple feature branches each add database migrations and are then merged, Alembic ends up with multiple "head" revisions, causing:

```
❌ Error running migrations: Multiple head revisions are present for given argument 'head'
```

This breaks database initialization and causes CI failures.

## Why This Happens

```
main branch:        A → B → C
                           ↓
feature-1:                 └→ D (adds migration 001)
                           ↓
feature-2:                 └→ E (adds migration 002)
                           ↓
After merge:        A → B → C → D → E
                               ↙   ↘
                            001   002  ← Multiple heads!
```

Both migrations point to the same parent (C), creating two heads.

## Our Solution Strategy

We use a **multi-layered defense** to prevent and fix multiple heads:

### 1. Pre-Commit Hook (First Line of Defense)
- **When**: Before every commit
- **What**: Detects multiple heads immediately
- **Action**: Blocks commit, requires fix before proceeding
- **Installed**: Automatically via pre-commit framework

```bash
# Runs automatically on 'git commit'
# Checks: uv run python scripts/ops/check_migration_heads.py --quiet
```

### 2. Pre-Push Hook (Second Line of Defense)
- **When**: Before pushing to remote
- **What**: Final check before code reaches GitHub
- **Action**: Offers to auto-merge or blocks push
- **Installed**: Run `./scripts/setup/install_git_hooks.sh`

```bash
# Runs automatically on 'git push'
# 1. Checks for multiple heads
# 2. Offers to auto-merge
# 3. Runs full test suite (CI mode)
```

### 3. Manual Tools (When Needed)

#### Check for Multiple Heads
```bash
# Just check (exit 1 if multiple heads)
uv run python scripts/ops/check_migration_heads.py

# Quiet mode (for scripts)
uv run python scripts/ops/check_migration_heads.py --quiet

# Auto-fix
uv run python scripts/ops/check_migration_heads.py --fix
```

#### Auto-Merge Script
```bash
# Interactive - asks for confirmation
./scripts/ops/auto_merge_migrations.sh

# Non-interactive (for CI)
CI=1 ./scripts/ops/auto_merge_migrations.sh
```

## Workflow: How to Handle Multiple Heads

### Scenario 1: Detected Before Commit (Ideal)
```bash
$ git commit -m "Add new feature"

🔍 Check for multiple Alembic migration heads...
❌ Multiple migration heads detected!

# Fix it:
$ uv run python scripts/ops/check_migration_heads.py --fix
✅ Created merge migration

$ git add alembic/versions/*_merge_migration_heads.py
$ git commit -m "Merge Alembic migration heads"
```

### Scenario 2: Detected Before Push
```bash
$ git push

🔍 Checking Alembic migration heads...
❌ Multiple Alembic migration heads detected!

Options:
  1. Auto-merge (recommended):
     ./scripts/ops/auto_merge_migrations.sh

  2. Manual merge:
     uv run alembic merge -m 'Merge migration heads' head

# Choose auto-merge:
$ ./scripts/ops/auto_merge_migrations.sh
Auto-merge migrations? (y/N): y
✅ Migration heads merged and committed

# Now push again:
$ git push
```

### Scenario 3: After Merging PR (Emergency)
```bash
# Multiple heads made it to main (CI failed)
$ git checkout main
$ git pull

# Create merge migration
$ uv run alembic merge -m "Merge migration heads" head
Generating merge revision...
  Merging revisions:
    - abc123de (feature 1)
    - def456gh (feature 2)
  ... into merge_revision_xyz789

# Review the generated file
$ cat alembic/versions/xyz789_merge_migration_heads.py

# Test it works
$ uv run python scripts/ops/migrate.py

# Commit and push
$ git add alembic/versions/xyz789_merge_migration_heads.py
$ git commit -m "Merge Alembic migration heads from main

Multiple heads occurred after merging PRs #123 and #124.
Both added migrations from common ancestor.

This merge migration resolves the conflict."

$ git push
```

## Best Practices for Team Development

### 1. Always Pull Before Creating Migrations
```bash
# ✅ CORRECT
git checkout main
git pull
git checkout -b feature/new-thing
# ... make changes ...
uv run alembic revision -m "Add new table"

# ❌ WRONG
git checkout -b feature/new-thing  # Stale main branch!
# ... make changes ...
uv run alembic revision -m "Add new table"  # Will create conflict later
```

### 2. Rebase Before Merging
```bash
# When your PR is ready
git checkout feature/new-thing
git fetch origin
git rebase origin/main

# If migrations conflict, fix them now:
uv run python scripts/ops/check_migration_heads.py --fix
git add alembic/versions/*.py
git rebase --continue
```

### 3. Check Before Pushing
```bash
# Pre-push hook runs automatically, but you can check manually:
uv run python scripts/ops/check_migration_heads.py

# Run full CI tests locally before pushing:
./run_all_tests.sh ci
```

### 4. Monitor CI
- If CI fails with "Multiple head revisions", fix immediately:
  1. Pull latest main
  2. Create merge migration
  3. Push fix to main

## Advanced: Manual Merge Migration

Sometimes you need to create a merge migration manually with specific properties:

```bash
# Create merge migration
uv run alembic merge -m "Merge migration heads from PR #123 and #124" abc123,def456

# Edit the generated file if needed
# Example: alembic/versions/xyz789_merge_migration_heads.py

"""Merge migration heads from PR #123 and #124

Revision ID: xyz789
Revises: abc123, def456
Create Date: 2025-10-09 17:00:00.000000
"""

from collections.abc import Sequence

revision: str = "xyz789"
down_revision: str | Sequence[str] | None = ("abc123", "def456")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    """Upgrade schema."""
    # Usually empty for merge migrations
    pass

def downgrade() -> None:
    """Downgrade schema."""
    # Usually empty for merge migrations
    pass
```

## Migration Naming Conventions

Merge migrations are automatically named:
- Auto-generated: `xyz789_merge_migration_heads.py`
- With context: `xyz789_merge_migration_heads_from_main_and_feature_x.py`

Regular migrations use sequential numbers:
- `001_initial_schema.py`
- `002_add_user_table.py`
- etc.

## Troubleshooting

### "Can't locate revision identified by 'head'"
```bash
# Check current heads
uv run alembic heads

# If multiple heads, merge them:
uv run python scripts/ops/check_migration_heads.py --fix
```

### "Can't locate revision identified by 'abc123'"
This means a migration file is missing or corrupted.

```bash
# List all revisions
uv run alembic history

# Check if file exists
ls -la alembic/versions/*abc123*.py

# If missing, you may need to restore from git history
git log --all --full-history -- "alembic/versions/*abc123*"
```

### Pre-commit hook too slow
The migration head check is very fast (<1 second). If it's slow, check:

```bash
# Ensure uv is installed and working
uv --version

# Test the check directly
time uv run python scripts/ops/check_migration_heads.py --quiet
```

## Tools Reference

### `scripts/ops/check_migration_heads.py`
Python script to detect and fix multiple heads.

**Usage:**
```bash
# Check only (exit 1 if multiple heads)
python scripts/ops/check_migration_heads.py

# Auto-fix
python scripts/ops/check_migration_heads.py --fix

# Quiet mode (for scripts)
python scripts/ops/check_migration_heads.py --quiet
```

### `scripts/ops/auto_merge_migrations.sh`
Bash script for interactive migration merging.

**Usage:**
```bash
# Interactive mode (asks for confirmation)
./scripts/ops/auto_merge_migrations.sh

# Non-interactive (CI mode)
CI=1 ./scripts/ops/auto_merge_migrations.sh
```

### `scripts/setup/install_git_hooks.sh`
Installs pre-push hook with migration checking.

**Usage:**
```bash
# Install hooks
./scripts/setup/install_git_hooks.sh

# Check what's installed
cat .git/hooks/pre-push
```

## Summary

**Prevention:**
1. ✅ Pre-commit hook catches multiple heads immediately
2. ✅ Pre-push hook provides final safety net
3. ✅ Always pull latest main before creating migrations
4. ✅ Rebase feature branches before merging

**Detection:**
- Pre-commit: Automatic on every commit
- Pre-push: Automatic before every push
- Manual: `uv run python scripts/ops/check_migration_heads.py`

**Fix:**
- Auto: `uv run python scripts/ops/check_migration_heads.py --fix`
- Interactive: `./scripts/ops/auto_merge_migrations.sh`
- Manual: `uv run alembic merge -m 'message' head`

**Result:**
- No more CI failures from multiple heads
- Automatic detection and resolution
- Clear error messages and fix instructions
- Minimal disruption to development workflow
