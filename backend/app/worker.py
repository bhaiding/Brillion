import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import QuestionGenerationJob
from app.question_pipeline.openai_generation import generate_candidate_ideas

logger = logging.getLogger("brillion.worker")


async def claim_job() -> QuestionGenerationJob | None:
    async with SessionLocal() as db:
        job = await db.scalar(
            select(QuestionGenerationJob)
            .where(QuestionGenerationJob.status == "queued")
            .order_by(QuestionGenerationJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job:
            job.status = "running"
            await db.commit()
            await db.refresh(job)
        return job


async def process(job: QuestionGenerationJob) -> None:
    async with SessionLocal() as db:
        attached = await db.get(QuestionGenerationJob, job.id)
        if not attached:
            return
        try:
            if attached.job_type == "generate_candidates":
                batch, usage = await generate_candidate_ideas(
                    attached.parameters["category"], int(attached.parameters["count"])
                )
                attached.result = {"ideas": [idea.model_dump() for idea in batch.ideas]}
                attached.prompt_tokens = usage["input_tokens"]
                attached.completion_tokens = usage["output_tokens"]
                attached.status = "awaiting_review"
            else:
                raise ValueError(f"Unsupported job type: {attached.job_type}")
        except Exception as exc:
            logger.exception("generation_job_failed", extra={"job_id": str(attached.id)})
            attached.status = "failed"
            attached.error = str(exc)[:2000]
        await db.commit()


async def run() -> None:
    logger.info("question_worker_started", extra={"started_at": datetime.now(UTC).isoformat()})
    while True:
        job = await claim_job()
        if job:
            await process(job)
        else:
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run())
