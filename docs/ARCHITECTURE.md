# Architecture and invariants

## State ownership

PostgreSQL is the source of truth. `rooms.state` and `state_version` provide a compact room cursor; `game_sessions` and `game_rounds` preserve the authoritative timeline and deadline. A Redis lock serializes each deadline transition across backend instances, while row locks and unique constraints provide the final correctness boundary.

Valid transitions are:

```text
LOBBY → QUESTION_PREVIEW → ANSWERING → SCORING → REVEAL
  → LEADERBOARD → QUESTION_PREVIEW (next round)
  → LEADERBOARD → FINISHED
```

SCORING is a short server-only transactional state. Clients never choose scores, state, timestamps, other players' submissions, or question IDs. The creator may request only validated host transitions.

## Time synchronization

The server stores and returns an absolute UTC `deadline_at` plus `server_time`. Phones calculate display time using the measured server offset. The API rejects at or after the persisted deadline regardless of the phone's clock. A cross-instance deadline worker acquires `lock:room:{code}`, locks the room row, and idempotently advances ANSWERING through SCORING to REVEAL.

## Privacy and reveal

During QUESTION_PREVIEW and ANSWERING, serialized state includes only whether each player submitted. Raw answers and matches are absent. During REVEAL, LEADERBOARD, and FINISHED, the server includes the round's answers, validity, rarity, points, interesting fact, and cumulative totals for every player.

## Persistence and recovery

Room and player records survive restarts. A signed, expiring room token binds a player UUID, room UUID, and role. Reconnection fetches a complete authorized snapshot before resuming events. WebSocket events are invalidation hints, not state: dropping one is safe because clients refetch the canonical snapshot.

## Concurrency invariants

- Unique `(round_id, player_id)` prevents two scored submissions.
- Unique `(room_id, nickname_normalized)` prevents nickname collisions.
- Unique `(game_id, round_index)` prevents duplicated rounds.
- Published answer sets are immutable; a game records its selected version IDs.
- Host transitions may include an expected state version, rejecting stale duplicate taps.
- Scores come from the published matched answer, never client input or answer speed.

## Scaling

API instances remain stateless. Redis pub/sub reaches sockets connected to any instance. PostgreSQL/Redis health is exposed at `/ready`; `/health` reports degraded dependencies without leaking credentials. Graceful shutdown gives active requests time to finish; phones reconnect with exponential backoff and full resynchronization.

