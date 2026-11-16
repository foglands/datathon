# AlphaForge AI · Current demonstration script

This is the recording plan for the revised three-action workspace. It is not evidence that a new video has been recorded. The existing `alphaforge-demo.mp4` is the earlier 5:23 recording at `13ccc42`, with offline interaction screens and separately recorded AWS evidence. Retain that attribution until a replacement is actually produced.

Target duration: approximately five minutes. Record the actual application and its visible statuses. Use the same frozen organizer archive across the scenes. Keep credentials, account identifiers and unrelated browser content out of the recording. Claim a current live AWS call only when its successful trace is visible in that run.

## 0:00–0:30 · The question

Show the Investment assistant and its three actions.

> Tell AlphaForge what you want to test and which rules matter. It compares two choices, evaluates one allocation, or audits a hypothetical trade. It shows which rule caused a breach, which calculation supports that finding, and what remains uncertain. These are historical self-assessments. The application does not execute trades or forecast returns.

## 0:30–1:15 · Amira: compare and explain

Select **Try Amira's question** and append `I care most about maximum drawdown.` The question compares NVDA and QQQ in the context of growth and diversification beyond technology. English and French input can use the model-assisted route; keep this recording and its outputs in English. Review both 100% illustrative reference allocations and explicitly select a named, verified ranking window. Confirm and show both report views. These references differ from the complete portfolio alternatives in the optional CLI example; do not mix their results.

> The model proposes the task, while the investor checks the actual inputs. A profile supplies context, not an automatic financial rule. Here, the confirmed priority is maximum drawdown. Both assets use the same CAD dates. Explanation first and Metrics first display the same reviewed values, and switching views does not run the model again. This establishes a historical comparison. It does not establish diversification beyond technology: a fund label alone cannot resolve missing underlying exposure evidence.

## 1:15–2:35 · Robert: same purchase, different risk definition

Use the starting allocation SPY 35%, XIU.TO 25%, QQQ 20%, ZST.TO 20%. Draft the original proposal to add 10 percentage points of NVDA by selling ZST.TO, keep 15% ZST.TO and cap loss at 14%. Show the clarification and choose terminal loss. Confirm the complete allocation and rules. Then separately authorize QQQ/ZST.TO funding. Show the actual calculated bounds rather than typing a result into the video.

> Robert's original purchase sells part of the reserve holding. First we audit exactly that proposal. The rule table identifies both the reserve requirement and the historical loss test. No alternative search has run. Now Robert explicitly authorizes the two funding holdings. Python solves that defined search and independently checks its certificate. Each source range is a marginal bound at the selected purchase size, so its endpoints are not independently interchangeable.

Create a second confirmed audit changing only terminal loss to maximum drawdown. Preserve the original record.

> Now only the definition of loss changes. Maximum drawdown measures the fall from a previous peak, rather than only the difference between the first and last value. The reported result changes according to that rule. If the authorized set is infeasible, the independent certificate supplies the reason; the application does not quietly relax the cap.

## 2:35–3:20 · Mateo: an honest evidence boundary

Evaluate a small covered portfolio containing a directly screened issuer and an ETF. Set an explicit GPFG exclusion or exclusion-and-observation rule; do not conflate the two. Show source date, disposition, coverage and unknown weight.

> Mateo asks for environmental and social controversy screening. AlphaForge uses a named, dated GPFG policy list. Excluded, under observation and not listed mean different things. Not listed is not an ESG rating. A verified direct-issuer check does not screen an ETF's undisclosed constituents. The financial calculations remain inspectable, while the unresolved screening rule stays unknown.

## 3:20–3:55 · A new asset and date boundary

Enter `I want to invest in 200 shares of AMD.` Show the request for allocation/portfolio context and the absence of eligible archived AMD prices. Demonstrate the supplementary CSV control and source/publication fields. Upload only a prepared, dated public-data example if it has been validated; otherwise leave the gap visible.

> A quantity alone does not define portfolio impact. The assistant needs the allocation and capital context. If an asset is absent from the archive, it asks for qualified data rather than presenting another asset as AMD. The knowledge date also checks when the source became available. A later retrieved, back-adjusted series cannot be presented as a vintage that was known earlier.

## 3:55–4:35 · Follow a value and show AWS

Expand a drawdown metric record, its source rows and review identity. Show the live Bedrock trace from this run, if available. Download JSON and a PDF. If the configured versioned bucket is available, save the report and show the returned version receipt.

> This number links to a metric identifier, formula version, window, source rows and file hash. An independent calculation checks it before publication. Bedrock interpreted the question and can assemble a short explanation from approved sentences and fixed transitions. Python owns the values and rule verdicts. The JSON and PDF share the reviewed record. A configured S3 bucket stores a versioned copy and returns its object receipt.

If a live call or S3 write is unavailable, say so and show the separately attributed historical proof. Do not label a mock or offline run live.

## 4:35–5:00 · Why the result is useful

Close on the original, changed-rule and evidence-limited reports.

> AlphaForge makes the trade-off reviewable: what was tested, which rule mattered, what would change the answer, and what evidence is missing. It keeps original decisions separate from authorized alternatives. Formula verification cannot remove source uncertainty or predict future losses. The repository includes the methods, tests, evidence boundaries and instructions to reproduce the result.

## Recording acceptance

- Record the application revision, organizer-data digest and execution mode alongside the video.
- Show confirmation before calculation and separate authorization before funding search.
- Change one Robert rule at a time; preserve the other inputs and the original report.
- Keep missing ETF screening coverage and unavailable metrics visible.
- Show actual result and AWS receipt values; do not substitute scripted numbers.
- Identify the existing recording as historical until a new MP4 is generated and checked.
