"""Logistics Agent Service — AutoGen-based route planning.

NANDA-compliant: self-hosts AgentFacts at /.well-known/agent-facts.
"""

from __future__ import annotations

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.agent_base import register_with_registry, register_deployment, sign_agent_facts
from shared.agent_facts import (
    AgentAddr, AgentCapabilities, AgentCertification, AgentDeploymentRecord,
    AgentEvaluations, AgentFacts, AgentRole, AgentSkill, AgentTelemetry,
    DeploymentResource, EndpointConfig, ProviderInfo,
)
from shared.config import LOGISTICS_PORT, LOGISTICS_URL, RESOLVER_URL
from agents.logistics.agent import plan_route

AGENT_ID = "logistics-agent"

AGENT_FACTS = sign_agent_facts(AgentFacts(
    id=f"nanda:{AGENT_ID}",
    agent_name=f"urn:agent:oneclickai:logistics:eu:{AGENT_ID}",
    label="TransEuropa Logistics",
    description="European logistics provider specializing in high-value automotive freight. Supports road, rail, and multimodal transport with real-time route optimization.",
    version="1.0.0",
    jurisdiction="EU",
    provider=ProviderInfo(name="TransEuropa Logistics GmbH", url="https://transeuropa.example.com"),
    endpoints=EndpointConfig(
        static=[LOGISTICS_URL],
        adaptive_resolver=RESOLVER_URL,
        adaptive_resolver_policies=["geo", "load"],
    ),
    context_requirements=["geo_location", "qos_requirements"],
    deployment=AgentDeploymentRecord(
        agent_id=f"nanda:{AGENT_ID}",
        resources=[
            DeploymentResource(
                resource_id="logistics-rotterdam-1",
                resource_type="datacenter",
                geo_location="Rotterdam, Netherlands",
                geo_lat=51.92, geo_lon=4.48,
                hardware=["cpu", "ssd"],
                bandwidth_mbps=5000.0,
                region="EU",
            ),
            DeploymentResource(
                resource_id="logistics-hamburg-1",
                resource_type="edge",
                geo_location="Hamburg, Germany",
                geo_lat=53.55, geo_lon=9.99,
                hardware=["cpu"],
                bandwidth_mbps=1000.0,
                region="EU",
            ),
        ],
        deployment_mode="multi-region",
        max_concurrent_sessions=500,
    ),
    role=AgentRole.LOGISTICS,
    framework="autogen",
    capabilities=AgentCapabilities(
        modalities=["structured_data"],
        authentication={"methods": ["api_key"], "required_scopes": ["logistics:route"]},
    ),
    skills=[
        AgentSkill(id="route_planning", description="Multi-modal route optimization across European transport networks"),
        AgentSkill(id="cost_estimation", description="Real-time freight cost calculation based on weight, volume, and urgency"),
        AgentSkill(id="scheduling", description="Delivery scheduling with carrier coordination"),
        AgentSkill(id="multimodal_transport", description="Road, rail, and combined transport planning"),
    ],
    evaluations=AgentEvaluations(performance_score=4.6, availability_90d="99.7%"),
    telemetry=AgentTelemetry(enabled=True, metrics={"avg_route_time_ms": 800, "on_time_delivery": 0.96}),
    certification=AgentCertification(
        level="verified", issuer="European Freight Alliance",
        issuance_date="2025-09-01T00:00:00Z", expiration_date="2026-09-01T00:00:00Z",
        policies=["GDP-compliant", "ADR-certified", "CO2-tracking"],
    ),
    facts_ttl=1800,
))

AGENT_ADDR = AgentAddr(
    agent_id=f"nanda:{AGENT_ID}",
    agent_name=AGENT_FACTS.agent_name,
    primary_facts_url=f"{LOGISTICS_URL}/.well-known/agent-facts",
    adaptive_resolver_url=RESOLVER_URL,
    ttl=1800,
    zone="oneclickai:logistics",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await register_with_registry(AGENT_ADDR)
    if AGENT_FACTS.deployment:
        await register_deployment(AGENT_FACTS.deployment)
    print(f"[{AGENT_ID}] Logistics Agent ready on port {LOGISTICS_PORT}")
    yield


app = FastAPI(title="Logistics Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/.well-known/agent-facts")
async def get_agent_facts():
    return AGENT_FACTS.model_dump(mode="json")


@app.post("/route")
async def handle_route(request: dict):
    return await plan_route(request)


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_ID, "framework": "autogen", "nanda": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=LOGISTICS_PORT)
