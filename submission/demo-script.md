# AlphaForge AI · Portfolio Decision Audit

PolyFinances Datathon 2026 · Demonstration script

The 5:23 recording uses genuine Streamlit reference runs against the organizer’s data. The interaction screenshots use Offline mode. The AWS chapter shows the separately recorded competition CloudShell results from commit `13ccc42aae144e95b986a731b49fad88a613c225`. The voiceover is synthesized. The final candidate at `fecddec` changes the Profile parser, and its later AWS checks reproduced the same Robert and Amira audit results. [Final-candidate verification](verification.md)

## 0:00–0:26 · Portfolio Decision Audit

Open on the title and show the two fictional investor situations.

> The same NVIDIA purchase can pass or fail depending on what you sell to fund it, and how you define the risk. AlphaForge audits a fictional investment decision against the investor's confirmed rules and the evidence available at the time. In the next five minutes, two investors will test the same trade, and we'll trace exactly what changes the answer.

## 0:26–1:04 · Confirm the rules before the audit

Show the confirmed trade, reserve and loss terms. Explain which clarification matters before the replay.

> Robert is three to five years from retirement. His starting portfolio holds thirty-five percent S P Y, twenty-five percent X I U, and twenty percent each in Q Q Q and Z S T. He proposes adding ten percentage points of NVIDIA by selling Z S T. He allows either fund for alternatives, allows a smaller buy, and wants to keep at least fifteen percent in Z S T. An instruction like, I cannot lose more than fourteen percent, still needs a risk definition. Here, we confirm terminal loss, from the start to the end of the replay.

## 1:04–1:46 · Robert · terminal loss

Show the actual Streamlit Robert reference audit in Offline mode. Keep the initial and QQQ-financed results visible.

> This is the actual prototype in offline reference mode. The financial calculations use official data and the independent Python audit. Selling ten points of the bond fund leaves only ten percent in reserve and produces a terminal loss of sixteen point one five percent, both breaches. A Q Q Q funded example keeps the twenty percent reserve and loses thirteen point two three percent. The tested range for a full purchase is zero to two point six three percentage points of funding from Z S T, with the rest from Q Q Q. At that boundary the loss cap leaves essentially no headroom.

## 1:46–2:28 · Change only how loss is measured

Show the actual Streamlit result for the changed maximum-drawdown rule, alongside the starting portfolio breach and certificate dates.

> Now we change one rule. Maximum drawdown measures the largest drop from an earlier peak to a later trough within each window. We keep the same portfolio, purchase, allowed funds, reserve floor, market data and fourteen percent cap. Under this definition, the starting portfolio already drops sixteen point zero five percent. The reviewed search finds no permitted purchase size or funding mix. The same hypothetical trade leads to a materially different answer because the risk definition changed. The original audit stays separate so the two decisions can be compared.

## 2:28–3:08 · Follow the figures back to evidence

Show data inputs, CAD conversion, aligned windows and how the independent checks are run.

> Both audits use adjusted closes from the starter archive. U S dollar observations are converted to Canadian dollars using same-day Bank of Canada exchange rates. The simulation aligns common observation dates and replays starting buy-and-hold weights across calendar year twenty twenty-two and early twenty twenty-five. An independent calculation checks the reported outcomes, feasible boundaries and, when relevant, the witness for infeasibility. The selected periods are historical scenarios. The displayed figures exclude trading costs, taxes and intraday moves.

## 3:08–3:50 · Amira · NVIDIA issuer exposure

Show the actual Amira Streamlit result, including the known issuer cap breach and the unresolved alternative.

> Amira wants growth and diversification. She proposes the same NVIDIA purchase, but confirms a fourteen percent issuer cap that includes what the funds already hold. The Z S T funded proposal has documented exposure of at least fourteen point one five percent, enough to establish a breach. Funding the same buy from Q Q Q lowers the documented NVIDIA exposure to thirteen point three nine percent. The underlying weights for two funds remain unverified. The application holds that alternative rather than assuming their undisclosed NVIDIA weights are zero.

## 3:50–4:25 · What evidence would settle it?

Show the QQQ-funded issuer evidence contribution ceiling computed by the prototype.

> The evidence challenge identifies the missing fund disclosures and the numerical requirement. To meet Amira's cap, X I U and Z S T can contribute no more than zero point six zero nine three seven percentage points of combined additional NVIDIA exposure. The existing disclosed weights were observed June thirtieth, twenty twenty-six, and the S E C filings published August twenty-eighth. We keep those holdings separate from the historical price windows. The evidence request does not release a trade.

## 4:25–5:02 · Recorded competition AWS execution

Show the separate competition CloudShell evidence from build 13ccc42, including successful Converse response counts and a request ID prefix.

> These are recorded results from competition CloudShell, separate from the offline interaction screens. Strands calls Amazon Nova Two Lite through Bedrock Converse. The evidence and scenario stages make checked tool selections, and Review independently verifies the numerical results. In the recorded Robert run, Bedrock also selected the loss-definition challenge. For Amira, it selected the qualified evidence request, with no further historical replay. The checked signals and model activity can be inspected as separate records.

## 5:02–5:23 · See what would change the answer

Close with the project, reproducible app and audit.

> AlphaForge shows which tested rules a simulated trade meets, what caused a breach, and what evidence could change the conclusion. The repository includes the reproducible app, independent test suite and measured architecture comparison. Use the audit record to follow each result to its inputs.

## Reproduce the sequence

- Start the app with the organizer’s starter ZIP. Choose **Reference case** and **Offline**, then confirm **Robert · loss definition**. Compare maximum drawdown using **Confirm this change and compare**.
- Choose **Amira · issuer exposure** and confirm the inputs. In **What could change this decision?**, select the check for required issuer disclosures. The starting portfolios and thresholds are fictional.
- Before recording live evidence, use the competition credentials and choose **Bedrock** mode. Expand **Agent activity and AWS trace** to reveal verified calls. Keep account details and tokens out of the recording.
- [Demo video](alphaforge-demo.mp4) · [One-pager](one-pager.pdf) · [Demo visuals](visual-handout.pdf) · [Final-candidate verification](verification.md)
- [Prototype and setup](../README.md) · [Architecture benchmark](../BENCHMARK.md) · [Iteration record](../AGENT_ITERATION.md)
