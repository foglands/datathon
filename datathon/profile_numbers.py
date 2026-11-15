"""Ground supported Profile limits in the investor's operative English or French text."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass


_WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split(), range(20),
))
_TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
_FRENCH_WORDS = dict(zip(
    "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize "
    "dix-sept dix-huit dix-neuf vingt".split(), range(21),
))
NUMBER = (
    r"\d{1,3}(?:[.,]\d{1,2})?|one hundred|"
    r"(?:" + "|".join(_TENS) + r")(?:[ -](?:" + "|".join(tuple(_WORDS)[1:10]) + r"))?|"
    + "|".join(_WORDS | _FRENCH_WORDS)
)
POINTS = (r"(?:\s+(?:percentage\s+points?|points?\s+of\s+portfolio\s+weight|"
          r"points?\s+de\s+pourcentage)(?!\w)|[-–]percentage[-–]points?(?!\w))")
_NUMERIC_TERMS = re.compile(
    r"(?<![\w.,+−-])(?P<amount>" + NUMBER + r")"
    r"(?:(?P<percent>\s*%|\s+(?:percent|pour\s+cent)\b)|(?P<points>" + POINTS + r"))"
    r"|(?<![\w.,+−-])(?P<bps>\d{1,5})\s+(?:basis\s+points?|bps|points?\s+de\s+base)\b",
    re.IGNORECASE,
)
_RULE_FIELDS = ("limit_bps", "reserve_floor_bps", "issuer_cap_bps")
_SENTENCE = re.compile(r"(?:[^;!?\n.]|\.(?!\s|$))+")
_RULE_BOUNDARY = re.compile(
    r"\s*,?\s+\b(?:and|et)\s+(?=(?:I\s+)?(?:keep|leave|retain|maintain|require|cap|limit|"
    r"gardez|conservez|maintenez|limitez|plafonnez)\b|(?:my|the)\s+(?:minimum|maximum|reserve|"
    r"historical loss|terminal loss|issuer cap)\b)", re.IGNORECASE,
)
_CORRECTION = re.compile(
    r"\b(?:new user clarification or correction \(takes precedence\)|correction|rectification|"
    r"nouvelle consigne)\s*:", re.IGNORECASE,
)
_INSTEAD_OF = re.compile(r"\b(?:instead of|rather than|au lieu de|plutôt que)\b", re.IGNORECASE)
_REMOVE = re.compile(
    r"\b(?:(?:do not|don['’]t|no longer) (?:apply|want|require|use|enforce|impose)|"
    r"remove|drop|cancel|without|supprimez|(?:n['’]appliquez|n['’]exigez) plus)\b", re.IGNORECASE,
)
_NO_RULE = re.compile(
    r"(?:^|\b(?:there is|impose|apply|have|given|want)\s+)\s*"
    r"no (?:[\w-]+\s+){0,3}(?:cap|limit|floor)\b|\baucun(?:e)? (?:[\w-]+\s+){0,3}"
    r"(?:plafond|limite|plancher)\b", re.IGNORECASE,
)
_NON_OPERATIVE = re.compile(
    r"\b(?:for (?:context|comparison|example) only|for example|third.party|unadopted|"
    r"(?:adviser|advisor|analyst|broker|student) (?:said|suggests?|suggested|recommended|wrote|estimated)|"
    r"(?:an?|the|this) (?:example|sample|illustration) (?:shows?|lists?|says?|has|includes?|maximum)|"
    r"(?:was|were|observed|reported|estimated|reached|hit|equaled)|à titre d['’]exemple)\b",
    re.IGNORECASE,
)
_REJECTED = re.compile(
    r"\b(?:(?:do not|don['’]t|never|no longer) (?:want|require|apply|adopt|use|enforce|impose|need|accept)|"
    r"I (?:reject|decline|disavow)|pas obligatoire|"
    r"ne (?:voulez|veux|souhaite|faut) pas|n['’](?:adopte|exige) pas)\b", re.IGNORECASE,
)
_UNCERTAIN = re.compile(
    r"\b(?:if|unless|could|might|maybe|seems?|approximately|roughly|around|between|"
    r"hypothetical|for example|for illustration|si|sauf|pourrait|peut-être|environ|entre)\b",
    re.IGNORECASE,
)
_UPPER_BOUND = re.compile(
    r"\b(?:cap(?:s|ped)?|limit(?:s|ed)?|maximum|maximal(?:e)?|at most|no (?:more|greater) than|"
    r"(?:cannot|can['’]t) (?:lose|exceed)|(?:may|must|should) not exceed|cutoff|threshold|ceiling|allowable|"
    r"plafond|plafonne[rz]?|limit(?:e|er|ez|ée|é)|au plus|ne peut pas dépasser|"
    r"ne doit pas dépasser|ne (?:perds?|perdre) pas plus de)\b", re.IGNORECASE,
)
_LOWER_BOUND = re.compile(
    r"\b(?:at least|minimum|minimal(?:e)?|floor|no less than|au moins|plancher)\b", re.IGNORECASE,
)
_RESERVE_ACTION = re.compile(
    r"\b(?:keep|retain|leave|maintain|hold|gardez|garder|conservez|conserver|maintenez|maintenir)\b",
    re.IGNORECASE,
)
_RESERVE_ASSET = re.compile(r"\bZST(?:\.TO)?\b", re.IGNORECASE)
_ISSUER_ASSET = re.compile(r"\b(?:NVDA|NVIDIA)\b", re.IGNORECASE)
_COMBINED_EXPOSURE = re.compile(
    r"\b(?:total(?:e)?|aggregat(?:e|ed)|combined|issuer|émetteur|including (?:\w+\s+){0,3}(?:funds|indirect)|"
    r"indirect(?:ly|e)? (?:holdings?|common.equity|exposure)|added together|"
    r"détenues? indirectement|y compris (?:\w+\s+){0,3}(?:fonds|indirecte?))\b", re.IGNORECASE,
)
_DIRECT_ONLY = re.compile(
    r"\b(?:direct(?:ly)? (?:held )?(?:only|alone)|only (?:my )?direct|excluding (?:\w+\s+){0,4}(?:funds?|indirect)|"
    r"sans (?:les |l['’])?(?:fonds|indirecte?))\b", re.IGNORECASE,
)
_LOSS = re.compile(r"\b(?:loss(?:es)?|lose|pertes?|perdre)\b", re.IGNORECASE)
_LOSS_METRICS = {
    "terminal_loss": re.compile(
        r"\b(?:terminal[-\s]+loss(?:es)?|(?:end[-\s]+to[-\s]+end|start[-\s]+to[-\s]+end|"
        r"start[-\s]+to[-\s]+finish)\s+loss(?:es)?|ending value[^!?;\n]{0,120}below (?:the )?opening value|"
        r"perte(?:s)? (?:terminale?s?|finale?s?)|perte(?:s)? (?:de |du )?(?:début|la valeur initiale)"
        r"[^.!?]{0,90}(?:fin|finale))\b", re.IGNORECASE,
    ),
    "max_drawdown": re.compile(
        r"\b(?:drawdown|peak[-\s]+to[-\s]+trough|decline from (?:a |the )?prior peak|"
        r"(?:baisse|repli|retrait) maximal(?:e)?|baisse(?:[^.!?]{0,50})du (?:sommet|pic) au creux)\b",
        re.IGNORECASE,
    ),
}


def percent_to_basis_points(token):
    token = token.lower()
    if token[0].isdigit():
        whole, _, decimals = token.replace(",", ".").partition(".")
        return int(whole) * 100 + int(decimals.ljust(2, "0"))
    if token == "one hundred":
        return 10000
    if token in _WORDS:
        return _WORDS[token] * 100
    if token in _FRENCH_WORDS:
        return _FRENCH_WORDS[token] * 100
    tens, _, ones = token.replace("-", " ").partition(" ")
    return (_TENS[tens] + _WORDS.get(ones, 0)) * 100


@dataclass(frozen=True)
class Binding:
    amount: int | None
    metric: str | None
    excerpt: str
    removed: bool = False


def _amounts(clause, *, portfolio_points):
    return {
        int(match["bps"]) if match["bps"] else percent_to_basis_points(match["amount"])
        for match in _NUMERIC_TERMS.finditer(clause)
        if not match["points"] or portfolio_points
    }


def _clauses(visible):
    """Split active prose while retaining original character offsets."""
    for sentence in _SENTENCE.finditer(visible):
        cursor = sentence.start()
        for boundary in _RULE_BOUNDARY.finditer(visible, sentence.start(), sentence.end()):
            yield cursor, boundary.start()
            cursor = boundary.end()
        # Preserve trailing full stops in an excerpt without reading through a masked quote.
        yield cursor, sentence.end() + int(visible[sentence.end():sentence.end() + 1] == ".")


def _rule_for(clause):
    """Classify a numeric clause by its named rule and comparison direction."""
    metrics = [definition for definition, pattern in _LOSS_METRICS.items() if pattern.search(clause)]
    upper = _UPPER_BOUND.search(clause)
    lower = _LOWER_BOUND.search(clause)
    if metrics or _LOSS.search(clause):
        if upper and not lower:
            return "limit_bps", metrics[0] if len(metrics) == 1 else None
        return None, None
    if upper and not lower and _ISSUER_ASSET.search(clause) and _COMBINED_EXPOSURE.search(clause) and not _DIRECT_ONLY.search(clause):
        return "issuer_cap_bps", None
    if _RESERVE_ASSET.search(clause) and not upper and (lower or _RESERVE_ACTION.search(clause)):
        return "reserve_floor_bps", None
    return None, None


def _removed_rule(clause):
    if not (_NO_RULE.search(clause) or (_REMOVE.search(clause)
            and (_UPPER_BOUND.search(clause) or _LOWER_BOUND.search(clause)))):
        return None
    if _LOSS.search(clause) or any(pattern.search(clause) for pattern in _LOSS_METRICS.values()):
        return "limit_bps"
    if _ISSUER_ASSET.search(clause) and _COMBINED_EXPOSURE.search(clause) and not _DIRECT_ONLY.search(clause):
        return "issuer_cap_bps"
    if _RESERVE_ASSET.search(clause):
        return "reserve_floor_bps"
    return None


def _bindings(request, visible):
    found = {field: [] for field in _RULE_FIELDS}
    corrections = tuple(match.end() for match in _CORRECTION.finditer(visible))
    for start, end in _clauses(visible):
        revision = bisect_right(corrections, end - 1)
        if revision:
            start = max(start, corrections[revision - 1])
        clause = visible[start:end]
        comparison = _INSTEAD_OF.split(clause, maxsplit=1)[0] if revision else clause
        excerpt = request[start:end].strip()
        if _NON_OPERATIVE.search(comparison):
            continue
        if field := _removed_rule(comparison):
            found[field].append((revision, Binding(None, None, excerpt, removed=True)))
            continue
        if _NO_RULE.search(comparison) or _REJECTED.search(comparison):
            continue
        field, metric = _rule_for(comparison)
        if field is None:
            continue
        amounts = _amounts(comparison, portfolio_points=field == "reserve_floor_bps")
        amount = next(iter(amounts)) if len(amounts) == 1 else None
        if (amount is not None and not 0 <= amount <= 10000) or _UNCERTAIN.search(comparison):
            amount = None
        found[field].append((revision, Binding(amount, metric, excerpt)))
    # An explicit correction supersedes only fields it actually addresses.
    current = {}
    for field, candidates in found.items():
        latest = max((revision for revision, _ in candidates), default=0)
        current[field] = [entry for revision, entry in candidates if revision == latest]
    return current


def ground_limits(request, visible, fields: Mapping, supplied: Mapping, *, hold_loss_metric=False):
    """Return verified rules and the optional fields that require direct entry."""
    grounded = {}
    unverified = []
    loss_metric = None
    for field, candidates in _bindings(request, visible).items():
        proposed = fields[field]
        if not candidates and proposed is None:
            continue
        coherent = {(item.amount, item.metric, item.removed) for item in candidates}
        if hold_loss_metric and field == "limit_bps":
            coherent = {(amount, None, removed) for amount, _, removed in coherent}
        bound = candidates[0] if len(coherent) == 1 else None
        if bound and bound.removed:
            grounded[field] = bound
            continue
        if bound is None or bound.amount is None or (proposed is not None and proposed != bound.amount):
            unverified.append(field)
            continue
        excerpt = supplied.get(field)
        # A provided source excerpt must cite the checked rule and its one amount.
        if excerpt and not (excerpt in bound.excerpt and _amounts(excerpt, portfolio_points=field == "reserve_floor_bps")
                            == {bound.amount}):
            unverified.append(field)
            continue
        grounded[field] = bound
        if field == "limit_bps" and not hold_loss_metric:
            loss_metric = bound.metric
    return grounded, unverified, loss_metric
