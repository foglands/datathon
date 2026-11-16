# Final repository verification

## Official case examples and submission update (November 16, 2026)

Three sidebar questions adapt the official case brief's investor situations (English edition, pp. 5–7). The current customer interface test exercises all three selections. Each fills the exact editable question, produces no report and makes no research call until the separate analysis action.

The full suite with the official organizer archive passed **578 tests with zero skips** on Linux Python 3.12 in 87.618 seconds. The seven customer interface tests also passed separately. The one-page summary and five-page technical guide were rebuilt from Markdown and reviewed visually. Current documentation links and installed dependency compatibility were checked. This regression uses local calculations and test fixtures. Hosted results and earlier live AWS evidence are recorded separately below.

The [earlier machine-readable results and tested-file hashes](final-verification.json) identify the earlier customer-only baseline based on `de17408bd400f465ddbe9d9de1ae4bcea06a1b1c`.

## Customer interface follow-up (Windows, November 16)

The customer entry point now uses `datathon/customer_ui.py` and `customer_ui.css`. The reviewed conclusion occupies the first result area, followed by the submitted question and evidence tabs. Promotional headlines and empty argument cards have been removed. Sidebar examples only fill the composer; they do not start a run.

A local browser trial of the AMD / 3,000 CAD / possible two-year withdrawal question first exposed invalid numeric signs/units and reference IDs during synthesis. After improving fact-quotation instructions, repair feedback and review-budget reservation, a fresh run displayed a reviewed conclusion, supporting evidence, counterpoints and a follow-up. The charts and evidence tabs were exercised. This is one observed live success, not a generalization or consistency claim. Hosted verification for the merged release is recorded separately below.

Targeted fixture validation: **71 tests passed** on Windows Python 3.10, including conclusion placement, context submission, empty/one-sided/withheld results, report tampering, signed quotations and completion-budget reservation. The restricted shell cannot create the loopback socket used by the normal Windows event loop; the local test harness replaced only event-loop wakeup/polling for these fixture tests. It did not make live network calls. Browser validation used the already running application and its real service configuration. Compilation and whitespace checks passed.

## Stash merge follow-up (Windows, November 16)

Resolved the two stash-restore conflicts by retaining the newer completion-budget logic and customer UI tests. Kept the archive-first provider, export wording and source hash display; did not restore the obsolete homepage or persona-based example buttons. The original stash patch and pre-merge files were saved outside the repository before reconciliation.

Corrected archive share sizing to use raw `close`, keeping `adj_close` for historical returns; adjusted-only inputs withhold share sizing. Public name resolution cannot bypass archive prices, and fallback coverage metadata is included in the asset fingerprint. **80 targeted fixture tests passed**, including four new archive-merge checks, using the same restricted-host test harness described above. Python compilation passed. Local Git index updates are completed through GitHub Desktop because this shell has read-only access to repository metadata.

## Deployment and conclusion follow-up (November 16)

The stash reconciliation was published as `81a034b9ce155ba82787af43e6306d8e3fee9022` to both the default and Streamlit deployment branches. The deployed customer homepage and a real AMD request were exercised at https://alphaforge-datathon.streamlit.app/. Public price/FX evidence was returned. The cloud app reported no usable AWS credentials, so live cloud model conclusions are **not** verified; the app retained checked evidence and showed the service reason. Local AWS success does not establish cloud AWS availability.

The subsequent conclusion change separates a direct bounded assessment from its detailed figures and requires independent review to assess decision relevance as well as factual support. Model-facing claim references are restricted to the evidence and context IDs available in that run. It does not impose a verdict from persona, horizon or willingness. The 81 targeted fixture tests pass, including rejection of an expanded evidence dump in the main conclusion. The v4 contract invalidates cached results from the older output format; live answer quality is evaluated separately.

## Earlier local results

| Check | Observed result |
| --- | --- |
| Full organizer-data regression | **562 passed, zero skips**, 65.989 seconds, Python 3.10 on macOS |
| Without organizer-data variables | **469 passed, 93 skipped** out of 562 discovered, 4.930 seconds |
| Offline reference CLI | **6/6** expected outcomes, including ambiguity, missing evidence and injected tampering |
| Dependency compatibility | `python -m pip check`: no broken requirements |
| Customer UI | Historical browser check: one question field, research action and optional context; the current sidebar-example layout is documented in the follow-up above |
| Developer UI regression | Reference workflows run through the separate `validation_app.py`; official-data UI regressions passed |
| PDFs | One-page summary and four-page technical guide regenerated; all five rendered pages visually inspected |
| Repository checks | Local documentation links resolve; whitespace check passed; credential-pattern scan found only a fixed synthetic regression sentinel; no unresolved matches |

The full regression output is [final-regression.log](final-regression.log). Tests use local calculations and mocked service clients. Expected failure cases passing means the application handled those failures as specified; it does not mean their investment proposals passed a rule.

## Reproduction

```bash
python -m pip install -r requirements.txt
python -m pip check
export DATATHON_STARTER_PATH="/absolute/path/to/Datathon2026.zip"
export DATATHON_FULL_STARTER_PATH="$DATATHON_STARTER_PATH"
python -m unittest discover -s tests -v
python -m datathon --data "$DATATHON_STARTER_PATH" --case all --mode offline --stress --report outputs/offline.json
python scripts/render_submission.py
```

Use `python -m streamlit run app.py` for customers and `python -m streamlit run validation_app.py` for the separate developer workbench. The [running guide](../docs/RUNNING.md) covers setup and troubleshooting.

## CI scope

The GitHub workflow installs pinned dependencies and runs the suite on Python 3.10 with no cloud credentials or organizer archive. Its run status is available in [GitHub Actions](https://github.com/foglands/datathon/actions). Data-dependent skips are expected and are not counted as full-data acceptance. The local results above do not assert that a remote workflow has run successfully. The first clean Linux run at `301042d` exposed one missing test dependency: `pypdf`. It is now explicitly pinned to the same 7.1.0 version used locally; the PDF extraction check and dependency compatibility check passed after the correction. The initial failed run remains visible in Actions. The follow-up commit triggers a fresh complete CI run.

## What this finalization does not establish

No new live Bedrock quality trial was run for the documentation and navigation cleanup. Existing source-qualified evidence is retained in [analysis-validation-2209.md](analysis-validation-2209.md) and [reasoning-validation.md](reasoning-validation.md). Paraphrase/irrelevant-detail consistency and fallible semantic review remain open. No universal model correctness, investment suitability or current credential validity is asserted.

The old MP4 remains a recording of an earlier revision. A fresh customer-flow video still needs recording; the [current script](demo-script.md) is ready. [submission/README.md](README.md) identifies current and historical artifacts.
