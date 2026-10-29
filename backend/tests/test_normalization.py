import pytest

from app.normalization import conservative_fuzzy_score, fuzzy_threshold, normalize_answer


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Côte d’Ivoire  ", "cote d ivoire"),
        ("Romeo & Juliet", "romeo and juliet"),
        ("Sgt. Pepper's", "sgt pepper s"),
        ("THE   NETHERLANDS", "the netherlands"),
    ],
)
def test_normalization(raw: str, expected: str) -> None:
    assert normalize_answer(raw) == expected


def test_fuzzy_matching_is_conservative_for_short_answers() -> None:
    assert fuzzy_threshold("mars") == 1.0
    assert conservative_fuzzy_score("mars", "marx") < fuzzy_threshold("mars")


def test_small_typo_in_long_answer_scores_highly() -> None:
    query = normalize_answer("Luxemborg")
    candidate = normalize_answer("Luxembourg")
    assert conservative_fuzzy_score(query, candidate) >= fuzzy_threshold(query)
