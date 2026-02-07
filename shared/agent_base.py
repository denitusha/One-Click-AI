"""Shared helpers used by every agent service — NANDA-compliant two-step resolution.

Supports both classic two-step resolution AND adaptive context-aware resolution
per the NANDA Adaptive Resolver paper.
"""

from __future__ import annotations

from typing import Any

import httpx

from shared.agent_facts import (
    AgentAddr,
    AgentDeploymentRecord,
    AgentFacts,
    RequesterContext,
)
from shared.config import COORDINATOR_URL, REGISTRY_URL, RESOLVER_URL
from shared.nanda_crypto import sign_document
from shared.schemas import AgentMessage


# ═══════════════════════════════════════════════════════════════════════════
# Registration (two-step: register AgentAddr with index, self-host AgentFacts)
# ═══════════════════════════════════════════════════════════════════════════


async def register_with_registry(addr: AgentAddr) -> None:
    """POST a lean AgentAddr record to the NANDA index.

    The agent's rich AgentFacts are NOT sent here — they are self-hosted
    at the agent's /.well-known/agent-facts endpoint.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{REGISTRY_URL}/register", json=addr.model_dump(mode="json")
            )
            resp.raise_for_status()
            print(f"[{addr.agent_id}] Registered AgentAddr with NANDA index")
        except Exception as exc:
            print(f"[{addr.agent_id}] Index registration failed: {exc}")


async def register_deployment(record: AgentDeploymentRecord) -> None:
    """Register agent deployment metadata with the adaptive resolver."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{RESOLVER_URL}/deployments", json=record.model_dump(mode="json")
            )
            resp.raise_for_status()
            print(f"[{record.agent_id}] Deployment record registered with resolver")
        except Exception as exc:
            print(f"[{record.agent_id}] Deployment registration failed: {exc}")


async def report_load(agent_id: str, load: float) -> None:
    """Report current load to the adaptive resolver."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            await client.patch(
                f"{RESOLVER_URL}/deployments/{agent_id}/load",
                params={"load": load},
            )
        except Exception:
            pass


def sign_agent_facts(facts: AgentFacts, signing_key: str | None = None) -> AgentFacts:
    """Sign an AgentFacts document."""
    payload = facts.model_dump(mode="json", exclude={"signature"})
    facts.signature = sign_document(payload, signing_key)
    return facts


# ═══════════════════════════════════════════════════════════════════════════
# Discovery (returns AgentAddr records from lean index)
# ═══════════════════════════════════════════════════════════════════════════


async def discover_agents(**kwargs) -> list[AgentAddr]:
    """Query the NANDA lean index — returns AgentAddr records (not full AgentFacts)."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(f"{REGISTRY_URL}/discover", json=kwargs)
            resp.raise_for_status()
            return [AgentAddr(**a) for a in resp.json()]
        except Exception as exc:
            print(f"[Discovery] Failed: {exc}")
            return []


async def fetch_agent_facts(primary_facts_url: str) -> AgentFacts | None:
    """Fetch rich AgentFacts from an agent's self-hosted endpoint.

    This is step 2 of NANDA resolution:
      AgentAddr.primary_facts_url → GET → AgentFacts
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(primary_facts_url)
            resp.raise_for_status()
            return AgentFacts(**resp.json())
        except Exception as exc:
            print(f"[Facts Fetch] Failed for {primary_facts_url}: {exc}")
            return None


async def resolve_agent_endpoint(agent_addr: AgentAddr) -> str | None:
    """Resolve an AgentAddr to its primary static endpoint.

    NANDA resolution paths:
      1. Direct:   AgentAddr → static endpoint
      2. Metadata: AgentAddr → FactsURL → AgentFacts → endpoints.static
      3. Adaptive: AgentAddr → adaptive_resolver_url → ephemeral endpoint

    This helper uses path 2 (metadata resolution) as default.
    """
    # Try fetching AgentFacts to get the endpoint list
    facts = await fetch_agent_facts(agent_addr.primary_facts_url)
    if facts and facts.endpoints.static:
        return facts.endpoints.static[0]
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Adaptive Resolution (per NANDA Adaptive Resolver paper)
# ═══════════════════════════════════════════════════════════════════════════


async def resolve_adaptive(
    agent_name: str,
    context: RequesterContext | None = None,
) -> dict[str, Any]:
    """Context-aware adaptive resolution via the Adaptive Resolver.

    Resolution flow per the Adaptive Resolver paper:
      1. Send agent_name + requester context to the resolver
      2. Resolver may return:
         - TailoredResponse (direct endpoint tailored to context)
         - NegotiationInvitation (trust/QoS negotiation required)
         - Referral (to authoritative NS for the agent's zone)

    Falls back to registry direct resolution if resolver is unavailable.
    """
    ctx = context or RequesterContext()
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{RESOLVER_URL}/resolve",
                json={"agent_name": agent_name, "context": ctx.model_dump(mode="json")},
            )
            resp.raise_for_status()
            result = resp.json()
            result_type = result.get("type", "unknown")
            print(f"[Adaptive] Resolved '{agent_name}' -> {result_type}")
            return result
        except Exception as exc:
            print(f"[Adaptive] Resolver unavailable ({exc}), falling back to index")
            # Fallback: use the registry directly
            addrs = await discover_agents(query=agent_name.split(":")[-1] if ":" in agent_name else agent_name)
            if addrs:
                endpoint = await resolve_agent_endpoint(addrs[0])
                return {
                    "type": "fallback",
                    "agent_id": addrs[0].agent_id,
                    "agent_name": addrs[0].agent_name,
                    "endpoint": endpoint or addrs[0].primary_facts_url.replace("/.well-known/agent-facts", ""),
                    "context_used": {},
                }
            return {"type": "error", "message": f"Agent '{agent_name}' not found"}


async def resolve_with_context_to_endpoint(
    agent_name: str,
    context: RequesterContext | None = None,
) -> str | None:
    """Convenience: adaptive resolve → extract endpoint URL."""
    result = await resolve_adaptive(agent_name, context)
    rtype = result.get("type", "")

    if rtype == "tailored_response":
        return result.get("endpoint")
    elif rtype == "fallback":
        return result.get("endpoint")
    elif rtype == "negotiation_invitation":
        # For now, skip negotiation and try direct resolution
        print(f"[Adaptive] Negotiation required: {result.get('reason')}")
        return None
    elif rtype == "referral":
        print(f"[Adaptive] Referral to: {result.get('referral_to')}")
        return None
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Coordinator communication
# ═══════════════════════════════════════════════════════════════════════════


async def send_agent_message(msg: AgentMessage) -> dict | None:
    """POST a message to the coordinator hub so it's logged + broadcast."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{COORDINATOR_URL}/events", json=msg.model_dump(mode="json")
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"[Msg] Failed to send event: {exc}")
            return None


async def notify_cascade_start(correlation_id: str, intent: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"{COORDINATOR_URL}/cascade/start",
                json={"correlation_id": correlation_id, "intent": intent},
            )
        except Exception as exc:
            print(f"[Cascade] Start notification failed: {exc}")


async def notify_cascade_complete(correlation_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{COORDINATOR_URL}/cascade/{correlation_id}/complete"
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"[Cascade] Complete notification failed: {exc}")
            return None


async def call_agent_endpoint(url: str, payload: dict) -> dict | None:
    """Call another agent's HTTP endpoint directly."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"[Agent Call] {url} failed: {exc}")
            return None
