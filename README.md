# AlphaForge AI · Portfolio Decision Audit

PolyFinances Datathon 2026 · Banque Nationale · AWS

AlphaForge AI shows how the funding source for a proposed trade changes a portfolio's risk and its fit with an investor's stated constraints. The prototype compares the original portfolio, the requested trade and feasible alternatives. It reports which rule drove the decision and which conclusions still depend on missing evidence.

[Quick start](#run-it) · [Latest local and AWS verification](submission/verification.md#risk-reliability-completion-on-local-and-competition-aws) · [Risk model reliability implementation](RISK_RELIABILITY_IMPLEMENTATION.md)

## Choose the scope of the audit

- **Original proposal.** Streamlit and interactive CLI requests first return an independently reviewed result for the submitted trade.
- **Alternative funding.** Prepare the search settings, then authorize search separately after seeing the original result. The search checks whether an authorized funding mix can support the full requested purchase. When a positive smaller purchase may help, the application asks before expanding an undecided size scope.
- **Limited review.** When a binding condition is unsupported, the investor can confirm a review of the supported parts of the original proposal. The report records which condition remains unassessed and limits the conclusion to the work performed.

Independent numerical review applies to all three scopes. The published report distinguishes completed checks, proven violations, unresolved evidence, and steps skipped outside the confirmed scope.

Select **Include equity sector analysis** to describe the potential change based on the approved GICS sector evidence. The view shows unmapped weight and the effect of using the same unknown holdings on both sides of the transaction. [Sector evidence and limitations](SECTOR_EVIDENCE.md)

The command-line demo uses a fictional CAD portfolio holding 35% SPY, 25% XIU.TO, 20% QQQ and 20% ZST.TO. The presets add **10 percentage points of NVDA**. In an interactive AWS request, `--search-alternatives` enables a separate confirmation prompt after the original audit. Enter `SEARCH` to authorize the solver within confirmed funding and size limits. [Changelog](CHANGELOG.md)

## Competition package

[Release verification](submission/verification.md) · [One-page summary](submission/one-pager.pdf) · [Technical summary](submission/technical-summary.pdf) · [Demo video recorded at `13ccc42`](submission/alphaforge-demo.mp4) · [Demo visuals](submission/visual-handout.pdf)

Application revision [`98661fe`](https://github.com/WindsTrace/datathon-prep/commit/98661fe71f880139d51d2361624193adc8db7c82) passed 219 regression tests on local macOS and the same 219 tests on competition AWS CloudShell. Both environments passed all six offline CLI cases. The competition account also passed 11 live Bedrock checks with 36 successful Converse responses. The [verification record](submission/verification.md#risk-reliability-completion-on-local-and-competition-aws) identifies the evidence and reproduction steps for each revision.

## What the prototype found

| Preset or test | Verified outcome |
| --- | --- |
| **Robert · 14% terminal-loss limit** | Selling 10 points of ZST.TO left 10% in the fund, below Robert's 15% minimum, and produced a 16.15% terminal loss in the 2022 replay. Keeping the full NVDA purchase allowed **0 to 2.63 percentage points** of funding from ZST.TO, with the rest from QQQ. The upper boundary leaves essentially zero headroom under the loss limit. |
| **Robert · 14% maximum-drawdown limit** | The starting portfolio had a **16.05%** drawdown in the 2022 replay. The audit verified that the permitted funding range, including zero purchase, has no solution under the two-window policy. |
| **Amira · 14% NVIDIA issuer cap** | Funding the full trade from ZST.TO gave **at least 14.15%** NVIDIA exposure when direct and disclosed indirect holdings were combined. Funding from QQQ reduced the known lower bound to **13.39%**. Unresolved look-through coverage prevents confirming that alternative against the cap. |
| **Stress fixtures** | An ambiguous loss limit triggered clarification. Removing the QQQ disclosure left the concentration decision unresolved while historical replay still ran. An intentionally altered loss figure was caught by independent recalculation and blocked from publication. |

## Check what could change the decision

After the original audit, open **What could change this decision?**. Select a specific assumption or let Review use Bedrock to pick one supported check. You can describe what matters for that follow-up. The system can verify one alternate loss definition, reserve floor, size rule or disclosure freshness limit. It can also explain which holdings disclosures are needed or abstain.

- **Robert:** compare terminal loss and maximum drawdown while keeping the trade, prices, exchange rates and other policy fields fixed. The checked result shows which funding range disappears.
- **Amira:** ask what evidence could settle the issuer cap. For the QQQ-funded illustration, documented NVIDIA exposure is about 13.39%. The combined undisclosed contribution from XIU.TO and ZST.TO must be at most 0.60937 percentage points to meet the cap. If reviewed disclosures are available, select them and re-audit the same policy and market replay. The default illustration remains unresolved. [Reviewed disclosures](ISSUER_EVIDENCE.md)
- A hypothetical result stays separate from the original audited policy. Its export shows the selected change, accepted checks and before/after accounting. Review still controls publication of verified results.

For reserve and disclosure-age checks, you can set a tighter threshold explicitly. The replay verifies that only this field changed. **Historical risk drivers** shows the largest verified contributions for the proposal under the displayed risk metric. The audit independently checks one concrete eligible funding example, with the allowable range where meaningful. If you did not specify a funding preference, the example uses the least ZST.TO sale among tied largest eligible purchases and is labeled as an example.

The [iteration log](AGENT_ITERATION.md) connects the design, real AWS observations and limits. Run the expanded official-data challenge benchmark to compare fixed rules, bundled execution and staged checks with one re-audit per case. The missing-FX resilience case is reported separately.

```bash
python -m datathon.challenge_benchmark --cohort expanded --data "$DATA" --mode offline \
  --repeats 2 --report outputs/challenge-expanded.json
python -m datathon.resilience_benchmark --data "$DATA" --repeats 2 --report outputs/resilience.json
```


## Agents and their handoffs

| Agent | Its role in the decision |
| --- | --- |
| Profile | Extracts the proposed trade, funding sources, preferences and explicit constraints. Requests clarification when the loss metric is ambiguous. |
| Evidence | Selects the frozen CAD market inputs and adds a dated issuer disclosure snapshot when the confirmed request has an issuer cap. |
| Exposure | Measures direct and indirect NVIDIA exposure and bounds disclosure gaps for policies with an issuer cap. |
| Scenario | Coordinates the historical replay for the two required windows and the optional fixed 2023 window. Python retains terminal loss and drawdown for independent review. |
| Alternatives | Calls the funding solver to check feasible purchase sizes, funding mixes and binding limits. |
| Review | Calls independent Python checks for metrics, limits, funding and exposure, or selects a supported follow-up check when the user delegates that choice. |

The profile establishes the simulation rules before Evidence runs. Exposure, when required, runs alongside Scenario. Alternatives runs after separate search authorization. Review runs before publication. In AWS mode Strands on Amazon Bedrock interprets requests and selects typed tools and arguments. Python validates the evidence set, snapshot date, loss metric and windows. If either routed agent fails to produce a usable result, Python applies the confirmed policy and the report identifies the fallback. Use **Agent activity and AWS trace** to see accepted arguments, rejections, skipped roles and fallbacks. [Routing and verification](https://github.com/WindsTrace/datathon-prep/issues/2)

Python owns derived values, rule verdicts and published explanations. Free-text amounts are tied to the applicable source wording and units, or explicitly entered before confirmation. Review rebuilds CAD prices from frozen closes and same-date USD/CAD observations before verifying risk metrics. Sector and issuer exposure changes have their own independent checks and publication status.

Open **Metric values and provenance** to inspect the verified value, method, denominator and review identifier. Download the audit JSON for the same metric references and for the calendar coverage, missing observations and historical scope. Reported risk is conditional on the paths used in the audit.

## Data and scope

- **Historical stress.** The official starter's adjusted closes and USD/CAD series drive a buy-and-hold replay. The two reference windows are 2021-12-31 to 2022-12-30 and 2024-12-31 to 2025-04-08. Structured input can add a fixed 2023-07-31 to 2023-10-31 replay. The solver and independent review both check the archived joint trading calendar, including historically documented FX exclusions. Terminal loss compares start and end values. Maximum drawdown measures the largest peak-to-trough decline. [Official release](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)
- **Issuer exposure.** The SPY and QQQ SEC filings are dated 2026-06-30 and were filed on 2026-08-28. The reproducible competition reference and publication cutoff are 2026-11-14. The prototype accepts holdings observations at most 180 days old. The dated issuer check is separate from the two historical price replays. Stale, unavailable, invalid and assumption-only weights remain unknown. They widen the exposure range. The displayed coverage is the share of portfolio weight with direct or verified look-through evidence. [Evidence rules](datathon/evidence.py)
- **Current scope.** The CLI uses the demo portfolio. In Streamlit, **Write a request → Enter inputs directly** lets the user confirm custom weights for the five supported assets. The fictional objective and withdrawal timing can be recorded alongside explicit policy limits. The initial NVDA purchase is funded by a single sale of QQQ or ZST.TO. The replays use closing prices and omit execution costs, taxes and intraday movements.

The full starter inventory inventories the asset universe, adjusted prices, exchange rates, corporate actions, macro series and source metadata. It checks common replay dates, lists omitted FX dates and records the organizer's build notes.

```bash
python -m datathon.starter_quality --data "$DATA" --report outputs/starter-quality.json
```

Macro observations are inventoried for provenance and may have been revised. The investment audit uses adjusted closes with same-date FX, and keeps holdings disclosures and their dates separate. Corporate-action rows document the vendor's recorded splits and distributions. Adjusted replay prices already account for the vendor's treatment of those events.

## Run it

Use **Python 3.10+** and the organizer's `Datathon2026.zip` or extracted `alphaforge_starter/` folder. The full regression suite uses all six starter CSV tables. Keep the organizer data outside version control. From the repository root, use your Python 3.10+ executable in place of `python3` if your shell defaults to an earlier version.

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATA="/path/to/Datathon2026.zip"
export DATATHON_STARTER_PATH="$DATA"
export DATATHON_FULL_STARTER_PATH="$DATA"
```

### Decision audit screen

```bash
python -m streamlit run app.py
```

Open **Reference case**, select **Offline**, then choose **Robert · loss definition**. To reproduce the funding frontier, enable **Search alternative funding**, run the original audit and select **Confirm and search alternative funding**. The other Robert cases isolate the reserve floor and permission for a smaller purchase. **Amira · issuer exposure** shows a proven breach for the proposal and, if search is authorized, an unresolved alternative. Open **Metric values and provenance** or **Agent activity and AWS trace**, or download the JSON audit record.

Choose **Write a request → Enter inputs directly** and select **Offline** or **Bedrock** for structured intake. With competition AWS credentials, **Write a request → Interpret text with Bedrock** uses the competition's Sonnet 4.5 inference profile and shows the editable interpretation before confirmation. Numeric rules are grounded in the relevant request wording or explicitly entered. The staged audit and delegated Review selector use Nova 2 Lite. Reference cases in **Offline** mode use deterministic calculations and simulated role events. Reference cases in **Bedrock** mode use the displayed structured inputs and real downstream calls. Streamlit and CLI use the same Python solver and independent review.

### Command-line verification

```bash
python -m datathon --data "$DATA" --case all --mode offline --stress --report outputs/offline.json
python -m unittest discover -q
```

For live calls, use an authenticated competition AWS session. The pinned Strands SDK is `1.63.0` and the default model is Nova 2 Lite via `us.amazon.nova-2-lite-v1:0` in `us-east-1`.

```bash
python -m datathon --data "$DATA" --case all --mode aws --stress --report outputs/aws.json
python -m datathon.runtime_benchmark --data "$DATA" --mode aws --jobs 1 3 --repeats 2 \
  --report outputs/runtime.json
```

Use `--case robert` or `--case amira` to run one persona. Offline mode simulates role handoffs and runs the financial calculations locally. [Latest test results](submission/verification.md#risk-reliability-completion-on-local-and-competition-aws) · [Earlier reproduction and AWS notes](PROTOTYPE.md)

To try the interactive audit, start with a fictional request. Select `1` for terminal loss when the clarification menu appears, then type `YES` once the interpreted terms match your intent.

```bash
python -m datathon --data "$DATA" --mode aws --report outputs/request.json \
  --request 'Add exactly 10 percentage points of NVDA by selling only ZST.TO. Keep at least 15% in ZST.TO. A smaller purchase is not allowed. I can lose at most 14%.'
```

With the terminal-loss clarification, this original-only audit reports breaches of the 15% reserve floor and the 14% terminal-loss limit. To test alternative funding, specify the permitted sources in the request, pass `--search-alternatives`, and enter `SEARCH` after the original audit. If the requested size is infeasible and smaller size remains undecided, a separate prompt can authorize a smaller purchase. [Changelog](CHANGELOG.md)

## Repository map

| Path | Contents |
| --- | --- |
| [`app.py`](app.py) | Streamlit decision audit, confirmed policy comparison and JSON export |
| [`datathon/`](datathon/) | CLI, orchestration, Strands roles, data loader, financial solver and independent governance audit |
| [`tests/`](tests/) | Regression tests for data coverage, rule checks, bad metrics, funding and infeasibility evidence |
| [`BENCHMARK.md`](BENCHMARK.md) | Paired comparison of deterministic, bundled single-agent and multi-agent audits |
| [`RISK_RELIABILITY_IMPLEMENTATION.md`](RISK_RELIABILITY_IMPLEMENTATION.md) | Proposed safeguards, implementation status, and acceptance evidence |
| [`PROTOTYPE.md`](PROTOTYPE.md) | Detailed reproduction steps, stress test behavior and AWS handoff fix |
| [`Introduction-Datathon.executed.ipynb`](Introduction-Datathon.executed.ipynb) | Executed official AWS workshop notebook |
| [`Datathon_Research_Brief.md`](Datathon_Research_Brief.md), [`AGENTS.md`](AGENTS.md), [`plan.md`](plan.md) | Earlier research, competition context and prep notes |
