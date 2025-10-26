#!/usr/bin/env python3
"""
Check that all advertised A2A skills have integration tests.

Compares:
- Skills advertised in agent card (from src/a2a_server/adcp_a2a_server.py)
- Test methods in tests/integration_v2/test_a2a_skill_invocation.py

Exit codes:
- 0: 100% skill coverage
- 1: Missing tests for some skills
"""

import re
import sys
from pathlib import Path


def get_advertised_skills() -> set[str]:
    """Extract skill names from agent card."""
    agent_file = Path("src/a2a_server/adcp_a2a_server.py")
    if not agent_file.exists():
        print(f"❌ Could not find {agent_file}")
        sys.exit(1)

    content = agent_file.read_text()

    # Find skills in create_agent_card function
    # Look for AgentSkill(name="...", ...) or AgentSkill(id="...", name="...", ...)
    skill_pattern = r'AgentSkill\s*\([^)]*name\s*=\s*["\']([^"\']+)["\']'
    skills = set(re.findall(skill_pattern, content))

    return skills


def get_tested_skills() -> set[str]:
    """Extract skill names that have test methods."""
    test_file = Path("tests/integration_v2/test_a2a_skill_invocation.py")
    if not test_file.exists():
        print(f"❌ Could not find {test_file}")
        sys.exit(1)

    content = test_file.read_text()

    # Find test methods that test specific skills
    # Pattern: def test_<something>_<skill_name>_skill or test_<skill_name>_skill
    test_pattern = r"def test_\w*?([a-z_]+)_skill\("
    raw_matches = re.findall(test_pattern, content)

    # Convert test names to skill names
    # E.g., "get_media_buy_delivery" stays as is
    # "explicit_get_products" becomes "get_products"
    skills = set()
    for match in raw_matches:
        # Remove common prefixes
        skill = match
        for prefix in [
            "explicit_",
            "natural_language_",
            "update_",
            "list_",
            "get_",
            "sync_",
            "approve_",
            "search_",
            "optimize_",
        ]:
            if match.startswith(prefix):
                # Keep the full name if it's a real skill
                skills.add(match)
                break
        else:
            skills.add(match)

    # Also check for skills in test data
    # Look for create_a2a_message_with_skill("skill_name", ...) or create_message_with_skill("skill_name", ...)
    skill_invocation_pattern = r'create_(?:a2a_)?message_with_skill\(\s*["\']([^"\']+)["\']'
    invoked_skills = set(re.findall(skill_invocation_pattern, content))
    skills.update(invoked_skills)

    return skills


def main():
    """Check A2A skill test coverage."""
    advertised = get_advertised_skills()
    tested = get_tested_skills()

    missing = advertised - tested
    extra = tested - advertised

    if not missing:
        print("✅ 100% A2A skill coverage")
        print(f"   {len(advertised)} skills advertised, all have tests")
        return 0

    print(f"❌ Missing tests for {len(missing)} skills:\n")
    for skill in sorted(missing):
        print(f"  • {skill}")

    if extra:
        print("\n⚠️  Tests for skills not in agent card:")
        for skill in sorted(extra):
            print(f"  • {skill}")

    print(f"\n📊 Coverage: {len(tested)}/{len(advertised)} skills tested")
    print(f"   ({100 * len(tested) / len(advertised):.1f}%)")

    return 1


if __name__ == "__main__":
    sys.exit(main())
