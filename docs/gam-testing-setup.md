# GAM Testing Configuration Guide

## Overview

This document explains the safe testing configuration system for Google Ad Manager (GAM) automation tests.

**🚨 CRITICAL SAFETY PRINCIPLE**: Never test against production ad units or networks!

## Test Configuration File

### Location
```
.gam-test-config.json
```

### Purpose
- Defines **designated test-only** GAM resources
- Prevents accidental testing against production systems
- Provides validation and safety checks
- Separates test environment from production discovery

### Structure

```json
{
  "comment": "Safe GAM test configuration - these are designated TEST ad units only",
  "environment": "TEST",
  "test_network": {
    "network_code": "23312659540",
    "display_name": "Wonderstruck Productions LLC - TEST ENVIRONMENT",
    "description": "This is a dedicated test GAM network - safe for automation testing"
  },
  "test_ad_units": {
    "root_ad_unit_id": "23312403859",
    "description": "Root test ad unit - safe for automated testing",
    "validation": {
      "network_matches": "23312659540",
      "environment_verified": true,
      "safe_for_automation": true
    }
  },
  "test_advertisers": {
    "primary_test_advertiser": "5879976174",
    "description": "Designated test advertiser account"
  },
  "safety_checks": {
    "require_network_validation": true,
    "require_test_environment_flag": true,
    "prevent_production_access": true,
    "safe_for_automation": true
  },
  "last_validated": "2025-09-06",
  "validated_by": "manual_testing_setup"
}
```

## Safety Features

### 1. Environment Validation
- Only allows `"environment": "TEST"`
- Rejects any other environment designation

### 2. Network Code Validation
- Validates network code matches expected test network
- Prevents testing against wrong GAM account

### 3. Safety Flags
- `safe_for_automation: true` required for automated testing
- Multiple validation checkpoints

### 4. Fallback Protection
- If config invalid/missing, falls back to adapter dynamic fetching
- Never uses hardcoded production IDs as fallback

## Usage

### Creating Test Configuration

1. **Verify Test Network**: Ensure your GAM network is designated for testing only
2. **Document Test Resources**: List all test-only ad units and advertisers
3. **Create Configuration**: Use the structure above
4. **Validate Safety**: Run validation tests before automation

### Test Script Integration

The test script automatically:
- Loads `.gam-test-config.json`
- Validates all safety requirements
- Uses designated test resources only
- Falls back safely if config invalid

### Example Output

```bash
🧪 Using DESIGNATED TEST ad unit: 23312403859
🛡️ Test environment: Wonderstruck Productions LLC - TEST ENVIRONMENT
```

## File Management

### .gitignore Protection
Test configuration files are automatically excluded from git:
```
# Test configurations (contain test network IDs - should not be in production)
.gam-test-config.json
gam_ad_units.json
```

### Local Development
- Each developer maintains their own test config
- Prevents accidental commit of test credentials
- Ensures production safety

## Migration from Discovery

### ❌ Old Approach (DANGEROUS)
- Used `gam_ad_units.json` from production discovery
- Could accidentally test against live ad units
- No validation of test vs production environment

### ✅ New Approach (SAFE)
- Uses dedicated `.gam-test-config.json`
- Explicit test-only resource designation
- Multiple safety validation layers
- Graceful fallback to dynamic fetching

## Best Practices

1. **Always Verify**: Before creating test config, manually verify GAM resources are test-only
2. **Document Purpose**: Include clear descriptions of why each resource is safe for testing
3. **Regular Validation**: Periodically verify test resources haven't changed purpose
4. **Team Communication**: Ensure all team members understand test vs production distinction
5. **Separate Credentials**: Use test-only OAuth credentials, never production credentials

## Troubleshooting

### Config Validation Errors
```bash
❌ Error loading test configuration: Invalid environment: PRODUCTION - only TEST environment allowed
🚨 SAFETY: Using fallback - adapter will fetch root ad unit dynamically
```

**Solution**: Update config file to use `"environment": "TEST"` and designated test resources.

### Network Mismatch Errors
```bash
❌ Error loading test configuration: Network code mismatch: using 12345, test config expects 23312659540
```

**Solution**: Ensure test script network code matches test configuration network code.

### Missing Config File
```bash
❌ Error loading test configuration: [Errno 2] No such file or directory: '.gam-test-config.json'
🚨 SAFETY: Using fallback - adapter will fetch root ad unit dynamically
```

**Solution**: Create test configuration file using template above, or rely on dynamic fetching.
