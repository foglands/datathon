# Changelog

## 2026-11-16 - Team 38 submission package

- Credit Peng Peng, Shaoze Ying and Xuhan Liu. Align the one-pager, technical guide, recording plan and setup documentation with the current customer workflow.
- Document live AWS searches, the verified Tesla price episode, supported analysis and the remaining public-data gaps.

## 2026-11-16 - Live web research

- Let the Bedrock planner select search topics and surface AgentCore search status and source links in the customer report.
- Verify selected issuer filing metadata directly against SEC EDGAR. Keep source excerpts outside numerical evidence and daily-price calculations.
- Run live research independently of the optional replay archive.

## 2026-11-16 - Daily data preparation and partial conclusions

- Validate and package daily-price exports for the three customer examples. Record the shared window, observation count, source, adjustment basis and archive digest.
- Include relevant existing holdings in comparative research without assigning them the proposed purchase amount. Keep comparisons within shared price, date and currency bases.
- Lead partial conclusions with their strongest supported finding. Show whether a source is unavailable, lacks coverage or needs a listing choice.

## 2026-11-16 - Hosted AWS and market data readiness

- Recover literal tickers for evidence when model intake is unavailable, while keeping the lack of a reviewed conclusion visible.
- Preserve explicit tickers and add dated fund and security disclosures for the three examples. Show successful Bedrock Converse responses alongside the evidence.
- Support a private, digest-pinned S3 snapshot for deployment and disable the external price adapter by default.

## 2026-11-16 - Case-based customer examples and submission documentation

- Rewrite the three sidebar questions around the official growth and diversification, growth and ESG, and retirement risk cases. Each is editable question text and uses the standard research flow.
- Align the README, setup documentation, demo script and submission package with the current interface and documented coverage limits.

## 2026-11-16 - Direct, evidence-bounded research conclusions

- Require a concise answer to the actual investment question before supporting figures or missing-information details; cap the expanded main answer at 80 words and version the customer contract as v4.
- Distinguish factual accuracy from decision relevance in independent review; a metric summary cannot replace the practical implication of stated conditions.
- Keep factual/comparison questions within their requested scope and preserve conditional judgments, uncertainty and numerical verification.

## 2026-11-16 - Reconcile stashed data changes with the current customer interface

- Resolve stash-restore conflicts while retaining conclusion-first rendering, review reserves and current customer tests.
- Preserve archive-first research and traceable source hashes without restoring obsolete homepage controls.
- Use raw archive close for share sizing and adjusted close for historical performance; withhold sizing when raw close is missing.
- Keep archive price precedence after name resolution and include fallback coverage metadata in the asset fingerprint.
- Pass 80 targeted fixture tests and compile the application and test modules.

## 2026-11-16 - Customer assessment layout and completion reliability

- Replace promotional headlines with a functional investment-research entry point and put the released conclusion first on the result page.
- Increase text size and contrast, use a consistent sans-serif hierarchy, and keep optional context and example questions in the customer workflow.
- Render reviewed supporting and opposing findings only when present; show checked evidence when a written assessment is unavailable.
- Reserve time and model calls for conclusion review, and give actionable reference and numeric-format repair feedback. Request Python fact quotations instead of model-retyped calculated quantities.
- Preserve independent numerical checks, semantic review and withheld unsupported conclusions.

## 2026-11-16 - Repository finalization and customer-only entry point

- Remove preset question buttons and Reference cases navigation from the customer app.
- Preserve development and historical validation in the separate `validation_app.py` entry point.
- Rewrite the README, running guide, current technical documentation and submission index; regenerate the one-page and technical PDFs.
- Retain version-qualified model failures and label the earlier video and visual artifacts as historical.
- Pin directly imported dependencies and add credential-free GitHub regression checks.
- Record current full-data validation and release packaging in `submission/final-verification.md`.

## 2026-11-16 — Task completion and argument support

- Connected task contracts and claim-level semantic review to the customer workflow.
- Allowed evidence retrieval after review rejection, with explicit time/call/retry limits and cached results.
- Added versioned conversation corrections/retractions and traceable security candidates.
- Separated complete, partial and evidence-only results in the page and exports.
- Added code-authored adversarial coverage and an opt-in frozen-data before/after runner.
- See `ANALYSIS_REQUIREMENTS_2209.md` and `submission/analysis-validation-2209.md` for evidence and limitations.

## 2026-11-16 · Contextual inquiry and conclusion-first reporting

- Replace online report sorting with model-selected analysis questions, bounded follow-up evidence tools, synthesis and a separate answer review.
- Pass the full current question and optional details to all reasoning stages. Keep unknowns, conflicts and explicit numerical rules visible without imposing a preset conclusion.
- Place the reviewed conclusion, supporting evidence, counterevidence and gaps above the report's context, metrics and charts. Every section links to user statements and checked evidence.
- Check numeric quotations against cited Python results; withhold an answer that fails independent review after a bounded repair.
- Add unseen name, paraphrase, irrelevant-detail and material-context acceptance cases. See `submission/reasoning-validation.md` for observed results and runtime failures found during validation.

## 2026-11-16 · General conversational investment research

- Replace the default professional workflow chooser with a plain-language customer journey and optional profile details. Keep official personas as test fixtures only.
- Connect public price history, Bank of Canada FX/CPI, independent calculations, withdrawal replay and dated bond disclosures to a report with charts.
- Add generic evidence-linked Bedrock intake, report interpretation and separate explanation review, with transparent checked-evidence fallback.
- Preserve conflicts, missing evidence, source dates and unassessed risks. Add HTML exports and updated current product documentation.
- See `submission/customer-validation.md` for 522-test acceptance, live custom-profile/bond runs and remaining limitations.

## 2026-11-15 · Complete the shared historical decision workflow

- Route Compare, Evaluate and Audit through one editable confirmation, dated evidence, independent replay and publication pipeline. Keep English deliverables while accepting English and French model drafts.
- Add multiple-source rational funding optimization with independently checked certificates, separate search authorization, and a bounded one-assumption challenge that preserves the original decision.
- Check recovery, rolling windows, CAD conversion, historical paths, exposure intervals, rule verdicts and report integrity independently. Unknown binding rules remain unknown; candidate labels cannot change their applicability.
- Present explanation-first and metrics-first views, verified charts, JSON and PDF exports, constrained Bedrock statement composition and optional versioned S3 storage.
- Withdraw invalid model prose, block tampered figures before display, distinguish source coverage from interval uncertainty, and keep unsupported solver constraints unassessed.
- Add a general CLI, safe runtime diagnostics, fictional persona inputs, updated English submission PDFs and an explicit target-architecture status matrix. See `submission/verification.md` for current acceptance and remaining limits.

## 2026-11-15 · Verify Bedrock intake and preserve grounded analysis

- Allow a second Bedrock request when the first tool call does not produce a checked question handoff. Retain the 12-second deadline and existing token budget. A valid handoff finishes the stage immediately.
- Clarify the difference between comparing two assets or portfolios and evaluating one portfolio with explicit weights. Preserve a locally grounded comparison when the classification differs, and surface the disagreement in the assistant.
- Keep the default Sonnet interpretation model after the Nova 2 Lite intake experiment missed the single-allocation handoff and mislabeled the audit. Record the trial and the competition CloudShell checks in the [verification record](submission/verification.md#competition-aws-acceptance).

## 2026-11-15 · Streamline the investment assistant interface

- Put one question composer and three reusable examples on the home screen. Group model settings and manual entry behind explicit controls.
- Bring the decision and verified figures forward. Fold reviewed inputs, detailed evidence, and audit rules into expandable sections.
- Use a responsive layout and keep an explicit action to start a new question and clear the previous result.

## 2026-11-15 · Assess one weighted portfolio and ground balance currency

- Read a single proposed allocation from the question and review its historical metrics using the same valuation and independent verification as the comparison workflow.
- Identify benchmark concentration from issuer disclosures. Show missing prices and require explicit approval for documented, same-benchmark illustrative substitutes. Keep the requested and replayed weights in the audit record.
- Ground inline and separate balance-currency declarations. Flag conflicting balances and keep percentage replays available independently of the balance.

## 2026-11-15 · Recover trade drafts when Bedrock is unavailable

- Open an editable, source-grounded offline draft for a trade entered through the assistant. Require review of the full request and confirmation before replay.
- Report AWS credential, permission, network, and service failures separately. Continue offline with the submitted text after a failed cloud interpretation.
- Default direct-entry audits to offline execution. Keep live Bedrock execution and alternative funding search explicitly authorized.

## 2026-11-15 · Rebuild question intake and require English input

- Route the full question to planning, grounded historical comparison, trade audit, or a scope explanation. Planning can answer before accessing market files.
- Offer one bounded Strands/Bedrock classification per explicitly authorized question. Model suggestions contain original clause references. Local checks preserve ownership, excluded choices, and unconfirmed conditions.
- Use an offline language check for user-facing questions and follow-ups. Keep text, tool selection, historical computation, and user confirmation distinct.
- Exercise 141 reproducible intake scenarios, English submission checks, and the Streamlit planning-to-data path. See the [verification record](submission/verification.md#question-intake-verification).

## 2026-11-15 · Respond to concentration and high-return claims

- Interpret open-ended first-person and guarantee questions about investing. Keep the stated savings balance, beginner context, interest in a concentrated position, and return claim available in the response.
- Explain individual stocks, cryptoassets, options, and high guaranteed returns using public investor-education sources.
- Offer an independently verified NVDA and BTC-USD example when both are mentioned. Keep the two historical series unranked.

## 2026-11-15 · Answer open-ended investment planning questions

- Recognize stated balances, spending needs, inflation concerns, and risk concerns in a planning question. Ask about missing timing or cash needs while offering relevant educational information and sources.
- Describe savings, equity fund, and gold trade-offs when the question raises them. Keep the currency, available investment amount, and risk limit open until stated.
- Offer a separate, unranked historical example for S&P 500 and gold exposure using SPY and GLD.

## 2026-11-15 · Ground comparisons in the investor's question

- Extract supported assets or weighted allocations, limits, historical measures, and stated context from the question. Show the interpreted request for confirmation before running it.
- Show an unranked comparison when the investor leaves the priority open. Flag ambiguous or unsupported constraints without substituting a manual form.
- Use Bedrock to locate original clauses when the local interpreter needs help. Check every extracted value in the typed source before offering it.
- Keep manual input available from the empty question and record the origin of inputs in the reviewed report.

## 2026-11-15 · Profile-first investment decision assistant

- Lead with an investor question, a task choice, and an explicit fictional profile. Keep reference cases in a separate workspace.
- Use a bounded Bedrock tool to propose the analysis task. Require the investor to confirm the task, inputs, and applicable rules before running it.
- Compare two assets or two user-defined allocations using common CAD trading dates. Independently recompute the historical results and verify the raw close and FX inputs before displaying them or exporting JSON.
- Explain how objectives, withdrawal timing, and risk willingness inform the suggested comparison measure. Apply explicit drawdown limits before evaluating the confirmed priority. Keep missing mandatory ESG evidence unresolved.
- Retain the trade audit, separate authorization for the funding search, and independently reviewed follow-up checks.
- Pass 243 regressions on macOS and competition CloudShell. Exercise the comparison and the proposed-trade audit from the new Streamlit entry point with real Bedrock calls. [Verification](submission/verification.md#profile-first-assistant-verification)

## 2026-11-15 · Portfolio decision audit workspace

- Add a Streamlit workspace for reference cases and custom requests, with a market-bundle status, a policy review card, and a separate funding search confirmation after the original audit.
- Organize published results into Decision, Evidence, and Agent activity. Show the publication status and the verification coverage of each section.
- Chart independently verified terminal loss and maximum drawdown by historical window. Use the same public projection for the chart, other displays, and the JSON download.
- Keep the original audit available during one-rule comparisons and reviewed follow-up checks.
- Verify 231 local regression tests and six offline CLI cases with the official starter. Check the original audit, separate funding authorization, and evidence display in Chrome, including a 390-pixel layout.

## 2026-11-15 · Configurable models and bounded tool recovery

- Read separate Bedrock model settings for Profile and the audit from the application environment.
- Ground explicitly qualified purchase quantities in English and French while retaining clarification for ambiguous amounts and incompatible units.
- Resolve a rejected Evidence or Scenario route using the confirmed arguments in the same stage. Hold unavailable market evidence immediately and require the checked Review handoff for publication.
- Add a paired benchmark with seed-generated inputs, custom manifests, and selectable model configurations. Report authorization, numerical agreement, model calls, and timing for both revisions.
- Verify 230 regressions on local macOS and competition CloudShell. The candidate passed 20/20 paired Bedrock checks with both model assignments and a custom Review manifest. [Verification record](submission/verification.md#generated-input-and-cross-model-verification)

## 2026-11-15 · Complete the risk reliability acceptance checks

- Bind free-text limits to the user's applicable clause, unit and rule. Request a correction or explicit entry when a binding amount cannot be verified, and record the origin of each confirmed input.
- Index published metrics by stable reference. Expose formula versions, units, denominators, evidence and review identity without duplicating financial values.
- Export the covered historical dates, documented exclusions, missing observations and consecutive gaps. Separate formula verification, historical scope and unanswered future risk questions.
- Derive the ZST.TO non-equity lower bound from disclosed fair value and NAV with a conservative display-precision adjustment. Leave unsupported exposure unmapped.
- Add independently expected path, scale, signed-contribution and strict-threshold cases, plus intake, provenance and coverage regressions.
- Verified 219 regression tests and six offline CLI cases on both local macOS and competition CloudShell. Eleven live Bedrock checks passed. [Verification record](submission/verification.md#risk-reliability-completion-on-local-and-competition-aws)
- [Risk model reliability implementation](RISK_RELIABILITY_IMPLEMENTATION.md) lists each proposed change, its implementation status, and the supporting acceptance evidence.
- Align the README setup, interactive CLI walkthrough, and result links with the verified application.

## 2026-11-15 · Formula-based risk and verified publication

- Limit model roles to interpreting requests and selecting allowed tools or follow-up checks. Generate public risk numbers, rule verdicts and explanations in Python.
- Rebuild CAD valuations from frozen adjusted closes and same-date exchange rates during Review. Record data fingerprints, method versions and the covered dates.
- Independently recompute sector and issuer exposure changes. Display each section's verification status and preserve the verified main audit when an optional section fails.
- Bind conclusions to their reviewed inputs. Reject altered or mismatched snapshots and apply the same publication checks to Streamlit, CLI reports and counterfactuals.
- Refresh the Streamlit data cache when the source changes and require a new audit before reusing a result or authorizing a search.
- Verified with the official ZIP using 195 local regression tests and six offline CLI scenarios. Tests included incorrect exchange-rate conversion, injected model commentary, tampered exposure values and outdated review data.

## 2026-11-14 · User-authorized audits and checked publication

- Audit the submitted trade first, including in Streamlit reference cases. Preparing search inputs never starts the search. Run the funding solver after the original result and a separate user confirmation.
- Defer a smaller-size question until the full-size search and independent review establish that a positive smaller trade can help.
- Preserve unassessed binding terms and show them alongside checked results. A limited review stops at the original trade.
- Publish independently reviewed numbers, deterministic explanations and safe trace identifiers. Withhold injected or unverified conclusions.
- Support optional equity-sector comparisons with dated evidence and shared uncertainty before and after the proposed trade. Keep sector caps outside the funding solver until they have independent verification.

## 2026-11-14 · Evidence integrity and bounded execution

- Check each archived replay calendar in both the funding solver and independent review. Withhold a funding result when expected trading sessions are missing.
- Screen drawdown inequalities that hold throughout the purchase domain. Preserve independently checked boundaries and date-pair witnesses.
- Ground clearly stated English and French purchase sizes in the original request. Keep confirmation and ambiguity checks before the audit.
- Re-audit reviewed issuer disclosures under the original policy using a digest-pinned catalog. Keep incomplete or stale evidence unresolved.
- Confirm custom starting weights and run a fixed additional 2023 replay. Record investor objective and withdrawal timing separately from binding limits.
- Bound time, HTTP attempts and observed model usage across each action. Add matched failure-recovery and controller-load benchmarks. [Results and reproduction](submission/verification.md)

## 2026-11-14 · Competition package

- Freeze the verified application revision and add the demo, judge one-pager, technical summary and sanitized Bedrock evidence.
- Preserve clearer portfolio-point wording in Profile. Record separate original, mixed and quote-focused intake results, including unexpected clarification requests.
- Reproduce the reference cases and full test suite from a clean checkout. [Verification and reproduction](submission/verification.md)

## 2026-11-14 · Verified funding examples and decision boundaries

- Recover fully explicit NVDA purchase size and single-source funding in supported wording and keep the user's confirmation step.
- Recompute signed per-asset drawdown contributions independently and show a concrete verified funding example for eligible requests without a stated funding preference.
- Accept a user-confirmed, tighter ZST.TO reserve floor or disclosure freshness age in a one-field replay. Test the underlying thresholds with an expanded official-data cohort and an independent missing-FX case.

## 2026-11-14 · Agent collaboration and one-rule decision checks

- Settle parallel work before returning the audit. Keep accepted tool results when model commentary fails. Release still requires independent review.
- Shorten live tool-driven stages and record the time from confirmed policy to independent review.
- Make draft policy fields editable before confirmation. Show the source wording when available and guard unresolved or unsupported binding terms.
- Add a bounded Review check with a separately verified result or a specific disclosure request. Match fixed, bundled and staged workflows in a held-out challenge benchmark.
- Record each implementation and validation milestone in the [agent iteration log](AGENT_ITERATION.md).

## 2026-11-14 · Architecture benchmark

- Added a reproducible benchmark with confirmed-policy cases and a separate free-text intake cohort. The deterministic, bundled single-agent and multi-agent arms share the frozen sources, portfolio tools and independent release checks.
- Record audit agreement, false releases, avoidable holds, intake accuracy, latency, actual Bedrock usage and role/tool completion. [Benchmark report](BENCHMARK.md) · [Implementation record](https://github.com/WindsTrace/datathon-prep/issues/4)

## 2026-11-14 · Evidence coverage and decision reasons

- Validate dated issuer disclosures against their observation date, publication cutoff and a configurable prototype freshness limit. The independent review repeats the check against the raw snapshot. Record and explain excluded holdings, covered portfolio weight and possible exposure ranges.
- Distinguish a breached starting portfolio with no feasible change from an infeasible required purchase size and unresolved evidence. Keep verified historical metrics available when only ETF holdings are incomplete. Withhold funding results for missing or unusable price or FX inputs.
- Show source and retrieval details for the historic market inputs. Display recorded rule status and the size of a breach, including breaches that round to less than 0.01 percentage points. [Implementation record](https://github.com/WindsTrace/datathon-prep/issues/3)

## 2026-11-14 · Policy-driven tool calls

- Evidence now chooses the market sources and, when an issuer cap applies, the available holdings disclosures and their as-of date. Only that branch runs the Exposure role. Unavailable holdings stay unknown.
- Scenario chooses the confirmed risk metric or reports both if the request has no historical loss cap. Both original stress windows and both independent risk calculations remain available for every completed audit.
- Python validates the chosen arguments and visibly records a deterministic fallback if a routed model cannot complete the required handoff. The results screen and JSON record expose tool choices, rejected fields and skipped stages. The independent review still controls which results are released. [Implementation record](https://github.com/WindsTrace/datathon-prep/issues/2)

## 2026-11-14 · Decision audit screen

- Added a Streamlit simulation that compares the starting portfolio, original proposal and reviewed outcome. It shows the tested constraints, applicable evidence and review findings, with a downloadable run record.
- Added Robert comparisons that change only the loss definition, the ZST.TO floor or permission for a smaller purchase. The Amira case displays the known issuer exposure separately from unresolved coverage.
- The live request path uses Strands and Amazon Bedrock for interpretation and requests confirmation before replay. The screen displays offline and live role events separately.
- Applied the workshop's deterministic checks and verified handoffs to the presentation of results. The UI reads the independent audit, explains unresolved decisions and uses recorded tool events as evidence. [Design and verification record](https://github.com/WindsTrace/datathon-prep/issues/1)

## 2026-11-14 · User-confirmed trade audit

- Added an interactive `--request` entry point for fictional NVDA purchases funded by QQQ or ZST.TO. The Strands profile agent extracts the original funding source, permitted funding sources, purchase size, explicit limits and permission to buy a smaller amount. It asks for clarification when needed and presents the interpreted inputs for confirmation before the audit runs.
- The solver and independent reviewer now distinguish an infeasible exact purchase from an infeasible funding range. A smaller diagnostic limit stays separate from eligible alternatives when the user requires the full amount.
- Tightened the six preset checks to require the observed verdicts. Robert's terminal-loss case also checks the independently verified funding boundary and feasible alternative. The drawdown case checks independent confirmation of infeasibility.
- Local verification passed 19 unit tests and all six official-data preset cases. The final competition CloudShell run passed the six presets and both interactive ZST.TO cases with Nova 2 Lite. One intermediate run over-asked for clarification on an already explicit terminal-loss limit. The final run verified that an ambiguous limit prompts a choice and that a supported explicit rule proceeds to confirmation.

With only ZST.TO available for funding, a 15% ZST.TO floor and a 14% terminal-loss limit, the 10-point request is infeasible. The 5-point purchase moves from diagnostic to eligible only after the user allows a smaller purchase.

For reproduction commands and an example request, see [Run it](README.md#run-it).
