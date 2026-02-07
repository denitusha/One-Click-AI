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
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

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

    event_dict = event.model_dump()
    logger.info(
        "EVENT  %-25s  from=%-20s  keys=%s",
        event.event_type,
        event.agent_id,
        list(event.data.keys()),
    )
    await manager.broadcast(event_dict)
    return {"status": "accepted"}


@app.get("/events")
async def get_events(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent event history (most recent last).

    Useful for the dashboard to catch up on page refresh without needing
    a full WebSocket reconnection dance.
    """
    history = manager.history
    return history[-limit:]


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
