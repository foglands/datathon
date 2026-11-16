"""A customer-facing conversation with research evidence progressively revealed."""

import altair as alt
import pandas as pd
import streamlit as st

from .customer_agents import customer_runtime
from .customer_report import methodology, report_markdown, report_html, verify_report, METHOD
from .customer_workflow import research_question
from .runtime_budget import run_sync_action


def _reset(question=""):
    st.session_state.customer_question = question
    st.session_state.pop("customer_report", None)
    st.session_state.pop("customer_context", None)
    st.session_state.pop("customer_state", None)


def _run(question, market_loader=None, *, continue_conversation=False):
    st.session_state.pop("customer_report", None)
    with st.status("Researching your idea…", expanded=True) as status:
        def progress(stage):
            status.update(label=stage)
            st.write(stage)
        try:
            market = market_loader() if market_loader else None
        except (OSError, ValueError):
            market = None
        report = run_sync_action(research_question(question, runtime=customer_runtime(), progress=progress, market_data=market,
            previous_state=st.session_state.get("customer_state") if continue_conversation else None))
        status.update(label="Your research is ready" if report["status"] == "ready" else "Partial research · some questions remain open",
                      state="complete", expanded=False)
    st.session_state.customer_report = report
    st.session_state.customer_context = question
    st.session_state.customer_state = report.get("conversation_state")


def _charts(analyses):
    rows = [{**point, "Asset": item["asset"]["symbol"], "Basis": item["basis"]}
            for item in analyses for point in item["metrics"]["path"]]
    frame = pd.DataFrame(rows)
    color = alt.Color("Asset:N", scale=alt.Scale(range=["#155e4c", "#d59243", "#4b77a3"]), legend=alt.Legend(orient="bottom"))
    base = alt.Chart(frame).encode(x=alt.X("date:T", title=None, scale=alt.Scale(type="utc")), color=color)
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**How the investment moved**")
        st.caption("Each series starts at 100; this is observed history.")
        chart = base.mark_line(strokeWidth=2.6).encode(
            y=alt.Y("index:Q", title="Indexed value", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="Date", timeUnit="utcyearmonthdate"), "Asset:N", "Basis:N", alt.Tooltip("index:Q", format=".2f", title="Indexed value")])
        st.altair_chart(chart.properties(height=270), width="stretch")
    with columns[1]:
        st.markdown("**How far it fell from earlier highs**")
        st.caption("A deeper dip means a larger observed loss from a previous peak.")
        chart = base.mark_line(strokeWidth=2.6).encode(
            y=alt.Y("drawdown:Q", title="Below previous high (%)"),
            tooltip=[alt.Tooltip("date:T", title="Date", timeUnit="utcyearmonthdate"), "Asset:N", "Basis:N", alt.Tooltip("drawdown:Q", format=".2f", title="Below high (%)")])
        st.altair_chart(chart.properties(height=270), width="stretch")
    first = analyses[0]["metrics"]
    bases = ", ".join(f"{item['asset']['symbol']}: {item['basis']}" for item in analyses)
    aligned = len({(item["metrics"]["start"], item["metrics"]["end"], item["metrics"]["observations"]) for item in analyses}) == 1
    st.caption((f"{first['start']} to {first['end']} · {first['observations']} common observations · {bases}. " if aligned
                else "Individual histories cover different periods; their total returns are not directly comparable. " + bases + ". ") +
               "Adjusted-close series; excluded dates and source limits are detailed below.")


def _scenarios(report):
    budget = report["plan"]["budget"]
    if not budget or budget["currency"] not in {"CAD", "USD"}:
        return
    with st.expander("What would a price change mean for this amount?"):
        st.write("These are simple hypothetical changes applied to the stated amount, with currency held fixed. "
                 "They are not forecasts, probability estimates, or limits on possible losses.")
        rows = [{"Hypothetical change": f"{shock:+.0%}", "Gain or loss": f"{budget['currency']} {budget['amount'] * shock:+,.2f}",
                 "Ending amount": f"{budget['currency']} {budget['amount'] * (1 + shock):,.2f}"}
                for shock in (-.20, -.10, .10, .20)]
        st.table(rows)


def _sources(report):
    with st.expander("Sources, dates and calculation details"):
        for item in report["analyses"]:
            asset = item["asset"]
            st.markdown(f"**{asset['symbol']} · {asset['source']}** — [Price history]({asset['source_url']})")
            st.text(f"Quote observed: {asset['price_as_of']}\nRetrieved: {asset['retrieved_at']}\n"
                    f"Quote currency: {asset['currency']} · Chart currency: {item['basis']}\n"
                    f"Missing price rows: {asset['omitted_rows']} · Missing same-date FX: {item['missing_fx']} · "
                    f"Other dates excluded for comparison: {item['alignment_omissions']}")
            st.caption(asset["adjustment"])
        if report["fx"]:
            st.markdown(f"[Bank of Canada · CAD per USD]({report['fx']['source_url']})")
            st.caption(f"Retrieved {report['fx']['retrieved_at']}")
        if report.get("cpi"):
            st.markdown(f"[Statistics Canada CPI via Bank of Canada]({report['cpi']['source_url']})")
            st.caption(report["cpi"]["basis"] + " · " + report["cpi"]["vintage"])
        st.write(methodology(report))


def _risk_checks(report):
    risks = report.get("risks", [])
    if not risks:
        return
    labels = {"assessed": "Calculated · limits apply", "needs_client_information": "Need your input",
              "missing_market_data": "Need source data", "not_supported": "Not supported", "not_applicable": "Not relevant"}
    st.subheader("Checks that matter for your question")
    st.table([{"Check": ("Trading-volume proxy" if risk["id"] == "market_liquidity" else risk["id"].replace("_", " ").capitalize()), "Status": labels[risk["status"]],
               "Why it matters": risk["reason"]} for risk in risks])
    for risk in risks:
        if risk["id"] == "cash_needs" and risk["results"]:
            st.markdown("**What withdrawals would have changed**")
            st.caption("A historical scenario with the stated amount and schedule. It is not a retirement-success probability.")
            for row in risk["results"]:
                st.write(f"{row['symbol']} · {row['currency']} {row['total_requested']:,.2f} requested, "
                         f"{row['shortfall']:,.2f} funding shortfall, {row['remaining']:,.2f} remaining at the end.")
                st.line_chart(pd.DataFrame(row["path"]).set_index("date")[["with_withdrawals", "without_withdrawals"]],
                              y_label=row["currency"], height=240)
                st.caption(row["schedule"]["timing_basis"] + " " + row["schedule"]["liquidation_rule"] + " " + row["recovery_note"])
                with st.expander(f"{row['symbol']} · withdrawal dates and shortfalls"):
                    st.dataframe(row["withdrawals"], hide_index=True, width="stretch")
        elif risk["id"] == "purchasing_power" and risk["results"]:
            st.markdown("**The purchasing-power difference**")
            st.table([{"Asset": row["symbol"], "Interval": row["start"] + " to " + row["end"],
                       "CAD nominal change": f"{row['nominal_return']:+.2%}", "CPI change": f"{row['cpi_change']:+.2%}",
                       "Real change": f"{row['real_return']:+.2%}"} for row in risk["results"]])
        elif risk["id"] == "interest_rate" and risk["results"]:
            st.markdown("**An illustrative interest-rate change**")
            st.table([{"Asset": row["symbol"], "Duration as of": row["as_of"], "Effective duration": f"{row['duration_years']:.2f} years",
                       "Yields rise 1 percentage point": f"{row['scenarios'][1]['approximate_price_change']:+.2%}",
                       "Yields fall 1 percentage point": f"{row['scenarios'][0]['approximate_price_change']:+.2%}"} for row in risk["results"]])
            st.caption("System-selected illustrative shocks, not forecasts. First-order duration approximation; credit spreads, FX and other conditions held fixed.")
        elif risk["id"] == "credit" and risk["results"]:
            with st.expander("Underlying bond credit quality · issuer disclosures"):
                for row in risk["results"]:
                    st.write(f"{row['symbol']} · as of {row['as_of']} · observed {row['observed_on']}")
                    st.table([{"Rating category": key, "Reported weight": f"{value:.2%}"} for key, value in row["rating_weights"].items()])
                    st.write(f"Unclassified or rounding residual: {row['unclassified_or_rounding_weight']:.2%}. " + row["limitation"])
                    st.table([{"Issuer sector category": key, "Reported weight": f"{value:.2%}"} for key, value in row["sector_weights"].items()])
    with st.expander("Supporting risk calculations, sources and gaps"):
        for risk in risks:
            st.markdown("**" + ("Trading-volume proxy" if risk["id"] == "market_liquidity" else risk["id"].replace("_", " ").capitalize()) + "**")
            st.write("Method: " + risk["method"])
            st.write("Data needed: " + risk["data_needed"])
            block = report["blocks"].get("risk." + risk["id"])
            if block:
                st.write(block["text"])
                for url in block["sources"]:
                    st.markdown(f"[Source evidence]({url})")


def _activity(report):
    with st.expander("How the assistant reached this report"):
        st.table([
            {"Step": "Understand", "Work": "Extract the proposed investments and stated conditions", "Execution": "Amazon Bedrock" if report["plan"]["origin"] == "bedrock" else "Local recovery parser"},
            {"Step": "Research", "Work": "Run selected evidence tools and investigate follow-up questions", "Execution": "Public source requests"},
            {"Step": "Calculate", "Work": "Compute sizing, historical changes and chart paths", "Execution": "Python formulas"},
            {"Step": "Review", "Work": "Recompute figures and every chart point independently", "Execution": "Passed" if report["analyses"] else "No report released"},
            {"Step": "Explain", "Work": "Investigate evidence gaps and synthesize a contextual answer", "Execution": "Amazon Bedrock" if report["editor"].get("origin") == "bedrock" else "Checked evidence template"},
        ])
        st.caption("Financial figures come from checked Python calculations. Model-written interpretation is reviewed in a separate step against the evidence. "
                   "These are observable actions, not private model reasoning.")
        st.json({"method": report["method"], "report_digest": report["report_digest"],
                 "intake": report["plan"].get("trace", []), "planning": report.get("planning", {}).get("trace", []), "report": report["editor"].get("trace", []),
                 "explanation_review": report["editor"].get("explanation_review", {})}, expanded=False)


def render_report(report):
    if not verify_report(report):
        st.error("This report no longer matches its checked evidence. Ask again to produce a fresh report.")
        return
    plan, analyses = report["plan"], report["analyses"]
    explanations = report["editor"].get("explanations", [])
    if analyses:
        with st.container(border=True):
            if report["editor"].get("answer_status") in {"partial", "evidence_only"}:
                st.info("Partial analysis: unresolved tasks or unsupported conclusions remain. Supported findings are retained below.")
            if explanations:
                for section in explanations:
                    st.markdown("### " + section["heading"])
                    st.write(section["text"])
                    with st.expander("Evidence behind this finding · " + section["heading"]):
                        for key in section["evidence_ids"]:
                            st.write(report["blocks"][key]["text"])
                        context = report.get("planning", {}).get("context", {})
                        for key in section.get("context_ids", []):
                            if key in context:
                                st.caption("Your words: " + context[key])
            else:
                st.markdown("### A checked conclusion is not available yet")
                st.write("The available calculations are shown below, but the analysis did not produce an independently accepted answer to your full question.")
                st.caption("This is an evidence-only result, not a personalized conclusion.")
    if plan["origin"] != "bedrock":
        st.info("The language model was unavailable. The limited local parser cannot provide a contextual investment assessment.")
    with st.expander("Your question and the context used"):
        st.text(report["question"])
        for condition in plan["conditions"]:
            st.text(f"{condition['kind'].replace('_', ' ').capitalize()} · {condition['excerpt']}")
        st.caption("Extracted statements are interpretations of your wording. Correct them in the conversation; unknowns stay unknown.")
        for conflict in report.get("profile", {}).get("conflicts", []):
            st.warning(f"Conflicting {conflict['field'].replace('_', ' ')}: " + " / ".join(conflict["statements"]) + " " + conflict["impact"])
    for resolution in report.get("resolutions", []):
        if resolution.get("status") == "needs_confirmation":
            st.warning("Please confirm the listing for " + resolution["query"])
            st.dataframe(resolution["candidates"], hide_index=True)
    with st.expander("Argument support and remaining tasks"):
        st.json({"arguments": report["editor"].get("arguments", []), "tasks": report.get("tasks", []),
                 "review": report["editor"].get("explanation_review", {}), "budget": report.get("execution_budget", {}),
                 "updates": (report.get("conversation_state") or {}).get("events", [])}, expanded=False)
        st.caption("Deterministic checks verify quantities and scope records. Semantic support is a separate, fallible model assessment.")
    with st.expander("Analysis questions and follow-up investigations"):
        for check in report.get("planning", {}).get("checks", []):
            st.write(check["question"])
        for outcome in report.get("tool_outcomes", []):
            st.write(outcome["question"])
            st.caption(outcome["outcome"])
        for step in report["editor"].get("analysis_steps", []):
            if step["action"] == "review":
                st.caption("Independent review: " + ("accepted" if step["accepted"] else "revision requested") + ". " + step["feedback"])
    for error in report["errors"]:
        st.warning(error)
    if analyses:
        st.subheader("The market evidence")
        if len(analyses) == 1:
            item = analyses[0]
            asset, metric = item["asset"], item["metrics"]
            first, second, third = st.columns(3)
            first.metric(f"{asset['symbol']} · latest observed", f"{asset['currency']} {asset['price']:,.2f}")
            second.metric(f"Historical change · {item['basis']}", f"{metric['return']:+.2%}")
            third.metric("Largest observed fall", f"{metric['drawdown']:.2%}")
            st.caption(f"Latest observation: {asset['price_as_of']} · Prices may be delayed; this is not an execution quote.")
        else:
            st.dataframe([{"Investment": item["asset"]["symbol"], "Latest observation": f"{item['asset']['currency']} {item['asset']['price']:.2f}",
                           "Observed at": item["asset"]["price_as_of"], "Historical change": f"{item['metrics']['return']:+.2%}",
                           "Largest fall": f"{item['metrics']['drawdown']:.2%}", "Historical currency": item["basis"]}
                          for item in analyses], hide_index=True, width="stretch")
        _charts(analyses)
        _risk_checks(report)
        st.subheader("Supporting calculations")
        for key in report["editor"]["order"]:
            if key.startswith("risk."):
                continue
            if (key == report["editor"]["takeaway"] and not explanations) or (key == "conclusion" and explanations):
                continue
            block = report["blocks"][key]
            st.markdown(f"**{block['title']}**")
            st.write(block["text"])
        _scenarios(report)
        _sources(report)
        st.download_button("Download report with charts", report_html(report), "investment-research.html", "text/html")
        with st.expander("Text version"):
            st.download_button("Download Markdown", report_markdown(report), "investment-research.md", "text/markdown")
    elif report["status"] == "unavailable":
        st.info("I could not obtain enough usable observations to support a numerical conclusion. "
                "You can retry, correct the ticker, or use a historical reference case.")
    _activity(report)


def render_customer(market_loader=None):
    cached = st.session_state.get("customer_report")
    if cached and cached.get("method") != METHOD:
        st.session_state.pop("customer_report", None)
        st.info("The analysis workflow has been updated. Research your question again to use contextual planning and review.")
    st.title("Turn an investment idea into a clearer decision.")
    st.write("Tell me what you are considering, what you want the money to do, and any conditions that matter. "
             "I will research the evidence, calculate the trade-offs, and explain what the results support.")
    st.caption("Investment research and hypothetical scenarios. No transactions are placed.")
    question = st.text_area("What are you thinking about?", key="customer_question", height=115, max_chars=4000,
                            placeholder="I am thinking of investing 3,000 CAD in AMD. I may need the money in two years. What should I understand?")
    action, reset = st.columns((4, 1))
    if action.button("Research my idea", type="primary"):
        if question.strip():
            _run(question.strip(), market_loader)
        else:
            st.info("Tell me the investment idea you would like to explore.")
    reset.button("New question", on_click=_reset)
    report = st.session_state.get("customer_report")
    if report:
        messages = (report.get("conversation_state") or {}).get("messages", [])
        original_question = messages[0]["text"] if messages else report["question"]
        original_question = original_question.split("\nUser clarification")[0].split("\nAdditional user-stated details")[0]
        if question.strip() != original_question:
            st.info("The report below belongs to the earlier question shown in Your idea, understood. Choose Research my idea to analyze your edited question.")
        render_report(report)
        st.subheader("Continue the conversation")
        if report["plan"]["question"]:
            st.write(report["plan"]["question"])
        followup = st.text_input("Add a condition, correct an assumption, or ask a follow-up", key="customer_followup", max_chars=1000)
        if st.button("Update my research") and followup.strip():
            _run(followup.strip(), market_loader, continue_conversation=True)
            st.rerun()
    with st.expander("Add details in your own words · optional"):
        st.caption("Use only the fields relevant to your question. Leave everything else blank.")
        with st.form("customer_optional_profile"):
            goal = st.text_input("What is this money for?")
            horizon = st.text_input("When might you need it?")
            withdrawal = st.text_input("Planned withdrawals: amount, currency, first date and frequency")
            willingness = st.text_input("How comfortable are you with investment losses?")
            capacity = st.text_input("What losses could you absorb given expenses, reserves, income or debts?")
            holdings = st.text_input("Current holdings and any allocation weights")
            preferences = st.text_input("Other constraints, preferences, or explanation depth")
            if st.form_submit_button("Use these details and research"):
                additions = [f"{label}: {value}" for label, value in (("Goal", goal), ("Horizon", horizon),
                    ("Withdrawal", withdrawal), ("Risk willingness", willingness), ("Loss capacity", capacity),
                    ("Current holdings", holdings), ("Preferences", preferences)) if value.strip()]
                if question.strip() and additions:
                    combined = ("Additional user-stated details:\n" if st.session_state.get("customer_state") else question.strip() + "\nAdditional user-stated details:\n") + "\n".join(additions)
                    _run(combined, market_loader, continue_conversation=bool(st.session_state.get("customer_state")))
                    st.rerun()
