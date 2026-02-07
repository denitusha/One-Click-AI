"""NANDA Adaptive Resolver — context-aware dynamic endpoint resolution.

Per the Adaptive Resolver paper, this microservice:
  1. Receives a resolution query with requester context
  2. Checks agent deployment records for available endpoints
  3. Returns *tailored* endpoints based on geo proximity, load, QoS, and security
  4. May return a NegotiationInvitation if trust negotiation is required
  5. Supports referral to authoritative name servers (hierarchical resolution)

Different requesters get different endpoints to the same agent.
"""

from __future__ import annotations

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.agent_facts import (
    AgentAddr,
    AgentDeploymentRecord,
    DeploymentResource,
    NegotiationInvitation,
    RequesterContext,
    TailoredResponse,
)
from shared.config import REGISTRY_URL, RESOLVER_PORT
from shared.nanda_crypto import sign_document

# ---------------------------------------------------------------------------
# In-memory deployment registry (authoritative name server state)
# ---------------------------------------------------------------------------

# agent_id -> AgentDeploymentRecord
deployment_records: dict[str, AgentDeploymentRecord] = {}

# Zone referrals: zone_prefix -> authoritative NS URL
zone_referrals: dict[str, str] = {}

# Cache of resolved agent_addr records (simulates recursive resolver cache)
addr_cache: dict[str, tuple[AgentAddr, float]] = {}  # agent_id -> (addr, expires_at)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[AdaptiveResolver] Starting on port {RESOLVER_PORT}")
    yield
    print("[AdaptiveResolver] Shutting down")


app = FastAPI(
    title="NANDA Adaptive Resolver",
    description="Context-aware dynamic resolution — tailored endpoints per requester",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ═══════════════════════════════════════════════════════════════════════════
# Deployment Record Registration
# ═══════════════════════════════════════════════════════════════════════════


@app.post("/deployments")
async def register_deployment(record: AgentDeploymentRecord):
    """Agents register their deployment metadata with the authoritative resolver."""
    deployment_records[record.agent_id] = record
    print(f"[AdaptiveResolver] Deployment registered: {record.agent_id} "
          f"({len(record.resources)} resources, mode={record.deployment_mode})")
    return {"status": "registered", "agent_id": record.agent_id}


@app.get("/deployments/{agent_id}")
async def get_deployment(agent_id: str):
    record = deployment_records.get(agent_id)
    if not record:
        raise HTTPException(404, "No deployment record")
    return record.model_dump(mode="json")


@app.patch("/deployments/{agent_id}/load")
async def update_load(agent_id: str, load: float):
    """Agents report their current load for adaptive routing."""
    record = deployment_records.get(agent_id)
    if record:
        record.current_load = max(0.0, min(1.0, load))
    return {"agent_id": agent_id, "current_load": load}


# ═══════════════════════════════════════════════════════════════════════════
# Zone Referrals (hierarchical resolution)
# ═══════════════════════════════════════════════════════════════════════════


@app.post("/zones/referral")
async def register_zone_referral(zone: str, authoritative_ns_url: str):
    """Register a zone referral — points a name-space zone to its authoritative NS."""
    zone_referrals[zone] = authoritative_ns_url
    return {"zone": zone, "authoritative_ns": authoritative_ns_url}


@app.get("/zones")
async def list_zones():
    return zone_referrals


# ═══════════════════════════════════════════════════════════════════════════
# Adaptive Resolution — the core API
# ═══════════════════════════════════════════════════════════════════════════


class ResolveRequest(BaseModel):
    agent_name: str
    context: RequesterContext = RequesterContext()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


GEO_LOOKUP: dict[str, tuple[float, float]] = {
    "maranello": (44.53, 10.86),
    "italy": (41.90, 12.50),
    "stuttgart": (48.78, 9.18),
    "germany": (51.16, 10.45),
    "eu": (50.85, 4.35),
    "london": (51.51, -0.13),
    "new york": (40.71, -74.01),
    "us": (39.83, -98.58),
    "global": (0.0, 0.0),
}


def _geo_to_latlon(geo: str | None) -> tuple[float, float] | None:
    if not geo:
        return None
    for key, coords in GEO_LOOKUP.items():
        if key in geo.lower():
            return coords
    return None


def _pick_best_resource(
    resources: list[DeploymentResource],
    requester_lat: float | None,
    requester_lon: float | None,
) -> DeploymentResource | None:
    """Pick the deployment resource closest to the requester (geo-aware dispatch)."""
    if not resources:
        return None
    if requester_lat is None or requester_lon is None:
        return resources[0]

    best = None
    best_dist = float("inf")
    for r in resources:
        if r.geo_lat is not None and r.geo_lon is not None:
            d = _haversine_km(requester_lat, requester_lon, r.geo_lat, r.geo_lon)
        else:
            d = 10000.0  # unknown location penalty
        if d < best_dist:
            best_dist = d
            best = r
    return best


async def _fetch_addr_from_index(agent_name: str) -> AgentAddr | None:
    """Step 1 of recursive resolution: query the lean index."""
    # Check cache first
    for aid, (addr, exp) in list(addr_cache.items()):
        if addr.agent_name == agent_name and exp > time.time():
            return addr

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{REGISTRY_URL}/discover",
                json={"query": agent_name.split(":")[-1] if ":" in agent_name else agent_name},
            )
            resp.raise_for_status()
            results = resp.json()
            for r in results:
                if r.get("agent_name") == agent_name or agent_name in r.get("agent_name", ""):
                    addr = AgentAddr(**r)
                    addr_cache[addr.agent_id] = (addr, time.time() + addr.ttl)
                    return addr
            if results:
                addr = AgentAddr(**results[0])
                addr_cache[addr.agent_id] = (addr, time.time() + addr.ttl)
                return addr
        except Exception as exc:
            print(f"[AdaptiveResolver] Index query failed: {exc}")
    return None


@app.post("/resolve", response_model=None)
async def adaptive_resolve(req: ResolveRequest):
    """Context-aware adaptive resolution — the core Adaptive Resolver API.

    Resolution flow per the paper:
      1. Recursive resolve: agent_name → index → AgentAddr
      2. Check for zone referral (hierarchical delegation)
      3. Fetch deployment record from authoritative NS
      4. Evaluate requester context against target requirements
      5. If negotiation needed → return NegotiationInvitation
      6. Otherwise → pick best endpoint via geo/load/QoS → return TailoredResponse
    """
    ctx = req.context

    # ── Step 1: Recursive resolution to get AgentAddr ──────────────────
    addr = await _fetch_addr_from_index(req.agent_name)
    if not addr:
        raise HTTPException(404, f"Agent '{req.agent_name}' not found in index")

    # ── Step 2: Check zone referrals (hierarchical delegation) ─────────
    if addr.zone and addr.zone in zone_referrals:
        referral_url = zone_referrals[addr.zone]
        return {
            "type": "referral",
            "agent_name": req.agent_name,
            "referral_to": referral_url,
            "zone": addr.zone,
            "message": f"Delegated to authoritative NS for zone '{addr.zone}'",
            "ttl": 3600,
        }

    # ── Step 3: Get deployment record ──────────────────────────────────
    deployment = deployment_records.get(addr.agent_id)

    # ── Step 4: Check context requirements from AgentFacts ─────────────
    # Fetch AgentFacts to see what context the target demands
    missing_context: list[str] = []
    agent_facts_data = None
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(addr.primary_facts_url)
            if resp.status_code == 200:
                agent_facts_data = resp.json()
                required = agent_facts_data.get("context_requirements", [])
                for field in required:
                    val = getattr(ctx, field, None)
                    if val is None:
                        missing_context.append(field)
        except Exception:
            pass

    # ── Step 5: Negotiation required? ──────────────────────────────────
    needs_negotiation = False
    negotiation_reason = ""

    # Missing required context → negotiation
    if missing_context:
        needs_negotiation = True
        negotiation_reason = f"Target requires context: {missing_context}"

    # High security request without matching auth → negotiation
    if ctx.security_level == "zero-trust" and not needs_negotiation:
        needs_negotiation = True
        negotiation_reason = "Zero-trust security requires mutual attestation"

    # Overloaded agent → negotiation for QoS guarantee
    if deployment and deployment.current_load > 0.9 and not needs_negotiation:
        needs_negotiation = True
        negotiation_reason = f"Agent at high load ({deployment.current_load:.0%}), QoS negotiation required"

    if needs_negotiation:
        return NegotiationInvitation(
            agent_id=addr.agent_id,
            negotiation_url=f"{addr.adaptive_resolver_url or addr.primary_facts_url}/negotiate",
            reason=negotiation_reason,
            required_context=missing_context,
            trust_requirements={"security_level": ctx.security_level or "authenticated"},
            ttl=60,
        ).model_dump(mode="json") | {"type": "negotiation_invitation"}

    # ── Step 6: Tailored endpoint selection ────────────────────────────
    context_used: dict[str, Any] = {}

    # Determine requester location
    req_lat = ctx.geo_lat
    req_lon = ctx.geo_lon
    if req_lat is None and ctx.geo_location:
        coords = _geo_to_latlon(ctx.geo_location)
        if coords:
            req_lat, req_lon = coords
            context_used["geo_resolved"] = ctx.geo_location

    # Pick best endpoint based on deployment resources (geo-aware)
    if deployment and deployment.resources:
        best_resource = _pick_best_resource(deployment.resources, req_lat, req_lon)
        if best_resource:
            context_used["geo_nearest_resource"] = best_resource.resource_id
            context_used["resource_location"] = best_resource.geo_location
            if req_lat and best_resource.geo_lat:
                context_used["distance_km"] = round(
                    _haversine_km(req_lat, req_lon, best_resource.geo_lat, best_resource.geo_lon), 1
                )
    else:
        best_resource = None

    # Choose endpoint: adaptive > deployment-specific > static from facts
    endpoint = ""
    if agent_facts_data:
        endpoints = agent_facts_data.get("endpoints", {})
        static_eps = endpoints.get("static", [])
        rotating_eps = endpoints.get("rotating", [])

        if rotating_eps:
            # Load-based selection from rotating pool
            import random
            endpoint = random.choice(rotating_eps)
            context_used["selection"] = "rotating_pool"
        elif static_eps:
            endpoint = static_eps[0]
            context_used["selection"] = "static_primary"
    else:
        endpoint = addr.primary_facts_url.replace("/.well-known/agent-facts", "")
        context_used["selection"] = "derived_from_facts_url"

    # Factor in load balancing
    if deployment:
        context_used["agent_load"] = f"{deployment.current_load:.0%}"
        context_used["deployment_mode"] = deployment.deployment_mode

    # Factor in QoS
    if ctx.qos_requirements:
        context_used["qos_applied"] = ctx.qos_requirements

    # Determine transport
    transport = "https"
    if ctx.session_type == "streaming":
        transport = "wss"
    elif ctx.session_type == "batch":
        transport = "https"
    context_used["transport"] = transport

    # Sign the tailored response
    tailored = TailoredResponse(
        agent_id=addr.agent_id,
        agent_name=addr.agent_name,
        endpoint=endpoint,
        transport=transport,
        ttl=min(addr.ttl, 300),
        context_used=context_used,
        negotiation_required=False,
    )
    payload = tailored.model_dump(mode="json", exclude={"signature"})
    tailored.signature = sign_document(payload)

    return tailored.model_dump(mode="json") | {"type": "tailored_response"}


# ═══════════════════════════════════════════════════════════════════════════
# Negotiation endpoint (simplified)
# ═══════════════════════════════════════════════════════════════════════════


class NegotiateRequest(BaseModel):
    agent_id: str
    requester_context: RequesterContext
    proposed_qos: Optional[dict[str, Any]] = None
    proposed_cost_limit: Optional[float] = None


@app.post("/negotiate")
async def negotiate_comms(req: NegotiateRequest):
    """Simplified negotiation: both parties agree on comms spec.

    Full implementation would involve multi-round exchange; this demo
    shows the structure with a single-round accept/counter.
    """
    deployment = deployment_records.get(req.agent_id)

    # Build comms spec from requester proposal + target capabilities
    comms_spec = {
        "protocol": "https",
        "encryption": "TLS-1.3",
        "auth_method": "jwt",
        "max_latency_ms": (req.proposed_qos or {}).get("max_latency_ms", 1000),
        "session_duration_s": 3600,
    }

    if deployment and deployment.current_load < 0.8:
        return {
            "status": "accepted",
            "comms_spec": comms_spec,
            "agent_id": req.agent_id,
            "message": "Negotiation accepted — comms channel ready",
        }
    else:
        comms_spec["max_latency_ms"] = max(comms_spec["max_latency_ms"], 2000)
        return {
            "status": "counter",
            "comms_spec": comms_spec,
            "agent_id": req.agent_id,
            "message": "Agent under load — adjusted QoS constraints",
        }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "nanda-adaptive-resolver",
        "deployments": len(deployment_records),
        "zones": len(zone_referrals),
        "cached_addrs": len(addr_cache),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=RESOLVER_PORT)
