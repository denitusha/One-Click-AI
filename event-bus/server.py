"""Event Bus – WebSocket relay for real-time dashboard updates.

Agents POST events via HTTP; the dashboard connects over WebSocket and
receives a live stream of every event as it happens.

Endpoints
---------
- ``POST /event``   – agents push events here (JSON body)
- ``WS   /ws``      – dashboard connects here to receive events
- ``GET  /events``  – fetch recent event history (HTTP, for late-joining clients)
- ``GET  /health``  – health check
- ``GET  /stats``   – connection / event counters
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# MongoDB (async) — graceful degradation if unavailable
try:
    import motor.motor_asyncio as motor_asyncio
except ImportError:
    motor_asyncio = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Ensure the shared package is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import EVENT_BUS_PORT  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("event-bus")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_HISTORY = 500  # max recent events kept in memory for late joiners
HEARTBEAT_INTERVAL = 30  # seconds between WebSocket keep-alive pings

# ---------------------------------------------------------------------------
# Event model (matches shared/message_types.py EventPayload shape)
# ---------------------------------------------------------------------------

class Event(BaseModel):
    """An event emitted by any agent in the network."""

    event_type: str = Field(
        ...,
        description=(
            "Event discriminator, e.g. 'AGENT_REGISTERED', 'RFQ_SENT', "
            "'QUOTE_RECEIVED', 'CASCADE_COMPLETE'"
        ),
    )
    agent_id: str = Field(..., description="Agent that generated this event")
    timestamp: str = Field(
        default="",
        description="ISO-8601 timestamp; server fills if blank",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event-specific payload",
    )
    run_id: str = Field(
        default="",
        description="Dashboard-generated run UUID (also extracted from data.run_id)",
    )


# ---------------------------------------------------------------------------
# Connection manager — tracks all active WebSocket clients
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self, max_history: int = MAX_HISTORY) -> None:
        self._clients: set[WebSocket] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self._event_count: int = 0
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        logger.info(
            "WebSocket client connected (%s total)", self.client_count
        )

        # Send event history so the dashboard can catch up
        if self._history:
            try:
                await ws.send_json({
                    "type": "HISTORY",
                    "events": list(self._history),
                })
            except Exception:
                logger.warning(
                    "Failed to send history — client already disconnected"
                )
                await self.disconnect(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        logger.info(
            "WebSocket client disconnected (%s remaining)", self.client_count
        )

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to every connected WebSocket client."""
        self._history.append(event)
        self._event_count += 1

        # Snapshot client set to avoid mutation during iteration
        async with self._lock:
            clients = set(self._clients)

        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)

        # Prune disconnected clients
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
            logger.info("Pruned %d dead WebSocket connections", len(dead))


# ---------------------------------------------------------------------------
# MongoDB persistence (optional — graceful degradation)
# ---------------------------------------------------------------------------
MONGODB_URI = os.environ.get("MONGODB_URI", "")
_mongo_collection: Any = None  # motor collection or None


async def _init_mongo() -> None:
    """Connect to MongoDB if configured and motor is available."""
    global _mongo_collection
    if not MONGODB_URI or motor_asyncio is None:
        if not MONGODB_URI:
            logger.info("MONGODB_URI not set — running in-memory only.")
        else:
            logger.warning("motor not installed — running in-memory only.")
        return
    try:
        client = motor_asyncio.AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        # Verify connectivity
        await client.admin.command("ping")
        db = client["event_bus"]
        _mongo_collection = db["events"]
        # Create indexes for fast queries
        await _mongo_collection.create_index("run_id")
        await _mongo_collection.create_index("timestamp")
        logger.info("Connected to MongoDB at %s", MONGODB_URI)
    except Exception as exc:
        logger.warning("MongoDB unavailable (%s) — falling back to in-memory.", exc)
        _mongo_collection = None


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

manager = ConnectionManager()
_start_time: float = 0.0


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated on_event decorators."""
    global _start_time
    _start_time = time.time()
    logger.info(
        "Event Bus starting on port %d  (WS at ws://localhost:%d/ws)",
        EVENT_BUS_PORT,
        EVENT_BUS_PORT,
    )
    await _init_mongo()
    yield
    logger.info(
        "Event Bus shutting down. Served %d events to %d clients.",
        manager.event_count,
        manager.client_count,
    )


app = FastAPI(
    title="OneClickAI Event Bus",
    description="WebSocket relay that streams agent events to the dashboard in real time.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow dashboard (React dev server typically on port 3000) to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.post("/event", status_code=202)
async def receive_event(event: Event) -> dict[str, str]:
    """Receive an event from an agent and broadcast it to all WS clients.

    Agents call this endpoint via a simple HTTP POST whenever something
    noteworthy happens (registration, RFQ sent, quote received, etc.).
    """
    # Fill in server-side timestamp if the agent didn't provide one
    if not event.timestamp:
        event.timestamp = datetime.now(timezone.utc).isoformat()

    # Extract run_id from data.run_id if not set at top level
    if not event.run_id and event.data.get("run_id"):
        event.run_id = str(event.data["run_id"])

    event_dict = event.model_dump()
    logger.info(
        "EVENT  %-25s  from=%-20s  keys=%s",
        event.event_type,
        event.agent_id,
        list(event.data.keys()),
    )
    await manager.broadcast(event_dict)

    # Persist to MongoDB (best-effort, non-blocking)
    if _mongo_collection is not None:
        try:
            await _mongo_collection.insert_one(event_dict.copy())
        except Exception as exc:
            logger.warning("MongoDB insert failed: %s", exc)

    return {"status": "accepted"}


@app.get("/events")
async def get_events(
    limit: int = 100,
    run_id: str = Query(default="", description="Filter events by run_id"),
) -> list[dict[str, Any]]:
    """Return recent event history (most recent last).

    Useful for the dashboard to catch up on page refresh without needing
    a full WebSocket reconnection dance.  Supports ``?run_id=...`` filtering.
    """
    # If MongoDB is available and a run_id filter is requested, query the DB
    if run_id and _mongo_collection is not None:
        try:
            cursor = _mongo_collection.find(
                {"run_id": run_id},
                {"_id": 0},
            ).sort("timestamp", 1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as exc:
            logger.warning("MongoDB query failed, falling back to in-memory: %s", exc)

    # Fallback: in-memory history with optional client-side-style filter
    history = manager.history
    if run_id:
        history = [
            e for e in history
            if e.get("run_id") == run_id or e.get("data", {}).get("run_id") == run_id
        ]
    return history[-limit:]


@app.get("/runs")
async def get_runs() -> list[dict[str, Any]]:
    """Return a list of distinct run_id values with timestamps.

    Useful for a future 'run history' feature.  Falls back to in-memory
    deduplication when MongoDB is unavailable.
    """
    if _mongo_collection is not None:
        try:
            pipeline = [
                {"$match": {"run_id": {"$ne": ""}}},
                {"$group": {
                    "_id": "$run_id",
                    "first_seen": {"$min": "$timestamp"},
                    "last_seen": {"$max": "$timestamp"},
                    "event_count": {"$sum": 1},
                }},
                {"$sort": {"first_seen": -1}},
                {"$limit": 50},
            ]
            cursor = _mongo_collection.aggregate(pipeline)
            runs = []
            async for doc in cursor:
                runs.append({
                    "run_id": doc["_id"],
                    "first_seen": doc["first_seen"],
                    "last_seen": doc["last_seen"],
                    "event_count": doc["event_count"],
                })
            return runs
        except Exception as exc:
            logger.warning("MongoDB aggregation failed: %s", exc)

    # Fallback: derive from in-memory history
    run_map: dict[str, dict[str, Any]] = {}
    for e in manager.history:
        rid = e.get("run_id") or e.get("data", {}).get("run_id", "")
        if not rid:
            continue
        if rid not in run_map:
            run_map[rid] = {"run_id": rid, "first_seen": e.get("timestamp", ""), "last_seen": e.get("timestamp", ""), "event_count": 0}
        run_map[rid]["last_seen"] = e.get("timestamp", "")
        run_map[rid]["event_count"] += 1
    return sorted(run_map.values(), key=lambda r: r["first_seen"], reverse=True)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "event-bus",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return {
        "connected_clients": manager.client_count,
        "total_events": manager.event_count,
        "history_size": len(manager.history),
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Dashboard connects here to receive a real-time stream of events.

    The server sends:
    - A ``HISTORY`` message on connect with recent events.
    - Individual event JSON objects as they arrive.
    - Periodic ``PING`` keep-alive messages.

    The client can send ``PING`` / ``PONG`` text frames; the server echoes
    ``PONG`` for keep-alive.
    """
    await manager.connect(ws)
    try:
        while True:
            # We keep the connection alive by reading from the client.
            # Clients may send "PING" or other messages; we simply acknowledge.
            try:
                raw = await asyncio.wait_for(
                    ws.receive_text(), timeout=HEARTBEAT_INTERVAL
                )
                # Handle client-side ping/pong
                if raw.strip().upper() in ("PING", "ping"):
                    await ws.send_json({"type": "PONG"})
                else:
                    # Attempt to parse as JSON – could be a client command
                    try:
                        msg = json.loads(raw)
                        if msg.get("type") == "PING":
                            await ws.send_json({"type": "PONG"})
                    except (json.JSONDecodeError, AttributeError):
                        pass  # ignore unknown text frames
            except asyncio.TimeoutError:
                # No message from client within the heartbeat window → send ping
                try:
                    await ws.send_json({"type": "PING"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        await manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=EVENT_BUS_PORT,
        reload=False,
        log_level="info",
    )
