"""Validate English questions locally before sending text to a model or tool."""

from functools import lru_cache
import re
from unicodedata import name, normalize


ENGLISH_QUESTION_MESSAGE = "Please enter your question in English, using a short sentence."
_TICKER_PAIR = re.compile(
    r"\s*\$?[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?\s+(?:vs\.?|versus)\s+"
    r"\$?[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?\s*[?.]?\s*"
)
_ABBREVIATION = re.compile(r"(?<!\w)\$?[A-Z]{2,8}(?:[.-][A-Z0-9]{1,5})?(?!\w)")
_PROPER_NAMES = re.compile(r"\b[A-ZÀ-ÖØ-Þ][^\W\d_]+(?:[ \t]+[A-ZÀ-ÖØ-Þ][^\W\d_]+)+")
_LATIN_NAME = re.compile(r"\b[A-ZÀ-ÖØ-Þ][^\W\d_]*(?<![A-Z])\b")
_STANDALONE_VALUE = re.compile(
    r"(?:(?:CAD|USD|EUR|GBP|CNY|HKD)\s*)?[$€£]?[+-]?\d+(?:[,.]\d+)*(?:\s*(?:%|bps|CAD|USD|EUR|GBP|CNY|HKD))?",
    re.I,
)
_CLAUSE_END = re.compile(r"(?<=[.!?;])\s+|\n+")
_FINANCE_TERMS = {"bitcoin", "crypto", "cryptoasset", "ethereum", "daycare", "etf", "gic"}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


@lru_cache(maxsize=1)
def _classifier():
    from langid.langid import LanguageIdentifier, model

    return LanguageIdentifier.from_modelstring(model, norm_probs=True)


@lru_cache(maxsize=1)
def _english_words():
    from english_words import get_english_words_set

    return get_english_words_set(["web2", "gcide"], lower=True) | _FINANCE_TERMS


def _has_short_english_prose(words):
    lexicon = _english_words()
    known = sum(word in lexicon or (word.endswith("s") and word[:-1] in lexicon) for word in words)
    return known == len(words) if len(words) <= 2 else known * 3 >= len(words) * 2


def is_english_question(question: str) -> bool:
    """Treat tickers as identifiers and check the language of the surrounding text."""
    if not isinstance(question, str) or not question.strip():
        return False
    text = normalize("NFKC", question).strip()
    if any(char.isalpha() and not name(char, "").startswith("LATIN") for char in text):
        return False
    if _TICKER_PAIR.fullmatch(text) or _STANDALONE_VALUE.fullmatch(text):
        return True

    if text.isupper():
        prose = text.lower()
    else:
        prose = _ABBREVIATION.sub(" ", text)
        prose = _PROPER_NAMES.sub(lambda match: match[0].split()[0] if match.start() == 0 else " ", prose)
        if len(_WORD.findall(prose)) <= 5:
            prose = _LATIN_NAME.sub(lambda match: match[0] if match[0].isascii() else " ", prose)
    prose = re.sub(r"\bvs\.?(?=\s|$)", "versus", prose, flags=re.I)
    words = _WORD.findall(prose.lower())
    if not words or len(words) <= 5 and not _has_short_english_prose(words):
        return False
    classifier = _classifier()
    language, confidence = classifier.classify(prose)
    if language != "en":
        if len(words) > 5 or confidence >= 0.65:
            return False
        if next(score for code, score in classifier.rank(prose) if code == "en") < 0.08:
            return False
    for clause in _CLAUSE_END.split(prose):
        clause_words = _WORD.findall(clause.lower())
        if 1 <= len(clause_words) <= 5 and not _has_short_english_prose(clause_words):
            return False
        if len(clause_words) >= 2:
            language, confidence = classifier.classify(clause)
            if language != "en" and confidence >= 0.75:
                return False
    return True
