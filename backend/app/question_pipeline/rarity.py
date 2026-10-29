from dataclasses import dataclass

from app.models import TIER_POINTS, RarityTier


@dataclass(frozen=True)
class RarityEvidence:
    corpus_frequency: float | None = None
    pageviews_percentile: float | None = None
    dataset_popularity: float | None = None
    recognition_estimate: float | None = None
    human_adjustment: float = 0.0


@dataclass(frozen=True)
class RarityResult:
    familiarity: float
    tier: RarityTier
    points: int
    model_version: str = "brillion-rarity-v1"


def estimate_rarity(evidence: RarityEvidence) -> RarityResult:
    """Weighted, deterministic familiarity estimate on a 0..1 scale.

    Signals are normalized within a question-type-specific importer before this function.
    Recognition is strongest; behavioral popularity breaks ties. Missing signals are omitted
    rather than treated as zero.
    """
    weighted = [
        (evidence.recognition_estimate, 0.45),
        (evidence.pageviews_percentile, 0.25),
        (evidence.dataset_popularity, 0.20),
        (evidence.corpus_frequency, 0.10),
    ]
    available = [(value, weight) for value, weight in weighted if value is not None]
    if not available:
        raise ValueError("At least one familiarity signal is required")
    familiarity = sum(float(value) * weight for value, weight in available) / sum(weight for _, weight in available)
    familiarity = max(0.0, min(1.0, familiarity + evidence.human_adjustment))
    if familiarity >= 0.78:
        tier = RarityTier.COMMON
    elif familiarity >= 0.62:
        tier = RarityTier.PREDICTABLY_OBSCURE
    elif familiarity >= 0.43:
        tier = RarityTier.UNCOMMON
    elif familiarity >= 0.24:
        tier = RarityTier.RARE
    elif familiarity >= 0.10:
        tier = RarityTier.DEEP_CUT
    else:
        tier = RarityTier.BRILLION
    return RarityResult(familiarity=familiarity, tier=tier, points=TIER_POINTS[tier])


def assign_designated_brillion(results: list[tuple[str, RarityResult, float]]) -> str:
    """Select one rare, reviewed candidate using rarity plus interestingness (0..1)."""
    eligible = [item for item in results if item[1].familiarity <= 0.18 and item[2] >= 0.55]
    if not eligible:
        raise ValueError("No answer meets Brillion discoverability and interestingness criteria")
    return min(eligible, key=lambda item: (item[1].familiarity, -item[2], item[0]))[0]
