# Conversational investment research

The default customer workspace implements the current product direction and the November 16 general-profile/risk requirements. The historical workbench remains available for regression validation and explicitly authorized funding searches.

## Inquiry and synthesis

The current flow is **understand → plan → execute evidence tools → synthesize → independently review**. The complete user request, including optional fields, reaches planning, synthesis and review. Extracted excerpts also receive stable per-request context references. Names and unrelated background do not define model routes or financial rules.

A Bedrock planner proposes up to four analytical questions, identifies the relevant user context and selects evidence tools. Basic dated asset/FX observations are validated first. The analyst then receives actual tool outcomes and can request up to two further batches of previously unused tools. A tool failure or missing holdings can cause a narrower answer or focused follow-up. No risk module is mandatory merely because its keyword appears in a profile. Explicit stated numerical rules remain checked facts; they do not force a particular lead conclusion.

The synthesis has four sections: direct conclusion, supporting evidence, counterevidence, and important gaps/next step. Each substantive section cites checked evidence and client statements. Python owns arithmetic. Numeric literals must match exact values in cited Python-authored evidence or an explicitly cited, extracted client input. Registry placeholders resolve to checked evidence. Input quotations must remain labeled inputs; they cannot become computed outcomes. An analysis question is not verified evidence and cannot seed the numeric registry. This checks numeric origin, while the independent reviewer checks meaning and citation relevance. It is not proof of every qualitative inference.

A separate reviewer checks whether the answer addresses the question, uses material context, grounds its claims, weighs both sides and respects evidence limits. A rejection produces specific feedback for one repair attempt. If that repair fails, the interface explicitly displays an evidence-only result instead of presenting a generic template as a personalized conclusion. This is a bounded orchestration loop, not unbounded autonomous browsing or proof that an LLM cannot err.

The report puts the reviewed answer and both sides of the reasoning before profile details, risk tables and charts. The former editor-only path and keyword-triggered recovery remain for legacy/offline tests, not as the online synthesis decision maker. Old cached reports are invalidated when the workflow version changes.

## Tools and scope

The planner can choose historical market analysis, holding-period windows, cash-needs replay, CPI purchasing power, duration, credit, traded-value proxy, exposures, a named controversy screen, tail-metric eligibility and portfolio-context checks. New holding-period analysis derives a single explicitly stated month/year horizon, checks overlapping historical outcomes with independent rational arithmetic, and refuses to extrapolate beyond available data. An unknown horizon produces a question, not a default.

The tool catalog is the current capability boundary. The model can choose tools and revise its scope; it cannot invent a data source, execute arbitrary code, manufacture thresholds or start an unrequested alternative-allocation search. Whole-portfolio impact remains unassessed without the required holdings and before/after allocation. The financial methods and source limits below still apply.

## General profiles

Supported fields include goals, horizon, withdrawals, willingness, capacity, income/debt/reserves, holdings, amount, base currency, concentration and asset-class conditions, exclusions, ESG preferences, experience and explanation depth. No name, age or occupation supplies defaults. Amira, Mateo and Robert exist only as validation fixtures. Profile changes can alter relevance, explanation and questions; they cannot change a historical calculation on identical inputs.

Extracted statements remain unconfirmed interpretations until the user reviews/corrects them. Multiple complete allocations and conflicting values are retained. A complete explicitly stated weight vector can use the existing buy-and-hold engine. No daily rebalancing, inferred allocation or automatic funding solver is introduced.

## Quantified and connected to the report

| Dimension | Implementation | Limit |
| --- | --- | --- |
| Historical risk | Terminal return/loss, drawdown, volatility, worst month, worst rolling 12/36-month returns, recovery and still-unrecovered state | Up to five years; exchange-calendar completeness is not certified |
| Stress replay | Existing engine with exact 2022 and early-2025 endpoints | Missing endpoints are not shifted; history is not a forecast |
| Currency | Same-date CAD/USD conversion, local/FX/interaction decomposition | Missing FX dates excluded; current whole-share sizing uses separately dated latest FX |
| Explicit portfolio | Existing weighted buy-and-hold engine for complete stated weights | No allocation inferred from a demographic or incomplete holdings |
| Withdrawals | Single or fixed monthly schedule, explicit amount/currency/start/duration; fractional unit sales, funding gaps and remaining assets | Relative timing mapped to a historical path; not retirement-success probability. No-withdrawal recovery is separate |
| Purchasing power | Canadian CPI and monthly aligned CAD nominal/real returns | Reference month is separate from retrieval/publication; latest vintage, retrospective only |
| Trading-volume proxy | Amount / mean of 20 observed close × volume values, currency consistent | Not spread, impact, execution certainty or ETF underlying liquidity; no invented threshold |
| Duration | Generic first-order minus duration × yield change using eligible disclosures | Initial catalog: AGG. Explicit system ±100 bp scenarios; ignores convexity, spreads and FX responses |
| Credit | Underlying rating buckets, issuer sectors, below-investment-grade, unrated and residual weights | Initial catalog: AGG. Not the ETF's rating, a default probability or repayment guarantee |
| Exposures/screens | Existing date-qualified issuer/sector/asset-class bounds and explicitly named GPFG checks | Partial coverage and unknown weight remain; incomplete ETF look-through is not certified |

Current whole-share sizing uses the latest observed price and can leave uninvested cash. Historical simulations instead invest the full initial amount in fractional units at the first historical observation. These are separate illustrations, not one simulated execution.

## Sources and qualification

Yahoo Finance's unofficial chart interface uses `range=5y`, daily adjusted closes and completed dates only. Provider adjustments are not applied twice. It may be delayed, throttled or changed. HTTPS verification remains enabled with certifi. This private research interface does not grant public redistribution rights; raw downloaded data are not bundled with the repository.

FX uses [Bank of Canada Valet](https://www.bankofcanada.ca/valet/docs/) `FXUSDCAD`, CAD per USD. CPI uses Statistics Canada all-items Canada CPI `V41690973` via [Bank of Canada](https://www.bankofcanada.ca/rates/price-indexes/cpi/). Real returns align the final observed price in each CPI reference month. Release vintages and future inflation are not inferred.

The small [bond disclosure catalog](datathon/bond_disclosures.json) is a factual extract checked against the [issuer's AGG page](https://www.ishares.com/us/products/239458/ishares-core-u-s-aggregate-bond-etf-agg). As-of date, observation date, unknown original publication date, locator and URL are separate. Disclosures older than 31 days or observed after the research date are rejected. They are dated snapshots, not fresh per-request lookups. Underlying rating weights retain issuer rounding/unclassified residual as unknown.

## Gaps and supported boundaries

- VaR/Expected Shortfall are withheld when requested because complete consecutive exchange-session coverage is not certified for this public route. No long-horizon scaling or future loss probability is fabricated.
- Other bond instruments require their own qualified duration/credit disclosures; they never inherit AGG values.
- Weekly, quarterly, variable, tax-aware and multiple simultaneous withdrawal schedules remain unsupported. Missing schedule fields trigger focused questions; short history restricts that result, not unrelated calculations.
- Company fundamentals, valuation, news, complete fund holdings, exhaustive issuer overlap and comprehensive ESG screening are not retrieved. Relevant conclusions remain limited.
- An explicit drawdown cap can show an observed breach. A sample below the cap cannot certify a pass without complete coverage and confirmed scope. Qualitative willingness/capacity never generates a numerical limit.
- The app places no trades and does not search alternative portfolios without separate authorization. The historical workbench retains controlled funding searches.

## Runtime, files and tests

Use the README environment and AWS configuration. Intake, explanation and explanation review use `DATATHON_PROFILE_MODEL_ID` in `us-east-1`, with bounded stage time/request/token budgets. Real traces expose successful versus failed or local execution.

Main files: `customer_reasoning.py`, `customer_tools.py`, `customer_acceptance.py`, `customer_agents.py`, `customer_profile.py`, `customer_data.py`, `customer_workflow.py`, `customer_risks.py`, `customer_bonds.py`, `customer_report.py`, `customer_view.py`. Existing replay and qualified exposure code is reused.

Run `python -m unittest tests.test_customer_research tests.test_customer_risks tests.test_customer_view -v`. Tests cover profile-name invariance, contrasting triggers, high willingness with a down payment, recurring withdrawals, complete weights, missing/conflicting data, absent FX, adjustment/date validation, tampering, source gaps and the simplified UI. The full suite retains existing workbench coverage.

Live acceptance must identify this revision independently of the old architecture baseline. Current validation is recorded in `submission/customer-validation.md`; earlier PDFs/videos and the 474-test baseline do not prove this new workspace.

## Generalization acceptance

Reference cases → Reasoning acceptance runs five previously unused fictional MSFT questions with frozen public observations: baseline, changed name, synonymous wording, irrelevant hobby and added tuition withdrawal/loss-capacity details. Independent comparisons assess substantive equivalence for the first transformations and justified contextual sensitivity for the material change; identical wording or a mechanically different verdict is not required. Accepted answers and identical core financial metrics are also required. Results are samples, not a guarantee of invariance for all language.

Automated tests separately exercise optional-form propagation, analysis-before-tools, follow-up tool use, absence of a forced lead, rejected/repair cycles, numeric-origin validation, horizon invariance and conclusion placement. See `submission/reasoning-validation.md` for this revision's observed acceptance, distinct from the earlier customer validation.
