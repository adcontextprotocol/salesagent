# Changesets

This directory contains changeset files for tracking version changes.

## Quick Start

```bash
# Generate a changeset
npx changeset

# Follow the interactive prompts to select version bump type and describe your changes
```

## What are changesets?

Changesets declare changes that should result in a version bump. Each file describes:
- **Version bump type**: patch, minor, or major
- **Summary**: What changed
- **Package**: Which package is affected (for monorepos)

## Version Bump Types

- `patch`: Bug fixes and minor updates (0.1.0 → 0.1.1)
- `minor`: New features (0.1.0 → 0.2.0)
- `major`: Breaking changes (0.1.0 → 1.0.0)

## Manual Changeset Creation

If you prefer not to use the CLI, create a markdown file:

**Example:** `.changeset/fix-auth-bug.md`

```markdown
---
"adcp-sales-agent": patch
---

Fixed authentication bug in GAM adapter that prevented OAuth token refresh
```

**Naming convention:** Use descriptive names like `fix-schema-validation.md` or `add-pricing-model.md`

## CI Requirements

✅ **Required**: All PRs must include a changeset file

❌ **Exceptions**: PRs labeled with `skip-changeset` (docs, tests, tooling only)

## Release Process

1. **Merge PR** with changeset to `main`
2. **Automated PR created**: "Version Packages" PR combines all changesets
3. **Merge Version PR**: Publishes new version automatically
4. **Version sync**: Both `package.json` and `pyproject.toml` updated

See [Contributing section in README](../README.md#changesets-for-version-management) for more details.
