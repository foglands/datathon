# Contextual reasoning: requested changes and acceptance

> Current analysis-contract revision: [22.09 requirements and implementation](ANALYSIS_REQUIREMENTS_2209.md). Validation and remaining gaps: [revision validation](submission/analysis-validation-2209.md). Earlier acceptance records below describe their recorded revision, not a claim of current universal correctness.


This records the user's latest product direction and supersedes earlier persona-driven or fixed risk-priority choices. Product language remains English. Amira, Mateo and Robert are test inputs only.

## User problem

Adding material optional information previously left the opinion and conclusion effectively unchanged. The product should answer the user's actual investment question, show its conclusion first, and explain which conditions matter and why.

## Required responsibilities

| Stage | Responsibility |
| --- | --- |
| Understand | Identify the idea, objective, explicit requests and unknowns from the current question. |
| Plan | Propose the claims to verify and the evidence needed to answer them. |
| Execute | Fetch dated data, calculate in Python, inspect explicit constraints and compare supported scenarios. |
| Synthesize | Weigh support, counterevidence, trade-offs and gaps in relation to the question. Request more evidence when useful. |
| Review | Independently check relevance, citations, material conflicts, uncertainty and scope. |

Client context informs these stages; it is not a persona classifier. Risk metrics are tools selected for the question. Missing holdings can require a narrower conclusion or a follow-up. An irrelevant risk should not trigger a mandatory full checklist.

## Evidence discipline

- Python supplies financial calculations. The model may quote only verified values from cited evidence.
- Unstated client information remains unknown. No automatic loss threshold, horizon or allocation.
- Substantive conclusions link to client statements, sourced data or checked computations.
- Conclusions include supporting evidence, opposing evidence and important missing information.
- Insufficient evidence restricts the conclusion; it does not authorize an invented answer.
- No fixed mapping such as short horizon → rejection, high willingness → growth emphasis, or largest risk → lead conclusion.

## Acceptance

Use questions beyond the three official personas. Changing a name must not affect financial treatment; paraphrases should preserve meaning; new material conditions should be explicitly used and any changed judgment explained; irrelevant details should not change judgment. A changed conclusion is not mandatory when the evidence justifies the same conclusion with an explanation.

Implementation and observed limits are recorded in [CUSTOMER_RESEARCH.md](CUSTOMER_RESEARCH.md) and [reasoning validation](submission/reasoning-validation.md). These are requirements, not a claim that finite tests establish universal generalization.

## Current acceptance status

The five-stage inquiry and conclusion-first report are implemented. Complete client fields, unknowns and conflicts now reach planning, synthesis and review. Evidence tools, format corrections and review repairs have separate bounded allowances.

The final development comparison passed name invariance and material-context sensitivity, but failed paraphrase and irrelevant-detail invariance. **Full generalization acceptance remains open.** The next work should separate the scope of historical evidence from the overall conditional judgment, preserve that distinction across synonymous questions, and test fresh requests without tuning the outcome to a persona or preset verdict. Model review is a fallible safeguard, not a proof of semantic correctness.
