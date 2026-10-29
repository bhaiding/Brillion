import re
import unicodedata

from rapidfuzz.fuzz import ratio

NON_WORD = re.compile(r"[^a-z0-9]+")
WHITESPACE = re.compile(r"\s+")


def normalize_answer(value: str) -> str:
    """Normalize human answers while retaining conservative semantic boundaries."""
    value = unicodedata.normalize("NFKD", value.strip().casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("&", " and ")
    value = NON_WORD.sub(" ", value)
    return WHITESPACE.sub(" ", value).strip()


def nickname_key(value: str) -> str:
    return WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).strip()).casefold()


def conservative_fuzzy_score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0
    if abs(len(query) - len(candidate)) > max(2, len(candidate) // 5):
        return 0
    return ratio(query, candidate) / 100


def fuzzy_threshold(value: str) -> float:
    if len(value) <= 4:
        return 1.0
    if len(value) <= 7:
        return 0.90
    return 0.86
