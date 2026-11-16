# AlphaForge AI: current customer demonstration

Five-minute recording plan for `app.py`. This script is current; `alphaforge-demo.mp4` still records an earlier workbench revision. Use fictional inputs and actual displayed results. Do not show credentials or substitute an older successful run for a failed current one.

## 0:00-0:40: One question

Select **AI and Bitcoin**, click **Apply question**, then click **Analyze my question**. The question is a fictional adaptation of the official Amira case. The investor holds SPY, has at least 15 years, tolerates big swings and is considering adding NVDA and IBIT. They want to know what that means for diversification.

Show that the loaded text can be edited. Explain that the application uses the conditions the user stated, and that the size of each position is still unknown.

## 0:40-1:30: Observable analysis

Show the stages: understanding, task planning, evidence collection, Python calculations, synthesis and independent review. Open task details after completion to show a question, required measure and actual output. A successful tool call alone does not establish task completion.

Explain that the market price is a dated observation and may be delayed.

## 1:30-2:40: Conclusion, then evidence

Start with the conclusion and its support, counterevidence and limits. Show the indexed history/drawdown charts and cited values. Use only the numbers displayed by this run.

If the result is partial or the interpretation is withheld, explain the specific unresolved task or review feedback. Checked evidence is not relabeled as an accepted personalized answer.

## 2:40-3:40: Compare a different situation

Start a new research request with **A stock before retirement**, the Robert adaptation. The investor hopes to retire in about four years, wants to protect savings and is tempted by TSLA. Show how the analysis addresses historical declines and the retirement horizon. Use the actual answer and identify any missing position size or withdrawal details.

The third example, **Growth with ESG preferences**, adapts the Mateo case. In an extended walkthrough, compare growth and stability across ESGU and SPY and show what the available evidence can establish about the investor's controversy exclusions.

## 3:40-4:25: Evidence and AWS

Open source dates, evidence references and model activity. Identify actual Bedrock calls and distinguish local calculations from model judgment. Explain that financial values come from Python and semantic review is a separate, fallible model invocation. Download the HTML report with charts.

## 4:25-5:00: Limits and reproducibility

State the missing data coverage and generalization limits. Explain that the three examples use the same workflow as a question typed from scratch. Point to the README, current validation and technical PDF.

Developer tests and historical cases run separately with `python -m streamlit run validation_app.py`. They do not belong in the customer tour. If showing them in a technical appendix, label them validation and distinguish recorded failed pairs from passed ones.
