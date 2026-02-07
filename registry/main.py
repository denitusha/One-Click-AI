"""NANDA Lean Index Service — DNS-like discovery for supply-chain agents.

Implements the NANDA paper's two-step resolution:
  1. Client queries index → receives AgentAddr (lean pointer ~120 bytes)
  2. Client fetches AgentFacts from primary_facts_url or private_facts_url

Resolution paths supported:
  - Direct:    AgentName → Index → AgentAddr → Endpoint
  - Metadata:  AgentName → Index → AgentAddr → FactsURL → AgentFacts
  - Privacy:   AgentName → Index → AgentAddr → PrivateFactsURL → AgentFacts
  - Adaptive:  AgentName → Index → AgentAddr → AdaptiveResolver → Endpoint
"""

from __future__ import annotations

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.agent_facts import AgentAddr, AgentFacts, RequesterContext
from shared.config import REGISTRY_PORT, RESOLVER_URL
from shared.nanda_crypto import sign_document, verify_signature
from registry.store import NandaIndexStore

store = NandaIndexStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[NANDA Index] Lean Index starting on port {REGISTRY_PORT}")
    yield
    print("[NANDA Index] Shutting down")


app = FastAPI(
    title="NANDA Lean Index",
    description="DNS-like agent registry implementing NANDA two-step resolution",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════════


@app.post("/register", response_model=AgentAddr)
async def register_agent(addr: AgentAddr):
    """Register a lean AgentAddr in the index.

    Agents call this on startup, providing their agent_id, agent_name (URN),
    primary_facts_url, and optional private_facts_url / adaptive_resolver_url.
    The registry signs the record and stores it.
    """
    # Sign the AgentAddr
    payload = addr.model_dump(mode="json", exclude={"signature"})
    addr.signature = sign_document(payload)
    addr.registered_at = datetime.utcnow().isoformat()

    registered = store.register(addr)
    print(
        f"[NANDA Index] Registered: {registered.agent_id} "
        f"(name={registered.agent_name}, ttl={registered.ttl}s)"
    )
    return registered


# ═══════════════════════════════════════════════════════════════════════════
# Resolution (analogous to DNS lookup)
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/resolve/{agent_id}", response_model=AgentAddr)
async def resolve_by_id(agent_id: str):
    """Direct resolution: agent_id → AgentAddr.

    Resolution path: AgentID → Index → AgentAddr
    """
    addr = store.resolve_by_id(agent_id)
    if not addr:
        raise HTTPException(status_code=404, detail="Agent not found or TTL expired")
    return addr


@app.get("/resolve/name/{agent_name:path}", response_model=AgentAddr)
async def resolve_by_name(agent_name: str):
    """Name resolution: agent_name (URN) → AgentAddr.

    Resolution path: AgentName → Index → AgentAddr
    """
    addr = store.resolve_by_name(agent_name)
    if not addr:
        raise HTTPException(status_code=404, detail="Agent name not found or TTL expired")
    return addr


@app.get("/resolve/{agent_id}/facts")
async def resolve_and_fetch_facts(agent_id: str, prefer_private: bool = False):
    """Two-step resolution: resolve AgentAddr then fetch the AgentFacts.

    Resolution paths:
      - Default:  AgentID → Index → AgentAddr → PrimaryFactsURL → AgentFacts
      - Private:  AgentID → Index → AgentAddr → PrivateFactsURL → AgentFacts
    """
    addr = store.resolve_by_id(agent_id)
    if not addr:
        raise HTTPException(status_code=404, detail="Agent not found or TTL expired")

    # Choose resolution path
    facts_url = (
        addr.private_facts_url if (prefer_private and addr.private_facts_url)
        else addr.primary_facts_url
    )

    # Fetch AgentFacts from the agent's self-hosted endpoint
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(facts_url)
            resp.raise_for_status()
            facts_data = resp.json()
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch AgentFacts from {facts_url}: {exc}",
            )

    return {
        "resolution_path": "private" if prefer_private else "primary",
        "agent_addr": addr.model_dump(mode="json"),
        "agent_facts": facts_data,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Context-Aware Resolution (Adaptive Resolver paper)
# ═══════════════════════════════════════════════════════════════════════════


class ContextResolveRequest(BaseModel):
    """Resolution query with requester context — per Adaptive Resolver paper."""
    agent_name: str
    context: RequesterContext = RequesterContext()


@app.post("/resolve/adaptive")
async def resolve_with_context(req: ContextResolveRequest):
    """Context-aware resolution: AgentName + Context → Tailored Endpoint.

    Resolution flow per Adaptive Resolver paper:
      1. Resolve agent_name → AgentAddr via lean index
      2. If agent has adaptive_resolver_url → delegate to adaptive resolver
      3. Otherwise → return AgentAddr with resolution metadata

    Different requesters may get different endpoints to the same agent.
    """
    addr = store.resolve_by_name(req.agent_name)
    if not addr:
        # Try fuzzy match on the last segment of the URN
        name_part = req.agent_name.split(":")[-1] if ":" in req.agent_name else req.agent_name
        results = store.discover(query=name_part)
        if results:
            addr = results[0]
        else:
            raise HTTPException(404, f"Agent '{req.agent_name}' not found in index")

    # Check if agent has an adaptive resolver → delegate to it
    if addr.adaptive_resolver_url:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{addr.adaptive_resolver_url}/resolve",
                    json={"agent_name": addr.agent_name, "context": req.context.model_dump(mode="json")},
                )
                if resp.status_code == 200:
                    return {
                        "resolution_path": "adaptive",
                        "resolver_url": addr.adaptive_resolver_url,
                        "tailored_result": resp.json(),
                    }
            except Exception as exc:
                print(f"[NANDA Index] Adaptive resolver delegation failed: {exc}, falling back")

    # Check if hierarchical referral is needed
    if addr.authoritative_ns and addr.authoritative_ns != f"http://localhost:{REGISTRY_PORT}":
        return {
            "resolution_path": "referral",
            "agent_addr": addr.model_dump(mode="json"),
            "referral_to": addr.authoritative_ns,
            "zone": addr.zone,
            "message": f"Refer to authoritative NS for zone '{addr.zone}'",
        }

    # Default: return AgentAddr with context acknowledgment
    return {
        "resolution_path": "direct",
        "agent_addr": addr.model_dump(mode="json"),
        "context_received": req.context.model_dump(mode="json", exclude_none=True),
        "note": "No adaptive resolver configured — returning lean AgentAddr for direct resolution",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Discovery
# ═══════════════════════════════════════════════════════════════════════════


class DiscoverRequest(BaseModel):
    role: Optional[str] = None
    capability: Optional[str] = None
    jurisdiction: Optional[str] = None
    query: Optional[str] = None


@app.post("/discover", response_model=list[AgentAddr])
async def discover_agents(req: DiscoverRequest):
    """Semantic discovery — search the lean index by role, capability, jurisdiction.

    For richer filtering (skills, evaluations), clients should fetch
    AgentFacts from returned primary_facts_url endpoints.
    """
    results = store.discover(
        role=req.role,
        capability=req.capability,
        jurisdiction=req.jurisdiction,
        query=req.query,
    )
    print(
        f"[NANDA Index] Discovery: role={req.role} cap={req.capability} "
        f"jur={req.jurisdiction} -> {len(results)} results"
    )
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Listing & Admin
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/agents", response_model=list[AgentAddr])
async def list_agents():
    """List all registered AgentAddr records (non-expired)."""
    return store.list_all()


@app.get("/agents/{agent_id}", response_model=AgentAddr)
async def get_agent(agent_id: str):
    """Get a specific AgentAddr."""
    addr = store.resolve_by_id(agent_id)
    if not addr:
        raise HTTPException(status_code=404, detail="Agent not found")
    return addr


@app.delete("/agents/{agent_id}")
async def deregister_agent(agent_id: str):
    """Remove an agent from the index."""
    if not store.remove(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "removed", "agent_id": agent_id}


class VerifyRequest(BaseModel):
    agent_addr: dict


@app.post("/verify")
async def verify_agent_addr(req: VerifyRequest):
    """Verify the signature on an AgentAddr record."""
    payload = {k: v for k, v in req.agent_addr.items() if k != "signature"}
    sig = req.agent_addr.get("signature", "")
    valid = verify_signature(payload, sig)
    return {"valid": valid, "agent_id": req.agent_addr.get("agent_id")}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "nanda-lean-index",
        "agents_count": store.count(),
        "architecture": "NANDA two-step resolution",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=REGISTRY_PORT)
