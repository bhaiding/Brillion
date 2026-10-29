import pytest

from app.models import RarityTier
from app.question_pipeline.rarity import RarityEvidence, assign_designated_brillion, estimate_rarity


def test_familiar_answer_is_common() -> None:
    result = estimate_rarity(
        RarityEvidence(recognition_estimate=0.95, pageviews_percentile=0.9, dataset_popularity=0.8)
    )
    assert result.tier == RarityTier.COMMON
    assert result.points == 10


def test_low_familiarity_answer_is_brillion() -> None:
    result = estimate_rarity(
        RarityEvidence(recognition_estimate=0.04, pageviews_percentile=0.08, dataset_popularity=0.1)
    )
    assert result.tier == RarityTier.BRILLION
    assert result.points == 100


def test_requires_real_evidence() -> None:
    with pytest.raises(ValueError):
        estimate_rarity(RarityEvidence())


def test_designated_answer_must_be_rare_and_interesting() -> None:
    rare = estimate_rarity(RarityEvidence(recognition_estimate=0.04))
    common = estimate_rarity(RarityEvidence(recognition_estimate=0.9))
    assert assign_designated_brillion([("obscure", rare, 0.9), ("obvious", common, 1.0)]) == "obscure"
