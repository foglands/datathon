"""Streamlit entry point for the AlphaForge portfolio simulation."""

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile

import streamlit as st

from datathon.agents import PROFILE_FIELDS, AgentRun, ground_profile_request
from datathon.audit_view import render_comparison, result_label
from datathon.counterfactual import counterfactual_options, issuer_disclosure_options, run_counterfactual
from datathon.data import load_market_data, market_data_source
from datathon.decision_view import render_decisions
from datathon.finance import BASE_WEIGHTS
from datathon.model_settings import configured_bedrock_runtime
from datathon.publication import publish_check, publish_report
from datathon.question_language import ENGLISH_QUESTION_MESSAGE, is_english_question
from datathon.runtime_budget import (
    CHALLENGE_LIMITS, PROFILE_LIMITS, RuntimeBudgetExceeded, bound_audit, run_bounded, run_sync_action,
)
from datathon.scope import EXTRA_WINDOW, OBJECTIVES, WITHDRAWAL_TIMES, ReplayScope
from datathon.streamlit_assistant import clear_assistant_result, render_assistant
from datathon.streamlit_results import render_audit_workspace
from datathon.workflow import (
    NUMERIC_POLICY_LABELS, Case, examples, interpret_request, numeric_input_provenance, preset_profile, profile_policy,
    run_case,
)


METRICS = {"terminal_loss": "Terminal loss", "max_drawdown": "Maximum drawdown"}
FUNDING = ("QQQ", "ZST.TO")
BLOCKING_PROFILE_FIELDS = {"unsupported_scope", "multiple_loss_limits", "conflict"}
DIRECT_PROFILE = "Enter inputs directly"
OFFLINE_PROFILE = "Interpret text offline"
BEDROCK_PROFILE = "Interpret text with Bedrock"
PROFILE_INPUT = (DIRECT_PROFILE, OFFLINE_PROFILE, BEDROCK_PROFILE)
MANUAL_SCOPE = "These inputs include every binding rule for this simulation."
OFFLINE_PROFILE_SCOPE = "I checked this draft against my request and confirmed every binding rule for this audit."
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
STYLES = Path(__file__).with_name("datathon") / "streamlit_style.css"


@st.cache_data(show_spinner=False)
def _cached_market_data(source_key):
    return load_market_data(source_key[0])


def market_data():
    source_key = st.session_state.get("market_source")
    return _cached_market_data(source_key) if source_key is not None else load_market_data()


def refresh_market_source():
    try:
        source_key = market_data_source()
    except OSError:
        source_key = None
    if source_key == st.session_state.get("market_source"):
        return

    st.session_state.market_source = source_key
    had_report = ("preset_result" in st.session_state or bool(st.session_state.get("request_results"))
                  or "decision_result" in st.session_state
                  or "assistant_comparison" in st.session_state)
    for key in ("preset_result", "comparison_result", "active_challenge", "request_confirmed",
                "request_resize_choice", "request_declined_resize"):
        st.session_state.pop(key, None)
    if "request_results" in st.session_state:
        st.session_state.request_results = {}
    st.session_state.pop("assistant_comparison", None)
    st.session_state.pop("decision_result", None)
    st.session_state.pop("decision_storage", None)
    draft = st.session_state.get("assistant_question_draft")
    if draft and draft[0]["status"] != "live_market":
        st.session_state.pop("assistant_question_draft")
    if had_report:
        st.info("Market data changed. Confirm and rerun the audit to use the current snapshot.")


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


def show_counterfactual(case, report, published, runtime):
    if not published["publication"]["independent_review_verified"]:
        return
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
        hint = st.text_input("What would you like to check?", max_chars=500, key=f"{key}-hint", help="Write in English.")
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
        if hint.strip() and not is_english_question(hint):
            st.warning(ENGLISH_QUESTION_MESSAGE)
            return
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
        left.markdown(f"**Original audit**  \n{result_label(published)}")
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
            and report["publication"]["independent_review_verified"])


def show_search_authorization(key):
    with st.container(key="audit-search-authorization", border=True):
        st.subheader("Explore alternative funding")
        st.caption("Authorize a separate search using the funding sources and size rules you confirmed.")
        return st.button(CONFIRM_SEARCH, key=key, type="primary")


def preset_audit(setup):
    with setup:
        scenario_column, execution_column = st.columns((3, 2))
        with scenario_column:
            name = st.selectbox(
                "Scenario", tuple(PRESETS), help="Choose a fictional case to explore a rule or evidence gap.",
            )
        with execution_column:
            mode = st.radio("Execution", ("Offline", "Bedrock"), horizontal=True)
        st.caption({
            "Offline": "Replay the organizer’s data with Python and locally simulated agent handoffs.",
            "Bedrock": "Run live Strands and Amazon Bedrock tool calls with the confirmed reference inputs.",
        }[mode])
        case, overrides, field, alternative, comparison_label = PRESETS[name]
        search = st.checkbox(
            SEARCH_ALTERNATIVES, key=f"preset_search_alternatives-{name}",
            help="Prepare the funding search settings. Confirm the search after reviewing the original trade.",
        )
        case = replace(case, search_alternatives=False)
        profile_data = {**preset_profile(case), **overrides}
        with st.container(key="audit-policy"):
            show_policy(profile_policy(profile_data, search_alternatives=search), search_alternatives=search)
        confirmed = st.button("Confirm inputs and run audit", type="primary")
    key = (mode, name, search)
    if st.session_state.get("preset_key") != key:
        st.session_state.preset_key = key
        st.session_state.pop("preset_result", None)
        st.session_state.pop("comparison_result", None)

    runtime = configured_bedrock_runtime() if mode == "Bedrock" else None
    if confirmed:
        st.session_state.pop("comparison_result", None)
        st.session_state.preset_result = audit(
            new_case(case), AgentRun("ok", profile_data, ({"role": "profile", "event": "preset_inputs_selected"},)), runtime
        )

    report = st.session_state.get("preset_result")
    if report is None:
        return
    published = publish_report(report)
    reviewed_search = published.get("search_alternatives", False)
    result_panel = st.container()
    can_compare = field is not None and (field != "allow_smaller" or reviewed_search)
    if can_compare and published["publication"]["independent_review_verified"]:
        with st.container(key="audit-rule-change", border=True):
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

    with result_panel:
        comparison = st.session_state.get("comparison_result")
        if comparison is not None:
            published_comparison = publish_report(comparison)
            left, right = st.columns(2)
            left.markdown(f"**Original policy**  \n{result_label(published)}")
            right.markdown(f"**With the confirmed change**  \n{result_label(published_comparison)}")
            for panel, result in zip(st.tabs(("Original policy audit", "Changed policy audit")),
                                     (published, published_comparison)):
                with panel:
                    if result["publication"]["independent_review_verified"] and result.get("policy"):
                        show_policy(result["policy"], search_alternatives=reviewed_search)
                    render_audit_workspace(result)
        else:
            render_audit_workspace(published)
    if search and can_confirm_search(published):
        if show_search_authorization("preset-confirm-alternatives"):
            search_case = replace(new_case(case), search_alternatives=True)
            confirmed = AgentRun("ok", profile_data, ({"role": "profile", "event": "alternative_search_authorized"},))
            if updated := audit(search_case, confirmed, runtime):
                st.session_state.preset_result = updated
                st.session_state.pop("comparison_result", None)
                st.rerun()
    show_counterfactual(replace(case, search_alternatives=reviewed_search), report, published, runtime)


def edit_profile(draft, run_id, *, manual=False, search_alternatives, audit_focus=None):
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
    purchase_column, funding_column = st.columns(2)
    with purchase_column:
        target = amount(
            "target_bps", "NVDA purchase size (percentage points)",
            "10 percentage points adds 10% of the portfolio to NVDA.",
        )
    with funding_column:
        source = option("initial_source", "Funding for the original proposal", FUNDING)
    edited = {
        "target_bps": target,
        "initial_source": source,
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
              or "limit_bps" in initial.get("unverified_numeric_fields", ())
              or initial.get("clarification_field") in {"loss_metric", "loss_limit"},
        key=f"{run_id}-apply_loss_cap",
    )
    metric, limit = None, None
    if loss_cap:
        initial_metric = initial.get("metric") or (audit_focus if manual else None)
        metric = st.radio("The cap measures", tuple(METRICS), format_func=METRICS.get,
                          index=tuple(METRICS).index(initial_metric) if initial_metric in METRICS else None,
                          key=f"{run_id}-metric")
        limit = amount("limit_bps", "Historical loss cap (%)", "Applies to every included historical window.")
        st.caption("Terminal loss compares the start and end. Maximum drawdown measures the largest fall from a prior peak.")
    reserve_column, issuer_column = st.columns(2)
    with reserve_column:
        reserve = amount("reserve_floor_bps", "Minimum ZST.TO weight (%)", "This floor is a binding rule.")
    with issuer_column:
        issuer = amount(
            "issuer_cap_bps", "Maximum total NVIDIA issuer exposure (%)",
            "Includes direct and disclosed indirect common equity.",
        )
    edited.update({
        "metric": metric,
        "limit_bps": limit,
        "reserve_floor_bps": reserve,
        "issuer_cap_bps": issuer,
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


def edit_scope(run_id, investor=None):
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
        if investor:
            objective, withdrawal = investor.objective, investor.withdrawal_time
        else:
            objective = st.selectbox("Fictional investment objective", OBJECTIVES, index=None,
                                     placeholder="Optional", key=f"{run_id}-objective")
            withdrawal = st.selectbox("Timing of next meaningful withdrawal", WITHDRAWAL_TIMES, index=None,
                                      placeholder="Optional", key=f"{run_id}-withdrawal")
        if objective or withdrawal:
            st.caption("Set any spending reserve and historical loss limits explicitly in the rules below.")
    if custom or include_2023 or objective or withdrawal:
        return ReplayScope(weights, include_2023, objective, withdrawal)
    return None


def live_request(setup, *, investor=None, assistant_question="", intent=None):
    intake_key = "assistant_trade_intake" if investor or assistant_question else "request_intake"
    with setup:
        intake = st.radio("Profile input", PROFILE_INPUT, index=1 if assistant_question else 0, horizontal=True,
                          key=intake_key)
    for key in ("request_draft", "request_results", "request_confirmed", "manual_draft_id"):
        if st.session_state.get("active_intake") != intake:
            st.session_state.pop(key, None)
    st.session_state.active_intake = intake
    manual = intake == DIRECT_PROFILE
    offline = intake == OFFLINE_PROFILE
    esg_required = bool(investor and investor.require_esg)
    with setup:
        search_column, sector_column = st.columns(2)
        requested_search = search_column.checkbox(
            SEARCH_ALTERNATIVES, key="request_search_alternatives",
            help="Prepare the funding search settings. Confirm the search after reviewing the original trade.",
            disabled=esg_required,
        )
        include_sector = sector_column.checkbox(INCLUDE_SECTOR, key="request_include_sector")
    unassessed = [{"code": "esg"}] if esg_required else []
    if esg_required:
        st.warning("Environmental or social screening is unresolved. A limited audit checks only the original trade.")
        if not st.checkbox(LIMITED_SCOPE, key="assistant-trade-limited-esg"):
            st.session_state.pop("request_confirmed", None)
            return
        requested_search = False
    scope = None
    scope_error = None
    if manual:
        with setup:
            mode = st.radio("Audit execution", ("Offline", "Bedrock"), horizontal=True, key="manual_execution")
            st.caption("Direct entry skips model interpretation. Bedrock execution uses live audit tools.")
        if "manual_draft_id" not in st.session_state:
            st.session_state.manual_draft_id = f"manual-{uuid4().hex[:12]}"
            st.session_state.request_results = {}
        run_id = st.session_state.manual_draft_id
        draft = AgentRun("ok", {}, ({"role": "profile", "event": "manual_profile_entered"},))
        question = None
        runtime = configured_bedrock_runtime() if mode == "Bedrock" else None
        try:
            scope = edit_scope(run_id, investor)
        except ValueError as exc:
            scope_error = str(exc)
    else:
        runtime = None if offline else configured_bedrock_runtime()
        if investor:
            scope = ReplayScope(objective=investor.objective, withdrawal_time=investor.withdrawal_time)
        with setup, st.form(f"{intake_key}-question"):
            request = st.text_area(
                "Fictional investment request", value=assistant_question if investor or assistant_question else ROBERT_REQUEST,
                height=145, max_chars=2000,
                key="assistant_trade_question" if investor or assistant_question else "reference_trade_question",
                help="Write in English.",
            )
            submitted = st.form_submit_button(
                "Interpret request offline" if offline else "Interpret request with Bedrock", type="primary",
            )
        previous = st.session_state.get("request_draft")
        if previous and previous[:2] != (request, requested_search):
            for key in ("request_draft", "request_results", "request_confirmed"):
                st.session_state.pop(key, None)
            previous = None
        recover_offline = st.session_state.pop("request_offline_recovery", False)
        initial_offline = bool(assistant_question and request == assistant_question and previous is None)
        if submitted or (offline and (recover_offline or initial_offline)):
            if not is_english_question(request):
                st.warning(ENGLISH_QUESTION_MESSAGE)
                return
            run_id = f"request-{uuid4().hex[:12]}"
            if offline:
                draft = ground_profile_request(request.strip(), run_id, search_alternatives=requested_search)
                question = draft.data.get("summary") if draft.status != "ok" else None
            else:
                with st.spinner("Identifying the trade and rules that need confirmation"):
                    try:
                        (draft, _, question), usage = run_sync_action(run_bounded(
                            interpret_request(request.strip(), configured_bedrock_runtime(profile=True), run_id,
                                              search_alternatives=requested_search, defer_smaller_authorization=True),
                            PROFILE_LIMITS,
                        ))
                        draft = replace(draft, trace=(*draft.trace, {"role": "profile", "event": "runtime_usage", **usage}))
                    except RuntimeBudgetExceeded:
                        draft = AgentRun("error", {}, (), "timeout")
                        question = "Amazon Bedrock interpretation reached its time budget."
            st.session_state.request_draft = (request, requested_search, run_id, draft, question)
            st.session_state.request_results = {}
            st.session_state.pop("request_confirmed", None)
        saved = st.session_state.get("request_draft")
        if not saved:
            return
        _, _, run_id, draft, question = saved
        if draft.status == "error":
            st.error(question or "The trade request could not be interpreted.")
            if not offline:
                def continue_offline():
                    st.session_state[intake_key] = OFFLINE_PROFILE
                    st.session_state.request_offline_recovery = True

                st.button("Continue offline", key=f"{intake_key}-recover", on_click=continue_offline)
            return
        if offline:
            st.caption("Offline interpretation proposes inputs from the request. Check the draft before running the historical audit.")
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
            unassessed.extend({"code": requirement["code"]} for requirement in requirements)
        if question and field != "unsupported_constraint":
            st.warning(question)

    search_alternatives = requested_search and not unassessed
    with st.container(key="audit-editor", border=True):
        edited, changes, loss_cap = edit_profile(
            draft, run_id, manual=manual, search_alternatives=search_alternatives,
            audit_focus=investor.audit_focus if investor else None,
        )
    if scope_error:
        st.session_state.pop("request_confirmed", None)
        st.warning(scope_error)
        return
    pending = [NUMERIC_POLICY_LABELS[field] for field in draft.data.get("unverified_numeric_fields", ())
               if field in NUMERIC_POLICY_LABELS and edited.get(field) is None]
    if pending:
        st.session_state.pop("request_confirmed", None)
        st.caption("Enter each unverified value before confirming the audit: " + ", ".join(pending) + ".")
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
    if unassessed:
        key += (("unassessed", tuple(record["code"] for record in unassessed)),)
    basis = (run_id, key)
    scope_widget_key = f"{run_id}-complete-{key!r}"
    body = {**edited, "status": "ok", "summary": "User confirmed the simulated audit inputs.", "evidence_ids": []}
    body["numeric_input_sources"] = numeric_input_provenance(
        body, manually_entered=NUMERIC_POLICY_LABELS if manual else changes,
        source_excerpts=draft.data.get("source_excerpts", {}),
    )
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
    with st.container(key="audit-policy"):
        show_policy(policy, search_alternatives=search_alternatives)
    if scope:
        st.caption("Starting weights · " + " · ".join(f"{ticker} {weight:.2%}" for ticker, weight in scope.baseline.items()))
        st.caption("Historical replays · " + ", ".join(window.id for window in scope.windows))
        if context := " · ".join(label for label in (scope.objective, scope.withdrawal_time) if label):
            st.caption(f"Planning context · {context}")
    complete = True
    if manual or offline:
        scope_label = MANUAL_SCOPE if manual else OFFLINE_PROFILE_SCOPE
        if unassessed:
            scope_label = "I checked the audit inputs and the requirements marked as not assessed."
        complete = st.checkbox(scope_label, key=scope_widget_key)
        if not complete:
            st.session_state.pop("request_confirmed", None)
    request_case = Case(
        run_id, "User-confirmed fictional request.", "terminal_loss", None, 0, scope=scope,
        include_sector=include_sector,
    )
    reports = st.session_state.request_results

    def run_confirmed(fields, result_key, *, search=False, allow_resize=False):
        trace = (*intent["trace"], *draft.trace) if intent else draft.trace
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
    published = publish_report(report)
    if investor:
        st.caption(f"Profile focus · {investor.explanation} The trade verdict uses the confirmed limits.")
    render_audit_workspace(published, preferred_metric=investor.priority if investor else None)
    if search_alternatives and can_confirm_search(published):
        if show_search_authorization("request-confirm-alternatives") and run_confirmed(body, key, search=True):
            st.rerun()
    if published.get("needs_smaller_authorization") and st.session_state.get("request_declined_resize") != basis:
        st.caption("The full purchase is infeasible. A smaller purchase could be checked if you authorize it.")
        if st.button("Authorize a smaller purchase and rerun"):
            resized_key = tuple((field, True if field == "allow_smaller" else value) for field, value in key)
            if run_confirmed({**body, "allow_smaller": True}, resized_key, search=True, allow_resize=True) is not None:
                st.session_state.request_resize_choice = basis
                st.rerun()
        if st.button("Keep the requested size"):
            st.session_state.request_declined_resize = basis
            st.rerun()
    show_counterfactual(replace(request_case, id=published["case"]), report, published, runtime)


def show_navigation(market_bundle_found):
    with st.container(key="app-navigation"):
        brand, navigation, status = st.columns((1.3, 2.4, 1.3), vertical_alignment="center")
        with brand:
            st.html(
                '<div class="app-brand"><span class="app-brand-mark" aria-hidden="true">◈</span>'
                '<span>AlphaForge <strong>AI</strong></span></div>'
            )
        with navigation, st.container(key="assistant-nav"):
            workspace = st.radio(
                "Workspace", ("Investment assistant", "Reference cases"), horizontal=True,
                label_visibility="collapsed", key="workspace",
            )
        with status:
            label = "Archived data ready" if market_bundle_found else "Archived data unavailable"
            data_state = "ready" if market_bundle_found else "unavailable"
            st.html(f'<div class="app-data-status" data-state="{data_state}">{label}</div>')
    return workspace


def show_usage_notes(market_bundle_found):
    with st.container(key="app-data-methods"), st.expander("Data and methods"):
        if not market_bundle_found:
            st.warning("Set DATATHON_STARTER_PATH to the organizer ZIP or extracted starter folder to run historical analyses.")
        st.markdown(
            "**Historical risk.** Terminal loss compares the start and end of a replay. Maximum drawdown "
            "measures the largest fall from a prior peak. Each result applies to its displayed historical windows.\n\n"
            "**Holdings evidence.** Issuer and sector ranges retain unknown exposure when disclosures are missing. "
            "A verified calculation can still yield an unresolved rule.\n\n"
            "**Historical data.** Compare two choices, evaluate one allocation, or audit a proposed change in CAD "
            "using the covered prices. Missing assets require an explicitly sourced upload. A controversy-list "
            "screen is not an ESG rating; undisclosed holdings remain unresolved.\n\n"
            "**Confirmed scope.** Review the extracted inputs before a replay. An original proposal does not "
            "authorize a funding search or a smaller purchase; those require a separate confirmation.\n\n"
            "**Reference cases.** Archived validation includes the NVDA purchase funded from QQQ or ZST.TO and "
            "earlier live-quote checks. These are separate from the main historical decision workflow. All runs are fictional."
        )


def reference_cases():
    setup = st.container(key="audit-setup", border=True)
    with setup:
        title, input_choice = st.columns((1, 2), vertical_alignment="center")
        title.subheader("Set up an audit")
        with input_choice, st.container(key="audit-input-choice"):
            st.radio("Input", ("Reference case", "Write a request"), horizontal=True,
                     key="audit_input", label_visibility="collapsed")
    if st.session_state.audit_input != st.session_state.get("active_input"):
        st.session_state.active_input = st.session_state.audit_input
        for key in ("preset_key", "request_draft", "request_results", "request_confirmed", "manual_draft_id", "active_intake"):
            st.session_state.pop(key, None)
    if st.session_state.audit_input == "Write a request":
        live_request(setup)
    else:
        preset_audit(setup)


def main():
    st.set_page_config(page_title="AlphaForge · Investment Decision Assistant", page_icon="◈", layout="wide")
    st.html(STYLES)
    refresh_market_source()
    market_bundle_found = bool(st.session_state.get("market_source"))
    workspace = show_navigation(market_bundle_found)
    if st.session_state.get("active_workspace") != workspace:
        clear_assistant_result()
        for key in ("active_input", "preset_key", "preset_result", "comparison_result"):
            st.session_state.pop(key, None)
        st.session_state.active_workspace = workspace
    if workspace == "Investment assistant":
        render_decisions(market_data)
    else:
        st.title("Reference cases")
        legacy = st.radio("Reference workspace", ("Audited trade examples", "Earlier assistant validation"),
                           horizontal=True, key="reference_workspace")
        if legacy == "Earlier assistant validation":
            st.caption("Earlier release retained for regression comparison. Use Investment assistant for the current three-path workflow.")
            render_assistant(market_data, live_request)
        else:
            reference_cases()
    show_usage_notes(market_bundle_found)


if __name__ == "__main__":
    main()
