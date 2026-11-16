# Customer workspace acceptance · 2026-11-16 UTC

This record covers the general customer workspace, not the earlier architecture baseline. Exact application/test hashes are in [customer-validation.json](customer-validation.json). The prior local `bb2a049` and remote `bb18bec` contain the same baseline tree.

## Automated acceptance

- Full suite: **522 tests passed** in 84.385 seconds, using Python 3.10.7 and the frozen organizer starter archive.
- Final UTC chart-date display adjustment: all **3 customer UI tests passed** again. No financial calculation changed after the full run.
- `git diff --check` passed. Credential-pattern scanning of changed text files found no AWS access-key literals, GitHub tokens or private-key headers; this is a limited pattern check, not a security audit.
- Customer coverage includes generic profiles, unchanged metrics across official/custom names, high willingness with a down-payment need, withdrawal arithmetic, CPI alignment, bond disclosure qualification/staleness, missing or conflicting inputs, explicit corrections, explicit base currency without invented capital, company-name resolution, malformed provider data, absent FX, tampered numbers/chart points, unsupported narrative claims and explanation rejection.

Reproduce:

```bash
export DATATHON_STARTER_PATH=/path/to/alphaforge_starter.zip
export DATATHON_FULL_STARTER_PATH="$DATATHON_STARTER_PATH"
python -m unittest discover -s tests -q
```

The archive used here has SHA256 `f0c7948a4bea4f10c621125d7b085d6781e61387368064fada6fd59596426ff2`.

## Live custom profile: willingness versus cash needs

Input:

> I am considering investing 3000 CAD in AMD. I am comfortable taking high investment risk. My goal is to fund living costs. I need to withdraw 500 CAD monthly for 24 months, starting next month.

Observed public price and official FX/CPI requests succeeded in the existing credentialed Streamlit process. Bedrock extracted the stated conditions. The report retained high willingness separately from withdrawals. In the observed historical path, requested withdrawals totaled CAD 12,000; the replay paid CAD 2,460.41, left CAD 9,539.59 shortfall and ended with zero assets. The no-withdrawal historical CAD return was +315.25% with 62.50% maximum drawdown. These are observations from this specific retrieved sample, not forecasts or stable provider fixtures.

The report showed both withdrawal/no-withdrawal paths and monthly CPI comparison. The observed replay fully invested initial capital in fractional units; the separately displayed latest-price whole-share estimate retained cash. Live inspection exposed an explanation that conflated these conventions and proposed untested changes; the prompt, evidence and narrative checks were tightened. A later explanation was withheld, with checked evidence retained. Semantic review remains fallible.

## Live bond question

Input:

> I am considering investing 5000 CAD in AGG, a bond ETF. My goal is capital preservation over 3 years. I want to understand interest-rate and credit risks.

At retrieval `2026-11-16T01:10:39Z`, the public quote observation was USD 95.09 dated `2026-11-13T21:00:00Z`. The aligned CAD history used 1,218 observations, excluded 37 dates lacking same-date FX, and displayed +12.39% terminal change and 12.75% drawdown. The CPI-aligned interval was separately labeled and showed -8.99% real change.

Bedrock generated three qualitative sections and a separate model review accepted them. The report explained the tension between the preservation goal and historical declines, while leaving whole-portfolio diversification unknown. The duration/credit evidence came from a qualified **dated issuer catalog snapshot**, not a fresh per-request issuer scrape. AGG duration as of November 12 was 5.70 years; system-selected parallel ±100 bp illustrations produced first-order ∓5.70% price sensitivity. Underlying rating buckets, residual coverage and issuer sectors were displayed with limitations.

## UI and exports

- [New homepage](customer-workspace.jpg): one natural-language question, optional details and generic examples. No persona routing or required Compare/Evaluate/Audit selection.
- [Live report](customer-report.jpg): reviewed conclusion, dated metrics and charts.
- Report HTML generation, escaping and vector-chart presence passed automated checks. The browser download callback timed out and a completed downloaded file was not verified. Do not present that attempt as a verified browser download.
- The app's current HTML/Markdown report exports are separate from the earlier submission PDF/video artifacts. The revised demonstration script and one-page Markdown are current; previous rendered PDF/video files remain historical.

## Remaining supported boundaries

Public prices may be delayed. Exchange-calendar completeness is not certified. VaR/ES are withheld without that coverage. Initial qualified duration/credit coverage is AGG only; other instruments require their own dated evidence. Complete ETF look-through, comprehensive ESG screening, fundamentals/news, future goal-success probabilities, complex withdrawal schedules and guaranteed execution liquidity remain unavailable. Partial evidence does not become a whole-portfolio verdict. Every failed or unsupported check retains a visible status.
