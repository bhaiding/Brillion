# REST and WebSocket contract

FastAPI publishes the complete typed OpenAPI document at `/openapi.json` and interactive docs at `/docs`.

Core REST routes:

- `POST /api/rooms` — create a room and creator/player session.
- `POST /api/rooms/{code}/join` — join with a unique nickname.
- `GET /api/rooms/{code}/state` — complete authorized snapshot.
- `PATCH /api/rooms/{code}/settings` — creator-only lobby settings.
- `POST /api/rooms/{code}/start` — creator-only question selection/start.
- `POST /api/rooms/{code}/advance` — creator-only validated transition.
- `POST /api/rooms/{code}/answers` — authoritative validation and lock.
- `DELETE /api/rooms/{code}/players/{id}` — creator-only lobby removal.
- `POST /api/rooms/{code}/rematch` — creator-only rematch.
- `POST /api/rooms/{code}/submissions/{id}/disputes` — dispute a result.
- `/api/admin/*` — secret-protected question, generation, import, publishing, cost, and dispute operations.

`GET /api/rooms/{code}/ws?token=…` opens the room stream. Server messages are deliberately small:

- `connected` includes server time.
- `state_changed` tells the client to fetch a fresh authorized snapshot.
- `pong` answers a client `ping` and includes server time.

Clients reconnect with exponential backoff and send `resync`; correctness never depends on receiving every event.

