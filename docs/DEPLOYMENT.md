# Hosted customer application

The customer application is deployed at [https://alphaforge-datathon.streamlit.app/](https://alphaforge-datathon.streamlit.app/).

The November 16, 2026 verification covers the public customer workflow and successful hosted Bedrock Converse calls. See the [verification record](../submission/final-verification.md).

## Deployment configuration

| Field | Value |
| --- | --- |
| Repository | `foglands/datathon` (public) |
| Branch | `architecture-completion-20261115` |
| Main file | `app.py` |
| Python | 3.11 |
| Dependencies | Root `requirements.txt` |
| Audience | Reviewers need working access to the deployed app; repository visibility is separate |

Streamlit Community Cloud follows changes pushed to the deployment branch. Publish application updates to that branch and keep GitHub's default branch `agent-optimization` synchronized. Use `app.py` for the customer deployment and `validation_app.py` for local developer validation.

## Account and secrets

Sign in at [Streamlit Community Cloud](https://share.streamlit.io/), review the service terms, and connect GitHub when requested. Select Create app and use the fields above. The repository owner made this repository public for deployment; private-repository access is not required.

In Advanced settings, select Python 3.11 and enter runtime configuration using [.streamlit/secrets.example.toml](../.streamlit/secrets.example.toml) as the non-secret template. Root-level secrets become environment variables consumed by the existing AWS provider chain. Enter actual AWS credentials directly in the hosting Secrets editor, never in GitHub, source files, screenshots or chat.

Bedrock needs an active AWS session with permission to invoke the configured model. Put all three fields of a temporary session at the top level of the Secrets editor. Saving credentials in a local PowerShell session affects only processes started from that shell. Streamlit Cloud reads its own Secrets configuration after the update propagates. Refresh expired credentials in the same editor.

## Live web research

The Bedrock planner selects up to two research topics per request. The app uses public instrument names and topic phrases for [Amazon Bedrock AgentCore Web Search](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/web-search-api.html). It shows source links and search status under **Evidence & sources → Live web searches**. For an issuer filing lookup, the app can confirm filing metadata and dates directly against SEC EDGAR.

Grant the existing app AWS identity `bedrock-agentcore:InvokeWebSearch` on `arn:aws:bedrock-agentcore:us-east-1:aws:tool/web-search.v1`, or replace the region with the configured request region. The same AWS credentials sign both Converse and search. See the [AgentCore setup guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/web-search-api-get-started.html). Set `DATATHON_WEB_SEARCH="0"` to disable web research.

Search results provide document leads. Daily return, volatility, drawdown and backtests require a verified series with dates, listing currency and adjustment basis. The report identifies metrics the available data cannot support.

## Optional daily-price snapshot for reproducible runs

Live web research runs without an archive. An optional market snapshot supplies daily-price charts for reproducible runs using data approved for the intended audience and report exports. The ZIP uses the starter CSV schema and includes source URLs, access and reuse terms, dates, processing and limitations.

### Prepare and verify the snapshot

1. Export daily closing prices for SPY, NVDA, IBIT, ESGU and TSLA. Use one adjustment basis across the file. Prefer closes adjusted for splits and cash distributions for historical growth comparisons. The app can also compare split-adjusted price returns, with distributions excluded. Include the raw close only if it is available independently.
2. Prepare a directory with these three CSVs:

   | File | Columns |
   | --- | --- |
   | `prices_daily.csv` | `date,ticker,adj_close,currency`. Optional `close,volume,name`. Use ISO dates, one completed daily observation per ticker and date, and CAD or USD. |
   | `fx_usdcad_daily.csv` | `date,usdcad`. Source `FXUSDCAD` observations from the [Bank of Canada Valet API](https://www.bankofcanada.ca/valet-api-how-to/). Preserve its CAD-per-USD convention and missing days. |
   | `sources_metadata.csv` | `file,source,source_url,retrieved_on,terms_of_use,processing,limitations,price_basis`. Include entries for both data files and link to the applicable terms. For prices use `split_adjusted_price` or `split_and_cash_distribution_adjusted`. |

3. From the repository root run `python -m scripts.prepare_price_archive path/to/csvs path/to/prices.zip --verify-examples`. The command validates the input using the application's reader, checks the shared analysis window for each example, and prints the ZIP's SHA-256. Locally set `DATATHON_PRICE_ARCHIVE_PATH` to the resulting ZIP and run the customer app. The reference workbench uses its separate `DATATHON_STARTER_PATH`.

[Databento US Equities Mini](https://databento.com/blog/databento-us-equities-mini-now-available) is a purchase-on-demand candidate for daily bars whose provider explicitly permits external redistribution. Its documented history starts March 28, 2023 and it aggregates component venues. Check the account's coverage and historical data estimate before downloading. Daily bars and [corporate-action adjustment data](https://databento.com/corporate-actions) are separate products. Use an appropriately authorized adjustment series or a licensed export with the adjustments already applied.

### Publish the verified snapshot

Keep the approved ZIP in a private S3 bucket and grant the app's AWS identity read access to that single object. Enter `DATATHON_PRICE_ARCHIVE_S3_URI` and `DATATHON_PRICE_ARCHIVE_SHA256` in Secrets, using the exact digest of the ZIP. In PowerShell, `Get-FileHash -Algorithm SHA256 -LiteralPath <archive-path>` computes it locally. The app checks the digest before using the data and reads a ZIP of up to 32 MiB. Reports retain the underlying price CSV hash and observation period.

The external Yahoo adapter is disabled by default. Activate `DATATHON_PUBLIC_FALLBACK="1"` only with verified permission for automated access and for the intended use of results. See the [source qualification](../CUSTOMER_RESEARCH.md#sources-and-qualification).

## Verify a release

1. Open the [hosted app](https://alphaforge-datathon.streamlit.app/) after Streamlit updates.
2. Check the three example questions. **Apply question** should fill editable text before **Analyze my question** starts the run.
3. Run the three fictional cases. Check which assets were interpreted, the observed Bedrock status, data dates, checked calculations, conclusion status and report export.
4. Open **Evidence & sources → Research service verification** for the Bedrock Converse result and **Live web searches** for search status and links. Test a follow-up correction and record the result against the deployed revision.

Do not send reviewer invitations unless specifically requested. If the app is made publicly accessible, its model calls consume the configured AWS account's quota/budget. Public app access and uploading AWS credentials to a hosting provider require the account owner's approval.

## Platform documentation

- [Deploy a repository and choose Python](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Store runtime secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [App visibility and sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
