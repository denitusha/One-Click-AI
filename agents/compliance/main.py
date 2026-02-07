"""Compliance Agent Service — LangGraph-based policy and ESG validation.

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
from shared.config import COMPLIANCE_PORT, COMPLIANCE_URL, RESOLVER_URL
from agents.compliance.graph import build_compliance_graph

AGENT_ID = "compliance-agent"

AGENT_FACTS = sign_agent_facts(AgentFacts(
    id=f"nanda:{AGENT_ID}",
    agent_name=f"urn:agent:oneclickai:compliance:eu:{AGENT_ID}",
    label="EU Regulatory Compliance Service",
    description="LangGraph-based compliance agent enforcing EU trade regulations, REACH/RoHS directives, and ESG sustainability frameworks with multi-stage jurisdiction, policy, and environmental validation.",
    version="1.0.0",
    jurisdiction="EU",
    provider=ProviderInfo(name="EU Compliance Services", url="https://eucompliance.example.com"),
    endpoints=EndpointConfig(
        static=[COMPLIANCE_URL],
        adaptive_resolver=RESOLVER_URL,
        adaptive_resolver_policies=["geo", "load", "threat-shield"],
    ),
    context_requirements=["geo_location", "security_level"],
    deployment=AgentDeploymentRecord(
        agent_id=f"nanda:{AGENT_ID}",
        resources=[DeploymentResource(
            resource_id="compliance-brussels-1",
            resource_type="datacenter",
            geo_location="Brussels, Belgium",
            geo_lat=50.85, geo_lon=4.35,
            hardware=["cpu", "high-memory"],
            bandwidth_mbps=5000.0,
            region="EU",
        )],
        deployment_mode="single-origin",
        max_concurrent_sessions=100,
    ),
    role=AgentRole.COMPLIANCE,
    framework="langgraph",
    capabilities=AgentCapabilities(
        modalities=["structured_data"],
        authentication={"methods": ["api_key", "jwt"], "required_scopes": ["compliance:check"]},
    ),
    skills=[
        AgentSkill(id="jurisdiction_validation", description="Validate cross-border trade compliance including sanctions and export controls"),
        AgentSkill(id="policy_enforcement", description="Verify ISO, REACH, RoHS, and industry-standard policy compliance"),
        AgentSkill(id="esg_assessment", description="Environmental, Social, and Governance impact scoring"),
        AgentSkill(id="sanctions_screening", description="Screen entities against international sanctions lists"),
    ],
    evaluations=AgentEvaluations(performance_score=4.85, availability_90d="99.99%", last_audited="2026-01-15T00:00:00Z", auditor_id="EU Regulatory Authority"),
    telemetry=AgentTelemetry(enabled=True, metrics={"avg_check_time_s": 3, "false_positive_rate": 0.002}),
    certification=AgentCertification(
        level="audited", issuer="EU Regulatory Authority",
        issuance_date="2025-07-01T00:00:00Z", expiration_date="2026-07-01T00:00:00Z",
        policies=["EU-regulatory", "REACH", "RoHS", "ESG-framework"],
        credential_type="W3C-VC-v2",
        revocation_url="https://eucompliance.example.com/vc-status",
    ),
    facts_ttl=3600,
))

AGENT_ADDR = AgentAddr(
    agent_id=f"nanda:{AGENT_ID}",
    agent_name=AGENT_FACTS.agent_name,
    primary_facts_url=f"{COMPLIANCE_URL}/.well-known/agent-facts",
    adaptive_resolver_url=RESOLVER_URL,
    ttl=3600,
    zone="oneclickai:compliance",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await register_with_registry(AGENT_ADDR)
    if AGENT_FACTS.deployment:
        await register_deployment(AGENT_FACTS.deployment)
    print(f"[{AGENT_ID}] Compliance Agent ready on port {COMPLIANCE_PORT}")
    yield


app = FastAPI(title="Compliance Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/.well-known/agent-facts")
async def get_agent_facts():
    return AGENT_FACTS.model_dump(mode="json")


@app.post("/check")
async def handle_check(request: dict):
    graph = build_compliance_graph()
    state = {"check_request": request}
    result = await graph.ainvoke(state)
    return result.get("final_result", {"compliant": True, "issues": []})


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_ID, "framework": "langgraph", "nanda": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=COMPLIANCE_PORT)
