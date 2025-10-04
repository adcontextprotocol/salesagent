#!/usr/bin/env python3
"""
Analyze test coverage for A2A skills and detect over-mocking anti-patterns.

This script performs three checks:
1. Coverage: Which AdCP skills have A2A tests?
2. Over-mocking: Are integration tests mocking internal handlers?
3. Spec compliance: Are tests using spec-compliant parameter names?
"""

import re
import sys
from pathlib import Path


class TestCoverageAnalyzer:
    """Analyze test coverage and detect anti-patterns."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.a2a_server_file = project_root / "src/a2a_server/adcp_a2a_server.py"
        self.test_file = project_root / "tests/integration/test_a2a_skill_invocation.py"

    def get_implemented_skills(self) -> set[str]:
        """Extract all implemented A2A skill handlers."""
        if not self.a2a_server_file.exists():
            return set()

        content = self.a2a_server_file.read_text()
        pattern = r"async def _handle_(\w+)_skill\("
        matches = re.findall(pattern, content)

        # Filter out 'explicit' which is not a skill name
        return {match for match in matches if match != "explicit"}

    def get_tested_skills(self) -> set[str]:
        """Extract all skills that have explicit A2A tests."""
        if not self.test_file.exists():
            return set()

        content = self.test_file.read_text()
        # Look for test function names that contain skill names
        pattern = r"def test_.*?(\w+)_skill.*?\("
        matches = re.findall(pattern, content)

        skills = set()
        for match in matches:
            # Clean up test name to extract skill
            if match in ["get_products", "create_media_buy", "get_signals"]:
                skills.add(match)

        return skills

    def find_over_mocking_violations(self) -> list[tuple[int, str]]:
        """Find instances of over-mocking internal handlers in integration tests."""
        if not self.test_file.exists():
            return []

        violations = []
        content = self.test_file.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, start=1):
            # Check for mocking internal handler functions
            if 'patch.object(handler, "_handle_' in line:
                violations.append((i, line.strip()))

        return violations

    def find_spec_compliance_issues(self) -> list[tuple[str, str]]:
        """Check for non-spec-compliant parameter names in tests."""
        issues = []

        if not self.test_file.exists():
            return issues

        content = self.test_file.read_text()

        # Check for singular media_buy_id instead of plural media_buy_ids
        if '"media_buy_id":' in content and "get_media_buy_delivery" in content:
            issues.append(
                (
                    "get_media_buy_delivery",
                    "Test may use singular 'media_buy_id' instead of spec-compliant 'media_buy_ids'",
                )
            )

        return issues

    def analyze(self) -> dict:
        """Run complete analysis."""
        implemented = self.get_implemented_skills()
        tested = self.get_tested_skills()
        untested = implemented - tested
        over_mocking = self.find_over_mocking_violations()
        spec_issues = self.find_spec_compliance_issues()

        return {
            "implemented_skills": sorted(implemented),
            "tested_skills": sorted(tested),
            "untested_skills": sorted(untested),
            "over_mocking_violations": over_mocking,
            "spec_compliance_issues": spec_issues,
            "coverage_percentage": (len(tested) / len(implemented) * 100) if implemented else 0,
        }

    def print_report(self, results: dict):
        """Print formatted analysis report."""
        print("=" * 80)
        print("A2A TEST COVERAGE ANALYSIS")
        print("=" * 80)
        print()

        # Coverage Summary
        print("📊 COVERAGE SUMMARY")
        print("-" * 80)
        implemented_count = len(results["implemented_skills"])
        tested_count = len(results["tested_skills"])
        print(f"   Implemented skills: {implemented_count}")
        print(f"   Tested skills:      {tested_count}")
        print(f"   Coverage:           {results['coverage_percentage']:.1f}%")
        print()

        # Untested Skills
        if results["untested_skills"]:
            print(f"❌ UNTESTED SKILLS ({len(results['untested_skills'])})")
            print("-" * 80)
            for skill in results["untested_skills"]:
                print(f"   • {skill}")
            print()

        # Over-Mocking Violations
        if results["over_mocking_violations"]:
            print(f"⚠️  OVER-MOCKING VIOLATIONS ({len(results['over_mocking_violations'])})")
            print("-" * 80)
            print("   Integration tests should NOT mock internal handler functions.")
            print("   Mock only external dependencies (database, adapters, HTTP).")
            print()
            for line_num, code in results["over_mocking_violations"]:
                print(f"   Line {line_num}: {code[:70]}...")
            print()

        # Spec Compliance Issues
        if results["spec_compliance_issues"]:
            print(f"⚠️  SPEC COMPLIANCE ISSUES ({len(results['spec_compliance_issues'])})")
            print("-" * 80)
            for skill, issue in results["spec_compliance_issues"]:
                print(f"   • {skill}: {issue}")
            print()

        # Summary Status
        print("=" * 80)
        if (
            not results["untested_skills"]
            and not results["over_mocking_violations"]
            and not results["spec_compliance_issues"]
        ):
            print("✅ ALL CHECKS PASSED")
        else:
            print("❌ ISSUES FOUND - See details above")
        print("=" * 80)

        return len(results["untested_skills"]) + len(results["over_mocking_violations"])


def main():
    """Run analysis and return exit code."""
    project_root = Path(__file__).parent.parent

    analyzer = TestCoverageAnalyzer(project_root)
    results = analyzer.analyze()
    issues_count = analyzer.print_report(results)

    # Exit with error if issues found (useful for CI)
    if "--strict" in sys.argv and issues_count > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
