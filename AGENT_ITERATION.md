# AlphaForge agent iteration

Baseline: `30fcdc2`. This iteration focuses on the Robert and Amira simulations and the agent work that differentiates them: identify a decision-changing rule or evidence gap, test it, and have an independent calculation verify the comparison. Benchmarks distinguish workflows on repeated development fixtures from decisions on new cases. GitHub Issues [#6](https://github.com/WindsTrace/datathon-prep/issues/6) and [#7](https://github.com/WindsTrace/datathon-prep/issues/7) record the earlier roadmap and intake experiment.

| Step | Goal | Acceptance evidence |
| --- | --- | --- |
| 1. Agent collaboration | Finish parallel work before returning, preserve checked results through optional model failures, and keep mandatory independent review. | Reproduce original failures, replay with injected faults, inspect immutable output and handoff trace, rerun the base audit cohort. |
| 2. User intent | Make the extracted rules inspectable and editable. Ask a targeted question or block rules that the current solver cannot honor. | Check negated and authorized quotes, corrections, conflicts, unsupported constraints and reconfirmation. Report real parser accuracy separately from UI confirmation. |
| 3. Decision-changing tests | Let Review select at most one bounded counterfactual or point to the missing evidence that prevents a decision. Keep the original policy fixed. | Show the changed field, before and after outcomes and proof, or explain why no material change is available. Reject a changed second field and invalid audit. |
| 4. Comparison and speed | Compare fixed rules, a bundled model session and separate agents using the same tools, data and replay budget. | Report correct choices, no-change cases, unsafe release, completion, phase latency and model calls. The first target for confirmed-input review is a median of 6.5 seconds, subject to unchanged decision quality. |
| 5. Integration | Verify the Streamlit and CLI paths, document limitations and commit results to GitHub. | Record real AWS evidence separately from local or injected tests. Keep raw starter data and credentials out of commits. |

The initial live benchmark returned 20/20 on each structured arm. Single-agent median latency was 4.78 seconds with 112 calls and multi-agent median latency was 9.44 seconds with 190 calls. The follow-up free-text experiment matched 7/14 requests in both branches. These are baseline observations.

## Step 1 · Stable handoffs and a shorter critical path

- Reproduced the baseline failure in which Exposure stopped while Scenario still wrote to the returned report. Both branches now settle before the report returns.
- A validated tool result remains usable if only the model's final handoff fails. Missing independent review still blocks the decision. Model explanation is optional and the default path uses the deterministic explanation of the verified result.
- A bounded Strands role can finish after its validated tool callback. The bundled control retains its original model session. The checked result, routing event and timing remain available for comparison.
- Local verification passed all ten targeted tests, including a Strands structured tool call with the real SDK and an injected model. The tests cover parallel settlement, post-tool failures and the independent review gate. Live completion and latency are measured separately below.

### Step 1 live result

AWS competition CloudShell, Nova 2 Lite, official starter data, `50dab34`, 10 cases × 2, up to three concurrent pairs.

| Audit arm | Correct status and reason | Independent parity and complete trace | Median elapsed | Converse calls |
| --- | ---: | ---: | ---: | ---: |
| Deterministic | 20/20 | 20/20 | 7.04 ms | 0 |
| Bundled with original completion behavior | 20/20 | 20/20 | 4.35 s | 112 |
| Staged with checked tool completion | 20/20 | 20/20 | 2.74 s | 86 |

All arms had zero false releases and zero avoidable holds. The staged median met the 6.5-second goal on this measured cohort. Historical staged median was 9.44 seconds in a separate run. The shared pre-optimization Profile parser obtained 6/12 on this run with six unnecessary clarifications and zero premature policies. Intake accuracy is a separate improvement target. A bundled mode that also stops after checked review is included for the fair follow-up comparison.

## Step 2 · User-confirmed intent

- The Profile handoff distinguishes resolvable missing fields from conflicting or unsupported material rules. It can retain exact request excerpts for user inspection, and the guard rejects ungrounded excerpts.
- Users can edit individual supported fields, see the compiled policy and confirm it explicitly. Edits invalidate the previous displayed decision until confirmation. Unsupported and dual-cap requests require the user to resolve the original instructions.
- The original wording and excerpts stay out of the Streamlit audit download. The extractor still relies on a model to recognize all material terms, so UI confirmation and separate live intake tests remain necessary.

## Step 3 · One decision-changing check

- Review can choose one typed, audited follow-up, abstain, or ask for the issuer disclosure that limits the decision. The report distinguishes an independently replayed hypothetical from the confirmed decision.
- The tool rejects unavailable and competing selections. The recheck verifies the changed field, frozen sources, market metrics, original portfolio and independent review. Amira's QQQ-funded illustration exposes a 0.60937-point disclosure gap without treating the alternative as eligible.
- The challenge works through the reference and user-confirmed Streamlit screens. Thirteen focused tests cover material and no-change replays, exposure evidence, bundled parity, audit mismatch and safe export.

## Step 4 · Matched challenge benchmark

- Nine new typed-policy cases test choosing the loss metric, reserve floor, exact purchase size, disclosure freshness, an evidence request and abstention. Each request can produce at most one re-audit.
- A fixed structured-signal policy is the control. Both live arms use the same bounded text-aware selector. They differ in whether the before/after audits are bundled or staged. This comparison measures the useful text selection against a structured control and the execution trade-offs, without attributing a shared selection result to agent count.
- The fixed control completed nine base audits with six correct follow-ups and zero unsafe releases or amendments. Choosing the expected option directly produced nine independently verified comparison outcomes. Live results follow below.

### Candidate observations and scope checks

The integrated candidate `33d6a86` passed 82/82 tests on official data in competition CloudShell. The production CLI passed 6/6 offline scenarios and the browser-style tests cover confirmation and comparison. The audit benchmark kept 20/20 valid decisions, independent parity and complete traces in all arms, with zero false releases and zero avoidable holds. The optimized bundled and staged arms reached median confirmed-to-review times of 2.58 s and 2.69 s, respectively. End-to-end staged audit took 2.70 s median, 3.10 s maximum and 86 model calls. Bundled took 2.59 s median, 5.11 s maximum and 92 calls. This meets the 6.5 s reviewed-latency goal on the cohort. It supports the shorter audited path and shows no accuracy advantage from agent count on these fixtures.

The new challenge cohort completed 18/18 baseline audits in all arms:

| Arm | Correct follow-up | Unsafe release | Unsafe policy change | Base audit p50 | Follow-up p50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed structured rules | 12/18 | 0 | 0 | 16.07 ms | 7.96 ms |
| Bundled audit plus text-aware selector | 16/18 | 0 | 0 | 2.93 s | 3.09 s |
| Staged audit plus text-aware selector | 16/18 | 0 | 0 | 2.85 s | 3.29 s |

Both live arms confused the same reserve versus purchase-size wording on both trials. The resulting no-change replay remained hypothetical. The follow-up maps the short-term bond sleeve explicitly to the reserve fund and differentiates a funding split from the permission to purchase less.

Profile v1: Nova 2 Lite matched 8/20 expanded raw prompts, median 1.40 s, all 20 checked typed handoffs and zero premature policies on expected-hold requests. The same prompts with Claude Haiku 4.5 matched 5/20, median 3.66 s, 12 checked handoffs and zero premature policies. The model-only change did not improve this cohort. Most failures were avoidable holds or wrong clarification fields. The next Profile revision simplifies tool fields and separates complete from additive funding permissions. Retests follow below.

The revised Review selector chose the correct check in 18/18 repeated cases with staged replay and 18/18 with bundled replay. The fixed policy was 12/18. Each arm had zero unsafe releases or changes to the original policy. Staged base audit p50/p95 were 2.62/3.33 s. Its follow-up p50/p95 were 3.25/4.18 s. Bundled base p50/p95 were 2.84/4.52 s, and follow-up p50/p95 3.05/4.91 s. This was a targeted retest after addressing the reserve wording in the same cohort. The result shows text-aware selection and replay quality on those cases, with no claim of general accuracy or a quality advantage from agent count.

An early revision of the smaller Profile contract matched 7/20 on the expanded raw cohort with zero premature policies. Since it did not meet the intended accuracy threshold, the app will offer direct structured entry that can run the identical review chain. Free text remains a reviewable draft.

### Structured entry and recovery

The primary request form now accepts supported rules directly. It requires the user to confirm the complete policy, supports staged Bedrock audit or offline verification, and invalidates the previous displayed report when a rule or execution mode changes. It remains usable when Profile times out. Bedrock free-text extraction is still available as an optional draft and uses a smaller, typed tool with separate additive and exhaustive funding permissions. The local suite on the official starter passed 91/91, including both Streamlit challenge paths and the direct-entry recovery path. On ten early typed-contract probes, Sonnet 4.5 matched 7/10 and Nova Pro matched 2/10. These samples were exploratory.

### Exact candidate model and trace checks

The `b4bd2ef` candidate passed 91/91 with the official starter in CloudShell. On the same 20 raw attempts, Nova 2 Lite matched 3/20 at p50 1.14 s. Sonnet 4.5 matched 14/20 at p50 3.60 s. Both produced 20 checked handoffs and zero premature policies on the expected-hold cases. The optional draft uses Sonnet for higher observed fidelity, while the audit and challenge still use Nova 2 Lite. The default structured form bypasses text parsing and still offers the staged Bedrock audit. Raw intent recognition remains below the completeness target. Its remaining failures included missing the stated purchase size and misdirected clarification.

Independent code review also reproduced a trace-redaction issue when the SDK echoed malformed tool arguments. The final revision records failed Profile tool attempts without their input or output and records normalized values on success. A regression exercises the real SDK tool schema with malformed data followed by a successful retry.

## Step 5 · Application and CLI integration

Streamlit AppTest on the exact `f0e559a` checkout in the competition AWS environment verified the Robert path through live staged audit and a live, independently checked maximum-drawdown replay. The original review took 3.13 seconds with four Converse calls. The follow-up took 4.00 seconds with one selection call and four replay calls. Amira completed the original audit in 3.32 seconds (five calls) and the issuer evidence request in 0.71 seconds (one call, no replay). The original policy survived both checks unchanged. The optional Profile used Sonnet and asked for the loss definition on Robert's ambiguous request.

The initial final-candidate CLI regression scored 1/6 because it sent the already-defined reference policies back through the experimentally weak Nova text parser. The CLI now passes confirmed structured policies to the same staged path as Streamlit and uses the selected Profile model for the genuinely ambiguous fixture. The interactive CLI still parses and confirms user text separately.

The `a731671` candidate then passed **6/6 live AWS CLI scenarios**, **92/92** official-data tests in CloudShell and **92/92** locally. The local CLI also passed 6/6 offline. Completion, latency, and challenge behavior are verified on these scoped fixtures. Free-text extraction and performance on other market data or portfolios remain open quality questions. The original stable release stays available on `main`; all this iteration's changes and measurements are on the private `agent-optimization` branch.

## Iteration 2 · Input fidelity, risk drivers and financial boundaries

- Start from `0975ae5`. Test the previously missed Sonnet purchase-size cases on the same cohort. Preserve reviewable drafts and direct confirmation.
- Independently attribute maximum drawdown to holdings at the portfolio's own peak and trough. Show one independently checked eligible funding example even when no funding preference is given.
- Support an explicit hypothetical ZST.TO floor or disclosure age in a one-field challenge. Continue checking that the original policy, price replay and raw disclosure records do not change.
- Add a second financial challenge cohort from the official starter with numerical boundaries, stale or unpublished evidence, no-change requests and a separate missing-FX resilience check.

### Iteration 2: audit and challenge inputs

The verified analysis includes signed asset contributions to the historical drawdown measured over the portfolio's own peak-to-trough dates. The independent review recomputes these figures, and a regression rejects a modified contribution. For a feasible case without a preferred funding source, the audit shows a verified example alongside the applicable range. If multiple mixes reach the same eligible maximum, the example uses the least ZST.TO sale and labels this display convention. A hard-limited, unresolved or invalid audit still withholds an ineligible example.

The user can explicitly test a tighter reserve or disclosure age. The challenge checks exact basis points or days and re-audits one field only. In the official Robert data, raising the reserve to 19.50% leaves only 0.50 percentage points of ZST.TO funding available for the full purchase. For the observed issuer disclosures, 137 days retains them and 136 days excludes them as stale.

The expanded challenge benchmark preregisters 10 decision requests and a separate endpoint-loss resilience case. The new cases exercise independent CAD boundary derivation, date cutoffs, calculations with unchanged decisions, and an out-of-scope security substitution. Forced expected choices passed all cases offline. In two fixed-rule repeats, selection matched 10/20 and the missing-FX resilience check passed 2/2, with no unsafe release or policy mutation.

### Iteration 2: Profile paired retest

On the same 10 requests and two repeats, Sonnet at `123a5c0` matched 16/20 versus the earlier 14/20 run. Median latency was 4.03 s. All 20 tool handoffs completed. The four remaining misses all asked for an already stated funding source. The next revision checks only an unambiguous source directly attached to a grounded buy clause. It keeps broader funding authorization and conflicted or quoted terms separate. A live retest checks the effect.

### Iteration 2: official-data Bedrock results

- With `20a71c4`, the new, unused challenge cohort produced **20/20** correct staged comparisons and **20/20** correct bundled comparisons. The fixed rule arm matched **10/20**. Each arm had **zero** unsafe releases or policy changes and passed **2/2** separate missing-FX checks. The two Bedrock arms share the same hint-aware selector. No relative decision-quality gain between the two live architectures was measured.
- On the same run, staged base-audit p50/p95 were **3.06/4.06 s**, and staged follow-up p50/p95 were **3.41/4.44 s**. Bundled base-audit p50/p95 were **3.05/4.39 s**, and its follow-up p50/p95 were **3.22/4.91 s**. These p95 values describe a 20-attempt sample with at most three concurrent pairs.
- The separate structural regression matched **20/20** decisions, independent audit parity and complete traces in each of the three arms, with zero false releases or avoidable holds. Confirmed-to-review medians were **2.55 s** staged with 86 calls and **2.54 s** bundled with 92 calls. The staged path remains below the 6.5-second target.
- At `fa28957` Sonnet matched **18/20** on the original paired intake requests, compared with 14/20 at the start and 16/20 after size recovery. All handoffs succeeded, zero expected-hold requests produced a draft policy, and p50 was **3.88 s**. The remaining two errors are repetitions of the same explicitly adopted quotation, which was held as a conflict. The supported direct input route remains available.

### Iteration 2: full starter data and limits

Inventoried all six supplied CSVs and the build warning file. The data contains 31 assets, 40,049 price observations, 1,245 FX fixings, 658 corporate-action rows, 8,281 macro observations across nine series and six source metadata rows. The two archived replay windows have 246 and 67 common price dates before FX alignment, and 244 and 67 after alignment. The missing 2022 common fixing dates are September 30 and November 11, both interior to the window. Both endpoint pairs are available in the official data. The benchmark deliberately removes one 2025 endpoint to verify withholding. Corporate actions and the asset universe inform checks and provenance; the simulation uses adjusted closes already normalized by the provider. Macro observations remain descriptive because the archive lacks publication-vintage history. The source inventory reproduces identically from the full ZIP and an extracted folder.

### Iteration 2: quote comparison and final verification

The final Profile prompt clarifies that an explicitly adopted financial quote participates like unquoted language, while a conflicting active rule still requires clarification. The validator and authorization gates are unchanged by this final prompt edit. On the 20 repeated original attempts the candidate matched **20/20**, versus **18/20** before this prompt edit and **14/20** at the start of this iteration. The final p50 was **3.72 s**. Both prompts matched **12/12** on a separate, newly frozen quoted-request cohort, with zero premature policies in each run. This comparison establishes repeatability on these limited request sets.

All **113/113** local regressions passed with the full official ZIP, including the full starter inventory and user interface, and the live AWS CLI still passed **6/6** reference cases after the financing, witness and challenge changes. This revision continues to use the confirmed structured path by default. Cross-asset applicability and interpretations outside the measured English wording remain unverified.
