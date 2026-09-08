# GAM testing setup

How to configure and run the manual test scripts that exercise the Google Ad Manager (GAM) adapter against a real GAM network.

**Critical safety principle**: Never test against production ad units or networks. Every resource these scripts touch must belong to a dedicated test network.

These scripts complement, not replace, the automated suites: unit and integration tests mock GAM, and the Docker-based stack described in [E2E testing](../../development/e2e-testing.md) uses the mock adapter. The scripts here are the only ones that make real GAM API calls, so they live in `tests/manual/` and run only when you invoke them explicitly.

## The manual test scripts

- `tests/manual/test_gam_supported_only.py` — exercises the targeting features the adapter supports (and verifies that unsupported ones fail explicitly). Reads its test resources from `.gam-test-config.json`.
- `tests/manual/test_gam_automation_real.py` — exercises order creation and lifecycle management. Takes its test resources as command-line arguments and environment variables.

Both create real objects in the GAM network you point them at.

## Test configuration file

### Location

`.gam-test-config.json` in the repository root.

### Purpose

The file names the designated test-only GAM resources for `test_gam_supported_only.py`, so test runs never depend on discovering resources from a live network — and never touch anything you did not explicitly designate.

### Structure

The script reads the following keys:

```json
{
  "comment": "Safe GAM test configuration - these are designated TEST ad units only",
  "environment": "TEST",
  "test_network": {
    "network_code": "23312659540",
    "display_name": "Example Publisher - TEST ENVIRONMENT"
  },
  "test_ad_units": {
    "root_ad_unit_id": "23312403859"
  },
  "test_advertisers": {
    "primary_test_advertiser": "5879976174"
  },
  "test_users": {
    "trafficker_id": "245414678"
  },
  "credentials": {
    "refresh_token": "your-test-oauth-refresh-token"
  }
}
```

The script targets the configured `root_ad_unit_id` and authenticates with the configured `refresh_token`. Descriptive fields such as `comment`, `display_name`, and `environment` document the file for humans; the script does not validate them, so the safety of the configuration rests on you designating test-only resources.

### Create the configuration

1. **Verify the test network**: Ensure the GAM network is designated for testing only.
2. **Document the test resources**: List the test-only ad units, advertisers, and users.
3. **Create the file**: Use the structure shown earlier, with your test network's IDs.
4. **Use test-only credentials**: The refresh token must belong to a user on the test network, never a production account.

### File management

The `.gitignore` excludes test configuration files from git:

```text
# Test configurations (contain test network IDs - should not be in production)
.gam-test-config.json
gam_ad_units.json
```

Each developer maintains their own test configuration. This prevents accidental commits of test network IDs and credentials.

## Lifecycle tests

`test_gam_automation_real.py` covers order lifecycle management:

```bash
python tests/manual/test_gam_automation_real.py \
  --network-code YOUR_TEST_NETWORK_CODE \
  --advertiser-id YOUR_TEST_ADVERTISER_ID \
  --trafficker-id YOUR_TEST_TRAFFICKER_ID \
  --refresh-token YOUR_TEST_REFRESH_TOKEN
```

You can supply the refresh token through the `GAM_TEST_REFRESH_TOKEN` environment variable instead of `--refresh-token`.

The lifecycle tests:

1. `test_lifecycle_activate_order` — activation of non-guaranteed orders.
2. `test_lifecycle_submit_for_approval` — submitting guaranteed orders for approval.
3. `test_lifecycle_activation_blocking` — guaranteed orders route activation through a workflow instead of activating directly.
4. `test_lifecycle_archive_order` — archival of orders.

Each test creates a real order through `GoogleAdManager.create_media_buy()` and then drives it through `update_media_buy()` lifecycle actions.

### Safety features

- **Automatic cleanup**: The script archives the orders it created and removes its test products after the run.
- **Small budgets**: Test orders use minimal budgets ($1-$20).
- **Short durations**: Test campaigns have flight dates of about one day.
- **Manual fallback**: If automatic cleanup fails, the output identifies the created orders so you can archive them by hand.

### Expected results

- Non-guaranteed activation succeeds.
- Guaranteed orders do not activate directly — activation creates an approval workflow step, which the blocking test verifies.
- Approval submission succeeds for guaranteed orders.
- Archival works for the orders the run created.

## Best practices

1. **Always verify**: Before writing the test configuration, manually confirm in GAM that every resource is test-only.
2. **Document purpose**: Keep the descriptive fields filled in so the next reader knows why each resource is safe.
3. **Validate regularly**: Periodically confirm the test resources haven't changed purpose.
4. **Communicate**: Ensure everyone on the team understands the test-versus-production distinction.
5. **Separate credentials**: Use test-only OAuth credentials, never production credentials. See [GAM service account authentication](service-account-setup.md) for how production credentials are managed.

## Related documentation

- [GAM adapter overview](README.md) — supported features
- [GAM product configuration](product-configuration.md) — the `implementation_config` these tests exercise
- [E2E testing](../../development/e2e-testing.md) — the automated, mock-adapter test stack
