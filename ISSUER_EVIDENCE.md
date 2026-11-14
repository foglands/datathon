# Reviewed issuer disclosures

Amira's original audit identifies the dated fund disclosures needed to resolve the NVIDIA common-equity cap. The issuer disclosure check can apply reviewed records and re-run the independent funding audit once. It preserves the original policy, market data and audit. A qualified record can narrow an exposure range while the remaining gaps keep the alternative unresolved.

The default release still leaves XIU.TO and ZST.TO unknown. The June 2026 management reports provide top-25 tables, and the BMO financial statements retrieved for the full portfolio schedule cover June 2025, outside the 180-day freshness window. A missing issuer in the top-25 table cannot establish zero exposure. No new factual issuer weight is bundled. [BlackRock June 2026 report](https://www.blackrock.com/ca/investors/en/literature/semi-annual-mrfp/sa-mrfp-xiu-en-ca.pdf) · [BMO June 2026 report](https://bmo.bynder.com/m/649f11fac077a423/original/SA_MRFP_ZST_E.pdf) · [BMO June 2025 statements](https://bmo.bynder.com/m/3c8c0efb79db1a88/original/SA_FS_ZST_E.pdf)

## Operator-reviewed catalog

The deployer prepares a local JSON manifest after independently checking each source document. Verify the fund identity, NVIDIA common-equity scope, complete holdings coverage, share of NAV, and when the dated information was made public. A complete holdings schedule must account for fund-of-fund exposure before it can establish an exact zero. Record the page, section or filing field so a reviewer can retrace the figure. A link and a manually entered number alone cannot establish the claim.

The manifest trust boundary is the deployer's protected configuration. Keep it separate from user inputs, and set its expected SHA-256 digest after reviewing the evidence. The application matches the manifest bytes to the pinned digest, bounds the file to 64 KiB and 64 records, and checks each selected record again at the independent review. It performs no document downloads or parsing on the audit path. The source document hash and locator describe what the operator verified. A hash protects the reviewed bytes against replacement and does not certify the contents of an arbitrary source.

Configure these environment variables before starting Streamlit.

| Variable | Value |
|---|---|
| `DATATHON_ISSUER_CATALOG` | Path to the operator-reviewed JSON manifest |
| `DATATHON_ISSUER_CATALOG_SHA256` | Lower-case SHA-256 digest of its exact bytes, computed after review |

The manifest has exactly three keys.

| Key | Value |
|---|---|
| `issuer_id` | `CUSIP:67066G104` |
| `scope` | `NVIDIA common equity as a fraction of fund net assets` |
| `disclosures` | List of reviewed disclosure records |

Each record has the fields below.

| Field | Value |
|---|---|
| `id` | Unique lowercase identifier, up to 64 characters, with digits, hyphens and underscores allowed |
| `ticker` | Fund ticker as used in the portfolio |
| `as_of`, `published_on` | Holding observation and publication dates in YYYY-MM-DD format |
| `weight` | NVIDIA fraction of fund NAV from 0 to 1 |
| `url` | HTTPS source link |
| `source` | Issuer or regulator and document description |
| `source_document_sha256` | Lower-case SHA-256 digest of the reviewed source document |
| `source_locator` | Page, table, filing field or equivalent section used to determine the weight |

Open **Amira · issuer exposure**, confirm the displayed rules and select **Identify required issuer disclosures**. Select the qualifying catalog records, at most one per unresolved fund, and choose **Re-audit reviewed disclosures**. Compare the separate audit with the original and download the review record. If the catalog cannot be verified or coverage remains incomplete, the UI preserves the existing evidence status.

The regression tests use labeled synthetic disclosure records only to verify the workflow. They cover a partial re-audit that remains unresolved and a complete re-audit that admits a full-size alternative under the same policy. The original ZST.TO-funded proposal still fails. No simulated holdings records are used as evidence in the application.

```bash
python -m unittest tests.test_issuer_reaudit tests.test_counterfactual tests.test_app
```
