# Equity sector evidence

The report compares before and after weights under one dated long-only holdings snapshot. It states exposure as a fraction of the whole portfolio. Each sector has an individual range. A sector's upper bound may allocate all of a fund's unmapped weight to that sector, so upper bounds across sectors cannot be added.

For the change, each ticker retains the same possible exposure fraction in both portfolios. Unchanged unknown positions cancel. A sold position contributes its negative weight change multiplied by its possible exposure. This measures the trade's effect with the snapshot held fixed.

## Included evidence

- **NVDA.** S&P DJI classifies the direct common stock as Information Technology. The capsule uses the October 30, 2026 S&P 500 constituent table. The April 2026 guide independently identifies the same sector and ticker. [S&P 500 constituents](https://www.spglobal.com/spdji/en/indices/equity/sp-500/) · [S&P DJI index education, Exhibit 2](https://www.spglobal.com/spdji/en/documents/education/education-an-overview-of-gics-and-sp-500-sector-industry-indices.pdf)
- **ZST.TO.** BMO's interim financial statements for June 30, 2026, filed August 28, show corporate debt fair value of 4,071,352 and asset-backed notes of 72,675, in thousands of CAD. These account for all 4,144,027 in the investment schedule. The reported net assets attributable to redeemable units are 4,158,550 in the same units. Allowing one displayed thousand CAD of precision in each conservative direction gives `(4,144,027 − 1) / (4,158,550 + 1)`, about 99.65% of fund NAV. The residual stays unmapped. The fund's bond-issuer industries are separate from the equity sectors. [BMO interim financial statements via SEDAR filing mirror, PDF pp. 2 and 5–6](https://newsfile.futunn.com/public/NN-PersistNoticeAttachment/7781/20260828/911_CSA_SEDAR_PLUS_NOTICE_RECORD_ID_2494089_en-us_0.pdf)

These sources were publicly available by November 14, 2026, the competition reference cutoff. Under this snapshot, moving ten points of portfolio value from ZST.TO to NVDA increases Information Technology exposure by about 9.97 to 10.00 percentage points. The holdings dataset remains partial. The report is descriptive. Sector caps and other unsupported portfolio constraints require explicit treatment by the planner and reviewer.

## Reviewed catalog

An operator can point `DATATHON_SECTOR_CATALOG` to a local JSON catalog and supply its reviewed content hash in `DATATHON_SECTOR_CATALOG_SHA256`. The catalog replaces the included snapshot. The manifest uses `taxonomy`, `version` and `records`. Each record carries `ticker`, `taxonomy`, `version`, `as_of`, `available_by`, `source_url`, `source_locator`, `denominator` and `weights`. Weights and bounds are fractions from zero to one.

| Denominator | Required evidence |
| --- | --- |
| `position` | One direct holding's full classification in one sector. |
| `nav` | Fund-level sector weights as fractions of net assets. Optional `non_equity_amounts` contains `fair_value`, `net_assets`, `display_unit` and `currency`, all from one dated report. Store the amounts as printed, and set `display_unit` to the number of currency units each printed integer represents. A legacy `non_equity_min` scalar without underlying amounts leaves that portion unmapped. |
| `equity_sleeve` | Sector weights within equities and an independently evidenced equity fraction of NAV. |

Pin the catalog after reviewing dated sources, asset identifiers, denominators, taxonomy versions and coverage. Keep parent fund and underlying positions from being counted together. Record ETF sector mappings only when the taxonomy is verified for those holdings. Invesco's QQQ published sector table uses ICB, which requires a documented mapping before those weights can populate a GICS catalog. [Invesco QQQ classification](https://www.invesco.com/qqq-etf/en/about.html)
