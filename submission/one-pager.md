# AlphaForge AI
## An investment idea, examined with evidence

**PolyFinances Datathon 2026 | Banque Nationale and AWS**

### Problem and value

Investment questions begin with an idea and real conditions, not a professional risk dashboard. AlphaForge lets a user describe what they are considering, what the money is for and what is unknown. It returns a conclusion with evidence, charts, counterarguments and important gaps. The customer interface has one question field and optional context; validation tools live in a separate developer app.

### Agentic analysis

The workflow understands the question, plans the analysis, calls evidence tools, synthesizes a judgment and independently reviews it. Amazon Bedrock performs the language tasks through Strands handoffs. The analyst can request further evidence after seeing results; missing holdings or unsupported measures can narrow the answer or prompt clarification. Task completion is checked against actual outputs.

### Evidence discipline

Financial calculations belong to Python and receive separate numerical checks. Claims cite checked results or the user's own statements. Unprovided information remains unknown. Goals, willingness to take risk, loss capacity and withdrawal needs are separate; a name or persona never supplies a threshold or dictates a conclusion. Failed semantic review withholds the interpretation while retaining checked evidence.

### Data and demonstration

Dated public adjusted prices, Bank of Canada FX/CPI and qualified disclosures support historical risk, CAD conversion, explicit-weight portfolios, fixed withdrawal paths, purchasing power and selected bond measures. A fictional user considering CAD 3,000 in AMD can add a near-term withdrawal need; the assistant should explain which evidence becomes relevant without imposing a preset verdict. HTML export preserves charts and source references.

### Honest limits and validation

Quotes may be delayed. Historical observations do not predict performance or establish suitability. Complete fund look-through, fundamentals/news and unrestricted ESG research are unavailable; initial duration/credit coverage is a dated AGG extract. A volume ratio does not establish execution feasibility. No trades are placed.

Automated regression covers calculations, source/state contracts, authorization, tampering and interface behavior. Live generalization remains partial: paraphrase consistency and fallible semantic review are documented limitations. Official personas are test fixtures alongside other fictional questions, not production routes.

[Code and setup](https://github.com/foglands/datathon/tree/architecture-completion-20261115) | [Technical guide](technical-summary.md) | [Validation](final-verification.md)
