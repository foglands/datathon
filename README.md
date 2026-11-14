# AlphaForge AI · Portfolio Decision Audit

PolyFinances Datathon 2026 · Banque Nationale · AWS

AlphaForge AI shows how the funding source for a proposed trade changes a portfolio's risk and its fit with an investor's stated constraints. The prototype compares the original portfolio, the requested trade and feasible alternatives. It reports which rule drove the decision and which conclusions still depend on missing evidence.

The command-line demo uses a fictional CAD portfolio holding 35% SPY, 25% XIU.TO, 20% QQQ and 20% ZST.TO. The presets add **10 percentage points of NVDA**. An interactive AWS run accepts a new simulated NVDA purchase, confirms the proposed sale and constraints with the user, then searches within the confirmed funding sources and purchase-size rules. [Changelog](CHANGELOG.md)

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
- **Amira:** ask what evidence could settle the issuer cap. For the QQQ-funded illustration, documented NVIDIA exposure is about 13.39%. The combined undisclosed contribution from XIU.TO and ZST.TO must be at most 0.60937 percentage points to meet the cap. The illustration remains unresolved.
- A hypothetical result stays separate from the original audited policy. Its export shows the selected change, accepted checks and before/after accounting. Review still controls publication of verified results.

The [iteration log](AGENT_ITERATION.md) connects the design, real AWS observations and limits. The new benchmark compares a fixed rule, a bundled audit and staged audits with the same paths, review gate and one-replay budget.

## Seven agents and their handoffs

| Agent | Its role in the decision |
| --- | --- |
| Profile | Extracts the proposed trade, funding sources, preferences and explicit constraints. Requests clarification when the loss metric is ambiguous. |
| Evidence | Selects the frozen CAD market inputs and adds a dated issuer disclosure snapshot when the confirmed request has an issuer cap. |
| Exposure | Measures direct and indirect NVIDIA exposure and bounds disclosure gaps for policies with an issuer cap. |
| Scenario | Selects how to report historical loss from the confirmed policy. It uses both required windows, and Python retains terminal loss and drawdown for independent review. |
| Alternatives | Calls the funding solver to check feasible purchase sizes, funding mixes and binding limits. |
| Review | Calls an independent recomputation to verify candidate metrics, rules, feasible ranges and infeasibility evidence. |
| Explanation | Summarizes the audited results, funding trade-offs and remaining uncertainty with source references. |

The profile establishes the simulation rules before Evidence runs. Exposure, when required, runs alongside Scenario, followed by Alternatives, Review and Explanation. In AWS mode Strands on Amazon Bedrock selects typed tool arguments from the confirmed rules and the frozen catalog. Python validates the exact evidence set, snapshot date, loss metric and windows. If either routed agent fails to produce a usable result, Python applies the confirmed policy and the report identifies the fallback. An independent review is still required for a verdict. Use **Agent activity and AWS trace** to see accepted arguments, rejections, skipped roles and fallbacks. [Routing and verification](https://github.com/WindsTrace/datathon-prep/issues/2)

## Data and scope

- **Historical stress.** The official starter's adjusted closes and USD/CAD series drive a buy-and-hold replay on common dates. The windows are 2021-12-31 to 2022-12-30 and 2024-12-31 to 2025-04-08. Terminal loss compares the start and end values. Maximum drawdown measures the largest peak-to-trough decline within the window. [Official release](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)
- **Issuer exposure.** The SPY and QQQ SEC filings are dated 2026-06-30 and were filed on 2026-08-28. The reproducible competition reference and publication cutoff are 2026-11-14. The prototype accepts holdings observations at most 180 days old. The dated issuer check is separate from the two historical price replays. Stale, unavailable, invalid and assumption-only weights remain unknown. They widen the exposure range. The displayed coverage is the share of portfolio weight with direct or verified look-through evidence. [Evidence rules](datathon/evidence.py)
- **Current scope.** The CLI runs preset Robert and Amira scenarios and accepts new simulated NVDA requests against the demo portfolio. The initial purchase is funded by a single sale of QQQ or ZST.TO. The replays use closing prices and omit execution costs, taxes and intraday movements. The results describe the tested scenarios and support educational investment simulations.

## Run it

Use **Python 3.10+** and the organizer's `Datathon2026.zip` or extracted `alphaforge_starter/` folder. Set `DATA` to its local path. The organizer data stays outside version control.

### Decision audit screen

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATATHON_STARTER_PATH=/path/to/Datathon2026.zip
python -m streamlit run app.py
```

Open **Robert · loss definition**, confirm the inputs, then compare the change to maximum drawdown. The app replays both policies and shows the starting portfolio, proposed trade and verified outcome. The other Robert cases isolate the reserve floor and permission for a smaller purchase. **Amira · issuer exposure** shows a proven breach for the proposal and an alternative that remains unresolved. Expand the evidence and review section or download the JSON audit record to inspect the calculations and role events.

Enter the supported constraints directly to bypass language interpretation, then choose Bedrock or Offline for the audit. Optional free-text intake uses the competition's Sonnet 4.5 inference profile. The staged audit and Review selector use Nova 2 Lite. Free-text inputs are editable before confirmation. Source excerpts, when available, point to the wording the model used. Flagged unsupported binding conditions or contradictions require explicit resolution. Reference cases can run offline with deterministic calculations and simulated agent events. With competition AWS credentials, choose **Write a request** to have Bedrock interpret a fictional request, ask for a missing risk definition, and audit the confirmed inputs. Running a reference case in **Bedrock** mode uses its displayed structured inputs and calls the downstream agents live. Both routes use the same Python solver and independent review as the CLI.

### Command-line verification

```bash
python3.10 -m venv .venv
source .venv/bin/activate
DATA=/path/to/Datathon2026.zip
python -m datathon --data "$DATA" --case all --mode offline --stress --report outputs/offline.json
python -m unittest discover -s tests -v
```

For live calls, use an authenticated competition AWS session. The pinned Strands SDK is `1.63.0` and the default model is Nova 2 Lite via `us.amazon.nova-2-lite-v1:0` in `us-east-1`.

```bash
python -m pip install -r requirements.txt
python -m datathon --data "$DATA" --case all --mode aws --stress --report outputs/aws.json
```

Use `--case robert` or `--case amira` to run one persona. Offline mode simulates role handoffs and runs the financial calculations locally. The first validated release passed **6/6 offline scenarios, 6/6 live competition CloudShell scenarios and 11/11 governance tests**. The live suite recorded **62 successful Converse responses**. Complete seven-role runs took **10.3–12.7 seconds** in that run. [Reproduction and AWS notes](PROTOTYPE.md)

To try the interactive audit, start with a fictional request. Select `1` for terminal loss when the clarification menu appears, then type `YES` once the interpreted terms match your intent.

```bash
python -m datathon --data "$DATA" --mode aws --report outputs/request.json \
  --request 'Add exactly 10 percentage points of NVDA by selling only ZST.TO. Keep at least 15% in ZST.TO. A smaller purchase is not allowed. I can lose at most 14%.'
```

With the terminal-loss clarification, the full request is infeasible. The audit shows 5% of the portfolio as a diagnostic limit. Rerun with explicit permission for a smaller purchase to make that size eligible. [Changelog](CHANGELOG.md)

## Repository map

| Path | Contents |
| --- | --- |
| [`app.py`](app.py) | Streamlit decision audit, confirmed policy comparison and JSON export |
| [`datathon/`](datathon/) | CLI, orchestration, Strands roles, data loader, financial solver and independent governance audit |
| [`tests/`](tests/) | Regression tests for data coverage, rule checks, bad metrics, funding and infeasibility evidence |
| [`BENCHMARK.md`](BENCHMARK.md) | Paired comparison of deterministic, bundled single-agent and multi-agent audits |
| [`PROTOTYPE.md`](PROTOTYPE.md) | Detailed reproduction steps, stress test behavior and AWS handoff fix |
| [`Introduction-Datathon.executed.ipynb`](Introduction-Datathon.executed.ipynb) | Executed official AWS workshop notebook |
| [`Datathon_Research_Brief.md`](Datathon_Research_Brief.md), [`AGENTS.md`](AGENTS.md), [`plan.md`](plan.md) | Earlier research, competition context and prep notes |
