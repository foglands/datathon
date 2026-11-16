# AlphaForge AI
## Investment research with evidence you can inspect

**PolyFinances Datathon 2026 · Team 38**

**Team members · Peng Peng, Shaoze Ying, Xuhan Liu**

### The problem

A promising investment can look very different when the investor needs the money soon, already owns similar assets, or has limits on acceptable losses. AlphaForge turns a plain-language question into traceable research tied to the user's stated goals, holdings, time horizon and constraints.

### How AlphaForge works

Bedrock Converse understands the question and plans the investigation. AgentCore Web Search retrieves relevant public source links during the request. Python computes financial measures from qualified data and independently checks the figures. The analyst weighs supporting and opposing evidence, and a separate Bedrock call reviews the claims and completed tasks. The report shows sources, assumptions, unresolved questions and the actual review status.

### What the prototype can show

**Retirement risk.** An [SEC-filed price table](https://www.sec.gov/Archives/edgar/data/1114446/000111444623000724/tc8172999f_1fwp.htm) supports a 73.39% Tesla decline between split-adjusted closing prices in Q4 2021 and Q4 2022. The live app finds additional sources and marks full-history measures as unresolved while the daily series remains unverified.

**Diversification and ESG.** Dated disclosures establish SPY's NVIDIA overlap, IBIT's Bitcoin exposure, and differences between ESGU's screening method and SPY's index objective. Quantifying portfolio changes or checking present-day exclusions requires further holdings and screening evidence.

### Analysis and audit capabilities

With qualified inputs, the system supports returns, drawdowns, volatility, recovery, rolling holding-period outcomes, stress replay, CAD/USD conversion, Canadian purchasing power, stated-weight portfolios and specified withdrawals. It can also show dated exposure and screening evidence, bond duration and credit, and a traded-volume proxy. The developer workbench supports independently reviewed portfolio replay and explicitly authorized funding searches.

### Validation and limits

The public app demonstrated Bedrock Converse and live AgentCore search. The full regression suite passed 591 tests. Reports preserve checked evidence when stronger claims cannot be supported. Complete ETF holdings, certified daily coverage and some provider data remain gaps. AlphaForge is a research prototype and places no trades.

[Live app](https://alphaforge-datathon.streamlit.app/) · [GitHub](https://github.com/foglands/datathon) · [Technical PDF](technical-summary.pdf) · [Verification](final-verification.md)
