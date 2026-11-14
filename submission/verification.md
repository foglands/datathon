# AlphaForge AI release verification

PolyFinances Datathon 2026 · verified November 14, Montréal

## Release and evidence

| Item | Version and result |
| --- | --- |
| Application code | [fecddec](https://github.com/WindsTrace/datathon-prep/commit/fecddec1812115b52b6b8d3a61fae9681f2f23e6). Later packaging commits contain documentation and media. |
| Clean checkout | **113/113** tests passed with the complete organizer ZIP. Official-data offline CLI **6/6** including ambiguity, incomplete disclosure and tampering. |
| Live integration | Robert and Amira staged Bedrock paths and the one-rule challenge ran on the exact application commit in the competition AWS account. The live selection and independent replay were observed separately. The live AWS CLI passed all six scenarios at the same commit. [Sanitized live evidence](live-proof.json) |
| Original intake regression | Production Sonnet 4.5 matched **12/12**, including **2/2** on the original unauthorized quotation. Both repetitions of ambiguous loss and incompatible funding asked the correct question. Compare **6/12** on the same cohort at `13ccc42`. |
| Other intake tests | The separately frozen quote cohort matched **12/12**. The mixed cohort matched **18/20** and produced two unnecessary purchase-size clarifications. No cohort emitted a premature policy for the expected-hold cases. All audited inputs still require confirmation. |
| Architecture and quality | [Earlier official-data architecture benchmark](../AGENT_ITERATION.md). The expanded staged and bundled live comparison scored 20/20 per arm, fixed structured rules scored 10/20, and each arm passed 2/2 missing-FX checks. Staged versus bundled confirmed-to-reviewed p50 was 2.55 s versus 2.54 s. Both live arms share the text-aware selector. |

The video uses genuine offline Streamlit screens recorded at `13ccc42`. The segment labeled live reports a separately recorded competition Bedrock run of that version. The current code revision expands Profile wording only. Its independently rerun live case and intake evidence is linked above.

## Reproduce

Use Python 3.10+ in a clean clone with the official starter ZIP kept outside the repository.

```bash
git checkout fecddec1812115b52b6b8d3a61fae9681f2f23e6
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATATHON_STARTER_PATH=/path/to/Datathon2026.zip
export DATATHON_FULL_STARTER_PATH="$DATATHON_STARTER_PATH"
python -m unittest discover -s tests -q
python -m datathon --data "$DATATHON_STARTER_PATH" --case all --stress --mode offline
python -m streamlit run app.py
```

In the app, use **Reference case** and **Offline** to reproduce Robert's 14% terminal-loss frontier, switch the measure to maximum drawdown, and open Amira's evidence request. Offline uses real financial data and calculations with simulated agent events. Use **Bedrock** with an authorized AWS session for live agent events and request IDs. Tool routing fallback is labeled separately when used. The application withholds a decision when independent review fails.

The three intake cohorts are assessed independently. Use the production model identifier for both original and new requests. The two packaged held-out runners require only an authorized AWS session.

```bash
python -m tests.test_intake_release \
  --model global.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --repeats 2 --jobs 3 --report outputs/intake-mixed.json
python -m tests.test_profile_quote_holdout \
  --repeats 2 --jobs 3 --report outputs/intake-quotes.json
```

[Demo video](alphaforge-demo.mp4) · [Demo script](demo-script.md) · [Demo visuals](visual-handout.pdf) · [One-page summary](one-pager.pdf) · [Technical summary](technical-summary.pdf)

## Organizer format and submission

The official English case, pages 15–16, calls for a demonstrable prototype, code and README, a roughly five-minute video, a one-page maximum summary and technical documentation. MP4 and PDF are the team's chosen file formats. The organizer website gives deadlines and directs competition-time coordination through the event communications. The repository and application package is ready for hand-in from the team's private repository. Formal contest upload and repository visibility are team-managed. [Organizer schedule](https://polyfinances.ca/datathon#competition) · [Event Discord](https://discord.gg/TDGKhbzhm)
