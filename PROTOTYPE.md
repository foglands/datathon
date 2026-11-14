# AlphaForge AI prototype

AlphaForge AI evaluates a proposal to add 10 percentage points of NVDA exposure, funded from either QQQ or ZST.TO. The fictional starting allocation is 35% SPY, 25% XIU.TO, 20% QQQ and 20% ZST.TO. The result shows what changed, which investor rule drove the decision and where evidence coverage limits the assessment. An earlier research brief documents the background analysis. [Research brief](Datathon_Research_Brief.md)

## Reproduce a run

Use Python 3.10 or later and the official `Datathon2026.zip` or its extracted `alphaforge_starter/` directory. The historical calculations read the supplied adjusted closing prices and USD/CAD series. A small issuer-disclosure snapshot covers part of the portfolio's underlying exposure. Keep the organizer archive and CSV files outside version control. [Official participant release](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)

From the repository root, create a local environment with Python 3.10 or later and run a case with simulated roles. Replace the data path with the ZIP or the extracted starter directory on your machine.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m datathon --data /path/to/Datathon2026.zip --case all --mode offline
```

Use `--case robert` or `--case amira` to run only that profile. Use `--report <file>` to save the result and trace as JSON. Add `--stress` to test an ambiguous loss limit, missing evidence and a deliberately tampered candidate result.

For AWS mode, use a Python environment with the project dependencies and an authenticated competition AWS session. The AWS integration uses `strands-agents==1.63.0` and invokes Amazon Nova 2 Lite through Amazon Bedrock in `us-east-1`. The prototype defaults to the US inference profile `us.amazon.nova-2-lite-v1:0`. Use the team's normal AWS credential chain. [Competition AWS setup](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/20-setup)

```bash
python -m pip install -r requirements.txt
AWS_REGION=us-east-1 python -m datathon --data /path/to/Datathon2026.zip --case all --mode aws --stress --report outputs/round1.json
python -m unittest discover -s tests -v
```

The offline and competition CloudShell suites each passed all six scenarios, and the independent governance checks passed 11 unit tests. The successful CloudShell run recorded 62 successful Converse responses across the six scenarios. Full seven-role cases took 10.3–12.7 seconds in that run. Inspect the JSON trace for the model, region, request IDs and model-requested tool results. The AWS validation used the competition participant role. [Executed workshop notebook](Introduction-Datathon.executed.ipynb)

The first live suite stopped at profile handoff because Nova could not complete the initial structured schema. The profile Agent now submits the same fields through a dedicated tool with primitive arguments. Python validates the payload and only then starts the analysis. Core verdicts come from the review tool. Agent commentary is recorded separately.

## Roles and handoffs

| Role | Evidence passed to the workflow |
| --- | --- |
| `profile` | The stated target allocation, allowed funding sources, preferences and explicit loss, reserve or issuer caps. An ambiguous loss rule routes to clarification. |
| `evidence` | Dated issuer disclosures and starter prices, with source references and coverage gaps. |
| `exposure` | Direct NVDA exposure plus the shares held indirectly through the ETFs, with coverage gaps shown explicitly. |
| `scenario` | Terminal loss and maximum drawdown for the selected 2022 and April 2025 windows. |
| `alternatives` | Other portfolio choices grounded in the same inputs and constraints. |
| `review` | Checks of candidate figures, evidence references and constraint status. |
| `explanation` | Decision summary tied to reviewed results, unresolved questions and conditions that could change the answer. |

Financial calculations and boundary checks run in Python so that the underlying figures and rule outcomes can be reproduced. Read the role trace to follow the evidence, calculations, checks and explanation for the selected case.

## Compare the cases

| Case | What to check |
| --- | --- |
| Robert | Compare historical terminal loss and maximum drawdown against a hypothetical 14% limit, with a separate 15% minimum weight for ZST.TO. |
| Amira | Apply a hypothetical 14% issuer cap. Treat exposure beyond the available look-through as uncertain when it can affect the constraint. |
| Stress | Check that an ambiguous loss limit prompts clarification, missing evidence yields an explicit coverage gap, and the review catches a tampered candidate. |

The ZST.TO-only request failed both of Robert's definitions. With the terminal-loss rule, keeping the full 10-point NVDA purchase allowed a ZST.TO contribution of up to 2.6317 percentage points. The lower-loss QQQ-only alternative left ZST.TO at 20%. Under the maximum-drawdown rule, the 2022 baseline's 16.05% drawdown was already over 14%. The reviewed peak–trough calculation excluded every permitted purchase size and funding mix in both windows. Amira's original request had a documented 14.15% minimum NVIDIA exposure and failed her 14% cap. The QQQ-funded alternative had a 13.39% documented minimum, with full exposure unresolved. The missing-QQQ test kept the historical risk calculation and returned insufficient concentration evidence.

The historical replay uses buy-and-hold weights set at the beginning of each window. Use December 31, 2021 through December 30, 2022 for the 2022 replay and December 31, 2024 through April 8, 2025 for the early 2025 replay. USD adjusted closes are converted to CAD using same-day USD/CAD observations, and only common trading dates enter the calculation. Terminal loss measures the decline from the start to the end of the window. Maximum drawdown measures the largest fall from an earlier peak within the window.

The portfolio and investor thresholds are hypothetical. The SPY and QQQ holdings snapshot is dated June 30, 2026, with disclosures available August 28, 2026. The prototype analyzes that snapshot separately from the historical market replay. Fees, liquidity and trading costs require separate estimates when relevant to a decision. The prototype supports educational investment simulations.
