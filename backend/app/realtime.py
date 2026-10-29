import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.config import get_settings

settings = get_settings()


class RealtimeHub:
    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.listeners: dict[str, asyncio.Task[None]] = {}
        self._guard = asyncio.Lock()

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def close(self) -> None:
        for task in self.listeners.values():
            task.cancel()
        await self.redis.aclose()

    async def connect(self, room_code: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._guard:
            self.connections[room_code].add(websocket)
            if room_code not in self.listeners:
                self.listeners[room_code] = asyncio.create_task(self._listen(room_code))

    async def disconnect(self, room_code: str, websocket: WebSocket) -> None:
        async with self._guard:
            self.connections[room_code].discard(websocket)

    async def publish(self, room_code: str, event: dict[str, Any]) -> None:
        await self.redis.publish(f"room:{room_code}", json.dumps(event, default=str))

    async def _listen(self, room_code: str) -> None:
        pubsub: PubSub = self.redis.pubsub()
        await pubsub.subscribe(f"room:{room_code}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                stale: list[WebSocket] = []
                for websocket in list(self.connections[room_code]):
                    try:
                        await websocket.send_text(message["data"])
                    except Exception:
                        stale.append(websocket)
                for websocket in stale:
                    self.connections[room_code].discard(websocket)
        finally:
            await pubsub.unsubscribe(f"room:{room_code}")
            await pubsub.aclose()

    @asynccontextmanager
    async def room_lock(self, room_id: str, timeout: int = 10):
        lock = self.redis.lock(f"lock:room:{room_id}", timeout=timeout, blocking_timeout=5)
        acquired = await lock.acquire()
        if not acquired:
            raise TimeoutError("Room is busy; please retry")
        try:
            yield
        finally:
            if await lock.owned():
                await lock.release()


hub = RealtimeHub()
