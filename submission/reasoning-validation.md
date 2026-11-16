# Contextual inquiry acceptance

This revision replaces online evidence sorting with model-led planning, bounded follow-up tool use, synthesis and independent review. The prior `customer-validation.md` describes the earlier workspace; its 522-test acceptance does not validate this change.

## Automated checks

The final full suite passed **534 tests** in **83.935 seconds**, using the complete starter archive. Subsequent regressions cover date-range parsing, uncomputed cross-unit comparisons, analysis-question contamination, cited client-input quantities and exact CPI observation windows. Customer inference settings and removal of operational noise from planning are also checked.

New tests verify that optional fields reach the full analysis context; a model can request portfolio evidence after seeing initial results; a reviewer can reject an answer for ignoring a material condition and force a repair; a second rejection withholds the conclusion; no numerical breach forces a lead conclusion; numerical placeholders must originate in cited verified evidence; name/paraphrase/unrelated-detail changes do not alter the deterministic holding-period calculation; and the conclusion precedes evidence tables.

The mocked orchestration tests establish program behavior, not model semantic quality. Live acceptance is recorded separately below.

## Runtime and bounded scope

Planning selects at most four evidence tools. Synthesis can request two more batches of at most two unused tools. Each model stage has a 45-second, two-HTTP-attempt and observed-token budget. The six-turn synthesis budget reserves up to two investigation batches, two format corrections and two reviewed answers; format correction cannot consume the reserved review repair. One rejected answer can be revised and reviewed once. The UI shows evidence only if no reviewed answer is available. These limits prevent unbounded loops; they do not guarantee a successful interpretation of every request.

All calculated financial values come from Python. Model-supplied numeric placeholders resolve only to exact strings in cited checked evidence. Direct numeric quotations must match those values or an explicitly cited extracted client input; comma/decimal formatting does not change the underlying value. Proposed analysis questions do not become numeric evidence. A separate semantic audit must still validate meaning and distinguish an input from an outcome. Goals and qualitative risk willingness do not become numerical thresholds. Explicit rules remain visible facts without forcing an answer order.

A holding-period tool now checks overlapping outcomes for a single stated month/year horizon, using independently verified arithmetic. It does not extrapolate beyond history or interpret overlapping outcomes as future probabilities. Portfolio-context checks preserve incomplete holdings rather than inventing weights or declaring diversification.

Customer inference uses temperature 0, and planning receives investment facts rather than request IDs, execution traces or a generated intake follow-up. This reduces unrelated sampling/input variation; it does not guarantee identical answers or semantic equivalence. Purchasing-power percentages must retain their exact CPI-aligned observation window rather than inherit a different full-price-history window.

## Live paired acceptance

The Reference cases → Reasoning acceptance workflow uses an unseen MSFT question and four transformations: a changed name, a paraphrase, an irrelevant hobby and optional tuition-withdrawal/loss-capacity details. One cached public-data snapshot is reused so source movements do not confound the comparison. Each answer must pass its own review; independent paired reviews then check semantic invariance or justified sensitivity. Raw provider price arrays and credentials are excluded from the compact evidence artifact.

The final five-case development run returned five independently accepted answers. The separate paired evaluator passed **2 of 4** comparisons: name invariance and the material tuition-withdrawal change. It failed paraphrase and irrelevant-detail invariance. All five requests retained identical core historical return/drawdown figures on the frozen observations. See [the actual results and traces](reasoning-live-acceptance.json).

The paraphrase shifted emphasis from qualified historical compatibility to inability to assess alignment without a precise horizon. The irrelevant-detail answer omitted purchasing-power evidence emphasized in the baseline. The paired evaluator considered these material; its judgments are retained as failures rather than relabeled as passes. Tool lists and prose need not match, but substantive scope and qualifications still need greater consistency.

The material change did affect the conclusion: the answer explained the fixed tuition obligation and cited the historical funding shortfall, rather than recycling the growth-focused baseline. Manual inspection also caught an overly favorable liquidity inference in that answer, so the final code adds a rejection for favorable execution-liquidity classifications based solely on the volume proxy. It also rejects new time cutoffs such as an unstated three-year boundary. These later guards have regression coverage; the saved five-case artifact precedes them and is not a claim that all its prose would pass the final validators.

**Generalization acceptance is not complete.** These requests began as non-persona examples and were subsequently reused during debugging; they are development regression cases, not an untouched held-out benchmark. A new VTI home-purchase question is recorded separately. Finite model evaluations do not prove universal personalization or language invariance.

## Failure discovered during live validation

The first five-case run did not produce accepted answers. A diagnostic trace showed `ReadTimeoutError` in the synthesis request: the inherited transport read timeout was 12 seconds. The new roles now have a separate 40-second read timeout inside the 45-second stage budget, and bounded answer length. Legacy roles retain their existing timeout. The failed run is retained separately; it is not counted as a passing semantic evaluation.

Further failures are recorded in [reasoning-failures.json](reasoning-failures.json). Manual inspection caught an incorrect days/months comparison that both model reviewers had accepted, plus unjustified zero-loss-capacity language. Numeric quotation checks alone cannot establish inference validity. The date parser and a specific cross-unit comparison guard were added, cash evidence now includes actual event dates, and review instructions explicitly cover unsupported thresholds and scope. The guard covers digit-form days/months comparison patterns; it is not a general natural-language theorem checker. Runtime role-instruction hashes make the contract used in a live call observable.

The third run also failed invariance checks: some answers used different qualifications and analysis scope. The paired reviewer now distinguishes substantive stance/caveats from optional additional calculations; it still fails an actual change in financial judgment or material uncertainty. Its judgment remains model based and requires inspection. Failed runs are retained rather than presented as passes.

## Fresh held-out question on the final code

A new request concerned 5,700 CAD in VTI for a home purchase in seven years, with stated willingness but undecided loss capacity. It was not used to tune the preceding fixes. The report limited its conclusion because the available history cannot cover the stated 84-month horizon, separated full-price and CPI-aligned periods, and preserved unknown capacity. The first proposed answer was rejected; a bounded repair passed the independent review. This validates one fresh question and a real review/repair cycle, not general language invariance. See [the observed answer and trace](reasoning-heldout-vti.json).

Follow-up tool requests after initial evidence are covered by program tests; the recorded live cases selected their evidence tools during planning. Do not present these cases as live proof of a subsequent investigative tool call.

The browser confirmed that the conclusion and both sides of the analysis appear before profile details, metrics and charts. [Customer report screenshot](contextual-reasoning.jpg).
