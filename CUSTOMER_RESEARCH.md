# Conversational investment research

> Current analysis-contract revision: [22.09 requirements and implementation](ANALYSIS_REQUIREMENTS_2209.md). Validation and remaining gaps: [revision validation](submission/analysis-validation-2209.md). Earlier acceptance records below describe their recorded revision, not a claim of current universal correctness.


The default customer workspace implements the current product direction and the November 16 general-profile/risk requirements. The historical workbench remains available through the separate `validation_app.py` for regression validation and explicitly authorized funding searches. The customer `app.py` has no reference-case navigation.

## Inquiry and synthesis

The current flow is **understand → plan → execute evidence tools → synthesize → independently review**. The complete user request, including optional fields, reaches planning, synthesis and review. Extracted excerpts also receive stable per-request context references. Names and unrelated background do not define model routes or financial rules.

A Bedrock planner proposes up to four analytical questions, identifies the relevant user context and selects evidence tools. Basic dated asset/FX observations are validated first. The analyst then receives actual tool outcomes and can request bounded further investigations, including review-driven repair and distinct explicitly stated horizons. The shared limits allow three investigation rounds, eight tool calls, twelve source calls and ten model-role calls within 240 seconds. A tool failure or missing holdings can cause a narrower answer or focused follow-up. No risk module is mandatory merely because its keyword appears in a profile. Explicit stated numerical rules remain checked facts; they do not force a particular lead conclusion.

The synthesis starts with a direct conclusion and uses supporting evidence, counterevidence, and important gaps/next step where useful; it does not fabricate opposition to fill a section. Substantive claims cite the checked evidence or client statements they use, with explicit scope, assumptions and limitations. Python owns arithmetic. Numeric literals must match exact values in cited Python-authored evidence or an explicitly cited, extracted client input. Registry placeholders resolve to checked evidence. Input quotations must remain labeled inputs; they cannot become computed outcomes. An analysis question is not verified evidence and cannot seed the numeric registry. This checks numeric origin, while the independent reviewer checks meaning and citation relevance. It is not proof of every qualitative inference.

A separate reviewer checks whether the answer addresses the question, uses material context, grounds its claims, weighs both sides and respects evidence limits. A rejection produces specific feedback for bounded repair, including retrieval or numerical verification when a catalog tool can resolve the problem. If that repair fails, the interface explicitly displays an evidence-only result instead of presenting a generic template as a personalized conclusion. This is a bounded orchestration loop, not unbounded autonomous browsing or proof that an LLM cannot err.

The report puts the reviewed answer and both sides of the reasoning before profile details, risk tables and charts. The former editor-only path and keyword-triggered recovery remain for legacy/offline tests, not as the online synthesis decision maker. Old cached reports are invalidated when the workflow version changes.

## Tools and scope

The planner can choose historical market analysis, holding-period windows, cash-needs replay, CPI purchasing power, duration, credit, traded-value proxy, exposures, a named controversy screen, tail-metric eligibility and portfolio-context checks. New holding-period analysis derives a single explicitly stated month/year horizon, checks overlapping historical outcomes with independent rational arithmetic, and refuses to extrapolate beyond available data. An unknown horizon produces a question, not a default.

The tool catalog is the current capability boundary. The model can choose tools and revise its scope; it cannot invent a data source, execute arbitrary code, manufacture thresholds or start an unrequested alternative-allocation search. Whole-portfolio impact remains unassessed without the required holdings and before/after allocation. The financial methods and source limits below still apply.

## General profiles

Supported fields include goals, horizon, withdrawals, willingness, capacity, income/debt/reserves, holdings, amount, base currency, concentration and asset-class conditions, exclusions, ESG preferences, experience and explanation depth. The three sidebar questions adapt the official situations. Names, ages and occupations supply no defaults. Profile changes can affect the interpretation while identical calculation inputs preserve their numerical results.

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

An approved archive supplies dated adjusted closes and FX. Hosted ZIPs are read from a private S3 object and checked against a configured digest. The [organizer archive](docs/RUNNING.md#organizer-archive-and-full-data-validation) is subject to its source terms.

Yahoo Finance's unofficial chart interface uses `range=5y`, daily adjusted closes and completed dates. HTTPS verification remains enabled. The adapter is disabled by default because [Yahoo's terms](https://legal.yahoo.com/ca/en/yahoo/terms/otos/) require permission for automated access. An operator who enables it must verify both access and intended reuse rights. No raw price history is committed.

FX uses [Bank of Canada Valet](https://www.bankofcanada.ca/valet/docs/) `FXUSDCAD`, CAD per USD. CPI uses Statistics Canada all-items Canada CPI `V41690973` via [Bank of Canada](https://www.bankofcanada.ca/rates/price-indexes/cpi/). Real returns align the final observed price in each CPI reference month. Release vintages and future inflation are not inferred. See the [Bank of Canada terms](https://www.bankofcanada.ca/terms/).

The [disclosure catalog](datathon/product_disclosures.py) records factual extracts from SEC EDGAR filings and issuer documents, checked November 16, 2026. It includes ESGU and ESGV screening methods, the SPY investment objective and a dated NVIDIA holding, IBIT's Bitcoin objective, published ESGU and SPY calendar 2022 fund returns, and an ordered pair of TSLA closing-price extremes across two quarters. Python calculates the difference in fund returns and the TSLA decline. These observations support scoped findings when a daily series is unavailable. They do not supply daily volatility, full-period drawdowns, current weights or individual controversy verification. See the [SEC reuse policy](https://www.sec.gov/about/webmaster-frequently-asked-questions).

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

Current production inquiry: `inquiry_engine.py` and `inquiry_contracts.py`; `customer_reasoning.py` also retains compatibility helpers. Other files: `customer_tools.py`, `customer_acceptance.py`, `customer_agents.py`, `customer_profile.py`, `customer_data.py`, `customer_workflow.py`, `customer_risks.py`, `customer_bonds.py`, `customer_report.py`, `customer_view.py`. Existing replay and qualified exposure code is reused.

Run `python -m unittest tests.test_customer_research tests.test_customer_risks tests.test_customer_view -v`. Tests cover profile-name invariance, contrasting triggers, high willingness with a down payment, recurring withdrawals, complete weights, missing/conflicting data, absent FX, adjustment/date validation, tampering, source gaps and the simplified UI. The full suite retains existing workbench coverage.

Live acceptance must identify this revision independently of the old architecture baseline. Current packaging and regression are recorded in `submission/final-verification.md`; live task-contract evidence is in `submission/analysis-validation-2209.md`. The earlier customer and 474-test records apply only to their revisions.

## Generalization acceptance

The separate developer app, under Reference cases → Reasoning acceptance, runs five previously unused fictional MSFT questions with frozen public observations: baseline, changed name, synonymous wording, irrelevant hobby and added tuition withdrawal/loss-capacity details. Independent comparisons assess substantive equivalence for the first transformations and justified contextual sensitivity for the material change; identical wording or a mechanically different verdict is not required. Accepted answers and identical core financial metrics are also required. Results are samples, not a guarantee of invariance for all language.

Automated tests separately exercise optional-form propagation, analysis-before-tools, follow-up tool use, absence of a forced lead, rejected/repair cycles, numeric-origin validation, horizon invariance and conclusion placement. See `submission/reasoning-validation.md` for this revision's observed acceptance, distinct from the earlier customer validation.
