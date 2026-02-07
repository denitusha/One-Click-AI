"""Coordinator WebSocket Hub — aggregates all inter-agent messages, streams to frontend."""

from __future__ import annotations

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.config import COORDINATOR_PORT
from shared.schemas import AgentMessage, NetworkCoordinationReport
from coordinator.report import ReportBuilder

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

connected_clients: list[WebSocket] = []
event_log: list[dict[str, Any]] = []
reports: dict[str, NetworkCoordinationReport] = {}
builders: dict[str, ReportBuilder] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def broadcast(event: dict) -> None:
    """Send an event to every connected WebSocket client."""
    event_log.append(event)
    dead: list[WebSocket] = []
    for ws in connected_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[Coordinator] Hub starting on port {COORDINATOR_PORT}")
    yield
    print("[Coordinator] Shutting down")


app = FastAPI(title="Coordinator Hub", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket endpoint ---------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    print(f"[Coordinator] Client connected ({len(connected_clients)} total)")
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        connected_clients.remove(ws)
        print(f"[Coordinator] Client disconnected ({len(connected_clients)} total)")


# --- REST endpoints -------------------------------------------------------

@app.post("/events")
async def receive_event(msg: AgentMessage):
    """Agents POST messages here; the hub logs and broadcasts them."""
    event = {
        "type": "agent_message",
        "data": msg.model_dump(mode="json"),
        "received_at": datetime.utcnow().isoformat(),
    }
    print(
        f"[Coordinator] {msg.sender_id} -> {msg.receiver_id} "
        f"({msg.message_type.value}): {(msg.explanation or '')[:80]}"
    )
    await broadcast(event)

    # Track in report builder if correlation_id exists
    cid = msg.correlation_id
    if cid and cid in builders:
        builders[cid].add_step(
            from_agent=msg.sender_id,
            to_agent=msg.receiver_id,
            action=msg.message_type.value,
            message_type=msg.message_type,
            explanation=msg.explanation,
        )

    return {"status": "ok"}


class StartCascade(BaseModel):
    correlation_id: str
    intent: str


@app.post("/cascade/start")
async def start_cascade(req: StartCascade):
    """Signal the start of a new coordination cascade."""
    builders[req.correlation_id] = ReportBuilder(intent=req.intent)
    await broadcast(
        {
            "type": "cascade_start",
            "correlation_id": req.correlation_id,
            "intent": req.intent,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
    return {"status": "started", "correlation_id": req.correlation_id}


class DiscoveryPathPayload(BaseModel):
    correlation_id: str
    query: dict
    matched_agents: list[str]


class TrustRecordPayload(BaseModel):
    correlation_id: str
    agent_id: str
    reputation_score: float
    verified: bool
    certification_level: str = "unknown"


class PolicyRecordPayload(BaseModel):
    correlation_id: str
    order_id: str
    compliant: bool
    issues: list[str] = []


class FinalPlanPayload(BaseModel):
    correlation_id: str
    plan: dict
    total_cost: float = 0.0
    total_lead_time_days: int = 0


@app.post("/cascade/{correlation_id}/discovery")
async def add_discovery(correlation_id: str, payload: DiscoveryPathPayload):
    """Record a NANDA discovery path in the report."""
    builder = builders.get(correlation_id)
    if not builder:
        return {"error": "Unknown cascade"}
    builder.add_discovery_path(payload.query, payload.matched_agents)
    return {"status": "ok"}


@app.post("/cascade/{correlation_id}/trust")
async def add_trust(correlation_id: str, payload: TrustRecordPayload):
    """Record a trust verification entry in the report."""
    builder = builders.get(correlation_id)
    if not builder:
        return {"error": "Unknown cascade"}
    builder.add_trust_record(payload.agent_id, payload.reputation_score, payload.verified)
    # Also store certification_level in the record
    builder.trust_verification[-1]["certification_level"] = payload.certification_level
    return {"status": "ok"}


@app.post("/cascade/{correlation_id}/policy")
async def add_policy(correlation_id: str, payload: PolicyRecordPayload):
    """Record a policy enforcement entry in the report."""
    builder = builders.get(correlation_id)
    if not builder:
        return {"error": "Unknown cascade"}
    builder.add_policy_record(payload.order_id, payload.compliant, payload.issues)
    return {"status": "ok"}


@app.post("/cascade/{correlation_id}/plan")
async def set_final_plan(correlation_id: str, payload: FinalPlanPayload):
    """Set the final execution plan with cost and timing."""
    builder = builders.get(correlation_id)
    if not builder:
        return {"error": "Unknown cascade"}
    builder.final_plan = payload.plan
    builder.total_cost = payload.total_cost
    builder.total_lead_time_days = payload.total_lead_time_days
    return {"status": "ok"}


@app.post("/cascade/{correlation_id}/complete")
async def complete_cascade(correlation_id: str):
    """Finalize a cascade and generate the Network Coordination Report."""
    builder = builders.get(correlation_id)
    if not builder:
        return {"error": "Unknown cascade"}
    report = builder.build()
    reports[correlation_id] = report
    await broadcast(
        {
            "type": "cascade_complete",
            "correlation_id": correlation_id,
            "report": report.model_dump(mode="json"),
        }
    )
    return report.model_dump(mode="json")


@app.get("/events")
async def get_events():
    """Return the full event log."""
    return event_log


@app.get("/reports")
async def get_reports():
    """Return all generated reports."""
    return {k: v.model_dump(mode="json") for k, v in reports.items()}


@app.get("/reports/{correlation_id}")
async def get_report(correlation_id: str):
    r = reports.get(correlation_id)
    if not r:
        return {"error": "Report not found"}
    return r.model_dump(mode="json")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "coordinator",
        "connected_clients": len(connected_clients),
        "events_logged": len(event_log),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=COORDINATOR_PORT)
