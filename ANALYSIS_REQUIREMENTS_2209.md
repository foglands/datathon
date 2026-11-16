# Analysis reliability revision — requirements and implementation

Source: the user's `22.09` document, received 2026-11-16 UTC. This revision concerns the production investment-assistant workflow. Interface and repository documentation remain English. The official personas remain test fixtures only.

## Diagnosis of the prior path

The customer path already used Bedrock intake/planning, dated public observations, independently checked Python calculations, synthesis and a separate model review. Its missing contracts were substantive: selecting a tool was not a verifiable completion condition; review feedback disabled further investigation; paragraph-level Boolean review did not locate unsupported claims; different wording could create false profile conflicts; follow-ups were concatenated text; and a report with prices but no accepted answer could be labeled ready.

## Requirement traceability

| Document requirement | Production implementation | Verification |
| --- | --- | --- |
| Inspect the actual input-to-page path | `customer_workflow.research_question` calls the new planner, task executor, argument synthesizer and reviewer | Workflow tests invoke this entry point, not just helpers |
| Observable task completion | `inquiry_contracts.Task` records question, relevance, inputs, expected outputs and measures, scope, completion condition, actual result and remaining gap | A successful asset-history call cannot complete a portfolio comparison |
| Honest tool capabilities | Structured catalog lists inputs, outputs, supported scope and limitations | Unsupported outputs stay missing; review cannot mark them complete |
| Bounded adaptive evidence gathering | Shared request budget; bounded model calls, source calls, tools, investigation rounds and format repairs; request-local cache keyed by tool and explicit input | New evidence remains available after semantic rejection; duplicate calls reuse evidence |
| Stop without pretending completion | No-new-information stop, partial findings and explicit unresolved task/request status | Supported local analysis survives a failed main claim or local defect |
| Structured arguments before final prose | Each displayed claim records type, citations, client context, relevance, assumptions and limitations | Final paragraphs are rendered from these claims; no additional unreviewed model paragraph |
| Evidence scope | Object, metric definition, currency, unit, dates, source, method and coverage accompany structured facts or complete qualified tool quotations | Wrong-object references and unaligned comparisons are rejected |
| Separate deterministic and semantic checks | Python validates quantities, references and declared scope; separate model call evaluates semantic support | True evidence with an unsupported inference is classified independently from reference validity |
| Specific repair feedback | Per-claim support status, defect category, local/conclusion severity, reason and retrieve/calculate/narrow/delete action | Reviewer rejection can trigger a different tool before revised synthesis |
| No fixed investment verdicts | Planner and synthesizer operate on the question and evidence; no persona, occupation, age, horizon or largest-risk verdict table | Numerical invariance and material context tests; model interpretation remains fallible |
| Generic security resolution | Public security search, candidate provenance, plausible spelling/name variants, explicit listing ambiguity and chart identity verification | Unrelated company and dual-market fixtures; no company-to-ticker lookup table added |
| Conversation updates | Versioned statements and explicit add/replace/retract/repeat/conflict events with literal excerpts; asset additions preserve earlier holdings and considered assets | Corrected fields replace active values, retractions become unknown, compatible wording is not automatically a conflict |
| Honest degradation | Existing state survives model outage; local recovery cannot delete prior fields | Failure-path state tests and partial-result UI |
| Diverse acceptance | Code-authored numerical/task/state oracles plus real Bedrock execution | See `submission/analysis-validation-2209.md`; tests are not all scored by the answer model |
| Before/after comparison | Preserved prior source, common model and frozen provider observations, explicit invocation/time budgets | Raw results and failures saved; no fabricated aggregate improvement score |

## Production responsibilities

`customer_agents.py` extracts literal statements and state update operations. `customer_state.py` preserves their history. `customer_data.py` resolves instruments and obtains dated data. `customer_workflow.py` owns the request. `inquiry_contracts.py` defines evidence/task boundaries and budgets. `customer_tools.py` runs selected computations and distinguishes evidence availability from completed analysis. `inquiry_engine.py` synthesizes arguments, reviews each claim and task, requests further evidence when feasible, and releases a complete or partial answer. `customer_view.py` and `customer_report.py` display the same completion limits. `revision_validation.py` supplies an opt-in reproducible comparison in the reference workspace.

The older `customer_reasoning.synthesize` remains a compatibility/reference implementation. The production workflow imports `inquiry_engine.synthesize_inquiry`; merely retaining an older function does not route customer requests through it.

## Research references and limits

- [FinResearchBench](https://arxiv.org/abs/2507.16248): motivates evaluating the argument/task structure, not just report fluency. Its judge framework is not imported as a correctness guarantee.
- [ReAct](https://arxiv.org/abs/2210.03629): motivates alternating evidence acquisition with interpretation. This implementation records observable actions and short argument summaries, not private reasoning traces.
- [STORM](https://aclanthology.org/2024.naacl-long.347/): motivates asking which perspectives and missing evidence could change the answer. It does not justify inventing opposing evidence.
- [ALCE](https://aclanthology.org/2023.emnlp-main.398/): motivates distinguishing citation presence from support and coverage. The project does not claim to reproduce the paper's benchmark scores.
- [Large Language Models Cannot Self-Correct Reasoning Yet](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8b4add8b0aa8749d80a34ca5d941c355-Abstract-Conference.html): motivates actionable external evidence and deterministic checks instead of repeated unsupported rewriting. A second model call is not objective proof.

## Scope boundaries

The customer tool catalog exposes standalone historical analysis and compatible product comparisons. It explicitly does not expose a full before/after portfolio solver, comprehensive fund look-through, company fundamentals or news research. Requests requiring these outputs must remain partial, even when other tasks succeed. The pre-existing reference workbench's portfolio replay is not silently substituted for an incompletely specified customer portfolio.

Numerical quotation validation cannot by itself verify natural-language meaning. Semantic review can still miss errors. Security-search ranking and data availability remain dependent on external sources. Currency support is currently CAD/USD for conversions; unknown currency is never inferred from a bare dollar sign. Five years of public history do not support longer historical holding-period claims. Finite tests cannot establish universal generalization.

## Reliability details discovered during live execution

- Exact Python quantities may be quoted directly; `numeric_bindings` records which cited calculation or active customer statement supports each quantity. Percent units, signs, full dates and currency labels are checked. Optional full-quotation tokens remain available, but are not mandatory.
- Model review receives the current claim/evidence snapshot, without prior rejected answers or stale format feedback. Suspected arithmetic problems can trigger an independent Python recheck, including an independent count of overlapping daily-start windows.
- Tool results expose the measures actually computed. Short histories do not claim complete long-window or stress statistics. Returned min/max does not fulfill an explicitly required median.
- A horizon task can quote a particular user-stated duration. Distinct periods receive distinct cache keys and evidence IDs; a near-term withdrawal must not silently receive the long-term goal's window.
- Review references can cite customer statements as well as market/calculation evidence. Missing support is a valid review finding; the reviewer need not invent a source.
- Assumptions and scope limits used to qualify the main judgment are displayed beside that judgment and checked with its numeric quotations.

- A conditional claim with an outstanding repair is not accepted or retained as a supported conclusion. Numeric provenance applies to argument metadata as well as the visible paragraph. Explicit missing statistics in task prose cannot be hidden by omitting them from the declared measure list.
- Exact repetitions of prior known facts retain their old source and turn. New or changed facts still need current-message evidence; a failed update does not commit a partial state or prevent a validated retry.
