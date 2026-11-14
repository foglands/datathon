"""Streamlit entry point for the AlphaForge portfolio simulation."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4
from zipfile import BadZipFile

import streamlit as st

from datathon.agents import PROFILE_FIELDS, AgentRun, StrandsAgents
from datathon.audit_view import render_comparison, render_evidence, result_label
from datathon.counterfactual import counterfactual_options, run_counterfactual
from datathon.data import load_market_data
from datathon.workflow import Case, examples, interpret_request, preset_profile, profile_policy, run_case


METRICS = {"terminal_loss": "Terminal loss", "max_drawdown": "Maximum drawdown"}
FUNDING = ("QQQ", "ZST.TO")
BLOCKING_PROFILE_FIELDS = {"unsupported_scope", "unsupported_constraint", "multiple_loss_limits", "conflict"}
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


def show_counterfactual(case, report, runtime):
    if not (options := counterfactual_options(report)):
        return
    st.subheader("What could change this decision?")
    st.caption("Compare one hypothetical change. The original audited rules stay in effect.")
    choices = {option.id: option.label for option in options}
    default = "Review Agent selects a check" if runtime is not None else "Choose a check using fixed rules (offline)"
    choices = {None: default, **choices}
    key = f"challenge-{report['case']}"
    selected = st.selectbox("Check to run", list(choices), format_func=choices.__getitem__, key=f"{key}-choice")
    hint = ""
    if runtime is not None and selected is None:
        hint = st.text_input("What would you like to check?", max_chars=500, key=f"{key}-hint")
    if st.button("Check once", key=f"{key}-run"):
        with st.spinner("Checking the assumption against the independent audit"):
            check = asyncio.run(run_counterfactual(
                market_data(), case, report, option_id=selected, selector_runtime=runtime, replay_runtime=runtime,
                challenge_hint=hint.strip() or None,
            ))
        st.session_state.active_challenge = (key, selected, hint, check)

    saved = st.session_state.get("active_challenge")
    if not saved or saved[:3] != (key, selected, hint):
        return
    _, _, _, check = saved
    if check["status"] == "invalid":
        st.warning(check["statement"])
        return
    st.write(check["statement"])
    if option := check["option"]:
        st.caption(option["label"])
    if comparison := check["replay"]:
        left, right = st.columns(2)
        left.markdown(f"**Original audited rules**  \n{result_label(report)}")
        right.markdown(f"**One hypothetical change**  \n{result_label(comparison)}")
        with st.expander("Independent rerun evidence"):
            render_comparison(comparison)
            st.json(check["comparison"]["differences"], expanded=False)
    if action := check["action"]:
        st.write("Disclosures to verify: " + ", ".join(action["holdings"]))
        qqq = action.get("thresholds", {}).get("qqq_only", {})
        if qqq.get("status") == "unresolved" and qqq.get("maximum_combined_additional_exposure") is not None:
            headroom = qqq["maximum_combined_additional_exposure"] * 100
            covered = qqq["known_lower"] * 100
            st.write(
                f"The QQQ-funded example has {covered:.2f}% documented NVIDIA exposure. "
                f"To meet the issuer cap, the listed funds' combined undisclosed contribution must be "
                f"at most {headroom:.5f} percentage points."
            )
    with st.expander("Check selection and verification record"):
        if check["selection_mode"] == "agent":
            calls = sum(event.get("event") == "bedrock" and event.get("status") == "success" for event in check["trace"])
            st.caption(f"{calls} successful Bedrock response(s) during selection.")
        st.json({"selection": check["trace"], "changed_fields": check["changed_fields"],
                 "verification": check["verified"], "evidence_request": check["action"]}, expanded=False)
    st.download_button("Download this check", json.dumps(check, indent=2, allow_nan=False) + "\n",
                       file_name=f"{report['case']}-challenge.json", mime="application/json", key=f"{key}-download")


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
    show_counterfactual(case, report, runtime)


def edit_profile(draft, run_id):
    """Collect a reviewable draft. Editing the draft never runs an audit."""
    initial = draft.data

    def amount(field, label, unit):
        basis_points = initial.get(field)
        value = st.number_input(
            label, min_value=0.0, max_value=100.0, value=basis_points / 100 if basis_points is not None else None,
            step=.01, format="%.2f", key=f"{run_id}-{field}", placeholder="Unstated", help=unit,
        )
        return round(value * 100) if value is not None else None

    def option(field, label, values, *, format_func=str):
        value = initial.get(field)
        index = values.index(value) if value in values else None
        return st.selectbox(label, values, index=index, format_func=format_func, key=f"{run_id}-{field}")

    st.subheader("Review and edit the interpreted inputs")
    st.caption("Check the values against your fictional request. Blank reserve and issuer limits are not applied.")
    edited = {
        "target_bps": amount("target_bps", "NVDA purchase size (percentage points)", "10 percentage points adds 10% of the portfolio to NVDA."),
        "initial_source": option("initial_source", "Funding for the original proposal", FUNDING),
        "allowed_sources": st.multiselect("Funding allowed for alternatives", FUNDING,
                                          default=initial.get("allowed_sources", []), key=f"{run_id}-allowed_sources"),
        "allow_smaller": option("allow_smaller", "Allow a smaller purchase", (True, False),
                                format_func=lambda value: "Yes" if value else "No"),
    }
    loss_cap = st.checkbox(
        "Apply a historical loss cap",
        value=initial.get("limit_bps") is not None or initial.get("metric") is not None
              or initial.get("clarification_field") in {"loss_metric", "loss_limit"},
        key=f"{run_id}-apply_loss_cap",
    )
    metric, limit = None, None
    if loss_cap:
        initial_metric = initial.get("metric")
        metric = st.radio("The cap measures", tuple(METRICS), format_func=METRICS.get,
                          index=tuple(METRICS).index(initial_metric) if initial_metric in METRICS else None,
                          key=f"{run_id}-metric")
        limit = amount("limit_bps", "Historical loss cap (%)", "Applies to both required historical windows.")
        st.caption("Terminal loss compares the start and end. Maximum drawdown measures the largest fall from a prior peak.")
    edited.update({
        "metric": metric,
        "limit_bps": limit,
        "reserve_floor_bps": amount("reserve_floor_bps", "Minimum ZST.TO weight (%)", "This floor is a binding rule."),
        "issuer_cap_bps": amount("issuer_cap_bps", "Maximum total NVIDIA issuer exposure (%)", "Includes direct and disclosed indirect common equity."),
        "prefer_reserve": option("prefer_reserve", "Preference to preserve ZST.TO", (None, True, False),
                                 format_func={None: "Unstated", True: "Prefer to preserve", False: "No preference"}.get),
    })
    edited["allowed_sources"] = sorted(edited["allowed_sources"])
    extracted = {key: initial.get(key) for key in PROFILE_FIELDS}
    extracted["allowed_sources"] = sorted(extracted["allowed_sources"] or [])
    changes = {key: {"from": extracted[key], "to": value} for key, value in edited.items() if value != extracted[key]}
    excerpts = initial.get("source_excerpts", {})
    if excerpts or changes:
        with st.expander("Source excerpts and manual edits"):
            if changes:
                st.caption("Edited fields use the values you entered above.")
            rows = [
                {"Field": label, "Basis": "Manual edit" if field in changes else excerpts.get(field, "No excerpt provided")}
                for field, label in (
                    ("target_bps", "Purchase size"), ("initial_source", "Original funding"),
                    ("allowed_sources", "Allowed funding"), ("allow_smaller", "Smaller purchase allowed"),
                    ("metric", "Loss definition"), ("limit_bps", "Loss cap"),
                    ("reserve_floor_bps", "Reserve floor"), ("issuer_cap_bps", "Issuer cap"),
                    ("prefer_reserve", "Reserve preference"),
                )
            ]
            st.table(rows)
    return edited, changes, loss_cap


def live_request():
    runtime = StrandsAgents()
    request = st.text_area("Fictional investment request", value=ROBERT_REQUEST, height=145)
    previous = st.session_state.get("request_draft")
    if previous and previous[0] != request:
        for key in ("request_draft", "request_results", "request_confirmed"):
            st.session_state.pop(key, None)
    if st.button("Interpret request with Bedrock", type="primary", disabled=not request.strip()):
        with st.spinner("Identifying the trade and rules that need confirmation"):
            run_id = f"request-{uuid4().hex[:12]}"
            draft, _, question = asyncio.run(interpret_request(request.strip(), runtime, run_id))
        st.session_state.request_draft = (request, run_id, draft, question)
        st.session_state.request_results = {}
        st.session_state.pop("request_confirmed", None)
    saved = st.session_state.get("request_draft")
    if not saved:
        return
    _, run_id, draft, question = saved
    if draft.status == "error":
        st.error(question)
        return
    if question:
        st.warning(question)
        if draft.data.get("clarification_field") in BLOCKING_PROFILE_FIELDS:
            if excerpt := draft.data.get("unsupported_excerpt"):
                st.text(excerpt)
            st.caption("Revise the original request before interpreting it again.")
            return

    edited, changes, loss_cap = edit_profile(draft, run_id)
    if loss_cap and (edited["metric"] is None or edited["limit_bps"] is None):
        st.session_state.pop("request_confirmed", None)
        st.caption("Select a loss definition and enter the cap before confirming.")
        return
    body = {**edited, "status": "ok", "summary": "User confirmed the simulated audit inputs.", "evidence_ids": []}
    try:
        policy = profile_policy(body)
    except ValueError as exc:
        st.session_state.pop("request_confirmed", None)
        if str(exc) != question:
            st.caption(str(exc))
        return
    key = tuple((field, tuple(value) if isinstance(value, list) else value) for field, value in edited.items())
    if st.session_state.get("request_confirmed") != key:
        st.session_state.pop("request_confirmed", None)

    st.subheader("Confirm the interpretation")
    show_policy(policy)
    if st.button("Confirm inputs and run audit", type="primary"):
        trace = draft.trace
        if changes:
            trace = (*trace, {"role": "profile", "event": "draft_edited", "changes": changes})
        confirmed = replace(draft, status="ok", data=body, trace=trace)
        case = new_case(Case(run_id, "User-confirmed fictional request.", "terminal_loss", None, 0))
        report = audit(case, confirmed, runtime)
        if report is not None:
            st.session_state.request_results[key] = report
            st.session_state.request_confirmed = key
        else:
            st.session_state.request_results.pop(key, None)
            st.session_state.pop("request_confirmed", None)
    if st.session_state.get("request_confirmed") != key:
        return

    reports = st.session_state.request_results
    if policy["loss_limit"] is not None:
        comparison_keys = {metric: tuple((field, metric if field == "metric" else value) for field, value in key)
                           for metric in METRICS}
        if all(variant in reports for variant in comparison_keys.values()):
            st.subheader("Compare the two confirmed rules")
            for column, (metric, variant) in zip(st.columns(2), comparison_keys.items()):
                column.markdown(f"**{METRICS[metric]}**  \n{result_label(reports[variant])}")
    show_report(reports[key])
    active = Case(reports[key]["case"], "User-confirmed fictional request.", "terminal_loss", None, 0)
    show_counterfactual(active, reports[key], runtime)


def main():
    st.set_page_config(page_title="AlphaForge · Portfolio Decision Audit", page_icon="◈", layout="wide")
    st.title("Portfolio Decision Audit")
    st.caption("AlphaForge AI · Fictional portfolio simulation · Historical results apply to the tested windows.")
    st.radio("Input", ("Reference case", "Write a request"), horizontal=True, key="audit_input")
    if st.session_state.audit_input != st.session_state.get("active_input"):
        st.session_state.active_input = st.session_state.audit_input
        for key in ("preset_key", "request_draft", "request_results", "request_confirmed"):
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
