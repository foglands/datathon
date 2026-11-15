"""Present the independently verified allocation comparison in Streamlit."""

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
_CAP_RESULT = {"pass": "Meets the limit", "fail": "Breaches the limit", "not_requested": "No limit requested"}
_REQUEST_LABELS = {
    "first_asset": "First asset",
    "second_asset": "Second asset",
    "options": "Allocation weights",
    "objective": "Investment objective",
    "withdrawal_time": "Withdrawal horizon",
    "risk_tolerance": "Willingness to take risk",
    "priority": "Comparison priority",
    "max_drawdown": "Drawdown limit",
    "include_2023": "2023 stress window",
    "require_esg": "ESG requirement",
}
_ROUTING_STATES = {"ready", "proposed", "unsupported", "unavailable", "needs_input"}
_ROUTING_TASKS = {"trade_audit", "compare_allocations"}
_TRACE_FIELDS = {
    "event", "role", "model_id", "region", "tool_name", "status", "duration_ms", "operation", "request_id", "http_status",
    "retry_attempts", "input_tokens", "output_tokens", "total_tokens",
}
_USAGE_FIELDS = {"elapsed_ms", "http_attempts_started", "responses_observed", "reported_total_tokens", "limit_reached"}


def _routing_record(intent: dict | None, *, from_request: bool = False) -> dict:
    if not intent or intent.get("status") not in _ROUTING_STATES:
        mode = "request_text" if from_request else "direct"
        return {"confirmed_task": "compare_allocations", "mode": mode}
    return {
        "confirmed_task": "compare_allocations",
        "mode": "bedrock_attempt",
        "status": intent["status"],
        "suggested_task": intent["task"] if intent.get("task") in _ROUTING_TASKS else None,
        "trace": [{key: value for key, value in event.items() if key in _TRACE_FIELDS} for event in intent["trace"]],
        "usage": {key: value for key, value in intent["usage"].items() if key in _USAGE_FIELDS},
    }


def _finding_message(report: dict) -> str:
    finding = report["finding"]
    status, basis = finding["status"], finding["basis"]
    if basis == "all_breach_cap":
        return "Both options breach the confirmed drawdown limit in at least one selected window."
    if status == "unavailable":
        return "A relative finding is unavailable under the confirmed requirements."
    if status == "neutral":
        return "Both options are shown side by side across the tested historical windows."
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
        .mark_bar()
        .encode(
            x=alt.X("Replay:N", title="Historical window", sort=sorted({row["Replay"] for row in series})),
            xOffset=alt.XOffset("Option:N", sort=list(options)),
            y=alt.Y("Value:Q", title=label, axis=alt.Axis(format=".0%")),
            color=alt.Color(
                "Option:N", title=None, scale=alt.Scale(domain=list(options), range=["#156c65", "#45638a"]),
                legend=alt.Legend(orient="bottom"),
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
    st.altair_chart(chart.properties(height=250), width="stretch", key="allocation-performance-chart")


def _render_decision(report: dict) -> None:
    if not report["options"]:
        return
    priority = report["priority"]
    rows = []
    for name, option in report["options"].items():
        row = {"Option": name}
        if priority is None:
            for metric, label in _MEASURE_BASIS.items():
                extreme = min if metric == "terminal_return" else max
                row[label] = f"{extreme(window[metric] for window in option['windows'].values()):.2%}"
        else:
            row[_MEASURE_BASIS[priority]] = f"{option['priority_value']:.2%}"
        row["Drawdown limit"] = _CAP_RESULT[option["max_drawdown_test"]]
        rows.append(row)
    st.table(rows)
    _render_chart(report)
    if report["requirements"]["esg"]["status"] == "unassessed":
        st.caption("The verified historical figures cover financial performance. ESG eligibility remains unknown.")


def _render_evidence(report: dict) -> None:
    verification = report["verification"]
    if not verification:
        st.info("No verification record is available for this comparison.")
        return
    st.caption("CAD adjusted closes on aligned dates. Each option is bought at the start of a window and held through its end.")
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


def _render_activity(record: dict) -> None:
    route = record["task_selection"]
    if route["mode"] == "direct":
        st.caption("The investor selected and confirmed the comparison task directly.")
    elif route["mode"] == "request_text":
        st.caption("The assistant read the comparison inputs from the written request and the investor confirmed them.")
    else:
        successful_calls = sum(
            event.get("event") == "bedrock" and event.get("status") == "success" for event in route["trace"]
        )
        st.caption(f"The investor confirmed the comparison task. Bedrock routing returned {successful_calls} successful response(s).")
        with st.expander("Task selection trace"):
            st.json(route, expanded=False)
    if record["verification"]:
        st.markdown("**Comparison and review**")
        st.write("Python compared the confirmed allocations and independently reproduced their historical metrics.")
    else:
        st.info("The verification step returned no publishable comparison.")


def render_allocation_result(
    report: dict,
    profile: InvestorProfile,
    *,
    intent: dict | None = None,
    request_sources: Mapping[str, str] | None = None,
) -> None:
    """Render and download the same checked result with the confirmed profile and bounded route trace."""
    sources = {field: excerpt for field, excerpt in (request_sources or {}).items()
               if field in _REQUEST_LABELS and isinstance(excerpt, str) and excerpt.strip()}
    record = {
        **publish_allocation_comparison(report),
        "investor_profile": profile.report(),
        "task_selection": _routing_record(intent, from_request=bool(sources)),
        "input_provenance": {field: "request_text" for field in sources},
    }
    title, color = _STATUS[record["status"]]
    with st.container(border=True, key="audit-summary-allocation"):
        st.subheader("Comparison outcome")
        st.badge(title, color=color)
        st.write(_finding_message(record))
        if record.get("reason"):
            st.warning(record["reason"])
        st.caption(profile.explanation)

    decision, evidence, activity = st.tabs(("Decision", "Evidence", "Agent activity"))
    with decision:
        _render_decision(record)
    with evidence:
        if sources:
            with st.expander("Wording behind the confirmed inputs"):
                for field, excerpt in sources.items():
                    st.caption(_REQUEST_LABELS[field])
                    st.text(excerpt)
        _render_evidence(record)
    with activity:
        _render_activity(record)
    st.download_button(
        "Download comparison record", json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        file_name="allocation-comparison.json", mime="application/json", key="download-allocation-comparison",
    )
