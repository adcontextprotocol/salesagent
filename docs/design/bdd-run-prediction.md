# Prediction for the first run after binding every feature file

Written BEFORE the run, so the run can falsify it. A prediction recalled
afterwards teaches nothing — it bends to whatever happened.

Baseline is run `1c81890872ef4fd9be44f6265ada9a44` (bdd_inprocess: 1902 passed,
768 failed, 5642 xfailed, 3 skipped, 8324 total). Since then: every feature file
is bound, the undispatchable-tool skip rule landed, and the compliance check
became outcome-aware.

## 1. Collection roughly triples

8324 → about 19000 instances. Collection counted 19062 selected, and a run should
land near it. A materially smaller number means feature files are not being
collected under the real runner.

## 2. Skips go from 3 to about 9169

This is the number that grades the skip rule. It was 3.

If it comes back near zero, the rule did not fire under the real runner — the
same silent no-op that the bare `except` around the feature re-parse produced,
where the check reported success while doing nothing.

## 3. The 345 form-bug failures clear

Failures reading `expected a success wire body, got error ...` should be GONE.
The compliance check now grades the error envelope when a call was refused. This
has only been verified by calling the function directly; the run is the first
real test of it.

If they persist, `_dispatch_errored` is not seeing the outcome the BDD transports
actually stash, and the fix is wrong rather than incomplete.

## 4. The 423 schema failures mostly persist

They trace to GH #2012 (`by_package` missing `pricing_model`, `rate`, `currency`
— 50 scenarios) and GH #1998 (`formats[].assets[]` pixel_tracker entries — 6
scenarios). Neither is fixed.

CAVEAT, and the reason this one is weak evidence either way: the boundary
refactor in the sibling worktree is rewriting response shapes right now
(`refactor: inherit the protocol envelope, delete the mixin that hand-declared
it`). Any movement in this number may be that work, not ours. Do not read a
change here as a finding.

## 5. A large NEW failure population: unbound steps

This is the one to look at, and it is expected rather than alarming. About 1600
newly-bound scenarios call registered tools yet have never had step definitions
written — UC-001 alone is 1110 instances. They should fail with
`StepDefinitionNotFound`, naming the step that is missing.

That failure is INFORMATION, not regression: nothing was passing before, because
nothing was collected. The list of missing steps is the work inventory for wiring
those use cases.

If instead these scenarios PASS in bulk, something is wrong — their steps would
have to be bound by a generic catch-all, which would mean they are being graded
by steps that assert nothing in particular.

## What would falsify the whole approach

Skips near zero (rule inert), or the previously-live 8300 instances showing new
failures that are not #2012/#1998. The latter would mean binding new files
perturbed the files that already worked, which nothing in the change should do.
