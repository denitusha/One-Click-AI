"""Supplier H — Brake Components — Custom Python (rule-based) agent.

Pure Python supplier with deterministic, rule-based logic — no LLM framework.
Inventory lookup, volume-discount pricing, and floor-price negotiation are
all computed directly from the simulated catalogue data.

Port 6009 · Skills: ``supply:brake_discs``, ``supply:brake_pads_ceramic``,
                    ``supply:brake_pads_semi_metallic``,
                    ``supply:brake_calipers_performance``

Endpoints
---------
- ``GET  /agent-facts`` — self-hosted AgentFacts (NANDA protocol)
- ``POST /rfq``         — receive an RFQ envelope, return a QUOTE envelope
- ``POST /counter``     — receive a COUNTER_OFFER, return REVISED_QUOTE or REJECT
- ``POST /order``       — confirm a purchase order
- ``GET  /health``      — health / readiness probe
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import (  # noqa: E402
    EVENT_BUS_HTTP_URL,
    INDEX_URL,
    SUPPLIER_PORTS,
)
from shared.message_types import (  # noqa: E402
    Envelope,
    MessageType,
    QuotePayload,
    RejectPayload,
    RevisedQuotePayload,
    make_envelope,
)
from shared.schemas import (  # noqa: E402
    AgentFacts,
    Certification,
    Endpoint,
    Evaluation,
    Policy,
    Skill,
)

from agents.supplier.inventory import (  # noqa: E402
    SUPPLIER_H_CATALOG,
    PartInfo,
    compute_volume_discount,
    evaluate_counter_offer,
    lookup_part,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [supplier-h] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supplier_h")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AGENT_ID = "supplier-h"
AGENT_NAME = "Brake Components (Custom Python)"
PORT = int(os.environ.get("PORT", SUPPLIER_PORTS.get("supplier_h", 6009)))
HOST = "0.0.0.0"
BASE_URL = f"http://localhost:{PORT}"

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_rfq_store: dict[str, dict[str, Any]] = {}  # rfq_id → RFQ + quoted price
_order_store: dict[str, dict[str, Any]] = {}  # order_id → order record


# ═══════════════════════════════════════════════════════════════════════════
# Rule-based quoting logic
# ═══════════════════════════════════════════════════════════════════════════

def _generate_quote(part_name: str, quantity: int) -> dict[str, Any] | None:
    """Generate a price quote using deterministic rule-based logic.

    Rules:
    1. Look up the part in Supplier H's catalogue.
    2. Apply volume discounts (≥20 → 2%, ≥50 → 3%, ≥100 → 5%).
    3. Cap available quantity at current stock level.
    4. Return quote data or ``None`` if the part is not found.
    """
    part = lookup_part("supplier_h", part_name)
    if part is None:
        return None

    discount = compute_volume_discount(quantity)
    unit_price = round(part.base_price * (1 - discount), 2)
    qty_available = min(quantity, part.stock_quantity)

    notes = "Rule-based pricing (no LLM). "
    if discount > 0:
        notes += f"Volume discount of {discount * 100:.0f}% applied for {quantity} units. "
    if qty_available < quantity:
        notes += f"Partial fulfilment: {qty_available}/{quantity} units in stock."
    else:
        notes += f"Full order can be fulfilled from stock ({part.stock_quantity} on hand)."

    return {
        "unit_price": unit_price,
        "currency": part.currency,
        "qty_available": qty_available,
        "lead_time_days": part.lead_time_days,
        "shipping_origin": part.shipping_origin,
        "certifications": part.certifications,
        "notes": notes.strip(),
    }


def _evaluate_counter(
    part_name: str, target_price: float
) -> dict[str, Any]:
    """Evaluate a counter-offer using simple floor-price rules.

    Rules:
    - If the target price ≥ floor price (base × floor_price_pct), ACCEPT
      at the target price (or floor, whichever is higher).
    - Otherwise REJECT — target is below our minimum margin.
    """
    result = evaluate_counter_offer("supplier_h", part_name, target_price)
    part = lookup_part("supplier_h", part_name)

    if result["accepted"]:
        return {
            "decision": "accept",
            "revised_price": result["revised_price"],
            "revised_lead_time": part.lead_time_days if part else None,
            "conditions": (
                f"Counter-offer accepted (rule-based). "
                f"Target €{target_price:.2f} is at or above floor €{result['floor_price']:.2f}."
            ),
        }
    return {
        "decision": "reject",
        "reason": result["reason"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# AgentFacts (self-hosted metadata)
# ═══════════════════════════════════════════════════════════════════════════

AGENT_FACTS = AgentFacts(
    id=AGENT_ID,
    agent_name=AGENT_NAME,
    label="Supplier H",
    description=(
        "German brake components supplier using pure rule-based Python logic "
        "(no LLM framework). Specialises in ventilated brake discs, ceramic and "
        "semi-metallic brake pads, and high-performance calipers for automotive "
        "applications. Deterministic pricing, fast response times, and strict "
        "floor-price negotiation policies."
    ),
    version="1.0.0",
    framework="custom",
    jurisdiction="EU",
    provider="Brake Components GmbH",
    skills=[
        Skill(
            id="supply:brake_discs",
            description=(
                "Ventilated cast iron brake discs with high thermal resistance"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=7,
        ),
        Skill(
            id="supply:brake_pads_ceramic",
            description=(
                "Low-dust ceramic brake pads for street and performance driving"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=5,
        ),
        Skill(
            id="supply:brake_pads_semi_metallic",
            description=(
                "High-performance semi-metallic brake pads for aggressive driving"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=4,
        ),
        Skill(
            id="supply:brake_calipers_performance",
            description=(
                "High-performance aluminum 4-piston brake calipers for track use"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=14,
        ),
        Skill(
            id="supply:brake_system",
            description=(
                "Complete integrated brake system with master cylinder, calipers, discs, pads, and ABS"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=20,
        ),
    ],
    endpoints=[
        Endpoint(
            path="/agent-facts",
            method="GET",
            description="Self-hosted AgentFacts (NANDA protocol)",
        ),
        Endpoint(
            path="/rfq",
            method="POST",
            description="Receive RFQ, return QUOTE",
        ),
        Endpoint(
            path="/counter",
            method="POST",
            description="Receive counter-offer, return REVISED_QUOTE or REJECT",
        ),
        Endpoint(
            path="/order",
            method="POST",
            description="Confirm purchase order",
        ),
        Endpoint(path="/health", method="GET", description="Health check"),
    ],
    evaluations=[
        Evaluation(evaluator="self", score=0.94, metric="reliability"),
        Evaluation(
            evaluator="industry_benchmark",
            score=0.90,
            metric="delivery_accuracy",
        ),
    ],
    certifications=[
        Certification(name="ISO 9001", issuer="TÜV SÜD"),
        Certification(name="IATF 16949", issuer="TÜV SÜD"),
        Certification(name="ECE R90", issuer="UNECE"),
        Certification(name="EU Tire Label", issuer="EU"),
    ],
    policies=[
        Policy(
            name="min_order_qty",
            description="Minimum order quantity varies by part",
            value={
                "brake_discs": 2,
                "brake_pads_ceramic": 4,
                "brake_pads_semi_metallic": 4,
                "brake_calipers_performance": 1,
                "brake_system": 1,
            },
        ),
        Policy(
            name="floor_price_policy",
            description=(
                "Floor prices vary by part: discs 85%, ceramic pads 80%, "
                "semi-metallic pads 82%, calipers 80%, brake_system 81% of base price"
            ),
            value={
                "brake_discs": 0.85,
                "brake_pads_ceramic": 0.80,
                "brake_pads_semi_metallic": 0.82,
                "brake_calipers_performance": 0.80,
                "brake_system": 0.81,
            },
        ),
        Policy(
            name="payment_terms",
            description="Net 30 days",
            value="net_30",
        ),
        Policy(
            name="negotiation_style",
            description=(
                "Rule-based: accept if target ≥ floor, reject otherwise. "
                "No LLM involved — instant deterministic decisions."
            ),
            value="deterministic",
        ),
    ],
    reliability_score=0.94,
    esg_rating="A",
    base_url=BASE_URL,
)


# ═══════════════════════════════════════════════════════════════════════════
# Event Bus helper
# ═══════════════════════════════════════════════════════════════════════════

async def _emit_event(
    event_type: str, data: dict[str, Any] | None = None
) -> None:
    """POST an event to the Event Bus (best-effort, non-blocking)."""
    event = {
        "event_type": event_type,
        "agent_id": AGENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{EVENT_BUS_HTTP_URL}/event", json=event)
    except Exception:
        logger.debug("Event Bus not reachable (non-fatal).")


# ═══════════════════════════════════════════════════════════════════════════
# NANDA Index registration
# ═══════════════════════════════════════════════════════════════════════════

async def _register_with_index() -> None:
    """Register this agent with the NANDA Lean Index."""
    payload = {
        "agent_id": AGENT_ID,
        "agent_name": AGENT_NAME,
        "facts_url": f"{BASE_URL}/agent-facts",
        "skills": [s.id for s in AGENT_FACTS.skills],
        "skill_descriptions": {s.id: s.description for s in AGENT_FACTS.skills},
        "region": "EU",
        "ttl": 3600,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{INDEX_URL}/register", json=payload)
            resp.raise_for_status()
            logger.info("Registered with NANDA Index: %s", resp.json())
    except Exception as exc:
        logger.warning("Failed to register with NANDA Index: %s", exc)


async def _emit_startup_event() -> None:
    """Notify the Event Bus that this agent is online."""
    await _emit_event(
        "AGENT_REGISTERED",
        {
            "agent_name": AGENT_NAME,
            "framework": "custom",
            "port": PORT,
            "skills": [s.id for s in AGENT_FACTS.skills],
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI application
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    logger.info("Supplier H (Brake - Custom Python) starting on port %d …", PORT)
    await _register_with_index()
    await _emit_startup_event()
    logger.info("Supplier H ready at %s  (pure rule-based, no LLM)", BASE_URL)
    yield
    logger.info("Supplier H shutting down.")


app = FastAPI(
    title="Supplier H — Brake Components (Custom Python)",
    description=(
        "Pure Python rule-based supplier agent. Deterministic quoting "
        "and negotiation — no LLM framework required."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/agent-facts")
async def agent_facts():
    """Self-hosted AgentFacts endpoint (NANDA protocol)."""
    return AGENT_FACTS.model_dump(mode="json")


@app.post("/rfq")
async def receive_rfq(envelope: Envelope):
    """Process an incoming RFQ and return a QUOTE (or REJECT).

    Entirely rule-based: look up the part in the catalogue, apply volume
    discounts, and return a deterministic quote.  No LLM calls.
    """
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", str(uuid.uuid4()))
    part_name = payload.get("part", "")
    quantity = int(payload.get("quantity", 1))
    required_by = payload.get("required_by", "")
    delivery_location = payload.get("delivery_location", "")
    compliance = payload.get("compliance_requirements", [])

    logger.info(
        "RFQ received: %s  —  %d × %s  (from %s)",
        rfq_id,
        quantity,
        part_name,
        envelope.from_agent,
    )

    # Persist RFQ for later counter-offer / order reference
    _rfq_store[rfq_id] = {
        "part": part_name,
        "quantity": quantity,
        "required_by": required_by,
        "delivery_location": delivery_location,
        "compliance": compliance,
        "from_agent": envelope.from_agent,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    # --- Check catalogue ---
    part_info = lookup_part("supplier_h", part_name)
    if part_info is None:
        logger.info("Part '%s' not in catalogue — rejecting RFQ", part_name)
        await _emit_event(
            "RFQ_REJECTED",
            {
                "rfq_id": rfq_id,
                "part": part_name,
                "reason": "not_in_catalogue",
                "from_agent": envelope.from_agent,
            },
        )
        reject_env = make_envelope(
            MessageType.REJECT,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=RejectPayload(
                rfq_id=rfq_id,
                rejection_reason=f"Part '{part_name}' is not in our catalogue.",
            ),
            correlation_id=rfq_id,
        )
        return reject_env.model_dump(mode="json")

    # --- Check minimum order quantity ---
    if quantity < part_info.min_order_qty:
        reason = (
            f"Quantity {quantity} is below minimum order quantity "
            f"of {part_info.min_order_qty} for {part_info.part_name}."
        )
        logger.info("MOQ not met for '%s' — rejecting RFQ: %s", part_name, reason)
        await _emit_event(
            "RFQ_REJECTED",
            {
                "rfq_id": rfq_id,
                "part": part_name,
                "reason": "below_moq",
                "min_order_qty": part_info.min_order_qty,
            },
        )
        reject_env = make_envelope(
            MessageType.REJECT,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=RejectPayload(rfq_id=rfq_id, rejection_reason=reason),
            correlation_id=rfq_id,
        )
        return reject_env.model_dump(mode="json")

    # --- Generate rule-based quote ---
    quote_data = _generate_quote(part_name, quantity)

    if quote_data is None:
        reject_env = make_envelope(
            MessageType.REJECT,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=RejectPayload(
                rfq_id=rfq_id,
                rejection_reason="Unable to generate quote.",
            ),
            correlation_id=rfq_id,
        )
        return reject_env.model_dump(mode="json")

    # --- Build QUOTE envelope ---
    valid_until = (datetime.now(timezone.utc) + timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )

    quote_payload = QuotePayload(
        rfq_id=rfq_id,
        unit_price=float(quote_data["unit_price"]),
        currency=quote_data.get("currency", part_info.currency),
        qty_available=int(quote_data["qty_available"]),
        lead_time_days=int(quote_data["lead_time_days"]),
        shipping_origin=quote_data.get("shipping_origin", part_info.shipping_origin),
        certifications=quote_data.get("certifications", part_info.certifications),
        valid_until=valid_until,
        notes=quote_data.get("notes", ""),
    )

    # Track the quoted price for counter-offer reference
    _rfq_store[rfq_id]["quoted_price"] = quote_payload.unit_price

    # Emit event
    await _emit_event(
        "QUOTE_GENERATED",
        {
            "rfq_id": rfq_id,
            "part": part_name,
            "to_agent": envelope.from_agent,
            "unit_price": quote_payload.unit_price,
            "qty_available": quote_payload.qty_available,
            "lead_time_days": quote_payload.lead_time_days,
            "method": "rule_based",
        },
    )

    response_env = make_envelope(
        MessageType.QUOTE,
        from_agent=AGENT_ID,
        to_agent=envelope.from_agent,
        payload=quote_payload,
        correlation_id=rfq_id,
    )

    logger.info(
        "QUOTE → %s: €%.2f/unit, %d available, %dd lead  [rule-based]",
        envelope.from_agent,
        quote_payload.unit_price,
        quote_payload.qty_available,
        quote_payload.lead_time_days,
    )
    return response_env.model_dump(mode="json")


@app.post("/counter")
async def receive_counter_offer(envelope: Envelope):
    """Process a counter-offer → return REVISED_QUOTE or REJECT.

    Simple floor-price rule: accept if target ≥ floor (varies by part),
    otherwise reject.  No LLM — instant deterministic decision.
    """
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", "")
    target_price = float(payload.get("target_price", 0.0))
    flexible_date = bool(payload.get("flexible_date", False))
    justification = payload.get("justification", "")

    # Look up the original RFQ
    rfq_data = _rfq_store.get(rfq_id, {})
    part_name = rfq_data.get("part", "")
    original_price = rfq_data.get("quoted_price", 0.0)

    logger.info(
        "COUNTER received for RFQ %s: target €%.2f  (original €%.2f, part=%s)  "
        "justification=%r",
        rfq_id,
        target_price,
        original_price,
        part_name,
        justification,
    )

    # --- Evaluate with rule-based logic ---
    if part_name:
        decision = _evaluate_counter(part_name, target_price)
    else:
        decision = {
            "decision": "reject",
            "reason": f"Unknown RFQ {rfq_id} — no part on record.",
        }

    # If the date is flexible and we rejected, log that we still can't help
    if decision["decision"] == "reject" and flexible_date:
        logger.info(
            "Customer indicated flexible date, but target €%.2f still below "
            "floor — cannot accept.",
            target_price,
        )

    # Emit event
    await _emit_event(
        "COUNTER_EVALUATED",
        {
            "rfq_id": rfq_id,
            "part": part_name,
            "target_price": target_price,
            "decision": decision["decision"],
            "method": "rule_based",
        },
    )

    # --- Build response envelope ---
    if decision["decision"] == "accept":
        part_info = lookup_part("supplier_h", part_name)
        revised_payload = RevisedQuotePayload(
            rfq_id=rfq_id,
            revised_price=float(decision["revised_price"]),
            revised_lead_time=decision.get(
                "revised_lead_time",
                part_info.lead_time_days if part_info else None,
            ),
            conditions=decision.get(
                "conditions",
                "Counter-offer accepted within floor-price policy.",
            ),
        )
        response_env = make_envelope(
            MessageType.REVISED_QUOTE,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=revised_payload,
            correlation_id=rfq_id,
        )
        logger.info(
            "COUNTER ACCEPTED → revised €%.2f  [rule-based]",
            revised_payload.revised_price,
        )
    else:
        reject_payload = RejectPayload(
            rfq_id=rfq_id,
            rejection_reason=decision.get("reason", "Below floor price."),
        )
        response_env = make_envelope(
            MessageType.REJECT,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=reject_payload,
            correlation_id=rfq_id,
        )
        logger.info(
            "COUNTER REJECTED: %s  [rule-based]",
            decision.get("reason"),
        )

    return response_env.model_dump(mode="json")


@app.post("/order")
async def receive_order(envelope: Envelope):
    """Confirm a purchase order and update internal state."""
    payload = envelope.payload
    order_id = payload.get("order_id", str(uuid.uuid4()))
    rfq_id = payload.get("rfq_id", "")
    part = payload.get("part", "")
    quantity = int(payload.get("quantity", 0))
    unit_price = float(payload.get("unit_price", 0.0))
    total_price = round(unit_price * quantity, 2)

    logger.info(
        "ORDER confirmed: %s  —  %d × %s @ €%.2f = €%.2f",
        order_id,
        quantity,
        part,
        unit_price,
        total_price,
    )

    _order_store[order_id] = {
        "order_id": order_id,
        "rfq_id": rfq_id,
        "part": part,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "confirmed",
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Optionally deduct stock (simulated)
    part_info = lookup_part("supplier_h", part)
    if part_info is not None:
        part_info.stock_quantity = max(0, part_info.stock_quantity - quantity)
        logger.info(
            "Stock updated for %s: %d remaining",
            part,
            part_info.stock_quantity,
        )

    await _emit_event(
        "ORDER_CONFIRMED",
        {
            "order_id": order_id,
            "part": part,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
        },
    )

    return {
        "status": "confirmed",
        "order_id": order_id,
        "message": f"Order {order_id} confirmed: {quantity} × {part}",
    }


@app.get("/health")
async def health():
    """Liveness / readiness probe."""
    return {
        "status": "ok",
        "service": "supplier-h",
        "framework": "custom",
        "agent_id": AGENT_ID,
        "catalog_parts": list(SUPPLIER_H_CATALOG.keys()),
        "active_rfqs": len(_rfq_store),
        "confirmed_orders": len(_order_store),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "supplier_brakes:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
