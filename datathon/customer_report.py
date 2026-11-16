"""Deterministic calculations, independent review and readable research evidence."""

from datetime import date
from fractions import Fraction
from html import escape
from math import fsum, isclose, sqrt
import re
from statistics import stdev

from .review_snapshot import fingerprint
from .decision_replay import evaluate as evaluate_history, verify as verify_history


METHOD = "customer-inquiry-v4"


def calculate(rows):
    """Reuse the established replay engine; names here are display aliases."""
    metrics = evaluate_history({"asset": 1.0}, [row["date"] for row in rows], {"asset": [row["price"] for row in rows]})
    return {"return": metrics["terminal_return"], "drawdown": metrics["max_drawdown"],
            "volatility": metrics["annualized_volatility"],
            "path": [{"date": point["date"], "index": point["value"] * 100, "drawdown": -point["drawdown"] * 100}
                     for point in metrics["observed_path"]],
            "start": metrics["start_date"], "end": metrics["end_date"], "observations": metrics["observations"], "extended": metrics}


def review(rows, metrics):
    """Reuse the independent Decimal-based engine and check every display alias."""
    if len(rows) < 20:
        return False
    equal = lambda left, right: isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)
    try:
        checked = verify_history({"asset": 1.0}, [row["date"] for row in rows], {"asset": [row["price"] for row in rows]}, metrics["extended"])
        if not (equal(metrics["return"], checked["terminal_return"]) and equal(metrics["drawdown"], checked["max_drawdown"])
                and equal(metrics["volatility"], checked["annualized_volatility"]) and metrics["start"] == rows[0]["date"]
                and metrics["end"] == rows[-1]["date"] and metrics["observations"] == len(rows)
                and len(metrics["path"]) == len(rows)):
            return False
        for reference, point in zip(checked["observed_path"], metrics["path"]):
            if (point["date"] != reference["date"] or not equal(point["index"], reference["value"] * 100)
                    or not equal(point["drawdown"], -reference["drawdown"] * 100)):
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _valuation(asset, budget, fx):
    if not budget or budget["currency"] not in {"CAD", "USD"}:
        return None
    if asset.get("price_field") == "adj_close":
        # Adjusted historical values cannot establish a share purchase price.
        return None
    currency = budget["currency"]
    rate, fx_date = 1.0, None
    if asset["currency"] != currency:
        if not fx or {asset["currency"], currency} != {"CAD", "USD"}:
            return None
        latest = fx["rows"][-1]
        # Old FX must not masquerade as a current purchase-cost observation.
        from datetime import date, datetime
        if (datetime.fromisoformat(asset["retrieved_at"]).date() - date.fromisoformat(latest["date"])).days > 7:
            return None
        rate = latest["rate"] if currency == "CAD" else 1 / latest["rate"]
        fx_date = latest["date"]
    converted = asset["price"] * rate
    whole = int(budget["amount"] // converted)
    remainder = budget["amount"] - whole * converted
    if not (whole * Fraction(str(converted)) <= Fraction(str(budget["amount"]))
            and (whole + 1) * Fraction(str(converted)) > Fraction(str(budget["amount"]))):
        raise ValueError("Purchase-size review failed.")
    return {"currency": currency, "price": converted, "whole_shares": whole, "remaining_cash": remainder,
            "budget": budget["amount"], "fx_rate": rate, "fx_date": fx_date}


def analyze(assets, budget, fx=None, calculator=calculate, *, target_currency=None):
    """Align all reported comparisons on common observed dates and a stated basis."""
    if not assets:
        return []
    target = budget["currency"] if budget and budget["currency"] in {"CAD", "USD"} else target_currency
    fx_by_date = {row["date"]: row["rate"] for row in fx["rows"]} if fx else {}
    prepared = []
    for asset in assets:
        rows = asset["rows"]
        basis = asset["currency"]
        missing_fx = 0
        if target and target != basis and {target, basis} == {"CAD", "USD"} and fx:
            converted = []
            for row in rows:
                if row["date"] not in fx_by_date:
                    missing_fx += 1
                    continue
                rate = fx_by_date[row["date"]]
                converted.append({"date": row["date"], "price": row["price"] * (rate if target == "CAD" else 1 / rate)})
            rows, basis = converted, target
        prepared.append({"asset": asset, "rows": rows, "basis": basis, "missing_fx": missing_fx})
    common = set.intersection(*(set(row["date"] for row in item["rows"]) for item in prepared))
    if len(common) < 20:
        raise ValueError("There are fewer than twenty common observations. A comparable historical report is unavailable.")
    result = []
    for item in prepared:
        rows = [row for row in item["rows"] if row["date"] in common]
        metrics = calculator(rows)
        if not review(rows, metrics):
            raise ValueError("The independent calculation check failed. No financial report was released.")
        result.append({**item, "rows": rows, "metrics": metrics,
                       "alignment_omissions": len(item["rows"]) - len(rows),
                       "valuation": _valuation(item["asset"], budget, fx), "review": "passed"})
    return result


def evidence_blocks(plan, analyses, errors):
    """Build substantive approved claims; model selects relevance, never figures."""
    blocks = {}
    required = None
    for item in analyses:
        asset, metric = item["asset"], item["metrics"]
        symbol, basis = asset["symbol"], item["basis"]
        blocks[f"{symbol}.behavior"] = {
            "title": f"What the history says about {symbol}",
            "text": f"Over {metric['start']} to {metric['end']}, {symbol}'s adjusted-price series changed by "
                    f"{metric['return']:+.2%} in {basis}. Its largest observed fall from a previous high was "
                    f"{metric['drawdown']:.2%}. These describe different risks: finishing ahead does not mean the journey avoided large losses.",
            "sources": [asset["source_url"]],
        }
        if item["valuation"]:
            value = item["valuation"]
            scope = "Used entirely for this one asset" if len(analyses) == 1 else "If the full amount were used for this asset alone"
            blocks[f"{symbol}.budget"] = {
                "title": f"What your amount represents in {symbol}",
                "text": f"{scope}, {value['currency']} {value['budget']:,.2f} corresponds to approximately "
                        f"{value['whole_shares']:,} whole shares at the observed price, leaving "
                        f"{value['currency']} {value['remaining_cash']:,.2f} before fees and currency spreads. "
                        "This is an indicative sizing calculation, not an order or a forecast. "
                        "This current-price whole-share estimate is separate from the historical replay, which invests the full stated amount in fractional units at its starting date. "
                        + (f"It uses the Bank of Canada daily exchange rate dated {value['fx_date']}; "
                           "the FX and equity observations are not simultaneous." if value["fx_date"] else ""),
                "sources": [asset["source_url"]] + (["https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/"] if value["fx_date"] else []),
            }
        if asset["price_age_days"] > 4:
            key = f"{symbol}.stale"
            blocks[key] = {"title": "The latest observation is old",
                           "text": f"The available {symbol} observation is dated {asset['price_as_of'][:10]}. "
                                   "It is too old to describe as a current market quote. Refresh the source before relying on the purchase-size estimate.",
                           "sources": [asset["source_url"]]}
            required = key

    conditions = plan["conditions"]
    if any(item["kind"] in {"loss", "capacity"} for item in conditions):
        loss_text = " ".join(item["excerpt"] for item in conditions if item["kind"] in {"loss", "capacity"})
        tolerances = re.findall(r"(?:cannot|can't|can’t)\s+(?:afford\s+to\s+)?lose\s+(?:more than\s+)?([0-9]+(?:\.[0-9]+)?)\s*%", loss_text, re.I)
        comparison = ""
        if len(tolerances) == 1 and 0 < float(tolerances[0]) <= 100:
            tolerance = float(tolerances[0]) / 100
            larger = [item for item in analyses if item["metrics"]["drawdown"] > tolerance]
            if larger:
                example = max(larger, key=lambda item: item["metrics"]["drawdown"])
                comparison = (f"You said you could not afford to lose more than {tolerance:.0%}. "
                              f"{example['asset']['symbol']} fell {example['metrics']['drawdown']:.2%} from a previous high in this sample. "
                              "That is a material tension with your stated loss capacity. A peak-based fall and a loss from your purchase price "
                              "use different starting points, so this comparison is a warning, not a formal limit test. ")
        blocks["risk_context"] = {
            "title": "Your concern about losses changes the question",
            "text": comparison + "Compare the observed peak-to-trough falls with the loss you could absorb without selling. "
                    "The worst fall in this sample is not a ceiling on future losses. A tolerance stated in everyday language "
                    "does not establish a formal portfolio risk limit, and no such limit has been certified here.", "sources": []}
        required = required or "risk_context"
    if any(item["kind"] in {"horizon", "liquidity"} for item in conditions):
        blocks["time_context"] = {
            "title": "When you need the money matters",
            "text": "A withdrawal during a decline can turn a temporary fall into a realized loss. The trailing sample "
                    "does not establish that the investment will recover before your stated withdrawal date. "
                    "Keep money required for near-term spending separate when assessing this idea.", "sources": []}
        horizon = " ".join(item["excerpt"] for item in conditions if item["kind"] in {"horizon", "liquidity"})
        months = re.findall(r"\b([0-9]+)\s+months?\b", horizon, re.I)
        if len(months) == 1 and 0 < int(months[0]) <= 12:
            blocks["time_context"]["text"] = (f"You expect to need this money in {int(months[0])} months. "
                "This leaves limited time to wait through a market decline. " + blocks["time_context"]["text"])
            required = required or "time_context"
    if any(item["kind"] in {"preference", "esg", "exclusion"} for item in conditions):
        blocks["preference_gap"] = {
            "title": "Your stated preferences still need evidence",
            "text": "Price history cannot verify environmental or social controversies, business quality, fund holdings, "
                    "or other non-price preferences. No issuer screening or preference-compliance verdict has been established by this report.", "sources": []}
        required = required or "preference_gap"
    if any(item["role"] in {"holding", "funding"} for item in plan["assets"]) or any(
            item["kind"] in {"portfolio", "funding"} for item in conditions):
        blocks["portfolio_gap"] = {
            "title": "Your existing portfolio has not been combined with this idea",
            "text": "The charts assess each researched asset separately. Existing holdings, any proposed sale, taxes, "
                    "cash needs and allocation weights have not been combined into a before-and-after portfolio. "
                    "The full stated amount is used only as an illustration for each asset, not allocated repeatedly.", "sources": []}
        required = required or "portfolio_gap"
    blocks["conclusion"] = {
        "title": "What can be concluded now",
        "text": "This research establishes how the named investment behaved in the observed sample and, when prices and "
                "currency data allow, what the stated amount represents. It does not establish whether today's price is "
                "cheap, whether future returns will meet your goal, or whether the idea fits your whole financial position. "
                "Those conclusions need business and valuation evidence together with your time horizon, liquidity needs and loss capacity.",
        "sources": []}
    if errors:
        blocks["data_gap"] = {"title": "Part of the requested evidence is missing",
                              "text": "The report covers only the instruments and currencies with usable observations. "
                                      "The missing evidence below prevents a complete comparison or conversion.", "sources": []}
        required = "data_gap"
    return blocks, required


def report_markdown(report):
    plan, analyses = report["plan"], report["analyses"]
    lines = ["# Investment research report", "", report["question"], "",
             "Simulation and research · dated observations, not future-return estimates.", ""]
    if report["editor"].get("answer_status") in {"partial", "evidence_only"}:
        lines += ["**Part of this question could not be answered yet. The findings below are the parts that were checked; open points are listed with the reason.**", ""]
    if analyses:
        for section in report["editor"].get("explanations", []):
            lines += [f"## {section['heading']}", "", section["text"], "",
                      "Evidence: " + "; ".join(report["blocks"][key]["title"] for key in section["evidence_ids"]), ""]
        for key in dict.fromkeys([report["editor"]["takeaway"], *report["editor"]["order"]]):
            block = report["blocks"][key]
            lines += [f"## {block['title']}", "", block["text"], ""]
        lines += ["## Market evidence", "", "| Asset | Latest observation | Historical change | Largest observed fall | Currency |",
                  "| --- | --- | --- | --- | --- |"]
        for item in analyses:
            asset, metric = item["asset"], item["metrics"]
            lines.append(f"| {asset['symbol']} | {asset['currency']} {asset['price']:.2f} at {asset['price_as_of']} | "
                         f"{metric['return']:+.2%} | {metric['drawdown']:.2%} | {item['basis']} |")
        lines += ["", "## Method and limits", "", methodology(report), "", "## Sources", ""]
        for item in analyses:
            asset = item["asset"]
            lines += [f"- [{asset['symbol']} · {asset['source']}]({asset['source_url']}); retrieved {asset['retrieved_at']}."]
        if report.get("fx"):
            lines += [f"- [Bank of Canada FXUSDCAD]({report['fx']['source_url']}); retrieved {report['fx']['retrieved_at']}."]
    if report.get("tasks"):
        lines += ["", "## Task completion and remaining evidence", ""]
        for task in report["tasks"]:
            lines += [f"- {task['question']} — {task['status']}. {task['remaining_gap']}"]
    if report["editor"].get("arguments"):
        lines += ["", "## Argument support", "", "Semantic review is fallible; a supported label is not a correctness guarantee.", ""]
        for row in report["editor"]["arguments"]:
            lines += [f"- {row['id']} ({row['kind']}): {row['relevance']} Evidence: {', '.join(row['evidence_ids'])}.",
                      "  Assumptions: " + ("; ".join(row["assumptions"]) or "None asserted."),
                      "  Limits: " + ("; ".join(row["limitations"]) or "See the cited evidence scope.")]
    for error in report["errors"]:
        lines += ["", f"Missing evidence: {error}"]
    lines += ["", "## What would improve the answer", "", plan["question"] or "Add your withdrawal date, loss capacity and existing holdings."]
    return "\n".join(lines)


def _svg(analyses, field, label):
    colors = ["#155e4c", "#b56c21", "#3b68a2"]
    values = [point[field] for item in analyses for point in item["metrics"]["path"]]
    low, high = min(values), max(values)
    span = high - low or 1
    days = [date.fromisoformat(point["date"]).toordinal() for item in analyses for point in item["metrics"]["path"]]
    first_day, last_day = min(days), max(days)
    parts = [f'<svg viewBox="0 0 720 300" role="img" aria-label="{escape(label)}">',
             '<rect width="720" height="300" fill="#f5f8f6"/>']
    for step in range(5):
        value = low + span * step / 4
        y = 245 - 200 * step / 4
        parts += [f'<line x1="65" y1="{y}" x2="695" y2="{y}" stroke="#dbe4df"/>',
                  f'<text x="55" y="{y + 4}" text-anchor="end" font-size="12">{value:.1f}</text>']
    for index, item in enumerate(analyses):
        path = item["metrics"]["path"]
        points = " ".join(f"{65 + 630 * (date.fromisoformat(point['date']).toordinal() - first_day) / max(1, last_day - first_day):.2f},{245 - (point[field] - low) / span * 200:.2f}"
                          for number, point in enumerate(path))
        parts += [f'<polyline fill="none" stroke="{colors[index % 3]}" stroke-width="2.5" points="{points}"/>',
                  f'<text x="{65 + index * 200}" y="20" fill="{colors[index % 3]}" font-size="13">'
                  f'{escape(item["asset"]["symbol"])} · {escape(item["basis"])}</text>']
    first = {"start": date.fromordinal(first_day).isoformat(), "end": date.fromordinal(last_day).isoformat()}
    parts += [f'<text x="65" y="276" font-size="12">{first["start"]}</text>',
              f'<text x="695" y="276" text-anchor="end" font-size="12">{first["end"]}</text>', '</svg>']
    return "".join(parts)


def report_html(report):
    """Standalone, escaped, printable report with reviewed vector charts."""
    if not verify_report(report) or not report["analyses"]:
        raise ValueError("Only a checked report can be exported.")
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>AlphaForge · Investment research</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:980px;margin:48px auto;padding:0 24px;color:#17332b}h1{font-size:36px;line-height:1.2}h2{margin-top:32px}p{max-width:80ch}small{color:#596d63}a{color:#155e4c}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #dbe4df;text-align:left}figure{margin:28px 0;break-inside:avoid}svg{width:100%;height:auto}blockquote{border-left:4px solid #155e4c;margin-left:0;padding-left:20px}@media print{body{margin:12px;font-size:11pt}h2{break-after:avoid}}</style>',
             '<main><small>ALPHAFORGE AI · INVESTMENT RESEARCH</small><h1>Your idea, examined with evidence.</h1>',
             f'<blockquote>{escape(report["question"])}</blockquote><small>Research and hypothetical scenarios. No transactions. '
             f'Created {escape(report["created_at"])}</small>']
    if report["editor"].get("answer_status") in {"partial", "evidence_only"}:
        parts += ['<p><strong>Part of this question could not be answered yet. The findings below are the parts that were checked; open points are listed with the reason.</strong></p>']
    for section in report["editor"].get("explanations", []):
        parts += [f'<h2>{escape(section["heading"])}</h2><p>{escape(section["text"])}</p>',
                  '<small>Model interpretation checked against: ' + escape("; ".join(report["blocks"][key]["title"] for key in section["evidence_ids"])) + '</small>']
    parts += ['<h2>The market evidence</h2><table><tr><th>Asset</th><th>Latest observed</th><th>Historical change</th><th>Largest fall</th></tr>']
    for item in report["analyses"]:
        asset, metric = item["asset"], item["metrics"]
        parts += [f'<tr><td>{escape(asset["symbol"])}</td><td>{escape(asset["currency"])} {asset["price"]:,.2f}<br><small>{escape(asset["price_as_of"])}</small></td>'
                  f'<td>{metric["return"]:+.2%} ({escape(item["basis"])})</td><td>{metric["drawdown"]:.2%}</td></tr>']
    parts += ['</table><figure><figcaption>Observed history · each series starts at 100</figcaption>',
              _svg(report["analyses"], "index", "Observed indexed investment values"), '</figure>',
              '<figure><figcaption>Observed fall from earlier highs (%)</figcaption>',
              _svg(report["analyses"], "drawdown", "Observed peak-to-trough falls"), '</figure>']
    for risk in report.get("risks", []):
        if risk["id"] == "cash_needs":
            for row in risk["results"]:
                series = [{"asset": {"symbol": label}, "basis": row["currency"], "metrics": {"path": [
                    {"date": point["date"], "value": point[field]} for point in row["path"]]}}
                    for label, field in (("With withdrawals", "with_withdrawals"), ("Without withdrawals", "without_withdrawals"))]
                parts += [f'<h2>{escape(row["symbol"])} · withdrawals and remaining assets</h2>',
                          _svg(series, "value", "Historical assets with and without withdrawals")]
    for key in report["editor"]["order"]:
        block = report["blocks"][key]
        parts += [f'<h2>{escape(block["title"])}</h2><p>{escape(block["text"])}</p>']
        parts += [f'<p><a href="{escape(url, quote=True)}">Supporting source</a></p>' for url in block["sources"]]
    parts += ['<h2>Sources, dates and limitations</h2>']
    for item in report["analyses"]:
        asset = item["asset"]
        parts += [f'<p><a href="{escape(asset["source_url"], quote=True)}">{escape(asset["symbol"])} · {escape(asset["source"])}</a>'
                  f'<br><small>Retrieved {escape(asset["retrieved_at"])}. Missing price observations: {asset["omitted_rows"]}; '
                  f'missing same-date FX: {item["missing_fx"]}; dates removed for comparison: {item["alignment_omissions"]}.</small></p>']
    if report["fx"]:
        parts += [f'<p><a href="{escape(report["fx"]["source_url"], quote=True)}">Bank of Canada · CAD per USD</a>'
                  f'<br><small>Retrieved {escape(report["fx"]["retrieved_at"])}</small></p>']
    parts += [f'<p>{escape(methodology(report))}</p>']
    parts += [f'<p>Missing evidence: {escape(error)}</p>' for error in report["errors"]]
    parts += [f'<h2>What would improve this answer</h2><p>{escape(report["plan"]["question"])}</p>',
              f'<small>Method: {escape(report["method"])} · Review fingerprint: {escape(report["report_digest"])}</small></main></html>']
    return "".join(parts)


def methodology(report):
    return ("The report requests up to five years of daily adjusted closes, excluding today's unfinished session. "
            "For comparisons it intersects the available observation dates. USD prices are multiplied by same-date CAD-per-USD "
            "rates when CAD is the requested analysis currency and FX data are available; missing FX dates are excluded, not filled using future rates. "
            "Returns compare the first and last included observations. Drawdown compares each observation with its earlier high. "
            "Displayed annualized volatility uses a 252-observation convention; it is withheld for cryptocurrency calendars. "
            "An independent implementation checks the figures and every chart point. This verifies arithmetic, not the original provider's accuracy "
            "or completeness. Exchange-calendar coverage is not certified; missing sessions can understate drawdown. "
            "This is a present-day retrospective, not a point-in-time backtest. Adjusted closes follow provider treatment of splits and distributions; "
            "taxes, transaction fees, spreads and execution effects are excluded. Historical CPI purchasing-power results, when available, are separate from nominal returns. Company fundamentals, news, exact ETF holdings "
            "and comprehensive controversy screening are unavailable. Any qualified partial disclosure is identified separately. Yahoo's unofficial interface may be delayed or unavailable and is used here "
            "for private research; public redistribution requires checking the source terms. No raw data is bundled with the repository.")


def verify_report(report):
    digest = report.get("report_digest")
    if digest != fingerprint({key: value for key, value in report.items() if key != "report_digest"}):
        return False
    return all(review(item["rows"], item["metrics"]) for item in report["analyses"])
