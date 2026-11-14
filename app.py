"""Streamlit entry point for the AlphaForge portfolio simulation."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4
from zipfile import BadZipFile

import streamlit as st

from datathon.agents import AgentRun, StrandsAgents
from datathon.audit_view import render_comparison, render_evidence, result_label
from datathon.data import load_market_data
from datathon.workflow import Case, examples, interpret_request, preset_profile, profile_policy, run_case


METRICS = {"terminal_loss": "Terminal loss", "max_drawdown": "Maximum drawdown"}
ROBERT, _ = examples("robert")
AMIRA, = examples("amira")
PRESETS = {
    "Robert · loss definition": (ROBERT, {}, "metric", "max_drawdown",
                                "Terminal loss → maximum drawdown"),
    "Robert · reserve floor": (ROBERT, {}, "reserve_floor_bps", 1800, "ZST.TO floor: 15% → 18%"),
    "Robert · purchase size": (ROBERT, {"allowed_sources": ["ZST.TO"], "allow_smaller": False},
                              "allow_smaller", True, "Exact size → smaller size allowed"),
    "Amira · issuer exposure": (AMIRA, {}, None, None, None),
}
ROBERT_REQUEST = next(case.user_request for case in examples("robert", stress=True) if case.ambiguous)


@st.cache_data(show_spinner=False)
def market_data():
    return load_market_data()


def show_policy(policy):
    st.markdown(
        f"**Buy {policy['target'] * 100:g} percentage points of NVDA** "
        f"using {policy['initial_source']} in the original proposal."
    )
    funding = ", ".join(policy["allowed_sources"])
    size = "smaller size allowed" if policy["allow_smaller"] else "exact size required"
    terms = [f"Funding: {funding}", size, f"ZST.TO floor: {policy['reserve_floor']:.2%}"]
    if policy["loss_limit"] is not None:
        terms.append(f"{METRICS[policy['metric']]} cap: {policy['loss_limit']:.2%}")
    if policy["issuer_cap"] is not None:
        terms.append(f"NVIDIA issuer cap: {policy['issuer_cap']:.2%}")
    if policy["prefer_reserve"] is True:
        terms.append("Preference: preserve ZST.TO")
    st.caption(" · ".join(terms))


def audit(case, profile, runtime):
    try:
        with st.spinner("Replaying the portfolios and checking the decision"):
            return asyncio.run(run_case(market_data(), case, runtime, confirmed_profile=profile))
    except (OSError, ValueError, BadZipFile) as exc:
        st.error(f"Market data could not be used. Check DATATHON_STARTER_PATH and the starter files. {exc}")
        return None


def show_report(report):
    render_comparison(report)
    render_evidence(report)
    st.download_button(
        "Download audit record",
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        file_name=f"{report['case']}.json", mime="application/json", key=f"download-{report['case']}",
    )


def new_case(case):
    return replace(case, id=f"{case.id}-{uuid4().hex[:12]}")


def preset_audit(mode):
    name = st.selectbox("Scenario", tuple(PRESETS))
    case, overrides, field, alternative, comparison_label = PRESETS[name]
    profile_data = {**preset_profile(case), **overrides}
    show_policy(profile_policy(profile_data))
    if field == "metric":
        st.caption("Terminal loss compares the start and end. Maximum drawdown measures the largest fall from a prior peak.")
    key = (mode, name)
    if st.session_state.get("preset_key") != key:
        st.session_state.preset_key = key
        st.session_state.pop("preset_result", None)
        st.session_state.pop("comparison_result", None)

    runtime = StrandsAgents() if mode == "Bedrock" else None
    if st.button("Confirm inputs and run audit", type="primary"):
        st.session_state.pop("comparison_result", None)
        st.session_state.preset_result = audit(
            new_case(case), AgentRun("ok", profile_data, ({"role": "profile", "event": "preset_inputs_selected"},)), runtime
        )

    report = st.session_state.get("preset_result")
    if report is None:
        return
    if field is not None and report["status"] not in {"invalid", "execution_error"} and report.get("audit"):
        st.subheader("Change one rule")
        st.caption(comparison_label)
        if st.button("Confirm this change and compare"):
            changed_data = {**profile_data, field: alternative}
            changed_case = replace(new_case(case), user_request=(
                f"{case.user_request}\nThe reviewer changed {field}. Use the confirmed review inputs."
            ))
            trace = ({"role": "profile", "event": "one_rule_changed", "field": field,
                      "previous": profile_data.get(field), "current": alternative},)
            st.session_state.comparison_result = audit(changed_case, AgentRun("ok", changed_data, trace), runtime)

    comparison = st.session_state.get("comparison_result")
    if comparison is not None:
        left, right = st.columns(2)
        left.markdown(f"**Original policy**  \n{result_label(report)}")
        right.markdown(f"**With the confirmed change**  \n{result_label(comparison)}")
        for panel, result in zip(st.tabs(("Original policy audit", "Changed policy audit")), (report, comparison)):
            with panel:
                if result.get("policy"):
                    show_policy(result["policy"])
                show_report(result)
    else:
        show_report(report)


def live_request():
    runtime = StrandsAgents()
    request = st.text_area("Fictional investment request", value=ROBERT_REQUEST, height=145)
    previous = st.session_state.get("request_draft")
    if previous and previous[0] != request:
        st.session_state.pop("request_draft", None)
        st.session_state.pop("request_results", None)
    if st.button("Interpret request with Bedrock", type="primary", disabled=not request.strip()):
        with st.spinner("Identifying the trade and the rules that need confirmation"):
            run_id = f"request-{uuid4().hex[:12]}"
            draft, policy, question = asyncio.run(interpret_request(request.strip(), runtime, run_id))
        st.session_state.request_draft = (request, run_id, draft, policy, question)
        st.session_state.request_results = {}
    saved = st.session_state.get("request_draft")
    if not saved or saved[0] != request:
        return
    _, run_id, draft, policy, question = saved
    if draft.status == "error":
        st.error(question)
        return
    if question:
        st.warning(question)
        if draft.data.get("clarification_field") != "loss_metric" or draft.data.get("limit_bps") is None:
            st.caption("Edit the request with the missing detail, then interpret it again.")
            return
        metric = st.radio("The cap measures", tuple(METRICS), format_func=METRICS.get, index=None, key=run_id)
        st.caption("Terminal loss compares the start and end. Maximum drawdown measures the largest fall from a prior peak.")
        if metric is None:
            return
        resolved = {**draft.data, "status": "ok", "metric": metric, "clarification_field": None}
        try:
            policy = profile_policy(resolved)
        except ValueError as exc:
            st.warning(str(exc))
            st.caption("Edit the request with the missing detail, then interpret it again.")
            return
        trace = (*draft.trace, {"role": "profile", "event": "loss_metric_selected", "metric": metric})
        draft = replace(draft, status="ok", data=resolved, trace=trace)

    st.subheader("Confirm the interpretation")
    show_policy(policy)
    selected = policy["metric"]
    if st.button("Confirm inputs and run audit", type="primary"):
        case = new_case(Case(run_id, request.strip(), "terminal_loss", None, 0))
        report = audit(case, draft, runtime)
        if report is not None:
            st.session_state.request_results[selected] = {**report, "user_request": request.strip()}
        else:
            st.session_state.request_results.pop(selected, None)
    reports = st.session_state.request_results
    if selected not in reports:
        return
    if len(reports) == 2:
        st.subheader("Compare the two confirmed rules")
        for col, metric in zip(st.columns(2), METRICS):
            col.markdown(f"**{METRICS[metric]}**  \n{result_label(reports[metric])}")
    show_report(reports[selected])


def main():
    st.set_page_config(page_title="AlphaForge · Portfolio Decision Audit", page_icon="◈", layout="wide")
    st.title("Portfolio Decision Audit")
    st.caption("AlphaForge AI · Fictional portfolio simulation · Historical results apply to the tested windows.")
    st.radio("Input", ("Reference case", "Write a request"), horizontal=True, key="audit_input")
    if st.session_state.audit_input != st.session_state.get("active_input"):
        st.session_state.active_input = st.session_state.audit_input
        for key in ("preset_key", "request_draft", "request_results"):
            st.session_state.pop(key, None)
    if st.session_state.audit_input == "Write a request":
        st.caption("Live profile interpretation and review use Strands on Amazon Bedrock.")
        live_request()
    else:
        mode = st.radio("Execution", ("Offline", "Bedrock"), horizontal=True)
        st.caption({
            "Offline": "Official data and the independent Python audit. Role events are simulated locally.",
            "Bedrock": "Confirmed reference inputs, then live Strands and Amazon Bedrock tool calls.",
        }[mode])
        preset_audit(mode)


if __name__ == "__main__":
    main()
