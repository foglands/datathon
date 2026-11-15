# AlphaForge AI release verification

PolyFinances Datathon 2026 · Montréal

## Offline trade intake and Bedrock recovery

The previous assistant opened Bedrock profile interpretation after recognizing a trade locally. A diagnostic run with the actual local SDK had no credential provider, stopped with `NoCredentialsError`, and started zero Bedrock HTTP attempts. The application previously displayed the generic `invocation_error`.

Local trade intake now drafts supported fields from the original text and requires the user to check the full scope. A missing or ambiguous field remains unresolved. Explicitly unsupported purchase or funding symbols are held. The confirmed offline audit uses the organizer data and the same independent review.

All 298 local regressions and six standard and stress CLI cases passed with the organizer data. The Streamlit regressions cover local drafts, credential guidance, recovery with the submitted text intact, direct-entry defaults, invalidation after changes, and separate funding-search authorization. A macOS browser check also completed the offline audit after a failed cloud attempt. It produced a downloadable audit after the user confirmed the original proposal. No successful competition AWS invocation was verified for this revision.

## Question intake verification

The previous local entry routed wording through a planning phrase gate and then a two-choice comparison parser. Its Bedrock task list did not include planning. On 72 independently assembled planning prompts, 63 missed the planning route and 4 preserved all checked amounts, goals, risk statements, and choices. The baseline was `fec73c7`.

The revised intake passed the 72 planning cases and all 141 labeled intake scenarios. Three seeds (17, 104, and 609) vary wording, amounts, order, separators, goals, risk concerns, choices, and limits. Additional cases check third-party amounts, excluded choices, unsupported actions, unsupported assets, and unrelated questions. The parser is tested internally on varied language forms. The product checks English locally before sending any user question or follow-up to Bedrock or opening a data workflow.

| Check | Observed result |
| --- | --- |
| Browser on macOS, organizer starter bundle | Both reported planning cases produced an answer on the first submission. Each optional example returned an independently verified historical comparison. A fresh bond-fund and index-fund planning question also reached a verified historical comparison. |
| Language boundary | English questions with short phrasing, ticker pairs and proper names can reach interpretation. Representative Chinese, French, Spanish, German and mixed-language requests are blocked with an English prompt. Very short or unclear text may need a fuller English sentence. |
| Confirmation and scope | A model-assisted numerical interpretation still requires scope and input review. An unsupported forecast in a separate clause leaves the planning answer available and does not open a replay for that mixed request. |
| Local macOS suite | 288 regressions passed with the organizer data. All six standard and stress CLI cases passed offline. |
| Strands SDK 1.63.0 | Botocore Stubber verified the Converse tool call and response parsing. Tests cover clause references, unavailable responses, unsupported tasks, and false attribution and financial fields. |
| Competition AWS | The console required sign-in during this check. The new intake has no live AWS result. Live results below apply to earlier revisions. |

Run `python -m unittest discover -q` after installing `requirements.txt` and setting `DATATHON_STARTER_PATH` and `DATATHON_FULL_STARTER_PATH` to the organizer bundle. The generated scenarios are in `tests/test_general_intake.py`. For a live smoke check in an authenticated competition environment, enter a fictional planning question, use **Interpret with Amazon Bedrock**, and open **Question interpretation activity** to check the returned tool and request metadata. The historical comparison remains a separate action.

## Mixed investment question verification

All 269 local regressions passed with the official starter data. The browser processed a single prompt about saved cash, peers' trading gains, NVIDIA, Bitcoin, options, and a guaranteed annual return. The response flagged the return claim and described concentration, crypto, and options risk. The work history left the withdrawal horizon open. The separate NVDA and BTC-USD example returned a verified, unranked CAD historical comparison. A standalone guarantee request also reaches educational guidance. Explicit forecast, historical analysis, and trade requests retain their existing routing checks.

## Planning question verification

All 266 local regressions passed with the official starter data. Streamlit tests verified a planning response before the market bundle was loaded. An open-ended question about family expenses, inflation, past losses, S&P 500 funds, and gold produced a spending question and sourced explanations of the options in the browser. No dated withdrawal or numeric loss limit was assumed. The optional SPY and GLD historical comparison ran separately and displayed both verified series in CAD without a relative winner.

## Question-driven comparison verification

The question intake regression passed 259 local tests on macOS with the organizer's starter data. All six offline CLI reference and stress cases passed.

| Input in the Streamlit question box | Checked result |
| --- | --- |
| Compare AGG and GLD with a maximum drawdown of no more than 12% | AGG met the cap in both test windows. GLD breached the cap. |
| Change only the cap in the question to 8% | The prior result cleared. Both assets breached the new cap in at least one window. |
| Compare AGG and GLD with no profile or priority | Both verified sets of measures appeared side by side. |

Chrome verified the cap change using Chinese input and displayed the corresponding original wording. The automated tests also check weighted allocations, quote provenance, and ambiguous or unsupported instructions. The new Bedrock clause-selection logic was checked with SDK tool tests using simulated responses. The live AWS runs in the following section cover the earlier assistant revision.

## Profile-first assistant verification

The November 15, 2026 validation used the organizer's frozen starter data on macOS with Python 3.10 and competition CloudShell in `us-east-1` with Python 3.13. Both environments passed 243 regression tests. The local offline CLI passed all six reference and stress cases.

| Live Streamlit flow in competition CloudShell | Observed outcome | Successful Bedrock responses |
| --- | --- | ---: |
| Compare two fictional allocations before a planned withdrawal | Bedrock suggested the comparison task. The user confirmed the task and profile, then entered AGG and GLD. The independently verified result showed AGG had the lower worst-window drawdown. | 1 |
| Audit adding eight percentage points of NVDA with ZST.TO funding | Bedrock suggested the trade audit and interpreted the trade and its stated loss and reserve limits. The confirmed trade breached an assessed constraint. Independent review published the original result. The alternative search was skipped. | 5 |

The live checks used Streamlit AppTest through the same application controls and actual Bedrock runtime. Browser checks confirmed the growth and capital-preservation paths produce different findings on identical assets. Chrome displayed the assistant entry and profile controls at 390 pixels without page overflow. The browser used the offline comparison for these layout checks.

To reproduce the live checks, launch the application from authenticated competition CloudShell or another environment with the configured Bedrock access. Enter a fictional AGG versus GLD question in **Investment assistant**, select **Suggest a task with Bedrock**, then confirm the comparison, capital preservation, and a withdrawal within one year. Select AGG and GLD and run the comparison. **Agent activity** records the successful routing response. For the audit, describe adding eight percentage points of NVDA funded only from ZST.TO with a 15% minimum remaining ZST.TO weight and a 14% terminal-loss cap. Suggest the task, confirm the profile, interpret the request with Bedrock, and confirm the original audit. The **Agent activity** tab records the tool and review calls. Use `python -m unittest discover -q` with both starter path variables set to reproduce the full regression run.

## Generated-input and cross-model verification

The November 15, 2026 comparison used the same official starter data for the [baseline `6d1fb52`](https://github.com/WindsTrace/datathon-prep/commit/6d1fb52a29f932dceaec94970d72a0820d1c79ad) and [application candidate `957b441`](https://github.com/WindsTrace/datathon-prep/commit/957b4416e6a93d558124a9122f05001f17dcb312). The paired runner generates supported portfolio weights, constraints, funding permissions, historical windows, disclosure gaps, and English or French requests from a seed. Both revisions receive the same generated inputs. The runner alternates execution order, compares financial outputs with an independently checked offline reference, and checks solver authorization separately.

| CloudShell cohort | Seed | Profile model | Audit model | Baseline | Candidate | Candidate request ID hash |
| --- | ---: | --- | --- | ---: | ---: | --- |
| Initial generated cohort | 20261115 | Claude Sonnet 4.5 | Nova 2 Lite | 6/8 | 8/8 | `f404f3eff1e4` |
| Independently seeded holdout | 142106706 | Claude Sonnet 4.5 | Nova 2 Lite | 6/8 | 8/8 | `0259db74d595` |
| Model roles swapped | 56558902 | Nova 2 Lite | Claude Sonnet 4.5 | 1/3 | 3/3 | `b606a9d82a05` |
| Custom manifest with authorized Review | 585936471 | Claude Sonnet 4.5 | Nova 2 Lite | 1/1 | 1/1 | `4d9e0a5bc129` |

The baseline passed 14/20 checks and the candidate passed 20/20. The baseline requested clarification in all six explicit English and French exact-quantity checks. The candidate grounded all six quantities and advanced to confirmation. The genuinely ambiguous and conflicting requests still required clarification. Both revisions agreed with the independently reviewed offline financial results for every generated audit and follow-up in the table, including the supplied manifest.

Each revision recorded 60 successful Converse responses across these cohorts. The median candidate-minus-baseline latency among pairs that passed on both revisions was −79.15 ms for the first cohort, +72.87 ms for the holdout, and −1,109.07 ms for the single comparable pair after swapping models. The authorized Review pair ran in 7,243.02 ms for the baseline and 6,798.78 ms for the candidate, with nine successful Converse responses each. These timings are individual experimental observations. The scripted rejected-route benchmark separately reduced tool attempts from five to four for the staged recovery path, with zero unsafe releases on either revision.

[Revision `77b9d0c`](https://github.com/WindsTrace/datathon-prep/commit/77b9d0c072a66a8269c373dfe910d108554f06e9) extends the benchmark checker to cover custom Review manifests with either search authorization state. The final revision passed 230/230 regressions on local macOS and competition CloudShell. The application passed 6/6 offline CLI checks on each environment. The custom-manifest replay used the updated checker and the same application runtime. Its manifest fingerprint starts with `0a27918bc8bf`.

Reproduce the independently seeded live comparison from the candidate checkout using a baseline checkout and the official dataset.

```bash
python -m datathon.paired_benchmark --data "$DATA" --mode aws \
  --baseline /path/to/baseline-checkout --candidate . --seed 142106706 \
  --report outputs/paired-holdout.json
```

The competition session stored the paired reports and final regression output under `/tmp/alphaforge-iteration/results/`.

## Risk reliability completion on local and competition AWS

Application commit [`98661fe`](https://github.com/WindsTrace/datathon-prep/commit/98661fe71f880139d51d2361624193adc8db7c82) was verified on November 15, 2026. Local macOS Python 3.10 and competition CloudShell Python 3.13 used the organizer's full starter tables.

| Check | Local | AWS CloudShell `us-east-1` |
| --- | ---: | ---: |
| Full Python regression suite, including Streamlit AppTest | 219 / 219 | 219 / 219 |
| Offline CLI reference and stress cases | 6 / 6 | 6 / 6 |
| Live Bedrock CLI reference and stress cases | | 6 / 6 |
| Additional live checks for this change | | 5 / 5 |

The eleven live checks collected **36 successful Bedrock Converse HTTP 200 responses**, each with an AWS request ID. The additional cases verify the following behavior.

| Additional live check | Observed result | Successful Converse calls | Sample request ID hash prefix |
| --- | --- | ---: | --- |
| English Profile | Correctly grounded purchase, loss, reserve and issuer values in the applicable request clauses. | 1 | `9d03cd835567` |
| French Profile | Correctly grounded purchase, loss and reserve values in the applicable request clauses. | 1 | `54b252c69d01` |
| Robert, original trade | Skipped Alternatives and exposed a verified drawdown reference and complete date coverage for both reference windows. | 3 | `489ce3946ebc` |
| Amira, sector evidence | Recomputed the ZST.TO disclosure bound. A modified bound withheld the sector section and preserved the verified main report. | 4 | `22dee134ac33` |
| Delegated Review | Selected the requested loss-metric change and published verified replay metric references under the original search scope. | 4 | `5404b0854de7` |

The full suite covered deterministic price paths, scaling, contribution conservation, missing dates, unresolved intake, and tampered publication. Observation coverage is independently checked for the three registered competition windows. Unregistered windows are explicitly marked as unverified. Reported risk is conditional on the historical scenarios.

Reproduce the standard local or CloudShell checks from the application commit using the full starter data.

```bash
DATATHON_STARTER_PATH="$DATA" DATATHON_FULL_STARTER_PATH="$DATA" python -m unittest discover -q
python -m datathon --data "$DATA" --mode offline --stress
python -m datathon --data "$DATA" --mode aws --stress --report /tmp/alphaforge-live.json
```

This CloudShell session saved the full suite output and CLI reports under `/tmp/alphaforge-98661fe-full-aws/`, with request ID hashes in `live-proof.json`.

## Formula-based publication on competition AWS

Application commit [`afe2036`](https://github.com/WindsTrace/datathon-prep/commit/afe2036c79ed87865bac885c6f3024bb018a2ecb) ran in the competition AWS CloudShell in `us-east-1` using the organizer starter dataset. The run was recorded on November 15, 2026 at 01:04 Toronto time. The CLI passed all six reference cases. Two additional original-only cases passed the publication checks. Across the eight cases, the observed Bedrock Converse responses included 30 HTTP 200 results with AWS request IDs.

| Case | Audit status | Publication | Successful Converse responses | Sample request ID hash prefix |
| --- | --- | --- | ---: | --- |
| Robert, authorized terminal-loss search | `fail` | `released` | 4 | `86b80d02b148` |
| Robert, authorized drawdown search | `fail` | `released` | 4 | `40ba3d4cb180` |
| Robert, modified risk claim | `invalid` | `blocked` | 4 | `bbcf50d6b0a0` |
| Robert, ambiguous loss definition | `needs_input` | `blocked` | 1 | `f217ca8fbdcc` |
| Amira, issuer concentration | `fail` | `limited` | 5 | `2a8d352d090b` |
| Amira, missing QQQ disclosure | `insufficient_evidence` | `limited` | 5 | `4af8a4d21902` |
| Robert, original trade only | `fail` | `released` | 3 | `253d254abcf4` |
| Amira, original trade with sector analysis | `fail` | `limited` | 4 | `88120db2cc05` |

Claude Sonnet 4.5 handled the ambiguous Profile case. Nova 2 Lite handled the audit stages. In both original-only cases, independent Review verified the CAD conversion and the workflow skipped Alternatives. Amira's issuer exposure change and sector section were verified separately. Modifying a sector bound after the audit withheld that section and preserved the verified main result. Modifying Robert's reviewed drawdown blocked publication of the main values.

Reproduce the six reference cases in the authorized AWS session.

```bash
python -m datathon --data "$DATA" --case all --mode aws --stress --report /tmp/alphaforge-live.json
```

The test session also saved the full CLI report at `/tmp/alphaforge-afe2036-cli-live.json` and the sanitized result at `/tmp/alphaforge-afe2036-live-proof.json` in CloudShell.

## Authorized audit and checked publication

Application commit [`186cdcf`](https://github.com/WindsTrace/datathon-prep/commit/186cdcfc66d0c15f163fcdeb1f16dfd40eff4353) applies the feedback on request scope and publication. A clean checkout passed **165/165 tests** with the full organizer ZIP. The six reference CLI scenarios passed both offline and on competition AWS.

| Check | Observation |
| --- | --- |
| Original proposal only | Returned the verified violation in the Robert fixture. The solver and independent frontier had **zero calls** offline and on AWS. |
| Authorized full-size search | Called the solver once. Independent review found a full-size alternative under the permitted sources. |
| Limited review with unassessed ESG | Preserved the verified violation and the unassessed binding term. The solver was skipped and the published scope was limited. |
| Smaller size authorization | The exact-size ZST.TO search found no full-size solution. The first response showed the authorization question and withheld the smaller allocation. After authorization, independent review verified 5.00 percentage points. |
| Follow-up and publication | Original-only and limited replays preserved scope in the local acceptance matrix. Injecting an incorrect metric blocked the published result. |
| Optional sector report | Dated and partial equity-sector evidence supports a change of **+8.37 to +10.00 percentage points** in Information Technology exposure in the 10-point ZST.TO-funded NVDA case. The report does not apply a sector cap. [Source conditions](../SECTOR_EVIDENCE.md) |

The independent matrix passed **8/8** locally, and its six live cases passed in competition CloudShell. The two additional live Profile probes accepted the original-only language and preserved the binding ESG requirement. In the matched Robert live sample, the original-only path took **3** Bedrock requests and the explicitly authorized search took **4**. These counts describe one matched execution, separate from the pressure tests below.

The prior mixed, bilingual and issuer Profile cohorts were each rerun once on Amazon Bedrock and matched **10/10**, **6/6** and **3/3**. None emitted a premature policy. These are scoped regression results on the stated examples.

With the existing Python environment and data, run the local regression matrix and request entry tests.

```bash
python -m unittest tests.test_audit_intent tests.test_request_entry \
  tests.test_app tests.test_publication tests.test_requirement_status tests.test_sector -q
```

In Streamlit choose **Write a request** for the new flow. **Search alternative funding** prepares the search inputs. Run the original audit, then choose **Confirm and search alternative funding** to authorize the search. Leave the smaller-size choice undecided to test the deferred question. Choose the limited review option to preserve a binding requirement that cannot currently be assessed. The existing video shows the earlier reference comparison.

In the current Streamlit reference cases, prepare and confirm search separately to reproduce the financing comparison from the recording. Interactive CLI requests use a separate `SEARCH` prompt when `--search-alternatives` is supplied. The command-line reference suite exercises predefined comparison fixtures.

The follow-up confirmation regression passed **171/171** local tests and the six offline reference scenarios. An issuer-exposure audit with an independently checked proposal remained inconclusive with zero solver calls until the user confirmed a separate search. The missing-price case withheld the search action because the required market series could not be reviewed.

## Optimized application

The optimized application is [`0c39d08`](https://github.com/WindsTrace/datathon-prep/commit/0c39d080edc7c050186df1ebea43e14c8473471e). Performance and structured UI measurements use its parent [`897f0b2`](https://github.com/WindsTrace/datathon-prep/commit/897f0b29e557fb35709a80fb0df56dfc546af80e). The final application commit adds the total-issuer-exposure Profile correction. Results for the separately recorded demo appear under **Earlier package and evidence**.

| Verification | Observed result |
| --- | --- |
| Complete organizer ZIP | **137/137** local tests at the final application commit using a clean checkout. The same commit passed all **6/6** offline and **6/6** competition AWS CLI scenarios. |
| New structured path | Recorded a custom starting portfolio and verified all **63** aligned dates in the optional 2023 window in Streamlit AppTest on competition AWS. The audit returned a full-size feasible outcome for this fixture after four successful Bedrock calls. |
| Data integrity | Removing only the 2022-06-16 price or FX session now withholds the verdict. The same price omission previously turned an infeasible 15.75% drawdown case into a verified partial purchase. |
| Drawdown compute | For Robert's reference 14% cap, the solver instantiates **1,834** of **31,857** date-pair constraints. On seven warm local measurements per revision after two warmups, median solver time was about **55 → 7 ms**, and the fully reviewed offline workflow about **69 → 22 ms**. These are local replay timings, measured separately from the network tests. |
| Matched failure recovery | Nine scripted cases, two repeats per arm. Staged recovered **8** paths and bundled **4**. Both matched **18/18** expected outcomes with zero unsafe releases. A separate four-case live Bedrock data-fault run was **4/4** in each arm, with 16 staged and 19 bundled Converse calls. |
| Profile holdouts | In production Sonnet at `0c39d08`, mixed **20/20**, bilingual **12/12**, separate quote **12/12**. Each set independently repeated the results of `f97deb8`. The earlier mixed baseline was **18/20**. The three sets and the additional issuer suite observed zero premature policies. |
| Supported issuer cap | The full text path at `897f0b2` found that Profile classified Amira's supported total exposure rule as unsupported. At `0c39d08`, real Sonnet passed **6/6** issuer-specific attempts, including supported total exposure and a separate unsupported direct-only cap. The combined text-to-reviewed-audit benchmark passed **4/4**, Robert and Amira twice each. |
| Issuer re-audit | Tests use synthetic, pinned and explicitly labeled disclosures to check partial and complete evidence. The normal Amira case still holds its alternative pending qualified XIU.TO and ZST.TO records. [Evidence requirements](../ISSUER_EVIDENCE.md) |

### Runtime and usage

The following structured controller runs used real Nova 2 Lite in the competition account. Each row contains four measurements: Robert and Amira twice each. Cache cold reloads the market snapshot in-process. Warm uses the already loaded snapshot. Times exclude human confirmation and browser rendering. With four observations the displayed p95 is the largest observed time.

| Cache | Maximum concurrency | Passed | p50 | p95 |
| --- | ---: | ---: | ---: | ---: |
| Cold | 1 | 4/4 | 2.89 s | 3.15 s |
| Warm | 1 | 4/4 | 2.93 s | 3.36 s |
| Cold | 3 | 4/4 | 3.10 s | 3.68 s |
| Warm | 3 | 4/4 | 2.83 s | 3.36 s |

The 16 requests started 72 Converse HTTP attempts and reported 113,064 tokens, with no observed transport retry or routing fallback. A separate offline benchmark completed **60/60** controller requests across 1, 3 and 6 concurrent requests with both cache modes. Warm local p95 was about **9, 23 and 41 ms**, respectively.

For the separate four-run live text-to-reviewed path at `0c39d08`, p50 was **9.34 s** and p95 was **10.20 s**. Across both models, the four complete requests started 22 Converse attempts and reported 38,175 tokens, with no observed transport retry. The benchmark confirms the predeclared fictional policies automatically after a field-by-field match. Interactive users still see and confirm their results.

| Action | Time budget | Maximum HTTP attempts | Observed token threshold |
| --- | ---: | ---: | ---: |
| Text interpretation | 12 s | 6 | 18,000 |
| Audit | 18 s | 16 | 45,000 |
| Follow-up | 22 s | 18 | 50,000 |

Transport allows one SDK retry for eligible failures. Once an action ends the budget blocks additional requests, while previously sent requests can still finish at the provider. Reported token thresholds use completed responses. The independent review remains mandatory.

## Earlier package and evidence

| Item | Version and result |
| --- | --- |
| Application code | [fecddec](https://github.com/WindsTrace/datathon-prep/commit/fecddec1812115b52b6b8d3a61fae9681f2f23e6). Later packaging commits contain documentation and media. |
| Clean checkout | **113/113** tests passed with the complete organizer ZIP. Official-data offline CLI **6/6** including ambiguity, incomplete disclosure and tampering. |
| Live integration | Robert and Amira staged Bedrock paths and the one-rule challenge ran on the exact application commit in the competition AWS account. The live selection and independent replay were observed separately. The live AWS CLI passed all six scenarios at the same commit. [Sanitized live evidence](live-proof.json) |
| Original intake regression | Production Sonnet 4.5 matched **12/12**, including **2/2** on the original unauthorized quotation. Both repetitions of ambiguous loss and incompatible funding asked the correct question. Compare **6/12** on the same cohort at `13ccc42`. |
| Other intake tests | The separately frozen quote cohort matched **12/12**. The mixed cohort matched **18/20** and produced two unnecessary purchase-size clarifications. No cohort emitted a premature policy for the expected-hold cases. All audited inputs still require confirmation. |
| Architecture and quality | [Earlier official-data architecture benchmark](../AGENT_ITERATION.md). The expanded staged and bundled live comparison scored 20/20 per arm, fixed structured rules scored 10/20, and each arm passed 2/2 missing-FX checks. Staged versus bundled confirmed-to-reviewed p50 was 2.55 s versus 2.54 s. Both live arms share the text-aware selector. |

The video uses genuine offline Streamlit screens recorded at `13ccc42`. The segment labeled live reports a separately recorded competition Bedrock run of that version. The earlier `fecddec` code revision expanded Profile wording. Its independently rerun live case and intake evidence is linked in the preceding table.

## Reproduce

Use Python 3.10+ in a clean clone with the official starter ZIP kept outside the repository.

```bash
git checkout 0c39d080edc7c050186df1ebea43e14c8473471e
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATATHON_STARTER_PATH=/path/to/Datathon2026.zip
export DATATHON_FULL_STARTER_PATH="$DATATHON_STARTER_PATH"
python -m unittest discover -s tests -q
python -m datathon --data "$DATATHON_STARTER_PATH" --case all --stress --mode offline
python -m datathon.resilience_benchmark --data "$DATATHON_STARTER_PATH" --repeats 2 \
  --report outputs/resilience-scripted.json
python -m streamlit run app.py
```

In the app, use **Reference case** and **Offline** to reproduce Robert's 14% terminal-loss frontier, switch the measure to maximum drawdown, and open Amira's evidence request. Offline uses real financial data and calculations with simulated agent events. Use **Bedrock** with an authorized AWS session for live agent events and request IDs. Tool routing fallback is labeled separately when used. The application withholds a decision when independent review fails.

Live benchmarks require an authorized competition AWS session. Intake cohorts are assessed independently.

```bash
python -m tests.test_intake_release \
  --cohort mixed --model global.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --repeats 2 --jobs 3 --report outputs/intake-mixed.json
python -m tests.test_intake_release \
  --cohort bilingual --repeats 2 --jobs 3 --report outputs/intake-bilingual.json
python -m tests.test_intake_release \
  --cohort issuer --repeats 2 --jobs 2 --report outputs/intake-issuer.json
python -m tests.test_profile_quote_holdout \
  --repeats 2 --jobs 3 --report outputs/intake-quotes.json
python -m datathon.runtime_benchmark --data "$DATATHON_STARTER_PATH" --mode aws \
  --jobs 1 3 --repeats 2 --report outputs/runtime-live.json
```

[Demo video](alphaforge-demo.mp4) · [Demo script](demo-script.md) · [Demo visuals](visual-handout.pdf) · [One-page summary](one-pager.pdf) · [Technical summary](technical-summary.pdf)

## Organizer format and submission

The official English case, pages 15–16, calls for a demonstrable prototype, code and README, a roughly five-minute video, a one-page maximum summary and technical documentation. MP4 and PDF are the team's chosen file formats. The organizer website gives deadlines and directs competition-time coordination through the event communications. The repository and application package is ready for hand-in from the team's private repository. Formal contest upload and repository visibility are team-managed. [Organizer schedule](https://polyfinances.ca/datathon#competition) · [Event Discord](https://discord.gg/TDGKhbzhm)
