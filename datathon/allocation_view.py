"""Present independently verified allocation analysis in Streamlit."""

import json
from collections.abc import Mapping

import altair as alt
import streamlit as st

from .allocation_compare import publish_allocation_comparison
from .investor_profile import PRIORITIES, InvestorProfile


_STATUS = {
    "verified": ("Verified comparison", "green"),
    "limited": ("Limited comparison", "orange"),
    "withheld": ("Comparison withheld", "red"),
}
_REPLAY_STATUS = {
    "verified": ("Verified allocation replay", "green"),
    "limited": ("Limited allocation replay", "orange"),
    "withheld": ("Allocation replay withheld", "red"),
}
_MEASURE_BASIS = {
    "terminal_return": "Lowest terminal return across the selected windows",
    "terminal_loss": "Highest terminal loss across the selected windows",
    "max_drawdown": "Highest drawdown across the selected windows",
}
_PREFERRED_RESULT = {
    "terminal_return": "highest minimum terminal return",
    "terminal_loss": "lowest maximum terminal loss",
    "max_drawdown": "lowest worst-window drawdown",
}
_CAP_RESULT = {"pass": "Meets the drawdown limit", "fail": "Breaches the drawdown limit"}
_ALLOCATION_COLORS = ("#165b46", "#7d978d")
_REQUEST_LABELS = {
    "first_asset": "First asset",
    "second_asset": "Second asset",
    "options": "Allocation weights",
    "weights": "Allocation weights",
    "objective": "Investment objective",
    "withdrawal_time": "Withdrawal horizon",
    "risk_tolerance": "Willingness to take risk",
    "priority": "Comparison priority",
    "max_drawdown": "Drawdown limit",
    "include_2023": "2023 stress window",
    "require_esg": "ESG requirement",
}
_ROUTING_STATES = {"ready", "proposed", "unsupported", "unavailable", "needs_input"}
_ROUTING_TASKS = {"trade_audit", "compare_allocations", "analyze_allocation"}
_TRACE_FIELDS = {
    "event", "role", "model_id", "region", "tool_name", "status", "duration_ms", "operation", "request_id", "http_status",
    "retry_attempts", "input_tokens", "output_tokens", "total_tokens",
}
_USAGE_FIELDS = {"elapsed_ms", "http_attempts_started", "responses_observed", "reported_total_tokens", "limit_reached"}


def _routing_record(intent: dict | None, *, from_request: bool = False, single: bool = False) -> dict:
    task = "analyze_allocation" if single else "compare_allocations"
    if not intent or intent.get("status") not in _ROUTING_STATES:
        mode = "request_text" if from_request else "direct"
        return {"confirmed_task": task, "mode": mode}
    return {
        "confirmed_task": task,
        "mode": "bedrock_attempt",
        "status": intent["status"],
        "suggested_task": intent["task"] if intent.get("task") in _ROUTING_TASKS else None,
        "trace": [{key: value for key, value in event.items() if key in _TRACE_FIELDS} for event in intent["trace"]],
        "usage": {key: value for key, value in intent["usage"].items() if key in _USAGE_FIELDS},
    }


def _finding_message(report: dict) -> str:
    if report.get("kind") == "single_allocation":
        if not report["options"]:
            return "Verified historical figures are unavailable."
        allocation = next(iter(report["options"].values()))
        if allocation["max_drawdown_test"] == "fail":
            return "The replay breached the confirmed drawdown limit in at least one historical window."
        if allocation["max_drawdown_test"] == "pass":
            return "The replay met the confirmed drawdown limit in every tested historical window."
        return ""
    finding = report["finding"]
    status, basis = finding["status"], finding["basis"]
    if basis == "all_breach_cap":
        return "Both options breach the confirmed drawdown limit in at least one selected window."
    if status == "unavailable":
        return "A relative finding is unavailable under the confirmed requirements."
    if status == "neutral":
        return ""
    if status == "tie":
        measure = _MEASURE_BASIS[report["priority"]].lower()
        return f"The eligible options tie on {measure}."
    option = finding["option"]
    if basis == "cap_pass":
        return f"{option} is the only option that meets the confirmed drawdown limit."
    return f"{option} had the {_PREFERRED_RESULT[report['priority']]} among the eligible options."


def _render_chart(report: dict) -> None:
    measures = tuple(PRIORITIES)
    initial_measure = report["priority"] or "max_drawdown"
    metric = st.radio(
        "Historical measure", measures, index=measures.index(initial_measure),
        format_func=PRIORITIES.__getitem__, horizontal=True, key=f"allocation-measure-{report['priority']}",
    )
    options = report["options"]
    series = [
        {"Option": name, "Replay": window_id, "Value": window[metric]}
        for name, option in options.items()
        for window_id, window in option["windows"].items()
    ]
    label = PRIORITIES[metric]
    chart = (
        alt.Chart(alt.Data(values=series))
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Replay:N", sort=sorted({row["Replay"] for row in series}), axis=alt.Axis(title=None, labelAngle=0)),
            xOffset=alt.XOffset("Option:N", sort=list(options)),
            y=alt.Y("Value:Q", title=label, axis=alt.Axis(format=".0%")),
            color=alt.Color(
                "Option:N", title=None, scale=alt.Scale(domain=list(options), range=list(_ALLOCATION_COLORS)),
                legend=alt.Legend(orient="bottom") if len(options) > 1 else None,
            ),
            tooltip=["Option:N", "Replay:N", alt.Tooltip("Value:Q", title=label, format=".2%")],
        )
    )
    constraint = report["requirements"]["max_drawdown"]
    if metric == "max_drawdown" and constraint["status"] == "assessed":
        limit = constraint["limit"]
        line = (
            alt.Chart(alt.Data(values=[{"Limit": limit}]))
            .mark_rule(color="#a85a20", strokeDash=[5, 4], strokeWidth=2)
            .encode(y="Limit:Q", tooltip=alt.Tooltip("Limit:Q", title="Confirmed limit", format=".2%"))
        )
        chart = chart + line
        st.caption(f"Dashed line marks the confirmed {limit:.2%} maximum drawdown limit.")
    chart = (
        chart.properties(height=218)
        .configure_view(stroke=None)
        .configure_axis(domain=False, tickSize=0, gridColor="#e3ede7", labelColor="#51615a", titleColor="#35453e")
    )
    st.altair_chart(chart, width="stretch", key="allocation-performance-chart")


def _render_key_figures(report: dict) -> None:
    options = report["options"]
    single = report.get("kind") == "single_allocation"
    priority = report["priority"]
    with st.container(key="allocation-key-figures"):
        if single:
            windows = next(iter(options.values()))["windows"].values()
            worst_drawdown, lowest_return = st.columns(2)
            worst_drawdown.metric("Largest drawdown", f"{max(window['max_drawdown'] for window in windows):.2%}",
                                  border=True)
            lowest_return.metric("Lowest terminal return", f"{min(window['terminal_return'] for window in windows):.2%}",
                                 border=True)
            return
        st.caption(_MEASURE_BASIS[priority or "max_drawdown"])
        for column, (name, option) in zip(st.columns(len(options)), options.items()):
            value = option["priority_value"] if priority else max(window["max_drawdown"] for window in option["windows"].values())
            column.metric(name, f"{value:.2%}", border=True)
            if limit_status := _CAP_RESULT.get(option["max_drawdown_test"]):
                column.caption(limit_status)


def _render_decision(report: dict) -> None:
    if not report["options"]:
        return
    _render_key_figures(report)
    _render_chart(report)
    if report["requirements"]["esg"]["status"] == "unassessed":
        st.caption("The verified historical figures cover financial performance. ESG eligibility remains unknown.")


def _render_evidence(report: dict) -> None:
    verification = report["verification"]
    if not verification:
        st.info("A verification record is unavailable.")
        return
    st.caption("CAD adjusted closes on aligned dates. Each allocation is bought at the start of a window and held through its end.")
    st.table([
        {
            "Window": window_id,
            "First date": window["start"],
            "Last date": window["end"],
            "Observations": window["observations"],
        }
        for window_id, window in verification["windows"].items()
    ])
    if sources := verification.get("sources"):
        with st.expander("Market data sources"):
            st.table([
                {"Source": row["source"], "Data": row["file"], "Retrieved": row["retrieved_on"]}
                for row in sources
            ])
    with st.expander("Exact historical values and confirmed allocations"):
        for name, option in report["options"].items():
            st.write(name)
            st.table([
                {"Asset": ticker, "Starting weight": f"{weight:.2%}"} for ticker, weight in option["weights"].items()
            ])
            st.table([
                {
                    "Window": window_id,
                    "Terminal return": f"{window['terminal_return']:.4%}",
                    "Terminal loss": f"{window['terminal_loss']:.4%}",
                    "Maximum drawdown": f"{window['max_drawdown']:.4%}",
                }
                for window_id, window in option["windows"].items()
            ])
    with st.expander("Source record and independent review"):
        st.json(verification, expanded=False)
    st.caption("Findings apply to the tested historical windows. The replay excludes transaction costs and taxes.")


def _render_proxy_basis(context: dict) -> None:
    substitutions = context["proxy_substitutions"]
    st.table([
        {"Requested asset": ticker, "Requested weight": f"{weight:.2%}", "Historical series used": substitutions.get(ticker, ticker)}
        for ticker, weight in context["requested_weights"].items()
    ])


def _render_activity(record: dict) -> None:
    route = record["task_selection"]
    single = route["confirmed_task"] == "analyze_allocation"
    task = "allocation replay" if single else "comparison"
    if route["mode"] == "direct":
        st.caption(f"The investor selected and confirmed the {task} directly.")
    elif route["mode"] == "request_text":
        st.caption(f"The assistant read the {task} inputs from the written request and the investor confirmed them.")
    else:
        successful_calls = sum(
            event.get("event") == "bedrock" and event.get("status") == "success" for event in route["trace"]
        )
        st.caption(f"The investor confirmed the {task}. Bedrock routing returned {successful_calls} successful response(s).")
        with st.expander("Task selection trace"):
            st.json(route, expanded=False)
    if record["verification"]:
        st.markdown("**Replay and review**" if single else "**Comparison and review**")
        st.write("Python replayed the confirmed weights and independently reproduced their historical metrics.")
    else:
        st.info(f"The verification step returned no publishable {task}.")


def render_allocation_result(
    report: dict,
    profile: InvestorProfile,
    *,
    intent: dict | None = None,
    request_sources: Mapping[str, str] | None = None,
    replay_context: Mapping[str, object] | None = None,
) -> None:
    """Render and download the same checked result with the confirmed profile and bounded route trace."""
    sources = {field: excerpt for field, excerpt in (request_sources or {}).items()
               if field in _REQUEST_LABELS and isinstance(excerpt, str) and excerpt.strip()}
    published = publish_allocation_comparison(report, replay_context=replay_context)
    single = published.get("kind") == "single_allocation"
    proxy = published.get("replay_context")
    profile_record = profile.report()
    if single:
        profile_record.update(priority=None, explanation="The historical replay uses the confirmed starting weights.")
    record = {
        **published,
        "investor_profile": profile_record,
        "task_selection": _routing_record(intent, from_request=bool(sources), single=single),
        "input_provenance": {field: "request_text" for field in sources},
    }
    title, color = (_REPLAY_STATUS if single else _STATUS)[record["status"]]
    if proxy:
        title = "Verified illustrative replay" if record["status"] == "verified" else "Limited illustrative replay"
    with st.container(key="allocation-results"):
        with st.container(border=True, key="audit-summary-allocation"):
            st.title("Allocation replay" if single else "Asset comparison", anchor=False)
            st.badge(title, color=color)
            if finding := _finding_message(record):
                st.write(finding)
            if proxy:
                st.warning("The figures describe the substitute allocation. Fund costs and tracking differences can change the original allocation's performance.")
            if record.get("reason"):
                st.warning(record["reason"])
            if record["priority"]:
                st.caption(profile_record["explanation"])

        decision, evidence, activity = st.tabs(("Decision", "Evidence", "Agent activity"))
        with decision:
            _render_decision(record)
        with evidence:
            if proxy:
                with st.expander("Approved substitutions", expanded=True):
                    _render_proxy_basis(proxy)
            if sources:
                with st.expander("Wording behind the confirmed inputs"):
                    for field, excerpt in sources.items():
                        st.caption(_REQUEST_LABELS[field])
                        st.text(excerpt)
            _render_evidence(record)
        with activity:
            _render_activity(record)
        st.download_button(
            "Download allocation record" if single else "Download comparison record",
            json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            file_name="allocation-replay.json" if single else "allocation-comparison.json", mime="application/json",
            key="download-allocation-comparison",
        )
