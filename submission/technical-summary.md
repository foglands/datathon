# AlphaForge AI | Technical summary

PolyFinances Datathon 2026 · Banque Nationale × AWS  
Reference financial results `13ccc42` · Scope and publication update `186cdcf`

## Decision and scope

AlphaForge AI audits a proposal to add NVIDIA exposure by selling QQQ, ZST.TO, or a permitted mix. Changing the funding source can change both historical loss and the fit with the investor's confirmed rules. The reference CAD weights are **35% SPY, 25% XIU.TO, 20% QQQ and 20% ZST.TO**. The reference purchase adds **10 percentage points of NVDA**, initially funded by ZST.TO. Structured entry also accepts custom weights for the five supported assets.

Streamlit confirms the trade, original financing and applicable limits. The investor may request a full-size funding search separately. Smaller-size authorization can be deferred. The optional Sonnet 4.5 Profile proposes editable fields and records unsupported binding terms. The user can choose a limited review of the original trade. A follow-up retains the approved scope when testing a rule or reviewed issuer disclosure.

## Agent roles and control points

| Stage | Responsibility and output |
| --- | --- |
| Profile | Optional free-text intake. Extracts supported rules, asks about missing or conflicting terms and leaves authority with the user's explicit confirmation. |
| Evidence | Selects market evidence, adding qualified issuer disclosure only when required. Keeps observation dates, publication dates and data gaps visible. |
| Exposure and Scenario | Run in parallel when both apply. Exposure computes direct and indirect issuer bounds. Scenario selects the confirmed loss test and invokes both required historical windows. |
| Alternatives | Runs only for a confirmed search. Checks full-size feasibility and may ask permission for a smaller purchase. Follows the confirmed funding sources. |
| Review | Recomputes the original audit independently. Checks funding ranges only when search is authorized. Associates verified rules and unresolved terms with their evidence. |
| Explanation | Publishes a deterministic explanation and the independently reviewed report. Unassessed rules stay visible. Unchecked figures and optional model prose stay outside the published result. |

Strands calls Amazon Bedrock in the competition account. Nova 2 Lite handles the staged audit and follow-up selection. Sonnet 4.5 handles optional Profile intake. Python supplies the numerical verdict. Evidence and Scenario can use a disclosed deterministic routing fallback. An absent or invalid independent review blocks release. Action-level time and HTTP attempt limits cover parallel roles. The app separates offline from live runs and exports the rules, tool actions and applicable Bedrock request IDs.

## Data and financial method

- **Historical replay.** The starter supplies adjusted closes and Bank of Canada USD/CAD fixings. Convert USD prices to CAD, then replay buy-and-hold value paths. The two reference windows are 2021-12-31 to 2022-12-30 and 2024-12-31 to 2025-04-08, with 244 and 67 aligned dates. A third, optional 2023 window has 63 dates. The audit compares the actual dates with the pinned calendars, which account for the archived FX gaps. Any unexpected missing session blocks a funding verdict. Macro data remains descriptive because publication vintages are unavailable.
- **Risk and alternatives.** Terminal loss measures the nonnegative start-to-end loss. Maximum drawdown measures the largest decline from a prior peak. Portfolio values are affine in the funding amounts. The solver screens peak/trough inequalities that hold throughout the purchase triangle, then solves the remaining constraints. The independent reviewer traverses the full date-pair set as needed and recomputes per-asset contributions at each portfolio's own peak and trough.
- **Issuer exposure.** The SPY and QQQ SEC N-PORT holdings are observed 2026-06-30 and filed 2026-08-28. The dated issuer check uses a 2026-11-14 reference and publication cutoff, with a 180-day default freshness limit. Direct equity and dated disclosed fund fractions establish a lower bound. Unknown look-through stays unknown, and a conservative upper bound accounts for the unverified portfolio weight. The historical price replay and the 2026 holdings snapshot answer different questions. The issuer check concerns NVIDIA common equity exposure.
- **Sector analysis.** Optional descriptive GICS sector intervals use a dated long-only NAV evidence set. Before and after calculations share the same uncertain fund exposures. Unmapped assets stay visible. A descriptive sector observation cannot settle a binding sector cap.

## Reproducible decisions

| Reference | Findings independently checked |
| --- | --- |
| Robert · 14% terminal-loss limit | ZST.TO-only funding leaves 10% in the fund, below the 15% floor. The 2022 terminal loss is 16.15%. The full purchase can use 0 to 2.63167 points of ZST.TO funding, with QQQ financing the rest. At 2.00 points the same loss is 13.82%, and at 3.00 points it is 14.11%. The QQQ-only example retains 20% in ZST.TO and has a 13.23% terminal loss. |
| Robert · 14% maximum-drawdown limit | Changing only the metric leaves the purchase with no permitted funding mix. The 2022 baseline drawdown is 16.05%; the 2022-01-04 to 2022-06-16 peak-to-trough bound independently rules out all permitted mixes, including zero additional purchase. |
| Amira · 14% issuer limit | The original ZST.TO-funded proposal has at least 14.15% NVIDIA exposure. The QQQ-funded illustration has a documented lower bound of 13.39%. A combined XIU.TO and ZST.TO NVIDIA contribution of at most 0.60937 points would meet the cap in that illustration. The relevant positions lack verified dated look-through, so the alternative remains unresolved. |

## Validation and limitations

- The scope and publication update at `186cdcf` passed **165/165** local tests and **6/6** CLI scenarios in both execution modes. Live audit-only used three Bedrock requests and zero solver calls in the matched Robert check. Authorized search used four requests and one solver call.
- Optimized application `0c39d08` passed **137/137 local tests** with the full organizer ZIP and **6/6** CLI scenarios in each of offline and live modes. Scripted paired faults recovered **8** staged and **4** bundled paths, with zero unsafe releases. The older live challenge at `20a71c4` scored 20/20 in both model arms and 10/20 with fixed rules.
- Live Sonnet at `0c39d08` matched **20/20** on the mixed set (ten cases, twice each), up from **18/20** at `fecddec`. The bilingual and quote sets each matched **12/12**. The total exposure set passed **6/6** and the text-to-reviewed-audit path passed **4/4**. User confirmation remains required.
- The default Amira result still has unresolved look-through. Reviewed synthetic disclosures exercise the re-audit in tests. The historical windows and issuer snapshot are scoped. Trading costs, taxes, bid-ask spreads and intraday losses are outside the simulation.

## Reproduction and references

Use Python 3.10 or later, the official ZIP or extracted `alphaforge_starter` folder, and the repository dependency pins. Run `python -m streamlit run app.py` after setting `DATATHON_STARTER_PATH`. The local and live CLI, benchmark and audit instructions are in the repository README. Live execution requires authorized Bedrock access. The competition account is temporary, so offline reproduction uses the archived data and deterministic review.

- [Final release verification](https://github.com/WindsTrace/datathon-prep/blob/agent-optimization/submission/verification.md)
- [Project README and reproduction](https://github.com/WindsTrace/datathon-prep/tree/agent-optimization#readme)
- [Expanded benchmark and interpretation](https://github.com/WindsTrace/datathon-prep/blob/13ccc42/AGENT_ITERATION.md)
- [PolyFinances organizer and official case materials](https://polyfinances.ca/datathon#competition)
- [SPY SEC N-PORT](https://www.sec.gov/Archives/edgar/data/884394/000141036826089410/primary_doc.html) · [QQQ SEC N-PORT](https://www.sec.gov/Archives/edgar/data/1067839/000106783926000030/primary_doc.html)
- [Bank of Canada exchange rates](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/) · [Amazon Bedrock](https://aws.amazon.com/bedrock/)
