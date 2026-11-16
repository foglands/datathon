"""Opt-in reproducible before/after observations, without an automatic quality claim."""
import asyncio
from time import monotonic

from .customer_acceptance import FrozenResearch, compact_report
from .customer_agents import CustomerAgents, customer_runtime
from .customer_workflow import research_question
from .runtime_budget import RuntimeBudgetExceeded


class CountRuntime:
    """Apply the same model invocation ceiling to both versions."""
    def __init__(self, inner):
        self.inner, self.calls, self.latencies = inner, 0, []

    def _role_instructions(self, role):
        return self.inner._role_instructions(role)

    def _inference_parameters(self, role):
        return self.inner._inference_parameters(role)

    async def run(self, role, payload, **kwargs):
        if self.calls >= 10:
            raise RuntimeBudgetExceeded("comparison_model_calls")
        self.calls += 1
        started = monotonic()
        try:
            return await self.inner.run(role, payload, **kwargs)
        finally:
            self.latencies.append({"role": role, "elapsed_seconds": round(monotonic() - started, 3)})


async def compare_revision(question, progress=lambda _: None):
    """The optional baseline is an immutable source copy, never reconstructed prose."""
    current = customer_runtime()
    provider = FrozenResearch()
    result = {"question": question, "model": current.model_id, "region": current.region,
        "limits": {"seconds_per_version": 240, "model_calls_per_version": 10, "source_cache": "shared"},
        "baseline_commit": "085de5df9e0047dd7334b25824990f4bb2b4157a", "versions": {},
        "assessment": "Raw reproducible observations; no uncalibrated correctness score. Task ledgers were absent in the baseline."}
    try:
        from _baseline_2209.customer_agents import CustomerAgents as BeforeAgents
        from _baseline_2209.customer_workflow import research_question as before_question
        # Same output ceilings for comparable runs; role instructions stay revision-specific.
        class ComparableBefore(BeforeAgents):
            def _output_token_limit(self, role):
                return current._output_token_limit(role)
        before = ComparableBefore(model_id=current.model_id, region=current.region, timeout_seconds=45, max_total_tokens=26000)
        versions = [("before", before_question, before), ("after", research_question, current)]
    except ImportError:
        result["baseline_unavailable"] = "No preserved baseline source was available. No improvement comparison is claimed."
        versions = [("after", research_question, current)]
    for name, workflow, runtime in versions:
        progress("Running " + name + " with the same model and cached public observations")
        counted = CountRuntime(runtime)
        started = monotonic()
        try:
            report = await asyncio.wait_for(workflow(question, runtime=counted, provider=provider, progress=progress), 240)
            result["versions"][name] = {"report": compact_report(report), "status": report["status"]}
        except (asyncio.TimeoutError, RuntimeBudgetExceeded):
            result["versions"][name] = {"status": "budget_exhausted"}
        result["versions"][name].update(elapsed_seconds=round(monotonic() - started, 3), model_calls=counted.calls,
                                       calls=counted.latencies)
    result["source_requests"] = [{"method": key[0], "arguments": list(key[1:])} for key in provider.cache]
    return result


async def collect_reliability_cases(progress=lambda _: None):
    """Fresh paired outputs for external/manual semantic assessment, not a model score."""
    import json
    import tempfile
    from pathlib import Path
    base = "I am Alex. I am considering 5700 USD in ITOT for a home deposit in 36 months. I have not set a loss limit. What does the historical evidence support and what remains uncertain?"
    cases = {"baseline": base, "renamed": base.replace("Alex", "Jordan"),
        "unrelated_detail": base + " My hobby is drawing.",
        "paraphrase": "My name is Alex. I am thinking of putting USD 5700 into ITOT towards a home down payment in 3 years. My loss limit is undecided. Explain what past observations can establish and the important unknowns.",
        "material_change": base + " I now need to withdraw the full 5700 USD in 3 months instead, with no other funds for this payment."}
    provider = FrozenResearch()
    result = {"cases": {}, "grading": "Code checks calculations; semantic comparison requires separate inspection. No automatic overall pass."}
    for name, question in cases.items():
        progress("Collecting paired case: " + name)
        result["cases"][name] = compact_report(await research_question(question, runtime=customer_runtime(), provider=provider, progress=progress))
        Path(tempfile.gettempdir(), "alphaforge-reliability-cases.json").write_text(json.dumps(result, indent=2))
    original = result["cases"]["baseline"]["metrics"]
    result["calculation_checks"] = {name: row["metrics"] == original for name, row in result["cases"].items()}
    result["note"] = "The material change alters relevance and cash-flow analysis, not the identical asset's no-withdrawal historical metrics."
    Path(tempfile.gettempdir(), "alphaforge-reliability-cases.json").write_text(json.dumps(result, indent=2))
    return result
