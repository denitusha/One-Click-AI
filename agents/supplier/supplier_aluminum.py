"""Supplier D — Aluminum & Materials — CrewAI-powered agent.

A two-role CrewAI crew handles incoming procurement requests:

- **Inventory Checker**: validates stock availability for requested parts.
- **Pricing Analyst**: generates competitive quotes and evaluates counter-offers.

Port 6005 · Skills: ``supply:aluminum_cans``, ``supply:aluminum_engine_block``, ``supply:aluminum_sheet_stock``

Endpoints
---------
- ``GET  /agent-facts`` — self-hosted AgentFacts (NANDA protocol)
- ``POST /rfq``         — receive an RFQ envelope, return a QUOTE envelope
- ``POST /counter``     — receive a COUNTER_OFFER, return REVISED_QUOTE or REJECT
- ``POST /order``       — confirm a purchase order
- ``GET  /health``      — health / readiness probe
"""

from __future__ import annotations

import asyncio
import json
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
    OPENAI_MODEL,
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
    SUPPLIER_D_CATALOG,
    PartInfo,
    compute_volume_discount,
    evaluate_counter_offer,
    lookup_part,
)

# ---------------------------------------------------------------------------
# CrewAI imports (graceful degradation if unavailable)
# ---------------------------------------------------------------------------
try:
    from crewai import Agent, Crew, Process, Task
    from crewai.tools import tool as crewai_tool

    CREWAI_AVAILABLE = True
except Exception:  # ImportError, ModuleNotFoundError, etc.
    CREWAI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [supplier-d] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supplier_d")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AGENT_ID = "supplier-d"
AGENT_NAME = "Aluminum & Materials Supplier (CrewAI)"
PORT = int(os.environ.get("PORT", SUPPLIER_PORTS["supplier_d"]))
HOST = "0.0.0.0"
BASE_URL = f"http://localhost:{PORT}"

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_rfq_store: dict[str, dict[str, Any]] = {}  # rfq_id → RFQ + quoted price
_order_store: dict[str, dict[str, Any]] = {}  # order_id → order record


# ═══════════════════════════════════════════════════════════════════════════
# CrewAI Tools
# ═══════════════════════════════════════════════════════════════════════════
if CREWAI_AVAILABLE:

    @crewai_tool("Check Inventory")
    def check_inventory_tool(part_name: str) -> str:
        """Check the warehouse inventory for a specific aluminum or materials part.
        Returns stock quantity, base price, lead time, and certifications.
        Use part identifiers like 'aluminum_cans', 'aluminum_engine_block', or 'aluminum_sheet_stock'."""
        part = lookup_part("supplier_d", part_name)
        if part is None:
            return f"Part '{part_name}' NOT FOUND in our inventory. We do not supply this part."
        return (
            f"INVENTORY CHECK RESULT:\n"
            f"Part: {part.part_name} ({part.part_id})\n"
            f"Description: {part.description}\n"
            f"Available Stock: {part.stock_quantity} units\n"
            f"Base Price: EUR {part.base_price:.2f} per unit\n"
            f"Lead Time: {part.lead_time_days} days\n"
            f"Shipping From: {part.shipping_origin}\n"
            f"Certifications: {', '.join(part.certifications)}\n"
            f"Minimum Order Quantity: {part.min_order_qty} units\n"
            f"Technical Specs: {json.dumps(part.specs)}"
        )

    @crewai_tool("Calculate Pricing")
    def calculate_pricing_tool(part_name: str, quantity: int) -> str:
        """Calculate optimal pricing for a part and quantity.
        Returns recommended unit price, total cost, and volume discount details.
        part_name should be like 'aluminum_cans' or 'aluminum_engine_block'. quantity is the number of units."""
        qty = int(quantity) if isinstance(quantity, str) else quantity
        part = lookup_part("supplier_d", part_name)
        if part is None:
            return f"Cannot calculate pricing: part '{part_name}' not in our catalogue."

        discount = compute_volume_discount(qty)
        unit_price = round(part.base_price * (1 - discount), 2)
        total_price = round(unit_price * qty, 2)
        floor = part.floor_price
        can_fulfill = qty <= part.stock_quantity

        return (
            f"PRICING ANALYSIS:\n"
            f"Part: {part.part_name}\n"
            f"Quantity Requested: {qty}\n"
            f"Base Price: EUR {part.base_price:.2f}/unit\n"
            f"Volume Discount: {discount * 100:.0f}%\n"
            f"Recommended Unit Price: EUR {unit_price:.2f}\n"
            f"Total Price: EUR {total_price:.2f}\n"
            f"Floor Price (absolute minimum): EUR {floor:.2f}/unit\n"
            f"Can Fulfill: {'YES' if can_fulfill else 'PARTIAL (stock: ' + str(part.stock_quantity) + ')'}\n"
            f"Available Quantity: {min(qty, part.stock_quantity)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# CrewAI crew builders
# ═══════════════════════════════════════════════════════════════════════════

def _build_rfq_crew(
    part_name: str,
    quantity: int,
    required_by: str,
    delivery_location: str,
    compliance: list[str],
) -> Crew | None:
    """Build a sequential crew: Inventory Checker → Pricing Analyst."""
    if not CREWAI_AVAILABLE:
        return None

    inventory_checker = Agent(
        role="Inventory Checker",
        goal=(
            "Verify part availability and stock levels for incoming purchase "
            "requests.  Report accurate inventory status including quantities, "
            "lead times, and certifications."
        ),
        backstory=(
            "You are a meticulous warehouse inventory specialist at Aluminum & "
            "Materials Supply Co., a leading European multi-industry supplier of "
            "aluminum products serving automotive, beverage, and manufacturing "
            "sectors.  Your expertise ensures accurate stock reporting and reliable "
            "supply commitments across diverse industries."
        ),
        tools=[check_inventory_tool],
        llm=OPENAI_MODEL,
        verbose=True,
        allow_delegation=False,
    )

    pricing_analyst = Agent(
        role="Pricing Analyst",
        goal=(
            "Generate competitive yet profitable price quotes based on inventory "
            "data, quantity requirements, and market conditions."
        ),
        backstory=(
            "You are a senior pricing analyst at Aluminum & Materials Supply Co. "
            "specialising in B2B pricing across multiple industries.  You consider "
            "volume discounts, urgency premiums, and competitive positioning to "
            "generate optimal quotes that win business while protecting margins."
        ),
        tools=[calculate_pricing_tool],
        llm=OPENAI_MODEL,
        verbose=True,
        allow_delegation=False,
    )

    compliance_str = ", ".join(compliance) if compliance else "standard"

    check_task = Task(
        description=(
            f"Check our inventory for part '{part_name}'.\n"
            f"The customer needs {quantity} units, delivered to "
            f"{delivery_location} by {required_by}.\n"
            f"Required compliance: {compliance_str}.\n"
            f"Verify we have sufficient stock and can meet the delivery timeline."
        ),
        expected_output=(
            "A detailed inventory status report including: availability (yes/no), "
            "stock quantity, lead time, certifications match, and any supply "
            "constraints."
        ),
        agent=inventory_checker,
    )

    quote_task = Task(
        description=(
            f"Based on the inventory check results, generate a price quote for "
            f"{quantity} units of '{part_name}'.\n"
            f"Delivery to {delivery_location} by {required_by}.\n"
            f"Consider volume discounts for the requested quantity.\n\n"
            f"You MUST output ONLY a valid JSON object with these exact fields:\n"
            f'{{"unit_price": <number>, "qty_available": <integer>, '
            f'"lead_time_days": <integer>, "notes": "<brief justification>"}}\n\n'
            f"Do NOT include any other text, explanation, or markdown formatting."
        ),
        expected_output=(
            'A JSON object: {"unit_price": ..., "qty_available": ..., '
            '"lead_time_days": ..., "notes": "..."}'
        ),
        agent=pricing_analyst,
    )

    return Crew(
        agents=[inventory_checker, pricing_analyst],
        tasks=[check_task, quote_task],
        process=Process.sequential,
        verbose=True,
    )


def _build_counter_crew(
    part_name: str,
    rfq_id: str,
    original_price: float,
    target_price: float,
    flexible_date: bool,
    justification: str,
) -> Crew | None:
    """Build a single-agent crew for counter-offer evaluation."""
    if not CREWAI_AVAILABLE:
        return None

    part = lookup_part("supplier_d", part_name)
    floor = part.floor_price if part else 0.0

    pricing_analyst = Agent(
        role="Pricing Analyst",
        goal=(
            "Evaluate counter-offers against floor prices and profitability "
            "targets.  Accept reasonable offers, or reject those below floor."
        ),
        backstory=(
            "You are the senior pricing analyst at Aluminum & Materials Supply Co. "
            f"For part '{part_name}', our absolute minimum floor price "
            f"is EUR {floor:.2f}/unit.  You protect margins while maintaining "
            "long-term customer relationships."
        ),
        tools=[calculate_pricing_tool],
        llm=OPENAI_MODEL,
        verbose=True,
        allow_delegation=False,
    )

    eval_task = Task(
        description=(
            f"Evaluate this counter-offer for RFQ {rfq_id}:\n"
            f"  Part: {part_name}\n"
            f"  Our original quote: EUR {original_price:.2f}/unit\n"
            f"  Customer target price: EUR {target_price:.2f}/unit\n"
            f"  Customer flexible on date: {flexible_date}\n"
            f"  Customer justification: {justification}\n"
            f"  Our floor price: EUR {floor:.2f}/unit\n\n"
            f"Rules:\n"
            f"  - If target >= floor: ACCEPT.  Set revised_price to target.\n"
            f"  - If target < floor: REJECT.\n\n"
            f"Output ONLY a JSON object (no other text):\n"
            f"Accept: "
            f'{{"decision": "accept", "revised_price": <number>, '
            f'"revised_lead_time": <integer_or_null>, "conditions": "<string>"}}\n'
            f"Reject: "
            f'{{"decision": "reject", "reason": "<explanation>"}}'
        ),
        expected_output="A JSON object with the pricing decision.",
        agent=pricing_analyst,
    )

    return Crew(
        agents=[pricing_analyst],
        tasks=[eval_task],
        process=Process.sequential,
        verbose=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Deterministic fallback logic (used when CrewAI / LLM is unavailable)
# ═══════════════════════════════════════════════════════════════════════════

def _deterministic_quote(part_name: str, quantity: int) -> dict[str, Any] | None:
    """Generate a quote using rule-based logic."""
    part = lookup_part("supplier_d", part_name)
    if part is None:
        return None

    discount = compute_volume_discount(quantity)
    unit_price = round(part.base_price * (1 - discount), 2)
    qty_available = min(quantity, part.stock_quantity)

    notes = "Standard pricing."
    if discount > 0:
        notes = f"Volume discount of {discount * 100:.0f}% applied for {quantity} units."
    if qty_available < quantity:
        notes += f" Partial fulfilment: {qty_available}/{quantity} units in stock."

    return {
        "unit_price": unit_price,
        "currency": part.currency,
        "qty_available": qty_available,
        "lead_time_days": part.lead_time_days,
        "shipping_origin": part.shipping_origin,
        "certifications": part.certifications,
        "notes": notes,
    }


def _deterministic_counter_eval(
    part_name: str,
    target_price: float,
) -> dict[str, Any]:
    """Evaluate a counter-offer deterministically."""
    result = evaluate_counter_offer("supplier_d", part_name, target_price)
    part = lookup_part("supplier_d", part_name)

    if result["accepted"]:
        return {
            "decision": "accept",
            "revised_price": result["revised_price"],
            "revised_lead_time": part.lead_time_days if part else None,
            "conditions": "Counter-offer accepted within our margin policy.",
        }
    return {
        "decision": "reject",
        "reason": result["reason"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Parse JSON from CrewAI output
# ═══════════════════════════════════════════════════════════════════════════

def _parse_crew_json(raw_output: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from a CrewAI output string."""
    text = raw_output.strip()
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()

    # Direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Find the first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    return None


# ═══════════════════════════════════════════════════════════════════════════
# AgentFacts (self-hosted metadata)
# ═══════════════════════════════════════════════════════════════════════════

AGENT_FACTS = AgentFacts(
    id=AGENT_ID,
    agent_name=AGENT_NAME,
    label="Supplier D",
    description=(
        "Multi-industry aluminum supplier powered by CrewAI. "
        "Serves automotive, beverage, and manufacturing sectors with aluminum "
        "products including beverage cans, engine blocks, and sheet stock.  "
        "Two-agent crew: Inventory Checker validates stock, Pricing Analyst "
        "generates optimal quotes."
    ),
    version="1.0.0",
    framework="crewai",
    jurisdiction="EU",
    provider="Aluminum & Materials Supply Co.",
    skills=[
        Skill(
            id="supply:aluminum_cans",
            description=(
                "Food-grade aluminum beverage cans in 330ml and 500ml sizes"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=5,
        ),
        Skill(
            id="supply:aluminum_engine_block",
            description=(
                "A356 aluminum alloy engine block, 6-cylinder, 3.0L displacement"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=35,
        ),
        Skill(
            id="supply:aluminum_sheet_stock",
            description=(
                "Raw aluminum sheets in various grades and thicknesses for manufacturing"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=10,
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
        Evaluation(evaluator="self", score=0.90, metric="reliability"),
        Evaluation(
            evaluator="industry_benchmark",
            score=0.85,
            metric="delivery_accuracy",
        ),
    ],
    certifications=[
        Certification(name="ISO 9001", issuer="TÜV SÜD"),
        Certification(name="IATF 16949", issuer="TÜV SÜD"),
        Certification(name="FDA", issuer="FDA"),
        Certification(name="ISO 22000", issuer="TÜV SÜD"),
        Certification(name="REACH", issuer="ECHA"),
    ],
    policies=[
        Policy(
            name="min_order_qty",
            description="Minimum order quantity varies by part",
            value={"aluminum_cans": 1000, "aluminum_engine_block": 1, "aluminum_sheet_stock": 100},
        ),
        Policy(
            name="floor_price_policy",
            description="Minimum 80-90% of base price on negotiations",
            value=0.85,
        ),
        Policy(
            name="payment_terms",
            description="Net 30 days",
            value="net_30",
        ),
    ],
    reliability_score=0.90,
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
            "framework": "crewai",
            "port": PORT,
            "skills": [s.id for s in AGENT_FACTS.skills],
            "crewai_available": CREWAI_AVAILABLE,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI application
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    logger.info("Supplier D (CrewAI) starting on port %d …", PORT)
    await _register_with_index()
    await _emit_startup_event()
    logger.info(
        "Supplier D ready at %s  (CrewAI: %s)",
        BASE_URL,
        "enabled" if CREWAI_AVAILABLE else "fallback-only",
    )
    yield
    logger.info("Supplier D shutting down.")


app = FastAPI(
    title="Supplier D — Aluminum & Materials (CrewAI)",
    description=(
        "CrewAI-powered aluminum supplier agent serving multiple industries "
        "with inventory check and pricing analysis."
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

    The CrewAI crew (Inventory Checker → Pricing Analyst) evaluates the
    request and generates a competitive quote.  Falls back to rule-based
    logic if the LLM is unavailable.
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
    part_info = lookup_part("supplier_d", part_name)
    if part_info is None:
        logger.info("Part '%s' not in catalogue — rejecting RFQ", part_name)
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

    # --- Try CrewAI crew ---
    quote_data: dict[str, Any] | None = None
    used_crewai = False

    if CREWAI_AVAILABLE:
        try:
            crew = _build_rfq_crew(
                part_name, quantity, required_by, delivery_location, compliance
            )
            if crew:
                logger.info("Running CrewAI crew for RFQ %s …", rfq_id)
                result = await asyncio.to_thread(crew.kickoff)
                raw_output = getattr(result, "raw", str(result))
                logger.info("CrewAI raw output: %s", raw_output[:500])

                parsed = _parse_crew_json(raw_output)
                if parsed and "unit_price" in parsed:
                    quote_data = parsed
                    used_crewai = True
                    logger.info(
                        "CrewAI quote parsed successfully: €%.2f/unit",
                        quote_data["unit_price"],
                    )
                else:
                    logger.warning(
                        "Could not parse JSON from CrewAI output — "
                        "falling back to deterministic."
                    )
        except Exception as exc:
            logger.warning(
                "CrewAI crew failed (%s) — falling back to deterministic.", exc
            )

    # --- Deterministic fallback ---
    if quote_data is None:
        logger.info("Using deterministic quote for %s", part_name)
        quote_data = _deterministic_quote(part_name, quantity)

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
        unit_price=float(quote_data.get("unit_price", part_info.base_price)),
        currency=quote_data.get("currency", part_info.currency),
        qty_available=int(
            quote_data.get(
                "qty_available", min(quantity, part_info.stock_quantity)
            )
        ),
        lead_time_days=int(
            quote_data.get("lead_time_days", part_info.lead_time_days)
        ),
        shipping_origin=quote_data.get(
            "shipping_origin", part_info.shipping_origin
        ),
        certifications=quote_data.get(
            "certifications", part_info.certifications
        ),
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
            "method": "crewai" if used_crewai else "deterministic",
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
        "QUOTE → %s: €%.2f/unit, %d available, %dd lead  [%s]",
        envelope.from_agent,
        quote_payload.unit_price,
        quote_payload.qty_available,
        quote_payload.lead_time_days,
        "crewai" if used_crewai else "deterministic",
    )
    return response_env.model_dump(mode="json")


@app.post("/counter")
async def receive_counter_offer(envelope: Envelope):
    """Process a counter-offer → return REVISED_QUOTE or REJECT.

    The Pricing Analyst evaluates the target price against our floor
    (80-90% of base depending on part).  Accepts if target ≥ floor; rejects otherwise.
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
        "COUNTER received for RFQ %s: target €%.2f  (original €%.2f, part=%s)",
        rfq_id,
        target_price,
        original_price,
        part_name,
    )

    # --- Try CrewAI ---
    decision: dict[str, Any] | None = None
    used_crewai = False

    if CREWAI_AVAILABLE and part_name:
        try:
            crew = _build_counter_crew(
                part_name,
                rfq_id,
                original_price,
                target_price,
                flexible_date,
                justification,
            )
            if crew:
                logger.info("Running CrewAI counter-offer evaluation …")
                result = await asyncio.to_thread(crew.kickoff)
                raw_output = getattr(result, "raw", str(result))
                parsed = _parse_crew_json(raw_output)
                if parsed and "decision" in parsed:
                    decision = parsed
                    used_crewai = True
                    logger.info("CrewAI decision: %s", decision["decision"])
        except Exception as exc:
            logger.warning("CrewAI counter evaluation failed: %s", exc)

    # --- Deterministic fallback ---
    if decision is None:
        if part_name:
            decision = _deterministic_counter_eval(part_name, target_price)
        else:
            decision = {
                "decision": "reject",
                "reason": f"Unknown RFQ {rfq_id}",
            }

    # Emit event
    await _emit_event(
        "COUNTER_EVALUATED",
        {
            "rfq_id": rfq_id,
            "part": part_name,
            "target_price": target_price,
            "decision": decision.get("decision", "reject"),
            "method": "crewai" if used_crewai else "deterministic",
        },
    )

    # --- Build response envelope ---
    if decision.get("decision") == "accept":
        part_info = lookup_part("supplier_d", part_name)
        revised_payload = RevisedQuotePayload(
            rfq_id=rfq_id,
            revised_price=float(
                decision.get("revised_price", target_price)
            ),
            revised_lead_time=(
                decision.get("revised_lead_time")
                or (part_info.lead_time_days if part_info else None)
            ),
            conditions=decision.get(
                "conditions",
                "Counter-offer accepted within our margin policy.",
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
            "COUNTER ACCEPTED → revised €%.2f  [%s]",
            revised_payload.revised_price,
            "crewai" if used_crewai else "deterministic",
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
            "COUNTER REJECTED: %s  [%s]",
            decision.get("reason"),
            "crewai" if used_crewai else "deterministic",
        )

    return response_env.model_dump(mode="json")


@app.post("/order")
async def receive_order(envelope: Envelope):
    """Confirm a purchase order."""
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
        "service": "supplier-d",
        "framework": "crewai",
        "agent_id": AGENT_ID,
        "crewai_available": CREWAI_AVAILABLE,
        "catalog_parts": list(SUPPLIER_D_CATALOG.keys()),
        "active_rfqs": len(_rfq_store),
        "confirmed_orders": len(_order_store),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "supplier_aluminum:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
