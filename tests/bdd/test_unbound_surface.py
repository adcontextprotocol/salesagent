"""Bind every feature file that no other module binds, so nothing is invisible.

Twenty feature files carrying 1604 scenarios were loaded by no test module at
all. Not skipped, not xfailed — NOT COLLECTED. They did not appear in a run's
totals, so no count anyone read was aware of them, and a scenario in them could
be broken for a year without a single report saying so. That is the one failure
mode a suite cannot self-report, because the evidence of the gap is the absence
of evidence.

Binding them here makes the whole corpus visible. What happens next is decided by
the registry, not by this module:

- A scenario calling a tool that is not in ``TOOLS`` is SKIPPED, with a reason
  naming the tool (``tests/bdd/unregistered_tools.py``, applied in ``conftest``).
  Roughly 1391 of these scenarios are that: inventory for protocol surface this
  seller has not built. They cost a collection entry and report honestly.
- Everything else RUNS. Three of the twenty files — UC-001, UC-025 and UC-032 —
  call only registered tools, so their 213 scenarios execute for the first time.
  Whatever they do is new information; a failure there is a finding, not a
  regression, because nothing was passing before.

This module is deliberately a bare list of ``scenarios()`` calls with no step
definitions of its own. A scenario whose steps are unbound fails on the missing
step, which names exactly what is needed to wire it — a better signal than
silence, and the reason not to pre-emptively stub anything here.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/BR-UC-001-discover-available-inventory.feature")
scenarios("features/BR-UC-007-list-authorized-properties.feature")
scenarios("features/BR-UC-008-manage-audience-signals.feature")
scenarios("features/BR-UC-009-update-performance-index.feature")
scenarios("features/BR-UC-012-manage-content-standards.feature")
scenarios("features/BR-UC-013-manage-property-lists.feature")
scenarios("features/BR-UC-014-sponsored-intelligence-session.feature")
scenarios("features/BR-UC-015-track-conversions.feature")
scenarios("features/BR-UC-016-sync-audiences.feature")
scenarios("features/BR-UC-017-account-financials-usage.feature")
scenarios("features/BR-UC-020-build-creative.feature")
scenarios("features/BR-UC-021-preview-creative.feature")
scenarios("features/BR-UC-022-creative-delivery-features.feature")
scenarios("features/BR-UC-023-sync-product-catalogs.feature")
scenarios("features/BR-UC-024-content-compliance.feature")
scenarios("features/BR-UC-025-property-features-validation.feature")
scenarios("features/BR-UC-027-manage-async-tasks.feature")
scenarios("features/BR-UC-028-manage-collection-lists.feature")
scenarios("features/BR-UC-030-manage-governance-binding.feature")
scenarios("features/BR-UC-032-compliance-test-controller.feature")
