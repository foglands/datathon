# Submission and evidence index

**PolyFinances Datathon 2026 · Team 38 · Peng Peng, Shaoze Ying, Xuhan Liu**

The customer application is `app.py`. Developer/reference tools are in `validation_app.py`, separate from the customer UI. Repository documentation and product text are in English.

## Current deliverables

| Artifact | Purpose |
| --- | --- |
| [Repository README](../README.md) | Product overview, startup and navigation |
| [Running guide](../docs/RUNNING.md) | Configuration, organizer data, diagnostics and CLI reproduction |
| [Hosted customer app](https://alphaforge-datathon.streamlit.app/) | Streamlit deployment of the customer entry point |
| [One-pager](one-pager.md) / [PDF](one-pager.pdf) | Team 38, problem, architecture, worked evidence, supported capabilities and limits |
| [Technical documentation](technical-summary.md) / [PDF](technical-summary.pdf) | Current inquiry architecture, live AWS calls, financial methods, evidence and verification |
| [Demo script](demo-script.md) | Five-minute recording plan centered on the same retirement-risk case as both PDFs |
| [Final verification](final-verification.md) | Current regression and packaging checks |

The PDFs are generated from their adjacent Markdown by `python scripts/render_submission.py`.

## Validation chronology

| Record | What it establishes |
| --- | --- |
| [Analysis-contract revision](analysis-validation-2209.md) | Latest inquiry/state contracts, observed live failures, frozen-data comparison and unresolved review reliability |
| [Reasoning evaluation](reasoning-validation.md) | Earlier context-sensitive synthesis; name/material-context success and failed paraphrase/irrelevant-detail pairs |
| [Customer validation](customer-validation.md) | Earlier 522-test customer-workspace revision and live fictional research examples |
| [Historical verification](verification.md) | Earlier 474-test workbench revision and dated reference/AWS cohorts |
| [Historical architecture matrix](architecture-status.md) | Coverage of the earlier decision-workbench target, not a completion claim for the current customer route |

The `revision-*.json` and `reasoning-*.json` files retain sanitized development observations, including failures. They are not interchangeable proof of current correctness. `aws-proof-298e9b0.json`, `live-proof.json` and `architecture-acceptance.json` describe their recorded earlier executions. Exact request IDs demonstrate observed calls, not continued credential validity or service availability.

## Historical visual artifacts

`alphaforge-demo.mp4` records workbench revision `13ccc42`. The demo script describes the current customer workflow. The [earlier homepage screenshot](customer-homepage.jpg), `visual-handout.pdf`, the `architecture-*.jpg` images, `customer-workspace.jpg`, `customer-report.jpg`, `contextual-reasoning.jpg` and `analysis-report-2209.jpg` illustrate earlier revisions.

## Requirements and development history

The current acceptance requirements are [ANALYSIS_REQUIREMENTS_2209.md](../ANALYSIS_REQUIREMENTS_2209.md) and [REASONING_REQUIREMENTS.md](../REASONING_REQUIREMENTS.md). [CUSTOMER_RESEARCH.md](../CUSTOMER_RESEARCH.md) details tool/source boundaries.

Earlier planning notes (`plan.md`, `PROTOTYPE.md`, `BENCHMARK.md`, `AGENT_ITERATION.md`, `Datathon_Research_Brief.md`) preserve development context; they do not override the current customer workflow. See [CHANGELOG.md](../CHANGELOG.md) for the sequence of changes.
