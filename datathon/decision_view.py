"""The shared confirmation and report UI for all three historical decision actions."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from datetime import date
from os import environ
from pathlib import Path
from zipfile import BadZipFile

import streamlit as st

from .decision_intake import configured_decision_runtime, draft_decision
from .decision_challenge import prepare_challenge, read_finding, run_challenges
from .decision_release import (
    configured_decision_explanation_runtime, explain_report, publish_report,
    report_json, report_pdf, store_report, validate_report_inputs,
)
from .decision_workflow import ACTIONS, PRIORITIES, authorize_funding, confirm_decision, run_decision
from .model_settings import bedrock_failure_message
from .runtime_budget import run_sync_action


_LABELS = {"compare": "Compare", "evaluate": "Evaluate", "audit": "Audit"}
_UNITS = {"percentage_points": "Percentage points", "shares": "Shares", "amount_cad": "CAD amount"}
_WINDOW_LABELS = {"full_history": "Full shared history", "2022": "2022 stress", "2025": "Early 2025 stress",
                  "2023": "2023 rate scenario", "custom": "Custom window"}
BOUNDARY = "Self-assessment on historical data. Rules are yours; results are facts about those rules. Not advice, no trading."


def _presets():
    directory = Path(__file__).resolve().parents[1] / "presets"
    profiles = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
    return {profile.pop("name"): profile for profile in profiles}


def _remember_draft(draft, question, use_model):
    st.session_state.decision_draft = (draft, question, use_model)
    st.session_state.decision_revision = st.session_state.get("decision_revision", 0) + 1
    st.session_state.pop("decision_result", None)


def _compose_draft(question, use_model):
    with st.spinner("Extracting the decision and its stated rules"):
        try:
            runtime = configured_decision_runtime() if use_model else None
            draft = run_sync_action(draft_decision(question, runtime))
        except Exception as exc:
            draft = run_sync_action(draft_decision(question))
            draft["trace"] = ({"event": "agent_exception", "role": "decision_intake", "error_type": type(exc).__name__},)
        _remember_draft(draft, question, use_model)


def _reset_decision():
    for key in list(st.session_state):
        if key.startswith("decision_"):
            del st.session_state[key]


def _load_example(name, example):
    _reset_decision()
    st.session_state.decision_selected_preset = name
    st.session_state.decision_question = example["question"]
    st.session_state.decision_example = example


def _profile_changed(revision):
    for field in ("objective", "withdrawal", "risk", "esg", "finance_literacy", "method_literacy", "goal"):
        st.session_state.pop(f"decision_{field}_{revision}", None)
    st.session_state.pop("decision_result_view", None)


def _profile_editor(profile, revision):
    with st.expander("Goals, experience and reading preference", expanded=bool(profile)):
        profile["objective"] = st.text_input("Purpose of this money", profile.get("objective", ""), key=f"decision_objective_{revision}")
        profile["withdrawal_time"] = st.text_input("When might a significant withdrawal be needed?", str(profile.get("withdrawal_time") or profile.get("horizon_years") or ""), key=f"decision_withdrawal_{revision}")
        profile["risk_tolerance"] = st.text_input("Willingness to accept losses", profile.get("risk_tolerance", ""), key=f"decision_risk_{revision}")
        profile["esg_screen"] = st.checkbox("Require an environmental and social controversy screen", value=bool(profile.get("esg_screen")), key=f"decision_esg_{revision}")
        st.caption("Profiles guide the explanation. They do not create numerical limits or authorize a search.")
        for field, label in (("finance_literacy", "Financial knowledge"), ("method_literacy", "Familiarity with historical analysis")):
            levels = ("basic", "working", "expert")
            current = profile.get(field, "working")
            profile[field] = st.selectbox(label, levels, index=levels.index(current) if current in levels else 1,
                                           format_func=str.title, key=f"decision_{field}_{revision}")
        goals = ("understand_result", "compare_options", "verify_numbers")
        goal = profile.get("task_goal", "understand_result")
        profile["task_goal"] = st.selectbox("What should the report help you do?", goals, index=goals.index(goal) if goal in goals else 0,
                                           format_func=lambda value: value.replace("_", " ").title(), key=f"decision_goal_{revision}")
        profile["view"] = "metric_first" if profile["task_goal"] == "verify_numbers" else "explain_first"
    return profile


def _asset_scope(draft, market_loader):
    symbols = {asset["symbol"] for asset in draft.get("assets", ())}
    symbols.update(symbol for entry in draft.get("portfolios", ()) for symbol in entry.get("weights", {}))
    if ticker := (draft.get("trade") or {}).get("symbol"):
        symbols.add(ticker)
    if not symbols:
        return []
    try:
        market = market_loader()
    except (OSError, ValueError, BadZipFile):
        st.info("The archived data are not loaded. You can prepare and confirm a draft; historical review needs the organizer snapshot.")
        return []
    missing = sorted(symbols - market.prices.keys())
    if missing:
        st.warning(f"{', '.join(missing)} is outside this frozen dataset of {len(market.prices)} assets. "
                   "Add adjusted-close prices and a dated public source under Dates and supplementary price data to run the replay.")
    with st.expander("Covered tickers"):
        st.write(", ".join(sorted(market.prices)))
    return missing


def _weights(text):
    weights = {}
    for row in text.replace(";", "\n").replace(",", "\n").splitlines():
        row = row.strip()
        if not row:
            continue
        pieces = row.replace(":", " ").split()
        if len(pieces) != 2:
            raise ValueError("Enter each holding as a ticker followed by its allocation percentage.")
        ticker, percentage = pieces
        ticker = ticker.upper()
        if ticker in weights:
            raise ValueError("Use each ticker only once per allocation.")
        try:
            weights[ticker] = float(Decimal(percentage.removesuffix("%")) / 100)
        except InvalidOperation as exc:
            raise ValueError("Enter allocation percentages as numbers.") from exc
    return weights


def _portfolio_editor(draft, action, revision):
    result = []
    for index in range(2 if action == "compare" else 1):
        entries = draft.get("portfolios", ())
        entry = entries[index] if len(entries) > index else {}
        label = st.text_input(f"Allocation {index + 1} name", entry.get("label", f"Allocation {index + 1}"),
                              key=f"decision_label_{revision}_{index}")
        text = "\n".join(f"{ticker} {weight * 100:.12g}%" for ticker, weight in entry.get("weights", {}).items())
        holdings = st.text_area(f"Allocation {index + 1} holdings", text,
                                placeholder="TICKER 100%",
                                help="Enter a ticker and its weight in percent on each line.",
                                key=f"decision_holdings_{revision}_{index}")
        result.append((label, holdings))
    return result


def _trade_editor(draft, revision):
    details = draft.get("trade") or {}
    col1, col2 = st.columns(2)
    symbol = col1.text_input("Purchase ticker", details.get("symbol") or "", key=f"decision_target_{revision}")
    source = col2.text_input("Holding sold for the original trade", details.get("source") or "",
                             key=f"decision_original_source_{revision}")
    keys = tuple(_UNITS)
    current = details.get("unit")
    unit = col1.selectbox("Purchase unit", keys, index=keys.index(current) if current in keys else 0,
                          format_func=_UNITS.get, key=f"decision_unit_{revision}")
    quantity = col2.number_input("Purchase quantity", min_value=0.0, value=float(details.get("quantity") or 0),
                                 key=f"decision_quantity_{revision}")
    capital = None
    if unit != "percentage_points":
        capital = st.number_input("Starting portfolio value in CAD", min_value=0.0,
                                  value=float(details.get("portfolio_value_cad") or 0),
                                  key=f"decision_value_{revision}")
    return {"symbol": symbol, "source": source, "unit": unit, "quantity": quantity, "portfolio_value_cad": capital}


def _rule_editor(draft, revision):
    constraints = draft.get("constraints", ())
    limits = [{**limit, "windows": limit.get("windows") or "default"} for limit in draft.get("risk_limits", ())]
    with st.expander("Rules and evidence", expanded=bool(constraints or limits)):
        if constraints or limits:
            for item in (*constraints, *limits):
                if excerpt := item.get("excerpt"):
                    st.text(excerpt)
        st.caption("Limits are fractions of portfolio value. Recovery limits use calendar days. "
                   "Default risk windows are the named 2022 and early 2025 replays.")
        example = '{"risk_limits":[{"metric":"max_drawdown","cap":0.2,"windows":"default"}],"constraints":[]}'
        rules = st.text_area("Edit structured rules", json.dumps({"risk_limits": limits, "constraints": constraints}, indent=2),
                             key=f"decision_rules_{revision}", placeholder=example, height=145)
        st.caption("Use asset_set with symbols, asset_class, sector, issuer, or exclusion_list, and specify min or max.")
    return rules


def _scope_editor(revision, *, expanded=False):
    with st.expander("Dates and supplementary price data", expanded=expanded):
        knowledge_date = st.date_input("Knowledge date", value=None, key=f"decision_knowledge_{revision}",
                                       help="Leave blank to use the organizer snapshot availability date.")
        optional = st.checkbox("Include the optional 2023 replay", key=f"decision_optional_{revision}")
        day1, day2 = st.columns(2)
        start = day1.date_input("Custom window start", value=None, key=f"decision_start_{revision}")
        end = day2.date_input("Custom window end", value=None, key=f"decision_end_{revision}")
        file = st.file_uploader("Supplementary adjusted-close prices", type="csv", key=f"decision_upload_{revision}",
                                help="CSV columns: ticker, date, adj_close, currency. Use a dated public source.")
        source = published = None
        if file is not None:
            source = st.text_input("Public price source URL", key=f"decision_upload_source_{revision}")
            published = st.date_input("Price source publication date", value=None,
                                      key=f"decision_upload_published_{revision}")
    upload = file.getvalue() if file is not None else None
    scope = {"include_2023": optional}
    for field, value in (("knowledge_date", knowledge_date), ("custom_start", start), ("custom_end", end),
                         ("upload_published_on", published)):
        if value is not None:
            scope[field] = value.isoformat()
    if upload is not None:
        scope["upload_sha256"] = hashlib.sha256(upload).hexdigest()
        scope["upload_source"] = source
    return scope, upload


def _submit(draft, portfolio_entries, scope, raw_rules, *, priority, ranking_window, action, trade, profile, capital=None):
    rules = json.loads(raw_rules)
    if not isinstance(rules, dict) or set(rules) != {"risk_limits", "constraints"} or any(
            not isinstance(value, list) or any(not isinstance(rule, dict) for rule in value) for value in rules.values()):
        raise ValueError("Provide a list of exposure rules and a list of risk limits.")
    unresolved = set(draft.get("missing", ())) & {"risk_limit", "binding_scope"}
    if rules["risk_limits"]:
        unresolved.discard("risk_limit")
    if unresolved:
        raise ValueError("Resolve the binding rule in the question before confirming. Use the clarification above.")
    supplied = {"intent": action, "portfolios": [{"label": label, "weights": _weights(holdings)}
                                               for label, holdings in portfolio_entries],
                "priority": priority, "ranking_window": ranking_window, "trade": trade, "profile": profile,
                "trace": draft.get("trace", ()),
                "origin": draft.get("origin", "user_defined"),
                "assumption_kind": draft.get("assumption_kind", "user_defined"), **rules}
    supplied["capital"] = capital
    return confirm_decision(supplied, scope=scope)


def _format(value, unit="fraction"):
    if value is None:
        return "Unknown"
    if unit == "days":
        return f"{value:g} days"
    return f"{value:.2%}"


def _explain(report):
    explanation = report.get("explanation") or {}
    template = explanation.get("template") or [explanation.get("summary", ""), *explanation.get("findings", ())]
    narrative = explanation.get("narrative") or {}
    if narrative.get("status") == "released" and narrative.get("text"):
        st.write(narrative["text"])
    elif narrative.get("status") == "withdrawn":
        st.info("The model's narrative was withdrawn by verification. The checked explanation remains available.")
        if narrative.get("reason"):
            st.caption("Verification reason: " + narrative["reason"].replace("_", " ") + ".")
    if isinstance(template, str):
        st.write(template)
    elif isinstance(template, (tuple, list)):
        for line in template:
            if line:
                st.write(line.get("text", line) if isinstance(line, dict) else line)


def _explanation_activity(report):
    explanation = report.get("explanation") or {}
    activity = {key: explanation.get(key) for key in ("status", "mode", "model_version", "reason", "trace")}
    narrative = explanation.get("narrative") or {}
    activity["narrative"] = {key: narrative[key] for key in ("status", "reason", "verification", "references")
                             if key in narrative}
    return activity


def _questions(report, confirmed, market_loader, upload):
    questions = {
        "why_fail": "Why did a rule fail?",
        "funding_difference": "Why does another funding source differ?",
        "purchase_quantity": "What if the purchase were smaller?",
        "rule_change": "What would change this rule's result?",
        "uncertain": "What remains uncertain?",
    }
    with st.expander("Ask about this result"):
        question = st.selectbox("Question about the checked result", tuple(questions),
                                format_func=questions.get, key="decision_followup_question")
        if question in {"why_fail", "funding_difference", "uncertain"}:
            answer = read_finding(report, question)
            if answer.get("message"):
                st.write(answer["message"])
            if answer.get("rules"):
                st.dataframe(answer["rules"], hide_index=True)
            for gap in answer.get("gaps", ()):
                st.write(gap)
            if answer.get("funding"):
                st.json(answer["funding"], expanded=False)
            return
        data = confirmed.data
        field, value, index = None, None, 0
        if question == "purchase_quantity":
            if data["intent"] != "audit":
                st.info("A purchase-size question needs an original trade audit.")
                return
            field = "purchase_quantity"
            value = st.number_input("Hypothetical smaller purchase", min_value=0.0,
                                    value=float(data["trade"]["quantity"]) / 2, key="decision_challenge_quantity")
            st.caption(f"Unit: {_UNITS[data['trade']['unit']]}. The funding source and other rules stay fixed.")
        else:
            fields = []
            if data["risk_limits"]:
                fields.extend(("risk_metric", "risk_cap"))
            if any(row.get("min") is not None for row in data["constraints"]):
                fields.append("holding_minimum")
            if not fields:
                st.info("This report has no supported numerical rule to vary. Start a new confirmed question to add one.")
                return
            labels = {"risk_metric": "Risk definition", "risk_cap": "Risk limit", "holding_minimum": "Minimum holding"}
            field = st.selectbox("One assumption to vary", fields, format_func=labels.get, key="decision_challenge_field")
            source = data["constraints"] if field == "holding_minimum" else data["risk_limits"]
            indices = [i for i, item in enumerate(source) if field != "holding_minimum" or item.get("min") is not None]
            index = st.selectbox("Rule to vary", indices, format_func=lambda i: json.dumps(source[i], ensure_ascii=False), key=f"decision_challenge_index_{field}")
            if field == "risk_metric":
                choices = tuple(metric for metric in ("terminal_loss", "max_drawdown", "worst_rolling_12m") if metric != source[index]["metric"])
                value = st.selectbox("Hypothetical risk definition", choices, format_func=lambda s: s.replace("_", " ").title(), key="decision_challenge_metric")
            else:
                current = source[index]["min" if field == "holding_minimum" else "cap"]
                days = field == "risk_cap" and source[index]["metric"] == "recovery_days"
                value = st.number_input("Hypothetical limit (days)" if days else "Hypothetical limit (%)",
                                        min_value=0.0, value=float(current if days else current * 100),
                                        key=f"decision_challenge_limit_{field}_{index}")
                value = value if days else value / 100
        try:
            proposal = prepare_challenge(confirmed, field=field, value=value, rule_index=index)
        except ValueError as exc:
            st.info(str(exc))
            return
        st.json(proposal.change)
        st.caption("This is a separately confirmed hypothetical check. It preserves the original result and grants no funding-search permission.")
        history = [item for item in st.session_state.get("decision_challenge_history", []) if item[0] == confirmed.id]
        stopped = len(history) >= 3 or any(item[2]["stopped_reason"] in {"verdict_changed", "independent_review_withheld"} for item in history)
        repeated = any(item[1] == proposal.change for item in history)
        if stopped:
            st.info("The challenge sequence has stopped: its verdict changed, independent review withheld a result, or three checks were completed.")
        if st.button("Confirm and run this hypothetical check", disabled=stopped or repeated):
            try:
                with st.spinner("Checking one changed assumption"):
                    result = run_challenges(confirmed, report, market_loader(), [proposal], acknowledged=True, upload=upload)
                st.session_state.decision_challenge_result = (confirmed.id, proposal.change, result)
                st.session_state.decision_challenge_history = [*history, (confirmed.id, proposal.change, result)]
            except (ValueError, OSError, BadZipFile) as exc:
                st.error(str(exc))
        saved = st.session_state.get("decision_challenge_result")
        if saved and saved[:2] == (confirmed.id, proposal.change):
            step = saved[2]["steps"][-1]
            st.write(f"Original: {step['before']['verdict']} · Hypothetical: {step['after']['verdict']}")
            _explain(step["report"])
            st.download_button("Download hypothetical JSON", report_json(step["report"]), "alphaforge-hypothetical.json", "application/json")


def _charts(report):
    options = report.get("options", {})
    windows = sorted({window for option in options.values() for window, record in option["windows"].items()
                      if record.get("observed_path")})
    if not windows:
        return
    with st.expander("Historical value and drawdown paths", expanded=True):
        window = st.selectbox("Value-path window", windows,
                              index=windows.index("full_history") if "full_history" in windows else 0,
                              format_func=lambda name: _WINDOW_LABELS.get(name, name), key="decision_chart_window")
        values = [{"Date": date.fromisoformat(point["date"]), "Value": point["value"], "Candidate": label}
                  for label, option in options.items() for point in option["windows"].get(window, {}).get("observed_path", ())]
        st.caption("CAD portfolio value normalized to 1 at the first observation. Each line is independently checked.")
        st.line_chart(values, x="Date", y="Value", color="Candidate", height=240)
        drawdowns = [{"Date": date.fromisoformat(point["date"]), "Drawdown": point["drawdown"], "Candidate": label}
                     for label, option in options.items() for point in option["windows"].get("full_history", {}).get("observed_path", ())]
        if drawdowns:
            st.caption("Full shared-history drawdown, shown as a positive fraction below the previous peak.")
            st.line_chart(drawdowns, x="Date", y="Drawdown", color="Candidate", height=220)
            for label, option in options.items():
                record = option["windows"].get("full_history", {})
                if record.get("recovery_date"):
                    st.caption(f"{label}: the maximum-drawdown peak was regained on {record['recovery_date']}.")
                elif record.get("recovery_status"):
                    st.caption(f"{label}: {record['recovery_status'].replace('_', ' ')} as of {record.get('end_date', 'the final observation')}.")


def _report(report, confirmed, market_loader, upload, use_model):
    try:
        validate_report_inputs(report, confirmed)
    except (ValueError, TypeError):
        st.error("Independent verification withheld this report because its checked inputs or results changed.")
        return
    if report["publication"]["status"] != "released":
        st.error("Independent verification withheld this report.")
        return
    st.subheader("Reviewed decision")
    st.caption(BOUNDARY)
    profile = confirmed.data.get("profile", {})
    if profile:
        st.caption(" · ".join(str(profile.get(field, "")) for field in ("preset", "objective", "withdrawal_time", "risk_tolerance") if profile.get(field)))
    verdict = report.get("verdict", "unknown").replace("_", " ").title()
    st.write(f"**Rule disposition** · {verdict}")
    view = st.radio("Report view", ("Explanation first", "Metrics first"), horizontal=True,
                     index=int(profile.get("view") == "metric_first"), key="decision_result_view")
    if view == "Explanation first":
        _explain(report)
    rows = []
    for label, option in report.get("options", {}).items():
        for window, record in option["windows"].items():
            rows.append({"Candidate": label, "Window": _WINDOW_LABELS.get(window, window),
                         "Terminal return": _format(record["terminal_return"]),
                         "Terminal loss": _format(record["terminal_loss"]),
                         "Max drawdown": _format(record["max_drawdown"]),
                         "Recovery": _format(record.get("recovery_days"), "days"),
                         "Coverage": record["coverage_status"].replace("_", " ")})
    if rows:
        st.dataframe(rows, hide_index=True)
    amount_rows = []
    for label, option in report.get("options", {}).items():
        for window, record in option["windows"].items():
            if "terminal_loss_amount" in record:
                amount_rows.append({"Candidate": label, "Window": _WINDOW_LABELS.get(window, window),
                                    "Terminal loss (CAD)": record["terminal_loss_amount"],
                                    "Drawdown peak (CAD)": record.get("drawdown_peak_amount"),
                                    "Peak-to-trough loss (CAD)": record.get("drawdown_loss_amount")})
    if amount_rows:
        st.dataframe(amount_rows, hide_index=True)
    if profile.get("finance_literacy") == "basic":
        st.caption("Terminal loss compares the start and end. Maximum drawdown is the largest fall from an earlier peak. "
                   "Recovery is the time from that peak until its value is reached again; unknown does not mean zero.")
    if profile.get("method_literacy") == "basic":
        st.caption("This replay holds the starting allocation without rebalancing. It describes observed paths and does not forecast future losses.")
    if view == "Metrics first":
        _explain(report)
    _charts(report)
    if rank := report.get("ranking"):
        if rank.get("order"):
            st.write("**Reviewed ranking** · " + " → ".join(item["candidate"] for item in rank["order"]))
        else:
            st.info(rank.get("reason") or "The available evidence does not support a ranking under the confirmed rules.")
    for tension in report.get("profile_tensions", ()):
        st.warning(tension)
    if report.get("rules"):
        with st.expander("Rules, margins and evidence", expanded=True):
            st.dataframe([{"Candidate": row["candidate"], "Rule": row["label"], "Window": row.get("window", ""),
                           "Disposition": row["status"].title(),
                           "Limit": _format(row.get("limit"), row.get("unit")),
                           "Margin": _format(row.get("headroom"), row.get("unit"))}
                          for row in report["rules"]], hide_index=True)
    if report.get("gaps"):
        with st.expander("What remains uncertain"):
            for item in report["gaps"]:
                st.write(item)
    if capital := report.get("capital"):
        st.caption(f"Confirmed starting value: {capital['currency']} {capital['value']:,.2f}. "
                   "Percentage-point amounts use this starting value; drawdown amounts use the relevant peak value.")
    if exposures := report.get("exposure"):
        with st.expander("Look-through exposure and screening evidence"):
            st.caption("Disclosed holdings, mandate bounds and unassessed weights remain separate. "
                       "A controversy-list screen is not an ESG rating.")
            st.json(exposures, expanded=False)
    with st.expander("Independent review, metrics and sources"):
        st.json({**{key: report.get(key) for key in ("review", "metric_records", "provenance", "governance", "trace")},
                 "explanation": _explanation_activity(report)}, expanded=False)
    if report.get("funding") is not None:
        with st.expander("Authorized funding analysis", expanded=True):
            result = report["funding"]
            st.write(f"**Funding result** · {result['status'].replace('_', ' ')}")
            if result.get("source_bounds"):
                st.dataframe([{"Source": ticker, "Minimum": _format(bounds["min"]), "Maximum": _format(bounds["max"])}
                              for ticker, bounds in result["source_bounds"].items()], hide_index=True)
            for item in result.get("reasons", ()):
                st.write(item)
            st.json(result, expanded=False)
    _questions(report, confirmed, market_loader, upload)

    downloads = st.columns(3)
    downloads[0].download_button("Download JSON", report_json(report), "alphaforge-decision.json", "application/json")
    downloads[1].download_button("Explanation PDF", report_pdf(report, view="investor"),
                                 "alphaforge-explanation.pdf", "application/pdf")
    downloads[2].download_button("Metrics PDF", report_pdf(report, view="audit"),
                                 "alphaforge-metrics.pdf", "application/pdf")
    if bucket := environ.get("DATATHON_AUDIT_BUCKET"):
        if st.button("Save reviewed record to AWS"):
            try:
                st.session_state.decision_storage = (confirmed.id, store_report(report, bucket=bucket))
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
        saved = st.session_state.get("decision_storage")
        if saved and saved[0] == confirmed.id:
            st.json(saved[1])

    if confirmed.data["intent"] == "audit":
        with st.expander("Authorize alternative funding"):
            portfolio = confirmed.data["portfolios"][0]["weights"]
            trade = confirmed.data["trade"]
            choices = [ticker for ticker in sorted(portfolio) if ticker != trade["symbol"]]
            sources = st.multiselect("Funding sources allowed for this search", choices, key="decision_search_sources")
            smaller = st.checkbox("Allow a smaller purchase if the full size is infeasible", key="decision_smaller")
            if st.button("Confirm and search authorized sources", disabled=not sources):
                try:
                    auth = authorize_funding(confirmed, sources=sources, allow_smaller=smaller)
                    _execute(confirmed, market_loader, upload, use_model, funding=auth)
                    st.rerun()
                except (ValueError, OSError, BadZipFile) as exc:
                    st.error(str(exc))


def _execute(confirmed, market_loader, upload, use_model, *, funding=None):
    with st.spinner("Replaying the confirmed windows and independently checking the results"):
        snapshot = run_decision(confirmed, market_loader(), upload=upload, funding=funding)
        report = publish_report(snapshot)
        if report["publication"]["status"] == "released" and use_model:
            try:
                report = run_sync_action(explain_report(report, configured_decision_explanation_runtime()))
            except Exception:
                st.info("Amazon Bedrock is unavailable for the explanation. Your independently checked historical result is retained.")
    st.session_state.decision_result = (confirmed.id, report)
    st.session_state.pop("decision_storage", None)


def render_decisions(market_loader):
    st.header("What decision would you like to review?")
    st.caption("Compare two allocations, evaluate one, or audit a simulated trade.")
    st.caption(BOUNDARY)
    st.button("Start a new question", on_click=_reset_decision)
    profiles = _presets()
    buttons = st.columns(len(profiles))
    for column, (name, profile) in zip(buttons, profiles.items()):
        if example := profile.get("example"):
            column.button(f"Try {name}'s question", on_click=_load_example, args=(name, example))
    question = st.text_area("Describe your decision", key="decision_question",
                            placeholder="Compare GLD and AGG. I care most about maximum drawdown.")
    st.caption("English and French questions are accepted. The interface and reports remain in English.")
    left, right = st.columns(2)
    if left.button("Draft with Amazon Bedrock", type="primary", disabled=not question.strip()):
        _compose_draft(question.strip(), True)
    if right.button("Draft offline", disabled=not question.strip()):
        _compose_draft(question.strip(), False)

    saved = st.session_state.get("decision_draft")
    missing_prices = []
    if saved and (question.strip() == saved[1] or question.strip() == saved[1].split("\nClarification: ", 1)[0]):
        draft, source_question, use_model = saved
        origin = draft.get("origin")
        st.caption("Amazon Bedrock draft" if origin == "bedrock" else "Offline draft")
        if use_model and origin != "bedrock":
            trace = draft.get("trace", ())
            if any(event.get("event") == "validation_error" for event in trace):
                st.info("The Bedrock draft did not pass input checks. Review the offline draft below.")
            else:
                st.info(bedrock_failure_message(trace))
        if draft.get("clarification"):
            st.info(draft["clarification"])
            answer = st.text_input("Answer this question", key=f"decision_clarification_{st.session_state.decision_revision}")
            if st.button("Update draft", disabled=not answer.strip()):
                _compose_draft(f"{source_question}\nClarification: {answer.strip()}", use_model)
                st.rerun()
        if draft.get("intent") == "out_of_scope":
            return
        if draft.get("reference_scope"):
            st.info(draft["reference_scope"])
        missing_prices = _asset_scope(draft, market_loader)
        if draft.get("sources"):
            with st.expander("Original words used in this draft"):
                for excerpt in draft["sources"].values():
                    st.text(excerpt)
        if draft.get("trace"):
            with st.expander("Question interpretation activity"):
                st.json(draft["trace"], expanded=False)
    elif question.strip():
        return
    else:
        draft, use_model = {}, False

    revision = st.session_state.get("decision_revision", 0)
    suggested = draft.get("intent")
    action = st.selectbox("Decision type", ACTIONS, index=ACTIONS.index(suggested) if suggested in ACTIONS else None,
                          placeholder="Choose Compare, Evaluate, or Audit", format_func=_LABELS.get,
                          key=f"decision_action_{revision}")
    if action is None:
        return
    st.subheader("Review and confirm inputs")
    names = tuple(profiles)
    selected_preset = st.session_state.get("decision_selected_preset")
    profile_name = st.selectbox("Fictional profile preset", names, index=names.index(selected_preset) if selected_preset in names else None,
                                 placeholder="Use the stated profile", key=f"decision_profile_{revision}",
                                 on_change=_profile_changed, args=(revision,))
    profile = ({"preset": profile_name, **{key: value for key, value in profiles[profile_name].items() if key != "example"}} if profile_name else {})
    profile.update(draft.get("profile") or {})
    profile = _profile_editor(profile, revision)
    example = st.session_state.get("decision_example", {})
    if example:
        st.caption("This question and its numerical example rules are team-defined assumptions, not rules supplied by the official persona.")
        draft = {**draft, "assumption_kind": "team_defined"}
    if action == "audit" and not draft.get("portfolios") and example.get("portfolio"):
        st.info("The starting weights below are a team-defined fictional example. Edit them before confirming.")
        draft = {**draft, "portfolios": [{"label": "Fictional starting allocation", "weights": example["portfolio"]}]}
    portfolio_entries = _portfolio_editor(draft, action, revision)
    trade = _trade_editor(draft, revision) if action == "audit" else None
    priority = ranking_window = None
    if action == "compare":
        choices = tuple(PRIORITIES)
        preferred = draft.get("priority")
        priority = st.selectbox("Ranking priority", choices, index=choices.index(preferred) if preferred in choices else None,
                                placeholder="Compare metrics without a ranking", format_func=PRIORITIES.get,
                                key=f"decision_priority_{revision}")
        if priority:
            ranking_window = st.selectbox("Ranking window", tuple(_WINDOW_LABELS), index=1,
                                          format_func=_WINDOW_LABELS.get, key=f"decision_rank_window_{revision}")
    raw_rules = _rule_editor(draft, revision)
    stated_capital = (draft.get("capital") or {}) if action == "evaluate" else {}
    currency = stated_capital.get("currency")
    starting_value = float(stated_capital["value"]) if currency == "CAD" else 0.0
    if currency and currency != "CAD":
        st.caption(f"The proposed amount is {currency} {stated_capital['value']:,.2f}. Enter its CAD equivalent for dollar results.")
    balance = st.number_input("Starting portfolio value in CAD (optional)", min_value=0.0, value=starting_value,
                              help="Use the starting value of the allocation under review. Leave zero for percentage-only analysis.",
                              key=f"decision_capital_{revision}")
    capital = {"value": balance, "currency": "CAD"} if balance else None
    if trade and trade["unit"] != "percentage_points" and balance:
        trade["portfolio_value_cad"] = balance
    scope, upload = _scope_editor(revision, expanded=bool(missing_prices))
    approved = st.checkbox("I checked the inputs and all binding rules for this fictional decision.",
                            key=f"decision_approved_{revision}")
    try:
        confirmed = _submit(draft, portfolio_entries, scope, raw_rules, priority=priority, ranking_window=ranking_window,
                            action=action, trade=trade, profile=profile, capital=capital)
    except (ValueError, AttributeError, TypeError) as exc:
        confirmed = None
        if approved:
            st.warning(str(exc))
    if st.button("Confirm and run historical review", type="primary", disabled=not (approved and confirmed)):
        try:
            _execute(confirmed, market_loader, upload, use_model)
        except (OSError, ValueError, TypeError, BadZipFile) as exc:
            st.session_state.pop("decision_result", None)
            st.error(str(exc))
    saved_report = st.session_state.get("decision_result")
    if approved and confirmed and saved_report and saved_report[0] == confirmed.id:
        _report(saved_report[1], confirmed, market_loader, upload, use_model)
