# AlphaForge AI Risk Model Reliability Implementation

This crosswalk follows the November 15, 2026 Risk Model Reliability Change Specification. [`c8a90d4`][base] is the original review baseline. [`98661fe`][app-rev] is the application revision that passed acceptance. [`afe2036`][first-change] introduced the first publication safeguards. The [verification record][verification] contains the local and competition AWS results.

| Status | Meaning |
| --- | --- |
| Implemented | The change is part of the execution or publication flow for the current product scope. |
| Existing and verified | The baseline already supported the behavior. This update retained and checked it and added acceptance tests where needed. |
| Partially implemented | The supported portion is in place. The specification calls for broader coverage. |
| Separate design | The specification treats this as a separate feature or future work. |

## 1. Responsibility for numerical values and calculations

| Specification item | Status | Implementation |
| --- | --- | --- |
| §1 and §3 Separate model decisions from numerical results | Implemented | Profile interprets and clarifies input. Evidence, Scenario, Exposure, Alternatives, and Review invoke approved tools at their respective stages. The model can select a supported follow-up check. Python uses frozen data and confirmed inputs to derive values, evaluate constraints, and generate published explanations. The optional model-generated explanation path was removed. [Agent roles][agents] · [Workflow][workflow] · [Publication][publication] |
| §3 Sources for prices, FX, holdings, and sector classifications | Implemented | The workflow freezes the official price and FX CSV files and records their fingerprints and source metadata. Holdings disclosures are screened for observation date, availability date, and freshness. Sector evidence retains its taxonomy, version, denominator, and source location. Missing evidence remains unknown. Reports distinguish evidence sufficiency from calculation verification. [Market data][data] · [Issuer evidence][issuer-evidence] · [Sector evidence][sector-evidence] |
| §3 User-supplied values and assumptions | Implemented | Free-text intake matches the amount, unit, and constraint to the user's wording. A unique, explicit value in a supported form can be recovered from the request. Unverified fields require clarification or direct entry and block the limited-scope shortcut. The report records the confirmed value, source type, and excerpt fingerprint. Users can review source excerpts in the input interface. Buy-and-hold assumptions and the treatment of fees, taxes, and intraday movements are documented separately. [Numeric grounding][profile-numbers] · [Policy validation][workflow] · [Scope notes][publication] |
| §4.1 Currency conversion | Implemented | USD adjusted closes are multiplied by the same-day FX rate in CAD per USD. CAD quotes are used directly. Review independently rebuilds the sequence from frozen source fields with Decimal arithmetic and checks for inverted rates, incorrect dates, and duplicate conversions. The data provider controls the upstream price adjustment methodology. [Loading and verification][data] |
| §4.2 Buy-and-hold path | Existing and verified | The portfolio path uses initial weights and CAD prices relative to each asset's opening price. Weights drift with price changes. The simulation uses adjusted closes and excludes fees, taxes, and intraday movements. Acceptance includes known price paths, currency conversion, and scaling. [Formulas][finance] · [Independent recalculation][governance] · [Formula tests][formula-tests] |
| §4.3 Terminal return and loss | Existing and verified | The report retains signed terminal return and nonnegative terminal loss. The profitable-path fixture preserves a 20% return, zero terminal loss, and the drawdown within the window. [Formula tests][formula-tests] |
| §4.4 Maximum drawdown and peak and trough dates | Existing and verified | Maximum drawdown is computed from portfolio net asset value and its running peak. The report retains the portfolio's peak and trough dates. Removing prices or FX on the actual trough date of a reference window leaves that window with insufficient evidence. [Formula tests][formula-tests] · [Calendar tests][calendar-tests] |
| §4.5 and §4.6 Return and drawdown contributions | Existing and verified | Independent recalculation preserves signed return contributions and drawdown contributions over each portfolio's own peak-to-trough interval. Tests cover contributions summing to the total, negative contributions, and different peak and trough dates before and after a trade. The report retains the dates for interpretation. [Independent recalculation][governance] · [Formula tests][formula-tests] |
| §4.7 Issuer and sector exposure | Implemented | Exposure bounds use portfolio weights and eligible evidence. Sector weights reported within the equity sleeve are converted to fund NAV. The before-and-after comparison shares the same unknown coefficients, so an unchanged holding's unknown contribution cancels. Each sector's interval is a separate bound. [Sector calculations][sector] · [Independent exposure review][exposure-review] · [Exposure tests][exposure-tests] |
| §4.8 Feasible region, precision, and tolerance | Partially implemented | The workflow uses the existing two-source solver and independently checks its feasibility boundary. Verdicts use full precision and display values are rounded. A regression verifies that a breach still fails when both displayed values round to 14.00%. Existing tests compare screening against the full constraint set. Numerical tolerances are defined in the relevant calculations. A unified per-metric tolerance register and public export remain pending. [Solver][finance] · [Review rules][governance] · [Boundary tests][boundary-tests] |
| §4.8 Descriptive sector analysis and sector limits | Existing and verified | Sector analysis publishes exposure bounds, changes, and coverage. A binding sector limit is recorded as unassessed and requires explicit confirmation of a limited audit. The solver can assess issuer exposure limits when the applicable policy and evidence are available. [Requirement status][requirements] · [Sector scope][sector-evidence] |
| §1 and §6 New estimation methods | Separate design | VaR, Expected Shortfall, market regime models, and ML training require separate definitions, data windows, and validation methods. The current results apply to the specified historical paths. [Product scope][readme] |

## 2. P0 and P1 implementation status

| Proposed improvement | Status | Implementation | Evidence |
| --- | --- | --- | --- |
| **P0-1 Independently verify supplemental figures** | Implemented | Review independently recalculates sector and issuer exposure changes. It checks classification, denominator, eligible dates, bounds, unknown share, changes under shared uncertainty, and sources. The publication layer releases verified results for each section. If a supplemental section has insufficient evidence or has been altered, the system withholds its figures and retains the verified core report. | [Workflow][workflow] · [Exposure review][exposure-review] · [Publication isolation tests][publication-tests] |
| **P0-2 Reference verified figures in published results and explanations** | Implemented | Public derived values have stable metric IDs and a `value_ref` pointing to the verified value in the same public report. Intake distinguishes wording grounded in the request from manual entry. Deterministic templates generate explanations and comparison directions. Rule calculations produce breach margins and remaining headroom. Missing and invalid references fail to resolve to a publishable number. A future free-form explanation feature would require a separate verification stage for generated text. | [Metric index][metric-records] · [Evidence interface][audit-view] · [Metric tests][metric-tests] |
| **P0-3 Independently reproduce CAD valuations from source records** | Implemented | Review receives the underlying prices, quote currency, rates, dates, and source records. It independently rebuilds the CAD prices and compares them against the calculation inputs. The checks cover duplicates, nonpositive or nonfinite prices, incorrect dates, inverted rates, and duplicate conversion. The report retains diagnostics when critical observations are missing. | [Currency verification][data] · [Market provenance tests][provenance-tests] · [Workflow boundary tests][financial-tests] |
| **P0-4 Freeze results and bind them to input versions** | Implemented | The immutable review snapshot binds input fingerprints, confirmed rules, formula versions, the review ID, and supplemental sections. Mismatched figures, rules, and review records invalidate publication of the affected report or follow-up. Streamlit discards old results and related authorizations when it detects a change in market data. Replacing an external holdings or sector catalog requires a fresh audit. Archived reports retain the snapshot they reviewed. | [Snapshots and versions][snapshot] · [Application cache boundary][app] · [Tamper tests][publication-tests] |
| **P1-1 Standardize records for published metrics** | Implemented | The index covers risk, contributions, exposure, funding boundaries, rule margins, and counterfactual results. It records method and version, unit, denominator, historical window or observation date, evidence, input fingerprint, assumptions, verification status, and review ID. The interface lets users inspect a selected metric. JSON uses the same index. Raw disclosure amounts and runtime telemetry retain their own provenance. | [Record contract][metric-records] · [Coverage tests][metric-tests] |
| **P1-2 Verify trading dates and observation coverage** | Partially implemented | The three official windows are checked against independent archived calendars. Reports include expected and actual observation counts, closures and known FX exclusions, reasons for unexpected gaps, and consecutive missing sessions. Missing critical dates in an official window withhold drawdown and solver results. Unregistered windows are marked `coverage_not_verified`. Independent calendars for additional markets and arbitrary date ranges remain pending. | [Trading calendars][calendar] · [Market data][data] · [Calendar tests][calendar-tests] |
| **P1-3 Derive a reproducible conservative lower bound** | Implemented | ZST.TO uses BMO's June 30, 2026 disclosures. The financial statements list non-equity investment fair value of 4,144,027 and net assets of 4,158,550, both in thousands of CAD. Allowing one reported unit on each side gives `(4,144,027 − 1) / (4,158,550 + 1)`, a lower bound of approximately 99.65%. For the same 10-percentage-point shift from ZST.TO to NVDA, the estimated increase in Information Technology exposure narrowed from approximately 8.37–10.00 to 9.97–10.00 percentage points. The export includes the amounts, unit, currency, and formula. Legacy catalog bounds without supporting amounts are treated as unmapped exposure. [Financial statements and page references][sector-evidence] | [Primary calculation][sector] · [Independent recalculation][exposure-review] · [Sector tests][sector-tests] |
| **P1-4 Separate calculation validity from future risk** | Implemented | The `scope_notes` field separates calculation verification, the scope of CAD buy-and-hold simulations, and open questions about future risk. Future loss probability, potential future loss size, and behavior on untested price paths remain open. | [Scope and publication fields][publication] · [Calculation methodology interface][audit-view] |

## 3. Agent workflow after the changes

| Stage | Current behavior |
| --- | --- |
| Profile and user confirmation | Supported figures are grounded in the request. Ambiguity, conflicts, or insufficient grounding trigger focused clarification or direct entry. The user confirms the rules to execute. User-supplied assumptions and market observations are recorded separately. |
| Evidence, Scenario, and Exposure | Evidence binds the supported source records, windows, and dates. Scenario and Exposure can run in parallel when both apply. Missing holdings or sector evidence yields uncertainty bounds with dated sources. |
| Original trade and Alternatives | The first audit evaluates the original trade independently. The funding solver and candidate review run after explicit authorization. The workflow can check the requested size first and ask for separate authorization if a smaller purchase is required. Follow-up checks retain the original search authorization. |
| Review and publication | Review invokes independent Python calculations. A correctly verified breach can be released. Supplemental sections have separate verification states, and unknown or unsupported rules are labeled. Verdicts use the confirmed limits and historical windows. Streamlit, CLI, and counterfactual exports share the same publication boundary. |

See the [application][app], [CLI][cli], [counterfactual workflow][counterfactual], and [requirement statuses][requirements].

## 4. Original acceptance matrix

| Original test | Verified coverage | Evidence |
| --- | --- | --- |
| 1 Known price path | 100 → 120 → 90 yields a 10% terminal loss and 25% maximum drawdown. | [Formula tests][formula-tests] |
| 2 Profitable price path | 100 → 90 → 120 yields a 20% terminal return, zero terminal loss, and 10% maximum drawdown. | [Formula tests][formula-tests] |
| 3 Constant prices and FX | Terminal return, terminal loss, and maximum drawdown are all zero. | [Formula tests][formula-tests] |
| 4 Constant price scaling | Scaling all asset prices by the same factor preserves risk percentages and contributions in the main calculation and Review. | [Formula tests][formula-tests] |
| 5 Currency conversion | Tests confirm same-day CAD conversion for USD quotes and original values for CAD quotes, and reject inverted or repeated conversions. The existing fixture varies both the USD quote and the FX rate. The specification's fixed-USD-price scenario has no dedicated fixture. | [Market provenance tests][provenance-tests] |
| 6 Contribution reconciliation | The sum of return contributions equals terminal return. The sum of drawdown contributions equals the portfolio's maximum drawdown. | [Formula tests][formula-tests] |
| 7 Signed contributions | An asset rising during the drawdown interval can have a negative contribution. Portfolios can have different peak and trough dates. | [Formula tests][formula-tests] |
| 8 Missing trading dates | Removing prices or FX on an actual trough date preserves the missing-data reason and blocks publication of the full result. Consecutive gaps are counted across expected trading sessions. | [Calendar tests][calendar-tests] |
| 9 Invalid inputs | Tests reject duplicate records, invalid formats, nonpositive prices, NaN, and infinity. | [Market provenance tests][provenance-tests] |
| 10 Incorrect denominator | A 20% fund position × 80% equity share × 40% sector share within equities yields 6.4%. Review rejects a result based on the wrong denominator. | [Exposure tests][exposure-tests] |
| 11 Unknown sector allocation | Unmapped shares remain unknown. This includes legacy lower bounds with insufficient supporting evidence. | [Sector tests][sector-tests] |
| 12 Shared unknown exposure | An unchanged holding's unknown coefficient cancels in the before-and-after difference. Tests cover both sector and issuer exposure. | [Sector tests][sector-tests] · [Exposure tests][exposure-tests] |
| 13 Sector tampering | A local test replaces a sector lower bound with 99% and verifies that publication withholds only that section. The AWS Amira check alters the ZST.TO disclosure bound and confirms the same behavior. | [Publication tests][publication-tests] · [AWS evidence][verification] |
| 14 Risk tampering | Review or the publication guard detects altered terminal loss, drawdown, or contributions. Tests also alter funding boundaries and numerical evidence supporting them. | [Governance tests][governance-tests] · [Publication tests][publication-tests] |
| 15 Model fabrication | CLI, JSON, and counterfactual tests inject claims of zero risk, guaranteed safety, or fictitious returns. Publication rejects the claims. Fabricated metric references fail to resolve to a value. | [CLI output tests][numeric-tests] · [Publication tests][publication-tests] · [Metric tests][metric-tests] |
| 16 Version mismatch | Tests verify that changed rules, evidence, figures, audit scope, and follow-up snapshots invalidate old reviews. Updating market data also revokes associated results and authorizations. | [Publication tests][publication-tests] · [Interface tests][app-tests] |
| 17 Alternatives not requested | Local offline and agent-based tests verify that both the solver and candidate boundary review are skipped. The live Robert audit and delegated Review retain the original search scope. | [Authorization tests][intent-tests] · [AWS evidence][verification] |
| 18 Generalization | Within the supported scope, tests cover Robert, Amira, custom weights, an additional fixed window, different sectors, and unknown evidence. Unsupported assets, rules, or windows trigger explicit limitations. End-to-end coverage for arbitrary new markets and assets remains outside the supported scope. | [Scope tests][scope-tests] · [Sector tests][sector-tests] · [AWS evidence][verification] |

## 5. Full verification and reproduction

| Verification | Observed result |
| --- | --- |
| Local macOS, Python 3.10, full official dataset | 219/219 full regression tests and 6/6 offline CLI cases |
| Competition AWS CloudShell `us-east-1`, Python 3.13, full official dataset | 219/219 full regression tests and 6/6 offline CLI cases |
| Live Bedrock execution at the same application revision | 11/11 checks, including six CLI cases and five supplemental checks. All 36 successful Converse HTTP 200 responses had AWS request IDs. |

The supplemental checks cover English and French numeric grounding, original-trade auditing with metric references, a publication block for altered sector evidence, and a delegated counterfactual review. For fixtures that intentionally breach constraints, lack evidence, or include tampering, tests pass when the system identifies or blocks the result as expected. The verification record includes redacted request ID fingerprints. [Verification record and reproduction commands][verification]

[base]: https://github.com/WindsTrace/datathon-prep/commit/c8a90d4e607c86ff60f36b86307ff92e6f85d232
[first-change]: https://github.com/WindsTrace/datathon-prep/commit/afe2036c79ed87865bac885c6f3024bb018a2ecb
[app-rev]: https://github.com/WindsTrace/datathon-prep/commit/98661fe71f880139d51d2361624193adc8db7c82
[verification]: https://github.com/WindsTrace/datathon-prep/blob/b19e00f706eacb16ea319e109286bf61ed94fe2c/submission/verification.md#risk-reliability-completion-on-local-and-competition-aws
[readme]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/README.md#data-and-scope
[agents]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/agents.py
[app]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/app.py
[cli]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/__main__.py
[workflow]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/workflow.py
[profile-numbers]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/profile_numbers.py
[finance]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/finance.py
[governance]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/governance.py
[data]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/data.py
[calendar]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/market_calendar.py
[issuer-evidence]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/evidence.py
[sector-evidence]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/SECTOR_EVIDENCE.md
[sector]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/sector.py
[exposure-review]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/exposure_review.py
[snapshot]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/review_snapshot.py
[publication]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/publication.py
[metric-records]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/metric_records.py
[audit-view]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/audit_view.py
[requirements]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/requirement_status.py
[counterfactual]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/counterfactual.py
[app-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_app.py
[boundary-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_drawdown_constraints.py
[calendar-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_market_calendar.py
[exposure-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_exposure_review.py
[financial-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_financial_boundary.py
[formula-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_formula_acceptance.py
[governance-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_governance.py
[intent-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_audit_intent.py
[metric-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_metric_records.py
[numeric-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_numeric_output.py
[provenance-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_market_provenance.py
[publication-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_publication.py
[scope-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_scope.py
[sector-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_sector.py
