# Changelog

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
