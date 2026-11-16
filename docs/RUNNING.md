# Running and reproducing AlphaForge

## Environment

Use Python 3.10+ and install `requirements.txt` in a virtual environment. Run commands from the repository root.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Windows PowerShell activation: `.venv\Scripts\Activate.ps1`. PowerShell environment syntax is `$env:DATATHON_AWS_REGION = "us-east-1"`; examples here use bash/zsh. The app does not automatically load a `.env` file.

## AWS configuration

Use an authorized AWS session or profile in the environment that launches Streamlit. Temporary sessions need their session token as well as access-key credentials. Do not print or commit them. Model calls can incur AWS charges; the session must be active and permitted to invoke the configured model.

| Variable | Default / purpose |
| --- | --- |
| `DATATHON_AWS_REGION` | `us-east-1` |
| `DATATHON_PROFILE_MODEL_ID` | `global.anthropic.claude-sonnet-4-5-20250929-v1:0`; customer intake, planner, analyst and reviewer, plus workbench drafting |
| `DATATHON_AUDIT_MODEL_ID` | `us.amazon.nova-2-lite-v1:0`; legacy audit roles |
| `AWS_PROFILE` | Optional existing profile through the normal AWS provider chain |
| `DATATHON_AUDIT_BUCKET` | Optional existing versioned S3 bucket for historical-workbench storage |

Set the AWS environment before launching Streamlit. In PowerShell, use `$env:DATATHON_AWS_REGION = "us-east-1"`. A temporary AWS session uses `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` from the same session. A configured AWS profile can also provide credentials. Use the [hosted deployment guide](DEPLOYMENT.md) for Streamlit Cloud.

The customer analyst and reviewer are separate invocations of the configured model, not independently trained models. Agreement does not prove semantic correctness. Numerical checks run separately in Python.

Customer inquiry defaults are 240 seconds, 10 model-role calls, 8 tool calls and 12 source calls, with bounded investigations, format repairs and reviews. These are execution limits, not a latency guarantee. Source and per-stage limits also apply. `inquiry_contracts.py` is authoritative.

```bash
python -m datathon.runtime_check --check-dns
```

This diagnoses provider availability and DNS without invoking AWS. Missing organizer data may be reported even if only public customer research is intended. Provider detection does not prove credentials are valid or a model is accessible; a successful live trace is separate evidence.

## Organizer archive and full-data validation

The archive is optional for public customer price research and required for complete historical regression. Obtain `Datathon2026.zip` or extracted `alphaforge_starter/` through the competition materials. The repository does not redistribute it. The loader expects all six starter CSV tables.

```bash
export DATATHON_STARTER_PATH="/absolute/path/to/Datathon2026.zip"
export DATATHON_FULL_STARTER_PATH="$DATATHON_STARTER_PATH"
python -m unittest discover -s tests -q
```

A complete extracted directory is also accepted. The second variable enables full-archive tests. Skipped official-data cases do not constitute full-data acceptance. Regression tests use local calculations and mocked services; live AWS credentials are not required.

For customer research, `DATATHON_STARTER_PATH` alone enables archive prices and FX. Use the three sidebar cases to test intake and dated disclosures. The organizer archive covers SPY, NVDA and TSLA, with disclosures supplying limited evidence for ESGU and IBIT. For Streamlit Cloud, a private approved ZIP can be configured using `DATATHON_PRICE_ARCHIVE_S3_URI` and `DATATHON_PRICE_ARCHIVE_SHA256`. The external adapter is opt-in for an authorized deployment. See the [hosting guide](DEPLOYMENT.md#market-data-for-the-hosted-app).

## Historical workbench and CLI

Run `python -m streamlit run validation_app.py` to open the separate developer workbench. Its **Reference cases → Historical decision workbench** view provides editable Compare/Evaluate/Audit inputs. `app.py` exposes no Reference cases navigation. Official personas are fictional examples, not production defaults.

```bash
python -m datathon --data "$DATATHON_STARTER_PATH" --case all --mode offline --stress --report outputs/offline.json
python -m datathon.decision_cli --example robert --data "$DATATHON_STARTER_PATH" --confirm --report outputs/robert.json --pdf outputs/robert.pdf --pdf-view audit
```

Read `examples/decision_requests/robert.json` before `--confirm`. Other examples are `amira` and `mateo`. A separately authorized search:

```bash
python -m datathon.decision_cli --example robert --data "$DATATHON_STARTER_PATH" --confirm --funding-sources QQQ,ZST.TO --authorize-search --report outputs/robert.json
```

This writes a separate search result. `--allow-smaller` extends size scope. Original-audit confirmation alone never authorizes search. See [workbench methods](historical-workbench.md).

## Optional integrations

Historical S3 export checks versioning and requires an ETag plus a non-null version ID. It does not create buckets or change access policies. Keep Block Public Access enabled. Permissions include `s3:GetBucketVersioning` and `s3:PutObject` on the selected bucket/prefix, plus applicable encryption-key permissions.

**Earlier assistant validation** retains a read-only Alpaca lookup using `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, optional `DATATHON_ALPACA_ACCOUNT` (paper or live) and `DATATHON_ALPACA_FEED` (iex, sip or delayed_sip). It is not required for the current research route or deterministic replay and places no orders.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing or expired AWS credentials | Refresh the authorized session, then launch the app from that shell. Another terminal cannot update a running process's environment. |
| Access denied / model unavailable | Confirm region and permissions for the exact model or inference profile. |
| Price or FX lookup unavailable | Check connectivity and visible provider errors. Endpoints may throttle or omit dates; missing data are not invented. |
| Listing ambiguity | Supply the requested ticker and exchange. |
| Partial / evidence-only research | Inspect unresolved tasks, source gaps and review feedback. Checked calculations may remain even when a conclusion is withheld. |
| Historical tests skip | Set both starter variables to the complete archive. |
| Old page or report after an update | Use Streamlit Rerun or refresh; rerun research for changed inputs. |

## Rebuild submission PDFs

```bash
python scripts/render_submission.py
```

This rebuilds the one-pager and technical-summary PDFs from their Markdown sources. Inspect rendered pages and keep the one-pager to one page. The MP4 and visual handout are historical artifacts; see the [submission index](../submission/README.md).
