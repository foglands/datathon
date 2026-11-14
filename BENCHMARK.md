# Architecture benchmark

The benchmark measures three ways to run the same portfolio audit after the investment constraints have been confirmed.

| Arm | How the audit runs |
| --- | --- |
| Deterministic | Python runs the stages and independent review with no inference. |
| Bundled single agent | One Strands session calls the same Python tools and summarizes the reviewed result. Tool dependencies and release gates are checked in code. |
| Multi-agent | Separate Strands sessions handle evidence, applicable exposure, scenarios, alternatives, review and explanation. Evidence and Scenario may use the recorded deterministic fallback. |

All arms use the official adjusted prices, CAD conversion, historical windows, disclosure qualification, funding solver and independent reviewer. The two AWS arms use the same Nova 2 Lite inference profile and region. Both produce the same deterministic decision explanation once the required review completes. Model commentary is separate.

Ten structured cases include terminal loss, drawdown, exact and smaller authorized purchases, a clean approval, known issuer breach, missing and stale holdings, a tampered calculation, and a structured input derived from the quoted-instruction case. The preregistered financial expectations and selected numerical bounds are in [benchmark_cases.py](datathon/benchmark_cases.py).

The six raw requests separately test the **shared production Profile parser** used ahead of either model architecture. The test gives the parser only the fictional request. It scores the full parsed policy or the material clarification field and releases no financial result. The deterministic workflow starts at confirmed fields. It has no free-text arm.

## Scoring and reproduction

- Status, reason, solver and starting-portfolio verdict are scored against the fixture expectations. The verifier's complete recomputed output is compared with the deterministic control for the same inputs. Selected expected funding boundaries are also checked within `1e-8` of portfolio weight.
- Score the original proposal and the availability of a positive-size, independently verified alternative as separate release opportunities. An incorrect positive result counts as a false release. Withholding an expected positive result counts as an avoidable hold. Potential funding noted by a rejected audit cannot count as a release.
- Trace completeness requires a reviewed proposal, both required windows, source identifiers and a successful review tool call for AWS. For the deterministic arm, recomputed audit findings provide the provenance.
- Median and range measure elapsed time for a decision after the data and structured input are ready. Each pair runs its model arms sequentially and alternates the starting arm. The AWS run allows three simultaneous pairs. Bedrock-reported tokens and Converse totals describe usage without assuming any dollar price.
- Each multi-agent stage has a 35-second timeout, 5 turns and 9,000 token budget. The expanded single session has 95 seconds, 16 turns and 54,000 tokens across its whole audit. Both use a 700-token response cap. These settings, session layout and fallback policies are workflow differences. This is not a causal test of agent count in isolation.

```bash
python -m pip install -r requirements.txt
python -m datathon.benchmark --data /path/to/Datathon2026.zip --mode offline \
  --repeats 2 --report outputs/benchmark-offline.json
python -m datathon.benchmark --data /path/to/Datathon2026.zip --mode aws \
  --repeats 2 --jobs 3 --code-ref e9e1b0a424182c3faaaa1bea11885dcdc0abc599 \
  --report outputs/benchmark-aws.json
```

Use the competition AWS participant credentials for the live run. The report includes the input file fingerprints, configuration, per-case observations and aggregate counts.

The team workshop brief reinforced the distinction between technical errors and valid outcomes under policy. A breached cap or unresolved disclosure still counts as a valid run when the fixture expects it. Budget exhaustion or an absent handoff is an execution error. Keep this distinction in the demo and show reproducible evidence on both Robert's and Amira's routes.

## Measured results

Competition CloudShell, `us-east-1`, Strands 1.63.0 and Nova 2 Lite, at
[`e9e1b0a`](https://github.com/WindsTrace/datathon-prep/commit/e9e1b0a424182c3faaaa1bea11885dcdc0abc599).
Each of the ten structured fixtures ran twice per arm. Each fixture repeated its expected decision and independent audit in every arm.

| Arm | Correct status and reason | Full audit parity | Trace complete | False releases | Avoidable holds | Median (range) | Converse | Input / output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Deterministic | 20/20 | 20/20 | 20/20 | 0/28 | 0/12 | 10.30 ms (8.52–119.57 ms) | 0 | 0 / 0 |
| Single agent | 20/20 | 20/20 | 20/20 | 0/28 | 0/12 | 4.78 s (3.71–6.98 s) | 112 | 433,032 / 7,407 |
| Multi-agent | 20/20 | 20/20 | 20/20 | 0/28 | 0/12 | 9.44 s (7.58–10.93 s) | 190 | 437,720 / 20,775 |

All model responses in the measured decision cohort reported usage. The two AWS arms had zero failed Converse responses and zero deterministic routing fallbacks in this run. Single and multi shared the same numerical and release gates. The single agent took about half the median time and made 41% fewer Converse calls. It used similar input token volume and fewer output tokens. The staged workflow provides dedicated role records and a defined recovery path, whose incremental value was not demonstrated in this final run.

The separate shared Profile parser matched the gold policy or question on **10/12** attempts. It asked the right question on all **4/4** ambiguous or contradictory attempts and emitted no premature policy in those cases. The two errors were unnecessary loss-metric questions on the repeated quoted-instruction request, so that case was held. The structured audit of the already confirmed request passed in both repetitions. Free-text clarification and the upstream human confirmation remain part of normal operation.

### Diagnosis and limits

| Iteration | Single correct status | Multi correct status | Shared intake correct | Observation |
| --- | ---: | ---: | ---: | --- |
| Initial budget, nine cases × two | 3/18 | 18/18 | 4/12 | Single exhausted turns or tokens. |
| Expanded budget at [`b9d22a5`](https://github.com/WindsTrace/datathon-prep/commit/b9d22a5500c36dbd263561a42a538854ba9ebd02), ten cases × two | 5/20 | 20/20 | 3/12 | A traced terminal-loss case kept submitting an invalid evidence scope. |
| Explicit scope enum and risk definitions at `e9e1b0a`, ten cases × two | 20/20 | 20/20 | 10/12 | Both decision arms completed the matched suite; the shared parser still over-clarified the quoted-instruction case. |

The expanded budget alone did not resolve the failure. Making the scope values explicit in the tool schema and bundled prompt was followed by complete results on the same ten cases. The revised Profile prompt also made common risk definitions and funding conflicts explicit. The final rerun uses these same development fixtures, so it measures observed repeatability rather than held-out generalization. The measured result does not establish arbitrary-portfolio coverage, suitability, any per-role quality lift or a model-independent speed advantage. No monetary cost estimate was used.

### Input fingerprints

SHA-256 of the decoded CSV text in the CloudShell run.

| File | SHA-256 |
| --- | --- |
| `prices_daily.csv` | `ff2a3f2d0a7d72ea835e8d616d041e0510f018340cef3d3e55b918830e8a569d` |
| `fx_usdcad_daily.csv` | `f04e218ac5b0145fd552b3d0dcfbf73e5e17bb9a6fb4562460dbec95cb8972b3` |
| `sources_metadata.csv` | `7ff17052c8235888c4984430830610ae0d81c0df71585afaacb87ba5fe531bdf` |
