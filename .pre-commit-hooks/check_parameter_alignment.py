#!/usr/bin/env python3
"""Check if MCP wrappers and A2A raw functions match their _impl signatures.

This hook prevents signature mismatches like the one in PR #350 where
sync_creatives MCP wrapper passed webhook_url but _impl expected push_notification_config.

Exit codes:
    0: All signatures aligned
    1: Found signature mismatches
"""
import ast
import sys
from pathlib import Path


def extract_function_params(file_path, func_name):
    """Extract parameter names from a function."""
    try:
        with open(file_path) as f:
            tree = ast.parse(f.read())
    except Exception as e:
        print(f"❌ Failed to parse {file_path}: {e}")
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            params = []
            for arg in node.args.args:
                params.append(arg.arg)
            return set(params)
    return None


# Define tools to check (tools using shared implementation pattern)
tools = [
    {
        "name": "sync_creatives",
        "impl": "_sync_creatives_impl",
        "mcp_wrapper": "sync_creatives",
        "a2a_raw": "sync_creatives_raw",
    },
    {
        "name": "create_media_buy",
        "impl": "_create_media_buy_impl",
        "mcp_wrapper": "create_media_buy",
        "a2a_raw": "create_media_buy_raw",
    },
    {
        "name": "update_media_buy",
        "impl": "_update_media_buy_impl",
        "mcp_wrapper": "update_media_buy",
        "a2a_raw": "update_media_buy_raw",
    },
    {
        "name": "get_media_buy_delivery",
        "impl": "_get_media_buy_delivery_impl",
        "mcp_wrapper": "get_media_buy_delivery",
        "a2a_raw": "get_media_buy_delivery_raw",
    },
    {
        "name": "update_performance_index",
        "impl": "_update_performance_index_impl",
        "mcp_wrapper": "update_performance_index",
        "a2a_raw": "update_performance_index_raw",
    },
    {
        "name": "list_creatives",
        "impl": "_list_creatives_impl",
        "mcp_wrapper": "list_creatives",
        "a2a_raw": "list_creatives_raw",
    },
    {
        "name": "list_creative_formats",
        "impl": "_list_creative_formats_impl",
        "mcp_wrapper": "list_creative_formats",
        "a2a_raw": "list_creative_formats_raw",
    },
    {
        "name": "list_authorized_properties",
        "impl": "_list_authorized_properties_impl",
        "mcp_wrapper": "list_authorized_properties",
        "a2a_raw": "list_authorized_properties_raw",
    },
]

# File paths
main_py = Path("src/core/main.py")
tools_py = Path("src/core/tools.py")

# Legacy parameters that are allowed in MCP wrappers for backwards compatibility
# These parameters should be converted to the canonical form before calling _impl
LEGACY_PARAMS = {"webhook_url"}

# Canonical parameters that can be replaced by legacy equivalents
# Format: {canonical_param: legacy_param}
LEGACY_CONVERSIONS = {"push_notification_config": "webhook_url"}

issues_found = []

for tool in tools:
    impl_params = extract_function_params(main_py, tool["impl"])
    mcp_params = extract_function_params(main_py, tool["mcp_wrapper"])
    raw_params = extract_function_params(tools_py, tool["a2a_raw"])

    if not impl_params:
        print(f"❌ Could not find {tool['impl']} in {main_py}")
        continue
    if not mcp_params:
        print(f"❌ Could not find {tool['mcp_wrapper']} in {main_py}")
        continue
    if not raw_params:
        print(f"❌ Could not find {tool['a2a_raw']} in {tools_py}")
        continue

    # Check MCP wrapper alignment (allow legacy params)
    # Allow legacy parameters if they convert to canonical form
    mcp_params_canonical = mcp_params.copy()

    # Handle legacy parameter conversions:
    # 1. If wrapper has BOTH canonical and legacy, remove legacy for comparison
    # 2. If wrapper has ONLY legacy (not canonical), replace with canonical
    for canonical, legacy in LEGACY_CONVERSIONS.items():
        if legacy in mcp_params_canonical:
            if canonical in mcp_params_canonical:
                # Both present - remove legacy (it's extra for backwards compat)
                mcp_params_canonical.remove(legacy)
            else:
                # Only legacy present - replace with canonical
                mcp_params_canonical.remove(legacy)
                mcp_params_canonical.add(canonical)

    if impl_params != mcp_params_canonical:
        mismatch = {
            "tool": tool["name"],
            "type": "MCP wrapper",
            "missing_in_wrapper": impl_params - mcp_params_canonical,
            "extra_in_wrapper": mcp_params_canonical - impl_params,
        }
        issues_found.append(mismatch)

    # Check A2A raw alignment (must match exactly)
    if impl_params != raw_params:
        mismatch = {
            "tool": tool["name"],
            "type": "A2A raw",
            "missing_in_raw": impl_params - raw_params,
            "extra_in_raw": raw_params - impl_params,
        }
        issues_found.append(mismatch)

if not issues_found:
    sys.exit(0)
else:
    print("\n❌ Found parameter signature mismatches:\n")
    for issue in issues_found:
        print(f"  {issue['tool']} - {issue['type']}:")
        if issue.get("missing_in_wrapper") or issue.get("missing_in_raw"):
            missing = issue.get("missing_in_wrapper") or issue.get("missing_in_raw")
            print(f"    Missing: {sorted(missing)}")
        if issue.get("extra_in_wrapper") or issue.get("extra_in_raw"):
            extra = issue.get("extra_in_wrapper") or issue.get("extra_in_raw")
            print(f"    Extra: {sorted(extra)}")
        print()

    print("💡 Tip: MCP wrappers and A2A raw functions must match their _impl signature.")
    print("   Legacy parameters like 'webhook_url' are allowed in MCP wrappers but must be converted.")
    print("   See docs/postmortems/2025-01-12-sync-creatives-parameter-mismatch.md for details.")
    sys.exit(1)
