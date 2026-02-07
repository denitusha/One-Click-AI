"""Procurement Agent — LangGraph state machine.

Flow: parse_intent → discover_suppliers → send_rfqs → evaluate_quotes →
      negotiate → place_order → request_manufacturing

NANDA-compliant: uses two-step resolution (AgentAddr → AgentFacts) for discovery.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from shared.agent_base import (
    call_agent_endpoint,
    discover_agents,
    fetch_agent_facts,
    notify_cascade_complete,
    notify_cascade_start,
    resolve_adaptive,
    resolve_with_context_to_endpoint,
    send_agent_message,
)
from shared.agent_facts import RequesterContext
from shared.config import LLM_MODEL, OPENAI_API_KEY
from shared.schemas import (
    AgentMessage,
    ComponentSpec,
    MessageType,
    RequestForQuote,
)

# ---------------------------------------------------------------------------
# Ferrari BOM (demo data)
# ---------------------------------------------------------------------------

FERRARI_BOM: list[dict[str, Any]] = [
    {"component_id": "ENG-001", "name": "V12 Engine Block", "category": "engine", "quantity": 1, "specifications": {"displacement": "6.5L", "material": "aluminum alloy"}},
    {"component_id": "ENG-002", "name": "Turbocharger Assembly", "category": "engine", "quantity": 2, "specifications": {"type": "twin-scroll"}},
    {"component_id": "CHS-001", "name": "Carbon Fiber Monocoque Chassis", "category": "chassis", "quantity": 1, "specifications": {"material": "carbon fiber", "weight_kg": 120}},
    {"component_id": "CHS-002", "name": "Suspension System", "category": "chassis", "quantity": 4, "specifications": {"type": "adaptive magnetic"}},
    {"component_id": "ELC-001", "name": "ECU (Engine Control Unit)", "category": "electronics", "quantity": 1, "specifications": {"processor": "ARM Cortex-R5"}},
    {"component_id": "ELC-002", "name": "Infotainment Display", "category": "electronics", "quantity": 1, "specifications": {"size": "10.25 inch", "type": "OLED"}},
    {"component_id": "TIR-001", "name": "Pirelli P Zero Tires", "category": "tires", "quantity": 4, "specifications": {"size": "285/30 ZR20", "compound": "soft"}},
    {"component_id": "BRK-001", "name": "Carbon Ceramic Brake Discs", "category": "brakes", "quantity": 4, "specifications": {"diameter_mm": 398}},
    {"component_id": "INT-001", "name": "Leather Interior Kit", "category": "interior", "quantity": 1, "specifications": {"material": "full-grain leather", "color": "Rosso"}},
    {"component_id": "BDY-001", "name": "Aluminum Body Panels", "category": "body", "quantity": 1, "specifications": {"material": "aluminum", "finish": "hand-welded"}},
]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ProcurementState(TypedDict, total=False):
    intent: str
    correlation_id: str
    bom: list[dict]
    discovered_suppliers: list[dict]  # AgentAddr records with resolved endpoint
    rfq_payload: dict
    quotes: list[dict]
    best_quote: dict | None
    negotiation_result: dict | None
    order: dict | None
    manufacturing_result: dict | None
    report: dict | None
    error: str | None


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def get_llm():
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0.3)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def parse_intent(state: ProcurementState) -> ProcurementState:
    """Understand user intent and map to BOM components."""
    intent = state["intent"]
    correlation_id = state.get("correlation_id", str(uuid.uuid4()))

    await notify_cascade_start(correlation_id, intent)

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are a procurement AI. The user says: '{intent}'. "
        f"Identify what type of product they want to procure. "
        f"Respond with ONLY a JSON object: {{\"product\": \"...\", \"category\": \"...\"}}"
    )

    await send_agent_message(AgentMessage(
        sender_id="procurement-agent",
        receiver_id="system",
        message_type=MessageType.INTENT,
        correlation_id=correlation_id,
        payload={"intent": intent, "llm_response": resp.content},
        explanation=f"Parsed user intent: {intent}. Mapped to Ferrari component BOM.",
    ))

    return {
        **state,
        "correlation_id": correlation_id,
        "bom": FERRARI_BOM,
    }


async def discover_suppliers_node(state: ProcurementState) -> ProcurementState:
    """Query NANDA index to find supplier agents (two-step + adaptive resolution)."""

    # Requester context for adaptive resolution (Maranello-based procurement)
    requester_ctx = RequesterContext(
        requester_id="nanda:procurement-agent",
        geo_location="Maranello, Italy",
        geo_lat=44.53,
        geo_lon=10.86,
        security_level="authenticated",
        session_type="request-response",
    )

    # Step 1: Query lean index for AgentAddr records
    supplier_addrs = await discover_agents(role="supplier")

    # Step 2: For each supplier, attempt adaptive resolution, then fallback to AgentFacts
    resolved_suppliers: list[dict] = []
    for addr in supplier_addrs:
        # Try adaptive resolution first (context-aware, tailored endpoint)
        adaptive_result = await resolve_adaptive(addr.agent_name, requester_ctx)
        adaptive_type = adaptive_result.get("type", "")

        # Also fetch AgentFacts for rich metadata
        facts = await fetch_agent_facts(addr.primary_facts_url)

        # Choose endpoint: prefer tailored from adaptive resolver
        if adaptive_type == "tailored_response":
            endpoint = adaptive_result.get("endpoint", "")
            resolution_method = "adaptive_resolver"
        elif facts and facts.endpoints.static:
            endpoint = facts.endpoints.static[0]
            resolution_method = "two_step_facts"
        else:
            endpoint = ""
            resolution_method = "unresolved"

        supplier_info = {
            "agent_id": addr.agent_id,
            "agent_name": addr.agent_name,
            "primary_facts_url": addr.primary_facts_url,
            "endpoint": endpoint,
            # Rich metadata from AgentFacts for trust evaluation
            "label": facts.label if facts else addr.agent_name,
            "jurisdiction": facts.jurisdiction if facts else "unknown",
            "certification_level": facts.certification.level if facts else "unknown",
            "certification_issuer": facts.certification.issuer if facts else "",
            "reputation_score": facts.reputation_score if facts else 0.5,
            "skills": [s.id for s in facts.skills] if facts else [],
            "ttl": addr.ttl,
            "signature_verified": bool(addr.signature),
            # Adaptive resolution metadata
            "resolution_method": resolution_method,
            "adaptive_context_used": adaptive_result.get("context_used", {}),
            "context_requirements": facts.context_requirements if facts else [],
            "deployment_mode": facts.deployment.deployment_mode if facts and facts.deployment else "unknown",
        }
        resolved_suppliers.append(supplier_info)

    await send_agent_message(AgentMessage(
        sender_id="procurement-agent",
        receiver_id="nanda-index",
        message_type=MessageType.DISCOVERY_REQUEST,
        correlation_id=state["correlation_id"],
        payload={
            "query": {"role": "supplier"},
            "resolution_path": "AgentName -> Index -> AgentAddr -> AdaptiveResolver -> TailoredEndpoint (+ FactsURL -> AgentFacts)",
            "requester_context": requester_ctx.model_dump(mode="json", exclude_none=True),
            "results_count": len(resolved_suppliers),
            "agents_discovered": [
                {"id": s["agent_id"], "resolution": s["resolution_method"]}
                for s in resolved_suppliers
            ],
        },
        explanation=(
            f"NANDA adaptive resolution: discovered {len(supplier_addrs)} AgentAddr records, "
            f"resolved via adaptive resolver with requester context (Maranello, Italy). "
            f"Methods: {', '.join(s['resolution_method'] for s in resolved_suppliers)}"
        ),
    ))

    return {**state, "discovered_suppliers": resolved_suppliers}


async def send_rfqs(state: ProcurementState) -> ProcurementState:
    """Send RFQ to all discovered suppliers."""
    components = [ComponentSpec(**c) for c in state["bom"]]
    rfq = RequestForQuote(
        components=components,
        required_by="2026-06-01",
        max_budget=500000.0,
        preferred_jurisdiction="EU",
    )
    rfq_dict = rfq.model_dump(mode="json")

    quotes: list[dict] = []
    for supplier in state["discovered_suppliers"]:
        endpoint = supplier.get("endpoint", "")
        sid = supplier["agent_id"]

        if not endpoint:
            continue

        await send_agent_message(AgentMessage(
            sender_id="procurement-agent",
            receiver_id=sid,
            message_type=MessageType.REQUEST_FOR_QUOTE,
            correlation_id=state["correlation_id"],
            payload=rfq_dict,
            explanation=f"Sending RFQ for {len(components)} components to {supplier.get('label', sid)}.",
        ))

        result = await call_agent_endpoint(f"{endpoint}/rfq", rfq_dict)
        if result:
            quotes.append(result)

            await send_agent_message(AgentMessage(
                sender_id=sid,
                receiver_id="procurement-agent",
                message_type=MessageType.QUOTE_RESPONSE,
                correlation_id=state["correlation_id"],
                payload=result,
                explanation=f"Received quote from {supplier.get('label', sid)}: ${result.get('total_price', 0):,.0f}, {result.get('lead_time_days', '?')} days.",
            ))

    return {**state, "rfq_payload": rfq_dict, "quotes": quotes}


async def evaluate_quotes(state: ProcurementState) -> ProcurementState:
    """Use LLM to evaluate and rank quotes, considering NANDA trust metadata."""
    quotes = state.get("quotes", [])
    if not quotes:
        return {**state, "best_quote": None, "error": "No quotes received"}

    # Enrich quotes with trust data from discovery
    suppliers_by_id = {s["agent_id"]: s for s in state.get("discovered_suppliers", [])}
    enriched = []
    for q in quotes:
        sid = q.get("supplier_id", "")
        # Match by raw ID or nanda-prefixed ID
        trust_info = suppliers_by_id.get(sid) or suppliers_by_id.get(f"nanda:{sid}", {})
        enriched.append({
            **q,
            "certification_level": trust_info.get("certification_level", "unknown"),
            "reputation_score": trust_info.get("reputation_score", 0.5),
            "jurisdiction": trust_info.get("jurisdiction", "unknown"),
        })

    llm = get_llm()
    prompt = (
        "You are a procurement analyst. Evaluate these supplier quotes and pick the best one. "
        "Consider price, lead time, availability, AND trust metadata (certification level, reputation score). "
        "Prefer audited/verified suppliers with higher reputation.\n\n"
        f"Quotes:\n{json.dumps(enriched, indent=2)}\n\n"
        "Respond with ONLY a JSON object: "
        '{"chosen_index": <int>, "reason": "<why this quote is best>"}'
    )
    resp = await llm.ainvoke(prompt)

    try:
        decision = json.loads(resp.content)
        idx = decision.get("chosen_index", 0)
        best = quotes[idx] if idx < len(quotes) else quotes[0]
        reason = decision.get("reason", "Best price/lead time ratio with verified trust")
    except Exception:
        best = min(quotes, key=lambda q: q.get("total_price", float("inf")))
        reason = "Selected lowest price (LLM parse fallback)"

    await send_agent_message(AgentMessage(
        sender_id="procurement-agent",
        receiver_id="system",
        message_type=MessageType.STATUS_UPDATE,
        correlation_id=state["correlation_id"],
        payload={"best_quote": best, "reason": reason},
        explanation=f"Evaluated {len(quotes)} quotes with NANDA trust metadata. Selected {best.get('supplier_id', 'unknown')}: {reason}",
    ))

    return {**state, "best_quote": best}


async def negotiate(state: ProcurementState) -> ProcurementState:
    """Attempt to negotiate a better deal with the chosen supplier."""
    best = state.get("best_quote")
    if not best:
        return {**state, "negotiation_result": None}

    supplier_id = best.get("supplier_id", "")
    supplier_info = next(
        (s for s in state["discovered_suppliers"]
         if s["agent_id"] == supplier_id or s["agent_id"] == f"nanda:{supplier_id}"),
        None,
    )
    if not supplier_info:
        return {**state, "negotiation_result": best}

    proposed_price = best.get("total_price", 0) * 0.9
    proposal = {
        "proposed_price": proposed_price,
        "proposed_lead_time_days": best.get("lead_time_days"),
        "conditions": "Bulk order for full Ferrari BOM — requesting 10% volume discount",
    }

    await send_agent_message(AgentMessage(
        sender_id="procurement-agent",
        receiver_id=supplier_id,
        message_type=MessageType.NEGOTIATION_PROPOSAL,
        correlation_id=state["correlation_id"],
        payload=proposal,
        explanation=f"Proposing ${proposed_price:,.0f} (10% discount) to {supplier_info.get('label', supplier_id)}.",
    ))

    endpoint = supplier_info.get("endpoint", "")
    result = await call_agent_endpoint(f"{endpoint}/negotiate", proposal) if endpoint else None

    if result:
        await send_agent_message(AgentMessage(
            sender_id=supplier_id,
            receiver_id="procurement-agent",
            message_type=MessageType.NEGOTIATION_PROPOSAL,
            correlation_id=state["correlation_id"],
            payload=result,
            explanation=f"Negotiation response from {supplier_info.get('label', supplier_id)}: accepted={result.get('accepted')}",
        ))

    return {**state, "negotiation_result": result or best}


async def place_order(state: ProcurementState) -> ProcurementState:
    """Place a confirmed order with the selected supplier."""
    neg = state.get("negotiation_result") or state.get("best_quote") or {}
    best_q = state.get("best_quote") or {}
    supplier_id = neg.get("supplier_id", best_q.get("supplier_id", ""))

    order = {
        "order_id": f"ORD-{uuid.uuid4().hex[:8]}",
        "supplier_id": supplier_id,
        "components": state["bom"],
        "agreed_price": neg.get("proposed_price", neg.get("total_price", 0)),
        "agreed_lead_time_days": neg.get("proposed_lead_time_days", neg.get("lead_time_days", 30)),
        "delivery_address": "Maranello, Italy",
    }

    await send_agent_message(AgentMessage(
        sender_id="procurement-agent",
        receiver_id=supplier_id,
        message_type=MessageType.ORDER_PLACEMENT,
        correlation_id=state["correlation_id"],
        payload=order,
        explanation=f"Placing order {order['order_id']} with {supplier_id} for ${order['agreed_price']:,.0f}.",
    ))

    return {**state, "order": order}


async def request_manufacturing(state: ProcurementState) -> ProcurementState:
    """Send order to the manufacturer — uses NANDA adaptive resolution."""
    order = state.get("order", {})

    # Adaptive resolution for manufacturer (context-aware)
    mfg_ctx = RequesterContext(
        requester_id="nanda:procurement-agent",
        geo_location="Maranello, Italy",
        geo_lat=44.53,
        geo_lon=10.86,
        security_level="authenticated",
        session_type="request-response",
        qos_requirements={"max_latency_ms": 5000, "priority": "high"},
    )

    # Step 1: Discover manufacturer via NANDA index
    mfg_addrs = await discover_agents(role="manufacturer")
    if not mfg_addrs:
        return {**state, "manufacturing_result": {"error": "No manufacturer found"}}

    mfg_addr = mfg_addrs[0]

    # Step 2: Try adaptive resolution, fallback to AgentFacts
    mfg_adaptive = await resolve_adaptive(mfg_addr.agent_name, mfg_ctx)
    mfg_facts = await fetch_agent_facts(mfg_addr.primary_facts_url)

    if mfg_adaptive.get("type") == "tailored_response":
        mfg_endpoint = mfg_adaptive.get("endpoint", "")
        resolution_method = "adaptive_resolver"
    elif mfg_facts and mfg_facts.endpoints.static:
        mfg_endpoint = mfg_facts.endpoints.static[0]
        resolution_method = "two_step_facts"
    else:
        mfg_endpoint = None
        resolution_method = "unresolved"

    if not mfg_endpoint:
        return {**state, "manufacturing_result": {"error": "No manufacturer endpoint"}}

    await send_agent_message(AgentMessage(
        sender_id="procurement-agent",
        receiver_id=mfg_addr.agent_id,
        message_type=MessageType.ORDER_PLACEMENT,
        correlation_id=state["correlation_id"],
        payload={
            **order,
            "resolution_method": resolution_method,
            "adaptive_context": mfg_adaptive.get("context_used", {}),
        },
        explanation=(
            f"Forwarding order {order.get('order_id')} to "
            f"{mfg_facts.label if mfg_facts else mfg_addr.agent_id} "
            f"(resolved via {resolution_method})."
        ),
    ))

    result = await call_agent_endpoint(f"{mfg_endpoint}/manufacture", order)

    if result:
        await send_agent_message(AgentMessage(
            sender_id=mfg_addr.agent_id,
            receiver_id="procurement-agent",
            message_type=MessageType.ORDER_CONFIRMATION,
            correlation_id=state["correlation_id"],
            payload=result,
            explanation=f"Manufacturing response: {result.get('notes', 'confirmed')}",
        ))

    report = await notify_cascade_complete(state["correlation_id"])
    return {**state, "manufacturing_result": result, "report": report}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_procurement_graph() -> StateGraph:
    g = StateGraph(ProcurementState)

    g.add_node("parse_intent", parse_intent)
    g.add_node("discover_suppliers", discover_suppliers_node)
    g.add_node("send_rfqs", send_rfqs)
    g.add_node("evaluate_quotes", evaluate_quotes)
    g.add_node("negotiate", negotiate)
    g.add_node("place_order", place_order)
    g.add_node("request_manufacturing", request_manufacturing)

    g.set_entry_point("parse_intent")
    g.add_edge("parse_intent", "discover_suppliers")
    g.add_edge("discover_suppliers", "send_rfqs")
    g.add_edge("send_rfqs", "evaluate_quotes")
    g.add_edge("evaluate_quotes", "negotiate")
    g.add_edge("negotiate", "place_order")
    g.add_edge("place_order", "request_manufacturing")
    g.add_edge("request_manufacturing", END)

    return g.compile()
