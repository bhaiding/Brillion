# Brillion

Brillion is a phone-first multiplayer rarity-trivia party game. One player creates a party and shares its six-character code. Everyone answers the same seven open-ended questions privately on their own phone. When the server-enforced timer expires, every phone reveals the whole party's answers and fixed rarity points, followed by a tied-rank-aware leaderboard.

There is no shared TV or main screen. The creator is also a player and has the small set of controls needed to start and advance the party.

## Architecture

- `frontend/`: React 19, TypeScript, Vite, Tailwind, Framer Motion, mobile-first layouts.
- `backend/`: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Redis pub/sub and distributed locks.
- PostgreSQL is canonical for rooms, identities, selected question versions, rounds, submissions, scores, disputes, and generation audit data.
- Redis carries cross-instance invalidation events and deadline-worker locks. No permanent game state lives only in Redis or process memory.
- Each game stores immutable published question-version IDs. Scoring remains reproducible after later question edits.
- Signed room tokens prove player identity; a room code grants no administrative authority.

See [architecture details](docs/ARCHITECTURE.md), [API/events](docs/API.md), and [source licensing](docs/DATA_SOURCES.md).

## Local setup

Requirements: Python 3.12+, Node 20+, PostgreSQL 16+, and Redis 7+. Docker Compose is the easiest way to run the datastores.

```bash
cp .env.example .env
docker compose up -d postgres redis
python3 -m venv .venv
.venv/bin/pip install -e 'backend[dev]'
cd backend && ../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.seed_data
../.venv/bin/uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. API docs are at `http://localhost:8000/docs`.

Never reuse the development secrets in production. Generate at least 32 random bytes for `SESSION_SIGNING_SECRET`; keep `ADMIN_SECRET` and `OPENAI_API_KEY` out of source control.

## Playing

1. Enter a nickname and create a game.
2. Share the displayed party code.
3. Friends enter the code and a unique nickname on their phones.
4. The creator starts the game and then starts each question's timer.
5. Everyone submits privately. Unrecognized answers can be corrected before a valid answer is locked.
6. At the deadline, every phone receives the full answer reveal and then the leaderboard.
7. After seven questions, the creator can start a rematch.

## Question bank and scoring

Run `python -m app.seed_data` after migrations to install the reviewed starter pack. Seed execution is idempotent. The starter pack currently contains 20 human-curated, fully playable questions; the schema and import/generation pipeline are built for thousands. The requested 100-question target must not be met by publishing unchecked AI lists, so additional candidates remain unpublished until authoritative-source, completeness, rarity-calibration, and human-review gates pass.

Scores are predetermined: Common 10, Predictably Obscure 15, Uncommon 30, Rare 60, Deep Cut 85, and Brillion 100. `brillion-rarity-v1` combines normalized, question-type-specific recognition, pageview, dataset-popularity, and corpus signals. Missing evidence is omitted rather than treated as zero. A human adjustment is recorded explicitly. Published scores never change inside a game.

The answer matcher applies Unicode/case/punctuation normalization, exact canonical and alias lookup, then conservative fuzzy matching with ambiguity separation. Short answers require exact matches. A rejected entry does not lock, so the player can retry before the deadline. Dispute resolutions create immutable scoring events and atomically update totals.

## Generation and review

Set `OPENAI_API_KEY` only on the backend/worker. From `/admin`, an authenticated administrator can queue schema-constrained candidate generation. The worker retries rate limits with exponential backoff and records token usage and job errors. Model output is only a candidate: it is never made playable automatically.

Dataset importers live in `backend/app/question_pipeline/importers.py`. Importers must record URL, license, retrieval date, and raw evidence. To publish a question, every answer must be verified and exactly one answer must be designated as the 100-point Brillion answer. Published versions are immutable; corrections create a new version.

## Tests

```bash
cd backend
../.venv/bin/pytest -q
../.venv/bin/ruff check app tests

cd ../frontend
npm run typecheck
npm run build
npm run e2e
```

The backend suite covers normalization, aliases/fuzzy safety, rarity tiers, room identity, duplicate nicknames, state transitions, hidden answers, duplicate submissions, fixed scores, and tied rankings. Playwright uses independent browser contexts for the creator and multiple players. PostgreSQL/Redis integration and multi-instance tests require the Compose services.

## Deploying to Render

The root `render.yaml` follows Render's current Blueprint format and creates a static frontend, FastAPI service, PostgreSQL database, and Key Value instance on Render's free plans. Because Render does not offer free background workers, the API process also polls queued question-generation jobs. Free services do not support pre-deploy commands, so the startup command runs Alembic and the idempotent seed process before starting Uvicorn.

1. Push the repository to GitHub.
2. In Render, create a Blueprint from that repository.
3. Supply `OPENAI_API_KEY` and optionally `SENTRY_DSN` when prompted.
4. If Render changes a service name because the name is already taken, update `FRONTEND_URL`, `BACKEND_URL`, and `ALLOWED_ORIGINS` to the exact public HTTPS origins.
5. Confirm `/ready`, database migrations, worker logs, and seed count before playing a live game.

This Blueprint costs **$0/month within Render's included free usage** and does not require a payment method. The tradeoffs are important: the API sleeps after 15 idle minutes and may need about a minute to wake; the workspace receives 750 free service hours per month; free Key Value data is erased on restart; and the free PostgreSQL database expires after 30 days with no backups. Permanent game records live in PostgreSQL, so Redis restarts only interrupt transient connections, but the database must be recreated, exported, or upgraded before its expiry. OpenAI generation can still incur API charges when a key is configured; normal gameplay makes no OpenAI calls.

### Rollback

Deploy the prior successful Render version for the API, worker, and static site. Database migrations are forward-compatible and should normally roll forward; only run `alembic downgrade` after reviewing the specific migration and taking a PostgreSQL backup. A saved game references immutable version IDs, so content rollback does not change completed scores.

## Troubleshooting

- **Room will not start:** fewer than seven published questions match the category/filter settings.
- **Players do not update:** verify `REDIS_URL`, Key Value health, WebSocket/WSS access, and exact frontend origin.
- **Database connection error:** Render supplies `postgresql://`; settings convert it to SQLAlchemy's asyncpg driver automatically.
- **Generation job fails:** check worker logs and `OPENAI_API_KEY`; gameplay is unaffected.
- **Nickname rejected:** names are unique within a room after Unicode-aware, case-insensitive normalization.
- **Refresh loses identity:** browser storage may be disabled or cleared; the signed token is what restores the seat.
