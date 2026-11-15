# Equity sector evidence

The report compares before and after weights under one dated long-only holdings snapshot. It states exposure as a fraction of the whole portfolio. Each sector has an individual range. A sector's upper bound may allocate all of a fund's unmapped weight to that sector, so upper bounds across sectors cannot be added.

For the change, each ticker retains the same possible exposure fraction in both portfolios. Unchanged unknown positions cancel. A sold position contributes its negative weight change multiplied by its possible exposure. This measures the trade's effect with the snapshot held fixed.

## Included evidence

- **NVDA.** S&P DJI classifies the direct common stock as Information Technology. The capsule uses the October 30, 2026 S&P 500 constituent table. The April 2026 guide independently identifies the same sector and ticker. [S&P 500 constituents](https://www.spglobal.com/spdji/en/indices/equity/sp-500/) · [S&P DJI index education, Exhibit 2](https://www.spglobal.com/spdji/en/documents/education/education-an-overview-of-gics-and-sp-500-sector-industry-indices.pdf)
- **ZST.TO.** BMO's June 30, 2026 report describes all 25 listed positions as debt and reports them together as 83.8% of fund NAV. The capsule uses 83.7% as a conservative non-equity lower bound to allow for display rounding. The undisclosed portion stays unmapped. Its bond-issuer industry allocation is separate from the equity sectors in this report. [BMO report, pp. 4–5](https://bmo.bynder.com/m/649f11fac077a423/original/SA_MRFP_ZST_E.pdf)

These sources were checked as publicly available by November 14, 2026. That date is the known availability cutoff for these records. Under this snapshot, moving ten points of portfolio value from ZST.TO to NVDA increases Information Technology exposure by 8.37 to 10.00 percentage points. The holdings dataset remains partial. The report is descriptive. Sector caps and other unsupported portfolio constraints require explicit treatment by the planner and reviewer.

## Reviewed catalog

An operator can point `DATATHON_SECTOR_CATALOG` to a local JSON catalog and supply its reviewed content hash in `DATATHON_SECTOR_CATALOG_SHA256`. The catalog replaces the included snapshot. The manifest uses `taxonomy`, `version` and `records`. Each record carries `ticker`, `taxonomy`, `version`, `as_of`, `available_by`, `source_url`, `source_locator`, `denominator` and `weights`. The optional keys are `non_equity_min` and `equity_fraction`. Weights and bounds are fractions from zero to one.

| Denominator | Required evidence |
| --- | --- |
| `position` | One direct holding's full classification in one sector. |
| `nav` | Already reconciled fund-level sector weights as fractions of net assets. A verified non-equity lower bound is optional. |
| `equity_sleeve` | Sector weights within equities and an independently evidenced equity fraction of NAV. |

Pin the catalog after reviewing dated sources, asset identifiers, denominators, taxonomy versions and coverage. Keep parent fund and underlying positions from being counted together. Record ETF sector mappings only when the taxonomy is verified for those holdings. Invesco's QQQ published sector table uses ICB, which requires a documented mapping before those weights can populate a GICS catalog. [Invesco QQQ classification](https://www.invesco.com/qqq-etf/en/about.html)
