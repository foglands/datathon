"""Question and profile entry for the fictional investment assistant."""

from zipfile import BadZipFile

import streamlit as st

from .allocation_compare import compare_allocations, comparison_assets
from .allocation_view import render_allocation_result
from .assistant_intent import suggest_intent
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
    for key in ("assistant_confirmed", "assistant_comparison", *_TRADE_STATE):
        st.session_state.pop(key, None)


def _assistant_question():
    st.subheader("What investment decision are you exploring?")
    question = st.text_area(
        "Investment question", height=104, max_chars=800, key="assistant_question",
        placeholder="For example, compare two allocations before a planned withdrawal.",
        help="Use fictional details. Choose a task yourself or ask Bedrock to suggest one.",
    ).strip()
    saved = st.session_state.get("assistant_intent")
    if saved and saved[0] != question:
        st.session_state.pop("assistant_intent")
        saved = None
    if st.button("Suggest a task with Bedrock", disabled=not question):
        with st.spinner("Finding the supported task that best matches the question"):
            intent = run_sync_action(suggest_intent(question, configured_bedrock_runtime(profile=True)))
        st.session_state.assistant_intent = saved = (question, intent)
        st.session_state["assistant_task"] = intent["task"]
        clear_assistant_result()
    intent = saved[1] if saved else None
    if intent:
        if intent["status"] == "proposed":
            st.info(f"Suggested task · {TASKS[intent['task']]}. Review the task and enter its specific inputs below.")
        elif intent["status"] == "unsupported":
            st.warning("This question needs a different analysis. Narrow it to a supported simulation to proceed.")
        else:
            st.warning("A task suggestion is unavailable. You can select a supported analysis directly.")
    task = st.selectbox("Analysis task", tuple(TASKS), format_func=TASKS.__getitem__, index=None,
                        placeholder="Choose an analysis", key="assistant_task")
    return question, task, intent


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
        try:
            data = data_loader()
            assets = comparison_assets(data, include_2023=include_2023)
        except (OSError, ValueError, BadZipFile):
            st.error("The market bundle could not be read. Check the organizer ZIP or extracted folder.")
            return
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
        signature = (options, profile, include_2023, cap)
        saved = st.session_state.get("assistant_comparison")
        if saved and saved[0] != signature:
            st.session_state.pop("assistant_comparison")
            saved = None
        if st.button("Confirm inputs and compare", type="primary", disabled=options is None):
            with st.spinner("Replaying both choices and independently checking the comparison"):
                try:
                    report = compare_allocations(data, options, priority=profile.priority, max_drawdown=cap,
                                                 include_2023=include_2023, require_esg=profile.require_esg)
                except ValueError as exc:
                    st.warning(str(exc))
                    return
            st.session_state.assistant_comparison = saved = (signature, report)
    if saved:
        render_allocation_result(saved[1], profile, intent=intent)


def render_assistant(data_loader, trade_entry):
    with st.container(key="assistant-question", border=True):
        question, task, intent = _assistant_question()
    with st.container(key="assistant-profile", border=True):
        profile = _investor_profile()
        signature = (question, task, profile)
        if st.session_state.get("assistant_confirmed") != signature:
            clear_assistant_result()
        if st.button("Confirm profile and continue", type="primary", disabled=not (task and profile)):
            st.session_state.assistant_confirmed = signature
    if st.session_state.get("assistant_confirmed") != signature:
        return
    accepted_intent = intent if intent and intent["task"] == task else None
    if task == "trade_audit":
        panel = st.container(key="assistant-trade", border=True)
        with panel:
            st.subheader(TASKS[task])
            st.caption("Review the trade details. A proposed sale can use QQQ or ZST.TO.")
        trade_entry(panel, investor=profile, assistant_question=question, intent=accepted_intent)
    else:
        _compare(data_loader, profile, accepted_intent)
