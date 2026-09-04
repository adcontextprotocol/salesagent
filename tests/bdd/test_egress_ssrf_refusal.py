"""BDD binding for the locally-added egress/SSRF refusal feature.

Covers the buyer-visible half of AdCP 3.1.1 L1 § "Webhook URL validation
(SSRF)" — a counterparty-supplied URL the egress seam refuses reaches the buyer
as VALIDATION_ERROR / correctable naming the field to fix, and discloses nothing
about our network. The conformance storyboard does not grade it, so there is no
BR-UC-* scenario to inherit; retire this file together with the local feature
once the upstream storyboard (adcp-req) grows the equivalent scenario.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-egress-ssrf-refusal.feature")
