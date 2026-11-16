# Conversational investment research

The default customer workspace implements the current product direction and the November 16 general-profile/risk requirements. The historical workbench remains available for regression validation and explicitly authorized funding searches.

## Journey and model boundaries

The user describes an idea and relevant conditions. Optional free-text profile fields are available, but no complete questionnaire is required. Bedrock extracts exact asset/condition excerpts and literal amounts. Fields retain their wording, category and `extracted_unconfirmed` status. Unknowns stay unknown; conflicting amount/currency statements withhold sizing without blocking independent price analysis.

The data tool fetches public adjusted closes, dated latest prices, and Bank of Canada FX. Goals and withdrawals trigger Canadian CPI. A deterministic plan identifies relevant checks, reasons, required evidence, methods and statuses. Python computes all financial values. Existing `decision_replay.evaluate` and `verify` supply the historical metrics and independent checks; new withdrawal, CPI, duration and trading-volume calculations use independent rational arithmetic checks.

Bedrock selects checked evidence and writes a qualitative interpretation. A separate model call reviews it against the evidence and user statements. Literal/spelled-out quantities and unsupported counterfactuals are rejected; numbers and rule verdicts remain deterministic. Semantic review is a safeguard, not proof that a model can never make an incorrect inference. Failed interpretation is withheld and the checked evidence remains available. Local fallback never masquerades as an AWS call.

The report presents a conclusion, graphs, relevant risks, assumptions, dates, gaps and a focused follow-up. Downloadable HTML includes vector charts and sources; Markdown contains the text. Observable activity records identify model/tool execution, not private model reasoning.

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

Main files: `customer_agents.py`, `customer_profile.py`, `customer_data.py`, `customer_workflow.py`, `customer_risks.py`, `customer_bonds.py`, `customer_report.py`, `customer_view.py`. Existing replay and qualified exposure code is reused.

Run `python -m unittest tests.test_customer_research tests.test_customer_risks tests.test_customer_view -v`. Tests cover profile-name invariance, contrasting triggers, high willingness with a down payment, recurring withdrawals, complete weights, missing/conflicting data, absent FX, adjustment/date validation, tampering, source gaps and the simplified UI. The full suite retains existing workbench coverage.

Live acceptance must identify this revision independently of the old architecture baseline. Current validation is recorded in `submission/customer-validation.md`; earlier PDFs/videos and the 474-test baseline do not prove this new workspace.
