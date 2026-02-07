"""Supplier Agent Service — AutoGen-based, cross-framework interop demo.

NANDA-compliant: self-hosts AgentFacts at /.well-known/agent-facts,
registers lean AgentAddr with the NANDA index.
"""

from __future__ import annotations

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from shared.config import SUPPLIER1_PORT, SUPPLIER1_URL, SUPPLIER2_PORT, SUPPLIER2_URL, RESOLVER_URL
from agents.supplier.agent import process_negotiation, process_rfq

# --- Configuration via env var ---
INSTANCE = os.getenv("SUPPLIER_INSTANCE", "1")

if INSTANCE == "2":
    AGENT_ID = "supplier-agent-2"
    PORT = SUPPLIER2_PORT
    URL = SUPPLIER2_URL
    AGENT_FACTS = sign_agent_facts(AgentFacts(
        id=f"nanda:{AGENT_ID}",
        agent_name=f"urn:agent:oneclickai:supplier:global:{AGENT_ID}",
        label="Global Value Parts Co.",
        description="Global supplier with competitive pricing and wide component availability.",
        version="1.0.0",
        jurisdiction="global",
        provider=ProviderInfo(name="Global Value Parts Co.", url="https://globalvalueparts.example.com"),
        endpoints=EndpointConfig(
            static=[URL],
            adaptive_resolver=RESOLVER_URL,
            adaptive_resolver_policies=["geo", "load"],
        ),
        context_requirements=["geo_location"],
        deployment=AgentDeploymentRecord(
            agent_id=f"nanda:{AGENT_ID}",
            resources=[DeploymentResource(
                resource_id="supplier2-shenzhen-1",
                resource_type="datacenter",
                geo_location="Shenzhen, China",
                geo_lat=22.54, geo_lon=114.06,
                hardware=["cpu", "ssd"],
                bandwidth_mbps=5000.0,
                region="Asia-Pacific",
            )],
            deployment_mode="single-origin",
            max_concurrent_sessions=200,
        ),
        role=AgentRole.SUPPLIER,
        framework="autogen",
        capabilities=AgentCapabilities(
            modalities=["structured_data"],
            authentication={"methods": ["api_key"], "required_scopes": ["supplier:quote"]},
        ),
        skills=[
            AgentSkill(id="engine_parts", description="V12 engine blocks and turbocharger assemblies"),
            AgentSkill(id="chassis", description="Carbon fiber and aluminum chassis components"),
            AgentSkill(id="electronics", description="ECUs, infotainment, and sensor systems"),
            AgentSkill(id="tires", description="High-performance tire supply"),
            AgentSkill(id="brakes", description="Carbon ceramic brake systems"),
            AgentSkill(id="interior", description="Leather interior kits"),
            AgentSkill(id="body_panels", description="Aluminum body panel fabrication"),
        ],
        evaluations=AgentEvaluations(performance_score=4.4, availability_90d="99.5%"),
        telemetry=AgentTelemetry(enabled=True, metrics={"avg_quote_time_s": 2}),
        certification=AgentCertification(
            level="verified", issuer="ISO Certification Authority",
            issuance_date="2025-06-01T00:00:00Z", expiration_date="2026-06-01T00:00:00Z",
            policies=["ISO9001", "competitive-pricing"],
        ),
        facts_ttl=1800,
    ))
    PRICE_MODIFIER = 0.90
else:
    AGENT_ID = "supplier-agent-1"
    PORT = SUPPLIER1_PORT
    URL = SUPPLIER1_URL
    AGENT_FACTS = sign_agent_facts(AgentFacts(
        id=f"nanda:{AGENT_ID}",
        agent_name=f"urn:agent:oneclickai:supplier:eu:{AGENT_ID}",
        label="Euro Premium Components GmbH",
        description="Premium European supplier specializing in high-performance automotive components. ESG-compliant and REACH-certified.",
        version="1.0.0",
        jurisdiction="EU",
        provider=ProviderInfo(name="Euro Premium Components GmbH", url="https://europremium.example.com", did="did:web:europremium.example.com"),
        endpoints=EndpointConfig(
            static=[URL],
            adaptive_resolver=RESOLVER_URL,
            adaptive_resolver_policies=["geo", "load", "threat-shield"],
        ),
        context_requirements=["geo_location", "security_level"],
        deployment=AgentDeploymentRecord(
            agent_id=f"nanda:{AGENT_ID}",
            resources=[
                DeploymentResource(
                    resource_id="supplier1-stuttgart-1",
                    resource_type="datacenter",
                    geo_location="Stuttgart, Germany",
                    geo_lat=48.78, geo_lon=9.18,
                    hardware=["cpu", "high-memory", "ssd"],
                    bandwidth_mbps=10000.0,
                    region="EU",
                ),
                DeploymentResource(
                    resource_id="supplier1-milan-1",
                    resource_type="edge",
                    geo_location="Milan, Italy",
                    geo_lat=45.46, geo_lon=9.19,
                    hardware=["cpu", "ssd"],
                    bandwidth_mbps=1000.0,
                    region="EU",
                ),
            ],
            deployment_mode="multi-region",
            max_concurrent_sessions=100,
        ),
        role=AgentRole.SUPPLIER,
        framework="autogen",
        capabilities=AgentCapabilities(
            modalities=["structured_data"],
            authentication={"methods": ["api_key", "oauth2"], "required_scopes": ["supplier:quote", "supplier:negotiate"]},
        ),
        skills=[
            AgentSkill(id="engine_parts", description="V12 engine blocks and turbocharger assemblies — OEM quality"),
            AgentSkill(id="chassis", description="Carbon fiber monocoque chassis and adaptive suspension"),
            AgentSkill(id="electronics", description="ECUs and OLED infotainment systems"),
            AgentSkill(id="tires", description="Pirelli P Zero high-performance tires"),
            AgentSkill(id="brakes", description="Carbon ceramic brake disc systems"),
            AgentSkill(id="interior", description="Full-grain leather interior kits — Italian craftsmanship"),
            AgentSkill(id="body_panels", description="Hand-welded aluminum body panels"),
        ],
        evaluations=AgentEvaluations(performance_score=4.75, availability_90d="99.9%", last_audited="2025-12-01T00:00:00Z", auditor_id="TUV Rheinland"),
        telemetry=AgentTelemetry(enabled=True, metrics={"avg_quote_time_s": 1.5, "fill_rate": 0.98}),
        certification=AgentCertification(
            level="audited", issuer="TUV Rheinland",
            issuance_date="2025-06-01T00:00:00Z", expiration_date="2026-06-01T00:00:00Z",
            policies=["ISO9001", "ESG-compliant", "REACH-compliant"],
            credential_type="W3C-VC-v2",
        ),
        facts_ttl=1800,
    ))
    PRICE_MODIFIER = 1.0

# ── Lean AgentAddr for the NANDA index ────────────────────────────────────
AGENT_ADDR = AgentAddr(
    agent_id=f"nanda:{AGENT_ID}",
    agent_name=AGENT_FACTS.agent_name,
    primary_facts_url=f"{URL}/.well-known/agent-facts",
    private_facts_url=None,
    adaptive_resolver_url=RESOLVER_URL,
    ttl=1800,
    zone="oneclickai:supplier",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await register_with_registry(AGENT_ADDR)
    if AGENT_FACTS.deployment:
        await register_deployment(AGENT_FACTS.deployment)
    print(f"[{AGENT_ID}] Supplier Agent ready on port {PORT}")
    yield


app = FastAPI(title=f"Supplier Agent ({AGENT_ID})", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/.well-known/agent-facts")
async def get_agent_facts():
    """Self-hosted AgentFacts endpoint per NANDA specification."""
    return AGENT_FACTS.model_dump(mode="json")


@app.post("/rfq")
async def handle_rfq(rfq: dict):
    quote = await process_rfq(rfq, AGENT_ID)
    quote["total_price"] = round(quote["total_price"] * PRICE_MODIFIER, 2)
    for k in quote.get("unit_prices", {}):
        quote["unit_prices"][k] = round(quote["unit_prices"][k] * PRICE_MODIFIER, 2)
    return quote


@app.post("/negotiate")
async def handle_negotiation(proposal: dict):
    return await process_negotiation(proposal, AGENT_ID)


@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_ID, "framework": "autogen", "nanda": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
