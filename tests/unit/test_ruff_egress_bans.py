"""Executable-exemption meta-test for the egress import bans.

The egress import bans live in a SECOND ruff config (``ruff-egress.toml`` at
the repo root, run as its own ``make quality`` line:
``uv run ruff check --config ruff-egress.toml --no-respect-gitignore
src/ scripts/``). They replace the deleted
AST scans #1 (raw network libs) and #2 (SDK/MCP client constructors) of the
old ``test_architecture_no_raw_egress.py`` — see GH #1589 and CLAUDE.md
pattern #9: all outbound HTTP goes through ``src/core/security/outbound_http.py``.

This module is the ban table's non-vacuity proof, replacing the deleted
guards' meta-tests. Four cases:

(a) POSITIVE  — every banned entry fires (TID251 in ruff's OUTPUT, not just
    exit status) for every resolving spelling: direct import, aliased import,
    dotted-attribute use, and the bypass re-export paths
    (``fastmcp.client`` / ``fastmcp.client.transports.http`` /
    ``adcp.client``) that a single-path ban would let through.
(b) NEGATIVE  — a clean snippet yields no TID251 (and the config loads).
(c) NON-VACUITY per exemption — every recorded marker line is a real violation
    site, and no file carries a suppression the record does not know about.
(d) CLOSED SET — the set of files with a violation absent all suppressions
    equals the recorded constant; a new exemption fails until recorded here.


Cases (c) and (d) do NOT parse suppressions themselves. They ask ruff, via
``--ignore-noqa``, what the violation set V is absent ALL suppressions, and
compare V against the recorded constants. This is the whole point: a regex
that mirrors ruff's noqa syntax mirrors it INCOMPLETELY — ``# ruff: noqa``,
bare ``# noqa``, ``# noqa:TID251`` with no space, and ``# flake8: noqa`` all
evaded the previous form (GH #1802 round-3 finding 2a). V is spelling-blind by
construction, because ruff computes it.

``--ignore-noqa`` suppresses only *inline* suppressions; it does NOT bypass
``[lint.per-file-ignores]``, so the ANN401 negated-glob scoping in the config
still holds (verified).


Every case shells out to the real ruff with the real config — the exemptions
are executable, never prose (Core Invariant of GH #1589).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.unit._architecture_helpers import repo_root

# Repo-root-relative path of the src-scoped egress ban config.
EGRESS_CONFIG = "ruff-egress.toml"

# Path a synthetic snippet is presented under (inside the scanned tree —
# tests/ is deliberately out of scope; tests import httpx/requests freely).
_SYNTHETIC_PATH = "src/core/_synthetic_egress_probe.py"

# The same probe under scripts/, proving the bans are not path-scoped: they apply
# wherever the gate points, and the gate points at src/ AND scripts/.
_SYNTHETIC_SCRIPTS_PATH = "scripts/_synthetic_egress_probe.py"


# passing it straight to send() type-checks clean under mypy.


# Module-level bans: the bare import fires, so verb enumeration is moot.
_MODULE_BANS: tuple[str, ...] = (
    "httpx",
    "requests",
    "aiohttp",
    "urllib.request",
    "ipaddress",
    # The HTTP stacks under and beside httpx/requests. httpx2 is ONE CHARACTER
    # from the banned spelling, and both httpx2 and httpcore2 are installed
    # transitively (via genai-prices) and importable (GH #1802 round-3 F1).
    "httpcore",
    "urllib3",
    "http.client",
    "httpx2",
    "httpcore2",
)

# Symbol bans: every resolving import path per symbol. The non-first entries
# are the bypass re-export spellings a single-path ban would miss
# (fastmcp.client re-exports the transports; adcp.client is the classes'
# real defining module).
_SYMBOL_BAN_PATHS: dict[str, tuple[str, ...]] = {
    "StreamableHttpTransport": (
        "fastmcp.client.transports",
        "fastmcp.client",
        "fastmcp.client.transports.http",
    ),
    "SSETransport": (
        "fastmcp.client.transports",
        "fastmcp.client",
        "fastmcp.client.transports.sse",
    ),
    "ADCPClient": ("adcp", "adcp.client"),
    "ADCPMultiAgentClient": ("adcp", "adcp.client"),
    "get_adcp_signed_headers_for_webhook": ("adcp.webhooks", "adcp"),
    # Resolve-then-check is a TOCTOU the egress package does not use (adcp.signing
    # pins the resolved IP in one step) — one path, no bypass re-export exists.
    "gethostbyname": ("socket",),
    # `Client(url)` INFERS an un-pinned StreamableHttpTransport from a bare URL
    # (verified at runtime): banning the transports without banning the
    # constructor that manufactures one leaves the hole open. The MCP seam is
    # the sanctioned importer and passes transport= only. The seam's own module
    # is the fourth path because importing FROM the seam re-exports the name.
    "Client": ("fastmcp", "fastmcp.client", "fastmcp.client.client"),
}


def _run_ruff_egress(source: str, stdin_filename: str) -> subprocess.CompletedProcess[str]:
    """Run ruff over *source* as *stdin_filename* with the egress ban config.

    The single helper every case goes through (DRY): same interpreter
    (``sys.executable -m ruff``), same config, same output format — so a
    passing case proves the REAL gate line would fire, not a lookalike.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            EGRESS_CONFIG,
            "--stdin-filename",
            stdin_filename,
            "--output-format",
            "concise",
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=False,
    )


def _assert_rule_fires(source: str, stdin_filename: str, label: str, code: str) -> None:
    """One assertion for every rule this config carries — see _assert_tid251_fires."""
    proc = _run_ruff_egress(source, stdin_filename)
    assert code in proc.stdout, (
        f"[{label}] expected a {code} violation from ruff for:\n{source}\n"
        f"--- ruff stdout ---\n{proc.stdout}\n--- ruff stderr ---\n{proc.stderr}"
    )


def _assert_tid251_fires(source: str, stdin_filename: str, label: str) -> None:
    _assert_rule_fires(source, stdin_filename, label, "TID251")


def _module_ban_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for module in _MODULE_BANS:
        alias = "_" + module.replace(".", "_")
        cases.append((f"{module}::direct-import", f"import {module}\n"))
        cases.append((f"{module}::aliased-import", f"import {module} as {alias}\n"))
        cases.append((f"{module}::from-import", f"from {module} import get\n"))
    return cases


def _symbol_ban_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for symbol, import_paths in _SYMBOL_BAN_PATHS.items():
        for path in import_paths:
            cases.append((f"{symbol}::from-{path}", f"from {path} import {symbol}\n"))
        canonical = import_paths[0]
        cases.append((f"{symbol}::aliased-import", f"from {canonical} import {symbol} as _aliased\n"))
        cases.append(
            (
                f"{symbol}::dotted-attribute",
                f"import {canonical} as _mod\n_mod.{symbol}('https://example.com')\n",
            )
        )
    return cases


_POSITIVE_CASES: list[tuple[str, str]] = _module_ban_cases() + _symbol_ban_cases()


class TestEgressBansFire:
    """(a) Every banned entry yields TID251, in every resolving spelling."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        _POSITIVE_CASES,
        ids=[label for label, _ in _POSITIVE_CASES],
    )
    def test_banned_spelling_yields_tid251(self, label: str, snippet: str) -> None:
        _assert_tid251_fires(snippet, _SYNTHETIC_PATH, label)

    def test_bans_are_not_path_scoped_to_src(self) -> None:
        """The same snippet fires under `scripts/`, which joined the scan set.

        banned-api entries are not path-scoped, so this is one probe, not one
        per entry. It pins the half of round-3 F2 that `_SCAN_DIRS` does not:
        the config applying wherever the gate points it.
        """
        _assert_tid251_fires("import requests\n", _SYNTHETIC_SCRIPTS_PATH, "scripts-scope")


class TestCleanCodePasses:
    """(b) The seam's own public surface is not flagged — and the config loads."""

    def test_clean_snippet_yields_no_tid251(self) -> None:
        clean = "from src.core.security.outbound_http import asend\n"
        proc = _run_ruff_egress(clean, _SYNTHETIC_PATH)
        # returncode == 0 also proves the config parsed — a missing/broken
        # ruff-egress.toml must fail HERE, not pass vacuously via empty output.
        assert proc.returncode == 0, (
            f"ruff did not run cleanly (config missing/broken?):\n"
            f"--- ruff stdout ---\n{proc.stdout}\n--- ruff stderr ---\n{proc.stderr}"
        )
        assert "TID251" not in proc.stdout, f"clean snippet was flagged:\n{proc.stdout}"
