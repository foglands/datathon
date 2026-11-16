# Dated exposure evidence

The decision workflow applies exposure rules only to qualified, dated records. A missing record gives a coefficient interval of `[0, 1]`; it never becomes a zero holding. Evidence describes the stated knowledge date separately from the dates of the historical price replays.

## Source classification and coverage

| Classification | Meaning | Limitation |
| --- | --- | --- |
| `direct` | A sourced identity, instrument category, sector classification, or named issuer screening state | Classifying a fund wrapper does not classify its underlying holdings. |
| `disclosed` | A cited holding or an exposure bound derived from a disclosed NAV denominator | Partial disclosure does not establish a complete holdings map. |
| `mandate_bounded` | An operator-reviewed bound supported by a dated mandate | A mandate is not a holdings verification. |
| `unknown` | No eligible evidence for the requested subject | The coefficient remains between zero and one. |

For each requested exposure, `disclosed_weight` is the portfolio weight covered by direct or disclosed records; `mandate_bounded_weight` and `unassessed_weight` identify the other source classes. Separately, `unknown_weight` is the weighted coefficient interval width. The legacy `coverage` field is one minus that interval width, **not** the fraction with a complete holdings disclosure. The report includes `coverage_basis` to make that distinction explicit.

Portfolio lower and upper bounds are sums of each position weight multiplied by its corresponding coefficient. A separate exact-rational computation checks both sums. Unknown issuer names do not inherit the zero coefficient for a different identified issuer: unresolved aliases remain unknown.

## Sources used by the supplied implementation

| Input | Observation and availability | Processing and limits |
| --- | --- | --- |
| [Organizer starter instrument manifest](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/50-datasets) | Source metadata retrieval date; available by November 14, 2026 | Both manifest and metadata fingerprints must match. Provides instrument buckets and selected direct issuer/sector identities. A bond ETF wrapper is not assumed to have 100% bond NAV. |
| SPY and QQQ SEC N-PORT disclosures | Holdings June 30, 2026; published August 28, 2026 | The already reviewed NVIDIA common-equity percentages are converted to NAV fractions. These records do not provide a complete issuer map. See [ISSUER_EVIDENCE.md](ISSUER_EVIDENCE.md). |
| NVIDIA SEC identity and S&P DJI taxonomy sources | Dates and exact locators retained in each accepted coefficient | Direct issuer identity is distinct from a current fund holding. The older month-dated classification is available only from the end of its publication month. |
| BMO ZST interim financial statements | June 30, 2026; available August 28, 2026 | The debt fair value divided by NAV uses an explicit rounding envelope. Residual NAV remains uncertain. See [SECTOR_EVIDENCE.md](SECTOR_EVIDENCE.md). |
| [NBIM observation/exclusion list](https://www.nbim.no/en/responsible-investment/exclusion-of-companies/) | List update August 11, 2026; source checked November 15, 2026 | Named direct-issuer checks cover ten supplied equities. The check date is separate from the source's stated update date. It is not a general ESG rating. |

The NBIM list check identifies Canadian Natural Resources as excluded and Toronto-Dominion Bank as under observation. The other eight named checks are `not_listed` within that dated list. That state means neither an exclusion nor observation was found under the reviewed issuer names; it is not a statement that a company has no controversy. The narrow `gpfg_exclusions` rule excludes only exclusions; `gpfg` also includes observation. Unreviewed issuers and ETF look-through remain `unknown` / unassessed.

The [NBIM disclaimer](https://www.nbim.no/en/disclaimer/) restricts reproduction. This implementation retains a small set of source-linked factual checks, not a copy of the complete table, and does not represent the list as an openly licensed dataset. Reusing or redistributing complete source materials requires checking their publisher terms. SEC filings and cited issuer materials likewise retain their applicable rights and limitations.

## Qualification and integrity

Publication dates must not exceed the confirmed knowledge date. Fund holdings, mandate bounds, and screening snapshots expire after the configured holdings-age threshold; a direct issuer identity or instrument taxonomy is not assigned that fund-holdings expiry. Conflicting equally dated bounds become unknown. Observation and publication dates cannot be silently replaced with retrieval dates.

The reviewed context includes `evidence_digest`. Changing its records, dates, aliases, or gaps before calculation invalidates the context. This fingerprint detects changed content; it does not establish source truth. Source qualification still depends on the cited document and the operator-reviewed catalog. Instruction-like text in an evidence record is rejected as `evidence_instruction_ignored` and cannot alter the policy.

The Python `extra_evidence` argument is an internal interface for operator-reviewed records and test fixtures. It is not an automatic source-verification service. The shipped UI does not turn arbitrary uploaded holdings text into qualified evidence. Complete issuer overlap, top-ten issuer concentration, HHI, and ETF GPFG screening need additional reviewed holdings data and are not claimed by these partial records.

## Validation

`tests/test_decision_evidence.py` covers NAV conversion, missing and stale holdings, publication cutoffs, source fingerprints, contradictory dated records, list scope, unqualified absence claims, context changes, unresolved issuer aliases, source-class versus interval coverage, and injected instructions. Run it together with the existing evidence and sector regression tests:

```bash
python -m unittest tests.test_decision_evidence tests.test_evidence \
  tests.test_exposure_review tests.test_sector tests.test_issuer_reaudit -q
```
