"""Reserved-TLD policy for notification proof-of-control.

This module answers exactly ONE question: *can an endpoint under this hostname
ever be PROVEN?* It is RFC 9421 notification-proof policy, not address policy.

It is NOT an SSRF gate and must never grow back into one. Address, scheme, DNS
and IP-pinning policy live in ONE place -- the egress seam,
``src/core/security/egress/policy.py``:

* :meth:`~src.core.security.egress.policy.EgressPolicy.check_registration` --
  the DNS-free verdict a stored URL earns at registration (reached from ingest
  code through ``webhook_validator.WebhookURLValidator.
  validate_webhook_url_registration``, the sanctioned ``(bool, str)`` wrapper);
* :meth:`~src.core.security.egress.policy.EgressPolicy.resolve_for_dial` --
  the DNS-full, IP-pinning verdict a URL earns the moment it is dialled.

This module used to carry a fourth copy of that address policy
(``check_url_ssrf``, ``check_url_syntax``, ``BLOCKED_NETWORKS``,
``BLOCKED_HOSTNAMES``). GH #1802 consolidated all four into the seam, and they
are DELETED here. Do not re-add them: a second spelling of address policy is
precisely the defect #1802 exists to make structurally impossible. Anything
that needs "where does this URL land" asks the seam.

What stays is the half the seam never owned and deliberately does not want: the
seam has no reserved-TLD notion at all, and a ``.example`` or ``.invalid`` host
passes ``check_registration`` on its own terms. "Can this brand document ever
exist, can this endpoint ever be proven" is a different question from "where
does this dial land", so it keeps its own owner here.
"""

from __future__ import annotations

# RFC 2606 / RFC 6761 reserved TLDs. These are guaranteed never to resolve to a
# real host, so a URL under one can be judged unreachable WITHOUT a DNS lookup --
# which is what makes "this endpoint cannot be proven" deterministic instead of
# dependent on whether the local resolver happens to hijack NXDOMAIN.
#
# The six names AdCP 3.1.1 enumerates for this refusal, exhaustively:
# v3.1.1:docs/creative/canonical-formats.mdx:222 -- "RFC 6761 special-use names
# (`.local`, `.localhost`, `.internal`, `.test`, `.example`, `.invalid`)".
#
# This module OWNS the decision; it is not a shared constant callers re-match for
# themselves. Match through ``reserved_tld_for_host`` / ``is_reserved_tld_host``,
# never by iterating this set at a call site -- a call-site ``endswith`` skips the
# normalization those functions apply and silently accepts a host the owner
# refuses (the sync_accounts provisioning bug, GH #1291).
#
# Deliberately NOT folded into the egress seam: the normative webhook-SSRF section
# (building/by-layer/L1/security.mdx:104-119) is a reserved-IP-RANGE rule and does
# not carry this name list, and folding it into the general address gate would
# refuse the e2e stack's own ``adcp.test`` origins. Callers that need "can this
# endpoint ever be proven?" ask for it explicitly.
RESERVED_TLDS: frozenset[str] = frozenset({".test", ".invalid", ".example", ".localhost", ".local", ".internal"})


def reserved_tld_for_host(hostname: str) -> str | None:
    """Which RFC 2606/6761 reserved TLD *hostname* sits under, or None.

    The single matcher for this policy. Normalizes case and a trailing root dot,
    and matches a bare reserved LABEL (``"test"``) as well as a suffix
    (``"acme.test"``) -- all three are spellings a caller's plain ``endswith``
    misses. Returns WHICH tld matched so callers can name it in a refusal
    message without re-deriving it.
    """
    lowered = hostname.lower().rstrip(".")
    for tld in RESERVED_TLDS:
        if lowered == tld.lstrip(".") or lowered.endswith(tld):
            return tld
    return None


def is_reserved_tld_host(hostname: str) -> bool:
    """Whether *hostname* sits under an RFC 2606/6761 reserved TLD."""
    return reserved_tld_for_host(hostname) is not None
