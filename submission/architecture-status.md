# Target architecture · Implementation status

This matrix compares the target specification with the current `decision_*` implementation. **Implemented** means executable code exists; it does not by itself mean a current live AWS acceptance run passed. **Partial** names the boundary. Historical tests and current remediation tests must remain separated in [verification.md](verification.md). Detailed source qualifications are in [DECISION_EVIDENCE.md](../DECISION_EVIDENCE.md).

## Architecture coverage

| Layer / target | Status | Evidence and current boundary |
| --- | --- | --- |
| Three historical actions | Implemented | `decision_workflow.py`: compare, evaluate and audit share confirmation and review; `decision_view.py` is the primary historical workspace. The earlier assistant is retained under Reference cases for regression comparison and is outside this historical engine. |
| Model draft → Python checks → user confirmation | Implemented with limits | `decision_intake.py` and `confirm_decision`; the model proposes structured fields, then literal numbers, tickers and structure are checked. Offline parsing remains a labeled fallback. This is not unrestricted language understanding. |
| Arbitrary language / EN-FR parity | Partial | The new model-assisted draft accepts original-language structured fields; EN/FR examples are supported and outputs stay English. Offline parsing has narrower coverage. The target 100-prompt bilingual acceptance and arbitrary-language correctness are not established. |
| Uniform profile and rule fields | Partial | General profile fields, `{asset_set,min,max}`, risk limits and trade units exist. Persona JSON files are separate. Literacy/task context is editable; comprehensive adaptation and all value-origin labels remain incomplete. |
| Generic symbols and allocations | Implemented for eligible data | General replay/funding accepts symbols as inputs. The legacy reference engine still contains demo tickers; the entire repository is not ticker-literal-free. |
| Frozen prices, hashes, row references and CAD conversion | Implemented | `decision_market.py` reconstructs source records and validates conversion. Provider accuracy and upstream adjustment quality remain external limitations. |
| Uploaded prices | Implemented with limits | Supplement missing eligible tickers using the same-date USD/CAD pipeline; source URL/date are user declarations, not authenticated provider attestations. |
| Knowledge-date gating | Implemented | Source publication/retrieval availability and observation cutoff are checked. Default is source availability, not an earlier final observation date. |
| Full, named and custom windows | Implemented with limits | Full shared history, 2022, early 2025, optional 2023 and custom dates. Independent calendars cover the archived windows; other windows disclose unverified coverage. |
| Extended historical metrics | Implemented | Terminal outcomes, drawdown, recovery/time underwater, rolling 12/36 months, volatility, worst complete month, signed contributions, FX decomposition and stress context; insufficient history yields unavailable values. |
| Independent metric implementation | Implemented | `decision_replay.py` includes a separate recomputation; market conversion and funding certificates have separate checks. Finite historical tests do not prove every possible input. |
| Multiple-source LP and certificates | Implemented with limits | Python `Fraction` simplex rather than the target SciPy implementation, with independent dual-optimality/Farkas-infeasibility certificate checks; explicit ticker bounds and supported historical risk metrics. Recovery-time search and non-ticker exposure constraints remain unassessed. |
| Dated issuer and sector evidence | Partial | Qualified disclosed/bounded/unknown intervals and source classifications; broad complete ETF look-through is unavailable. |
| GPFG screening | Partial | Dated named direct-issuer checks with exclusion/observation distinction. ETF constituent screening remains incomplete; not listed is not an ESG rating. |
| Top-N issuer and portfolio HHI | Not implemented | Current subject-specific exposure bounds do not constitute full portfolio issuer concentration coverage. |
| Independent exposure verification | Partial | A reviewed evidence-context digest detects mutation; exact-rational recomputation checks interval products/sums. Source-class coverage is separate from interval width. This does not independently re-read every original disclosure. |
| Governance checklist and profile tensions | Partial | Rule statuses, margins, unknown evidence, historical-only scope, review and authorization are exposed. Unsupported binding conditions stay unknown; user labels cannot alter verdicts. Profile tensions are bounded rules, not comprehensive suitability assessment. |
| One facts source and two views | Implemented with limits | Sealed reviewed report feeds explanation-first/metrics-first and JSON/PDF; the UI checks its binding before display. Complete per-number provenance and all origin/kind labels remain a tracked coverage requirement. |
| Model narrative + verification gate | Implemented with limits | At most 120 words and one or two approved references. Every sentence must exactly match an approved sentence or fixed allowed transition, and all selected-reference sentences must appear. Invalid prose is withdrawn while the template remains. This is strict approved-sentence composition, not unrestricted semantic verification. Current live acceptance remains separate. |
| Bounded question/challenge loop | Implemented with limits | `decision_challenge.py` reads reasons from the report or independently replays one confirmed field from the original decision; three rounds maximum and stop on verdict change. Changed policies need separate funding consent. Model selection of the new actions remains unverified. |
| Model disclosure selection | Not implemented as specified | Evidence eligibility is deterministic; no arbitrary-document selection benchmark is claimed. |
| Versioned S3 record | Implemented, live evidence required | Optional `DATATHON_AUDIT_BUCKET`; versioning precheck and ETag/version receipt. Existence of code or a mocked client does not prove a real upload. |
| Knowledge Base / Guardrails / CloudWatch / Step Functions | Not deployed by this implementation | These remain target services. Existing local checks and traces are not presented as managed AWS services. Object Lock is also optional future work. |
| Complete target evaluation | Partial | Formula, authorization, tamper, data and prior AWS cohorts exist. New-route bilingual generalization, arbitrary-rule coverage and external-user comprehension remain unestablished. |
| Current competition documents and video | Partial | English source documents, the five-page technical PDF and one-page summary PDF are updated; all six PDF pages were rendered and visually checked. A new actual screen recording remains outstanding; the existing MP4 is attributed to `13ccc42`. |

## Five target conversations

| Target | Supported now | Remaining boundary |
| --- | --- | --- |
| Robert | Ground/confirm a trade and loss definition; original proposal; separate generic funding search; reviewed metrics and certificates | Current local browser acceptance covers the typed draft, confirmed original failure, separately authorized funding and accepted checked narrative; see the version-qualified verification record. Model-selected challenge actions and unrestricted prose verification are not claimed complete. |
| Amira | Compare confirmed assets or allocations; show common-window risk and known subject-specific exposures | “Adding” alternatives need complete starting portfolios/funding to establish portfolio impact. Full issuer overlap, HHI and diversification coverage are incomplete. |
| Mateo | Apply a named controversy-list rule to qualified direct-issuer evidence; preserve unknown ETF weight | No complete SPY/QQQ constituent controversy percentage is asserted without dated look-through. |
| AMD / out-of-archive | Keep missing context explicit, accept a qualified supplementary price CSV, and run the generic engine when inputs are sufficient | A 200-share quantity alone does not define portfolio weights. Current quote research is separate from frozen replay. |
| French request | Model-assisted drafting accepts original French excerpts and structured values; the interface and result remain English | Exact target trade, bond-look-through coverage and the full bilingual benchmark still need documented acceptance; offline French coverage is narrower. |

## Conditions for completion claims

A full target-completion claim requires all five conversations to pass on the recorded revision, complete numeric/source traceability, no unsafe publication in the fault cohort, a current demonstrated AWS operation, and truthful disclosure of missing evidence. The target also asks for a bilingual interpretation study and external comprehension measurement. They must be performed and reported, not inferred from unit-test counts.
