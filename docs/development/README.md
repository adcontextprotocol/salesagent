# Development Guide

Documentation for contributors to the AdCP Sales Agent codebase.

## Getting Started

1. Clone the repository
2. Copy `.env.template` to `.env`
3. Run `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`
4. Access Admin UI at http://localhost:8000/admin

See [Contributing](contributing.md) for detailed development workflows.

## Documentation

- **[Architecture](architecture.md)** - System design and component overview
- **[Contributing](contributing.md)** - Development workflows, testing, code style
- **[Troubleshooting](troubleshooting.md)** - Common development issues

## Key Resources

- **[CLAUDE.md](../../CLAUDE.md)** - Detailed development patterns and conventions
- **[Tests](../../tests/)** - Test suite and examples
- **[Source](../../src/)** - Application source code

## Quick Reference

### Running Tests

```bash
./run_all_tests.sh ci     # Full suite with PostgreSQL
./run_all_tests.sh quick  # Fast iteration

# Manual pytest
uv run pytest tests/unit/ -x
uv run pytest tests/integration/ -x
```

### Code Quality

```bash
# Pre-commit hooks
pre-commit run --all-files

# Type checking
uv run mypy src/core/your_file.py --config-file=mypy.ini
```

### Database Migrations

```bash
uv run python migrate.py                    # Run migrations
uv run alembic revision -m "description"    # Create migration
```
