# Analysis reliability validation — 22.09 revision

This is an implementation and observed validation record, not a claim of universal generalization or objectively correct model review. English remains the product language. No persona-specific verdict rules were introduced.

## Main-path changes

| Files | Purpose |
| --- | --- |
| `inquiry_contracts.py`, `inquiry_engine.py` | Observable task contracts, shared budgets, argument synthesis, claim/task review and bounded evidence repair |
| `customer_tools.py`, `customer_risks.py` | Checked measurements, actual output coverage, compatible comparisons, independent window-count replay and explicit horizon inputs |
| `customer_state.py`, `customer_agents.py`, `customer_profile.py` | Sourced statements, corrections/retractions/repetitions, unknowns and preservation of prior facts |
| `customer_data.py` | Generic listing resolution, ambiguity/provenance, dated observations and request-local source cache |
| `customer_workflow.py` | Production wiring and partial versus complete result status |
| `customer_view.py`, `customer_report.py` | Conclusion first, visible limitations, task/evidence trace and consistent export status |
| `customer_acceptance.py`, `revision_validation.py` | Compact observations, same-data comparison and paired fictional requests |
| `test_inquiry_contracts.py`, customer test modules | Independent code-authored numerical, scope, state and repair expectations |

The active path is `customer_view → research_question → understand/apply_turn → plan_inquiry → execute_checks → synthesize_inquiry/review_claims → customer_view/report`. The older compatibility synthesizer is not the production entry point.

## Automated result

`DATATHON_STARTER_PATH=/tmp/alphaforge-assistant-starter.zip DATATHON_FULL_STARTER_PATH=/tmp/alphaforge-assistant-starter.zip <venv>/bin/python -m unittest discover -s tests`

**562 tests passed in 79.062 seconds** on Python 3.10. After the final volume-capability guard, all 83 targeted customer/contract tests also passed (2.047 seconds). `git diff --check` passed. The archive paths are local test inputs, not embedded application dependencies.

## Validation method

Deterministic tests check arithmetic/reference/scope contracts, short and unavailable coverage, cache input identity, review-driven retrieval, genuine versus superficial completion, field correction/retraction, and generic entity ambiguity. These expectations are authored in code; they are not grades from the answer model.

Live calls used Amazon Bedrock, `global.anthropic.claude-sonnet-4-5-20250929-v1:0`, `us-east-1`, temperature zero. Prices were frozen within paired/comparison runs. Five first-use ITOT requests varied name, unrelated hobby, wording and a material near-term withdrawal. These became development cases after their first results were inspected.

## Failures retained

| Artifact | Observed failure and response |
| --- | --- |
| `revision-first-failure.json` | Initial comparison had a baseline wrapper token-limit mismatch and a later timeout; excluded from improvement claims |
| `revision-contract-failure.json` | An overstrict quotation contract prevented a useful answer; numeric quotation binding replaced the mandatory placeholder rule |
| `revision-handoff-failure.json` | Free-text response bypassed the required structured handoff; supported Sonnet terminal tools now use named tool choice |
| `revision-context-id-failure.json` | Stable customer-state IDs were absent from the citation registry; registry now includes them |
| `revision-quotation-failure.json` | Valid copied numbers were rejected; exact typed quantities are now accepted with provenance |
| `revision-review-false-positive.json` | Reviewer incorrectly rejected a Python window count and repeated old errors; review now sees a fresh snapshot and can request calculation verification |
| `revision-optional-field-failure.json` | Provider filled a horizon field on unrelated task types; only tools supporting that parameter now consume it, with an exact-source check for actual horizon tasks |
| `revision-live-semantic-failure.json` | A first-use SCHX customer report overstated execution feasibility from a volume proxy despite model approval; a deterministic capability-boundary guard now rejects such assertions |
| `revision-paired-first-run.json` | Four answers released, one paraphrase failed review handoff; some completion and goal-amount interpretations were inconsistent |

The first paired run is **not an all-pass result**. All five retained identical no-withdrawal asset metrics. Names/hobbies did not reverse the main historical qualification, but name substitution introduced an unsupported assumption that the investment amount was the required deposit; unrelated detail changed completion status. The paraphrase produced a valid main historical summary but also an unsupported “trivial market impact” inference, and its review handoff failed. The material withdrawal triggered a Python cash-flow replay with a shortfall, but the requested short horizon received long-horizon evidence; the reviewer noticed this. These findings motivated generic schema, support-reference, task-input and qualification fixes, not a ticker-specific answer.

## Comparable baseline

Baseline source was preserved before editing from the published state at `085de5df9e0047dd7334b25824990f4bb2b4157a`. Both versions receive the same question/model, shared frozen public observations, a 240-second outer limit, ten role invocations and the current role output ceilings. Contracts differ by revision. Baseline per-call timeout is 45 seconds; the new engine permits 80 seconds within the same outer budget. This is a bounded comparison, not identical per-call latency. The baseline has no task ledger; task-completion metrics cannot be retrospectively fabricated. API tokens are observed usage; dollar cost is unknown because account pricing was not assumed.

## Remaining scope limits

The customer catalog does not yet expose a complete before/after portfolio solver, comprehensive fund look-through, fundamentals, news or future return forecasts. Missing portfolio weights or qualified sources must produce a scoped answer or follow-up. The existing reference engine is retained but not silently used to invent customer allocations.

Semantic entailment and materiality are still judged by a fallible model. Exact number matching does not prove that prose uses a number correctly. Task prose can request more than its enumerated measures; semantic review may miss that mismatch. A finite paired sample does not establish invariant behavior on all unseen questions. Yahoo observations are dated public data, not guaranteed real-time execution quotes; currency conversion remains CAD/USD.

The most valuable next evaluation is a larger untouched set with independent human claim/task labels, repeated runs and explicit statistical uncertainty, followed by exposing additional calculators through the same honest task contracts.

## Observed before/after comparison

`revision-comparison.json` retains the same-data ITOT paraphrase comparison with the final volume-capability guard. Both versions delivered an answer; both were manually inspected. The earlier run remains in `revision-comparison-before-boundary.json`.

| Observation | Preserved baseline | Revised inquiry |
| --- | --- | --- |
| End-to-end latency | 45.978 s | 72.629 s |
| Role invocations | 5 | 5 |
| App status | ready | partial |
| Observable task completion | No ledger | 3 complete, 1 blocked cash-flow task |
| Asset no-withdrawal metrics | Identical | Identical |
| Material unknowns | Loss capacity, reserves, portfolio fit | Loss capacity and unspecified target; cash-flow gap explicitly retained |

The new version was slower. This small comparison does **not** establish an aggregate quality improvement. It does establish that incomplete requested work is observable and retained as partial instead of being hidden behind a fluent report. API-response counts and deduplicated observed tokens are recorded in `revision-comparison-summary.json`; dollar cost remains unknown.

The revised conclusion distinguishes the USD 5700 investment budget from the unstated down-payment target, quotes the verified historical return and drawdown, and qualifies future outcomes. The volume language states that a small ratio does not indicate execution difficulty, alongside an explicit statement that the proxy cannot measure spreads, impact or certainty. This negative wording can still invite an overly favorable interpretation; the result is not proof of execution feasibility or universal semantic reliability.

The final guard checks a specific evidence boundary: the current catalog has a volume ratio but no spread, depth, price-impact or execution-feasibility evidence. Positive assertions about those quantities are rejected for repair; explicit statements that they remain unknown are allowed. This is a bounded check and cannot recognize every natural-language paraphrase. It encodes no investment verdict or persona mapping.

## Reproduce the preserved baseline comparison

From a clone containing the published branch, export the baseline commit's `datathon/` directory into a temporary Python package named `_baseline_2209`, and add its parent to `PYTHONPATH` alongside the current repository. Use the same installed requirements and existing AWS environment for both versions. Then run `asyncio.run(datathon.revision_validation.compare_revision(question))`, or the comparison button in Reference cases → Reasoning acceptance. If the baseline package is absent, the harness explicitly reports that no before/after claim is available. It does not synthesize a baseline answer.

The separate `collect_reliability_cases()` function holds source observations fixed across the five paired inputs. Its output is raw evidence for independent review, not an automatic overall pass. For a new evaluation, replace the development questions before inspecting outputs and retain all failures.

A further live follow-up exposed a transactional intake bug: a rejected state update prematurely marked the handoff as submitted, preventing correction on retry. The state is now committed only after validation succeeds, and a regression test repairs an invalid target and confirms that the corrected horizon is retained.

## Live conversation-state repair

The SCHX follow-up changed a 2-year course-funding horizon to a one-time USD 4800 withdrawal in 3 months, with no other funds for that payment. `revision-followup-failure.json` records the original failure: the model repeated old facts that were not quotations from the new message, and strict extraction rejected the entire update.

The repair accepts only **exact matches to already known active facts** as carry-forward, retaining their original provenance; changed or new facts still require current-message quotations. Assets not repeated by the user remain known. The successful real Bedrock state check in `revision-followup-state.json` has no validation errors, replaces the old horizon with `in 3 months`, records the explicit withdrawal, preserves SCHX and the original amount, and keeps loss capacity unknown. This is verified separately from whether a later full report succeeds.

## Final review-gate corrections

`revision-conditional-review-failure.json` records a real follow-up in which the reviewer classified the main claim as conditional **and requested narrowing**, yet the earlier acceptance condition treated the status alone as approval. Acceptance and retention now also require `repair == none`. A requested repair cannot be published as an accepted judgment merely because its support classification says conditional.

The same run exposed a task asking for shortfall frequency while receiving a single-path cash-flow replay. Explicit statistical requests in the task question/completion condition (median, percentiles, distribution, shortfall frequency) now remain missing unless the actual output supplies them, even if the planner omits them from its measure list. The catalog explicitly states that cash-flow replay covers one historical starting path.

Numeric binding now covers argument relevance, assumptions and limitations as well as displayed prose. A model-created dollar calculation in a relevance field cannot bypass the Python calculation requirement. Each of these failures has an independent regression test.

The stored before/after comparison precedes these last review-gate and conversation-state fixes; it is retained with that limitation rather than relabeled as a benchmark of every final change.

## Final customer-page execution

`revision-final-followup.json` was copied from the actual page's argument/task/review export after the final gates were active. The customer interaction began with SCHX, USD 4800 and a 2-year course-funding goal, then explicitly corrected the withdrawal to once in 3 months with no other funds. The corrected state reached planning and the calculators.

Observed results: 1190 overlapping 3-month windows; worst observed change −18.00%; the single replay starting 2021-11-15 paid USD 4537.33 against USD 4800 requested, leaving USD 262.67 shortfall. These are historical calculations, not a probability or a forecast. The report displayed the conclusion first, with assumptions, limits, citations, price/drawdown charts and a withdrawal chart.

The run took 78.152 seconds, four role invocations, four selected tool executions and one cached-source operation, reporting 62477 tokens. Three tasks were marked complete; cash-needs analysis remained **partial** because the requested distribution was not produced by a single-path replay. The page prominently displayed the partial-result status. Screenshot: `analysis-report-2209.jpg`.

**Manual semantic acceptance is not an all-pass.** The final model-approved prose still uses qualitative likelihood language beyond a computed frequency and suggests unresearched alternative product categories. The visible scope limits and partial banner do not prove those assertions. These are retained as semantic-review false positives, not concealed or rewritten as successful test results. The deterministic task, quantity, provenance and state gates passed their independent tests; the fallible model entailment check remains a material limitation. No claim of fully automated proof, universal personalization or universal invariance is made.
