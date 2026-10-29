from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.game import (
    advance_game,
    build_state,
    create_room,
    ensure_transition,
    join_room,
    score_and_reveal,
    start_game,
    submit_answer,
)
from app.models import (
    Answer,
    AnswerAlias,
    GameState,
    Question,
    QuestionVersion,
    RarityTier,
    ReviewStatus,
    utcnow,
)
from app.normalization import normalize_answer
from app.schemas import RoomSettings
from app.security import read_token


async def add_bank(db, count: int = 7) -> None:
    for index in range(count):
        question = Question(
            slug=f"question-{index}",
            category="Science" if index % 2 else "Geography",
            review_status=ReviewStatus.PUBLISHED,
        )
        db.add(question)
        await db.flush()
        version = QuestionVersion(
            question_id=question.id,
            version=1,
            text=f"Name answer {index}",
            eligibility_criteria="Use a published answer",
            validation_status="validated",
            review_status=ReviewStatus.PUBLISHED,
        )
        db.add(version)
        await db.flush()
        question.active_version_id = version.id
        common = Answer(
            question_version_id=version.id,
            canonical_name=f"Common {index}",
            normalized_name=normalize_answer(f"Common {index}"),
            tier=RarityTier.COMMON,
            points=10,
            familiarity=0.9,
        )
        rare = Answer(
            question_version_id=version.id,
            canonical_name=f"Rare {index}",
            normalized_name=normalize_answer(f"Rare {index}"),
            tier=RarityTier.BRILLION,
            points=100,
            familiarity=0.05,
            is_designated_brillion=True,
        )
        db.add_all([common, rare])
        await db.flush()
        db.add(
            AnswerAlias(
                answer_id=rare.id,
                question_version_id=version.id,
                alias=f"Deep cut {index}",
                normalized_alias=normalize_answer(f"Deep cut {index}"),
            )
        )
    await db.commit()


def test_invalid_transition_is_rejected() -> None:
    with pytest.raises(HTTPException):
        ensure_transition(GameState.LOBBY, GameState.REVEAL)


async def test_creator_is_a_player_and_duplicate_nickname_is_rejected(db) -> None:
    room, host, host_token = await create_room(db, RoomSettings(), "Avery")
    assert room.host_player_id == host.id
    assert read_token(host_token).subject_id == host.id
    with pytest.raises(HTTPException) as error:
        await join_room(db, room, " avery ")
    assert error.value.status_code == 409


async def test_complete_round_hides_then_reveals_answers_and_scores_ties(db) -> None:
    await add_bank(db)
    room, host, host_token = await create_room(db, RoomSettings(), "Host")
    guest, guest_token = await join_room(db, room, "Guest")
    host_claims = read_token(host_token)
    guest_claims = read_token(guest_token)
    await start_game(db, room)
    preview = await build_state(db, room, guest_claims)
    assert preview.state == GameState.QUESTION_PREVIEW
    assert preview.results is None

    await advance_game(db, room)
    current = await build_state(db, room, host_claims)
    question_index = int(current.question.text.rsplit(" ", 1)[-1])
    await submit_answer(db, room, host_claims, f"Rare {question_index}")
    await submit_answer(db, room, guest_claims, f"Deep cut {question_index}")

    answering = await build_state(db, room, guest_claims)
    assert answering.results is None
    assert all(player.submitted for player in answering.players)

    game_round = await db.scalar(select(__import__("app.models", fromlist=["GameRound"]).GameRound))
    game_round.deadline_at = utcnow() - timedelta(seconds=1)
    await db.commit()
    await score_and_reveal(db, room)
    revealed = await build_state(db, room, guest_claims)
    assert revealed.state == GameState.REVEAL
    assert {result.raw_answer for result in revealed.results} == {
        f"Rare {question_index}",
        f"Deep cut {question_index}",
    }
    assert all(result.points == 100 for result in revealed.results)
    assert [entry.rank for entry in revealed.leaderboard] == [1, 1]


async def test_answer_is_locked_and_deadline_is_enforced(db) -> None:
    await add_bank(db)
    room, host, token = await create_room(db, RoomSettings(), "Host")
    claims = read_token(token)
    await start_game(db, room)
    await advance_game(db, room)
    state = await build_state(db, room, claims)
    question_index = int(state.question.text.rsplit(" ", 1)[-1])
    await submit_answer(db, room, claims, f"Common {question_index}")
    with pytest.raises(HTTPException) as duplicate:
        await submit_answer(db, room, claims, f"Rare {question_index}")
    assert duplicate.value.status_code == 409
