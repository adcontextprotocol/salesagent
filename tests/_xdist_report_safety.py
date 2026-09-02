"""Keep an unserializable test report from silently voiding an xdist session.

The hole
--------
pytest hands a report to the xdist wire via
``_pytest/reports.py::_report_to_json``, which starts with::

    d = report.__dict__.copy()      # EVERY attribute, raw

and then sanitizes exactly three things: ``longrepr``, values that are
``os.PathLike``, and ``result``. Everything else any plugin has attached to the
report crosses the wire as-is. execnet's ``_Serializer._save`` dispatches on
``type(obj)`` with an EXACT match over
``NoneType bool bytes complex dict float frozenset int list long set str tuple
Channel`` -- a *subclass* of any of those is refused too -- and raises
``DumpError`` for anything else.

A ``DumpError`` on a worker kills the worker; the master then trips its own
assertion (``xdist/dsession.py:232``) or dies with "Unexpectedly no active
workers available". Either way the session ends **after** reporting only the
tests already collected back, and the summary line says zero failures. A
truncated run is indistinguishable from a green one.

The live instance
-----------------
``pytest-json-report`` -- which ``tox.ini`` passes on every suite -- attaches
``report._json_report_extra`` (its ``plugin.py:105``), whose ``['log']`` entry
holds ``dict(record.__dict__)`` for each captured log record
(``plugin.py:51``). That handler nulls ``msg``, ``args`` and ``exc_info``, but
``logging`` merges anything passed as ``extra={...}`` straight into
``record.__dict__``, so an ``extra`` payload reaches the wire untouched.

Production logs that way in ~75 places -- e.g.
``src/adapters/gam/utils/logging.py:386`` (``extra={"details": details}``) --
so a unit test with a mocked collaborator puts a ``MagicMock`` on the wire
without failing, without asserting anything unusual, and without any hint in
its own output. Measured on this branch, ``tests/unit/`` + ``tests/harness/``
with ``--json-report`` and a FIXED order (``-p no:randomly``):

    workers  collected  reported  lost  summary
      0        5846       5846      0   5810 passed, 0 failed
      4        5846       5430    416   5394 passed, 0 failed
      8        5846       5348    498   5312 passed, 0 failed
     14        5846       5271    575   5235 passed, 0 failed

This module closes the hole at the wire boundary rather than at the ~75 call
sites: the boundary is one place and cannot be regressed by new logging, and
the same hole is open to any future plugin attribute, not just this one.

An offender is REPLACED, never dropped, and always announced on stderr with
its report and key path -- the failure mode being fixed here is silence, so
trading a crash for a quiet mutation would miss the point.
"""

from __future__ import annotations

import sys
from typing import Any

# execnet's _Serializer._save does `self._dispatch[type(obj)]` -- an exact type
# match. Subclasses (an IntEnum, a str subclass, a dict subclass) are refused
# exactly like a mock is, so membership is tested with `type(x) is` semantics
# for atoms and normalised to the base type for containers.
_ATOM_TYPES: frozenset[type] = frozenset({type(None), bool, bytes, complex, float, int, str})

# Guards against a pathological structure costing more than the run it protects.
_MAX_DEPTH = 40
_REPR_LIMIT = 240


def _short_repr(value: Any) -> str:
    """``repr`` that cannot itself raise, and cannot blow up the wire payload."""
    try:
        text = repr(value)
    except Exception as exc:  # a __repr__ that raises must not become a second crash
        text = f"<unreprable {type(value).__name__}: {exc!r}>"
    return text if len(text) <= _REPR_LIMIT else text[: _REPR_LIMIT - 3] + "..."


def _type_name(value: Any) -> str:
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def make_execnet_safe(
    value: Any, *, _depth: int = 0, _seen: frozenset[int] = frozenset()
) -> tuple[Any, list[str], bool]:
    """Return ``(safe_value, offenders, changed)``, never raising.

    A container whose ``items()`` or ``__iter__`` raises degrades to its repr
    with an offender, rather than escaping into the hookwrapper. An exception
    out of here kills the worker -- which is precisely the failure this module
    exists to prevent, so the net must not be able to cause it. Recursion goes
    through this function, so the guard covers every depth, not just the top.
    """
    try:
        return _walk(value, _depth=_depth, _seen=_seen)
    except Exception as exc:  # noqa: BLE001 -- see the docstring: no escape, ever
        return _short_repr(value), [f" = <unwalkable: {exc!r}> {_type_name(value)}"], True


def _walk(value: Any, *, _depth: int = 0, _seen: frozenset[int] = frozenset()) -> tuple[Any, list[str], bool]:
    """Return ``(safe_value, offenders, changed)``.

    ``safe_value`` contains only types execnet serializes. ``offenders`` names
    every value that had to be REPLACED (by its repr), so the caller can report
    it. ``changed`` is True whenever ``safe_value`` differs from the input in any
    way -- including the silent case where nothing was replaced but a container
    SUBCLASS had to be normalised to its base type.

    ``changed`` and ``offenders`` are deliberately separate. Collapsing them is a
    real bug with a live reproduction: a plain ``collections.Counter`` reaching a
    report normalises cleanly to a ``dict`` and produces no offender, so gating
    the return on ``offenders`` hands back the ORIGINAL, still-undumpable object
    and throws the normalised copy away. Measured: one Counter in ``extra=`` on a
    single PASSING test killed a ``-n 2`` session and lost 77 of 85 items, with
    the sanitizer reporting nothing.
    """
    if type(value) in _ATOM_TYPES:
        return value, [], False

    if _depth >= _MAX_DEPTH:
        return _short_repr(value), [f" = <depth limit {_MAX_DEPTH}> {_type_name(value)}"], True

    ident = id(value)
    if ident in _seen:
        return _short_repr(value), [f" = <cycle> {_type_name(value)}"], True

    offenders: list[str] = []

    # `issubclass(type(...))`, not `isinstance`: a mock with a container spec
    # (`Mock(spec=dict)`, `create_autospec(dict)`) has a SPOOFED `__class__`, so it
    # satisfies `isinstance` while being neither iterable nor a real container.
    # Under `isinstance` those took two paths, both violating this module's
    # contract: `Mock(spec=dict)` raised TypeError out of the walk and killed the
    # worker; `MagicMock(spec=dict)` returned an EMPTY container with no offender
    # and no announcement -- a value destroyed silently. The atom branch above
    # already uses exact-type semantics for the same reason.
    if issubclass(type(value), dict):
        seen = _seen | {ident}
        # A dict SUBCLASS (OrderedDict, defaultdict, Counter) is refused by
        # execnet's exact-type dispatch just as a mock is, so rebuilding is a
        # change even when every element was already fine.
        changed = type(value) is not dict
        out: dict[Any, Any] = {}
        for key, item in value.items():
            safe_key, key_offenders, key_changed = make_execnet_safe(key, _depth=_depth + 1, _seen=seen)
            safe_item, item_offenders, item_changed = make_execnet_safe(item, _depth=_depth + 1, _seen=seen)
            changed = changed or key_changed or item_changed
            offenders.extend(f"<key>{o}" for o in key_offenders)
            offenders.extend(
                f".{safe_key}{o}" if isinstance(safe_key, str) else f"[{safe_key!r}]{o}" for o in item_offenders
            )
            out[safe_key] = safe_item
        return (out if changed else value), offenders, changed

    if issubclass(type(value), (list, tuple)):
        seen = _seen | {ident}
        # Same exact-type rule: a list subclass, or a namedtuple (a tuple
        # subclass), must be rebuilt as the plain base type.
        changed = type(value) not in (list, tuple)
        items = []
        for index, item in enumerate(value):
            safe_item, item_offenders, item_changed = make_execnet_safe(item, _depth=_depth + 1, _seen=seen)
            changed = changed or item_changed
            offenders.extend(f"[{index}]{o}" for o in item_offenders)
            items.append(safe_item)
        if not changed:
            return value, offenders, False
        return (list(items) if isinstance(value, list) else tuple(items)), offenders, True

    if issubclass(type(value), (set, frozenset)):
        seen = _seen | {ident}
        changed = type(value) not in (set, frozenset)
        items = []
        for item in value:
            safe_item, item_offenders, item_changed = make_execnet_safe(item, _depth=_depth + 1, _seen=seen)
            changed = changed or item_changed
            offenders.extend(item_offenders)
            items.append(safe_item)
        if not changed:
            return value, offenders, False
        base = set if isinstance(value, set) else frozenset
        return base(items), offenders, True

    # Everything else -- including subclasses of the atom types, which execnet's
    # exact-type dispatch refuses just as firmly as it refuses a mock.
    return _short_repr(value), [f" = {_type_name(value)}"], True


# pytest-json-report attaches the SAME `_json_report_extra` object to a test's
# call report and its teardown report, so an unmodified announcement fires twice
# per item. Announce each (nodeid, offenders) once per worker process.
_announced: set[tuple[str, tuple[str, ...]]] = set()


def sanitize_serialized_report(data: Any, *, nodeid: str = "<unknown>", stream: Any = None) -> Any:
    """Sanitize one already-serialized report dict, announcing any offender.

    Returns ``data`` unchanged (the same object) when the walk found nothing to
    rebuild. The walk still builds a replacement tree and discards it in that
    case -- measured on the realistic wire shape at 14.7 us for a report with no
    log records, 26.2 us with one and 69.5 us with five, i.e. under 4 s of CPU
    across a full unit run's ~17.5k reports x3 phases, spread over N workers.
    Cheap enough that avoiding the allocation is not worth the branching.

    Note for anyone reading ``unit.json`` downstream: a replaced value lands in
    the report as a STRING, so a log record whose ``process`` was poisoned reads
    ``"<MagicMock ...>"`` where an int was expected. That is deliberate -- the
    alternative is dropping it silently -- but it means the JSON is a faithful
    record of what happened, not of what the field's type claims.

    Scope: this covers test REPORTS only. xdist also puts ``workerinfo`` and
    ``workeroutput`` (execnet ``remote.py``) on the same wire without passing
    them through ``pytest_report_to_serializable``; today those carry only
    int/bool/str, but ``config.workeroutput`` is a public dict any plugin may
    write into.
    """
    if not isinstance(data, dict):
        return data
    safe, offenders, changed = make_execnet_safe(data)
    if not changed:
        return data
    if not offenders:
        # A container subclass was normalised but nothing was replaced. Nothing
        # to announce -- but the REBUILT value is what must go on the wire.
        return safe

    unique = tuple(sorted(set(offenders)))
    if (nodeid, unique) in _announced:
        return safe
    _announced.add((nodeid, unique))

    out = stream if stream is not None else sys.stderr
    print(
        f"[xdist-report-safety] {nodeid}: {len(offenders)} value(s) in this report cannot cross "
        f"the execnet wire and were replaced by their repr -- "
        f"{'; '.join(unique[:10])}"
        f"{' ...' if len(unique) > 10 else ''}",
        file=out,
        flush=True,
    )
    return safe
