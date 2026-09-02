"""BDD binding for the locally-added request-bounds feature.

Grades the four behaviourally-reachable constraint relaxations:
a local model redeclared a field its adcp parent constrains and dropped the
bound, so an out-of-bounds request is accepted (or refused with the wrong code).

Retire together with the local feature once adcp-req grows the equivalent
storyboard scenarios.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-constraint-relaxation-rejections.feature")
