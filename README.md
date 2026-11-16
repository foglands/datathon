# AlphaForge AI

### An investment idea, examined with evidence

**PolyFinances Datathon 2026 · Banque Nationale · AWS**

**Try AlphaForge:** [Open the hosted app](https://alphaforge-datathon.streamlit.app/) · [One-page summary](submission/one-pager.pdf) · [Technical guide](submission/technical-summary.pdf) · [Submission index](submission/README.md)

The hosted verification recorded working market-data retrieval, Python calculations and charts. That run returned checked evidence with no reviewed conclusion because the host had no usable Bedrock credentials. See the [deployment guide](docs/DEPLOYMENT.md) and [verification record](submission/final-verification.md).

Describe what you are considering and what matters to you. AlphaForge turns that question into an analysis plan, retrieves dated public observations, calculates the evidence in Python, and presents a conclusion with supporting evidence, counterevidence, charts and important gaps.

The customer interface starts with one question and optional context. Use **Apply question** in the sidebar to load an editable example, then select **Analyze my question** to start. Follow-up questions can add or correct conditions.

## Three example questions

The examples are fictional adaptations of the official PolyFinances Datathon 2026 case brief (English edition, pp. 5–7). The instruments are illustrative. All three use the same analysis workflow and only the context stated in the question.

| Example | What the user wants to understand |
| --- | --- |
| AI and Bitcoin (Amira) | Whether adding NVDA and IBIT to SPY could undermine diversification, even when the investor can tolerate volatility and has at least 15 years. |
| Growth with ESG preferences (Mateo) | How ESGU and SPY compare for a ten-year investor seeking growth and stability, and what the issuers' disclosures establish about screening. |
| A stock before retirement (Robert) | How TSLA's historical losses relate to a four-year retirement horizon and a need to protect savings. |

## How it works

1. **Understand the question.** Retain stated goals, amounts, horizons, cash needs, holdings and constraints. Missing information remains unknown.
2. **Plan the analysis.** Propose questions and select the tools needed to answer them.
3. **Collect and calculate evidence.** Retrieve observations, run Python calculations and verify numerical results. Keep source dates and scope limitations.
4. **Synthesize an answer.** Weigh supporting and opposing evidence. Request additional analysis when a gap can be resolved within the available tools and budget.
5. **Review the conclusion.** A separate model call checks claims, citations, material context and unresolved tasks. Failed review can trigger repair; unsupported prose is withheld.

The reviewed conclusion appears above the supporting evidence and source tabs. If the evidence or review is incomplete, the result shows the checked observations and what remains unresolved. Reports can be downloaded as standalone HTML with charts or as Markdown. The application is for research and simulation.

## Quick start

Use **Python 3.10 or later**. Cloud deployment uses Python 3.11. Clone the repository and enter its directory:

```bash
git clone --branch architecture-completion-20261115 https://github.com/foglands/datathon.git
cd datathon
```

**macOS and Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the URL printed by Streamlit, normally `http://localhost:8501`. For model-led research, configure an authorized AWS session with access to the configured Bedrock model in `us-east-1`, then launch the app from that shell. Temporary credentials include a session token. Use the [AWS setup and diagnostics](docs/RUNNING.md#aws-configuration) for local use or the [deployment guide](docs/DEPLOYMENT.md) for Streamlit Cloud Secrets.

Set `DATATHON_STARTER_PATH` to use a local archive. A hosted app can load an approved ZIP from a private S3 object with a pinned SHA-256 digest. The three examples also have sourced filing evidence that remains usable without daily prices. Broader historical analysis and charts need a configured price source. The external Yahoo adapter starts disabled. An operator can enable it only after confirming permission for the intended access and use. See the [data setup](docs/RUNNING.md#organizer-archive-and-full-data-validation) and [hosted configuration](docs/DEPLOYMENT.md).

## Evidence and supported scope

| Capability | Current boundary |
| --- | --- |
| Asset research | Up to three instruments, using the configured archive and an external feed only if authorized and enabled. Reports preserve dates and source hashes. Ambiguous listings need clarification. |
| Historical risk | Return/loss, drawdown, volatility, rolling outcomes, recovery and selected stress replays; history is not a forecast |
| Currency and purchasing power | CAD/USD conversion using Bank of Canada FX; Canadian CPI where relevant and available; distinct observation periods |
| Portfolio and withdrawals | Complete explicitly stated weights; single or fixed monthly withdrawal schedules with sufficient inputs; no inferred holdings or success probability |
| Product and exposure evidence | Dated fund and issuer disclosures, including ESGU screening, SPY holdings, IBIT exposure and a TSLA historical decline. Screening methodology alone cannot verify holdings or company controversies. |
| Follow-up and review | Sourced corrections/retractions, bounded extra tool calls, claim/task review, visible partial and evidence-only outcomes |

Quotes may be delayed. Public research is a current retrospective, not a historical-vintage backtest or execution feed. Fundamentals, valuation, news, complete fund look-through and comprehensive ESG screening are not supplied. A traded-volume ratio does not prove execution feasibility. VaR/ES are withheld without certified observation coverage. See [sources and method boundaries](CUSTOMER_RESEARCH.md).

## Validation status

The latest full-data regression result and commands are in [final verification](submission/final-verification.md). Tests cover calculations, evidence provenance, task contracts, conversation state, authorization, tampering and Streamlit behavior.

**Model generalization remains partial.** Frozen-data trials exposed paraphrase/irrelevant-detail inconsistencies and semantic-review false positives. Failures are retained in the [analysis reliability record](submission/analysis-validation-2209.md) and [reasoning evaluation](submission/reasoning-validation.md). Unit-test success or model approval does not establish universal answer quality or investment suitability.

```bash
python -m unittest discover -s tests -q
```

Without the organizer archive, data-dependent tests skip. Set both starter-path variables for complete coverage; see [RUNNING.md](docs/RUNNING.md). GitHub Actions runs the credential-free suite without Bedrock calls or bundled organizer data.

## Historical reference workbench

A separate developer app, `python -m streamlit run validation_app.py`, preserves Compare, Evaluate and Audit, fictional personas, controlled funding searches and acceptance tools. Reference cases are absent from the customer interface. Original-proposal review never authorizes an alternative search. See [workbench methods](docs/historical-workbench.md) and [CLI examples](docs/RUNNING.md#historical-workbench-and-cli).

## Repository map

| Location | Purpose |
| --- | --- |
| `app.py`, `datathon/customer_ui.py`, `datathon/customer_ui.css` | Customer application, conversation and visual layout |
| `validation_app.py` | Separate developer workbench and reference cases |
| `customer_agents.py`, `customer_state.py`, `customer_profile.py` | Grounded intake, sourced state changes and relevant context |
| `inquiry_engine.py`, `inquiry_contracts.py`, `customer_tools.py` | Analysis tasks, bounded investigation, synthesis and claim/task review |
| `customer_data.py`, `customer_risks.py`, `customer_bonds.py` | Public observations and calculation tools |
| `customer_workflow.py`, `customer_report.py` | Orchestration, report binding and exports |
| `datathon/decision_*.py` | Historical confirmation, replay, evidence, review and funding machinery |
| `tests/`, `examples/`, `presets/` | Regression suite and fictional validation inputs |
| `docs/`, `submission/` | Running guide, technical documents, PDFs, screenshots and dated validation |

Module names without a directory prefix are under `datathon/`.

## AWS, data and license

Amazon Bedrock performs question understanding, planning, synthesis and separate semantic review through Strands tool handoffs. Python remains the authority for numerical results. Optional versioned S3 export exists in the historical workbench. Knowledge Bases, managed Guardrails, Step Functions and Object Lock are not claimed deployed services.

Use fictional inputs for demonstration. Raw downloaded prices, the organizer archive, credentials and private account data are not bundled. Source terms remain applicable; the [MIT license](LICENSE) covers project code, not third-party data redistribution rights.

[Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Requirements](ANALYSIS_REQUIREMENTS_2209.md) · [Submission index](submission/README.md)
