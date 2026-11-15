"""Results workspace for a published AlphaForge audit."""

import json

import altair as alt
import streamlit as st

from .audit_view import released_funding_example, render_agent_activity, render_comparison, render_evidence
from .metric_records import metric_id, resolve_metric


_RELEASE = {
    "released": ("Released", "green"),
    "limited": ("Limited release", "orange"),
    "blocked": ("Withheld", "red"),
}
_METRICS = {"terminal_loss": "Terminal loss", "max_drawdown": "Maximum drawdown", "terminal_return": "End-of-window return"}
_PORTFOLIOS = {"baseline": "Starting", "proposal": "Proposed", "maximum": "Funding example"}
_SERIES_COLORS = ("#7d978d", "#165b46", "#476c8c")
_SECTION_LABELS = {
    "main_audit": "Main audit",
    "exposure_change": "Issuer exposure change",
    "sector_analysis": "Sector exposure",
}
_SECTION_STATES = {
    "verified": "Independently verified",
    "invalid": "Withheld after a failed verification check",
    "unavailable": "Awaiting evidence or verification",
    "not_requested": "Outside the requested scope",
}


def _render_outcome(report: dict) -> None:
    publication = report["publication"]
    release = publication["status"]
    label, color = _RELEASE[release]
    with st.container(border=True, key=f"audit-summary-{report['case']}"):
        st.subheader("Audit outcome")
        st.badge(label, color=color)
        explanation = report["explanation"]
        if release == "blocked":
            st.error(explanation)
        elif publication["independent_review_verified"]:
            st.write(explanation)
        else:
            st.warning(explanation)


def _render_key_figures(series: list[dict], metric: str, case: str) -> None:
    portfolios = list(dict.fromkeys(row["Portfolio"] for row in series))
    select_value = min if metric == "terminal_return" else max
    with st.container(key=f"audit-key-figures-{case}"):
        st.caption(f"Worst {_METRICS[metric].lower()} across the selected windows")
        for column, name in zip(st.columns(len(portfolios)), portfolios):
            value = select_value(row["Value"] for row in series if row["Portfolio"] == name)
            column.metric(name, f"{value:.2%}", border=True)


def _window_series(report: dict, metric: str) -> list[dict]:
    verified = report["audit"]["verified"]
    funding_example = released_funding_example(report)
    return [
        {"Portfolio": label, "Window": window, "Value": value}
        for leg, label in _PORTFOLIOS.items()
        if leg != "maximum" or funding_example is not None
        for window in verified.get(leg, {}).get("windows", {})
        if (value := resolve_metric(report, metric_id("audit", "verified", leg, "windows", window, metric))) is not None
    ]


def _render_windows(report: dict, preferred_metric: str | None = None) -> None:
    policy_metric = report.get("policy", {}).get("metric")
    default = preferred_metric or policy_metric
    if default not in _METRICS:
        default = "terminal_loss"
    measures = tuple(_METRICS)
    metric = st.radio(
        "Historical measure", measures, index=measures.index(default), format_func=_METRICS.__getitem__,
        horizontal=True, key=f"audit-window-metric-{report['case']}",
    )
    series = _window_series(report, metric)
    if not series:
        return
    _render_key_figures(series, metric, report["case"])
    measure = _METRICS[metric]
    windows = list(dict.fromkeys(row["Window"] for row in series))
    observed = {row["Portfolio"] for row in series}
    palette = {label: color for label, color in zip(_PORTFOLIOS.values(), _SERIES_COLORS) if label in observed}
    chart = (
        alt.Chart(alt.Data(values=series))
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Window:N", sort=windows, axis=alt.Axis(title=None, labelAngle=0)),
            xOffset=alt.XOffset("Portfolio:N", sort=list(palette)),
            y=alt.Y("Value:Q", title=measure, axis=alt.Axis(format=".0%")),
            color=alt.Color(
                "Portfolio:N", title=None,
                scale=alt.Scale(domain=list(palette), range=list(palette.values())),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["Window:N", "Portfolio:N", alt.Tooltip("Value:Q", title=measure, format=".2%")],
        )
    )
    limit = resolve_metric(report, metric_id("policy", "loss_limit"))
    if policy_metric == metric and limit is not None:
        limit_line = (
            alt.Chart(alt.Data(values=[{"Limit": limit}]))
            .mark_rule(color="#935016", strokeDash=[5, 4], strokeWidth=2)
            .encode(
                y=alt.Y("Limit:Q", title=measure, axis=alt.Axis(format=".0%")),
                tooltip=alt.Tooltip("Limit:Q", title="Confirmed limit", format=".2%"),
            )
        )
        chart = chart + limit_line
        st.caption(f"Dashed line · Confirmed {measure.lower()} limit {limit:.2%}.")
    chart = (
        chart.properties(height=218)
        .configure_view(stroke=None)
        .configure_axis(domain=False, tickSize=0, gridColor="#e3ede7", labelColor="#51615a", titleColor="#35453e")
    )
    st.altair_chart(chart, width="stretch", key=f"audit-window-chart-{report['case']}")


def _render_review_record(report: dict) -> None:
    publication = report["publication"]
    with st.expander("Independent review"):
        st.table([
            {"Section": label, "Verification": _SECTION_STATES[state]}
            for section, label in _SECTION_LABELS.items()
            if (state := publication["section_verification"].get(section)) in _SECTION_STATES
        ])
        if review_id := publication.get("review_id"):
            st.caption("Review ID")
            st.code(review_id, language=None)


def render_audit_workspace(report: dict, *, preferred_metric: str | None = None) -> None:
    """Render and export the same verified public projection."""
    with st.container(key=f"audit-results-{report['case']}"):
        _render_outcome(report)
        decision, evidence, activity = st.tabs(("Decision", "Evidence", "Agent activity"))
        with decision:
            if report["publication"]["independent_review_verified"]:
                _render_windows(report, preferred_metric)
                with st.expander("Portfolio details and rule checks"):
                    render_comparison(report, show_explanation=False)
        with evidence:
            _render_review_record(report)
            render_evidence(report, include_activity=False)
        with activity:
            render_agent_activity(report)
            if report.get("runtime_usage"):
                with st.expander("Runtime and model usage"):
                    st.json(report["runtime_usage"], expanded=False)
        st.download_button(
            "Download audit record",
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            file_name=f"{report['case']}.json", mime="application/json", key=f"download-{report['case']}",
        )
