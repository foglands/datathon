"""Streamlit entry point for the AlphaForge portfolio simulation."""

import json
from dataclasses import replace
from uuid import uuid4
from zipfile import BadZipFile

import streamlit as st

from datathon.agents import PROFILE_FIELDS, PROFILE_MODEL, AgentRun, StrandsAgents
from datathon.audit_view import render_comparison, render_evidence, result_label
from datathon.counterfactual import counterfactual_options, issuer_disclosure_options, run_counterfactual
from datathon.data import load_market_data
from datathon.finance import BASE_WEIGHTS
from datathon.publication import publish_check, publish_report
from datathon.runtime_budget import (
    CHALLENGE_LIMITS, PROFILE_LIMITS, RuntimeBudgetExceeded, bound_audit, run_bounded, run_sync_action,
)
from datathon.scope import EXTRA_WINDOW, OBJECTIVES, WITHDRAWAL_TIMES, ReplayScope
from datathon.workflow import Case, examples, interpret_request, preset_profile, profile_policy, run_case


METRICS = {"terminal_loss": "Terminal loss", "max_drawdown": "Maximum drawdown"}
FUNDING = ("QQQ", "ZST.TO")
BLOCKING_PROFILE_FIELDS = {"unsupported_scope", "multiple_loss_limits", "conflict"}
PROFILE_INPUT = ("Enter inputs directly", "Interpret text with Bedrock")
MANUAL_SCOPE = "These inputs include every binding rule for this simulation."
SEARCH_ALTERNATIVES = "Search alternative funding"
CONFIRM_SEARCH = "Confirm and search alternative funding"
INCLUDE_SECTOR = "Include equity sector analysis"
LIMITED_SCOPE = "Audit only supported rules and mark the other requirements as not assessed."
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


def show_policy(policy, *, search_alternatives=True):
    st.markdown(
        f"**Buy {policy['target'] * 100:g} percentage points of NVDA** "
        f"using {policy['initial_source']} in the original proposal."
    )
    terms = ["Original proposal only"]
    if search_alternatives:
        funding = ", ".join(policy["allowed_sources"])
        size = {True: "smaller size allowed", False: "exact size required", None: "test the requested size first"}
        terms = [f"Alternative funding: {funding}", size[policy["allow_smaller"]]]
    terms.append(f"ZST.TO floor: {policy['reserve_floor']:.2%}")
    if policy["loss_limit"] is not None:
        terms.append(f"{METRICS[policy['metric']]} cap: {policy['loss_limit']:.2%}")
    if policy["issuer_cap"] is not None:
        terms.append(f"NVIDIA issuer cap: {policy['issuer_cap']:.2%}")
    if search_alternatives and policy["prefer_reserve"] is True:
        terms.append("Preference: preserve ZST.TO")
    st.caption(" · ".join(terms))


def audit(case, profile, runtime):
    async def evaluate():
        return await run_case(market_data(), case, runtime, confirmed_profile=profile)

    try:
        with st.spinner("Replaying the portfolios and checking the decision"):
            return run_sync_action(bound_audit(evaluate(), case.id, live=runtime is not None))
    except (OSError, ValueError, BadZipFile) as exc:
        st.error(f"Market data could not be used. Check DATATHON_STARTER_PATH and the starter files. {exc}")
        return None


def show_report(report):
    report = publish_report(report)
    render_comparison(report)
    render_evidence(report)
    if report.get("runtime_usage"):
        with st.expander("Runtime and model usage"):
            st.json(report["runtime_usage"], expanded=False)
    st.download_button(
        "Download audit record",
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        file_name=f"{report['case']}.json", mime="application/json", key=f"download-{report['case']}",
    )


def show_counterfactual(case, report, runtime):
    if not (options := counterfactual_options(report)):
        return
    st.subheader("What could change this decision?")
    st.caption("Test one rule or recheck a missing disclosure. The original audit stays available.")
    choices = {option.id: option.label for option in options}
    default = "Review Agent selects a check" if runtime is not None else "Choose a check using fixed rules (offline)"
    choices = {None: default, **choices}
    key = f"challenge-{report['case']}"
    selected = st.selectbox("Check to run", list(choices), format_func=choices.__getitem__, key=f"{key}-choice")
    hint = ""
    threshold = None
    reviewed_ids = ()
    option = next((item for item in options if item.id == selected), None)
    if runtime is not None and selected is None:
        hint = st.text_input("What would you like to check?", max_chars=500, key=f"{key}-hint")
    if option and option.value_unit == "basis_points":
        value = st.number_input(
            "Hypothetical minimum ZST.TO weight (%)",
            min_value=option.minimum_value / 100,
            max_value=option.maximum_value / 100,
            value=option.preset_value / 100,
            step=.01, format="%.2f", key=f"{key}-reserve",
        )
        threshold = round(value * 100)
    elif option and option.value_unit == "days":
        threshold = st.number_input(
            "Hypothetical maximum holdings age (days)",
            min_value=option.minimum_value, max_value=option.maximum_value, value=option.preset_value,
            step=1, key=f"{key}-age",
        )
    if selected == "request_issuer_evidence":
        try:
            available = issuer_disclosure_options(report)
        except ValueError:
            available = {}
            st.warning("The reviewed issuer catalog is unavailable.")
        if available:
            reviewed_ids = tuple(st.multiselect(
                "Reviewed holdings disclosures to apply", list(available),
                format_func=lambda item: f"{available[item].ticker} · {available[item].as_of} · {available[item].source}",
                key=f"{key}-disclosures",
            ))
            st.caption("The re-audit uses the same policy and market data.")
        else:
            st.caption("No reviewed disclosure qualifies for the unresolved holdings at this audit date.")
    if st.button("Re-audit reviewed disclosures" if reviewed_ids else "Check once", key=f"{key}-run"):
        with st.spinner("Checking the assumption against the independent audit"):
            try:
                check, usage = run_sync_action(run_bounded(run_counterfactual(
                    market_data(), case, report, option_id=selected, selector_runtime=runtime, replay_runtime=runtime,
                    challenge_hint=hint.strip() or None, challenge_value=threshold,
                    issuer_disclosure_ids=reviewed_ids or None,
                ), CHALLENGE_LIMITS))
            except RuntimeBudgetExceeded:
                st.session_state.pop("active_challenge", None)
                st.warning("The check reached its time budget before it could verify a comparison.")
                return
            check["runtime_usage"] = usage
        st.session_state.active_challenge = (key, selected, hint, threshold, reviewed_ids, check)

    saved = st.session_state.get("active_challenge")
    if not saved or saved[:5] != (key, selected, hint, threshold, reviewed_ids):
        return
    check = publish_check(saved[-1])
    if check["status"] == "invalid":
        st.warning(check["statement"])
        return
    st.write(check["statement"])
    if option := check["option"]:
        st.caption(option["label"])
    if comparison := check["replay"]:
        left, right = st.columns(2)
        left.markdown(f"**Original audit**  \n{result_label(publish_report(report))}")
        label = "Independent re-audit with reviewed disclosures" if reviewed_ids else "One hypothetical change"
        right.markdown(f"**{label}**  \n{result_label(comparison)}")
        with st.expander("Independent rerun evidence"):
            render_comparison(comparison)
            st.json(check["comparison"]["differences"], expanded=False)
    if action := check["action"]:
        for row in action.get("reviewed_disclosures", ()):
            st.markdown(f"**{row['ticker']}** · observed {row['as_of']} · "
                        f"published {row['published_on']} · [Source]({row['url']})")
            st.caption(f"{row['source_locator']} · {row['weight']:.4%} issuer weight")
        remaining = action.get("remaining_holding_gaps", action["holdings"])
        if remaining:
            st.write("Disclosures to verify: " + ", ".join(remaining))
        qqq = {} if reviewed_ids else action.get("thresholds", {}).get("qqq_only", {})
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
                  "verification": check["verified"], "issuer_evidence": check["action"],
                 "runtime_usage": check.get("runtime_usage")}, expanded=False)
    st.download_button("Download this check", json.dumps(check, indent=2, allow_nan=False) + "\n",
                       file_name=f"{report['case']}-challenge.json", mime="application/json", key=f"{key}-download")


def new_case(case):
    return replace(case, id=f"{case.id}-{uuid4().hex[:12]}")


def can_confirm_search(report):
    return (report.get("search_alternatives") is False and not report.get("unassessed_requirements")
            and publish_report(report)["publication"]["independent_review_verified"])


def preset_audit(mode):
    name = st.selectbox("Scenario", tuple(PRESETS))
    case, overrides, field, alternative, comparison_label = PRESETS[name]
    search = st.checkbox(
        SEARCH_ALTERNATIVES, key=f"preset_search_alternatives-{name}",
        help="Prepare the funding search settings. Confirm the search after reviewing the original trade.",
    )
    case = replace(case, search_alternatives=False)
    profile_data = {**preset_profile(case), **overrides}
    show_policy(profile_policy(profile_data, search_alternatives=search), search_alternatives=search)
    if field == "metric":
        st.caption("Terminal loss compares the start and end. Maximum drawdown measures the largest fall from a prior peak.")
    key = (mode, name, search)
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
    reviewed_search = report.get("search_alternatives", False)
    can_compare = field is not None and (field != "allow_smaller" or reviewed_search)
    if can_compare and report["status"] not in {"invalid", "execution_error"} and report.get("audit"):
        st.subheader("Change one rule")
        st.caption(comparison_label)
        if st.button("Confirm this change and compare"):
            changed_data = {**profile_data, field: alternative}
            changed_case = replace(new_case(case), search_alternatives=reviewed_search, user_request=(
                f"{case.user_request}\nThe reviewer changed {field}. Use the confirmed review inputs."
            ))
            trace = ({"role": "profile", "event": "one_rule_changed", "field": field,
                      "previous": profile_data.get(field), "current": alternative},)
            st.session_state.comparison_result = audit(changed_case, AgentRun("ok", changed_data, trace), runtime)

    comparison = st.session_state.get("comparison_result")
    if comparison is not None:
        left, right = st.columns(2)
        left.markdown(f"**Original policy**  \n{result_label(publish_report(report))}")
        right.markdown(f"**With the confirmed change**  \n{result_label(publish_report(comparison))}")
        for panel, result in zip(st.tabs(("Original policy audit", "Changed policy audit")), (report, comparison)):
            with panel:
                if result.get("policy"):
                    show_policy(result["policy"], search_alternatives=reviewed_search)
                show_report(result)
    else:
        show_report(report)
    if search and can_confirm_search(report):
        if st.button(CONFIRM_SEARCH, key="preset-confirm-alternatives"):
            search_case = replace(new_case(case), search_alternatives=True)
            confirmed = AgentRun("ok", profile_data, ({"role": "profile", "event": "alternative_search_authorized"},))
            if updated := audit(search_case, confirmed, runtime):
                st.session_state.preset_result = updated
                st.session_state.pop("comparison_result", None)
                st.rerun()
    show_counterfactual(replace(case, search_alternatives=reviewed_search), report, runtime)


def edit_profile(draft, run_id, *, manual=False, search_alternatives):
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

    st.subheader("Enter simulation inputs" if manual else "Review and edit the interpreted inputs")
    if not manual:
        st.caption("Check the values against your fictional request.")
    st.caption("Blank reserve and issuer limits are not applied.")
    edited = {
        "target_bps": amount("target_bps", "NVDA purchase size (percentage points)", "10 percentage points adds 10% of the portfolio to NVDA."),
        "initial_source": option("initial_source", "Funding for the original proposal", FUNDING),
        "allowed_sources": initial.get("allowed_sources", []),
        "allow_smaller": None,
        "prefer_reserve": initial.get("prefer_reserve"),
    }
    if search_alternatives:
        edited["allowed_sources"] = st.multiselect(
            "Funding allowed for alternatives", FUNDING,
            default=initial.get("allowed_sources") or ([edited["initial_source"]] if edited["initial_source"] else []),
            key=f"{run_id}-allowed_sources",
        )
        if type(initial.get("allow_smaller")) is bool:
            edited["allow_smaller"] = option("allow_smaller", "Allow a smaller purchase", (True, False),
                                             format_func=lambda value: "Yes" if value else "No")
        edited["prefer_reserve"] = option(
            "prefer_reserve", "Preference to preserve ZST.TO", (None, True, False),
            format_func={None: "Unstated", True: "Prefer to preserve", False: "No preference"}.get,
        )
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
        limit = amount("limit_bps", "Historical loss cap (%)", "Applies to every included historical window.")
        st.caption("Terminal loss compares the start and end. Maximum drawdown measures the largest fall from a prior peak.")
    edited.update({
        "metric": metric,
        "limit_bps": limit,
        "reserve_floor_bps": amount("reserve_floor_bps", "Minimum ZST.TO weight (%)", "This floor is a binding rule."),
        "issuer_cap_bps": amount("issuer_cap_bps", "Maximum total NVIDIA issuer exposure (%)", "Includes direct and disclosed indirect common equity."),
    })
    edited["allowed_sources"] = sorted(edited["allowed_sources"] or [])
    extracted = {key: initial.get(key) for key in PROFILE_FIELDS}
    extracted["allowed_sources"] = sorted(extracted["allowed_sources"] or [])
    changes = {key: {"from": extracted[key], "to": value} for key, value in edited.items() if value != extracted[key]}
    excerpts = initial.get("source_excerpts", {})
    if not manual and (excerpts or changes):
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
                if search_alternatives or field not in {"allowed_sources", "allow_smaller", "prefer_reserve"}
            ]
            st.table(rows)
    return edited, changes, loss_cap


def edit_scope(run_id):
    with st.expander("Starting portfolio and planning context"):
        custom = st.checkbox("Use custom starting weights", key=f"{run_id}-custom-weights")
        weights = None
        if custom:
            weights = {
                ticker: round(st.number_input(
                    f"{ticker} starting weight (%)", min_value=0.0, max_value=100.0, value=value * 100,
                    step=.01, format="%.2f", key=f"{run_id}-weight-{ticker}",
                ) * 100)
                for ticker, value in BASE_WEIGHTS.items()
            }
            st.caption(f"Total starting weight {sum(weights.values()) / 100:.2f}%")
        include_2023 = st.checkbox(
            "Include the fixed 2023 replay",
            help=f"{EXTRA_WINDOW.start} through {EXTRA_WINDOW.end}. The 2022 and 2025 replays are still included.",
            key=f"{run_id}-scope-2023",
        )
        objective = st.selectbox("Fictional investment objective", OBJECTIVES, index=None,
                                 placeholder="Optional", key=f"{run_id}-objective")
        withdrawal = st.selectbox("Timing of next meaningful withdrawal", WITHDRAWAL_TIMES, index=None,
                                  placeholder="Optional", key=f"{run_id}-withdrawal")
        if objective or withdrawal:
            st.caption("Set any spending reserve and historical loss limits explicitly in the rules below.")
    if custom or include_2023 or objective or withdrawal:
        return ReplayScope(weights, include_2023, objective, withdrawal)
    return None


def live_request():
    intake = st.radio("Profile input", PROFILE_INPUT, horizontal=True, key="request_intake")
    for key in ("request_draft", "request_results", "request_confirmed", "manual_draft_id"):
        if st.session_state.get("active_intake") != intake:
            st.session_state.pop(key, None)
    st.session_state.active_intake = intake
    manual = intake == PROFILE_INPUT[0]
    requested_search = st.checkbox(
        SEARCH_ALTERNATIVES, key="request_search_alternatives",
        help="Prepare the funding search settings. Confirm the search after reviewing the original trade.",
    )
    include_sector = st.checkbox(INCLUDE_SECTOR, key="request_include_sector")
    unassessed = []
    scope = None
    scope_error = None
    if manual:
        st.caption("Enter the supported rules for your fictional scenario. Direct entry skips model interpretation.")
        mode = st.radio("Audit execution", ("Bedrock", "Offline"), horizontal=True, key="manual_execution")
        if "manual_draft_id" not in st.session_state:
            st.session_state.manual_draft_id = f"manual-{uuid4().hex[:12]}"
            st.session_state.request_results = {}
        run_id = st.session_state.manual_draft_id
        draft = AgentRun("ok", {}, ({"role": "profile", "event": "manual_profile_entered"},))
        question = None
        runtime = StrandsAgents() if mode == "Bedrock" else None
        try:
            scope = edit_scope(run_id)
        except ValueError as exc:
            scope_error = str(exc)
    else:
        runtime = StrandsAgents()
        request = st.text_area("Fictional investment request", value=ROBERT_REQUEST, height=145)
        previous = st.session_state.get("request_draft")
        if previous and previous[:2] != (request, requested_search):
            for key in ("request_draft", "request_results", "request_confirmed"):
                st.session_state.pop(key, None)
        if st.button("Interpret request with Bedrock", type="primary", disabled=not request.strip()):
            with st.spinner("Identifying the trade and rules that need confirmation"):
                run_id = f"request-{uuid4().hex[:12]}"
                try:
                    (draft, _, question), usage = run_sync_action(run_bounded(
                        interpret_request(request.strip(), StrandsAgents(model_id=PROFILE_MODEL), run_id,
                                          search_alternatives=requested_search, defer_smaller_authorization=True),
                        PROFILE_LIMITS,
                    ))
                    draft = replace(draft, trace=(*draft.trace, {"role": "profile", "event": "runtime_usage", **usage}))
                except RuntimeBudgetExceeded:
                    for key in ("request_draft", "request_results", "request_confirmed"):
                        st.session_state.pop(key, None)
                    st.warning("Interpretation reached its time budget. You can enter the simulation inputs directly.")
                    return
            st.session_state.request_draft = (request, requested_search, run_id, draft, question)
            st.session_state.request_results = {}
            st.session_state.pop("request_confirmed", None)
        saved = st.session_state.get("request_draft")
        if not saved:
            return
        _, _, run_id, draft, question = saved
        if draft.status == "error":
            st.error(question)
            st.caption("Switch to Enter inputs directly to audit a complete set of supported rules without Bedrock intake.")
            return
        field = draft.data.get("clarification_field")
        if field in BLOCKING_PROFILE_FIELDS:
            if question:
                st.warning(question)
            if excerpt := draft.data.get("unsupported_excerpt"):
                st.text(excerpt)
            st.caption("Revise the original request before interpreting it again. Direct entry can audit supported rules you choose to confirm.")
            return
        if field == "unsupported_constraint" or draft.data.get("unassessed_requirements"):
            requirements = draft.data.get("unassessed_requirements") or [
                {"code": "other_binding", "excerpt": draft.data.get("unsupported_excerpt")}
            ]
            st.warning("Some binding requirements have not been assessed. A limited audit can only check the original proposal against supported rules.")
            for requirement in requirements:
                if excerpt := requirement.get("excerpt"):
                    st.text(excerpt)
            if not st.checkbox(LIMITED_SCOPE, key=f"{run_id}-limited-scope"):
                st.session_state.pop("request_confirmed", None)
                return
            unassessed = [{"code": requirement["code"]} for requirement in requirements]
        if question and field != "unsupported_constraint":
            st.warning(question)

    search_alternatives = requested_search and not unassessed
    edited, changes, loss_cap = edit_profile(
        draft, run_id, manual=manual, search_alternatives=search_alternatives,
    )
    if scope_error:
        st.session_state.pop("request_confirmed", None)
        st.warning(scope_error)
        return
    if loss_cap and (edited["metric"] is None or edited["limit_bps"] is None):
        st.session_state.pop("request_confirmed", None)
        st.caption("Select a loss definition and enter the cap before confirming.")
        return
    key = tuple((field, tuple(value) if isinstance(value, list) else value) for field, value in edited.items())
    key += (("search_alternatives", search_alternatives), ("include_sector", include_sector))
    if manual:
        key += (("execution", mode),)
    if scope:
        key += (("scope", (tuple(scope.baseline.items()), scope.include_2023, scope.objective, scope.withdrawal_time)),)
    basis = (run_id, key)
    scope_widget_key = f"{run_id}-complete-{key!r}"
    body = {**edited, "status": "ok", "summary": "User confirmed the simulated audit inputs.", "evidence_ids": []}
    if unassessed:
        body["unassessed_requirements"] = unassessed
    if search_alternatives and st.session_state.get("request_resize_choice") == basis:
        body["allow_smaller"] = True
        key = tuple((field, True if field == "allow_smaller" else value) for field, value in key)
    try:
        policy = profile_policy(
            body, baseline=scope.baseline if scope else BASE_WEIGHTS,
            search_alternatives=search_alternatives, defer_smaller_authorization=True,
        )
    except ValueError as exc:
        st.session_state.pop("request_confirmed", None)
        if str(exc) != question:
            st.caption(str(exc))
        return
    if st.session_state.get("request_confirmed") != key:
        st.session_state.pop("request_confirmed", None)

    st.subheader("Confirm your inputs" if manual else "Confirm the interpretation")
    show_policy(policy, search_alternatives=search_alternatives)
    if scope:
        st.caption("Starting weights · " + " · ".join(f"{ticker} {weight:.2%}" for ticker, weight in scope.baseline.items()))
        st.caption("Historical replays · " + ", ".join(window.id for window in scope.windows))
        if context := " · ".join(label for label in (scope.objective, scope.withdrawal_time) if label):
            st.caption(f"Planning context · {context}")
    complete = True
    if manual:
        complete = st.checkbox(MANUAL_SCOPE, key=scope_widget_key)
        if not complete:
            st.session_state.pop("request_confirmed", None)
    request_case = Case(
        run_id, "User-confirmed fictional request.", "terminal_loss", None, 0, scope=scope,
        include_sector=include_sector,
    )
    reports = st.session_state.request_results

    def run_confirmed(fields, result_key, *, search=False, allow_resize=False):
        trace = draft.trace
        if changes and not manual:
            trace = (*trace, {"role": "profile", "event": "draft_edited", "changes": changes})
        if search:
            trace = (*trace, {"role": "profile", "event": "alternative_search_authorized"})
        if allow_resize:
            trace = (*trace, {"role": "profile", "event": "smaller_purchase_authorized"})
        confirmed = replace(draft, status="ok", data=fields, trace=trace)
        case = replace(new_case(request_case), search_alternatives=search)
        report = audit(case, confirmed, runtime)
        if report is not None:
            reports[result_key] = report
            st.session_state.request_confirmed = result_key
        else:
            reports.pop(result_key, None)
            st.session_state.pop("request_confirmed", None)
        return report

    if st.button("Confirm inputs and run audit", type="primary", disabled=not complete):
        run_confirmed(body, key)
    if st.session_state.get("request_confirmed") != key:
        return

    if policy["loss_limit"] is not None:
        comparison_keys = {metric: tuple((field, metric if field == "metric" else value) for field, value in key)
                           for metric in METRICS}
        if all(variant in reports for variant in comparison_keys.values()):
            st.subheader("Compare the two confirmed rules")
            for column, (metric, variant) in zip(st.columns(2), comparison_keys.items()):
                column.markdown(f"**{METRICS[metric]}**  \n{result_label(publish_report(reports[variant]))}")
    report = reports[key]
    show_report(report)
    if search_alternatives and can_confirm_search(report):
        if st.button(CONFIRM_SEARCH, key="request-confirm-alternatives") and run_confirmed(body, key, search=True):
            st.rerun()
    if report.get("needs_smaller_authorization") and st.session_state.get("request_declined_resize") != basis:
        st.caption("The full purchase is infeasible. A smaller purchase could be checked if you authorize it.")
        if st.button("Authorize a smaller purchase and rerun"):
            resized_key = tuple((field, True if field == "allow_smaller" else value) for field, value in key)
            if run_confirmed({**body, "allow_smaller": True}, resized_key, search=True, allow_resize=True) is not None:
                st.session_state.request_resize_choice = basis
                st.rerun()
        if st.button("Keep the requested size"):
            st.session_state.request_declined_resize = basis
            st.rerun()
    show_counterfactual(replace(request_case, id=report["case"]), report, runtime)


def main():
    st.set_page_config(page_title="AlphaForge · Portfolio Decision Audit", page_icon="◈", layout="wide")
    st.title("Portfolio Decision Audit")
    st.caption("AlphaForge AI · Fictional portfolio simulation · Historical results apply to the tested windows.")
    st.radio("Input", ("Reference case", "Write a request"), horizontal=True, key="audit_input")
    if st.session_state.audit_input != st.session_state.get("active_input"):
        st.session_state.active_input = st.session_state.audit_input
        for key in ("preset_key", "request_draft", "request_results", "request_confirmed", "manual_draft_id", "active_intake"):
            st.session_state.pop(key, None)
    if st.session_state.audit_input == "Write a request":
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
