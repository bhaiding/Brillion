import hashlib
import random
import secrets
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import (
    Answer,
    AnswerAlias,
    AnswerAttempt,
    GameRound,
    GameSession,
    GameState,
    PlayerSubmission,
    Question,
    QuestionVersion,
    ReviewStatus,
    Room,
    RoomPlayer,
    ScoringEvent,
    as_utc,
    utcnow,
)
from app.normalization import (
    conservative_fuzzy_score,
    fuzzy_threshold,
    nickname_key,
    normalize_answer,
)
from app.schemas import (
    AnswerResultView,
    GameStateView,
    LeaderboardEntry,
    PlayerView,
    QuestionView,
    RoomSettings,
    SubmissionResult,
)
from app.security import SessionClaims, issue_token, new_secret, secret_hash

settings = get_settings()
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

ALLOWED_TRANSITIONS: dict[GameState, set[GameState]] = {
    GameState.LOBBY: {GameState.QUESTION_PREVIEW},
    GameState.QUESTION_PREVIEW: {GameState.ANSWERING},
    GameState.ANSWERING: {GameState.SCORING},
    GameState.SCORING: {GameState.REVEAL},
    GameState.REVEAL: {GameState.LEADERBOARD},
    GameState.LEADERBOARD: {GameState.QUESTION_PREVIEW, GameState.FINISHED},
    GameState.FINISHED: {GameState.QUESTION_PREVIEW},
}


def ensure_transition(current: GameState, target: GameState) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(409, f"Cannot transition from {current.value} to {target.value}")


def require_room_claim(claims: SessionClaims | None, room: Room) -> SessionClaims:
    if claims is None or claims.room_id != room.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired room session")
    return claims


def require_host(claims: SessionClaims | None, room: Room) -> SessionClaims:
    claims = require_room_claim(claims, room)
    if claims.role != "host" or claims.subject_id != room.host_player_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Host authorization required")
    return claims


async def room_by_code(db: AsyncSession, code: str, *, lock: bool = False) -> Room:
    query = select(Room).where(Room.code == code.upper())
    if lock:
        query = query.with_for_update()
    room = await db.scalar(query)
    if room is None or room.closed_at is not None:
        raise HTTPException(404, "Room not found")
    if as_utc(room.expires_at) < utcnow():
        raise HTTPException(410, "Room has expired")
    return room


async def create_room(
    db: AsyncSession, room_settings: RoomSettings, host_nickname: str
) -> tuple[Room, RoomPlayer, str]:
    for _ in range(12):
        code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(6))
        raw_secret = new_secret()
        room = Room(
            code=code,
            host_secret_hash=secret_hash(raw_secret),
            settings=room_settings.model_dump(),
            expires_at=utcnow() + timedelta(hours=settings.room_ttl_hours),
        )
        db.add(room)
        try:
            await db.flush()
            host_player = RoomPlayer(
                room_id=room.id,
                nickname=host_nickname,
                nickname_normalized=nickname_key(host_nickname),
                session_hash=secret_hash(new_secret()),
                connected=True,
            )
            db.add(host_player)
            await db.flush()
            room.host_player_id = host_player.id
            await db.commit()
            await db.refresh(room)
            await db.refresh(host_player)
            return room, host_player, issue_token(host_player.id, room.id, "host")
        except IntegrityError:
            await db.rollback()
    raise HTTPException(503, "Could not allocate a room code; please retry")


async def join_room(db: AsyncSession, room: Room, nickname: str) -> tuple[RoomPlayer, str]:
    if room.state != GameState.LOBBY:
        raise HTTPException(409, "This game has already started")
    session_secret = new_secret()
    player = RoomPlayer(
        room_id=room.id,
        nickname=nickname,
        nickname_normalized=nickname_key(nickname),
        session_hash=secret_hash(session_secret),
        connected=True,
    )
    db.add(player)
    try:
        await db.commit()
        await db.refresh(player)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "That nickname is already in use in this room") from exc
    return player, issue_token(player.id, room.id, "player")


async def select_question_versions(
    db: AsyncSession,
    room_settings: RoomSettings,
    seed: str,
    exclude_version_ids: set[str] | None = None,
) -> list[QuestionVersion]:
    query = (
        select(QuestionVersion)
        .join(Question, Question.id == QuestionVersion.question_id)
        .where(
            QuestionVersion.review_status == ReviewStatus.PUBLISHED,
            Question.review_status == ReviewStatus.PUBLISHED,
            Question.active_version_id == QuestionVersion.id,
        )
        .options(selectinload(QuestionVersion.question))
    )
    categories = [c for c in room_settings.categories if c.lower() != "mixed"]
    if categories:
        query = query.where(Question.category.in_(categories))
    if room_settings.family_friendly:
        query = query.where(Question.family_friendly.is_(True))
    candidates = list((await db.scalars(query)).all())
    count = room_settings.question_count
    if len(candidates) < count:
        raise HTTPException(
            422,
            f"Only {len(candidates)} reviewed questions match these settings; {count} are required",
        )

    rng = random.Random(seed)
    rng.shuffle(candidates)
    fresh = [candidate for candidate in candidates if str(candidate.id) not in (exclude_version_ids or set())]
    if len(fresh) >= count:
        candidates = fresh
    selected: list[QuestionVersion] = []
    category_counts: dict[str, int] = defaultdict(int)
    pool = list(candidates)
    while pool and len(selected) < count:
        candidate_index, candidate = min(
            enumerate(pool), key=lambda pair: (category_counts[pair[1].question.category], pair[0])
        )
        pool.pop(candidate_index)
        selected.append(candidate)
        category_counts[candidate.question.category] += 1
    return selected


async def start_game(db: AsyncSession, room: Room) -> GameSession:
    if room.state != GameState.LOBBY:
        raise HTTPException(409, "The game has already started")
    players = list(
        (
            await db.scalars(select(RoomPlayer).where(RoomPlayer.room_id == room.id, RoomPlayer.removed_at.is_(None)))
        ).all()
    )
    if not players:
        raise HTTPException(422, "At least one player must join before starting")
    room_settings = RoomSettings.model_validate(room.settings)
    seed = secrets.token_hex(16)
    previous_game = await db.scalar(
        select(GameSession).where(GameSession.room_id == room.id).order_by(GameSession.sequence.desc()).limit(1)
    )
    questions = await select_question_versions(
        db,
        room_settings,
        seed,
        set(previous_game.question_version_ids) if previous_game else None,
    )
    prior_count = await db.scalar(select(func.count(GameSession.id)).where(GameSession.room_id == room.id))
    game = GameSession(
        room_id=room.id,
        sequence=int(prior_count or 0) + 1,
        selection_seed=seed,
        question_version_ids=[str(q.id) for q in questions],
        current_round_index=0,
        state=GameState.QUESTION_PREVIEW,
        deadline_at=(
            utcnow() + timedelta(seconds=room_settings.automatic_transition_seconds)
            if not room_settings.host_controlled_transitions
            else None
        ),
    )
    db.add(game)
    await db.flush()
    for index, question in enumerate(questions):
        db.add(
            GameRound(
                game_id=game.id,
                round_index=index,
                question_version_id=question.id,
                question_snapshot={
                    "id": str(question.id),
                    "text": question.text,
                    "category": question.question.category,
                    "eligibility_criteria": question.eligibility_criteria,
                    "version": question.version,
                    "scoring_model_version": question.scoring_model_version,
                },
                state=GameState.QUESTION_PREVIEW,
            )
        )
    ensure_transition(room.state, GameState.QUESTION_PREVIEW)
    room.state = GameState.QUESTION_PREVIEW
    room.state_version += 1
    await db.commit()
    await db.refresh(game)
    return game


async def current_game(db: AsyncSession, room: Room) -> GameSession | None:
    return await db.scalar(
        select(GameSession).where(GameSession.room_id == room.id).order_by(GameSession.sequence.desc()).limit(1)
    )


async def current_round(db: AsyncSession, game: GameSession) -> GameRound:
    round_record = await db.scalar(
        select(GameRound).where(GameRound.game_id == game.id, GameRound.round_index == game.current_round_index)
    )
    if round_record is None:
        raise HTTPException(409, "The current round is unavailable")
    return round_record


async def advance_game(db: AsyncSession, room: Room) -> GameState:
    game = await current_game(db, room)
    if game is None:
        raise HTTPException(409, "No active game")
    now = utcnow()
    room_settings = RoomSettings.model_validate(room.settings)

    if room.state == GameState.QUESTION_PREVIEW:
        target = GameState.ANSWERING
        round_record = await current_round(db, game)
        round_record.state = target
        round_record.opened_at = now
        round_record.deadline_at = now + timedelta(seconds=room_settings.answer_seconds)
        game.deadline_at = round_record.deadline_at
    elif room.state == GameState.REVEAL:
        target = GameState.LEADERBOARD
        (await current_round(db, game)).state = target
        game.deadline_at = (
            now + timedelta(seconds=room_settings.automatic_transition_seconds)
            if not room_settings.host_controlled_transitions
            else None
        )
    elif room.state == GameState.LEADERBOARD:
        if game.current_round_index + 1 >= room_settings.question_count:
            target = GameState.FINISHED
            game.completed_at = now
        else:
            target = GameState.QUESTION_PREVIEW
            game.current_round_index += 1
            (await current_round(db, game)).state = target
        game.deadline_at = (
            now + timedelta(seconds=room_settings.automatic_transition_seconds)
            if target == GameState.QUESTION_PREVIEW and not room_settings.host_controlled_transitions
            else None
        )
    else:
        raise HTTPException(409, f"The host cannot advance from {room.state.value}")

    ensure_transition(room.state, target)
    room.state = game.state = target
    game.state_started_at = now
    room.state_version += 1
    await db.commit()
    return target


async def match_answer(
    db: AsyncSession, question_version_id: uuid.UUID, raw_answer: str
) -> tuple[Answer | None, str | None]:
    normalized = normalize_answer(raw_answer)
    answer = await db.scalar(
        select(Answer).where(
            Answer.question_version_id == question_version_id,
            Answer.normalized_name == normalized,
        )
    )
    if answer:
        return answer, "exact"
    alias = await db.scalar(
        select(AnswerAlias)
        .where(
            AnswerAlias.question_version_id == question_version_id,
            AnswerAlias.normalized_alias == normalized,
        )
        .options(selectinload(AnswerAlias.answer))
    )
    if alias:
        return alias.answer, "alias"

    rows = (
        await db.execute(
            select(Answer, AnswerAlias.normalized_alias)
            .outerjoin(AnswerAlias, AnswerAlias.answer_id == Answer.id)
            .where(Answer.question_version_id == question_version_id)
        )
    ).all()
    best: tuple[float, Answer] | None = None
    runner_up = 0.0
    for candidate, alias_value in rows:
        for value in (candidate.normalized_name, alias_value):
            if not value:
                continue
            score = conservative_fuzzy_score(normalized, value)
            if best is None or score > best[0]:
                runner_up = best[0] if best else 0.0
                best = (score, candidate)
            elif score > runner_up and candidate.id != best[1].id:
                runner_up = score
    threshold = fuzzy_threshold(normalized)
    if best and best[0] >= threshold and best[0] - runner_up >= 0.08:
        return best[1], "fuzzy"
    return None, None


async def submit_answer(db: AsyncSession, room: Room, claims: SessionClaims, raw_answer: str) -> SubmissionResult:
    if claims.role not in {"player", "host"}:
        raise HTTPException(403, "Only room players may submit answers")
    if room.state != GameState.ANSWERING:
        raise HTTPException(409, "Answers are not being accepted right now")
    game = await current_game(db, room)
    if game is None:
        raise HTTPException(409, "No active game")
    round_record = await current_round(db, game)
    now = utcnow()
    if round_record.deadline_at is None or now >= as_utc(round_record.deadline_at):
        raise HTTPException(409, "The answer deadline has passed")
    existing = await db.scalar(
        select(PlayerSubmission).where(
            PlayerSubmission.round_id == round_record.id,
            PlayerSubmission.player_id == claims.subject_id,
        )
    )
    if existing:
        raise HTTPException(409, "Your answer is already locked")

    answer, method = await match_answer(db, round_record.question_version_id, raw_answer)
    db.add(
        AnswerAttempt(
            round_id=round_record.id,
            player_id=claims.subject_id,
            raw_answer=raw_answer.strip(),
            normalized_answer=normalize_answer(raw_answer),
            recognized=answer is not None,
            match_method=method,
        )
    )
    if answer is None:
        await db.commit()
        return SubmissionResult(
            accepted=False,
            locked=False,
            message="That answer is not recognized. Check the spelling or try another answer.",
        )

    submission = PlayerSubmission(
        round_id=round_record.id,
        player_id=claims.subject_id,
        raw_answer=raw_answer.strip(),
        normalized_answer=normalize_answer(raw_answer),
        matched_answer_id=answer.id,
        match_method=method,
        valid=True,
        points=answer.points,
        tier=answer.tier,
    )
    db.add(submission)
    try:
        await db.flush()
        db.add(
            ScoringEvent(
                submission_id=submission.id,
                event_type="initial_score",
                new_points=answer.points,
                reason=f"Published answer-bank {method} match",
                actor="system",
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Your answer is already locked") from exc
    return SubmissionResult(
        accepted=True,
        locked=True,
        message="Answer locked in",
        canonical_answer=answer.canonical_name,
    )


async def score_and_reveal(db: AsyncSession, room: Room) -> None:
    """Atomically end answering and reveal. Scores were fixed at submission time."""
    if room.state != GameState.ANSWERING:
        return
    game = await current_game(db, room)
    if game is None:
        return
    round_record = await current_round(db, game)
    now = utcnow()
    if round_record.deadline_at and now < as_utc(round_record.deadline_at):
        return
    ensure_transition(room.state, GameState.SCORING)
    room.state = game.state = round_record.state = GameState.SCORING
    room.state_version += 1
    await db.flush()
    ensure_transition(GameState.SCORING, GameState.REVEAL)
    room.state = game.state = round_record.state = GameState.REVEAL
    room.state_version += 1
    round_record.revealed_at = now
    game.state_started_at = now
    room_settings = RoomSettings.model_validate(room.settings)
    game.deadline_at = (
        now + timedelta(seconds=room_settings.automatic_transition_seconds)
        if not room_settings.host_controlled_transitions
        else None
    )
    await db.commit()


async def leaderboard(db: AsyncSession, room: Room) -> list[LeaderboardEntry]:
    players = list(
        (
            await db.scalars(select(RoomPlayer).where(RoomPlayer.room_id == room.id, RoomPlayer.removed_at.is_(None)))
        ).all()
    )
    totals = dict(
        (
            await db.execute(
                select(PlayerSubmission.player_id, func.coalesce(func.sum(PlayerSubmission.points), 0))
                .join(GameRound, GameRound.id == PlayerSubmission.round_id)
                .join(GameSession, GameSession.id == GameRound.game_id)
                .where(GameSession.room_id == room.id)
                .group_by(PlayerSubmission.player_id)
            )
        ).all()
    )
    ordered = sorted(players, key=lambda p: (-int(totals.get(p.id, 0)), p.nickname.casefold()))
    result: list[LeaderboardEntry] = []
    last_score: int | None = None
    rank = 0
    for index, player in enumerate(ordered, start=1):
        score = int(totals.get(player.id, 0))
        if score != last_score:
            rank = index
            last_score = score
        result.append(LeaderboardEntry(rank=rank, player_id=player.id, nickname=player.nickname, score=score))
    return result


async def build_state(db: AsyncSession, room: Room, claims: SessionClaims | None) -> GameStateView:
    require_room_claim(claims, room)
    players = list(
        (
            await db.scalars(
                select(RoomPlayer)
                .where(RoomPlayer.room_id == room.id, RoomPlayer.removed_at.is_(None))
                .order_by(RoomPlayer.created_at)
            )
        ).all()
    )
    board = await leaderboard(db, room)
    score_by_player = {entry.player_id: entry.score for entry in board}
    game = await current_game(db, room)
    round_record: GameRound | None = None
    submitted_ids: set[uuid.UUID] = set()
    if game and game.current_round_index >= 0:
        round_record = await current_round(db, game)
        submitted_ids = set(
            (
                await db.scalars(select(PlayerSubmission.player_id).where(PlayerSubmission.round_id == round_record.id))
            ).all()
        )
    player_views = [
        PlayerView(
            id=player.id,
            nickname=player.nickname,
            connected=player.connected,
            submitted=player.id in submitted_ids,
            score=score_by_player.get(player.id, 0),
        )
        for player in players
    ]
    question = None
    results = None
    final_answers = None
    if round_record:
        snapshot = round_record.question_snapshot
        question = QuestionView(
            text=snapshot["text"],
            category=snapshot["category"],
            eligibility_criteria=snapshot["eligibility_criteria"],
        )
        if room.state in {
            GameState.REVEAL,
            GameState.LEADERBOARD,
            GameState.FINISHED,
        }:
            submissions = list(
                (
                    await db.scalars(
                        select(PlayerSubmission)
                        .where(PlayerSubmission.round_id == round_record.id)
                        .options(selectinload(PlayerSubmission.player))
                    )
                ).all()
            )
            by_player = {submission.player_id: submission for submission in submissions}
            answer_ids = [s.matched_answer_id for s in submissions if s.matched_answer_id]
            answers = {
                answer.id: answer
                for answer in (await db.scalars(select(Answer).where(Answer.id.in_(answer_ids)))).all()
            }
            results = []
            for player in players:
                submission = by_player.get(player.id)
                matched = answers.get(submission.matched_answer_id) if submission else None
                results.append(
                    AnswerResultView(
                        player_id=player.id,
                        nickname=player.nickname,
                        raw_answer=submission.raw_answer if submission else None,
                        canonical_answer=matched.canonical_name if matched else None,
                        valid=bool(submission and submission.valid),
                        points=submission.points if submission else 0,
                        tier=submission.tier if submission else None,
                        total_score=score_by_player.get(player.id, 0),
                        interesting_fact=matched.interesting_fact if matched else None,
                    )
                )
    if room.state == GameState.FINISHED and game:
        all_rows = (
            await db.execute(
                select(PlayerSubmission, GameRound, RoomPlayer, Answer)
                .join(GameRound, GameRound.id == PlayerSubmission.round_id)
                .join(RoomPlayer, RoomPlayer.id == PlayerSubmission.player_id)
                .outerjoin(Answer, Answer.id == PlayerSubmission.matched_answer_id)
                .where(GameRound.game_id == game.id)
                .order_by(GameRound.round_index)
            )
        ).all()
        final_answers = defaultdict(list)
        for submission, game_round, player, answer in all_rows:
            final_answers[str(player.id)].append(
                {
                    "round": game_round.round_index + 1,
                    "answer": submission.raw_answer,
                    "canonical_answer": answer.canonical_name if answer else None,
                    "points": submission.points,
                    "tier": submission.tier.value if submission.tier else None,
                }
            )
        final_answers = dict(final_answers)
    settings_model = RoomSettings.model_validate(room.settings)
    hide_board = settings_model.hide_leaderboard and room.state != GameState.FINISHED
    return GameStateView(
        server_time=datetime.now(UTC),
        room_code=room.code,
        state=room.state,
        state_version=room.state_version,
        host_player_id=room.host_player_id,
        settings=settings_model,
        players=player_views,
        game_id=game.id if game else None,
        round_index=game.current_round_index if game else None,
        round_number=game.current_round_index + 1 if game else None,
        question_count=settings_model.question_count,
        question=question,
        deadline_at=game.deadline_at if game else None,
        results=results,
        leaderboard=None if hide_board else board,
        final_answers=final_answers,
    )


async def create_rematch(db: AsyncSession, room: Room) -> GameSession:
    if room.state != GameState.FINISHED:
        raise HTTPException(409, "A rematch can only begin after the game is finished")
    room.state = GameState.LOBBY
    room.state_version += 1
    await db.flush()
    return await start_game(db, room)


def deterministic_selection_digest(question_ids: list[str], seed: str) -> str:
    return hashlib.sha256((seed + "|" + "|".join(question_ids)).encode()).hexdigest()
