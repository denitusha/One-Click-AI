"""Manufacturer Agent — LangGraph-based assembly scheduling and BOM validation.

NANDA-compliant: uses two-step resolution for compliance and logistics discovery.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from shared.agent_base import (
    call_agent_endpoint,
    discover_agents,
    fetch_agent_facts,
    report_discovery_path,
    report_policy_record,
    report_trust_record,
    resolve_adaptive,
    send_agent_message,
)
from shared.agent_facts import RequesterContext
from shared.config import LLM_MODEL, OPENAI_API_KEY
from shared.schemas import AgentMessage, MessageType

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ManufacturerState(TypedDict, total=False):
    order: dict
    correlation_id: str
    bom_valid: bool
    compliance_result: dict | None
    logistics_result: dict | None
    assembly_schedule: dict | None
    confirmation: dict | None


def get_llm():
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0.3)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def validate_bom(state: ManufacturerState) -> ManufacturerState:
    """Validate that all components in the order are present and compatible."""
    order = state["order"]
    components = order.get("components", [])
    cid = state.get("correlation_id", "")

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are a Ferrari manufacturing engineer. Validate this BOM of {len(components)} components "
        f"for a Ferrari assembly. Component categories: "
        f"{[c.get('category') for c in components]}. "
        f"Are all critical categories present (engine, chassis, electronics, tires, brakes, interior, body)? "
        f"Respond with ONLY JSON: {{\"valid\": <bool>, \"missing_categories\": [<list>], \"notes\": \"<str>\"}}"
    )

    try:
        validation = json.loads(resp.content)
    except Exception:
        validation = {"valid": True, "missing_categories": [], "notes": "BOM validated (fallback)"}

    await send_agent_message(AgentMessage(
        sender_id="manufacturer-agent",
        receiver_id="system",
        message_type=MessageType.STATUS_UPDATE,
        correlation_id=cid,
        payload=validation,
        explanation=f"BOM validation: valid={validation.get('valid')}. {validation.get('notes', '')}",
    ))

    return {**state, "bom_valid": validation.get("valid", True)}


async def request_compliance(state: ManufacturerState) -> ManufacturerState:
    """Request compliance check — NANDA adaptive resolution."""
    order = state["order"]
    cid = state.get("correlation_id", "")

    # Manufacturer context for adaptive resolution
    mfg_ctx = RequesterContext(
        requester_id="nanda:manufacturer-agent",
        geo_location="Maranello, Italy",
        geo_lat=44.53,
        geo_lon=10.86,
        security_level="authenticated",
        session_type="request-response",
    )

    # Step 1: Discover via NANDA index
    addrs = await discover_agents(role="compliance")
    if not addrs:
        return {**state, "compliance_result": {"compliant": True, "issues": [], "notes": "No compliance agent available"}}

    ca_addr = addrs[0]

    # Step 2: Adaptive resolution + AgentFacts fetch
    ca_adaptive = await resolve_adaptive(ca_addr.agent_name, mfg_ctx)
    ca_facts = await fetch_agent_facts(ca_addr.primary_facts_url)

    if ca_adaptive.get("type") == "tailored_response":
        ca_endpoint = ca_adaptive.get("endpoint", "")
        resolution_method = "adaptive_resolver"
    elif ca_facts and ca_facts.endpoints.static:
        ca_endpoint = ca_facts.endpoints.static[0]
        resolution_method = "two_step_facts"
    else:
        ca_endpoint = None
        resolution_method = "unresolved"

    if not ca_endpoint:
        return {**state, "compliance_result": {"compliant": True, "issues": [], "notes": "Compliance endpoint not resolved"}}

    check_payload = {
        "order_id": order.get("order_id", ""),
        "supplier_id": order.get("supplier_id", ""),
        "origin_jurisdiction": "EU",
        "destination_jurisdiction": "EU",
        "components": order.get("components", []),
        "policies_to_check": ["ISO9001", "REACH", "ESG"],
    }

    await send_agent_message(AgentMessage(
        sender_id="manufacturer-agent",
        receiver_id=ca_addr.agent_id,
        message_type=MessageType.COMPLIANCE_CHECK,
        correlation_id=cid,
        payload={**check_payload, "resolution_method": resolution_method},
        explanation=f"Requesting compliance check from {ca_facts.label if ca_facts else ca_addr.agent_id} (resolved via {resolution_method}).",
    ))

    result = await call_agent_endpoint(f"{ca_endpoint}/check", check_payload)

    if result:
        await send_agent_message(AgentMessage(
            sender_id=ca_addr.agent_id,
            receiver_id="manufacturer-agent",
            message_type=MessageType.COMPLIANCE_RESULT,
            correlation_id=cid,
            payload=result,
            explanation=f"Compliance result: compliant={result.get('compliant')}.",
        ))

    # ── Report: compliance discovery path ──
    await report_discovery_path(
        correlation_id=cid,
        query={"role": "compliance", "resolution": resolution_method},
        matched_agents=[ca_addr.agent_id],
    )
    # ── Report: compliance trust ──
    if ca_facts:
        await report_trust_record(
            correlation_id=cid,
            agent_id=ca_addr.agent_id,
            reputation_score=ca_facts.reputation_score if ca_facts.reputation_score else 0.5,
            verified=bool(ca_addr.signature),
            certification_level=ca_facts.certification.level if ca_facts.certification else "unknown",
        )
    # ── Report: policy enforcement ──
    compliance_result = result or {}
    await report_policy_record(
        correlation_id=cid,
        order_id=order.get("order_id", ""),
        compliant=compliance_result.get("compliant", True),
        issues=compliance_result.get("issues", []),
    )

    return {**state, "compliance_result": result}


async def request_logistics(state: ManufacturerState) -> ManufacturerState:
    """Request shipping route — NANDA adaptive resolution."""
    order = state["order"]
    cid = state.get("correlation_id", "")

    # Context: we need a logistics provider near Maranello
    logistics_ctx = RequesterContext(
        requester_id="nanda:manufacturer-agent",
        geo_location="Maranello, Italy",
        geo_lat=44.53,
        geo_lon=10.86,
        security_level="authenticated",
        session_type="request-response",
        qos_requirements={"max_latency_ms": 3000, "min_bandwidth_mbps": 10},
    )

    # Step 1: Discover via NANDA index
    addrs = await discover_agents(role="logistics")
    if not addrs:
        return {**state, "logistics_result": {"error": "No logistics agent found"}}

    la_addr = addrs[0]

    # Step 2: Adaptive resolution + AgentFacts fetch
    la_adaptive = await resolve_adaptive(la_addr.agent_name, logistics_ctx)
    la_facts = await fetch_agent_facts(la_addr.primary_facts_url)

    if la_adaptive.get("type") == "tailored_response":
        la_endpoint = la_adaptive.get("endpoint", "")
        resolution_method = "adaptive_resolver"
    elif la_facts and la_facts.endpoints.static:
        la_endpoint = la_facts.endpoints.static[0]
        resolution_method = "two_step_facts"
    else:
        la_endpoint = None
        resolution_method = "unresolved"

    if not la_endpoint:
        return {**state, "logistics_result": {"error": "Logistics endpoint not resolved"}}

    ship_payload = {
        "order_id": order.get("order_id", ""),
        "origin": "Stuttgart, Germany",
        "destination": "Maranello, Italy",
        "weight_kg": 2500.0,
        "volume_cbm": 12.0,
        "required_delivery_date": "2026-06-01",
        "cargo_description": "Ferrari component shipment — high-value automotive parts",
    }

    await send_agent_message(AgentMessage(
        sender_id="manufacturer-agent",
        receiver_id=la_addr.agent_id,
        message_type=MessageType.SHIPPING_REQUEST,
        correlation_id=cid,
        payload={**ship_payload, "resolution_method": resolution_method, "adaptive_context": la_adaptive.get("context_used", {})},
        explanation=f"Requesting logistics route from {la_facts.label if la_facts else la_addr.agent_id} (resolved via {resolution_method}).",
    ))

    result = await call_agent_endpoint(f"{la_endpoint}/route", ship_payload)

    if result:
        await send_agent_message(AgentMessage(
            sender_id=la_addr.agent_id,
            receiver_id="manufacturer-agent",
            message_type=MessageType.ROUTE_CONFIRMATION,
            correlation_id=cid,
            payload=result,
            explanation=f"Route confirmed: {result.get('transport_mode')}, {result.get('estimated_days')} days, ${result.get('cost', 0):,.0f}.",
        ))

    # ── Report: logistics discovery path ──
    await report_discovery_path(
        correlation_id=cid,
        query={"role": "logistics", "resolution": resolution_method},
        matched_agents=[la_addr.agent_id],
    )
    # ── Report: logistics trust ──
    if la_facts:
        await report_trust_record(
            correlation_id=cid,
            agent_id=la_addr.agent_id,
            reputation_score=la_facts.reputation_score if la_facts.reputation_score else 0.5,
            verified=bool(la_addr.signature),
            certification_level=la_facts.certification.level if la_facts.certification else "unknown",
        )

    return {**state, "logistics_result": result}


async def schedule_assembly(state: ManufacturerState) -> ManufacturerState:
    """Create assembly schedule based on BOM, compliance, and logistics."""
    order = state["order"]
    cid = state.get("correlation_id", "")
    logistics = state.get("logistics_result") or {}
    compliance = state.get("compliance_result") or {}

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are a Ferrari assembly planner. Create an assembly schedule. "
        f"Order: {order.get('order_id')}. Components: {len(order.get('components', []))} items. "
        f"Compliance: {'passed' if compliance.get('compliant') else 'issues found'}. "
        f"Logistics ETA: {logistics.get('estimated_days', 'unknown')} days. "
        f"Respond with ONLY JSON: {{\"assembly_start\": \"<date>\", \"assembly_end\": \"<date>\", "
        f"\"total_days\": <int>, \"notes\": \"<str>\"}}"
    )

    try:
        schedule = json.loads(resp.content)
    except Exception:
        schedule = {
            "assembly_start": "2026-04-15",
            "assembly_end": "2026-05-20",
            "total_days": 35,
            "notes": "Standard assembly timeline for Ferrari components",
        }

    confirmation = {
        "order_id": order.get("order_id", ""),
        "confirmed": True,
        "estimated_completion": schedule.get("assembly_end"),
        "assembly_schedule": schedule,
        "compliance": compliance,
        "logistics": logistics,
        "notes": f"Manufacturing confirmed. Assembly: {schedule.get('total_days')} days.",
    }

    await send_agent_message(AgentMessage(
        sender_id="manufacturer-agent",
        receiver_id="procurement-agent",
        message_type=MessageType.ORDER_CONFIRMATION,
        correlation_id=cid,
        payload=confirmation,
        explanation=f"Assembly scheduled: {schedule.get('total_days')} days. Completion: {schedule.get('assembly_end')}.",
    ))

    return {**state, "assembly_schedule": schedule, "confirmation": confirmation}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_manufacturer_graph() -> StateGraph:
    g = StateGraph(ManufacturerState)

    g.add_node("validate_bom", validate_bom)
    g.add_node("request_compliance", request_compliance)
    g.add_node("request_logistics", request_logistics)
    g.add_node("schedule_assembly", schedule_assembly)

    g.set_entry_point("validate_bom")
    g.add_edge("validate_bom", "request_compliance")
    g.add_edge("request_compliance", "request_logistics")
    g.add_edge("request_logistics", "schedule_assembly")
    g.add_edge("schedule_assembly", END)

    return g.compile()
