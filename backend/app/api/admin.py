import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_admin
from app.models import (
    TIER_POINTS,
    Answer,
    AnswerAlias,
    AnswerAttempt,
    AnswerDispute,
    Question,
    QuestionGenerationJob,
    QuestionReview,
    QuestionVersion,
    ReviewStatus,
)
from app.normalization import normalize_answer
from app.question_pipeline.importers import IMPORTERS
from app.schemas import (
    AdminAliasCreate,
    AdminAnswerCreate,
    AdminQuestionCreate,
    AdminQuestionUpdate,
    GenerateQuestionsRequest,
    ImportDatasetRequest,
    ResolveDisputeRequest,
)

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_admin)])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/questions", status_code=201)
async def create_question(payload: AdminQuestionCreate, db: Db) -> dict[str, str]:
    if await db.scalar(select(Question).where(Question.slug == payload.slug)):
        raise HTTPException(409, "A question with that slug already exists")
    question = Question(
        slug=payload.slug,
        category=payload.category,
        family_friendly=payload.family_friendly,
        review_status=ReviewStatus.DRAFT,
    )
    db.add(question)
    await db.flush()
    version = QuestionVersion(
        question_id=question.id,
        version=1,
        text=payload.text,
        eligibility_criteria=payload.eligibility_criteria,
        source_references=payload.source_references,
        review_status=ReviewStatus.DRAFT,
        validation_status="pending",
        generation_metadata={"method": "admin_created"},
    )
    db.add(version)
    await db.flush()
    question.active_version_id = version.id
    await db.commit()
    return {"question_id": str(question.id), "version_id": str(version.id), "status": "draft"}


@router.get("/questions")
async def list_questions(
    db: Db,
    search: str | None = None,
    category: str | None = None,
    review_status: ReviewStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    query = select(Question).options(selectinload(Question.versions))
    if search:
        query = query.where(Question.slug.ilike(f"%{search}%"))
    if category:
        query = query.where(Question.category == category)
    if review_status:
        query = query.where(Question.review_status == review_status)
    questions = list((await db.scalars(query.offset(offset).limit(limit))).unique().all())
    return {
        "items": [
            {
                "id": str(q.id),
                "slug": q.slug,
                "category": q.category,
                "review_status": q.review_status.value,
                "active_version_id": str(q.active_version_id) if q.active_version_id else None,
                "versions": len(q.versions),
            }
            for q in questions
        ],
        "offset": offset,
        "limit": limit,
    }


@router.get("/questions/{question_id}")
async def question_detail(question_id: uuid.UUID, db: Db) -> dict:
    question = await db.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.versions).selectinload(QuestionVersion.answers).selectinload(Answer.aliases))
    )
    if not question:
        raise HTTPException(404, "Question not found")
    return {
        "id": str(question.id),
        "slug": question.slug,
        "category": question.category,
        "review_status": question.review_status.value,
        "versions": [
            {
                "id": str(version.id),
                "version": version.version,
                "text": version.text,
                "criteria": version.eligibility_criteria,
                "status": version.review_status.value,
                "answers": [
                    {
                        "id": str(answer.id),
                        "canonical": answer.canonical_name,
                        "aliases": [alias.alias for alias in answer.aliases],
                        "tier": answer.tier.value,
                        "points": answer.points,
                        "familiarity": answer.familiarity,
                        "evidence": answer.familiarity_evidence,
                    }
                    for answer in version.answers
                ],
            }
            for version in question.versions
        ],
    }


@router.patch("/questions/{question_id}")
async def update_question(question_id: uuid.UUID, payload: AdminQuestionUpdate, db: Db) -> dict[str, str]:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    if not question.active_version_id:
        raise HTTPException(409, "Question has no active version")
    current = await db.get(QuestionVersion, question.active_version_id)
    if not current:
        raise HTTPException(409, "Active version is missing")
    if payload.text or payload.eligibility_criteria:
        latest = await db.scalar(
            select(func.max(QuestionVersion.version)).where(QuestionVersion.question_id == question.id)
        )
        replacement = QuestionVersion(
            question_id=question.id,
            version=int(latest or 0) + 1,
            text=payload.text or current.text,
            difficulty=current.difficulty,
            eligibility_criteria=payload.eligibility_criteria or current.eligibility_criteria,
            source_references=current.source_references,
            generation_metadata={
                "derived_from": str(current.id),
                "edited_at": datetime.now(UTC).isoformat(),
            },
            validation_status="pending",
            review_status=ReviewStatus.DRAFT,
            scoring_model_version=current.scoring_model_version,
        )
        db.add(replacement)
        await db.flush()
        question.active_version_id = replacement.id
    if payload.review_status:
        question.review_status = ReviewStatus(payload.review_status)
    await db.commit()
    return {"status": "updated", "question_id": str(question.id)}


@router.post("/questions/{question_id}/publish")
async def publish_question(question_id: uuid.UUID, db: Db) -> dict[str, str]:
    question = await db.get(Question, question_id)
    if not question or not question.active_version_id:
        raise HTTPException(404, "Question or active version not found")
    version = await db.scalar(
        select(QuestionVersion)
        .where(QuestionVersion.id == question.active_version_id)
        .options(selectinload(QuestionVersion.answers))
    )
    if not version or len(version.answers) < 2:
        raise HTTPException(422, "A question needs a complete validated answer set before publication")
    if any(answer.validation_status != "verified" for answer in version.answers):
        raise HTTPException(422, "Every answer must be verified before publication")
    brillion_count = sum(answer.is_designated_brillion for answer in version.answers)
    if brillion_count != 1:
        raise HTTPException(422, "Exactly one answer must be designated as the 100-point answer")
    version.review_status = ReviewStatus.PUBLISHED
    version.validation_status = "validated"
    version.published_at = datetime.now(UTC)
    question.review_status = ReviewStatus.PUBLISHED
    db.add(
        QuestionReview(
            question_version_id=version.id,
            reviewer="admin",
            decision="published",
            notes="Publication checks passed",
        )
    )
    await db.commit()
    return {"status": "published", "version_id": str(version.id)}


@router.post("/question-versions/{version_id}/answers", status_code=201)
async def add_answer(version_id: uuid.UUID, payload: AdminAnswerCreate, db: Db) -> dict[str, str]:
    version = await db.get(QuestionVersion, version_id)
    if not version:
        raise HTTPException(404, "Question version not found")
    if version.review_status == ReviewStatus.PUBLISHED:
        raise HTTPException(409, "Published versions are immutable; create a new version first")
    normalized = normalize_answer(payload.canonical_name)
    duplicate = await db.scalar(
        select(Answer).where(Answer.question_version_id == version_id, Answer.normalized_name == normalized)
    )
    if duplicate:
        raise HTTPException(409, "That answer already exists")
    answer = Answer(
        question_version_id=version_id,
        canonical_name=payload.canonical_name.strip(),
        normalized_name=normalized,
        tier=payload.tier,
        points=TIER_POINTS[payload.tier],
        familiarity=payload.familiarity,
        familiarity_evidence=payload.familiarity_evidence,
        source_metadata=payload.source_metadata,
        interesting_fact=payload.interesting_fact,
        is_designated_brillion=payload.is_designated_brillion,
        validation_status="verified",
    )
    db.add(answer)
    await db.flush()
    for value in payload.aliases:
        db.add(
            AnswerAlias(
                answer_id=answer.id,
                question_version_id=version_id,
                alias=value,
                normalized_alias=normalize_answer(value),
            )
        )
    await db.commit()
    return {"answer_id": str(answer.id), "status": "created"}


@router.post("/answers/{answer_id}/aliases", status_code=201)
async def add_alias(answer_id: uuid.UUID, payload: AdminAliasCreate, db: Db) -> dict[str, str]:
    answer = await db.get(Answer, answer_id)
    if not answer:
        raise HTTPException(404, "Answer not found")
    version = await db.get(QuestionVersion, answer.question_version_id)
    if version and version.review_status == ReviewStatus.PUBLISHED:
        raise HTTPException(409, "Published answer banks are immutable; create a new version first")
    alias = AnswerAlias(
        answer_id=answer.id,
        question_version_id=answer.question_version_id,
        alias=payload.alias.strip(),
        normalized_alias=normalize_answer(payload.alias),
    )
    db.add(alias)
    await db.commit()
    return {"alias_id": str(alias.id), "status": "created"}


@router.post("/generate", status_code=202)
async def queue_generation(payload: GenerateQuestionsRequest, db: Db) -> dict[str, str]:
    job = QuestionGenerationJob(job_type="generate_candidates", parameters=payload.model_dump(), status="queued")
    db.add(job)
    await db.commit()
    return {"job_id": str(job.id), "status": job.status}


@router.post("/import", status_code=202)
async def import_dataset(payload: ImportDatasetRequest, db: Db) -> dict:
    importer = IMPORTERS.get(payload.importer)
    if not importer:
        raise HTTPException(422, f"Unknown importer. Available: {', '.join(IMPORTERS)}")
    entities = await importer.import_entities(payload.payload)
    return {"importer": payload.importer, "entities": [entity.model_dump() for entity in entities]}


@router.get("/jobs")
async def generation_jobs(db: Db, limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    jobs = list(
        (
            await db.scalars(
                select(QuestionGenerationJob).order_by(QuestionGenerationJob.created_at.desc()).limit(limit)
            )
        ).all()
    )
    return [
        {
            "id": str(job.id),
            "status": job.status,
            "type": job.job_type,
            "parameters": job.parameters,
            "result": job.result,
            "prompt_tokens": job.prompt_tokens,
            "completion_tokens": job.completion_tokens,
            "estimated_cost_usd": job.estimated_cost_usd,
            "error": job.error,
        }
        for job in jobs
    ]


@router.get("/quality-metrics")
async def quality_metrics(db: Db) -> dict:
    attempts = int(await db.scalar(select(func.count(AnswerAttempt.id))) or 0)
    rejected = int(
        await db.scalar(select(func.count(AnswerAttempt.id)).where(AnswerAttempt.recognized.is_(False))) or 0
    )
    frequent = (
        await db.execute(
            select(AnswerAttempt.normalized_answer, func.count(AnswerAttempt.id).label("count"))
            .where(AnswerAttempt.recognized.is_(False))
            .group_by(AnswerAttempt.normalized_answer)
            .order_by(func.count(AnswerAttempt.id).desc())
            .limit(25)
        )
    ).all()
    open_disputes = int(
        await db.scalar(select(func.count(AnswerDispute.id)).where(AnswerDispute.status == "open")) or 0
    )
    return {
        "attempts": attempts,
        "rejected_attempts": rejected,
        "rejection_rate": rejected / attempts if attempts else 0,
        "open_disputes": open_disputes,
        "frequent_unrecognized": [{"answer": normalized, "count": count} for normalized, count in frequent],
    }


@router.get("/disputes")
async def disputes(db: Db, status: str = "open") -> list[dict]:
    rows = list(
        (
            await db.scalars(
                select(AnswerDispute).where(AnswerDispute.status == status).order_by(AnswerDispute.created_at)
            )
        ).all()
    )
    return [
        {
            "id": str(row.id),
            "submission_id": str(row.submission_id),
            "status": row.status,
            "reason": row.player_reason,
            "resolution": row.resolution,
        }
        for row in rows
    ]


@router.post("/disputes/{dispute_id}/resolve")
async def resolve_dispute(dispute_id: uuid.UUID, payload: ResolveDisputeRequest, db: Db) -> dict[str, str]:
    dispute = await db.get(AnswerDispute, dispute_id)
    if not dispute or dispute.status != "open":
        raise HTTPException(404, "Open dispute not found")
    from app.models import PlayerSubmission, ScoringEvent

    submission = await db.get(PlayerSubmission, dispute.submission_id, with_for_update=True)
    if not submission:
        raise HTTPException(404, "Submission not found")
    previous = submission.points
    if payload.accepted_answer_id:
        answer = await db.get(Answer, payload.accepted_answer_id)
        if not answer:
            raise HTTPException(422, "Accepted answer was not found")
        submission.matched_answer_id = answer.id
        submission.valid = True
        submission.points = payload.points or answer.points
        submission.tier = answer.tier
        submission.adjudication_status = "accepted_after_review"
    else:
        submission.adjudication_status = "rejected_after_review"
    db.add(
        ScoringEvent(
            submission_id=submission.id,
            event_type="dispute_resolution",
            previous_points=previous,
            new_points=submission.points,
            reason=payload.reason,
            actor="admin",
        )
    )
    dispute.status = "resolved"
    dispute.resolution = payload.reason
    dispute.resolved_by = "admin"
    dispute.resolved_at = datetime.now(UTC)
    await db.commit()
    return {"status": "resolved", "dispute_id": str(dispute.id)}
