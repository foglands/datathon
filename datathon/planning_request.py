"""Identify the context a user stated in an open-ended investment question."""

import re
from decimal import Decimal


_DECISION_SIGNAL = re.compile(
    r"[?？]|\b(?:compar(?:e|ing)|choos(?:e|ing)|decid(?:e|ing)|weigh(?:ing)?|prioriti[sz](?:e|ing)|consider(?:ing)?|recommend|suggest|evaluate|assess|"
    r"guidance|advice|trade[- ]?offs|pros and cons|lean toward|help (?:me|us)|thinking (?:about|of)|"
    r"torn between|wonder(?:ing)?|how to|what to|where to)\b"
    r"|怎么|怎麼|怎样|怎樣|如何|选哪|選哪|取舍|取捨|比较|比較|对比|對比|建议|建議|适合|適合|考虑|考慮|纠结|糾結"
    r"|\b(?:comment|quel(?:le)?s?|choisir|comparer|h[ée]siter|conseil|pour et contre)\b",
    re.I,
)
_FINANCIAL_TOPIC = re.compile(
    r"\b(?:invest(?:or|ing|ments?)?|investment portfolio|brokerage|asset allocation|share price|"
    r"dividends?|purchasing power|retirement savings|savings accounts?|(?:my|our|your) cash|"
    r"mutual funds?|index funds?|exchange[- ]traded funds?|ETFs?)\b"
    r"(?!\s+(?:(?:my|our|more|your)\s+)?(?:time|effort|energy)\b)"
    r"|投资|投資|理财|理財|组合配置|組合配置|股价|股價|购买力|購買力"
    r"|\b(?:placements? financiers?|investissements?|portefeuille|[ée]pargnes?)\b",
    re.I,
)
_EXACT_TRADE = re.compile(
    r"\baudit\b[^.?!]{0,60}\b(?:trade|purchase|position)\b"
    r"|\b(?:buy|add|increase|sell)\b[^.?!]{0,65}\b(?:percentage points?|basis points?|bps)\b"
    r"|\b(?:place|execute|submit) (?:a |the |my )?(?:market |limit )?(?:order|trade|purchase)\b"
    r"|(?:下单|下單|执行交易|執行交易)|(?:买入|買入|卖出|賣出)[^。！？]{0,30}(?:百分点|百分點)",
    re.I,
)
_EXPLICIT_ANALYSIS = re.compile(
    r"\b(?:compare|backtest)\b[^.?!\n]{0,100}\b(?:maximum drawdown|terminal loss|terminal return|replay)\b"
    r"|\b(?:forecast|predict|project|estimate)\b[^.?!\n]{0,75}\b(?:returns?|prices?|yield|profit)\b"
    r"|(?:比较|比較|对比|對比|回测|回測)[^。！？\n]{0,30}(?:回撤|期末收益|历史回放|歷史回放)"
    r"|(?:预测|預測|预估|預估)[^。！？\n]{0,25}(?:收益|回报|回報|涨幅|漲幅|价格|價格)",
    re.I,
)
_CLAUSE = re.compile(r".+?(?:[!?。！？;；\n]|\.(?=\s|$)|$)", re.S)
_NUMBER = r"\d+(?:[,，]\d{3})*(?:\.\d+)?(?:\s*[kKmM](?!\w))?"
_CURRENCY_ALIASES = {
    "CAD": r"CAD|CA\$|C\$|Canadian dollars?|加元|加币|加幣",
    "USD": r"USD|US\$|U\.?S\.? dollars?|American dollars?|美元",
    "AUD": r"AUD|AU\$|A\$|Australian dollars?",
    "NZD": r"NZD|NZ\$|New Zealand dollars?",
    "EUR": r"EUR|euros?|€",
    "GBP": r"GBP|British pounds?|pounds? sterling|£",
    "CNY": r"CNY|RMB|Chinese yuan|人民币|人民幣",
    "HKD": r"HKD|HK\$|Hong Kong dollars?|港币|港幣",
    "JPY": r"JPY|Japanese yen",
}
_CURRENCY = "|".join(_CURRENCY_ALIASES.values())
_AMOUNT = re.compile(
    rf"(?<![A-Za-z0-9_.+−-])[+−-]?(?:(?:(?:{_CURRENCY})(?:\s*\$)?|\$)\s*[+−-]?{_NUMBER}"
    rf"|{_NUMBER}\s*(?:[万萬]\s*)?(?:元(?:人民币|人民幣)?|dollars?|{_CURRENCY})"
    rf"|{_NUMBER}\s*[万萬])(?![A-Za-z0-9_])",
    re.I,
)
_EXPLICIT_CURRENCY = re.compile(_CURRENCY, re.I)
_AMOUNT_VALUE = re.compile(r"(?P<digits>\d+(?:[,，]\d{3})*(?:\.\d+)?)(?:\s*(?P<scale>[kKmM万萬])(?![A-Za-z]))?")
_AMOUNT_SCALE = {"k": 3, "m": 6, "万": 4, "萬": 4}
_INLINE_CURRENCY = re.compile(rf"\s*(?:\(\s*|(?:in\s+)?)(?P<currency>{_CURRENCY})(?![A-Za-z0-9_])\s*\)?", re.I)
_BALANCE_SUBJECT = r"(?:(?:the|this|that|my|our|your|stated|starting|above)\s+)*(?:(?:cash|savings|account)\s+)?(?:balance|amount|savings|cash|money)"
_BALANCE_LINK = r"(?:(?:is|are|will be|should be)(?:\s+(?:(?:held|denominated|treated|processed|expressed|stated)\s+(?:as|in)|in))?|in)"
_CURRENCY_DECLARATION = re.compile(
    rf"(?:(?P<correction>actually|correction|i mean)\b\s*[:,]?\s*)?"
    rf"(?:(?:{_BALANCE_SUBJECT}\s+{_BALANCE_LINK}|(?:the\s+)?currency(?:\s+(?:of|for)\s+{_BALANCE_SUBJECT})?"
    rf"\s*(?:[:=]|\bis\b))\s*)?(?P<currency>{_CURRENCY})"
    rf"(?:\s*\(\s*(?P<alias>{_CURRENCY})\s*\))?(?:\s*,?\s+not\s+(?P<excluded>{_CURRENCY}))?[.!;。；]?",
    re.I,
)
_BALANCE_REFERENCE = re.compile(r"(?:(?:the|this|that|my|our|your)\s+)?", re.I)
_BALANCE_REFERENCE_CURRENCY = re.compile(
    rf"\s+(?:(?:cash|savings|account|starting)\s+)?balance\s+{_BALANCE_LINK}\s+(?P<currency>{_CURRENCY})"
    rf"(?![A-Za-z0-9_])(?:\s*\(\s*(?P<alias>{_CURRENCY})\s*\))?",
    re.I,
)
_OTHER_AMOUNT_SUFFIX = re.compile(
    r"^\s*(?:(?:of\s+)?(?:(?:credit card|student|mortgage|outstanding)\s+)?(?:debt|loans?|liabilities)\b"
    r"|(?:left\s+)?(?:in|on|as|tied up in)\s+(?:(?:my|our|the|a)\s+)*(?:current\s+|existing\s+|unrealized\s+)?"
    r"(?:holdings?|stocks?|shares?|investments?|equity|crypto(?:currency)?|bitcoin|funds?|loans?|debt|principal)\b"
    r"|(?:in|on)\s+\$?[A-Z][A-Z0-9]{1,7}(?:[.-][A-Z0-9]+)?\b|(?:的)?(?:债务|債務|贷款|貸款|欠款))",
)
_CASH = re.compile(
    r"\b(?:bank account|savings account|che(?:ck|qu)ing account|savings|saved|cash savings|cash balance|money in (?:the |my |our )?bank|"
    r"money sitting (?:idle|in the bank)|cash sitting (?:idle|in the bank)|[ée]pargne|compte bancaire|compte d['’][ée]pargne|"
    r"(?:mon|notre) compte)\b"
    r"|存款|积蓄|積蓄|存[在进進]银行|存[在进進]銀行|银行账户|銀行賬戶|现金余额|現金餘額",
    re.I,
)
_OWN_POSITION = re.compile(
    r"\b(?:my|our)\s+(?:bank|savings|che(?:ck|qu)ing|cash|money|investment budget)\b"
    r"|\b(?:I|we)\s+(?:(?:currently|recently|already|finally|just)\s+)?(?:have|hold|saved|set aside|put aside|accumulated)\b"
    r"|\b(?:I['’]ve|we['’]ve)\s+(?:(?:recently|already|finally|just)\s+)?(?:got|saved|set aside|put aside|tucked away|accumulated)\b"
    r"|\b(?:I|we)\b[^.?!;\n]{0,75}\band\s+(?:finally\s+)?saved\b"
    r"|我(?:们|們)?(?:的|手头|手頭|目前|现在|現在|已经|已經|刚|剛|还剩|還剩|攒了|攢了|存了|有)"
    r"|\b(?:mon|notre)\s+(?:compte|[ée]pargne)\b|\b(?:j['’]ai|nous avons)\b",
    re.I,
)
_DIRECT_BALANCE = re.compile(
    r"\b(?:I|we)\s+(?:(?:currently|recently|already|finally|just)\s+)?(?:have|hold|saved|set aside|put aside|accumulated)\s+"
    r"|\b(?:I['’]ve|we['’]ve)\s+(?:(?:recently|already|finally|just)\s+)?(?:got|saved|set aside|put aside|tucked away|accumulated)\s+"
    r"|我(?:们|們)?(?:手[头頭]|目前|现在|現在|已经|已經|刚|剛)?(?:有|攒了|攢了|存了|还剩|還剩)"
    r"|\b(?:j['’]ai|nous avons)\s+",
    re.I,
)
_APPROXIMATION = re.compile(r"\s*(?:(?:about|around|roughly|approximately|environ)\s+|大约|大約|大概)?", re.I)
_BALANCE_CONNECTOR = re.compile(
    r"(?:\b(?:has|have|holds?|contains?|saved|left|is|are|set aside|put aside|tucked away|stands at|balance of|total of|ai|avons|contient|solde de)"
    r"(?:\s+(?:about|around|roughly|approximately|environ))?\s*|(?:余额|餘額|有|还剩|還剩|攒了|攢了|存了|为|為)(?:大[约約概])?\s*|:\s*)$",
    re.I,
)
_STATEMENT_BOUNDARY = re.compile(
    r",(?![0-9])|，(?![0-9])|\b(?:but|while|whereas)\b"
    r"|\band\s+(?=(?:my|our|their|his|her)\s+(?!bank\b|savings\b|cash\b)|(?:I|we|he|she|they)\s+)"
    r"|(?:但是|但|然而|可是|而是)",
    re.I,
)
_OTHER_PERSON = re.compile(
    r"\b(?:my|our|your|a|the)\s+(?:co-?workers?|colleagues?|friends?|parents?|siblings?|partners?|"
    r"boss|uncle|aunt|brother|sister|mother|father|neighbor|neighbour|client|customer)\b"
    r"|^\s*(?:(?:he|she|they)\s+|(?:his|her|their|your)\s+(?:bank|savings|cash|money)\b)"
    r"|(?:我(?:的)?|我们(?:的)?|他(?:的)?|她(?:的)?|某位)(?:同事|朋友|父母|邻居|鄰居|客户|客戶)|^(?:他|她)(?:们|們)?(?:的|有|存了|想)",
    re.I,
)
_QUOTED_STATEMENT = re.compile(r"^[\s:]*[\"'“‘«]")
_UNASSERTED_CASH = re.compile(
    r"\b(?:if|suppose|assuming|imagine|hypothetically|not|never|no longer|used to|hope to|plan to|want to|owe|in debt|credit limit)\b"
    r"|(?:假如|如果|假设|假設|曾经|曾經|希望|计划|計劃|没有|沒有|没了|欠款)|\b(?:si|supposons|imaginons)\b",
    re.I,
)
_NEAR_NEGATION = re.compile(
    r"(?:\b(?:not|never|no|(?:don|didn|isn|wasn|weren|aren)[’']t)(?:\s+[\w’'-]+){0,3}|不|没|沒有|没有)\s*$",
    re.I,
)
_PRECEDING_EXCLUSION = re.compile(
    r"\b(?:avoid(?:ing)?|rul(?:e|ed|ing) out|exclud(?:e|ed|ing)|stay(?:ing)? away from|no interest in|"
    r"not interested in|(?:don['’]t|do not) want(?: to (?:buy|hold|choose|consider))?|(?:rather|prefer) not to (?:buy|hold|consider))"
    r"(?:\s+(?!but\b|instead\b|favor\b)[\w&'-]+){0,4}\s*$"
    r"|\b(?:pas de|pas d['’]|sans|[ée]vite)\s*$|(?:不(?:考虑|考慮|打算买|打算買|想买|想買|买|買)|排除|避开|避開)\s*$",
    re.I,
)
_FOLLOWING_EXCLUSION = re.compile(
    r"^\s+(?:(?:is|are)\s+(?:off the table|ruled out|out of the question)|(?:doesn't|does not) interest me)\b"
    r"|^\s*(?:就算了|不考虑|不考慮)",
    re.I,
)
_EXCLUSION_LIST = re.compile(
    r"\b(?:(?:do not|don['’]t|never|rather not)\s+(?:want|buy|hold|consider|choose|invest in)|"
    r"avoid(?:ing)?|rul(?:e|ed|ing) out|exclud(?:e|ed|ing)|stay(?:ing)? away from|no interest in|not interested in)\b"
    r"|(?:不(?:考虑|考慮|打算买|打算買|想买|想買|买|買)|排除|避开|避開)|\bpas (?:de\s+|d['’])",
    re.I,
)
_EXCLUSION_BOUNDARY = re.compile(
    r"\b(?:but|however|instead|in favor of)\b|[,，]\s*(?=(?:I|we|can|could|should|would|what about|how about)\b)"
    r"|(?:但是|然而|而是|可是|改为|改為)",
    re.I,
)
_DURATION = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|eighteen|twenty|several|a few)\s+(?:months?|years?)"
_STATED_DATE = r"(?:this|next)\s+(?:month|year|spring|summer|fall|autumn|winter)|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}"
_PROMISE = r"\b(?:guarantee(?:d|s)?|assured)\b|保证|保證|承诺|承諾|保證獲利"
_RETURN = r"\b(?:returns?|yields?|profits?|gains?|earnings)\b|回报|回報|收益|年化|利率|獲利|盈利"
_RETURN_CLAIM = re.compile(rf"(?:{_PROMISE}).{{0,80}}(?:{_RETURN})|(?:{_RETURN}).{{0,55}}(?:{_PROMISE})", re.I)
_NVIDIA = re.compile(r"\b(?:Nvidia|NVDA)\b|英伟达|英偉達|輝達", re.I)
_BITCOIN = re.compile(r"\b(?:bitcoin|btc(?:-usd)?)\b|比特币|比特幣", re.I)
_LOSS_EVENT = r"\b(?:crash(?:es)?|loss(?:es)?|drop(?:s|ped|ping)?|declin(?:e|es|ed|ing)|volatility|drawdowns?)\b"
_SPENDING_EFFECT = re.compile(r"\b(?:leave (?:me|us) short|couldn['’]t afford|could not afford|hurt (?:my|our) ability)\b|付不起|负担不起|負擔不起", re.I)
_POINTS = {
    "spending": re.compile(
        r"\b(?:expenses|(?<!treasury )(?<!t-)bills|tuition|childcare|daycare|living costs|down payment|rent payments|"
        r"need (?:the|this|my|our) (?:money|cash)|planned withdrawal|d[ée]penses|frais de scolarit[ée]|loyer|mise de fonds)\b"
        r"|宝宝开销|寶寶開銷|孩子开销|孩子開銷|育儿|育兒|学费|學費|首付|开销|開銷|开支|開支|支出|用钱|用錢",
        re.I,
    ),
    "inflation": re.compile(r"\b(?:inflation|cost of living|purchasing power)\b|通胀|通脹|通货膨胀|通貨膨脹|购买力|購買力|生活成本", re.I),
    "growth": re.compile(
        r"\b(?:extra (?:cash|money|income)|grow (?:my |our |the )?(?:money|savings|capital)|long-term growth|"
        r"earn (?:more|interest|a return)|build wealth|financial (?:freedom|independence)|supplement (?:my |our )?income)\b"
        r"|额外(?:收入|收益)|額外(?:收入|收益)|赚点钱|賺點錢|长期增长|長期增長|增值|赚取利息|賺取利息|财务自由|財務自由",
        re.I,
    ),
    "risk": re.compile(
        r"\b(?:lost money|loss[- ]averse|risk[- ]averse|low risk tolerance|(?:can't|cannot|can’t) afford (?:a |any )?loss|"
        r"(?:afraid|scared|terrified|worried|concerned) (?:about|of) [^.?!;\n]{0,42}"
        r"(?:crash(?:es)?|loss(?:es)?|losing|a drop|volatility|drawdown)|fear (?:of )?(?:market crashes|losses)|"
        r"want to avoid (?:losses|large drawdowns|market crashes))\b"
        rf"|\b(?:lose sleep|uneasy|uncomfortable|anxious)\b[^.?!;\n]{{0,55}}{_LOSS_EVENT}"
        rf"|{_LOSS_EVENT}[^.?!;\n]{{0,52}}\b(?:leave (?:me|us) short|couldn['’]t afford|could not afford|hurt (?:my|our) ability)\b"
        r"|\b(?:j['’]ai peur|je crains)[^.?!;\n]{0,45}(?:krach|baisse|pertes?|volatilit[ée])\b"
        r"|(?:担心|擔心|怕|害怕)[^。！？\n]{0,16}(?:亏钱|虧錢|亏损|虧損|大跌|暴跌|崩盘|崩盤|回撤)"
        r"|(?:亏过钱|虧過錢|亏了钱|虧了錢|亏损过|虧損過|厌恶风险|厭惡風險|不能亏|不能虧|保本)",
        re.I,
    ),
    "timing": re.compile(
        rf"\b(?:time horizon|investment horizon|withdrawal date)\s*(?:is\s+|of\s+|:\s*)(?:{_DURATION}|{_STATED_DATE})\b"
        r"|\b(?:need|withdraw|spend|use|access|pay|park|lock up)\b[^.?!;\n]{0,48}"
        rf"\b(?:(?:in|within|after|by|until|over|for)\s+{_DURATION}|{_STATED_DATE})\b"
        r"|(?:\d+|[一二三四五六七八九十两兩])?(?:个|個)?(?:月|年|半年)(?:后|後|内|內)[^。！？\n]{0,20}"
        r"(?:用钱|用錢|提款|取款|支付|付费|付費|开销|開銷|支出)",
        re.I,
    ),
    "beginner": re.compile(
        r"\b(?:new to investing|never invested|first time investing|(?:don't|do not|don’t) know (?:anything )?about investing)\b"
        r"|投资新手|投資新手|没投过资|沒投過資|不懂投资|不懂投資", re.I,
    ),
    "concentration": re.compile(
        r"\b(?:put|invest|allocate|move|bet) (?:just )?(?:all|everything|my entire|our entire|the entire)\b"
        r"|\b(?:buy|purchase)\b[^.?!\n]{0,60}\bwith all (?:my|our)\b|全仓|全倉|梭哈|全部投(?:入)?|全部买|全部買", re.I,
    ),
    "peer_trading": re.compile(
        r"\b(?:coworkers|colleagues|friends|people online)\b[^.?!\n]{0,70}\b(?:trad(?:e|ing)|buy(?:ing)?|invest(?:ing)?|made|making)\b"
        r"|(?:同事|朋友|网友|網友)[^。！？\n]{0,25}(?:赚钱|賺錢|投资|投資|炒股|交易)", re.I,
    ),
    "return_claim": _RETURN_CLAIM,
}
_INSTRUMENTS = {
    "sp500": re.compile(r"(?<![A-Za-z])S\s*(?:&|and)\s*P[\s-]*500\b|标普\s*500|標普\s*500", re.I),
    "gold": re.compile(
        r"\bgold\b(?![- ](?:colou?r(?:ed|s)?|paint|shoes|dress|shirt|fabric|medal|jewelry|jewellery|ring|necklace|earrings?)\b)"
        r"|黄金(?!首饰|戒指|项链|颜色)|黃金(?!首飾|戒指|項鏈|顏色)|金条|金條", re.I,
    ),
    "cash_deposits": re.compile(r"\b(?:GICs?|CPG|high-interest savings(?: accounts?)?|term deposits?|certificates? of deposit|d[ée]p[ôo]ts? [àa] terme)\b|定期存款|高息储蓄|高息儲蓄", re.I),
    "bonds": re.compile(
        r"(?<!family )(?<!social )(?<!chemical )(?<!covalent )(?<!ionic )(?<!molecular )(?<!bail )"
        r"\bbonds?\b|\b(?:fixed income|treasury bills?|T-bills?|fonds obligataires?)\b|债券|債券|国债|國債", re.I,
    ),
    "equity_funds": re.compile(r"\b(?:(?:equity|stock|index)\s+(?:funds?|ETFs?)|fonds indiciels?|fonds d['’]actions)\b|股票基金|指数基金|指數基金", re.I),
    "individual_stock": re.compile(rf"(?:{_NVIDIA.pattern})|\b(?:individual|single-company|tech|technology) (?:stocks?|shares?)\b|科技股|个股|個股", re.I),
    "crypto": re.compile(rf"(?:{_BITCOIN.pattern})|\b(?:crypto(?:currenc(?:y|ies))?|ethereum)\b|加密货币|加密貨幣", re.I),
    "options": re.compile(r"\b(?:options trading|trad(?:e|ing) (?:[^.?!\n]{1,45},\s*)?options|(?:stock|call|put) options|calls and puts)\b|期权|期權", re.I),
}
_EXAMPLE_SYMBOLS = {
    "SPY": _INSTRUMENTS["sp500"], "GLD": _INSTRUMENTS["gold"], "NVDA": _NVIDIA, "BTC-USD": _BITCOIN,
}


def _stated_point(pattern: re.Pattern, clause: str) -> bool:
    return any(not _NEAR_NEGATION.search(clause[:match.start()]) for match in pattern.finditer(clause))


def _mentioned_instrument(pattern: re.Pattern, clauses: list[str]) -> bool:
    for clause in clauses:
        for section in _EXCLUSION_BOUNDARY.split(clause):
            for match in pattern.finditer(section):
                before = section[:match.start()]
                after = section[match.end():]
                if not (_NEAR_NEGATION.search(before) or _PRECEDING_EXCLUSION.search(before)
                        or _EXCLUSION_LIST.search(before) or _FOLLOWING_EXCLUSION.search(after)):
                    return True
    return False


def _personal_statements(clause: str) -> list[str]:
    reports_other_person = bool(_OTHER_PERSON.search(clause))
    return [
        statement for part in _STATEMENT_BOUNDARY.split(clause) if (statement := part.strip())
        and not _OTHER_PERSON.search(statement)
        and not (reports_other_person and _QUOTED_STATEMENT.search(statement))
    ]


def _cash_statements(clauses: list[str]):
    for index, clause in enumerate(clauses):
        for statement in _personal_statements(clause):
            if not _OWN_POSITION.search(statement) or _UNASSERTED_CASH.search(statement):
                continue
            if _stated_point(_CASH, statement):
                amounts = [
                    match for match in _AMOUNT.finditer(statement) if _BALANCE_CONNECTOR.search(statement[:match.start()])
                ]
                yield index, statement, amounts, True
            elif balance := _DIRECT_BALANCE.search(statement):
                start = _APPROXIMATION.match(statement, balance.end()).end()
                if amount := _AMOUNT.match(statement, start):
                    yield index, statement, [amount], False


def balance_currency_code(source: str | None) -> str | None:
    """Return the ISO code for a recognized currency excerpt."""
    if not isinstance(source, str):
        return None
    return next((code for code, alias in _CURRENCY_ALIASES.items() if re.fullmatch(alias, source.strip(), re.I)), None)


def _amount_value(literal):
    match = _AMOUNT_VALUE.search(literal)
    digits = match["digits"].replace(",", "").replace("，", "")
    scale = _AMOUNT_SCALE.get((match["scale"] or "").lower(), 0)
    sign = "-" if set(literal[:match.start()]) & {"-", "−"} else ""
    return Decimal(f"{sign}{digits}e{scale}")


def _balance_facts(clauses, points):
    saved, other, references = [], [], []
    for index, statement, amounts, names_cash in _cash_statements(clauses):
        if names_cash:
            points.setdefault("cash_position", statement)
        for match in amounts:
            suffix = _INLINE_CURRENCY.match(statement, match.end())
            end = suffix.end() if suffix else match.end()
            if _OTHER_AMOUNT_SUFFIX.match(statement[end:]):
                continue
            currencies = [currency[0] for currency in _EXPLICIT_CURRENCY.finditer(match[0])]
            if suffix:
                currencies.append(suffix["currency"])
            (saved if names_cash else other).append((index, match[0], currencies))

    declarations = []
    for index, clause in enumerate(clauses):
        if match := _CURRENCY_DECLARATION.fullmatch(clause):
            currency, alias, correction, excluded = match.group("currency", "alias", "correction", "excluded")
            corrected = bool(correction or excluded and balance_currency_code(excluded) != balance_currency_code(currency))
            declarations.append((index, corrected, (currency, alias)))
        if amount := _AMOUNT.match(clause, _BALANCE_REFERENCE.match(clause).end()):
            if match := _BALANCE_REFERENCE_CURRENCY.match(clause, amount.end()):
                currencies = [currency[0] for currency in _EXPLICIT_CURRENCY.finditer(amount[0])]
                currencies.extend(match.group("currency", "alias"))
                references.append((index, amount[0], currencies))

    balances = (saved or other) + references
    if not balances:
        return None
    if len({_amount_value(amount) for _, amount, _ in balances}) > 1:
        return "conflicting_amounts"
    points["amount"] = balances[0][1]

    found = {}
    currency_statements = [(index, False, currencies) for index, _, currencies in balances] + declarations
    for _, correction, currencies in sorted(currency_statements, key=lambda item: item[0]):
        if correction:
            found.clear()
        for currency in currencies:
            if code := balance_currency_code(currency):
                found.setdefault(code, currency)
    if len(found) > 1:
        return "conflicting_currencies"
    if found:
        points["currency"] = next(iter(found.values()))
    return None


def planning_context(text: str) -> dict:
    """Extract source excerpts and mentioned instruments independently of routing."""
    if not isinstance(text, str) or len(text) > 8000:
        return {"points": {}, "instruments": (), "examples": (), "financial": False}

    clauses = [match[0].strip() for match in _CLAUSE.finditer(text) if match[0].strip()]
    points = {}
    for name, pattern in _POINTS.items():
        for clause in clauses:
            if name in {"peer_trading", "return_claim"}:
                if _stated_point(pattern, clause):
                    points[name] = clause
                    break
                continue
            statements = _personal_statements(clause)
            matches = [
                statement for statement in statements
                if not (name == "spending" and _SPENDING_EFFECT.search(statement))
                and _stated_point(pattern, statement)
            ]
            if matches:
                points[name] = clause if len(matches) == len(statements) and not _OTHER_PERSON.search(clause) else matches[0]
                break

    balance_issue = _balance_facts(clauses, points)

    instruments = tuple(name for name, pattern in _INSTRUMENTS.items() if _mentioned_instrument(pattern, clauses))
    examples = tuple(symbol for symbol, pattern in _EXAMPLE_SYMBOLS.items() if _mentioned_instrument(pattern, clauses))
    planning_facts = points.keys() & {"cash_position", "growth", "beginner", "return_claim"}
    financial = bool(instruments or planning_facts or _FINANCIAL_TOPIC.search(text))
    context = {"points": points, "instruments": instruments, "examples": examples, "financial": financial}
    if balance_issue:
        context["balance_issue"] = balance_issue
    return context


def parse_planning_request(text: str, *, require_decision: bool = False) -> dict | None:
    """Recognize investment decisions and retain only evidence stated by the user."""
    if not isinstance(text, str) or len(text) > 8000 or _EXACT_TRADE.search(text):
        return None
    if _stated_point(_EXPLICIT_ANALYSIS, text):
        return None

    context = planning_context(text)
    points = context["points"]
    personal_goal = not require_decision and bool(points.keys() & {"spending", "growth", "inflation"}) and len(points) > 1
    if context["financial"] and (_DECISION_SIGNAL.search(text) or personal_goal or "return_claim" in points):
        return {name: value for name, value in context.items() if name != "financial"}
    return None
