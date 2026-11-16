# AlphaForge AI: current customer demonstration

Five-minute recording plan for `app.py`. This script is current; `alphaforge-demo.mp4` still records an earlier workbench revision. Use fictional inputs and actual displayed results. Do not show credentials or substitute an older successful run for a failed current one.

## 0:00-0:40: One question

Show the customer homepage: no example buttons, persona choices or Reference cases navigation.

Enter: `I am considering investing 3000 CAD in AMD. I may need the money in two years. What should I understand?`

Explain that unknown conditions remain unknown and optional context is interpreted in relation to the question.

## 0:40-1:30: Observable analysis

Show the stages: understanding, task planning, evidence collection, Python calculations, synthesis and independent review. Open task details after completion to show a question, required measure and actual output. A successful tool call alone does not establish task completion.

Explain that the market price is a dated observation and may be delayed.

## 1:30-2:40: Conclusion, then evidence

Start with the conclusion and its support, counterevidence and limits. Show the indexed history/drawdown charts and cited values. Use only the numbers displayed by this run.

If the result is partial or the interpretation is withheld, explain the specific unresolved task or review feedback. Checked evidence is not relabeled as an accepted personalized answer.

## 2:40-3:40: Change a material condition

Add a fictional follow-up: `Correction: I need to withdraw 2500 CAD in six months for tuition, and I have no other money for that payment.`

Show which active facts changed, which persisted, and how the tasks or conclusion respond. Do not script a predetermined rejection or different verdict. Missing schedule details may legitimately cause a focused question.

## 3:40-4:25: Evidence and AWS

Open source dates, evidence references and model activity. Identify actual Bedrock calls and distinguish local calculations from model judgment. Explain that financial values come from Python and semantic review is a separate, fallible model invocation. Download the HTML report with charts.

## 4:25-5:00: Limits and reproducibility

State the missing data coverage and generalization limits. Explain that official personas are tests only. Point to the README, current validation and technical PDF.

Developer tests and historical cases run separately with `python -m streamlit run validation_app.py`. They do not belong in the customer tour. If showing them in a technical appendix, label them validation and distinguish recorded failed pairs from passed ones.
