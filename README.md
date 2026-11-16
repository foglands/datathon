> Current reasoning update: the customer flow now plans analysis questions, selects evidence tools, can investigate follow-up gaps, synthesizes an answer and independently reviews its use of your conditions. The conclusion appears first. See [requested changes](REASONING_REQUIREMENTS.md), [workflow](CUSTOMER_RESEARCH.md) and [reasoning acceptance](submission/reasoning-validation.md).

> Current analysis-contract revision: [22.09 requirements and implementation](ANALYSIS_REQUIREMENTS_2209.md). Validation and remaining gaps: [revision validation](submission/analysis-validation-2209.md). Earlier acceptance records below describe their recorded revision, not a claim of current universal correctness.


> Generalization acceptance is partial: name and material-context comparisons passed; paraphrase and irrelevant-detail consistency remain open. Do not treat this revision as a fully validated customer advisory product.

# AlphaForge AI · Investment Decision Assistant

PolyFinances Datathon 2026 · Banque Nationale · AWS

Describe an investment idea and the conditions that matter. AlphaForge understands the question, retrieves dated public market evidence, runs relevant calculations, checks them independently, and returns an illustrated report with a reviewed model interpretation.

**A general investment-research conversation · Evidence before conclusions · Simulation only**

[Run locally](#run-locally) · [Technical documentation](submission/technical-summary.md) · [Architecture status](submission/architecture-status.md) · [Verification record](submission/verification.md) · [Recording script](submission/demo-script.md)

## Start with your own idea

The default **Investment assistant** is now a conversational research workspace. See [Current customer workflow, quantified risks and limits](CUSTOMER_RESEARCH.md).

Enter an idea and select **Research my idea**. There is no Compare/Evaluate/Audit selection or mandatory questionnaire. Optional profile fields accept free text and unknowns. Follow-up answers update the research; conflicting statements remain visible. The official Amira, Mateo and Robert personas are **test fixtures only** and never supply production defaults or classifications.

Example: `I am considering investing 3000 CAD in AMD. I am comfortable taking high investment risk. My goal is to fund living costs. I need to withdraw 500 CAD monthly for 24 months, starting next month.`

The report separates willingness from financial capacity and withdrawal needs. It includes dated public prices, CAD conversion, historical and withdrawal charts, purchasing-power results when Canadian CPI is available, relevant risk checks, and source gaps. Download a standalone HTML report with vector charts or Markdown. A separate Bedrock review checks the model's qualitative interpretation; rejected prose is withheld while checked calculations remain available.

Public research uses Yahoo Finance's unofficial chart interface and Bank of Canada Valet, with no extra market-data credentials. The route supports up to three named instruments, up to five years of observations, and CAD/USD conversion. Source timestamps and failures are visible. This is a current retrospective, not a historical-vintage backtest or guaranteed real-time feed. Raw downloaded market data are not committed.

## Historical validation workbench

Open **Reference cases → Historical decision workbench** for the preserved advanced interface. The sections below describe its three historical actions, which share the confirmation, evidence, replay, rule and publication pipeline.

| Action | Confirmed input | Published result |
| --- | --- | --- |
| **Compare** | Two assets or complete allocations; optional ranking priority and binding rules | Common-window metrics, rule dispositions, and a ranking only where the confirmed rules and evidence permit it |
| **Evaluate** | One complete allocation and optional binding rules | Historical metrics, assessed exposure intervals, uncertainty and applicable profile tensions |
| **Audit** | Starting allocation, purchase, original funding source and rules | Original proposal first; separately authorized funding search with verified candidates, source ranges or infeasibility evidence |

Examples:

- `Compare GLD and AGG. I care most about maximum drawdown.`
- `Evaluate a portfolio with 60% in SPY and 40% in AGG.`
- `Add 10 percentage points of NVDA by selling ZST.TO. Keep at least 15% in ZST.TO. Terminal loss must not exceed 14%.`

For a trade, also enter the complete starting allocation. The reference portfolio is 35% SPY, 25% XIU.TO, 20% QQQ and 20% ZST.TO. These are fictional demonstration inputs. The 14% cap and 15% reserve are team-defined example rules, not rules supplied by the organizer or inferred from a person's age.

The model-assisted draft accepts English and French wording; the interface and reports remain in English. Select **Draft with Amazon Bedrock** or **Draft offline**, inspect the quoted source wording, edit the fields, and confirm the complete scope before running the historical engine. Offline drafts remain labeled. An ambiguous loss cap needs a definition; unsupported conditions remain unresolved. Structured entry is available with an empty question.

After an audit, **Authorize alternative funding** asks which existing holdings may be sold and whether a smaller purchase is allowed. Preparing those inputs does not run the solver. Confirming the original proposal does not authorize alternatives.

## Read and export the result

Switch between **Explanation first** and **Metrics first** without rerunning the engine. Both read the same reviewed report. Inspect the rules, margins, coverage, evidence, model activity and metric records from the result. Download its JSON or either PDF view.

A released report can contain a verified breach or an unresolved condition. Publication means the displayed calculation passed its review; it does not mean the proposed investment passed every rule. Missing evidence is not treated as zero exposure. Missing calendar coverage prevents a binding historical rule from being declared satisfied on that window. An unsupported binding condition is always unknown, and a user-supplied portfolio label cannot change the rule disposition. The interface verifies the report's binding before displaying its result.

The optional model explanation is limited to 120 words and one or two reviewed references. Every sentence must exactly match an approved sentence or a fixed allowed transition, and every selected reference must appear in full. Invalid references, altered or omitted claims, unexpected tickers or prohibited advice withdraw the narrative; the checked deterministic explanation remains available. This is strict approved-sentence composition, not unrestricted semantic verification.

## Check what would change the finding

The general challenge workflow can read the existing report to explain a failure, a funding difference or uncertainty. A changed risk metric, cap, holding minimum or reduced purchase quantity needs separate confirmation. It changes one field from the original decision, keeps that original report intact, allows at most three rounds, and stops when the verdict changes. Funding-search consent is not inherited by a changed policy. Model selection of these new challenge actions has not yet received live acceptance.

## Data and supported scope

The organizer archive contains 31 assets. A decision can use covered assets and a supplementary adjusted-close CSV for absent symbols. Availability still depends on common dates, eligible sources, currency and coverage. The new engine takes symbols as inputs; the older **Reference cases** workspace retains its five-asset NVDA demonstration.

| Evidence | Treatment |
| --- | --- |
| Adjusted closes and USD/CAD | Frozen source bytes, SHA-256 fingerprints, CSV row references and same-date CAD conversion; independently reconstructed before review |
| Historical windows | Full shared history, named 2022 and early-2025 replays, optional 2023 and a user-specified interval; each window has its own coverage status |
| Knowledge date | Sources must have been available by the cutoff. The default follows source availability, not an earlier price observation date. Back-adjusted snapshots are retrospective evidence, not historical vintages. |
| Issuer and sector disclosures | Dated source qualifications, conservative intervals, unmapped exposure and source classifications; incomplete holdings stay unknown |
| GPFG screening | Dated checks for covered direct issuers; exclusions and observations are distinct. A company absent from that list has not received an ESG rating. ETF look-through is incomplete; source-class coverage is separate from interval uncertainty. [Evidence qualifications](DECISION_EVIDENCE.md) |
| Supplementary CSV | Columns `ticker,date,adj_close,currency`, with a public source URL and publication date. USD and CAD are supported. Uploaded source declarations remain user supplied. |

Metrics include signed terminal return, nonnegative terminal loss, maximum drawdown and its dates, recovery or unresolved time underwater, rolling 12/36-month outcomes, annualized volatility, worst complete month, contributions, FX decomposition and named-window stress context. Short histories leave unsupported measures unavailable. Returns use vendor-adjusted closes without an added tax, transaction-cost or inflation model. The 252-session volatility convention and exact calendar-period definitions are documented in the [technical summary](submission/technical-summary.md).

The general funding solver supports one or more authorized source holdings, explicit ticker-weight bounds, terminal-loss, drawdown and eligible rolling-12-month loss constraints. It returns exact-rational certificates for independent verification. Binding exposure constraints without verified solver coefficients, recovery-time funding constraints and insufficient window coverage produce `unassessed`; they are not dropped to manufacture a solution. Individual source ranges are marginal bounds at the selected purchase size, not independently interchangeable allocations.

## Run locally

Use Python 3.10 or later and the organizer's `Datathon2026.zip` or extracted `alphaforge_starter/` containing all six CSV tables. Keep source data and credentials outside version control.

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATA="/path/to/Datathon2026.zip"
export DATATHON_STARTER_PATH="$DATA"
export DATATHON_FULL_STARTER_PATH="$DATA"
python -m streamlit run app.py
```

The deterministic historical review works without AWS credentials. For model-assisted drafting, use an authenticated competition AWS session in the application process. Do not paste credentials into code, documentation or exported reports.

Decision drafting has a 30-second deadline, at most two HTTP attempts, an 18,000 observed-token threshold and an 8,000-byte request limit. A timeout preserves the question as an explicitly labeled offline draft and records the exhausted budget; it does not retry indefinitely.

| Setting | Default or meaning |
| --- | --- |
| `DATATHON_PROFILE_MODEL_ID` | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `DATATHON_AUDIT_MODEL_ID` | `us.amazon.nova-2-lite-v1:0` |
| `DATATHON_AWS_REGION` | `us-east-1` |
| `DATATHON_AUDIT_BUCKET` | Optional existing S3 bucket with versioning enabled; enables the reviewed-record save action |

The S3 operation checks bucket versioning and requires an ETag and non-null version ID in the write receipt. It does not create a bucket or change its permissions. Keep Block Public Access enabled. The receipt identifies the exact stored report version. Downloaded JSON/PDF files remain available when S3 is not configured.

Under **Reference cases → Earlier assistant validation**, the preserved assistant retains the earlier read-only Alpaca lookup. It uses `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, optional `DATATHON_ALPACA_ACCOUNT=paper|live`, and `DATATHON_ALPACA_FEED=iex|sip|delayed_sip`. Its dated single-ticker quote and recent price history are not substituted into the frozen decision replay. This provider is optional for the three historical actions.

## Verify and reproduce

```bash
python -m unittest discover -s tests -q
python -m datathon --data "$DATA" --case all --mode offline --stress --report outputs/offline.json
```

The `datathon` command reproduces the established reference workflow. The new CLI runs the shared general engine from reviewable fictional example files:

```bash
python -m datathon.decision_cli --example robert --data "$DATA" --confirm \
  --report outputs/robert.json --pdf outputs/robert.pdf --pdf-view audit
python -m datathon.decision_cli --example robert --data "$DATA" --confirm \
  --funding-sources QQQ,ZST.TO --authorize-search --report outputs/robert.json
```

Use `--example amira` or `--example mateo` for the other examples in `examples/decision_requests/`. Read the example before passing `--confirm`. Search authorization produces a separate `.search.json`; `--allow-smaller` explicitly extends size scope. Without `--authorize-search`, the CLI asks for a separate `SEARCH` confirmation; declining it keeps the original report and never runs the solver.

For local environment diagnosis, `python -m datathon.runtime_check --data "$DATA" --check-dns` reports runtime/data status, credential-provider availability and DNS reachability without invoking an AWS service. A detected provider is not proof that credentials are valid.

Tests named `test_decision_*` cover the new general decision modules. Full-data tests need both starter path variables; a run with skips is not a complete competition-data acceptance run.

The [verification record](submission/verification.md) separates each code revision and environment. The recorded `298e9b0` acceptance passed 319 tests on macOS and competition CloudShell, six live reference CLI cases, and the documented UI, fault and runtime cohorts. Those measurements do not automatically validate later code. New local results and any fresh AWS evidence belong in their own dated section.

The existing MP4 records `13ccc42`. The [current recording script](submission/demo-script.md) describes the updated demonstration; a script update is not a new recording. The [architecture status](submission/architecture-status.md) identifies incomplete target requirements, including broader evidence, model evaluation and cloud services.

## Source map

| Module | Responsibility |
| --- | --- |
| `decision_intake.py`, `decision_view.py` | Drafting, clarification, editable confirmation and report interaction |
| `decision_workflow.py`, `decision_challenge.py` | Confirmed decision, rule evaluation, explicit funding authorization and bounded one-field follow-ups |
| `decision_market.py`, `decision_evidence.py` | Frozen price provenance, date eligibility and exposure evidence |
| `decision_replay.py`, `decision_funding.py` | Asset-independent historical calculations, independent recomputation and certified funding search |
| `decision_release.py` | Review-bound publication, checked explanations, JSON/PDF and optional versioned S3 writes |
| `presets/` | Fictional persona context; presets do not silently become binding rules |
| `tests/` | Formula, evidence, authorization, intake, publication, UI and fault regressions |
| `submission/` | Technical summary, recording script, verification and architecture status |

[Implementation plan](plan.md) · [Earlier architecture experiments](BENCHMARK.md) · [Iteration history](AGENT_ITERATION.md) · [Reliability changes](RISK_RELIABILITY_IMPLEMENTATION.md)
