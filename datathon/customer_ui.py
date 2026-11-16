"""Customer research workspace: conversation, observable progress and useful errors."""

from copy import deepcopy
from html import escape
from pathlib import Path

import streamlit as st

from .customer_agents import customer_runtime
from .customer_data import UnavailableResearch
from .customer_report import METHOD, report_html, report_markdown, verify_report
from .customer_view import _charts, _risk_checks, _scenarios, _sources
from .customer_workflow import research_question
from .hosted_market import HostedArchiveError
from .model_settings import bedrock_failure_message
from .runtime_budget import RuntimeBudgetExceeded, run_sync_action
from .web_research import configured_search


EXAMPLES = {
    "AI and Bitcoin": (
        "I already hold SPY and I'm investing for at least 15 years. I'm okay with big swings, "
        "and I'd like to add some Nvidia (NVDA) and a Bitcoin ETF (IBIT). "
        "Would that still leave me diversified, or would I be leaning too heavily on the same risks?"
    ),
    "Growth with ESG preferences": (
        "I want to grow my savings over the next 10 years, but I'd like to keep the ups and downs manageable. "
        "I'm looking at ESGU and SPY, and I want to avoid companies with serious environmental or social controversies. "
        "How do the two funds compare, and how can I tell what they actually screen out?"
    ),
    "A stock before retirement": (
        "I'm hoping to retire in about four years. I'd still like my savings to grow, but I can't afford a big drop. "
        "I keep hearing about Tesla (TSLA) and I'm tempted to buy some. "
        "How bad have its past drops been, and what would that risk mean for my retirement savings?"
    ),
}
STEPS = (
    ("understand", "Understand your question", "Identify the idea and the conditions you stated."),
    ("plan", "Plan the analysis", "Choose the questions that need evidence."),
    ("sources", "Find the source data", "Resolve the instruments and retrieve dated observations."),
    ("calculate", "Calculate and check", "Compute the figures and independently check the arithmetic."),
    ("investigate", "Investigate the evidence", "Run the selected checks and look into material gaps."),
    ("synthesize", "Build the conclusion", "Connect the evidence to your question."),
    ("review", "Review the answer", "Check the claims, sources and unfinished work."),
)
STYLE = Path(__file__).with_name("customer_ui.css")


def _reset(question=""):
    for key in ("customer_report", "customer_context", "customer_state", "customer_history", "customer_error",
                "customer_execution", "customer_attempt", "customer_followup", "customer_goal", "customer_timing", "customer_constraints"):
        st.session_state.pop(key, None)
    st.session_state.customer_question = question


def _apply_example():
    _reset(EXAMPLES[st.session_state.customer_example])


def _step_for(message):
    for prefix, key in (("Understanding", "understand"), ("Planning", "plan"), ("Looking up", "sources"),
                        ("Checking the Bank", "sources"), ("Calculating", "calculate"),
                        ("Collecting", "investigate"), ("Preparing", "synthesize"), ("Checking each", "review")):
        if message.startswith(prefix):
            return key
    return "investigate"


def _step_html(key, title, description, state):
    labels = {"waiting": "Waiting", "running": "In progress", "complete": "Complete", "attention": "Needs attention", "skipped": "Not reached"}
    mark = "✓" if state == "complete" else "!" if state == "attention" else str([s[0] for s in STEPS].index(key) + 1)
    # Active tracks animate without implying a measured token-level percentage.
    value = ' aria-valuenow="100"' if state == "complete" else ' aria-valuenow="0"' if state in {"waiting", "skipped"} else ""
    return (f'<div class="research-step" data-state="{state}"><span class="step-number">{mark}</span>'
            f'<div class="step-body"><div class="step-title">{escape(title)}<span>{labels[state]}</span></div>'
            f'<div class="step-description">{escape(description)}</div>'
            f'<div class="step-track" role="progressbar" aria-label="{escape(title)}" aria-valuemin="0" aria-valuemax="100"{value}><i></i></div></div></div>')


def _trace_events(report):
    events = []
    for part in (report.get("plan", {}), report.get("planning", {}), report.get("editor", {})):
        events.extend(part.get("trace", []))
    for step in report.get("editor", {}).get("analysis_steps", []):
        for part in (step.get("details", {}), step.get("review", {})):
            events.extend(part.get("trace", []))
    return events


def _service_problem(events, reason=""):
    """Use structured error codes; never echo exception payloads or credentials."""
    specific = {
        "deadline": "The assessment did not finish within this stage's time limit.",
        "review_reserve": "The written assessment could not finish with enough time remaining for its independent review.",
        "no_new_information_or_repair": "The assessment repeated a claim that the evidence review had already rejected.",
        "time_budget": "The research exhausted its total time budget.",
        "model_call_timeout": "The model did not finish this stage before its timeout.",
        "model_calls_budget": "The research reached its model-call limit before a supported answer was ready.",
        "tool_calls_budget": "The research reached its evidence-tool limit with work still unresolved.",
        "token_budget": "The model reached the configured token budget before finishing this stage.",
        "invalid_handoff": "The model response did not satisfy this stage’s required output format.",
        "tool_not_completed": "The model did not submit a valid result for this stage.",
    }
    message = specific.get(reason) or bedrock_failure_message(events, stop_reason=reason)
    if "credentials" in message or "expired" in message.lower():
        action = "Refresh the AWS session used to run this app, then retry this question."
    elif "access" in message:
        action = "Check the app’s Bedrock model access, then retry."
    elif "limit" in message:
        action = "Wait briefly, then retry this question."
    elif "time" in message or "connect" in message:
        action = "Check the research service connection and retry. A narrower question may finish sooner."
    elif "Install" in message:
        action = "Install the project dependencies in the environment running the app."
    else:
        action = "Retry the question. If it persists, check the research service configuration."
    return {"stage": "Research service", "reason": message, "action": action}


def _issues(report):
    result = []
    plan, editor = report["plan"], report.get("editor", {})
    trace = _trace_events(report)
    if plan.get("origin") != "bedrock" or report.get("planning", {}).get("origin") == "unavailable":
        result.append(_service_problem(trace, plan.get("failure", "")))
    for issue in report.get("source_issues", []):
        queries = ", ".join(issue["queries"])
        result.append({"stage": "Source data", "reason": f"{queries}: {issue['reason']}" if queries else issue["reason"],
                       "action": issue["action"]})
    for error in report.get("errors", []):
        if not any(error == issue["reason"] or error in {f"{query}: {issue['reason']}" for query in issue["queries"]}
                   for issue in report.get("source_issues", [])):
            result.append({"stage": "Evidence limits", "reason": str(error)[:700],
                           "action": "Use the available evidence or narrow the requested calculation."})
    review = editor.get("explanation_review", {}) or {}
    if report.get("blocks") and editor.get("answer_status") == "evidence_only":
        failure = editor.get("failure") or review.get("failure") or editor.get("budget", {}).get("stop_reason")
        reason = _service_problem(trace, failure)["reason"] if failure else review.get("feedback")
        result.append({"stage": "Answer review", "reason": reason or "A supported written conclusion could not be completed.",
                       "action": "Use the checked evidence below, add the missing context, or ask a narrower question."})
    elif editor.get("answer_status") == "partial":
        remaining = review.get("remaining_user_requests", [])
        blocked = [t.get("remaining_gap") or t.get("completion_review") for t in report.get("tasks", []) if t.get("status") != "complete"]
        reason = " ".join(remaining or [x for x in blocked if x])
        if reason:
            result.append({"stage": "Open analysis", "reason": reason[:1000],
                           "action": "Add the requested information in the follow-up, or keep the conclusion within the stated scope."})
    return result


def _show_issue(issue):
    with st.container(key="issue-" + str(abs(hash((issue["stage"], issue["reason"]))))):
        st.html('<div class="issue-kicker">' + escape(issue["stage"]) + '</div>')
        st.write(issue["reason"])
        st.caption("Next step · " + issue["action"])


def _run(question, market_loader=None, *, continue_conversation=False, retry=False):
    previous = st.session_state.get("customer_report")
    prior_state = deepcopy(st.session_state.get("customer_state")) if continue_conversation else None
    if retry and st.session_state.get("customer_attempt"):
        attempt = st.session_state.customer_attempt
        question, prior_state = attempt["question"], deepcopy(attempt["previous_state"])
        continue_conversation = attempt["continue"]
    st.session_state.customer_attempt = {"question": question, "previous_state": prior_state, "continue": continue_conversation}
    st.session_state.pop("customer_error", None)
    states = {key: "waiting" for key, _, _ in STEPS}
    current, log = None, []
    with st.status("Researching your question", expanded=True) as status:
        overall = st.progress(0, text="Starting your research")
        slots = {key: st.empty() for key, _, _ in STEPS}

        def draw():
            for key, title, description in STEPS:
                slots[key].markdown(_step_html(key, title, description, states[key]), unsafe_allow_html=True)
            completed = sum(value == "complete" for value in states.values())
            overall.progress(completed / len(STEPS), text=f"{completed} of {len(STEPS)} stages completed")

        def progress(message):
            nonlocal current
            key = _step_for(message)
            if current and current != key and states[current] == "running":
                states[current] = "complete"
            current, states[key] = key, "running"
            log.append({"stage": key, "description": message})
            status.update(label=message)
            draw()

        draw()
        try:
            provider = None
            try:
                market = market_loader() if market_loader else None
            except HostedArchiveError as exc:
                market = None
                provider = UnavailableResearch(str(exc))
            except (OSError, ValueError):
                market = None
            report = run_sync_action(research_question(question, runtime=customer_runtime(), progress=progress,
                market_data=market, provider=provider, previous_state=prior_state, web_search=configured_search()))
        except Exception as exc:
            if current:
                states[current] = "attention"
            if isinstance(exc, RuntimeBudgetExceeded):
                issue = {"stage": dict((key, title) for key, title, _ in STEPS).get(current, "Research"),
                         "reason": "The research reached its time or request budget before this stage finished.",
                         "action": "Retry, or ask one smaller question at a time."}
            else:
                code = getattr(exc, "response", {}).get("Error", {}).get("Code", "") if isinstance(getattr(exc, "response", None), dict) else ""
                issue = _service_problem([{"event": "agent_exception", "error_type": type(exc).__name__, "error_code": code}])
                issue["stage"] = dict((key, title) for key, title, _ in STEPS).get(current, "Research")
                if isinstance(exc, (ValueError, ArithmeticError)):
                    issue.update(reason="An input or calculation did not pass its validation check. A new report was not released.",
                                 action="Check the stated instruments, amounts, currencies and timing, then retry.")
            st.session_state.customer_error = issue
            draw()
            status.update(label="Research paused · " + issue["stage"], state="error", expanded=True)
            st.session_state.customer_execution = {"states": states, "events": log}
            return False
        if current:
            states[current] = "attention" if report["status"] in {"unavailable", "needs_input"} or report.get("editor", {}).get("answer_status") == "evidence_only" else "complete"
        for key in states:
            if states[key] == "waiting":
                states[key] = "skipped"
        if report["plan"].get("origin") != "bedrock":
            states["understand"] = "attention"
        if report.get("planning", {}).get("origin") == "unavailable":
            states["plan"] = "attention"
        if report.get("errors"):
            states["sources"] = "attention"
        if any(task.get("status") in {"blocked", "partial"} for task in report.get("tasks", [])):
            states["investigate"] = "attention"
        if report.get("blocks") and report.get("editor", {}).get("answer_status") == "evidence_only" and states["review"] != "skipped":
            states["review"] = "attention"
        draw()
        status.update(label="Research complete" if report["status"] == "ready" else "Research finished · see the open questions below",
                      state="error" if report["status"] == "unavailable" else "complete", expanded=False)
    if continue_conversation and previous and verify_report(previous) and not retry:
        history = st.session_state.get("customer_history", [])
        history.append({"question": previous["question"], "answer": deepcopy(previous.get("editor", {}).get("explanations", []))})
        st.session_state.customer_history = history[-6:]
    elif not continue_conversation:
        st.session_state.pop("customer_history", None)
    st.session_state.customer_execution = {"states": states, "events": log}
    st.session_state.customer_report = report
    st.session_state.customer_state = report.get("conversation_state")
    st.session_state.customer_context = question
    return True


def _sidebar():
    with st.sidebar:
        st.html('<div class="rail-brand"><span class="brand-symbol">a<span>↗</span></span><div>AlphaForge<span class="brand-subtitle">INVESTMENT RESEARCH</span></div></div>')
        st.button("New research", icon=":material/add:", use_container_width=True, on_click=_reset, key="new-research")
        st.html('<div class="rail-label">START WITH A QUESTION</div>')
        st.radio("Example questions", list(EXAMPLES), key="customer_example", label_visibility="collapsed")
        selected = EXAMPLES[st.session_state.customer_example]
        st.caption(selected)
        st.button("Apply question", icon=":material/north_east:", use_container_width=True, on_click=_apply_example)
        report = st.session_state.get("customer_report")
        if report:
            with st.container(key="rail-context"):
                st.html('<div class="rail-label">IN THIS RESEARCH</div>')
                assets = [row["asset"]["symbol"] for row in report.get("analyses", [])]
                if assets:
                    st.write(" · ".join(assets))
                for condition in report["plan"].get("conditions", [])[:4]:
                    if condition["kind"] in {"goal", "horizon", "withdrawal", "capacity"}:
                        st.caption(condition["excerpt"])
        st.html('<div class="rail-footer"><span class="rail-dot"></span>Investment research assistant<p>Public data. Hypothetical scenarios.<br>No transactions are placed.</p></div>')


def _execution():
    execution = st.session_state.get("customer_execution")
    if not execution:
        return
    with st.expander("Research progress", icon=":material/route:"):
        for key, title, description in STEPS:
            st.html(_step_html(key, title, description, execution["states"].get(key, "skipped")))
        investigations = sum(row["stage"] == "investigate" for row in execution["events"])
        if investigations > 1:
            st.caption("The assistant returned to the evidence stage to investigate an unresolved question.")


def _context_inputs():
    with st.popover("Add context", icon=":material/tune:", use_container_width=True):
        st.markdown("**Your investment context**")
        st.caption("These are your stated conditions. Leave anything unknown blank.")
        st.text_input("What is this money for?", key="customer_goal", placeholder="For example, a future down payment")
        st.text_input("When might you need it?", key="customer_timing", placeholder="Your investment or withdrawal horizon")
        st.text_input("Holdings, cash needs or other constraints", key="customer_constraints", placeholder="Amounts, currencies, losses you could absorb…")


def _composer(market_loader):
    with st.container(key="research-composer"):
        with st.form("research-question", border=False):
            question = st.text_area("Your investment question", key="customer_question", height=140, max_chars=4000,
                label_visibility="collapsed", placeholder="Which investment are you considering? Include your question, amount and when you might need the money.")
            controls, hint, action = st.columns((1.1, 2.1, 1.4), vertical_alignment="center")
            with controls:
                _context_inputs()
            with hint:
                st.caption("Use an investment name or ticker. Add relevant objectives and constraints.")
            with action:
                submitted = st.form_submit_button("Analyze my question", icon=":material/arrow_forward:", type="primary", use_container_width=True)
    if submitted:
        if not question.strip():
            st.info("Start with an investment name or a question you want to explore.")
            return
        additions = [f"{label}: {st.session_state.get(key, '').strip()}" for label, key in (
            ("Goal", "customer_goal"), ("Horizon", "customer_timing"), ("Other conditions", "customer_constraints")) if st.session_state.get(key, "").strip()]
        complete_question = question.strip() + ("\nAdditional user-stated details:\n" + "\n".join(additions) if additions else "")
        if _run(complete_question, market_loader):
            st.rerun()


def _section(section, label=None):
    if label is not False:
        st.html('<h3 class="answer-heading">' + escape(label or section["heading"]) + '</h3>')
    main, *qualifiers = section["text"].split(" Assumptions: ", 1)
    main, *limits = main.split(" Scope limits: ", 1)
    if label is False:
        st.html('<p class="conclusion-text">' + escape(main) + '</p>')
    else:
        st.write(main)
    if qualifiers:
        assumptions, *nested_limits = qualifiers[0].split(" Scope limits: ", 1)
        st.write("Assumptions: " + assumptions)
        limits.extend(nested_limits)
    for limitation in limits:
        st.write("Limits: " + limitation)


def _conclusion(report):
    """Lead with released prose; never relabel raw evidence as a verdict."""
    sections = report.get("editor", {}).get("explanations", [])
    conclusion = [s for s in sections if s["heading"] == "My research conclusion"]
    with st.container(key="research-conclusion"):
        st.html('<div class="answer-label">Research conclusion</div>')
        if conclusion:
            for section in conclusion:
                _section(section, False)
        else:
            st.html('<h1 class="conclusion-unavailable">A conclusion is not available yet.</h1>')
            disclosure = next((block for key, block in report.get("blocks", {}).items() if key.endswith(".disclosure")), None)
            if disclosure:
                st.markdown("**" + disclosure["title"] + "**")
                st.write(disclosure["text"])
                for url in disclosure["sources"]:
                    st.markdown("[Source](" + url + ")")
            elif any(block.get("scope", {}).get("level") != "source_lead" and key != "data_gap"
                     for key, block in report.get("blocks", {}).items()):
                st.write("Checked evidence is available below. The written assessment could not be verified.")
            elif report.get("source_issues"):
                st.write(report["source_issues"][0]["reason"])
            else:
                st.write(report["plan"].get("question") or "We could not retrieve enough evidence to complete this assessment.")


def _available_evidence(report):
    """Show checked facts without inventing a conclusion or opposing arguments."""
    st.subheader("Available evidence")
    for block in report.get("blocks", {}).values():
        if block.get("scope", {}).get("level") == "source_lead":
            continue
        with st.container(border=True):
            st.markdown("**" + block["title"] + "**")
            st.write(block["text"])
            for url in block.get("sources", []):
                st.markdown("[Source](" + url + ")")


def _customer_issues(report):
    issues = _issues(report)
    if not issues:
        return
    review = report.get("editor", {}).get("explanation_review", {}) or {}
    outstanding = review.get("remaining_user_requests", [])
    if outstanding:
        st.subheader("What remains unanswered")
        for item in outstanding:
            st.write(item)
    source_issues = report.get("source_issues", [])
    if len(source_issues) == 1:
        st.warning(source_issues[0]["reason"])
    elif report.get("errors"):
        st.warning("Some evidence could not be collected or calculated. See the details below.")
    with st.expander("Analysis details and limitations"):
        for issue in issues:
            _show_issue(issue)
        for step in report.get("editor", {}).get("analysis_steps", []):
            details = step.get("details", {})
            for defect in details.get("validation_errors", []):
                st.caption("Assessment check: " + defect)
        events = _trace_events(report)
        reference = next((e.get("stop_reason") for e in reversed(events) if e.get("event") == "agent_end"), None)
        if reference:
            st.caption("Service reference: " + reference)


def _evidence(report):
    for section in report.get("editor", {}).get("explanations", []):
        with st.expander(section["heading"]):
            for key in section.get("evidence_ids", []):
                block = report["blocks"].get(key)
                if block:
                    st.markdown("**" + block["title"] + "**")
                    st.write(block["text"])
    _risk_checks(report)
    _sources(report)
    calls = [event for event in _trace_events(report) if event.get("event") == "bedrock" and event.get("status") == "success"]
    if calls:
        with st.expander("Research service verification"):
            st.write("Amazon Bedrock Converse returned successful responses for this research.")
            stages = {event.get("role", "") for event in calls} - {""}
            if stages:
                st.caption("Roles: " + ", ".join(sorted(stages)))
            st.caption("Model: " + calls[0]["model_id"] + " · Request region: " + calls[0]["region"])
    with st.expander("The question and context used"):
        st.write(report["question"])
        for condition in report["plan"].get("conditions", []):
            st.caption(condition["kind"].replace("_", " ").capitalize() + " · " + condition["excerpt"])


def render_report(report):
    if not verify_report(report):
        _show_issue({"stage": "Report integrity", "reason": "This report no longer matches its checked evidence.",
                     "action": "Run the question again to generate a fresh report."})
        return
    analyses, editor = report.get("analyses", []), report.get("editor", {})
    status = editor.get("answer_status", "evidence_only")
    _conclusion(report)
    with st.container(key="research-user-question"):
        st.html('<div class="answer-label">Your question</div>')
        st.write(report["question"])
    title, actions = st.columns((4, 1), vertical_alignment="center")
    labels = {"reviewed": "Assessment reviewed", "partial": "Partial assessment", "evidence_only": "Assessment incomplete"}
    with title:
        st.html('<div class="result-meta"><span class="result-status" data-state="' + escape(status) + '">' + labels.get(status, "Research") + '</span><span>AlphaForge Investment Research</span></div>')
    with actions:
        if report.get("blocks"):
            with st.popover("Export", icon=":material/ios_share:", use_container_width=True):
                st.download_button("Report with charts" if analyses else "HTML report", report_html(report), "investment-research.html", "text/html", use_container_width=True)
                st.download_button("Markdown", report_markdown(report), "investment-research.md", "text/markdown", use_container_width=True)
    if not report.get("blocks") and not report.get("web_search"):
        _customer_issues(report)
        return
    labels = ["Assessment", "Evidence & sources"]
    if analyses:
        labels.insert(1, "Charts & scenarios")
    tabs = dict(zip(labels, st.tabs(labels)))
    overview, evidence = tabs["Assessment"], tabs["Evidence & sources"]
    with overview:
        explanations = editor.get("explanations", [])
        panels = [(label, [s for s in explanations if s["heading"] == heading])
                  for heading, label in (("What supports this view", "Supporting evidence"),
                                         ("What argues against it", "Counterpoints & risks"))]
        populated = [panel for panel in panels if panel[1]]
        if populated:
            columns = st.columns(len(populated), gap="large")
            for column, (label, sections) in zip(columns, populated):
                with column, st.container(border=True):
                    for section in sections:
                        _section(section, label)
        elif report.get("blocks") and not any(s["heading"] == "My research conclusion" for s in explanations):
            _available_evidence(report)
        for section in explanations:
            if section["heading"] not in {"My research conclusion", "What supports this view", "What argues against it"}:
                with st.container(key="research-next-step"):
                    _section(section, "Uncertainties & next steps")
        for conflict in report.get("profile", {}).get("conflicts", []):
            st.warning("Conflicting " + conflict["field"].replace("_", " ") + ": " + " / ".join(conflict["statements"]) + ". " + conflict["impact"])
        _customer_issues(report)
    if analyses:
        with tabs["Charts & scenarios"]:
            _charts(analyses)
            _scenarios(report)
            st.caption("Observed history and hypothetical scenarios, with their own dates and assumptions. Neither is a forecast.")
    with evidence:
        _evidence(report)


def render_customer(market_loader=None):
    st.html(STYLE)
    cached = st.session_state.get("customer_report")
    if cached and cached.get("method") != METHOD:
        st.session_state.pop("customer_report", None)
        st.session_state.pop("customer_state", None)
        st.info("The analysis workflow changed. Start a fresh research question.")
    _sidebar()
    st.html('<div class="workspace-topline"><span>Investment research</span><span class="workspace-mode">Hypothetical analysis</span></div>')
    report = st.session_state.get("customer_report")
    if not report:
        st.html('<div class="research-hero"><h1>Investment research assistant</h1><p>Ask about an investment, compare assets or examine how your cash needs affect an idea.</p></div>')
        _composer(market_loader)
    else:
        render_report(report)
        history = st.session_state.get("customer_history", [])
        if history:
            with st.expander(f"Earlier questions ({len(history)})"):
                for turn in history:
                    with st.chat_message("user"):
                        st.write(turn["question"])
                    with st.chat_message("assistant", avatar=":material/insights:"):
                        for section in turn["answer"]:
                            st.write(section["text"])
        _execution()
        for resolution in report.get("resolutions", []):
            if resolution.get("status") == "needs_confirmation":
                st.warning("Confirm the listing for " + resolution["query"])
                st.dataframe(resolution["candidates"], hide_index=True)
        follow_up = report["plan"].get("question", "")
        if follow_up:
            with st.container(key="followup-hint"):
                st.markdown("**To refine this assessment**")
                st.write(follow_up)
        if prompt := st.chat_input("Ask a follow-up or add details to your question", key="customer_followup", max_chars=1000):
            if _run(prompt.strip(), market_loader, continue_conversation=True):
                st.rerun()
    if error := st.session_state.get("customer_error"):
        _show_issue(error)
        if not report:
            _execution()
    retryable = bool(st.session_state.get("customer_error")) or bool(report and report["status"] in {"unavailable", "partial"})
    if retryable and st.session_state.get("customer_attempt"):
        if st.button("Retry analysis", icon=":material/refresh:", key="retry-research"):
            if _run("", market_loader, retry=True):
                st.rerun()
