"""Procurement Agent Service — LangGraph-powered entry point for one-click procurement.

NANDA-compliant: self-hosts AgentFacts at /.well-known/agent-facts,
registers lean AgentAddr with the NANDA index.
"""

from __future__ import annotations

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.agent_base import register_with_registry, register_deployment, sign_agent_facts
from shared.agent_facts import (
    AgentAddr,
    AgentCapabilities,
    AgentCertification,
    AgentDeploymentRecord,
    AgentEvaluations,
    AgentFacts,
    AgentRole,
    AgentSkill,
    AgentTelemetry,
    DeploymentResource,
    EndpointConfig,
    ProviderInfo,
)
from shared.config import PROCUREMENT_PORT, PROCUREMENT_URL, RESOLVER_URL

from agents.procurement.graph import build_procurement_graph

AGENT_ID = "procurement-agent"

# ── NANDA AgentFacts (rich metadata, self-hosted) ─────────────────────────
AGENT_FACTS = sign_agent_facts(AgentFacts(
    id=f"nanda:{AGENT_ID}",
    agent_name=f"urn:agent:oneclickai:{AGENT_ID}",
    label="Procurement Agent",
    description="LangGraph-powered procurement agent that orchestrates the full buy-side coordination cascade — intent parsing, supplier discovery, RFQ, negotiation, and order placement.",
    version="1.0.0",
    documentation_url=f"{PROCUREMENT_URL}/docs",
    jurisdiction="global",
    provider=ProviderInfo(name="One Click AI", url="https://oneclickai.dev"),
    endpoints=EndpointConfig(
        static=[PROCUREMENT_URL],
        adaptive_resolver=RESOLVER_URL,
        adaptive_resolver_policies=["geo", "load"],
    ),
    context_requirements=["geo_location"],
    role=AgentRole.PROCUREMENT,
    framework="langgraph",
    capabilities=AgentCapabilities(
        modalities=["text", "structured_data"],
        streaming=False,
        batch=False,
        authentication={"methods": ["api_key"], "required_scopes": ["procure:execute"]},
    ),
    skills=[
        AgentSkill(id="intent_parsing", description="Parse natural language procurement intents into structured BOM", input_modes=["text"], output_modes=["structured_data"]),
        AgentSkill(id="supplier_discovery", description="Discover and evaluate suppliers via NANDA registry", input_modes=["structured_data"], output_modes=["structured_data"]),
        AgentSkill(id="rfq_management", description="Broadcast RFQs and collect supplier quotes", input_modes=["structured_data"], output_modes=["structured_data"]),
        AgentSkill(id="negotiation", description="LLM-driven price and lead-time negotiation", input_modes=["structured_data"], output_modes=["structured_data"]),
        AgentSkill(id="order_placement", description="Place confirmed orders with selected suppliers", input_modes=["structured_data"], output_modes=["structured_data"]),
    ],
    evaluations=AgentEvaluations(performance_score=4.5, availability_90d="99.8%"),
    telemetry=AgentTelemetry(enabled=True, metrics={"avg_cascade_time_s": 45, "success_rate": 0.97}),
    certification=AgentCertification(
        level="verified",
        issuer="One Click AI",
        issuance_date="2026-01-01T00:00:00Z",
        expiration_date="2027-01-01T00:00:00Z",
        policies=["best-value", "multi-source"],
    ),
    deployment=AgentDeploymentRecord(
        agent_id=f"nanda:{AGENT_ID}",
        resources=[DeploymentResource(
            resource_id="procurement-eu-1",
            resource_type="datacenter",
            geo_location="Maranello, Italy",
            geo_lat=44.53,
            geo_lon=10.86,
            hardware=["cpu", "ssd"],
            bandwidth_mbps=1000.0,
            region="EU",
        )],
        deployment_mode="single-origin",
        max_concurrent_sessions=50,
    ),
    facts_ttl=3600,
))

# ── NANDA AgentAddr (lean record for the index) ──────────────────────────
AGENT_ADDR = AgentAddr(
    agent_id=f"nanda:{AGENT_ID}",
    agent_name=f"urn:agent:oneclickai:{AGENT_ID}",
    primary_facts_url=f"{PROCUREMENT_URL}/.well-known/agent-facts",
    private_facts_url=None,
    adaptive_resolver_url=RESOLVER_URL,
    ttl=3600,
    zone="oneclickai:procurement",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await register_with_registry(AGENT_ADDR)
    if AGENT_FACTS.deployment:
        await register_deployment(AGENT_FACTS.deployment)
    print(f"[{AGENT_ID}] Procurement Agent ready on port {PROCUREMENT_PORT}")
    yield


app = FastAPI(title="Procurement Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── NANDA: self-host AgentFacts ───────────────────────────────────────────

@app.get("/.well-known/agent-facts")
async def get_agent_facts():
    """Self-hosted AgentFacts endpoint per NANDA specification."""
    return AGENT_FACTS.model_dump(mode="json")


# ── Business endpoints ────────────────────────────────────────────────────

class IntentRequest(BaseModel):
    intent: str
    correlation_id: str | None = None


@app.post("/intent")
async def handle_intent(req: IntentRequest):
    """Entry point: user declares procurement intent."""
    cid = req.correlation_id or str(uuid.uuid4())
    graph = build_procurement_graph()
    initial_state = {"intent": req.intent, "correlation_id": cid}

    try:
        result = await graph.ainvoke(initial_state)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "correlation_id": cid,
            "error": str(exc),
        }

    return {
        "status": "completed",
        "correlation_id": cid,
        "order": result.get("order"),
        "manufacturing_result": result.get("manufacturing_result"),
        "report": result.get("report"),
        "quotes_received": len(result.get("quotes", [])),
        "best_quote": result.get("best_quote"),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_ID, "framework": "langgraph", "nanda": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PROCUREMENT_PORT)
