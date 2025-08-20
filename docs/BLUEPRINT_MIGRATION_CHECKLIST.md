# Flask Blueprint Migration Checklist

This document provides a comprehensive checklist for migrating Flask routes to blueprints to prevent template rendering errors and ensure smooth migrations.

## Pre-Migration Checklist

- [ ] **Identify all routes** to be migrated
- [ ] **List all templates** that reference these routes
- [ ] **Document all `url_for()` calls** that will need updating
- [ ] **Run baseline tests** to ensure everything works before migration

## Migration Steps

### 1. Create Blueprint Structure

- [ ] Create blueprint file in `src/admin/blueprints/`
- [ ] Import necessary dependencies
- [ ] Define blueprint with appropriate name and url_prefix
- [ ] Copy route functions from main app

### 2. Update Route Decorators

- [ ] Change `@app.route` to `@blueprint_name.route`
- [ ] Adjust route paths if using url_prefix
- [ ] Ensure all HTTP methods are specified correctly

### 3. Fix Imports and Dependencies

- [ ] Import models and utilities correctly
- [ ] Update `from admin_ui import X` to proper imports
- [ ] Ensure database session handling uses `get_db_session()`
- [ ] Import Flask utilities (`flash`, `redirect`, `url_for`, etc.)

### 4. Register Blueprint

- [ ] Import blueprint in main app
- [ ] Register with `app.register_blueprint()`
- [ ] Set correct `name` parameter if overriding default
- [ ] Verify url_prefix is set correctly

### 5. Update ALL Templates

**This is the most critical step to prevent runtime errors!**

#### Form Actions
- [ ] Update form `action="{{ url_for('old_route') }}"` to `action="{{ url_for('blueprint.route') }}"`
- [ ] Check both GET and POST forms
- [ ] Verify forms that submit via JavaScript

#### Navigation Links
- [ ] Update `href="{{ url_for('old_route') }}"` to `href="{{ url_for('blueprint.route') }}"`
- [ ] Check header navigation
- [ ] Check footer links
- [ ] Check breadcrumbs
- [ ] Check "Back" buttons

#### JavaScript/AJAX URLs
- [ ] Update `fetch('{{ url_for("old_route") }}')`
- [ ] Update `$.ajax({ url: '{{ url_for("old_route") }}' })`
- [ ] Check inline JavaScript in templates
- [ ] Check separate JS files that use template variables

#### Redirect URLs
- [ ] Update `redirect(url_for('old_route'))` in Python code
- [ ] Update `window.location.href = '{{ url_for("old_route") }}'` in JavaScript

### 6. Update Python Code

- [ ] Update all `url_for()` calls in route handlers
- [ ] Update redirects in error handlers
- [ ] Update test files that reference routes
- [ ] Update any utility functions that generate URLs

### 7. Session and Authentication

- [ ] Ensure session keys are consistent
  - `session["role"]` vs `session["is_super_admin"]`
  - `session["user"]` vs `session["email"]`
  - `session["authenticated"]` is set
- [ ] Update decorators if moved to blueprint
- [ ] Verify authentication checks still work

## Testing Checklist

### Automated Tests

- [ ] Run template validation test:
  ```bash
  uv run pytest tests/integration/test_template_url_validation.py -v
  ```

- [ ] Run template rendering tests:
  ```bash
  uv run pytest tests/integration/test_template_rendering.py -v
  ```

- [ ] Run all integration tests:
  ```bash
  uv run pytest tests/integration/ -v
  ```

- [ ] Run pre-commit hooks:
  ```bash
  pre-commit run --all-files
  ```

### Manual Testing

- [ ] Test each migrated route directly
- [ ] Test form submissions
- [ ] Test navigation from/to migrated pages
- [ ] Test with different user roles (super admin, tenant admin, viewer)
- [ ] Test error cases (404, 403, 500)
- [ ] Check browser console for JavaScript errors
- [ ] Verify redirects work correctly

## Common Issues and Solutions

### Issue: "BuildError: Could not build url for endpoint 'X'"

**Cause**: Template has `url_for('X')` but route name changed or needs blueprint prefix

**Solution**:
1. Find the correct endpoint name (usually `blueprint.route_name`)
2. Update all templates with the new name
3. Run template validation test to confirm

### Issue: "Method Not Allowed"

**Cause**: Form submits to wrong endpoint or endpoint doesn't accept POST

**Solution**:
1. Check form action URL
2. Verify route accepts POST method: `@route(..., methods=['GET', 'POST'])`
3. Ensure form action matches route that handles POST

### Issue: Session/Authentication Issues

**Cause**: Session keys inconsistent between old and new code

**Solution**:
1. Standardize session keys across all blueprints
2. Set all required keys: `role`, `authenticated`, `email`, etc.
3. Update templates that check session variables

### Issue: Circular Import Errors

**Cause**: Blueprint imports from main app which imports blueprint

**Solution**:
1. Move shared utilities to separate modules
2. Use late imports inside functions if necessary
3. Restructure imports to avoid cycles

## Post-Migration Cleanup

- [ ] Remove old routes from main app
- [ ] Delete commented-out code
- [ ] Update documentation
- [ ] Run full test suite
- [ ] Deploy to staging and test
- [ ] Monitor error logs after deployment

## Validation Commands Summary

```bash
# Quick validation
uv run pytest tests/integration/test_template_url_validation.py::TestTemplateUrlValidation::test_all_template_url_for_calls_resolve

# Full template tests
uv run pytest tests/integration/test_template_rendering.py tests/integration/test_template_url_validation.py -v

# Pre-commit validation
pre-commit run template-url-validation --all-files

# Check specific template
grep -n "url_for" templates/your_template.html

# Find all url_for calls that might need updating
grep -r "url_for(['\"]old_route_name['\"]" templates/
```

## Prevention Tips

1. **Always run template validation** after route changes
2. **Use consistent naming** for routes and blueprints
3. **Document endpoint names** in route docstrings
4. **Test incrementally** - migrate one blueprint at a time
5. **Keep templates simple** - avoid complex url_for logic
6. **Use the pre-commit hook** to catch issues before commit

Remember: Template errors often don't show up until runtime in production. The comprehensive test suite we've built will catch these issues early!
