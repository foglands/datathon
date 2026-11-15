# AlphaForge AI release verification

PolyFinances Datathon 2026 · verified November 14, Montréal

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
