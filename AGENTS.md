# Datathon Agent

This workspace carries forward the Datathon project for AlphaForge AI, the 2026 PolyFinances challenge with Banque Nationale and AWS.

The official release contains the English and French 19-page case briefs, the English and French 12-slide participant decks, and `alphaforge_starter/`. Use the case for detailed requirements, the participant deck for evaluation and AWS eligibility, and organizer logistics for deadlines and submission channels. [Datathon2026.zip](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)

## How to work in this project

- Current user product direction (November 16): the customer workspace is a general investment-research conversation. Infer no profile from a name or age. Users state their own ideas, objectives, withdrawal needs, loss capacity, preferences and constraints. The official Amira, Mateo and Robert personas are validation fixtures only; they must not supply defaults, routing rules or model assumptions in production. Keep technical configuration in the validation workspace.

- Respond to the user in Chinese by default. Keep official French labels where they help trace a requirement and use the language requested for competition deliverables.
- Write GitHub-facing documentation, change notes, issue and pull request text, commit messages, and push summaries in English.
- The user asked to understand the full requirements, explore deeply, and wait for the challenge before developing a solution. The kickoff slides now establish the challenge. When asked to implement, start with a specific investment decision to support, then use the current organizer materials to resolve open questions and choose the workflow with the team.
- The user aims to win an award. Design the prototype and pitch around what the judges can verify against the rubric. Show a specific, evidence-backed financial insight, the investor constraint that changes the decision, the distinct contribution of each agent, and the concrete AWS operation. Use the same case across the prototype, video, technical documentation and one-pager.
- Treat the organizer's latest written instructions as authoritative. This file records the kickoff materials and earlier project discussions. Update it when a newer organizer instruction clarifies a rule or deadline. Distinguish organizer requirements, prior preparation, and implementation choices.

### Workflow acceptance

- Tests for an original-proposal request should verify that Profile does not require approval for a smaller purchase and no funding solver runs. Any alternative search requires independent confirmation of the search scope.
- Exercise the same trade with an explicit search request, an unsupported binding condition and an injected calculation error. Compare checked findings and release status across the runs.
- Keep estimates separate from verified facts. Sector analysis should expose its source classification, coverage and unknown weight. Enforcing a sector cap also requires solver support and independent verification.
- Compute all derived financial values and binding verdicts in Python. Build reports from independently reviewed results tied to the same inputs, rules and method versions. In the conversational research workspace, the report model may additionally write qualitative interpretations tied to checked evidence IDs; independently review this prose and withhold it when unsupported. Model prose never supplies financial quantities or binding verdicts.

## Challenge and constraints

- Build an explainable agentic decision aid for investment using public financial data. Possible use cases include comparing assets, analyzing scenarios, explaining risks, proposing a hypothetical allocation, or another defensible aid. The asset universe, tools, models and most architecture choices are open.
- Use the competition AWS environment and at least one AWS service in the solution. AWS must make a real, demonstrable contribution to the running prototype. The official participant deck makes effective integration a condition of eligibility for final evaluation. Show which application step calls AWS, what it returns, why it is used, and how a reviewer can reproduce that step. (Participant deck, slide 7.)
- Use simulation only. Exclude real transactions, personalized financial advice and confidential bank or personal data. Clearly distinguish sourced facts, assumptions and hypothetical scenarios. Show material uncertainty, data limitations and situations where the evidence is inconclusive. Tie explanations to the sources, tool actions and rules actually used.
- The kickoff permits one or several agents. The user chose a multi-agent architecture for this project. Give each agent a distinct task, explicit input and output fields, and the tools its role needs. Show how agents hand off evidence and decisions and how the application checks the result.
- The official case makes the starter dataset optional, with no required asset or asset class. Document each source's relevance, date, processing, limitations and applicable terms. In a historical simulation use only information available on the decision date. Keep observation and publication dates separate. (Official case, pp. 10–14.) [Public financial data](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/50-datasets)
- The official Workshop provides coding assistant setups for Codex on Bedrock, Claude Code on Bedrock and Kiro. For Codex on Bedrock, the Workshop uses the team's AWS account and a supported OpenAI model ID. The application can separately call a Bedrock runtime model through Converse. [Workshop coding assistants](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/40-quickstarts/60-ai-coding-assistant) · [Codex on Bedrock](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/40-quickstarts/60-ai-coding-assistant/30-codex)

## Investor personas and demo

| Persona | Profile | What the demo should test |
| --- | --- | --- |
| Amira | 26, high risk tolerance, 15+ years | Seek long-term growth and consider emerging technology or crypto exposure while maintaining diversification beyond technology. Explain how diversification affected the result. |
| Mateo | 41, moderate risk tolerance, 8–12 years | Balance growth and stability. Incorporate his explicit preference to avoid significant environmental or social controversies. Distinguish evidence of screening from unresolved issuer coverage. |
| Robert | 59, low to moderate risk tolerance, 3–5 years | Favor capital preservation and stability approaching retirement. When a media-driven opportunity conflicts with his profile, flag the mismatch and explain the risk. |

Build the demo around a concrete question and visibly different inputs. The official case treats the personas as references, and the participant deck recommends showing at least two contrasting situations. Change one assumption at a time to illustrate sensitivity. Show the data, agent actions, constraints, result and explanation in the same end-to-end tour. Ground explanations in observable execution and disclose conflicts, missing evidence and material uncertainty. (Official case, pp. 4–9, 15, 17. Participant deck, slides 4 and 11.)

The research brief in `Datathon_Research_Brief.md` records the proposed demo and supporting evidence. The worked example shows a decrease in geographic concentration alongside an increase in S&P 500 exposure and loss under an explicit hypothetical shock. Compare the same proposed move across personas and show which constraint changes the outcome. Treat the research brief's agent topology, tickers and shock parameters as candidate implementation choices.

## Investor analysis from the official finance workshop

Geneviève Daigneault's 16-slide workshop provides design guidance. Its portfolio walkthrough is an example, and the kickoff remains the source for competition rules. [Understanding the Investor Before Building the Solution](https://chatgpt.com/library?file_id=libfile_45683714475c8191b8fa95a48f9a0566&account_id=personal)

- Start with what the money needs to enable and when a significant withdrawal is expected. Represent the objective, horizon, willingness to take risk, financial capacity for loss, constraints and preferences as separate inputs. Age and visible holdings alone cannot establish those inputs. Apply constraints such as liquidity or concentration limits before ranking options by preferences such as ESG. If a missing input could change the result, state it and make the output conditional or narrow the question. (Slides 3, 7–8, 10, 14–15.)
- Check how instruments generate returns and where their risks come from. Compare like-for-like return measures over the same period and state the currency and treatment of fees, distributions and inflation where relevant. Choose risk measures for the question. Risk can include liquidity, credit, interest rates, inflation, currency and concentration as well as market losses. (Slides 4–8.)
- Measure diversification through underlying exposures and how they move together. Where holdings data allow it, look through funds and ETFs for overlap across assets, sectors, regions or risk factors. Flag stale or missing holdings and distinguish measured exposures from approximations. (Slides 9, 11, 13.)
- Record the source, as-of date, definition, currency, transformations, assumptions and missing fields for data that drive the result. Distinguish price from total return, reported results from estimates, and facts from opinions. Check fund holdings dates and the frequency, revisions or inflation treatment of macro data when applicable. The deck points to the Bank of Canada and Statistics Canada for macro data, and SEDAR+ and SEC EDGAR for filings. (Slides 11, 16.)
- Make the simulation traceable from data to findings, risk and trade-off analysis, and then to the hypothetical decision. Answer four questions in the result or demo: what data was used, why the choice follows, what limits the result, and what would change it. Mention relevant alternatives. (Slides 12, 15.)
- The worked example asks whether increasing an existing XSP holding would improve geographic diversification in a test portfolio with Canadian stocks, ZEQT and XSP. Compare current positions, weights, cash and exposures with the hypothetical change. Check XSP's index, CAD hedging, underlying holdings and fees, then assess geographic concentration and overlap with ZEQT. Explain the trade-offs and missing investor information. Use this as a possible demo pattern without adopting the example tickers as a project requirement. (Slides 13–14.)

## Submissions and judging

| Deliverable | Include |
| --- | --- |
| Prototype and GitHub code | One working end-to-end use case with an accessible explanation. README covering dependencies, data, configuration and reproduction. |
| Video | Approximately five minutes. Show the problem, agent roles, data, output and its explanation end to end. |
| Technical documentation | Architecture, agent roles and interactions, controls, methods, sources, assumptions, an explanation tied to data or observable execution, validation, limitations and potential improvements. |
| One-pager | At most one page covering problem, agentic approach, originality, data, explainability and concrete user value. |

The official simplified rubric assigns 20% each to solution quality/relevance/innovation, agentic intelligence/explainability, and data analysis/processing. UX/UI is 10%, quality of AWS integration is 15%, and presentation/business value/marketing is 15%. The full grid is reserved for judges. The assessment emphasizes the overall value and the quality of evidence supporting the result. (Official case, pp. 17–19. Participant deck, slide 10.)

| Date and time (Montréal) | Organizer website schedule |
| --- | --- |
| Sat Nov 14, 2026, 10:30 and 12:00 | Challenge announcement and competition start with Q&A, respectively. |
| Sun Nov 15, 2026, 16:00 and 23:59 | On-site event ends at 16:00. GitHub and application due at 23:59. |
| Mon Nov 16, 2026, 13:59 and 14:00 | Competition AWS accounts close and data are destroyed at 13:59. Video, one-pager and technical documentation due at 14:00. |
| Fri Nov 20, 2026, 14:00 and 18:00 | Finalist pitches start at 14:00. Networking starts at 18:00. |

The schedule photo lists the two Monday times in the reverse order. The event website and the AWS Workshop agree that the team account closes at 13:59. Export reproducibility materials and record AWS demo evidence before account closure. [PolyFinances event schedule](https://polyfinances.ca/datathon#competition) · [Workshop export and cleanup](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/90-cleanup)

## AWS workshop and prior preparation

- The Workshop uses one temporary AWS account per team. Use `us-east-1` (N. Virginia) as the application and AWS CLI request region. The team AWS Console and CloudShell were available, and the Bedrock Converse smoke tests passed on November 14, 2026, with `global.amazon.nova-2-lite-v1:0`. The AWS CLI text test returned `ready`. In the Python test, Nova requested the `compare_shock_losses` tool, the code computed 15.63% and 16.43% losses for the two fictional portfolios, and the model returned both figures and a test marker generated by the tool. The verified environment was competition CloudShell. Rerun this check in the environment that will host the application. [Workshop setup](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/20-setup)
- The November 14 setup checks also verified the AWS identity, listed 108 active Bedrock foundation models, and received `ready` from `global.anthropic.claude-haiku-4-5-20251001-v1:0`. The Codex CLI smoke test returned `bedrock-ok` with provider `amazon-bedrock`, model `openai.gpt-5.6-sol`, and exit code 0.
- The official introductory notebook ran in an isolated Python environment in competition CloudShell, an execution route the Workshop supports. All 13 code cells completed with exit code 0 and no cell errors. The saved outputs cover Yahoo Finance, Bank of Canada Valet, FRED, SEC EDGAR, risk and correlation calculations, Bedrock text and structured extraction, and a Strands agent that called its tools. Use these outputs as workshop validation and keep the competition prototype's own evaluation separate. [Official notebook instructions](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/20-setup/20-sagemaker-unified-studio) · [Executed notebook](https://chatgpt.com/library?file_id=libfile_ca31bd6cfc3481919f0e1ccd121f7bd7&account_id=personal)
- The Workshop recommends Nova 2 Lite for initial development and notes Anthropic may need a one-time account activation. Use bounded retries and backoff for throttling. Keep S3 Block Public Access enabled and keep AWS credentials, bank and personal data out of the repo and AI assistants. Coordinate shared account resources with teammates. [Responsible use](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/20-setup/10-responsible-use)
- The Workshop provides a Strands example with Python 3.10+, Strands Agents 1.63.0 and Bedrock in `us-east-1`. Pin the model explicitly and calculate financial metrics in Python. Treat the validated workshop version as a reproducibility reference. [Workshop Strands example](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/35-agents/20-strands)
- The workshop handout describes working in Python through Kiro or using JupyterLab in SageMaker AI Studio. It suggests calling Bedrock directly or through Strands when a model needs to reason over and explain text. It also introduces Knowledge Bases, Guardrails, AgentCore and Code Interpreter as options. Choose services for the required workflow and verify what the competition account can actually run before committing to them.
- The handout's Strands example uses Python 3.10 or later and a tool that computes annualized volatility from daily adjusted closing prices. Use deterministic code for metrics, have the model explain the results, and link figures to their sources. Account for split adjustments and use the information release date to avoid look-ahead bias. Pair returns with risk measures that suit the question, such as volatility or maximum drawdown.
- The workshop describes one temporary account per team. Before the official shutdown, preserve code, reproducible public-data references or permitted snapshots, and AWS demo evidence. Retrieve the access details from the organizer's email and keep credentials out of repository files and documentation. [AWS workshop handout email](https://mail.google.com/mail/u/0/#all/1a1b7378724b187f) · [AWS workshop recording](https://d1y1jqv0xt2on8.cloudfront.net/GMT20261106-190357_Recording_1920x1080.mp4) · [Competition Discord](https://discord.com/invite/F88aCj7ST)
- The user previously reported a MacBook setup with Python 3.9, pandas, matplotlib and Streamlit. Streamlit ran locally and a GitHub test push succeeded. Kiro was discussed as the local editor. These are preparation details, so confirm the runtime and dependencies before using them in this workspace.
- The earlier Streamlit example used five fictional stocks to demonstrate sector exposure. Prior chat records list `app.py` and `requirements.txt`, with `python -m streamlit run app.py` as the launch command. The ZIP contents still need direct inspection before reuse. [Datathon_Portfolio_Demo.zip](https://chatgpt.com/library?file_id=libfile_83e9d6b881188191902e84ce70950041&account_id=personal)
- The previously shared preparation repository could not be verified through the GitHub connector. [WindsTrace/datathon-prep](https://github.com/WindsTrace/datathon-prep)

## Source material and open items

The official `alphaforge_starter/` snapshot was retrieved on November 13, 2026. It contains 31 assets, 40,049 daily prices spanning November 12, 2021 to November 12, 2026, 658 corporate actions, 1,245 USD/CAD observations and 8,281 macro observations across nine series. It lacks XSP, ZEQT, underlying ETF holdings, ESG ratings, news and company fundamentals. Keep using dated issuer disclosures for an XSP/ZEQT demo. Use `adj_close` for starter return calculations, account for listing currency and trading calendars, and avoid applying listed splits a second time. The macro data include reference-month dates and latest FRED revisions. Verify each source's reuse terms before publishing raw extracts. (Starter `README.md` and `sources_metadata.csv`.)

The official case defers exact deadlines, submission platforms, formats and infrastructure logistics to the organizer. The release contains no submission form or portal link. The earlier portfolio demo ZIP could not be inspected locally. The kickoff photos below preserve supplementary context.

| Slide | Topic |
| --- | --- |
| [IMG_3911.jpeg](https://chatgpt.com/library?file_id=libfile_b0df757fe96c81919e74b010b8c4a619&account_id=personal) | Supplemental schedule photo |
| [IMG_3912.jpeg](https://chatgpt.com/library?file_id=libfile_b41694793f608191bf94ca106f172f30&account_id=personal) | Challenge brief |
| [IMG_3913.jpeg](https://chatgpt.com/library?file_id=libfile_fd2be5295b3c81918f0baade28077865&account_id=personal) | Personas and test cases |
| [IMG_3914.jpeg](https://chatgpt.com/library?file_id=libfile_60e9dc89c56481918d49cbca759ead24&account_id=personal) | Agent roles |
| [IMG_3915.jpeg](https://chatgpt.com/library?file_id=libfile_060df306dcbc819181f87fcdf7c6db0d&account_id=personal) | Data |
| [IMG_3916.jpeg](https://chatgpt.com/library?file_id=libfile_96118a178a80819195dddf745256d6d8&account_id=personal) | AWS eligibility and integration |
| [IMG_3917.jpeg](https://chatgpt.com/library?file_id=libfile_201e59bc776c819193f81068a02e7bd7&account_id=personal) | Demo design and sensitivity |
| [IMG_3918.jpeg](https://chatgpt.com/library?file_id=libfile_b06f96a07d788191a832f255248beef1&account_id=personal) | Four deliverables |
| [IMG_3919.jpeg](https://chatgpt.com/library?file_id=libfile_8abb8768fce88191994b1329204ba59a&account_id=personal) | Judging criteria |
| [IMG_3920.jpeg](https://chatgpt.com/library?file_id=libfile_70b4bc2e5abc8191ba731b56b327fc93&account_id=personal) | Simulation and transparency |
| [IMG_3921.jpeg](https://chatgpt.com/library?file_id=libfile_b5090b5cf6f08191b329f9a8b68729ff&account_id=personal) | Content not recovered |
| [IMG_3922.jpeg](https://chatgpt.com/library?file_id=libfile_f5bba9107ce88191a8bd44ba4851f468&account_id=personal) | Investor concepts workshop |
| [IMG_3923.jpeg](https://chatgpt.com/library?file_id=libfile_98f63623a96081919050e86ffb255aac&account_id=personal) | Workshop scope and follow-up |
| [Official finance workshop PPTX](https://chatgpt.com/library?file_id=libfile_45683714475c8191b8fa95a48f9a0566&account_id=personal) | Investor profile, comparable data, portfolio exposures and XSP walkthrough |
| [November 10 screenshot](https://chatgpt.com/library?file_id=libfile_2f687e0a6f188191a21eb948d1f14755&account_id=personal) | Earlier setup screenshot |
