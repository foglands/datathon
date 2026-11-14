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

## Step 3 · One decision-changing check

- Review can choose one typed, audited follow-up, abstain, or ask for the issuer disclosure that limits the decision. The report distinguishes an independently replayed hypothetical from the confirmed decision.
- The tool rejects unavailable and competing selections. The recheck verifies the changed field, frozen sources, market metrics, original portfolio and independent review. Amira's QQQ-funded illustration exposes a 0.60937-point disclosure gap without treating the alternative as eligible.
- The challenge works through the reference and user-confirmed Streamlit screens. Thirteen focused tests cover material and no-change replays, exposure evidence, bundled parity, audit mismatch and safe export.

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

## Step 4 · Matched challenge benchmark

- Nine new typed-policy cases test choosing the loss metric, reserve floor, exact purchase size, disclosure freshness, an evidence request and abstention. Each request can produce at most one re-audit.
- A fixed structured-signal policy is the control. Both live arms use the same bounded text-aware selector. They differ in whether the before/after audits are bundled or staged. This comparison measures the useful text selection against a structured control and the execution trade-offs, without attributing a shared selection result to agent count.
- The fixed control completed nine base audits with six correct follow-ups and zero unsafe releases or amendments. Choosing the expected option directly produced nine independently verified comparison outcomes. Live results follow below.
