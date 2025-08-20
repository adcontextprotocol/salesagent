# Blueprint Migration Plan

## Summary
- **Total routes in admin_ui.py**: ~80 routes
- **Already migrated**: 8 routes (auth, health, index, some tenant routes)
- **Remaining**: ~72 routes
- **Target**: Systematically migrate all routes to blueprints

## Migration Phases

### Phase 1: Core Admin Routes (COMPLETED) ✅
- [x] Authentication routes (`/login`, `/logout`, `/auth/*`)
- [x] Health check routes (`/health`, `/api/health`)
- [x] Index route (`/`)
- [x] Basic tenant dashboard (`/tenant/<tenant_id>`)

### Phase 2: Product Management Routes (IN PROGRESS)
Priority: HIGH - These are frequently used
- [ ] `/tenant/<tenant_id>/products` - List products
- [ ] `/tenant/<tenant_id>/product/new` - Create product
- [ ] `/tenant/<tenant_id>/product/<product_id>` - View/edit product
- [ ] `/tenant/<tenant_id>/product/<product_id>/delete` - Delete product
- [ ] `/tenant/<tenant_id>/products/bulk/*` - Bulk operations
- [ ] `/api/tenant/<tenant_id>/products/*` - Product APIs

### Phase 3: Principal/Advertiser Management Routes
Priority: HIGH - Core functionality
- [ ] `/tenant/<tenant_id>/principals` - List principals
- [ ] `/tenant/<tenant_id>/principal/new` - Create principal
- [ ] `/tenant/<tenant_id>/principal/<principal_id>` - View/edit principal
- [ ] `/tenant/<tenant_id>/principal/<principal_id>/delete` - Delete principal

### Phase 4: Creative Management Routes
Priority: MEDIUM
- [ ] `/tenant/<tenant_id>/creative-formats` - List formats
- [ ] `/tenant/<tenant_id>/creative-format/new` - Create format
- [ ] `/tenant/<tenant_id>/creative-format/<format_id>` - Edit format
- [ ] `/tenant/<tenant_id>/creatives/*` - Creative operations
- [ ] `/api/tenant/<tenant_id>/creatives/*` - Creative APIs

### Phase 5: GAM Integration Routes
Priority: MEDIUM - Adapter-specific
- [ ] `/tenant/<tenant_id>/gam/*` - GAM-specific routes
- [ ] `/api/tenant/<tenant_id>/gam/*` - GAM APIs
- [ ] `/tenant/<tenant_id>/inventory/*` - Inventory management
- [ ] `/api/gam/*` - GAM reporting APIs

### Phase 6: Operations & Monitoring Routes
Priority: LOW - Admin tools
- [ ] `/tenant/<tenant_id>/operations` - Operations dashboard
- [ ] `/tenant/<tenant_id>/media-buys` - Media buy management
- [ ] `/tenant/<tenant_id>/tasks` - Task management
- [ ] `/tenant/<tenant_id>/audit-logs` - Audit log viewer

### Phase 7: Settings & Configuration Routes
Priority: LOW
- [ ] `/settings` - Super admin settings (partially done)
- [ ] `/tenant/<tenant_id>/settings/*` - Tenant settings
- [ ] `/mcp-test` - MCP protocol test
- [ ] `/api/settings/*` - Settings APIs

### Phase 8: Utility Routes
Priority: LOWEST
- [ ] `/targeting-browser` - Targeting browser
- [ ] `/parsing-demo` - Creative parsing demo
- [ ] `/api/utils/*` - Utility APIs
- [ ] Static/asset routes

## Migration Strategy

### For Each Phase:
1. **Create Blueprint Module**
   - Create `src/admin/blueprints/{module}.py`
   - Import necessary dependencies
   - Define blueprint with appropriate URL prefix

2. **Move Routes**
   - Copy route functions from `admin_ui.py`
   - Update imports and dependencies
   - Fix decorator to use blueprint

3. **Update Templates**
   - Update all `url_for()` calls to use blueprint namespace
   - Test template rendering
   - Fix any broken links

4. **Add Tests**
   - Create test file in `src/admin/tests/`
   - Test route accessibility
   - Test business logic
   - Test template rendering

5. **Validate**
   - Run `test_template_url_validation.py`
   - Run `test_schema_field_validation.py`
   - Manual QA of affected pages

## Next Steps

1. Start with Phase 2 (Product Management) as it's high priority
2. Use the migration scripts in `scripts/` to automate parts of the process
3. Test thoroughly after each phase
4. Commit after each successful phase

## Success Criteria

- [ ] All routes migrated to blueprints
- [ ] All tests passing
- [ ] No template rendering errors
- [ ] No broken links
- [ ] Admin UI fully functional
- [ ] Clean separation of concerns
- [ ] Improved maintainability

## Notes

- Keep `admin_ui.py` functional during migration (gradual migration)
- Use feature flags if needed for complex migrations
- Document any breaking changes
- Update API documentation as needed
