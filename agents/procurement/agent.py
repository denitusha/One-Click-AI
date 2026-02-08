"""Procurement Agent — LangGraph state machine.

Orchestrates the full supply-chain coordination cascade:

    DECOMPOSE → DISCOVER → VERIFY → NEGOTIATE → PLAN

Each node is an async function that reads/writes to the shared
``ProcurementState``.  The agent emits real-time events to the
Event Bus so the dashboard can visualise progress.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any

import httpx
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import (  # noqa: E402
    EVENT_BUS_HTTP_URL,
    INDEX_URL,
    OPENAI_MODEL,
    PROCUREMENT_PORT,
)
from shared.message_types import (  # noqa: E402
    AcceptPayload,
    CounterOfferPayload,
    LogisticsRequestPayload,
    MessageType,
    OrderPayload,
    RFQPayload,
    make_envelope,
)
from shared.schemas import AgentFacts  # noqa: E402

try:
    from .bom import BOM, BOMPart, decompose_bom  # noqa: E402
    from .negotiation import (  # noqa: E402
        NegotiationResult,
        SupplierQuote,
        build_execution_summary,
        generate_counter_offer,
        rank_quotes,
        select_winner,
    )
except ImportError:
    from agents.procurement.bom import BOM, BOMPart, decompose_bom  # noqa: E402
    from agents.procurement.negotiation import (  # noqa: E402
        NegotiationResult,
        SupplierQuote,
        build_execution_summary,
        generate_counter_offer,
        rank_quotes,
        select_winner,
    )

logger = logging.getLogger("procurement.agent")

AGENT_ID = "procurement-agent"
AGENT_NAME = "Procurement Orchestrator"


# ═══════════════════════════════════════════════════════════════════════════
# State definition
# ═══════════════════════════════════════════════════════════════════════════

class ProcurementState(TypedDict, total=False):
    """Shared state that flows through all LangGraph nodes."""

    # Input
    intent: str
    run_id: str  # dashboard-generated UUID for tab isolation

    # Phase: DECOMPOSE
    bom: dict[str, Any]  # serialised BOM

    # Phase: DISCOVER
    # Maps part skill_query → list of AgentAddr dicts from the Index
    discovered_suppliers: dict[str, list[dict[str, Any]]]

    # Phase: VERIFY
    # Maps supplier_id → AgentFacts dict (only verified suppliers)
    verified_suppliers: dict[str, dict[str, Any]]
    # Maps supplier_id → rejection reason
    rejected_suppliers: dict[str, str]

    # Phase: NEGOTIATE
    negotiation_results: list[dict[str, Any]]  # serialised NegotiationResult list
    orders: list[dict[str, Any]]  # placed orders

    # Phase: DISCOVER (missing parts — no suppliers found)
    missing_parts: list[dict[str, Any]]

    # Phase: PLAN
    logistics_plans: list[dict[str, Any]]  # ShipPlan payloads

    # Final output
    report: dict[str, Any]

    # Bookkeeping
    events: Annotated[list[dict[str, Any]], add]  # append-only event log
    errors: Annotated[list[str], add]
    phase: str  # current phase label


# ═══════════════════════════════════════════════════════════════════════════
# Helper: emit events to Event Bus
# ═══════════════════════════════════════════════════════════════════════════

async def _emit_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    agent_id: str = AGENT_ID,
    run_id: str = "",
) -> dict[str, Any]:
    """POST an event to the Event Bus (best-effort, non-blocking)."""
    payload = data or {}
    if run_id:
        payload["run_id"] = run_id
    event = {
        "event_type": event_type,
        "agent_id": agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{EVENT_BUS_HTTP_URL}/event", json=event)
    except Exception as exc:
        logger.debug("Event bus unreachable (%s), event buffered locally.", exc)
    return event


# ═══════════════════════════════════════════════════════════════════════════
# Node 1: DECOMPOSE — BOM decomposition
# ═══════════════════════════════════════════════════════════════════════════

async def decompose_node(state: ProcurementState) -> dict[str, Any]:
    """Decompose the user intent into a Bill of Materials."""
    intent = state["intent"]
    rid = state.get("run_id", "")
    logger.info("▶ DECOMPOSE  intent=%s", intent)

    ev = await _emit_event("INTENT_RECEIVED", {"intent": intent}, run_id=rid)

    bom: BOM = await decompose_bom(intent, model=OPENAI_MODEL)
    bom_dict = bom.model_dump(mode="json")

    ev2 = await _emit_event(
        "BOM_GENERATED",
        {
            "total_parts": bom.total_parts,
            "systems": bom.systems,
            "parts": [p.part_id for p in bom.parts],
        },
        run_id=rid,
    )

    return {
        "bom": bom_dict,
        "phase": "DECOMPOSE",
        "events": [ev, ev2],
        "errors": [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node 2: DISCOVER — query NANDA Index for suppliers per part
# ═══════════════════════════════════════════════════════════════════════════

async def discover_node(state: ProcurementState) -> dict[str, Any]:
    """Query the NANDA Index for suppliers matching each BOM part skill."""
    logger.info("▶ DISCOVER")
    rid = state.get("run_id", "")
    bom_dict = state["bom"]
    parts: list[dict[str, Any]] = bom_dict.get("parts", [])

    discovered: dict[str, list[dict[str, Any]]] = {}
    missing_parts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    errors: list[str] = []

    min_score = 0.65

    async with httpx.AsyncClient(timeout=10.0) as client:
        for part in parts:
            skill = part.get("skill_query", "")
            part_id = part.get("part_id", "")
            part_name = part.get("part_name", "")
            description = part.get("description", "")
            specs = part.get("specs", {})
            compliance = part.get("compliance_requirements", [])
            quantity = part.get("quantity", 1)
            system = part.get("system", "")
            
            # Build a rich natural-language query from the BOM part
            query = f"{part_name}"
            if description:
                query += f" - {description}"
            if specs:
                spec_str = ", ".join(f"{k}: {v}" for k, v in specs.items())
                query += f" ({spec_str})"
            
            # Build the resolve request with min_score filtering
            resolve_body = {
                "query": query,
                "skill_hint": skill,
                "context": {
                    "region": "EU",
                    "compliance_requirements": compliance,
                    "urgency": "standard",
                },
                "min_score": min_score,
            }

            ev = await _emit_event(
                "DISCOVERY_QUERY",
                {
                    "part": part_id,
                    "skill": skill,
                    "query": query,
                    "method": "adaptive_resolver",
                },
                run_id=rid,
            )
            events.append(ev)

            try:
                resp = await client.post(
                    f"{INDEX_URL}/resolve",
                    json=resolve_body,
                )
                resp.raise_for_status()
                resolved_agents = resp.json()
                
                # Convert ResolvedAgent list to AgentAddr-like dicts for compatibility
                results = [
                    {
                        "agent_id": r.get("agent_id"),
                        "agent_name": r.get("agent_name"),
                        "facts_url": r.get("facts_url"),
                        "skills": r.get("skills", []),
                        "region": r.get("region"),
                        "relevance_score": r.get("relevance_score", 0.0),
                        "context_score": r.get("context_score", 0.0),
                        "combined_score": r.get("combined_score", 0.0),
                        "matched_skill": r.get("matched_skill", ""),
                        "match_reason": r.get("match_reason", ""),
                    }
                    for r in resolved_agents
                ]

                # Double-filter: only keep suppliers with combined_score >= min_score
                results = [
                    r for r in results
                    if r.get("combined_score", 0.0) >= min_score
                ]

                discovered[skill] = results

                if results:
                    ev2 = await _emit_event(
                        "DISCOVERY_RESULT",
                        {
                            "part": part_id,
                            "skill": skill,
                            "suppliers_found": len(results),
                            "supplier_ids": [r.get("agent_id") for r in results],
                            "agents": [
                                {
                                    "agent_id": r.get("agent_id"),
                                    "agent_name": r.get("agent_name", r.get("agent_id", "")),
                                    "relevance_score": r.get("relevance_score", 0.0),
                                    "combined_score": r.get("combined_score", 0.0),
                                    "match_reason": r.get("match_reason", ""),
                                }
                                for r in results
                            ],
                            "top_score": results[0].get("combined_score", 0.0) if results else 0.0,
                        },
                        run_id=rid,
                    )
                    events.append(ev2)
                    logger.info(
                        "  Resolved %d suppliers for %s (top_score=%.2f, method=%s)",
                        len(results),
                        part_id,
                        results[0].get("combined_score", 0.0) if results else 0.0,
                        results[0].get("match_reason", "none") if results else "none",
                    )
                else:
                    # No suppliers passed the score threshold — mark as missing
                    missing_entry = {
                        "part_id": part_id,
                        "part_name": part_name,
                        "skill_query": skill,
                        "quantity": quantity,
                        "system": system,
                        "reason": "No suppliers found above score threshold",
                    }
                    missing_parts.append(missing_entry)

                    ev_miss = await _emit_event(
                        "PART_MISSING",
                        {
                            "part_id": part_id,
                            "part_name": part_name,
                            "skill_query": skill,
                            "quantity": quantity,
                            "system": system,
                            "reason": "No suppliers found above score threshold",
                        },
                        run_id=rid,
                    )
                    events.append(ev_miss)
                    logger.warning(
                        "  MISSING: %s (%s) — no suppliers above min_score=%.2f",
                        part_id,
                        skill,
                        min_score,
                    )
            except Exception as exc:
                err = f"Discovery failed for {skill}: {exc}"
                logger.warning("  %s", err)
                errors.append(err)
                discovered[skill] = []

    return {
        "discovered_suppliers": discovered,
        "missing_parts": missing_parts,
        "phase": "DISCOVER",
        "events": events,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node 3: VERIFY — ZTAA verification of AgentFacts
# ═══════════════════════════════════════════════════════════════════════════

# Verification thresholds
MIN_RELIABILITY = 0.7
ACCEPTABLE_ESG = {"A+", "A", "A-", "B+", "B", "B-"}
REQUIRED_JURISDICTION = {"EU", "US", "UK", "CH"}


async def verify_node(state: ProcurementState) -> dict[str, Any]:
    """Fetch AgentFacts from each discovered supplier and run ZTAA verification."""
    logger.info("▶ VERIFY (ZTAA)")
    rid = state.get("run_id", "")
    discovered = state.get("discovered_suppliers", {})
    seen_ids: set[str] = set()
    verified: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    events: list[dict[str, Any]] = []
    errors: list[str] = []

    # Collect unique suppliers across all skills
    all_suppliers: list[dict[str, Any]] = []
    for suppliers in discovered.values():
        for s in suppliers:
            sid = s.get("agent_id", "")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                all_suppliers.append(s)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for supplier in all_suppliers:
            sid = supplier.get("agent_id", "")
            facts_url = supplier.get("facts_url", "")

            if not facts_url:
                rejected[sid] = "No facts_url provided"
                continue

            # Fetch AgentFacts
            try:
                resp = await client.get(facts_url)
                resp.raise_for_status()
                facts_dict = resp.json()

                ev = await _emit_event(
                    "AGENTFACTS_FETCHED",
                    {
                        "agent_id": sid,
                        "supplier_id": sid,
                        "agent_name": facts_dict.get("agent_name", sid),
                    },
                    run_id=rid,
                )
                events.append(ev)
            except Exception as exc:
                reason = f"Cannot fetch AgentFacts from {facts_url}: {exc}"
                rejected[sid] = reason
                errors.append(reason)
                logger.warning("  %s", reason)
                continue

            # --- ZTAA Checks ---
            rejection_reasons: list[str] = []

            # 1. Reliability score
            rel = facts_dict.get("reliability_score", 0.0)
            if rel < MIN_RELIABILITY:
                rejection_reasons.append(
                    f"reliability_score {rel} < {MIN_RELIABILITY}"
                )

            # 2. ESG rating
            esg = facts_dict.get("esg_rating", "F")
            if esg not in ACCEPTABLE_ESG:
                rejection_reasons.append(f"ESG rating '{esg}' not acceptable")

            # 3. Jurisdiction
            jur = facts_dict.get("jurisdiction", "")
            if jur and jur not in REQUIRED_JURISDICTION:
                rejection_reasons.append(
                    f"jurisdiction '{jur}' not in {REQUIRED_JURISDICTION}"
                )

            # 4. Certifications (basic check — must have at least one)
            certs = facts_dict.get("certifications", [])
            if not certs:
                # Soft warning, not a hard reject
                logger.info("  Supplier %s has no certifications (soft warning)", sid)

            if rejection_reasons:
                rejected[sid] = "; ".join(rejection_reasons)
                ev = await _emit_event(
                    "VERIFICATION_RESULT",
                    {
                        "agent_id": sid,
                        "agent_name": facts_dict.get("agent_name", sid),
                        "supplier_id": sid,
                        "passed": False,
                        "reasons": rejection_reasons,
                    },
                    run_id=rid,
                )
                events.append(ev)
                logger.info("  ✗ %s REJECTED: %s", sid, rejection_reasons)
            else:
                verified[sid] = facts_dict
                ev = await _emit_event(
                    "VERIFICATION_RESULT",
                    {
                        "agent_id": sid,
                        "agent_name": facts_dict.get("agent_name", sid),
                        "supplier_id": sid,
                        "passed": True,
                        "framework": facts_dict.get("framework", "unknown"),
                        "reliability": rel,
                        "esg": esg,
                    },
                    run_id=rid,
                )
                events.append(ev)
                logger.info("  ✓ %s VERIFIED (rel=%.2f, esg=%s)", sid, rel, esg)

    logger.info(
        "  Verification complete: %d verified, %d rejected",
        len(verified),
        len(rejected),
    )
    return {
        "verified_suppliers": verified,
        "rejected_suppliers": rejected,
        "phase": "VERIFY",
        "events": events,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node 4: NEGOTIATE — RFQ → QUOTE → COUNTER → ACCEPT/REJECT → ORDER
# ═══════════════════════════════════════════════════════════════════════════

async def negotiate_node(state: ProcurementState) -> dict[str, Any]:
    """Run the full negotiation cascade for every BOM part."""
    logger.info("▶ NEGOTIATE")
    rid = state.get("run_id", "")
    bom_dict = state["bom"]
    parts: list[dict[str, Any]] = bom_dict.get("parts", [])
    discovered = state.get("discovered_suppliers", {})
    verified = state.get("verified_suppliers", {})
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    results: list[NegotiationResult] = []
    all_orders: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for part_dict in parts:
            part_id = part_dict.get("part_id", "")
            skill = part_dict.get("skill_query", "")
            quantity = part_dict.get("quantity", 1)
            compliance = part_dict.get("compliance_requirements", [])

            result = NegotiationResult(
                part=part_id,
                rfq_id=str(uuid.uuid4()),
            )

            # Find verified suppliers for this part
            supplier_addrs = discovered.get(skill, [])
            verified_for_part = [
                s for s in supplier_addrs if s.get("agent_id") in verified
            ]

            if not verified_for_part:
                logger.warning("  No verified suppliers for %s — skipping", part_id)
                errors.append(f"No verified suppliers for part {part_id}")
                results.append(result)
                continue

            # --- Send RFQs ---
            rfq_payload = RFQPayload(
                rfq_id=result.rfq_id,
                part=part_id,
                quantity=quantity,
                required_by="2026-04-01",
                delivery_location="Stuttgart, Germany",
                compliance_requirements=compliance,
                specs=part_dict.get("specs", {}),
            )

            for supplier in verified_for_part:
                sid = supplier.get("agent_id", "")
                facts = verified.get(sid, {})
                base_url = facts.get("base_url", "")

                if not base_url:
                    # Try to derive from facts_url
                    facts_url = supplier.get("facts_url", "")
                    base_url = facts_url.rsplit("/", 1)[0] if facts_url else ""

                if not base_url:
                    continue

                # Send RFQ
                envelope = make_envelope(
                    MessageType.RFQ,
                    from_agent=AGENT_ID,
                    to_agent=sid,
                    payload=rfq_payload,
                    correlation_id=result.rfq_id,
                )

                ev = await _emit_event(
                    "RFQ_SENT",
                    {
                        "rfq_id": result.rfq_id,
                        "part": part_id,
                        "to_agent": sid,
                        "supplier": sid,
                        "supplier_name": facts.get("agent_name", sid),
                        "quantity": quantity,
                    },
                    run_id=rid,
                )
                events.append(ev)

                try:
                    resp = await client.post(
                        f"{base_url}/rfq",
                        json=envelope.model_dump(mode="json"),
                    )
                    resp.raise_for_status()
                    quote_data = resp.json()

                    # Check if the supplier rejected the RFQ
                    q_type = quote_data.get("type", "")
                    if q_type in ("REJECT", "reject", MessageType.REJECT):
                        reason = quote_data.get("payload", {}).get(
                            "rejection_reason", "rejected"
                        )
                        logger.info(
                            "  RFQ rejected by %s for %s: %s",
                            sid, part_id, reason,
                        )
                        await _emit_event(
                            "REJECT_SENT",
                            {
                                "part": part_id,
                                "to_agent": sid,
                                "reason": reason,
                            },
                            run_id=rid,
                        )
                        continue  # skip to next supplier

                    # Extract the quote payload
                    q_payload = quote_data.get("payload", quote_data)

                    quote = SupplierQuote(
                        supplier_id=sid,
                        supplier_name=facts.get("agent_name", sid),
                        framework=facts.get("framework", "unknown"),
                        rfq_id=result.rfq_id,
                        part=part_id,
                        unit_price=q_payload.get("unit_price", 0),
                        currency=q_payload.get("currency", "EUR"),
                        qty_available=q_payload.get("qty_available", 0),
                        lead_time_days=q_payload.get("lead_time_days", 0),
                        shipping_origin=q_payload.get("shipping_origin", ""),
                        certifications=q_payload.get("certifications", []),
                        reliability_score=facts.get("reliability_score", 0.9),
                        esg_rating=facts.get("esg_rating", "A"),
                        region=supplier.get("region", "EU") or "EU",
                    )
                    result.quotes.append(quote)

                    ev2 = await _emit_event(
                        "QUOTE_RECEIVED",
                        {
                            "rfq_id": result.rfq_id,
                            "part": part_id,
                            "from_agent": sid,
                            "supplier": sid,
                            "supplier_name": facts.get("agent_name", sid),
                            "unit_price": quote.unit_price,
                            "lead_time_days": quote.lead_time_days,
                            "framework": quote.framework,
                        },
                        run_id=rid,
                    )
                    events.append(ev2)
                    logger.info(
                        "  Quote from %s for %s: €%.2f, %dd lead",
                        sid,
                        part_id,
                        quote.unit_price,
                        quote.lead_time_days,
                    )
                except Exception as exc:
                    err = f"RFQ to {sid} for {part_id} failed: {exc}"
                    logger.warning("  %s", err)
                    errors.append(err)

            # --- Filter out invalid quotes (e.g. zero-price) ---
            result.quotes = [q for q in result.quotes if q.unit_price > 0]

            # --- Rank and Counter-Offer ---
            if result.quotes:
                ranked = rank_quotes(result.quotes)

                # Send counter-offer to the top supplier (10% discount)
                top = ranked[0]

                # Safety net: skip counter-offer if price is invalid
                if top.unit_price <= 0:
                    logger.warning(
                        "  Skipping counter-offer for %s: invalid price €%.2f",
                        part_id, top.unit_price,
                    )
                    result.winner = top
                    negotiations.append(result)
                    continue

                counter_data = generate_counter_offer(top)
                counter_payload = CounterOfferPayload(**counter_data)
                counter_env = make_envelope(
                    MessageType.COUNTER_OFFER,
                    from_agent=AGENT_ID,
                    to_agent=top.supplier_id,
                    payload=counter_payload,
                    correlation_id=result.rfq_id,
                )

                top_facts = verified.get(top.supplier_id, {})
                top_base_url = top_facts.get("base_url", "")
                if not top_base_url:
                    facts_url_t = next(
                        (
                            s.get("facts_url", "")
                            for s in verified_for_part
                            if s.get("agent_id") == top.supplier_id
                        ),
                        "",
                    )
                    top_base_url = facts_url_t.rsplit("/", 1)[0] if facts_url_t else ""

                if top_base_url:
                    ev3 = await _emit_event(
                        "COUNTER_SENT",
                        {
                            "rfq_id": result.rfq_id,
                            "part": part_id,
                            "to_agent": top.supplier_id,
                            "supplier": top.supplier_id,
                            "supplier_name": top.supplier_name,
                            "target_price": counter_data["target_price"],
                        },
                        run_id=rid,
                    )
                    events.append(ev3)

                    try:
                        resp = await client.post(
                            f"{top_base_url}/counter",
                            json=counter_env.model_dump(mode="json"),
                        )
                        resp.raise_for_status()
                        revised_data = resp.json()
                        r_payload = revised_data.get("payload", revised_data)

                        # Check if it's a revised quote or a rejection
                        r_type = revised_data.get("type", "")
                        if r_type == MessageType.REJECT or r_type == "REJECT":
                            logger.info(
                                "  Counter rejected by %s for %s",
                                top.supplier_id,
                                part_id,
                            )
                        else:
                            revised_price = r_payload.get(
                                "revised_price", top.unit_price
                            )
                            revised_quote = SupplierQuote(
                                supplier_id=top.supplier_id,
                                supplier_name=top.supplier_name,
                                framework=top.framework,
                                rfq_id=result.rfq_id,
                                part=part_id,
                                unit_price=revised_price,
                                currency=top.currency,
                                qty_available=top.qty_available,
                                lead_time_days=r_payload.get(
                                    "revised_lead_time", top.lead_time_days
                                )
                                or top.lead_time_days,
                                shipping_origin=top.shipping_origin,
                                certifications=top.certifications,
                                reliability_score=top.reliability_score,
                                esg_rating=top.esg_rating,
                                region=top.region,
                            )
                            result.revised_quote = revised_quote
                            result.counter_offer_sent = True
                            result.counter_offer_to = top.supplier_id

                            ev4 = await _emit_event(
                                "REVISED_RECEIVED",
                                {
                                    "rfq_id": result.rfq_id,
                                    "part": part_id,
                                    "from_agent": top.supplier_id,
                                    "supplier": top.supplier_id,
                                    "supplier_name": top.supplier_name,
                                    "revised_price": revised_price,
                                },
                                run_id=rid,
                            )
                            events.append(ev4)
                            logger.info(
                                "  Revised quote from %s: €%.2f",
                                top.supplier_id,
                                revised_price,
                            )
                    except Exception as exc:
                        logger.warning(
                            "  Counter-offer to %s failed: %s", top.supplier_id, exc
                        )

                # --- Select Winner ---
                winner = select_winner(result)
                if winner:
                    result.winner = winner
                    result.accepted = True
                    order_id = str(uuid.uuid4())
                    result.order_id = order_id

                    # Send ACCEPT
                    accept_payload = AcceptPayload(
                        rfq_id=result.rfq_id,
                        order_id=order_id,
                        accepted_price=winner.unit_price,
                        quantity=quantity,
                    )
                    ev5 = await _emit_event(
                        "ACCEPT_SENT",
                        {
                            "rfq_id": result.rfq_id,
                            "part": part_id,
                            "to_agent": winner.supplier_id,
                            "supplier": winner.supplier_id,
                            "supplier_name": winner.supplier_name,
                            "price": winner.unit_price,
                            "order_id": order_id,
                        },
                        run_id=rid,
                    )
                    events.append(ev5)

                    # Build ORDER
                    order = OrderPayload(
                        order_id=order_id,
                        rfq_id=result.rfq_id,
                        supplier_id=winner.supplier_id,
                        part=part_id,
                        quantity=quantity,
                        unit_price=winner.unit_price,
                        currency=winner.currency,
                        total_price=round(winner.unit_price * quantity, 2),
                        delivery_location="Stuttgart, Germany",
                        required_by="2026-04-01",
                        shipping_origin=winner.shipping_origin,
                        certifications=winner.certifications,
                    )
                    all_orders.append(order.model_dump(mode="json"))

                    # Send ORDER to supplier
                    winner_facts = verified.get(winner.supplier_id, {})
                    winner_base_url = winner_facts.get("base_url", "")
                    if not winner_base_url:
                        wf = next(
                            (
                                s.get("facts_url", "")
                                for s in verified_for_part
                                if s.get("agent_id") == winner.supplier_id
                            ),
                            "",
                        )
                        winner_base_url = wf.rsplit("/", 1)[0] if wf else ""

                    if winner_base_url:
                        order_env = make_envelope(
                            MessageType.ORDER,
                            from_agent=AGENT_ID,
                            to_agent=winner.supplier_id,
                            payload=order,
                            correlation_id=result.rfq_id,
                        )
                        try:
                            await client.post(
                                f"{winner_base_url}/order",
                                json=order_env.model_dump(mode="json"),
                            )
                            ev6 = await _emit_event(
                                "ORDER_PLACED",
                                {
                                    "order_id": order_id,
                                    "part": part_id,
                                    "supplier": winner.supplier_id,
                                    "supplier_id": winner.supplier_id,
                                    "supplier_name": winner.supplier_name,
                                    "quantity": quantity,
                                    "unit_price": winner.unit_price,
                                    "total_price": order.total_price,
                                    "currency": winner.currency,
                                    "lead_time_days": winner.lead_time_days,
                                },
                                run_id=rid,
                            )
                            events.append(ev6)
                        except Exception as exc:
                            logger.warning(
                                "  Order placement to %s failed: %s",
                                winner.supplier_id,
                                exc,
                            )

            results.append(result)

    # Serialise results
    serialised_results = []
    for r in results:
        serialised_results.append({
            "part": r.part,
            "rfq_id": r.rfq_id,
            "quotes_count": len(r.quotes),
            "counter_offer_sent": r.counter_offer_sent,
            "counter_offer_to": r.counter_offer_to,
            "winner": r.winner.supplier_id if r.winner else None,
            "winner_name": r.winner.supplier_name if r.winner else None,
            "winner_framework": r.winner.framework if r.winner else None,
            "winner_price": r.winner.unit_price if r.winner else None,
            "winner_score": r.winner.score if r.winner else None,
            "accepted": r.accepted,
            "order_id": r.order_id,
        })

    return {
        "negotiation_results": serialised_results,
        "orders": all_orders,
        "phase": "NEGOTIATE",
        "events": events,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node 5: PLAN — logistics + final report
# ═══════════════════════════════════════════════════════════════════════════

async def plan_node(state: ProcurementState) -> dict[str, Any]:
    """Request logistics plans and generate the final Network Coordination Report."""
    logger.info("▶ PLAN")
    rid = state.get("run_id", "")
    orders = state.get("orders", [])
    discovered = state.get("discovered_suppliers", {})
    verified = state.get("verified_suppliers", {})
    bom_dict = state.get("bom", {})
    neg_results = state.get("negotiation_results", [])
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    logistics_plans: list[dict[str, Any]] = []

    # --- Find logistics agents in the Index ---
    logistics_agents: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INDEX_URL}/search", params={"skills": "logistics"}
            )
            resp.raise_for_status()
            logistics_agents = resp.json()
    except Exception as exc:
        logger.warning("  Could not discover logistics agents: %s", exc)
        errors.append(f"Logistics discovery failed: {exc}")

    # --- Send LOGISTICS_REQUEST for each order ---
    async with httpx.AsyncClient(timeout=15.0) as client:
        for order in orders:
            log_req = LogisticsRequestPayload(
                order_id=order.get("order_id", ""),
                pickup_location=order.get("shipping_origin", "Unknown"),
                delivery_location=order.get("delivery_location", "Stuttgart, Germany"),
                cargo_description=f"{order.get('part', '')} x{order.get('quantity', 0)}",
                weight_kg=50.0,  # simulated
                volume_m3=0.5,  # simulated
                required_by=order.get("required_by", ""),
                priority="standard",
            )

            ev = await _emit_event(
                "LOGISTICS_REQUESTED",
                {
                    "order_id": order.get("order_id"),
                    "part": order.get("part"),
                    "pickup": log_req.pickup_location,
                    "delivery": log_req.delivery_location,
                    "cargo": log_req.cargo_description,
                },
                run_id=rid,
            )
            events.append(ev)

            # Try each logistics agent
            plan_received = False
            for logi in logistics_agents:
                logi_id = logi.get("agent_id", "")
                logi_facts_url = logi.get("facts_url", "")
                logi_base_url = logi_facts_url.rsplit("/", 1)[0] if logi_facts_url else ""

                if not logi_base_url:
                    continue

                try:
                    envelope = make_envelope(
                        MessageType.LOGISTICS_REQUEST,
                        from_agent=AGENT_ID,
                        to_agent=logi_id,
                        payload=log_req,
                        correlation_id=order.get("order_id", ""),
                    )
                    resp = await client.post(
                        f"{logi_base_url}/logistics",
                        json=envelope.model_dump(mode="json"),
                    )
                    resp.raise_for_status()
                    ship_data = resp.json()
                    ship_payload = ship_data.get("payload", ship_data)
                    logistics_plans.append(ship_payload)

                    ev2 = await _emit_event(
                        "SHIP_PLAN_RECEIVED",
                        {
                            "order_id": order.get("order_id"),
                            "route": ship_payload.get("route", []),
                            "transit_time_days": ship_payload.get("transit_time_days", 0),
                            "cost": ship_payload.get("cost", 0),
                            "estimated_arrival": ship_payload.get("estimated_arrival", ""),
                            "pickup": order.get("shipping_origin", ""),
                            "delivery": order.get("delivery_location", "Stuttgart, Germany"),
                            "from_agent": logi_id,
                        },
                        run_id=rid,
                    )
                    events.append(ev2)
                    plan_received = True
                    break  # one plan per order is sufficient
                except Exception as exc:
                    logger.warning(
                        "  Logistics request to %s failed: %s", logi_id, exc
                    )

            if not plan_received:
                # Generate a placeholder plan
                placeholder = {
                    "order_id": order.get("order_id", ""),
                    "route": [
                        order.get("shipping_origin", "Origin"),
                        "Stuttgart, Germany",
                    ],
                    "total_distance_km": 500.0,
                    "transit_time_days": 3,
                    "cost": 850.0,
                    "currency": "EUR",
                    "carrier": "Default Road Freight",
                    "mode": "road_freight",
                    "estimated_arrival": "2026-03-28",
                    "notes": "Placeholder plan (logistics agent unavailable)",
                }
                logistics_plans.append(placeholder)

    # --- Build Network Coordination Report ---
    missing_parts = state.get("missing_parts", [])
    report = _build_report(
        bom_dict=bom_dict,
        discovered=discovered,
        verified=verified,
        rejected=state.get("rejected_suppliers", {}),
        neg_results=neg_results,
        orders=orders,
        logistics_plans=logistics_plans,
        missing_parts=missing_parts,
    )

    ev_final = await _emit_event(
        "CASCADE_COMPLETE",
        {
            "total_cost": report.get("execution_plan", {}).get("total_cost", 0),
            "parts_ordered": report.get("execution_plan", {}).get("parts_ordered", 0),
            "suppliers_engaged": report.get("execution_plan", {}).get(
                "suppliers_engaged", 0
            ),
            "missing_parts_count": len(missing_parts),
        },
        run_id=rid,
    )
    events.append(ev_final)

    logger.info("✓ CASCADE COMPLETE — report generated")
    return {
        "logistics_plans": logistics_plans,
        "report": report,
        "phase": "PLAN",
        "events": events,
        "errors": errors,
    }


def _build_report(
    bom_dict: dict[str, Any],
    discovered: dict[str, list[dict[str, Any]]],
    verified: dict[str, dict[str, Any]],
    rejected: dict[str, str],
    neg_results: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    logistics_plans: list[dict[str, Any]],
    missing_parts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the Network Coordination Report."""
    # Discovery paths
    discovery_paths = []
    for skill, suppliers in discovered.items():
        discovery_paths.append({
            "skill": skill,
            "suppliers_found": len(suppliers),
            "supplier_ids": [s.get("agent_id") for s in suppliers],
        })

    # Trust verification
    trust_verification = {
        "verified_count": len(verified),
        "rejected_count": len(rejected),
        "verified_agents": list(verified.keys()),
        "rejected_agents": {
            agent_id: reason for agent_id, reason in rejected.items()
        },
        "policy": {
            "min_reliability": MIN_RELIABILITY,
            "acceptable_esg": sorted(ACCEPTABLE_ESG),
            "required_jurisdiction": sorted(REQUIRED_JURISDICTION),
        },
    }

    # Message exchanges summary
    total_messages = 0
    for nr in neg_results:
        total_messages += nr.get("quotes_count", 0)  # RFQ + QUOTE pairs
        if nr.get("counter_offer_sent"):
            total_messages += 2  # COUNTER + REVISED
        if nr.get("accepted"):
            total_messages += 2  # ACCEPT + ORDER

    # Execution plan
    total_cost = sum(o.get("total_price", 0) for o in orders)
    total_logistics_cost = sum(lp.get("cost", 0) for lp in logistics_plans)

    execution_plan = {
        "total_cost": round(total_cost + total_logistics_cost, 2),
        "procurement_cost": round(total_cost, 2),
        "logistics_cost": round(total_logistics_cost, 2),
        "currency": "EUR",
        "parts_ordered": len(orders),
        "suppliers_engaged": len(verified),
        "orders": orders,
        "logistics_plans": logistics_plans,
    }

    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intent": bom_dict.get("intent", ""),
        "bom_summary": {
            "vehicle_type": bom_dict.get("vehicle_type", ""),
            "total_parts": bom_dict.get("total_parts", 0),
            "systems": bom_dict.get("systems", []),
        },
        "discovery_paths": discovery_paths,
        "trust_verification": trust_verification,
        "policy_enforcement": {
            "ztaa_enabled": True,
            "agents_verified": len(verified),
            "agents_rejected": len(rejected),
        },
        "message_exchanges": {
            "total_messages": total_messages,
            "negotiation_rounds": len(neg_results),
            "details": neg_results,
        },
        "execution_plan": execution_plan,
        "missing_parts": missing_parts or [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# LangGraph: build and compile the graph
# ═══════════════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    """Construct the Procurement Agent state machine.

    DECOMPOSE → DISCOVER → VERIFY → NEGOTIATE → PLAN → END
    """
    graph = StateGraph(ProcurementState)

    # Register nodes
    graph.add_node("decompose", decompose_node)
    graph.add_node("discover", discover_node)
    graph.add_node("verify", verify_node)
    graph.add_node("negotiate", negotiate_node)
    graph.add_node("plan", plan_node)

    # Wire edges: linear cascade
    graph.add_edge(START, "decompose")
    graph.add_edge("decompose", "discover")
    graph.add_edge("discover", "verify")
    graph.add_edge("verify", "negotiate")
    graph.add_edge("negotiate", "plan")
    graph.add_edge("plan", END)

    return graph


def compile_graph():
    """Build and compile the procurement graph, ready to invoke."""
    graph = build_graph()
    return graph.compile()


# Pre-compiled graph instance for the server to use
procurement_graph = compile_graph()
