# AlphaForge AI | Technical summary

PolyFinances Datathon 2026 · Banque Nationale × AWS  
Reference financial results `13ccc42` · Fictional portfolio simulation

## Decision and scope

AlphaForge AI audits a proposal to add NVIDIA exposure by selling QQQ, ZST.TO, or a permitted mix. Changing the funding source can change both the portfolio's historical loss and its fit with the investor's confirmed rules. The fictional starting weights are **35% SPY, 25% XIU.TO, 20% QQQ and 20% ZST.TO**. The reference request buys **10 percentage points of NVDA**, initially funded by ZST.TO. Scope is one CAD portfolio, one candidate issuer and two funding assets.

The default Streamlit input lets the user state and confirm the size, original and allowed funding, whether a smaller buy is permitted, the historical risk metric and cap, the ZST.TO floor, the NVIDIA issuer cap and any reserve preference. The optional Sonnet 4.5 Profile proposes editable fields from plain text. A follow-up can test one tighter threshold or alternate rule, request a specific disclosure, or abstain. The original policy and audit remain available alongside any independently verified follow-up.

## Agent roles and control points

| Stage | Responsibility and output |
| --- | --- |
| Profile | Optional free-text intake. Extracts supported rules, asks about missing or conflicting terms and leaves authority with the user's explicit confirmation. |
| Evidence | Selects market evidence, adding qualified issuer disclosure only when required. Keeps observation dates, publication dates and data gaps visible. |
| Exposure and Scenario | Run in parallel when both apply. Exposure computes direct and indirect issuer bounds. Scenario selects the confirmed loss test and invokes both required historical windows. |
| Alternatives | Computes the permitted funding region, policy headroom and an eligible funding example when verified. If the requested size is unreachable, separately identifies any permissible smaller purchase. |
| Review | Independently recomputes the results and checks source inputs, candidate figures, boundary conditions and any claim of infeasibility. A bounded follow-up can choose one check from an explicit catalog. |
| Explanation | Turns verified figures, rule status, evidence and missing information into the result shown in the interface. The default release uses the deterministic checked summary. |

Strands calls Amazon Bedrock in the competition account. Nova 2 Lite handles the staged audit and follow-up selection. The optional Profile uses Sonnet 4.5. Models select typed tools. Deterministic calculations supply the numerical verdict. The checked tool outputs remain usable if optional narration fails. Evidence and Scenario can disclose a deterministic routing fallback. An absent or invalid independent review blocks release. The app labels offline reproduction separately and exports a JSON audit with rule values, evidence IDs, tool actions and applicable Bedrock request IDs. Raw free text and excerpts are excluded from exported records.

## Data and financial method

- **Historical replay.** The official starter supplies adjusted daily closing prices, CAD/USD listing currency and Bank of Canada USD/CAD fixings. USD price observations are converted to CAD before taking returns. Both windows use initial weights and buy-and-hold value paths on intersected dates. The two windows are 2021-12-31 to 2022-12-30 and 2024-12-31 to 2025-04-08, with 244 and 67 aligned dates. Two interior 2022 common price dates are omitted because no same-date FX fixing was supplied. Missing endpoints make a required replay unavailable. Corporate actions inform provenance checks. Macro observations are descriptive because publication-vintage history is unavailable.
- **Risk and alternatives.** Terminal loss is the nonnegative start-to-end loss. Maximum drawdown is the largest fractional decline from a prior peak during a window. The two-asset funding solver checks allowed holdings, permitted purchase sizes, reserve and risk or exposure rules over the permitted purchase domain. At fixed purchase size, historical portfolio values are affine in the split of funding. A drawdown limit is checked against every earlier/later observation pair, and review independently recomputes signed per-asset contributions using the portfolio's own peak/trough dates. The end of a feasible interval is reported as a boundary with the relevant rule and available headroom.
- **Issuer exposure.** The SPY and QQQ SEC N-PORT holdings are observed 2026-06-30 and filed 2026-08-28. The dated issuer check uses a 2026-11-14 reference and publication cutoff, with a 180-day default freshness limit. Direct equity and dated disclosed fund fractions establish a lower bound. Unknown look-through stays unknown, and a conservative upper bound accounts for the unverified portfolio weight. The historical price replay and the 2026 holdings snapshot answer different questions. The issuer check concerns NVIDIA common equity exposure.

## Reproducible decisions

| Reference | Findings independently checked |
| --- | --- |
| Robert · 14% terminal-loss limit | ZST.TO-only funding leaves 10% in the fund, below the 15% floor. The 2022 terminal loss is 16.15%. The full purchase can use 0 to 2.63167 points of ZST.TO funding, with QQQ financing the rest. At 2.00 points the same loss is 13.82%, and at 3.00 points it is 14.11%. The QQQ-only example retains 20% in ZST.TO and has a 13.23% terminal loss. |
| Robert · 14% maximum-drawdown limit | Changing only the metric leaves the purchase with no permitted funding mix. The 2022 baseline drawdown is 16.05%; the 2022-01-04 to 2022-06-16 peak-to-trough bound independently rules out all permitted mixes, including zero additional purchase. |
| Amira · 14% issuer limit | The original ZST.TO-funded proposal has at least 14.15% NVIDIA exposure. The QQQ-funded illustration has a documented lower bound of 13.39%. A combined XIU.TO and ZST.TO NVIDIA contribution of at most 0.60937 points would meet the cap in that illustration. The relevant positions lack verified dated look-through, so the alternative remains unresolved. |

## Validation and limitations

- Earlier release checks recorded **113/113 local regressions** with the official dataset and **6/6 live AWS CLI reference cases**. The release verification log separately identifies the revision and checks for the final package. The expanded 20-attempt challenge benchmark at `20a71c4` obtained 20/20 correct follow-up checks in both staged and bundled Bedrock arms versus 10/20 for fixed rules. All three arms had zero unsafe releases or policy changes on this cohort and passed separate missing-FX checks. Staged base and follow-up median latency were 3.06 s and 3.41 s, respectively.
- On 20 repeated intake requests, the final optional Sonnet Profile matched 20/20. It also matched 12/12 in a separate quote-focused cohort. Confirmation remains required. Shared decision gates and finite test sets limit the inference to these cases. The staged and bundled arms tied on this benchmark.
- Evaluation covers two selected historical windows and a frozen issuer snapshot. Trading costs, taxes, bid-ask spreads and intraday losses fall outside that scope. The educational simulation uses a defined fictional portfolio and ends at the audit. Extending it to more portfolios would require verified holdings across more funds and independent tests of the expanded coverage.

## Reproduction and references

Use Python 3.10 or later, the official ZIP or extracted `alphaforge_starter` folder, and the repository dependency pins. Run `python -m streamlit run app.py` after setting `DATATHON_STARTER_PATH`. The local and live CLI, benchmark and audit instructions are in the repository README. Live execution requires authorized Bedrock access. The competition account is temporary, so offline reproduction uses the archived data and deterministic review.

- [Final release verification](https://github.com/WindsTrace/datathon-prep/blob/agent-optimization/submission/verification.md)
- [Project README and reproduction](https://github.com/WindsTrace/datathon-prep/tree/agent-optimization#readme)
- [Expanded benchmark and interpretation](https://github.com/WindsTrace/datathon-prep/blob/13ccc42/AGENT_ITERATION.md)
- [PolyFinances organizer and official case materials](https://polyfinances.ca/datathon#competition)
- [SPY SEC N-PORT](https://www.sec.gov/Archives/edgar/data/884394/000141036826089410/primary_doc.html) · [QQQ SEC N-PORT](https://www.sec.gov/Archives/edgar/data/1067839/000106783926000030/primary_doc.html)
- [Bank of Canada exchange rates](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/) · [Amazon Bedrock](https://aws.amazon.com/bedrock/)
