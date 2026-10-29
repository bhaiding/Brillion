import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.dependencies import session_claims
from app.game import (
    advance_game,
    build_state,
    create_rematch,
    create_room,
    join_room,
    require_host,
    require_room_claim,
    room_by_code,
    start_game,
    submit_answer,
)
from app.models import AnswerDispute, GameRound, GameSession, PlayerSubmission, RoomPlayer, as_utc, utcnow
from app.realtime import hub
from app.schemas import (
    AdvanceRequest,
    CreateDisputeRequest,
    CreateRoomRequest,
    GameStateView,
    JoinRoomRequest,
    SubmissionResult,
    SubmitAnswerRequest,
    TokenResponse,
    UpdateRoomSettingsRequest,
)
from app.security import SessionClaims, issue_token, read_token

router = APIRouter(prefix="/rooms", tags=["rooms"])
Db = Annotated[AsyncSession, Depends(get_db)]
Claims = Annotated[SessionClaims, Depends(session_claims)]


async def broadcast_state(code: str) -> None:
    await hub.publish(code, {"type": "state_changed", "room_code": code})


@router.post("", response_model=TokenResponse, status_code=201)
async def create_room_endpoint(payload: CreateRoomRequest, db: Db) -> TokenResponse:
    room, host_player, token = await create_room(db, payload.settings, payload.nickname)
    return TokenResponse(room_code=room.code, token=token, role="host", player_id=host_player.id)


@router.post("/{code}/join", response_model=TokenResponse, status_code=201)
async def join_room_endpoint(code: str, payload: JoinRoomRequest, db: Db) -> TokenResponse:
    room = await room_by_code(db, code)
    player, token = await join_room(db, room, payload.nickname)
    await broadcast_state(room.code)
    return TokenResponse(room_code=room.code, token=token, role="player", player_id=player.id)


@router.get("/{code}/state", response_model=GameStateView)
async def room_state(code: str, claims: Claims, db: Db) -> GameStateView:
    room = await room_by_code(db, code)
    return await build_state(db, room, claims)


@router.patch("/{code}/settings", response_model=GameStateView)
async def update_settings(code: str, payload: UpdateRoomSettingsRequest, claims: Claims, db: Db) -> GameStateView:
    room = await room_by_code(db, code, lock=True)
    require_host(claims, room)
    if room.state.value != "LOBBY":
        raise HTTPException(409, "Settings can only be changed in the lobby")
    room.settings = payload.settings.model_dump()
    room.state_version += 1
    await db.commit()
    await broadcast_state(room.code)
    return await build_state(db, room, claims)


@router.post("/{code}/start", response_model=GameStateView)
async def start(code: str, claims: Claims, db: Db) -> GameStateView:
    room = await room_by_code(db, code, lock=True)
    require_host(claims, room)
    await start_game(db, room)
    await broadcast_state(room.code)
    return await build_state(db, room, claims)


@router.post("/{code}/advance", response_model=GameStateView)
async def advance(code: str, payload: AdvanceRequest, claims: Claims, db: Db) -> GameStateView:
    room = await room_by_code(db, code, lock=True)
    require_host(claims, room)
    if payload.expected_state_version is not None and payload.expected_state_version != room.state_version:
        raise HTTPException(409, "The game state changed; refresh before advancing")
    await advance_game(db, room)
    await broadcast_state(room.code)
    return await build_state(db, room, claims)


@router.post("/{code}/answers", response_model=SubmissionResult)
async def answer(code: str, payload: SubmitAnswerRequest, claims: Claims, db: Db) -> SubmissionResult:
    room = await room_by_code(db, code)
    require_room_claim(claims, room)
    result = await submit_answer(db, room, claims, payload.answer)
    if result.accepted:
        await broadcast_state(room.code)
    return result


@router.delete("/{code}/players/{player_id}", status_code=204)
async def remove_player(code: str, player_id: uuid.UUID, claims: Claims, db: Db) -> Response:
    room = await room_by_code(db, code, lock=True)
    require_host(claims, room)
    if room.state.value != "LOBBY":
        raise HTTPException(409, "Players can only be removed before the game starts")
    player = await db.scalar(select(RoomPlayer).where(RoomPlayer.id == player_id, RoomPlayer.room_id == room.id))
    if player is None or player.removed_at is not None:
        raise HTTPException(404, "Player not found")
    player.removed_at = utcnow()
    player.connected = False
    room.state_version += 1
    await db.commit()
    await broadcast_state(room.code)
    return Response(status_code=204)


@router.post("/{code}/leave", status_code=204)
async def leave(code: str, claims: Claims, db: Db) -> Response:
    room = await room_by_code(db, code)
    require_room_claim(claims, room)
    if claims.role == "player":
        player = await db.get(RoomPlayer, claims.subject_id)
        if player:
            player.connected = False
            player.last_seen_at = utcnow()
            await db.commit()
            await broadcast_state(room.code)
    return Response(status_code=204)


@router.post("/{code}/close", status_code=204)
async def close_room(code: str, claims: Claims, db: Db) -> Response:
    room = await room_by_code(db, code, lock=True)
    require_host(claims, room)
    room.closed_at = utcnow()
    room.state_version += 1
    await db.commit()
    await broadcast_state(room.code)
    return Response(status_code=204)


@router.post("/{code}/rematch", response_model=GameStateView)
async def rematch(code: str, claims: Claims, db: Db) -> GameStateView:
    room = await room_by_code(db, code, lock=True)
    require_host(claims, room)
    await create_rematch(db, room)
    await broadcast_state(room.code)
    return await build_state(db, room, claims)


@router.post("/{code}/claim-host", response_model=TokenResponse)
async def claim_host(code: str, claims: Claims, db: Db) -> TokenResponse:
    """Recover a party whose creator has been disconnected for at least 60 seconds."""
    room = await room_by_code(db, code, lock=True)
    require_room_claim(claims, room)
    if claims.role != "player":
        raise HTTPException(409, "This session already has creator controls")
    claimant = await db.get(RoomPlayer, claims.subject_id)
    current_host = await db.get(RoomPlayer, room.host_player_id) if room.host_player_id else None
    if claimant is None or claimant.removed_at is not None:
        raise HTTPException(403, "Player is no longer active in this room")
    if current_host and current_host.connected:
        raise HTTPException(409, "The party creator is still connected")
    if current_host and utcnow() - as_utc(current_host.last_seen_at) < timedelta(seconds=60):
        raise HTTPException(409, "Wait one minute for the creator to reconnect")
    room.host_player_id = claimant.id
    room.state_version += 1
    await db.commit()
    token = issue_token(claimant.id, room.id, "host")
    await broadcast_state(room.code)
    return TokenResponse(room_code=room.code, token=token, role="host", player_id=claimant.id)


@router.get("/{code}/leaderboard", response_model=GameStateView)
async def get_leaderboard(code: str, claims: Claims, db: Db) -> GameStateView:
    room = await room_by_code(db, code)
    return await build_state(db, room, claims)


@router.post("/{code}/submissions/{submission_id}/disputes", status_code=201)
async def create_dispute(
    code: str, submission_id: uuid.UUID, payload: CreateDisputeRequest, claims: Claims, db: Db
) -> dict[str, str]:
    room = await room_by_code(db, code)
    require_room_claim(claims, room)
    submission = await db.scalar(
        select(PlayerSubmission)
        .join(GameRound, GameRound.id == PlayerSubmission.round_id)
        .join(GameSession, GameSession.id == GameRound.game_id)
        .where(PlayerSubmission.id == submission_id, GameSession.room_id == room.id)
    )
    if not submission:
        raise HTTPException(404, "Submission not found")
    if claims.role == "player" and submission.player_id != claims.subject_id:
        raise HTTPException(403, "You may only dispute your own answer")
    dispute = AnswerDispute(submission_id=submission.id, player_reason=payload.reason)
    db.add(dispute)
    await db.commit()
    return {"dispute_id": str(dispute.id), "status": dispute.status}


@router.websocket("/{code}/ws")
async def room_socket(websocket: WebSocket, code: str, token: str) -> None:
    origin = websocket.headers.get("origin")
    if origin and origin not in get_settings().allowed_origins:
        await websocket.close(code=4403, reason="Origin is not allowed")
        return
    claims = read_token(token)
    if claims is None:
        await websocket.close(code=4401, reason="Invalid session")
        return
    async with SessionLocal() as db:
        try:
            room = await room_by_code(db, code)
            require_room_claim(claims, room)
        except HTTPException:
            await websocket.close(code=4403, reason="Room authorization failed")
            return
        await hub.connect(room.code, websocket)
        player: RoomPlayer | None = None
        if claims.role in {"player", "host"}:
            player = await db.get(RoomPlayer, claims.subject_id)
            if player is None or player.removed_at is not None or player.room_id != room.id:
                await websocket.close(code=4403, reason="Player is no longer in this room")
                return
            player.connected = True
            player.last_seen_at = utcnow()
            await db.commit()
        await websocket.send_json({"type": "connected", "server_time": datetime.utcnow().isoformat()})
        await broadcast_state(room.code)
        try:
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "server_time": datetime.utcnow().isoformat()})
                    if player:
                        player.last_seen_at = utcnow()
                        await db.commit()
                elif message.get("type") == "resync":
                    await websocket.send_json({"type": "state_changed", "room_code": room.code})
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(room.code, websocket)
            if player:
                player.connected = False
                player.last_seen_at = utcnow()
                await db.commit()
                await broadcast_state(room.code)
