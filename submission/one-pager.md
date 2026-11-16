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

Dated prices, Bank of Canada FX/CPI and qualified disclosures support historical risk, currency conversion, portfolios with stated weights, fixed withdrawals, purchasing power and selected bond measures. Three examples adapt the official cases: AI and Bitcoin with diversification, growth and stability with ESG preferences, and a popular stock before retirement. HTML export preserves charts and sources.

### Honest limits and validation

Quotes may be delayed. Historical observations do not predict performance or establish suitability. Complete fund look-through, fundamentals/news and unrestricted ESG research are unavailable; initial duration/credit coverage is a dated AGG extract. A volume ratio does not establish execution feasibility. No trades are placed.

Automated regression covers calculations, provenance, state, authorization, tampering and the interface. Live validation records inconsistent responses to paraphrases and errors in semantic review. Each example runs through the same analysis workflow as a question typed from scratch.

[Hosted app](https://alphaforge-datathon.streamlit.app/) | [Code and setup](https://github.com/foglands/datathon/tree/architecture-completion-20261115) | [Technical guide](technical-summary.md) | [Validation](final-verification.md)
