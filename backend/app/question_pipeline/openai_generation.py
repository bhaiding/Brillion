import asyncio
from typing import Any

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings

settings = get_settings()


class CandidateIdea(BaseModel):
    question: str
    category: str
    eligibility_criteria: str
    suitability_rationale: str
    suggested_authoritative_sources: list[str] = Field(min_length=1)
    exhaustive_set_feasible: bool
    family_friendly: bool = True


class CandidateBatch(BaseModel):
    ideas: list[CandidateIdea]


async def generate_candidate_ideas(category: str, count: int) -> tuple[CandidateBatch, dict[str, int]]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for AI-assisted question generation")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    schema: dict[str, Any] = CandidateBatch.model_json_schema()
    prompt = (
        "Propose open-ended party trivia prompts with finite, objectively verifiable answer sets. "
        "Do not invent answers. Prefer authoritative structured datasets and reject subjective, "
        f"ambiguous, or time-sensitive ideas. Category: {category}. Count: {count}."
    )
    for attempt in range(5):
        try:
            response = await client.responses.create(
                model=settings.openai_model,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "candidate_batch",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
            try:
                batch = CandidateBatch.model_validate_json(response.output_text)
            except ValidationError as exc:
                raise RuntimeError("Model returned malformed structured output") from exc
            usage = getattr(response, "usage", None)
            return batch, {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        except RateLimitError:
            if attempt == 4:
                raise
            await asyncio.sleep(2**attempt)
    raise RuntimeError("Question generation exhausted retry attempts")
