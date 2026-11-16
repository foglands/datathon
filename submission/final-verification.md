# Final repository verification

November 16, 2026. Application baseline: `de17408bd400f465ddbe9d9de1ae4bcea06a1b1c`, plus the customer-only entry-point changes in this finalization commit. [Machine-readable results and tested-file hashes](final-verification.json) identify the checked source without relying on a mutable branch name.

## Customer interface follow-up (Windows, November 16)

The customer entry point now uses `datathon/customer_ui.py` and `customer_ui.css`. The reviewed conclusion occupies the first result area, followed by the submitted question and evidence tabs. Promotional headlines and empty argument cards have been removed. Sidebar examples only fill the composer; they do not start a run.

A local browser trial of the AMD / 3,000 CAD / possible two-year withdrawal question first exposed invalid numeric signs/units and reference IDs during synthesis. After improving fact-quotation instructions, repair feedback and review-budget reservation, a fresh run displayed a reviewed conclusion, supporting evidence, counterpoints and a follow-up. The charts and evidence tabs were exercised. This is one observed live success, not a generalization or consistency claim. Hosted deployment has not been updated by this local change.

Targeted fixture validation: **71 tests passed** on Windows Python 3.10, including conclusion placement, context submission, empty/one-sided/withheld results, report tampering, signed quotations and completion-budget reservation. The restricted shell cannot create the loopback socket used by the normal Windows event loop; the local test harness replaced only event-loop wakeup/polling for these fixture tests. It did not make live network calls. Browser validation used the already running application and its real service configuration. Compilation and whitespace checks passed.

## Local results

| Check | Observed result |
| --- | --- |
| Full organizer-data regression | **562 passed, zero skips**, 65.989 seconds, Python 3.10 on macOS |
| Without organizer-data variables | **469 passed, 93 skipped** out of 562 discovered, 4.930 seconds |
| Offline reference CLI | **6/6** expected outcomes, including ambiguity, missing evidence and injected tampering |
| Dependency compatibility | `python -m pip check`: no broken requirements |
| Customer UI | Browser confirmed one question field, research action and optional context; no preset example buttons or Reference cases navigation |
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
