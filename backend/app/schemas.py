import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models import GameState, RarityTier


class RoomSettings(BaseModel):
    question_count: int = Field(default=7, ge=1, le=7)
    answer_seconds: int = Field(default=25, ge=10, le=90)
    categories: list[str] = Field(default_factory=lambda: ["mixed"])
    family_friendly: bool = True
    hide_leaderboard: bool = False
    host_controlled_transitions: bool = True
    automatic_transition_seconds: int = Field(default=8, ge=3, le=30)


class CreateRoomRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    settings: RoomSettings = Field(default_factory=RoomSettings)

    @field_validator("nickname")
    @classmethod
    def clean_host_nickname(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned or any(ord(char) < 32 for char in cleaned):
            raise ValueError("Nickname contains invalid characters")
        return cleaned


class JoinRoomRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)

    @field_validator("nickname")
    @classmethod
    def clean_nickname(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned or any(ord(char) < 32 for char in cleaned):
            raise ValueError("Nickname contains invalid characters")
        return cleaned


class TokenResponse(BaseModel):
    room_code: str
    token: str
    role: Literal["host", "player"]
    player_id: uuid.UUID | None = None


class PlayerView(BaseModel):
    id: uuid.UUID
    nickname: str
    connected: bool
    submitted: bool = False
    score: int = 0


class QuestionView(BaseModel):
    text: str
    category: str
    eligibility_criteria: str


class SubmissionResult(BaseModel):
    accepted: bool
    locked: bool
    message: str
    canonical_answer: str | None = None


class AnswerResultView(BaseModel):
    player_id: uuid.UUID
    nickname: str
    raw_answer: str | None
    canonical_answer: str | None
    valid: bool
    points: int
    tier: RarityTier | None
    total_score: int
    interesting_fact: str | None = None


class LeaderboardEntry(BaseModel):
    rank: int
    player_id: uuid.UUID
    nickname: str
    score: int


class GameStateView(BaseModel):
    server_time: datetime
    room_code: str
    state: GameState
    state_version: int
    host_player_id: uuid.UUID | None
    settings: RoomSettings
    players: list[PlayerView]
    game_id: uuid.UUID | None = None
    round_index: int | None = None
    round_number: int | None = None
    question_count: int = 7
    question: QuestionView | None = None
    deadline_at: datetime | None = None
    results: list[AnswerResultView] | None = None
    leaderboard: list[LeaderboardEntry] | None = None
    final_answers: dict[str, list[dict[str, Any]]] | None = None


class SubmitAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=200)


class UpdateRoomSettingsRequest(BaseModel):
    settings: RoomSettings


class AdvanceRequest(BaseModel):
    expected_state_version: int | None = None


class CreateDisputeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ResolveDisputeRequest(BaseModel):
    accepted_answer_id: uuid.UUID | None = None
    points: int = Field(default=0)
    reason: str = Field(min_length=3, max_length=500)


class AdminQuestionUpdate(BaseModel):
    text: str | None = None
    eligibility_criteria: str | None = None
    review_status: str | None = None


class AdminQuestionCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=160)
    category: str = Field(min_length=2, max_length=80)
    text: str = Field(min_length=10, max_length=500)
    eligibility_criteria: str = Field(min_length=10, max_length=2000)
    source_references: list[dict[str, Any]] = Field(min_length=1)
    family_friendly: bool = True


class AdminAnswerCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=240)
    aliases: list[str] = Field(default_factory=list)
    tier: RarityTier
    familiarity: float = Field(ge=0, le=1)
    familiarity_evidence: dict[str, Any]
    source_metadata: list[dict[str, Any]] = Field(min_length=1)
    interesting_fact: str | None = None
    is_designated_brillion: bool = False


class AdminAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=240)


class GenerateQuestionsRequest(BaseModel):
    category: str
    count: int = Field(default=5, ge=1, le=25)


class ImportDatasetRequest(BaseModel):
    importer: str
    payload: dict[str, Any]
