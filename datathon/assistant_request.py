"""Ground supported comparison inputs in the investor's own question."""

import re
from decimal import Decimal
from typing import Iterable


_INTENT = re.compile(
    r"\b(?:compar(?:e|ed|ison|ing|er|ez|aison)|versus|vs\.?)\b|对比|比較|比较|对照|相比|比一比"
    r"|\bwhich\b[^.?!]{0,150}\b(?:performed? better|did better|had (?:the )?(?:higher|lower))\b"
    r"|哪[个個只隻支][^?？。！]{0,22}更", re.I,
)
_SIDE = re.compile(r"\b(?:versus|vs\.?|against|compared (?:to|with)|contre|and\s+(?:portfolio|allocation|option)\s+B)\b|对比|比較|比较|对照|相比|与|和", re.I)
_PORTFOLIO = re.compile(r"\b(?:holdings|allocations?|portfolios?|weights?|pondérations?|portefeuilles?)\b|组合|組合|配置|权重|權重", re.I)
_TRADE = re.compile(r"\b(?:buy|buying|sell|selling|purchase|selling|rebalance|rééquilibrer|acheter|vendre)\b|买入|買入|卖出|賣出|调仓|調倉", re.I)
_PERCENT = r"(?<![\d.+-])(?<!\d,)(?P<number>[+-]?\d+(?:[.,]\d+)?)\s*[%％]"
_RISK_LIMIT = r"(?:max(?:imum)?\s+)?(?:historical\s+)?(?:drawdown|repli maximal)|最大回撤|历史回撤|歷史回撤|回撤"
_CAP = re.compile(
    rf"(?:{_RISK_LIMIT})(?:\s+(?:cap|limit|ceiling))?\s*(?:(?:[:：=≤]|<=)|(?:of|is|at most|no more than|under|below|up to|must not exceed|cannot exceed|must be|限为|上限为?|不能超过|不能超過|不超过|不超過|最多|低于|低於|≤)\s*)+[ \t]*{_PERCENT}"
    rf"|{_PERCENT.replace('?P<number>', '?P<leading>')}\s*(?:(?:as\s+(?:the\s+)?)?(?:{_RISK_LIMIT})\s*(?:cap|limit|ceiling|上限|以内|以內)|(?:{_RISK_LIMIT})\s*(?:以内|以內|上限))"
    rf"|(?:cap|limit)\s+(?:the\s+)?(?:{_RISK_LIMIT})\s+(?:at|to)\s+{_PERCENT.replace('?P<number>', '?P<bounded>')}",
    re.I,
)
_CONTEXT_CAP = re.compile(rf"\b(?:my|the)\s+(?:limit|cap)\s*(?:is|of|=|:)\s*{_PERCENT}", re.I)
_METRICS = {
    "max_drawdown": r"\b(?:max(?:imum)?\s+)?drawdowns?\b|(?:最大|历史|歷史)?回撤|\brepli maximal\b",
    "terminal_loss": r"\b(?:terminal|end[- ]of[- ](?:window|period)) loss\b|期末亏损|期末虧損|期末损失|期末損失|\bperte finale\b",
    "terminal_return": r"\b(?:terminal|end[- ]of[- ](?:window|period)|historical) returns?\b|期末收益|期末回报|期末回報|历史收益|歷史收益|\brendement final\b",
}
_OBJECTIVES = {
    "Growth": r"\b(?:long[- ]term growth|capital growth|growth objective|(?:goal|objective) is growth|croissance à long terme)\b|长期增长|長期增長|(?:目标|目標)(?:是|为|為)增长",
    "Capital preservation": r"\b(?:capital preservation|preserv(?:e|ing) (?:my |the )?(?:capital|principal)|préserver (?:le|mon) capital)\b|保本|本金保护|本金保護|保住本金|资本保全|資本保全",
}
_RISK_TOLERANCE = {
    "Low": r"\b(?:low risk tolerance|risk tolerance (?:is )?low|risk[- ]averse|low willingness to take risk)\b|低风险承受|低風險承受|风险承受(?:能力|意愿)?(?:偏)?低|風險承受(?:能力|意願)?(?:偏)?低|不愿承担高风险",
    "Moderate": r"\b(?:moderate risk tolerance|risk tolerance (?:is )?moderate|moderate willingness to take risk)\b|中等风险承受|中等風險承受|风险承受(?:能力|意愿)?中等|風險承受(?:能力|意願)?中等",
    "High": r"\b(?:high risk tolerance|risk tolerance (?:is )?high|high willingness to take risk|can tolerate high risk)\b|高风险承受|高風險承受|风险承受(?:能力|意愿)?(?:较)?高|風險承受(?:能力|意願)?(?:較)?高",
}
_WITHDRAW = r"\b(?:withdraw(?:al|ing)?|need (?:the|this|my) money|need (?:the|these) funds|cash out|retrait)\b|提款|取款|用钱|用錢|用这笔钱|用這筆錢|取出(?:资金|資金|这笔钱|這筆錢)"
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "一": 1, "二": 2, "两": 2, "兩": 2,
            "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "半年": 0.5}
_WHEN = re.compile(
    r"(?<![\d.])(?P<quantity>\d+(?:\.\d+)?|" + "|".join(_NUMBERS) + r")\s*"
    r"(?P<unit>years?\b|months?\b|ans?\b|mois\b|年|个?月|個月)|(?P<half>半年|half (?:a|one) year)",
    re.I,
)
_ESG = re.compile(r"(?<![A-Za-z0-9_])ESG(?![A-Za-z0-9_])|环境和社会|環境和社會|环境(?:与|與)社会|環境(?:与|與)社會", re.I)
_ESG_OFF = re.compile(r"\b(?:without|no|ignore|exclude|skip|do not (?:require|consider|use)|don't (?:require|consider|use))\s+(?:an?\s+)?(?:mandatory\s+)?ESG\b|(?:不用|无需|無需|不需要|不要|排除|忽略)\s*ESG", re.I)
_ESG_ON = re.compile(r"\b(?:must (?:consider|include|pass|satisfy)|require|consider|with)\s+(?:an?\s+)?(?:mandatory\s+)?ESG\b|\bESG (?:screening )?(?:is )?(?:mandatory|required)\b|(?:必须|必須|需要|要求)(?:考虑|考慮|通过|通過|符合|满足|滿足)?\s*ESG", re.I)
_REPLAY_2023 = re.compile(
    r"\b(?P<action>(?:do not|don't)\s+(?:include|add)|include|add|exclude|omit|skip|remove)\s+(?:(?:the|an?)\s+)?(?:optional\s+)?2023(?:\s+(?:stress|replay|window)){0,3}\b"
    r"|(?P<action_zh>不加上|不加入|不纳入|不納入|不包含|加上|加入|纳入|納入|包含|排除|不要|不含|不包括)\s*2023\s*(?:年(?:压力|壓力)?(?:窗口|回放)?)?", re.I,
)
_UNSUPPORTED = (
    (r"\b(?:live quotes?|current prices?|price target|predict|forecast|expected returns?|best to buy|should (?:i|we) buy|guarantee[ds]?|(?:how|what|which) will|next (?:week|month|quarter|year) returns?|future returns?|(?:performance|returns?) (?:next|over the next) (?:week|month|quarter|year)|(?:compare|comparison) [^.?!]{1,75} (?:during|over) (?:the )?next (?:month|quarter|year))\b|实时(?:价格|行情)|即時(?:價格|行情)|预测|預測|目标价|目標價|该买|該買|推荐买|推薦買|适合买|適合買|(?:未来|未來|明年)(?:收益|回报|回報|走势|走勢|表现|表現)", "The comparison replays historical data. Please remove the forecast, live-price, or trading recommendation requirement."),
    (r"\b(?:sharpe|sortino|volatility|standard deviation|tracking error|expense ratio|fees?|tax(?:es)?|dividend yield|value at risk|liquidity|credit rating|duration|beta|annual(?:ized|ised) returns?|correlation)\b|夏普|波动率|波動率|跟踪误差|费用|費用|费率|費率|税费|稅費|股息率|流动性|流動性|信用评级|相关性|相關性|年化", "The requested metric or requirement is outside the comparison scope. Use historical terminal return, terminal loss, or maximum drawdown."),
    (r"\b(?:in|using|denominated in|convert(?:ed)? to|currency[: ]+)\s*(?:US\s*dollars?|USD|EUR|GBP|CNY|HKD|euros?)\b|以(?:美元|欧元|歐元|人民币|人民幣|港币|港幣)(?:计|計|计算|計算|比较|比較)|换成(?:美元|人民币)", "The historical comparison uses CAD. Confirm a CAD comparison to proceed."),
    (r"\b(?:at least|minimum|no less than|more than)\s+[+-]?\d+(?:[.,]\d+)?\s*%|\b(?:minimum|floor) (?:terminal |historical )?return\b|(?:至少|最低|不低于|不低於|大于|大於)[ \t]*[+-]?\d+(?:[.,]\d+)?\s*[%％]", "Minimum percentage requirements are outside this comparison. The supported loss constraint is a maximum drawdown limit."),
    (r"\b(?:just|only|exactly)\s+(?:use\s+)?(?:the\s+)?20\d{2}\b|\b(?:since|from|to|through|between|during|in)\s+20\d{2}\b|\b(?:last|past)\s+\d+\s+(?:years?|months?)\b|(?:仅|僅|只|从|從|截至|期间|期間)\s*20\d{2}", "The comparison uses fixed 2022 and early 2025 stress replays. You can explicitly add the optional 2023 replay."),
    (r"\b(?:strictly below|strictly less than|strictly under)\b|(?<![<>=])<(?![=])|严格低于|嚴格低於", "The drawdown cap includes its boundary. Please confirm that a value equal to the cap is allowed."),
)
_UNKNOWN = re.compile(r"(?<![A-Za-z0-9_.$-])(?:\$[A-Za-z]{1,9}|[A-Z]{2,8})(?:[.-][A-Za-z0-9]{1,5})?(?![A-Za-z0-9_-]|\.[A-Za-z0-9])")
_ORDINARY = frozenset("AI AM AND ARE AS AT CAD CAN CASH CHOOSE COMPARE ETF ETFS EUR ESG FOR GBP GROWTH I IN IS IT MAX MONTHS MY NO NOT OF ONLY OR OUT PORTFOLIO RISK SHOW STOCK THE TO USD USE VS WITH YEARS".split())
_CLAUSE = re.compile(r".+?(?:[!?。！？;；\n]|\.(?=\s|$)|$)", re.S)
_BINDING = re.compile(r"\b(?:must|require(?:s|d)?|need to|can't|cannot|may not|avoid|only|maximum|limit|cap|under|at most|exclude|ignore|never|except|without|no|not|don't|if|unless|provided that)\b|必须|必須|只能|不得|不超过|不超過|上限|限制|禁止|不能|避免|忽略|不要|排除|除外|如果|除非|仅在|僅在", re.I)
_IGNORE = re.compile(r"\b(?:do not|don't|ignore|exclude|omit|without|skip|avoid|never|rather than|instead of|not use)\b|不(?:用|要|考虑|考慮|需要)|忽略|排除|而非|不要用", re.I)
_EXPLICIT_RANKING = re.compile(r"\b(?:by|rank|prioriti[sz]e|prioritise|most important|primarily|based on|minimi[sz]e|maximi[sz]e)\b|根据|根據|按|依照|优先|優先|以.{0,22}为主|以.{0,22}為主|哪个|哪個", re.I)
_SAFE_ONLY = re.compile(r"\bonly\s+(?:compare|show historical (?:data|performance|results?))\b|\bcompare\s+only\b|只(?:比较|比較|对比|看历史数据|看歷史資料)", re.I)
_QUALITATIVE_DOWNSIDE = re.compile(r"\b(?:safer|less risky|lower (?:historical )?(?:risk|downside)|more stable)\b|更稳健|更穩健|更稳定|更穩定|更安全|风险更低|風險更低", re.I)


def _result(status, fields, sources, message=""):
    return {"status": status, "fields": fields, "sources": sources, "message": message}


def _blank(text, spans):
    """Hide grounded values without moving their offsets in the original question."""
    chars = list(text)
    for start, stop in spans:
        chars[start:stop] = " " * (stop - start)
    return "".join(chars)


def _mentions(patterns, text):
    return {name: match for name, pattern in patterns.items() if (match := re.search(pattern, text, re.I))}


def _asset_pattern(assets):
    names = "|".join(re.escape(name) for name in sorted(assets, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9_.$-])\$?(?P<ticker>{names})(?![A-Za-z0-9_-]|\.[A-Za-z0-9])", re.I)


def _weight_matches(text, assets, *, allow_unbound=False):
    """Associate a percentage with the immediately adjacent ticker."""
    space = r"[^\S\r\n]" if allow_unbound else r"\s"
    left_connector = re.compile(rf"{space}*(?:[:：=]|at)?{space}*", re.I)
    right_connector = re.compile(rf"{space}*(?:(?:of|in|into|to){space}+)?", re.I)
    matches = []
    for number in re.finditer(_PERCENT, text):
        left = [asset for asset in assets if asset.end() <= number.start()
                and left_connector.fullmatch(text[asset.end():number.start()])]
        right = [asset for asset in assets if asset.start() >= number.end()
                 and right_connector.fullmatch(text[number.end():asset.start()])]
        if not left and not right and allow_unbound:
            continue
        if len(left) + len(right) != 1:
            return None
        asset = (left or right)[0]
        value = Decimal(number["number"].replace(",", "."))
        if not 0 < value <= 100:
            return None
        matches.append((min(asset.start(), number.start()), max(asset.end(), number.end()), asset, value))
    return matches


def _allocations(text, assets):
    weights = _weight_matches(text, assets)
    if not weights or {asset.span() for _, _, asset, _ in weights} != {asset.span() for asset in assets}:
        return None
    splits = []
    for divider in _SIDE.finditer(text):
        left = [(asset["ticker"].upper(), value) for _, stop, asset, value in weights if stop <= divider.start()]
        right = [(asset["ticker"].upper(), value) for start, _, asset, value in weights if start >= divider.end()]
        if len(left) + len(right) != len(weights):
            continue
        if all(group and len(dict(group)) == len(group) and sum(value for _, value in group) == 100 for group in (left, right)):
            splits.append((left, right))
    if len(splits) != 1:
        return None
    return {name: {ticker: float(value / 100) for ticker, value in group}
            for name, group in zip(("Current allocation", "Proposed allocation"), splits[0])}


def _horizons(text):
    result = {}
    for clause in _CLAUSE.finditer(text):
        withdrawal = re.search(_WITHDRAW, clause[0], re.I)
        if not withdrawal:
            continue
        for when in _WHEN.finditer(clause[0]):
            quantity = when["quantity"]
            number = (_NUMBERS[quantity.lower()] if quantity and quantity.lower() in _NUMBERS else float(quantity)) if quantity else .5
            unit = when["unit"] or "year"
            months = number if unit.lower().startswith(("month", "mois")) or unit.endswith("月") else number * 12
            prefix = clause[0][max(0, when.start() - 19):when.start()]
            if months in (12, 60) and re.search(r"\b(?:more than|over|after)\s*$|超过\s*$|超過\s*$", prefix, re.I):
                months += 1
            bucket = "Within 1 year" if months <= 12 else "1 to 5 years" if months <= 60 else "More than 5 years"
            start = clause.start() + min(withdrawal.start(), when.start())
            end = clause.start() + max(withdrawal.end(), when.end())
            result[bucket] = (start, end)
    return result


def parse_comparison_request(text: str, assets: Iterable[str], *, extract_only: bool = False) -> dict:
    """Extract a narrow comparison contract or ask about an unresolved instruction.

    `extract_only` lets another validated input path ground individual phrases.
    Blank or unstated profile fields stay blank, including the ranking metric.
    """
    fields, sources, spans = {}, {}, []
    if not isinstance(text, str) or not text.strip():
        return _result("unrecognized", fields, sources)
    if len(text) > 8000:
        return _result("clarify", fields, sources, "Please shorten the comparison request.")
    assets = {name.upper() for name in assets if isinstance(name, str) and name}
    found = list(_asset_pattern(assets).finditer(text)) if assets else []
    intent = _INTENT.search(text)
    if not intent and not extract_only:
        return _result("unrecognized", fields, sources)

    def save(key, value, start, end):
        fields[key] = value
        sources[key] = text[start:end]
        spans.append((start, end))

    if _TRADE.search(text) and intent:
        return _result("unsupported", fields, sources, "This question includes a trade. Use the trade audit or compare two fully specified holdings allocations.")

    cap_matches = list(_CAP.finditer(text))
    cap_excerpt_start = cap_matches[0].start() if cap_matches else None
    if not cap_matches:
        metrics = _mentions(_METRICS, text)
        context_cap = _CONTEXT_CAP.search(text)
        if context_cap and set(metrics) == {"max_drawdown"}:
            drawdown = metrics["max_drawdown"]
            if drawdown.end() <= context_cap.start() and re.fullmatch(r"[\s.,:;]+", text[drawdown.end():context_cap.start()]):
                cap_matches = [context_cap]
                cap_excerpt_start = drawdown.start()
    if cap_matches:
        caps = {Decimal(next(value for value in match.groupdict().values() if value is not None).replace(",", ".")) for match in cap_matches}
        if len(caps) != 1 or not 0 <= next(iter(caps)) <= 100:
            return _result("clarify", fields, sources, "Please confirm a single maximum drawdown limit between 0% and 100%.")
        save("max_drawdown", float(next(iter(caps)) / 100), cap_excerpt_start, cap_matches[0].end())
        spans.extend(match.span() for match in cap_matches[1:])

    for key, patterns in (("objective", _OBJECTIVES), ("risk_tolerance", _RISK_TOLERANCE)):
        values = _mentions(patterns, text)
        if len(values) > 1:
            return _result("clarify", fields, sources, "Please confirm which stated objective or risk preference should govern this comparison.")
        if values:
            value, match = next(iter(values.items()))
            save(key, value, *match.span())

    horizons = _horizons(text)
    if len(horizons) > 1:
        return _result("clarify", fields, sources, "Please confirm the time of your next meaningful withdrawal.")
    if horizons:
        horizon, span = next(iter(horizons.items()))
        save("withdrawal_time", horizon, *span)
        if "objective" not in fields:
            save("objective", "Fund a planned withdrawal", *span)

    esg_on = list(_ESG.finditer(_blank(text, [match.span() for match in _ESG_OFF.finditer(text)])))
    esg_off = _ESG_OFF.search(text)
    if esg_on and esg_off:
        return _result("clarify", fields, sources, "Please confirm whether ESG screening is required.")
    if esg_on or esg_off:
        excerpt = esg_off or _ESG_ON.search(text) or esg_on[0]
        save("require_esg", bool(esg_on), *excerpt.span())

    replays = list(_REPLAY_2023.finditer(text))
    actions = {((m["action"] or m["action_zh"]).lower() in {"include", "add", "加上", "加入", "纳入", "納入", "包含"}) for m in replays}
    if len(actions) > 1:
        return _result("clarify", fields, sources, "Please confirm whether to include the optional 2023 replay.")
    if actions:
        save("include_2023", next(iter(actions)), *replays[0].span())
        spans.extend(match.span() for match in replays[1:])

    ranking_text = _blank(text, [match.span() for match in cap_matches])
    rankings = _mentions(_METRICS, ranking_text)
    if any(_IGNORE.search(clause[0]) and _mentions(_METRICS, clause[0]) for clause in _CLAUSE.finditer(_blank(ranking_text, spans))):
        return _result("clarify", fields, sources, "Please state the single metric you want to prioritize, or request a side-by-side comparison without a ranking.")
    if len(rankings) > 1 and _EXPLICIT_RANKING.search(ranking_text):
        return _result("clarify", fields, sources, "Please choose one ranking metric, or ask to see the metrics side by side.")
    if not rankings and _QUALITATIVE_DOWNSIDE.search(ranking_text):
        return _result("clarify", fields, sources, "For lower historical downside, should the comparison prioritize maximum drawdown or terminal loss?")
    if len(rankings) == 1:
        priority, match = next(iter(rankings.items()))
        save("priority", priority, *match.span())

    folded = _blank(text, [asset.span() for asset in found])
    for pattern, message in _UNSUPPORTED:
        if re.search(pattern, folded, re.I):
            return _result("unsupported", fields, sources, message)
    if re.search(r"\b20\d{2}\b", _blank(folded, spans)):
        return _result("unsupported", fields, sources, "Use the standard 2022 and early 2025 replays, or ask to add the optional 2023 replay explicitly.")

    unknown = [match[0] for match in _UNKNOWN.finditer(folded) if match[0].startswith("$") or match[0] not in _ORDINARY]
    if unknown:
        return _result("clarify", fields, sources, "Please confirm supported ticker symbols. The question includes " + ", ".join(dict.fromkeys(unknown)) + ".")

    unbound = _blank(text, [match.span() for match in cap_matches])
    if re.search(_PERCENT, unbound):
        options = _allocations(unbound, found)
        if options is None:
            return _result("clarify", fields, sources, "Please label the two allocations, attach a percentage to each ticker, and make each side total 100%. State any drawdown limit separately.")
        weights = list(re.finditer(_PERCENT, unbound))
        start = min(found[0].start(), weights[0].start())
        stop = max(found[-1].end(), weights[-1].end())
        fields["options"] = options
        sources["options"] = text[start:stop]
    elif found:
        distinct = list(dict.fromkeys(asset["ticker"].upper() for asset in found))
        if len(distinct) != 2 or _PORTFOLIO.search(text):
            if not extract_only or len(distinct) > 2 or _PORTFOLIO.search(text):
                return _result("clarify", fields, sources, "Please name two assets, or specify each ticker and its weight for both allocations.")
        for key, ticker in zip(("first_asset", "second_asset"), distinct):
            asset = next(match for match in found if match["ticker"].upper() == ticker)
            save(key, ticker, *asset.span())

    remaining = _blank(folded, spans + [match.span() for match in rankings.values()])
    if _BINDING.search(_SAFE_ONLY.sub(" ", remaining)):
        return _result("clarify", fields, sources, "Part of your requirement could not be checked. State the drawdown cap or ESG requirement explicitly, or confirm a narrower question.")
    if "options" in fields or {"first_asset", "second_asset"} <= fields.keys():
        return _result("ready", fields, sources)
    if extract_only:
        return _result("unrecognized", fields, sources)
    return _result("clarify", fields, sources, "Please provide two supported ticker symbols or two complete weighted allocations.")
