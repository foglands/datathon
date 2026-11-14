# Changelog

## 2026-11-14 · User-confirmed trade audit

- Added an interactive `--request` entry point for fictional NVDA purchases funded by QQQ or ZST.TO. The Strands profile agent extracts the original funding source, permitted funding sources, purchase size, explicit limits and permission to buy a smaller amount. It asks for clarification when needed and presents the interpreted inputs for confirmation before the audit runs.
- The solver and independent reviewer now distinguish an infeasible exact purchase from an infeasible funding range. A smaller diagnostic limit stays separate from eligible alternatives when the user requires the full amount.
- Tightened the six preset checks to require the observed verdicts. Robert's terminal-loss case also checks the independently verified funding boundary and feasible alternative. The drawdown case checks independent confirmation of infeasibility.
- Local verification passed 19 unit tests and all six official-data preset cases. The final competition CloudShell run passed the six presets and both interactive ZST.TO cases with Nova 2 Lite. One intermediate run over-asked for clarification on an already explicit terminal-loss limit. The final run verified that an ambiguous limit prompts a choice and that a supported explicit rule proceeds to confirmation.

With only ZST.TO available for funding, a 15% ZST.TO floor and a 14% terminal-loss limit, the 10-point request is infeasible. The 5-point purchase moves from diagnostic to eligible only after the user allows a smaller purchase.

For reproduction commands and an example request, see [Run it](README.md#run-it).
