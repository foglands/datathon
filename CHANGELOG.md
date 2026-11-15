# Changelog

## 2026-11-15 · Complete the risk reliability acceptance checks

- Bind free-text limits to the user's applicable clause, unit and rule. Request a correction or explicit entry when a binding amount cannot be verified, and record the origin of each confirmed input.
- Index published metrics by stable reference. Expose formula versions, units, denominators, evidence and review identity without duplicating financial values.
- Export the covered historical dates, documented exclusions, missing observations and consecutive gaps. Separate formula verification, historical scope and unanswered future risk questions.
- Derive the ZST.TO non-equity lower bound from disclosed fair value and NAV with a conservative display-precision adjustment. Leave unsupported exposure unmapped.
- Add independently expected path, scale, signed-contribution and strict-threshold cases, plus intake, provenance and coverage regressions.
- Verified 219 regression tests and six offline CLI cases on both local macOS and competition CloudShell. Eleven live Bedrock checks passed. [Verification record](submission/verification.md#risk-reliability-completion-on-local-and-competition-aws)

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
