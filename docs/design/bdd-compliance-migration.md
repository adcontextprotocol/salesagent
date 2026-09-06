# Add a response compliance check to every BDD scenario

Every scenario carries a compliance check, so that a scenario which passes is
compliant with the pinned AdCP schema. A general check grades the whole
document; the scenario's existing assertions stay as the specific check. The
two are complementary — the general one catches a malformed response the
specific assertions never look at, and the specific one catches a wrong value
the schema permits.

This page is the instruction for that migration. It was derived from a 12-
scenario pilot (commit `1370df882`) chosen to span every shape, and the
measurements it cites are that pilot's.

## Scope

The migration applies ONLY to the 30 feature files that a `tests/bdd/test_*.py`
module loads. The other 20 files call tools this seller has not built; they are
inventory for unbuilt protocol surface and are left alone. Verified: no loaded
file names an unregistered tool, so no line you add can hit the registry
refusal in `tests/helpers/response_schemas.py`.

## The sentence to add

Three forms. Add ONE per scenario, as the FIRST `Then` of the scenario, with
the previous first `Then` becoming an `And` beneath it.

| Situation | Line |
|-----------|------|
| The tool responds in one shape | `Then the response is compliant with the <tool> spec` |
| The scenario pins ONE outcome of a branching tool | `Then the response is compliant with the <tool> <branch> spec` |
| The scenario asserts a refusal | `Then the error is compliant with the AdCP error spec` |

Four tools branch: `create_media_buy`, `update_media_buy` and `sync_creatives`
into `success` / `error` / `submitted`, and `sync_accounts` into `success` /
`error`. The other ten respond in one shape. Read the branch words from
`branch_names(tool)`, never from memory — they come from the schema's own
`oneOf` titles.

## Choosing the form

The scenario already states its outcome. Read it; do not decide it.

- `Then the response should succeed`, or a status of `"completed"` → the
  `success` branch.
- `Then the response status should be "submitted"`, or an assertion that a
  `task_id` is present → the `submitted` branch.
- `Then the operation should fail`, or assertions about an error code and
  recovery → the refusal line. This is the single most common shape: 93 of the
  457 scenarios in the branching-tool files.
- A `Scenario Outline` whose outcome is a column → the general form, with no
  branch word. See below.

## The scenario outline

A `Scenario Outline` cannot name a branch. 104 scenarios end in `Then the
result should be <outcome>`, and a single outline carries both `Examples: Valid
partitions` and `Examples: Invalid partitions` — so no one line is right for
every row. The `<outcome>` column holds prose (`error with suggestion`,
`budget validation passes`), not branch words, so it cannot be interpolated
into the sentence either.

Use the general form on those. It grades the whole `oneOf` — "one of the legal
shapes" — which is weaker than naming a branch but is NOT vacuous. Measured
against `create-media-buy-response.json`: an empty object, an object of junk
keys, a success document missing `confirmed_at` and `revision`, a submitted
document missing `task_id`, and a success document whose `status` is misspelled
are all rejected.

Refusing the general form here was the original design, and it was wrong: it
would have left those 104 scenarios with no compliance check at all, which is
the outcome the rule exists to prevent.

## Refusals are not exempt

A refusal carries no response document, so it is the path most easily left
unchecked — and leaving it unchecked is how "the suite is schema-clean" comes
to mean "the happy paths are". `build_two_layer_error_envelope` emits
`{adcp_error, errors[], context}`, and every entry in `errors[]` is a
`core/error.json` object requiring `code` and `message`. The step grades them.

The error line is tool-independent by design. The AdCP error vocabulary is
OPEN — `code` is a wire-typed string, the published codes are documentary, and
a receiver decodes an unknown one by reading `recovery` — so there is nothing
per-tool to resolve. WHICH code was emitted is a different obligation, graded
by `assert_envelope_shape`; this grades that the refusal is well-formed.

## Working method

Within one feature file the transformation is usually identical across many
scenarios, because they share a first `Then`. Use a single `replace_all` edit
per distinct first-`Then` shape rather than editing scenario by scenario. In
the pilot, six `get_products` scenarios and 43 `create_media_buy` refusals each
went in one edit.

Use the Read/Edit/Write tools. Scripted heredoc edits have destroyed feature
and factory files in this repo more than once.

Check the result of a `replace_all` before moving on. A dropped trailing space
in the pilot's replacement produced `And the error code should be"BUDGET_TOO_LOW"`
across 43 scenarios; `grep` for the line you rewrote and read it.

## Verification

Run the module on the box — `cassini test bdd tests/bdd/test_ucNNN_*.py`.
Local pytest does not run BDD properly here.

A green run is not enough on its own. Confirm the scenarios you touched are
among the PASSES and not among the xfails: a scenario sitting in a ledger
xfails whether or not your line is correct, so it proves nothing about the line.
In the pilot, the `submitted` and refusal shapes were confirmed executing, and
the success-branch scenario was found to be xfail-ledgered on "UC-002 harness
not yet wired" — so that one line is added but not yet graded, which is worth
knowing and worth saying.

If a scenario goes red, that is a finding, not an obstacle. A response that
does not match its pinned schema is the defect this migration exists to expose.
Record it and xfail the scenario with a reason naming the divergence; do not
weaken the check to make it pass.
