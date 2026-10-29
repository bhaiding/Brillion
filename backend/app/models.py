import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Normalize driver-returned timestamps; SQLite drops timezone metadata in tests."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class GameState(enum.StrEnum):
    LOBBY = "LOBBY"
    QUESTION_PREVIEW = "QUESTION_PREVIEW"
    ANSWERING = "ANSWERING"
    SCORING = "SCORING"
    REVEAL = "REVEAL"
    LEADERBOARD = "LEADERBOARD"
    FINISHED = "FINISHED"


class ReviewStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class RarityTier(enum.StrEnum):
    COMMON = "common"
    PREDICTABLY_OBSCURE = "predictably_obscure"
    UNCOMMON = "uncommon"
    RARE = "rare"
    DEEP_CUT = "deep_cut"
    BRILLION = "brillion"


TIER_POINTS = {
    RarityTier.COMMON: 10,
    RarityTier.PREDICTABLY_OBSCURE: 15,
    RarityTier.UNCOMMON: 30,
    RarityTier.RARE: 60,
    RarityTier.DEEP_CUT: 85,
    RarityTier.BRILLION: 100,
}


class Question(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.DRAFT, index=True)
    family_friendly: Mapped[bool] = mapped_column(Boolean, default=True)
    versions: Mapped[list["QuestionVersion"]] = relationship(
        back_populates="question", foreign_keys="QuestionVersion.question_id"
    )


class QuestionVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "question_versions"
    __table_args__ = (UniqueConstraint("question_id", "version", name="uq_question_version"),)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(40), default="mixed")
    eligibility_criteria: Mapped[str] = mapped_column(Text)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_status: Mapped[str] = mapped_column(String(40), default="pending")
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scoring_model_version: Mapped[str] = mapped_column(String(40), default="brillion-rarity-v1")
    question: Mapped[Question] = relationship(back_populates="versions", foreign_keys=[question_id])
    answers: Mapped[list["Answer"]] = relationship(back_populates="question_version", cascade="all, delete-orphan")


class Answer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("question_version_id", "normalized_name", name="uq_answer_normalized"),
        CheckConstraint("points IN (10, 15, 30, 60, 85, 100)", name="ck_answer_points"),
        Index("ix_answers_question_normalized", "question_version_id", "normalized_name"),
    )
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_versions.id", ondelete="CASCADE"), index=True
    )
    canonical_name: Mapped[str] = mapped_column(String(240))
    normalized_name: Mapped[str] = mapped_column(String(240))
    tier: Mapped[RarityTier] = mapped_column(Enum(RarityTier))
    points: Mapped[int] = mapped_column(Integer)
    familiarity: Mapped[float] = mapped_column(Float)
    familiarity_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_metadata: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation_status: Mapped[str] = mapped_column(String(40), default="verified")
    interesting_fact: Mapped[str | None] = mapped_column(Text)
    is_designated_brillion: Mapped[bool] = mapped_column(Boolean, default=False)
    question_version: Mapped[QuestionVersion] = relationship(back_populates="answers")
    aliases: Mapped[list["AnswerAlias"]] = relationship(back_populates="answer", cascade="all, delete-orphan")
    sources: Mapped[list["AnswerSource"]] = relationship(back_populates="answer", cascade="all, delete-orphan")


class AnswerAlias(UUIDMixin, Base):
    __tablename__ = "answer_aliases"
    __table_args__ = (
        UniqueConstraint("question_version_id", "normalized_alias", name="uq_alias_per_question"),
        Index("ix_alias_lookup", "question_version_id", "normalized_alias"),
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"))
    question_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_versions.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(240))
    normalized_alias: Mapped[str] = mapped_column(String(240))
    answer: Mapped[Answer] = relationship(back_populates="aliases")


class AnswerSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answer_sources"
    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(String(160))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    answer: Mapped[Answer] = relationship(back_populates="sources")


class RarityEvaluation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rarity_evaluations"
    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"))
    model_version: Mapped[str] = mapped_column(String(60))
    raw_evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    familiarity_estimate: Mapped[float] = mapped_column(Float)
    assigned_tier: Mapped[RarityTier] = mapped_column(Enum(RarityTier))
    review_status: Mapped[str] = mapped_column(String(40), default="pending")


class Room(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rooms"
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    host_secret_hash: Mapped[str] = mapped_column(String(128))
    state: Mapped[GameState] = mapped_column(Enum(GameState), default=GameState.LOBBY, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    host_player_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    players: Mapped[list["RoomPlayer"]] = relationship(back_populates="room")
    games: Mapped[list["GameSession"]] = relationship(back_populates="room")


class RoomPlayer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "room_players"
    __table_args__ = (UniqueConstraint("room_id", "nickname_normalized", name="uq_room_nickname"),)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(32))
    nickname_normalized: Mapped[str] = mapped_column(String(32))
    session_hash: Mapped[str] = mapped_column(String(128), unique=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    room: Mapped[Room] = relationship(back_populates="players")
    submissions: Mapped[list["PlayerSubmission"]] = relationship(back_populates="player")


class GameSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "game_sessions"
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    selection_seed: Mapped[str] = mapped_column(String(64))
    question_version_ids: Mapped[list[str]] = mapped_column(JSON)
    current_round_index: Mapped[int] = mapped_column(Integer, default=-1)
    state: Mapped[GameState] = mapped_column(Enum(GameState), default=GameState.QUESTION_PREVIEW)
    state_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    room: Mapped[Room] = relationship(back_populates="games")
    rounds: Mapped[list["GameRound"]] = relationship(back_populates="game")


class GameRound(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "game_rounds"
    __table_args__ = (UniqueConstraint("game_id", "round_index", name="uq_game_round"),)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True)
    round_index: Mapped[int] = mapped_column(Integer)
    question_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_versions.id"))
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    state: Mapped[GameState] = mapped_column(Enum(GameState), default=GameState.QUESTION_PREVIEW)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game: Mapped[GameSession] = relationship(back_populates="rounds")
    submissions: Mapped[list["PlayerSubmission"]] = relationship(back_populates="round")


class PlayerSubmission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "player_submissions"
    __table_args__ = (UniqueConstraint("round_id", "player_id", name="uq_round_player_submission"),)
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_rounds.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("room_players.id", ondelete="CASCADE"), index=True)
    raw_answer: Mapped[str] = mapped_column(String(240))
    normalized_answer: Mapped[str] = mapped_column(String(240))
    matched_answer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answers.id"))
    match_method: Mapped[str | None] = mapped_column(String(40))
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    points: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[RarityTier | None] = mapped_column(Enum(RarityTier))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    adjudication_status: Mapped[str] = mapped_column(String(40), default="final")
    player: Mapped[RoomPlayer] = relationship(back_populates="submissions")
    round: Mapped[GameRound] = relationship(back_populates="submissions")


class AnswerAttempt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answer_attempts"
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_rounds.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("room_players.id", ondelete="CASCADE"), index=True)
    raw_answer: Mapped[str] = mapped_column(String(240))
    normalized_answer: Mapped[str] = mapped_column(String(240), index=True)
    recognized: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    match_method: Mapped[str | None] = mapped_column(String(40))


class ScoringEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scoring_events"
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("player_submissions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40))
    previous_points: Mapped[int] = mapped_column(Integer, default=0)
    new_points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120))


class AnswerDispute(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "answer_disputes"
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("player_submissions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    player_reason: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestionGenerationJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "question_generation_jobs"
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    job_type: Mapped[str] = mapped_column(String(60))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class QuestionReview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "question_reviews"
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_versions.id", ondelete="CASCADE"), index=True
    )
    reviewer: Mapped[str] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)


class AdminUser(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "admin_users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
