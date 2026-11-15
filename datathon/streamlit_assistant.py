"""Question and profile entry for the fictional investment assistant."""

from zipfile import BadZipFile

import streamlit as st

from .allocation_compare import compare_allocations, comparison_assets
from .allocation_view import render_allocation_result
from .assistant_intent import suggest_intent
from .assistant_request import parse_comparison_request
from .assistant_request_model import interpret_comparison_request
from .investor_profile import InvestorProfile, PRIORITIES, RISK_TOLERANCES, suggest_priority
from .model_settings import configured_bedrock_runtime
from .runtime_budget import run_sync_action
from .scope import OBJECTIVES, WITHDRAWAL_TIMES


TASKS = {
    "compare_allocations": "Compare assets or allocations",
    "trade_audit": "Audit a proposed NVDA trade",
}
_TRADE_STATE = ("request_draft", "request_results", "request_confirmed", "manual_draft_id",
                "request_resize_choice", "request_declined_resize", "active_intake", "active_challenge")


def clear_assistant_result():
    for key in ("assistant_confirmed", "assistant_comparison", "assistant_confirm_text_scope", *_TRADE_STATE):
        st.session_state.pop(key, None)


def _assistant_question():
    st.subheader("What investment decision are you exploring?")
    return st.text_area(
        "Investment question", height=104, max_chars=800, key="assistant_question",
        placeholder="Compare AGG and GLD. Maximum drawdown must not exceed 12%.",
        help="Use fictional details. Include the assets, any preferred measure, and binding limits in your own words.",
    ).strip()


async def _bedrock_draft(question, assets, local):
    runtime = configured_bedrock_runtime(profile=True)
    route = None
    if local["status"] == "unrecognized":
        route = await suggest_intent(question, runtime)
        if route["task"] == "trade_audit":
            return local, route
        if route["task"] != "compare_allocations":
            return local, route
    draft = await interpret_comparison_request(question, assets, runtime)
    if trace := draft.get("trace"):
        logged_route = {"status": "proposed", "task": "compare_allocations", "trace": trace,
                        "usage": draft.get("usage", {})}
        if route:
            logged_route["trace"] = [*route["trace"], *trace]
        route = logged_route
    return draft, route


def _market_bundle(data_loader):
    try:
        return data_loader()
    except (OSError, ValueError, BadZipFile):
        st.error("The market bundle could not be read. Check the organizer ZIP or extracted folder.")
        return None


def _question_draft(question, data_loader):
    actions = st.columns(2)
    use_local = actions[0].button("Interpret question", type="primary")
    use_model = actions[1].button("Interpret with Bedrock")
    if use_local or use_model:
        clear_assistant_result()
        st.session_state.pop("assistant_question_draft", None)
        if (data := _market_bundle(data_loader)) is None:
            return None
        assets = comparison_assets(data)
        draft = parse_comparison_request(question, assets)
        route = None
        if use_model and draft["status"] not in {"ready", "unsupported"}:
            with st.spinner("Checking how the question maps to supported evidence and inputs"):
                draft, route = run_sync_action(_bedrock_draft(question, assets, draft))
        st.session_state.assistant_question_draft = (draft, route)
    return st.session_state.get("assistant_question_draft")


def _question_options(fields):
    if options := fields.get("options"):
        return options
    first, second = fields.get("first_asset"), fields.get("second_asset")
    return {first: {first: 1.0}, second: {second: 1.0}} if first and second and first != second else None


def _show_question_sources(sources):
    st.text("\n".join(f"{field.replace('_', ' ').capitalize()} · {excerpt}" for field, excerpt in sources.items()))


def _render_question_answer(question, saved, data_loader, trade_entry):
    if saved is None:
        st.caption("Interpret the question to see the options and limits that will be used.")
        return
    draft, route = saved
    if route and route["task"] == "trade_audit":
        panel = st.container(key="assistant-trade", border=True)
        with panel:
            st.subheader(TASKS["trade_audit"])
            st.caption("Review the trade extracted from your question with the audit tool.")
        trade_entry(panel, assistant_question=question, intent=route)
        return

    fields = draft["fields"]
    options = _question_options(fields)
    scope_check = bool(draft.get("scope_review_required")) and draft["status"] == "clarify" and bool(options)
    if draft["status"] != "ready" and not scope_check:
        st.warning(draft["message"] or "Describe a historical comparison with two choices, or use Bedrock to interpret a supported trade.")
        if draft["sources"]:
            _show_question_sources(draft["sources"])
        return
    if not options:
        st.warning("Identify two distinct assets or give the full weights for two allocations.")
        return

    objective, horizon = fields.get("objective"), fields.get("withdrawal_time")
    risk = fields.get("risk_tolerance")
    priority = fields.get("priority") or suggest_priority(objective, horizon, risk)
    profile = InvestorProfile(objective, horizon, priority, fields.get("require_esg", False), risk_tolerance=risk)
    include_2023, cap = fields.get("include_2023", False), fields.get("max_drawdown")
    with st.container(key="assistant-options", border=True):
        st.subheader("Review the inputs from your question")
        st.table([{"Option": name, "Starting weights": ", ".join(f"{symbol} {weight:.2%}" for symbol, weight in weights.items())}
                  for name, weights in options.items()])
        if context := " · ".join(x for x in (objective, horizon, risk) if x):
            st.caption(context)
        st.write(f"Comparison priority · {PRIORITIES[priority]}" if priority else "Show the historical measures side by side.")
        if cap is not None:
            st.write(f"Maximum historical drawdown limit · {cap:.2%}")
        if profile.require_esg:
            st.warning("Your required ESG screen remains unresolved. Verified financial measures can still be shown.")
        st.caption("Historical replays · 2022, 2023, and 2025" if include_2023 else "Historical replays · 2022 and 2025")
        if draft["sources"]:
            with st.expander("Wording used from your question"):
                _show_question_sources(draft["sources"])
        if scope_check:
            st.warning(draft["message"])
            confirmed = st.checkbox("I checked these inputs against my whole question and they cover every binding condition.",
                                    key="assistant_confirm_text_scope")
        else:
            confirmed = True
        st.caption("To correct an input, edit your question and interpret it again.")
    _run_comparison(data_loader, options, profile, include_2023, cap, route, can_run=confirmed,
                    request_sources=draft["sources"])


def _investor_profile():
    st.subheader("Confirm the fictional investor profile")
    left, right = st.columns(2)
    objective = left.selectbox("Investment objective", OBJECTIVES, index=None, key="assistant_objective")
    withdrawal = right.selectbox("Time until the next meaningful withdrawal", WITHDRAWAL_TIMES,
                                 index=None, key="assistant_horizon")
    left, right = st.columns(2)
    tolerance = left.selectbox("Willingness to take risk", RISK_TOLERANCES, index=None,
                               placeholder="Optional", key="assistant_risk_tolerance")
    require_esg = right.checkbox("Require verified environmental or social screening", key="assistant_esg")
    if require_esg:
        st.caption("The available data lack reviewed ESG screening. This requirement will remain unresolved.")
    if not (objective and withdrawal):
        return None
    suggested = suggest_priority(objective, withdrawal, tolerance)
    priorities = tuple(PRIORITIES)
    priority = st.radio(
        "Comparison priority", priorities, index=priorities.index(suggested), horizontal=True,
        format_func=PRIORITIES.__getitem__, key=f"assistant-priority-{objective}-{withdrawal}-{tolerance}",
    )
    profile = InvestorProfile(objective, withdrawal, priority, require_esg, risk_tolerance=tolerance)
    st.caption(profile.explanation)
    return profile


def _allocation(side, name, assets):
    chosen = st.multiselect(f"{name} holdings", assets, key=f"assistant-{side}-assets")
    weights = {}
    for ticker in chosen:
        weight = st.number_input(f"{name} · {ticker} weight (%)", min_value=0.01, max_value=100., value=None,
                                 step=.01, format="%.2f", key=f"assistant-{side}-weight-{ticker}")
        if weight is not None:
            weights[ticker] = round(weight * 100)
    if not chosen or len(weights) != len(chosen) or sum(weights.values()) != 10000:
        st.caption("Enter weights totaling 100%.")
        return None
    return {ticker: bps / 10000 for ticker, bps in weights.items()}


def _compare(data_loader, profile, intent):
    with st.container(key="assistant-options", border=True):
        st.subheader("Set up the comparison")
        mode = st.radio("Compare", ("Two assets", "Two allocations"), horizontal=True, key="assistant_compare_mode")
        include_2023 = st.checkbox("Add the 2023 stress window", key="assistant_compare_2023")
        if (data := _market_bundle(data_loader)) is None:
            return
        assets = comparison_assets(data, include_2023=include_2023)
        if len(assets) < 2:
            st.warning("Two assets with complete observations are needed for these windows.")
            return
        left, right = st.columns(2)
        if mode == "Two assets":
            first = left.selectbox("First asset", assets, index=None, key="assistant_first_asset")
            second = right.selectbox("Second asset", assets, index=None, key="assistant_second_asset")
            options = {first: {first: 1.0}, second: {second: 1.0}} if first and second and first != second else None
            if first and first == second:
                st.caption("Choose two different assets to compare.")
        else:
            with left:
                first = _allocation("current", "Current allocation", assets)
            with right:
                second = _allocation("proposed", "Proposed allocation", assets)
            options = {"Current allocation": first, "Proposed allocation": second} if first and second else None
        drawdown = st.number_input(
            "Maximum historical drawdown limit (%)", min_value=0., max_value=100., value=None,
            step=.01, format="%.2f", placeholder="No limit", key="assistant_compare_cap",
            help="Optional binding rule, applied to each allocation in every displayed window.",
        )
        st.caption("The comparison applies the options and requirements you confirm here and in the profile.")
        cap = round(drawdown * 100) / 10000 if drawdown is not None else None
    _run_comparison(data_loader, options, profile, include_2023, cap, intent)


def _run_comparison(data_loader, options, profile, include_2023, cap, intent, *, can_run=True, request_sources=None):
    signature = (options, profile, include_2023, cap)
    saved = st.session_state.get("assistant_comparison")
    if saved and (saved[0] != signature or not can_run):
        st.session_state.pop("assistant_comparison")
        saved = None
    if st.button("Confirm inputs and compare", type="primary", disabled=options is None or not can_run):
        if (data := _market_bundle(data_loader)) is None:
            return
        with st.spinner("Replaying both choices and independently checking the comparison"):
            try:
                report = compare_allocations(data, options, priority=profile.priority, max_drawdown=cap,
                                             include_2023=include_2023, require_esg=profile.require_esg)
            except ValueError as exc:
                st.warning(str(exc))
                return
        st.session_state.assistant_comparison = saved = (signature, report)
    if saved:
        render_allocation_result(saved[1], profile, intent=intent, request_sources=request_sources)


def render_assistant(data_loader, trade_entry):
    with st.container(key="assistant-question", border=True):
        question = _assistant_question()
        if question != st.session_state.get("assistant_last_question"):
            clear_assistant_result()
            st.session_state.pop("assistant_question_draft", None)
            st.session_state.assistant_last_question = question
        if question:
            saved = _question_draft(question, data_loader)
        else:
            task = st.selectbox("Analysis task", tuple(TASKS), format_func=TASKS.__getitem__, index=None,
                                placeholder="Choose a task to enter inputs directly", key="assistant_task")
    if question:
        _render_question_answer(question, saved, data_loader, trade_entry)
        return
    if task is None:
        return
    with st.container(key="assistant-profile", border=True):
        profile = _investor_profile()
        signature = (task, profile)
        if st.session_state.get("assistant_confirmed") != signature:
            clear_assistant_result()
        if st.button("Confirm profile and continue", type="primary", disabled=not (task and profile)):
            st.session_state.assistant_confirmed = signature
    if st.session_state.get("assistant_confirmed") != signature:
        return
    if task == "trade_audit":
        panel = st.container(key="assistant-trade", border=True)
        with panel:
            st.subheader(TASKS[task])
            st.caption("Review the trade details. A proposed sale can use QQQ or ZST.TO.")
        trade_entry(panel, investor=profile)
    else:
        _compare(data_loader, profile, None)
