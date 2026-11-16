# AlphaForge AI

## Know which rule changes the decision

Tell AlphaForge what you want to test and which rules matter. It uses independently checked historical data to explain a hypothetical investment decision: which rule is met, what caused a breach, and which evidence is missing.

**Compare two choices · Evaluate one allocation · Audit a proposed trade**

| Fictional investor | Question and useful answer |
| --- | --- |
| **Amira — growth and diversification** | Compare two confirmed exposures over the same historical dates. Show risk and return trade-offs, while leaving incomplete issuer look-through visible. |
| **Robert — capital preservation** | Audit one purchase, then authorize specific alternative funding. Changing terminal loss to maximum drawdown can change feasibility without changing the trade or market data. |
| **Mateo — controversy preferences** | Apply a named, dated GPFG screen. Distinguish excluded, observation and not listed; unassessed ETF constituents remain unknown. |

### Why the result is reviewable

A model proposes a source-grounded draft from English or French input; the user confirms its terms. Python calculates CAD buy-and-hold metrics from frozen prices and same-date FX. Separate implementations and rational funding-certificate checks verify the result. Publication binds the input, rules, methods and facts. Explanation-first and metrics-first views, JSON and PDF share that reviewed record.

In the fictional Robert example, buying 10 portfolio percentage points of NVDA from ZST.TO produces a 16.15% terminal loss in the 2022 replay, above the 14% cap. The separately authorized QQQ/ZST.TO search needs at least approximately 7.37 points from QQQ for the same purchase. This is a checked historical boundary, not a forecast.

### AWS has an observable role

Strands calls Amazon Bedrock for drafting, a bounded explanation assembled from approved sentences and fixed transitions, and the preserved delegated follow-up. Recorded traces distinguish real requests from offline execution. Optional S3 storage checks bucket versioning and returns an object version receipt. The verification record identifies the exact revisions that received live AWS acceptance; it does not transfer older results to new code.

### Practical value and limits

AlphaForge helps a learner or reviewer answer: **What was tested? Which rule mattered? What would change the answer? What is still unknown?** It is a historical simulation, not advice, a forecast or a trading system. Complete ETF controversy screening, unrestricted rule/language coverage and some target services remain unfinished and are listed in the architecture-status matrix.

[Code and reproduction](https://github.com/foglands/datathon) · [Technical documentation](technical-summary.md) · [Verification](verification.md)
