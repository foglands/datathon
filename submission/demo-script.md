# AlphaForge AI demonstration

**PolyFinances Datathon 2026 · Team 38 · Peng Peng, Shaoze Ying, Xuhan Liu**

Five-minute recording plan for the current customer app. The main example is the retirement-risk case used in the [one-pager](one-pager.pdf) and [technical documentation](technical-summary.pdf). Use fictional inputs and capture the result from the current run. Keep credentials and hosting settings outside the frame.

## 0:00-0:35 · Problem and team

Show the product and identify Team 38. Explain that the same stock can raise different questions for someone retiring in four years and someone investing for much longer. AlphaForge connects the decision to disclosed evidence, the person's constraints and the limits of the available data.

## 0:35-1:20 · Start the retirement-risk investigation

Choose **A stock before retirement** and select **Apply question**. Show the editable question. The fictional investor is considering Tesla, wants to protect savings and expects to retire in about four years. Submit with **Analyze my question**.

Show progress through intake, planning, sources, calculation, synthesis and review. Point out that the app preserves the stated horizon and that the proposed allocation and acceptable numerical loss threshold remain unknown. A model-only estimate cannot establish those inputs.

## 1:20-2:15 · Show the finding and its consequence

Show the release status and the first available checked finding. The documented pair of split-adjusted closes is USD 409.97 in Q4 2021 and USD 109.10 in Q4 2022. Python computes a 73.39% decline between those points. If both numbers are shown on screen, use them to explain the calculation. This is a concrete example of the size of loss relevant to the stated concern. Full-history maximum drawdown, recovery and the effect on all retirement savings require more evidence.

If the current run releases only checked evidence, show that evidence and label the result accordingly. Show price and drawdown charts when the run has a verified series. Show the documented episode, source links and missing tasks when it has limited coverage.

## 2:15-3:20 · Show how the system obtained and checked evidence

Open **Evidence & sources**. In **Live web searches**, show the returned query, search time, actual links and status. When shown, open **Research service verification** and point to the actual Bedrock Converse model, region and role records. Show the checked filing source separately from the general search links. If the selected example omits a needed lookup, label a supplemental request explicitly and use it to show the relevant search topic.

Explain that Converse plans and reviews the analysis, AgentCore finds sources and Python calculates and verifies the financial measures. Open one observable task to show the requested measure, scope and actual completion status. Show HTML or Markdown export as available, with charts where the evidence supports them.

## 3:20-4:20 · Show another decision

Use **AI and Bitcoin** to show that dated SPY holdings provide evidence of NVIDIA overlap and the IBIT objective identifies Bitcoin exposure. The combined diversification effect needs current exposure and allocations. Briefly point to **Growth with ESG preferences** as an additional test of the same workflow. ESGU's published screening method addresses part of that question. Issuer-level exclusion needs the relevant holdings and screening evidence.

Use a follow-up with a changed constraint, such as a two-year retirement horizon, if it helps show which assumption changed. Corner cases and separate developer tools can be explained while showing the documented capability and its boundary.

## 4:20-5:00 · Close with validation and limitations

Show the GitHub submission index with the team details, technical PDF, one-pager and verification record. Mention the 591-test regression and the separately recorded live AWS searches. Explain that the developer workbench supports reproducible portfolio replay and explicitly authorized funding searches. Note the remaining daily-series and holdings coverage gaps, and describe the review as a distinct check with a visible outcome.

The earlier `alphaforge-demo.mp4` records the historical workbench. This script addresses the customer interface.
