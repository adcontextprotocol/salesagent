"""Grading for the BR-RULE-029 retry backoff schedule.

BR-RULE-029 INV-3 says a retried delivery backs off "1s, 2s, 4s + jitter". Two
suites need to grade that same sentence — the UC-004 BDD steps and the webhook
integration tests — so the schedule lives here once. Encoding it twice is how
one copy drifts into grading a ratio while the other grades magnitudes.

Magnitudes, not ratios: a ratio check ("each delay is >= 1.5x the last") passes
for any geometric schedule, so 0.1s/0.2s/0.4s satisfies it while breaking the
invariant. The delays themselves are the contract.

The jitter source is pinned in some environments and absent in others, so the
caller states which it has via ``jitter``; see the argument docs below.
"""

from __future__ import annotations

# BR-RULE-029 INV-3: the base schedule, before jitter.
BR_RULE_029_BASE_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)

# Production draws jitter from uniform(0, 1), so an unpinned delay may exceed its
# base by up to (but not including) one second.
JITTER_WINDOW_SECONDS = 1.0

# Float comparison tolerance for a pinned jitter offset.
_TOLERANCE = 1e-6


def assert_backoff_schedule(durations: list[float], *, jitter: float | None) -> None:
    """Assert observed sleep durations match BR-RULE-029's 1s/2s/4s (+ jitter).

    Args:
        durations: the sleep durations actually observed, in order. A short run
            (2 sleeps for 3 attempts) is graded against the matching prefix of
            the schedule, not padded or excused.
        jitter: how the caller's environment treats the jitter draw.

            * ``float`` — the jitter source is pinned to this value (a test env
              patching ``random.uniform``), so each delay must equal its base
              plus exactly that offset. Grading a window here would let a
              magnitude regression hide inside the jitter slack.
            * ``None`` — the jitter draw is live or absent. Each delay must fall
              in ``[base, base + 1)`` AND at least one must differ from its base,
              which is what proves randomisation is actually applied.

    Raises:
        AssertionError: if a delay does not match its attempt's expected value,
            if more delays were observed than the schedule defines, or if
            ``jitter is None`` and every delay is exactly its base.
    """
    assert durations, "Expected at least one backoff sleep, got none"
    assert len(durations) <= len(BR_RULE_029_BASE_DELAYS), (
        f"Observed {len(durations)} backoff sleeps but BR-RULE-029 defines only "
        f"{len(BR_RULE_029_BASE_DELAYS)} ({list(BR_RULE_029_BASE_DELAYS)}): {_fmt(durations)}"
    )

    expected_bases = BR_RULE_029_BASE_DELAYS[: len(durations)]

    if jitter is None:
        for attempt, (actual, base) in enumerate(zip(durations, expected_bases, strict=True)):
            assert base <= actual < base + JITTER_WINDOW_SECONDS, (
                f"Backoff sleep {attempt + 1} was {actual:.3f}s, outside BR-RULE-029's "
                f"[{base:.1f}s, {base + JITTER_WINDOW_SECONDS:.1f}s) window for that attempt. "
                f"Full schedule: {_fmt(durations)}, expected bases {list(expected_bases)}"
            )
        assert any(actual != base for actual, base in zip(durations, expected_bases, strict=True)), (
            f"Backoff sleeps {_fmt(durations)} are the exact base delays {list(expected_bases)} — "
            "no jitter. BR-RULE-029 requires randomisation so retries do not thunder."
        )
        return

    for attempt, (actual, base) in enumerate(zip(durations, expected_bases, strict=True)):
        expected = base + jitter
        assert abs(actual - expected) < _TOLERANCE, (
            f"Backoff sleep {attempt + 1} was {actual:.3f}s, expected {expected:.3f}s "
            f"(BR-RULE-029 base {base:.1f}s + pinned jitter {jitter:.3f}s). "
            f"Full schedule: {_fmt(durations)}, expected bases {list(expected_bases)}"
        )


def _fmt(durations: list[float]) -> list[str]:
    return [f"{d:.3f}" for d in durations]
