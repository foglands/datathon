"""Identify the context a user stated in an open-ended investment question."""

import re


_INTENT = re.compile(
    r"\b(?:how|where) (?:should|can|could|do|would) (?:I|we)\s+"
    r"(?:invest|save|allocate|put|split|protect|start investing)\b"
    r"|\bwhat (?:should|can|could) (?:I|we) (?:do with|invest in|buy)\b"
    r"|\b(?:should|could|can|may) (?:I|we) (?:just |really |simply )?(?:buy|invest|keep|save|put|hold)\b"
    r"|\b(?:can|could|would) you (?:recommend|suggest)\b[^.?!\n]{0,60}\b(?:invest(?:ments?)?|funds?|portfolios?|stocks?)\b"
    r"|\b(?:what are (?:the |my )?(?:options|trade-offs|pros and cons)|"
    r"(?:help (?:me|us) (?:plan|decide|think through))|(?:explain|understand) the (?:risks|trade-offs))\b"
    r"|\b(?:how to|way to) (?:invest|allocate|protect (?:my |our )?(?:money|savings))\b"
    r"|\bis\b[^.?!\n]{1,65}\ba (?:good|sensible|suitable|safe|reasonable) (?:investment|option|choice)\b"
    r"|(?:怎么|怎麼|怎样|怎樣|如何|应不应该|應不應該|该不该|該不該|要不要|是否应该|是否應該|能不能|能否|可以|适不适合|適不適合)"
    r"[^。！？?！\n]{0,22}(?:投资|投資|理财|理財|配置|买|買|存|分配|保值)"
    r"|(?:投资|投資|存款|黄金|黃金)[^。！？?！\n]{0,20}(?:怎么选|怎麼選|如何选择|如何選擇)",
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
_CURRENCY = r"CA\$|US\$|C\$|A\$|CAD|USD|EUR|GBP|CNY|HKD|Canadian dollars?|US dollars?|人民币|人民幣|加元|加币|加幣|美元|港币|港幣|£|€"
_AMOUNT = re.compile(
    rf"(?<![A-Za-z0-9_.+−-])[+−-]?(?:(?:{_CURRENCY}|\$)\s*[+−-]?{_NUMBER}"
    rf"|{_NUMBER}\s*(?:{_CURRENCY}|[万萬](?:元|加元|加币|加幣|美元|人民币|人民幣)?))(?![A-Za-z0-9_])",
    re.I,
)
_EXPLICIT_CURRENCY = re.compile(_CURRENCY, re.I)
_CASH = re.compile(
    r"\b(?:bank account|savings account|savings|saved|cash savings|cash balance|money in (?:the |my |our )?bank|"
    r"money sitting (?:idle|in the bank)|cash sitting (?:idle|in the bank))\b|存款|存[在进進]银行|存[在进進]銀行|银行账户|銀行賬戶|现金余额|現金餘額",
    re.I,
)
_NEAR_NEGATION = re.compile(r"(?:\b(?:not|never|no|don't|didn't|do not|did not)(?:\s+\w+){0,2}|不|没|沒有|没有)\s*$", re.I)
_DURATION = r"(?:\d+|one|two|three|four|five|six|several|a few)\s+(?:months?|years?)"
_STATED_DATE = r"(?:this|next)\s+(?:month|year|spring|summer|fall|autumn|winter)|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+20\d{2}"
_PROMISE = r"\b(?:guarantee(?:d|s)?|assured)\b|保证|保證|承诺|承諾|保證獲利"
_RETURN = r"\b(?:returns?|yields?|profits?|gains?|earnings)\b|回报|回報|收益|年化|利率|獲利|盈利"
_RETURN_CLAIM = re.compile(rf"(?:{_PROMISE}).{{0,80}}(?:{_RETURN})|(?:{_RETURN}).{{0,55}}(?:{_PROMISE})", re.I)
_NVIDIA = re.compile(r"\b(?:Nvidia|NVDA)\b|英伟达|英偉達|輝達", re.I)
_BITCOIN = re.compile(r"\b(?:bitcoin|btc(?:-usd)?)\b|比特币|比特幣", re.I)
_POINTS = {
    "spending": re.compile(
        r"\b(?:expenses|bills|tuition|childcare|daycare|living costs|down payment|rent payments|"
        r"need (?:the|this|my|our) money|planned withdrawal)\b|宝宝开销|寶寶開銷|孩子开销|孩子開銷|育儿|育兒|学费|學費|首付|开销|開銷|开支|開支|支出|用钱|用錢",
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
        r"|(?:担心|擔心|怕|害怕)[^。！？\n]{0,16}(?:亏钱|虧錢|亏损|虧損|大跌|暴跌|崩盘|崩盤|回撤)"
        r"|(?:亏过钱|虧過錢|亏了钱|虧了錢|亏损过|虧損過|厌恶风险|厭惡風險|不能亏|不能虧|保本)",
        re.I,
    ),
    "timing": re.compile(
        rf"\b(?:time horizon|investment horizon|withdrawal date)\s*(?:is\s+|of\s+|:\s*)(?:{_DURATION}|{_STATED_DATE})\b"
        r"|\b(?:need|withdraw|spend|use|access|pay)\b[^.?!;\n]{0,48}"
        rf"\b(?:in|within|after|by|until|over)\s+(?:{_DURATION}|{_STATED_DATE})\b"
        r"|(?:\d+|[一二三四五六七八九十两兩])?(?:个|個)?(?:月|年|半年)(?:后|後|内|內)[^。！？\n]{0,12}(?:用钱|用錢|提款|取款|支付|付费|付費)",
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
    "gold": re.compile(r"\bgold\b|黄金|黃金|金条|金條", re.I),
    "cash_deposits": re.compile(r"\b(?:GICs?|high-interest savings accounts?|term deposits?|certificates? of deposit)\b|定期存款|高息储蓄|高息儲蓄", re.I),
    "bonds": re.compile(r"\b(?:bonds?|fixed income|treasury bills?|T-bills?)\b|债券|債券|国债|國債", re.I),
    "equity_funds": re.compile(r"\b(?:equity|stock|index)\s+(?:funds?|ETFs?)\b|股票基金|指数基金|指數基金", re.I),
    "individual_stock": re.compile(rf"(?:{_NVIDIA.pattern})|\b(?:individual|single-company|tech|technology) stocks?\b|科技股|个股|個股", re.I),
    "crypto": re.compile(rf"(?:{_BITCOIN.pattern})|\b(?:crypto(?:currenc(?:y|ies))?|ethereum)\b|加密货币|加密貨幣", re.I),
    "options": re.compile(r"\b(?:options trading|trad(?:e|ing) (?:[^.?!\n]{1,45},\s*)?options|(?:stock|call|put) options|calls and puts)\b|期权|期權", re.I),
}
_EXAMPLE_SYMBOLS = {
    "SPY": _INSTRUMENTS["sp500"], "GLD": _INSTRUMENTS["gold"], "NVDA": _NVIDIA, "BTC-USD": _BITCOIN,
}


def _stated_point(pattern: re.Pattern, clause: str) -> bool:
    return any(not _NEAR_NEGATION.search(clause[:match.start()]) for match in pattern.finditer(clause))


def parse_planning_request(text: str) -> dict | None:
    """Extract verbatim planning context without assigning amounts or risk limits."""
    if not isinstance(text, str) or len(text) > 8000 or _EXACT_TRADE.search(text):
        return None
    if _stated_point(_EXPLICIT_ANALYSIS, text):
        return None

    clauses = [match[0].strip() for match in _CLAUSE.finditer(text) if match[0].strip()]
    if not (_INTENT.search(text) or any(_stated_point(_RETURN_CLAIM, clause) for clause in clauses)):
        return None
    points = {}
    for name, pattern in {"cash_position": _CASH, **_POINTS}.items():
        if clause := next((clause for clause in clauses if _stated_point(pattern, clause)), None):
            points[name] = clause

    cash_amounts = {m[0] for clause in clauses if _stated_point(_CASH, clause) for m in _AMOUNT.finditer(clause)}
    amounts = cash_amounts or {match[0] for match in _AMOUNT.finditer(text)}
    if len(amounts) == 1:
        amount = next(iter(amounts))
        points["amount"] = amount
        if currency := _EXPLICIT_CURRENCY.search(amount):
            points["currency"] = currency[0]

    instruments = tuple(name for name, pattern in _INSTRUMENTS.items() if pattern.search(text))
    if not instruments and not points.keys() - {"concentration", "peer_trading", "timing"}:
        return None
    examples = tuple(symbol for symbol, pattern in _EXAMPLE_SYMBOLS.items() if pattern.search(text))
    return {"points": points, "instruments": instruments, "examples": examples}
