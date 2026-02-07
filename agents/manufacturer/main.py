"""Manufacturer Agent Service — LangGraph-powered assembly and coordination.

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
from shared.config import MANUFACTURER_PORT, MANUFACTURER_URL, RESOLVER_URL
from agents.manufacturer.graph import build_manufacturer_graph

AGENT_ID = "manufacturer-agent"

AGENT_FACTS = sign_agent_facts(AgentFacts(
    id=f"nanda:{AGENT_ID}",
    agent_name=f"urn:agent:oneclickai:manufacturer:eu:{AGENT_ID}",
    label="Ferrari Manufacturing Facility",
    description="Ferrari's Maranello assembly facility — LangGraph-based manufacturing orchestration with BOM validation, compliance coordination, logistics integration, and assembly scheduling.",
    version="1.0.0",
    jurisdiction="EU",
    provider=ProviderInfo(name="Ferrari S.p.A.", url="https://ferrari.com", did="did:web:ferrari.com"),
    endpoints=EndpointConfig(
        static=[MANUFACTURER_URL],
        adaptive_resolver=RESOLVER_URL,
        adaptive_resolver_policies=["geo", "load", "threat-shield"],
    ),
    context_requirements=["geo_location", "security_level"],
    role=AgentRole.MANUFACTURER,
    framework="langgraph",
    capabilities=AgentCapabilities(
        modalities=["structured_data"],
        authentication={"methods": ["oauth2", "jwt"], "required_scopes": ["manufacture:execute"]},
    ),
    skills=[
        AgentSkill(id="assembly", description="Full vehicle assembly from validated BOM"),
        AgentSkill(id="bom_validation", description="Validate completeness and compatibility of Bill of Materials"),
        AgentSkill(id="quality_control", description="Multi-stage quality inspection and testing"),
        AgentSkill(id="scheduling", description="Assembly line scheduling and capacity planning"),
    ],
    evaluations=AgentEvaluations(performance_score=4.9, availability_90d="99.95%", last_audited="2025-11-01T00:00:00Z", auditor_id="IATF"),
    telemetry=AgentTelemetry(enabled=True, metrics={"throughput_vehicles_month": 12, "defect_rate": 0.001}),
    certification=AgentCertification(
        level="audited", issuer="IATF (International Automotive Task Force)",
        issuance_date="2025-06-01T00:00:00Z", expiration_date="2026-06-01T00:00:00Z",
        policies=["ISO9001", "ISO14001", "IATF16949"],
        credential_type="W3C-VC-v2",
    ),
    deployment=AgentDeploymentRecord(
        agent_id=f"nanda:{AGENT_ID}",
        resources=[
            DeploymentResource(
                resource_id="manufacturer-maranello-1",
                resource_type="datacenter",
                geo_location="Maranello, Italy",
                geo_lat=44.53, geo_lon=10.86,
                hardware=["cpu", "gpu", "high-memory"],
                bandwidth_mbps=10000.0,
                region="EU",
            ),
            DeploymentResource(
                resource_id="manufacturer-fiorano-1",
                resource_type="edge",
                geo_location="Fiorano, Italy",
                geo_lat=44.52, geo_lon=10.82,
                hardware=["cpu", "ssd"],
                bandwidth_mbps=1000.0,
                region="EU",
            ),
        ],
        deployment_mode="multi-region",
        max_concurrent_sessions=20,
    ),
    facts_ttl=3600,
))

AGENT_ADDR = AgentAddr(
    agent_id=f"nanda:{AGENT_ID}",
    agent_name=AGENT_FACTS.agent_name,
    primary_facts_url=f"{MANUFACTURER_URL}/.well-known/agent-facts",
    adaptive_resolver_url=RESOLVER_URL,
    ttl=3600,
    zone="oneclickai:manufacturer",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await register_with_registry(AGENT_ADDR)
    if AGENT_FACTS.deployment:
        await register_deployment(AGENT_FACTS.deployment)
    print(f"[{AGENT_ID}] Manufacturer Agent ready on port {MANUFACTURER_PORT}")
    yield


app = FastAPI(title="Manufacturer Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/.well-known/agent-facts")
async def get_agent_facts():
    return AGENT_FACTS.model_dump(mode="json")


@app.post("/manufacture")
async def handle_manufacture(order: dict):
    graph = build_manufacturer_graph()
    cid = order.get("correlation_id", order.get("order_id", ""))
    state = {"order": order, "correlation_id": cid}
    result = await graph.ainvoke(state)
    return result.get("confirmation", {"confirmed": True, "notes": "Manufacturing complete"})


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_ID, "framework": "langgraph", "nanda": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=MANUFACTURER_PORT)
