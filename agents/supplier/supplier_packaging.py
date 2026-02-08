"""Supplier E — Packaging & Ingredients — LangChain-powered agent.

A simple LangChain chain (prompt template → ChatOpenAI → JSON output parser)
handles incoming procurement requests.  The LLM generates competitive quotes
and evaluates counter-offers based on inventory context injected via the prompt.

Port 6006 · Skills: ``supply:labels_packaging``, ``supply:caffeine_supply``,
                  ``supply:taurine_supply``, ``supply:bottling_equipment``,
                  ``supply:distribution_supplies``

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
    SUPPLIER_E_CATALOG,
    PartInfo,
    compute_volume_discount,
    evaluate_counter_offer,
    lookup_part,
)

# ---------------------------------------------------------------------------
# LangChain imports (graceful degradation if unavailable)
# ---------------------------------------------------------------------------
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    LANGCHAIN_AVAILABLE = True
except Exception:  # ImportError, ModuleNotFoundError, etc.
    LANGCHAIN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [supplier-e] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supplier_e")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AGENT_ID = "supplier-e"
AGENT_NAME = "Packaging & Ingredients Supplier (LangChain)"
PORT = int(os.environ.get("PORT", SUPPLIER_PORTS["supplier_e"]))
HOST = "0.0.0.0"
BASE_URL = f"http://localhost:{PORT}"

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_rfq_store: dict[str, dict[str, Any]] = {}  # rfq_id → RFQ + quoted price
_order_store: dict[str, dict[str, Any]] = {}  # order_id → order record


# ═══════════════════════════════════════════════════════════════════════════
# LangChain chains
# ═══════════════════════════════════════════════════════════════════════════

_llm: Any = None
_rfq_chain: Any = None
_counter_chain: Any = None


def _init_chains() -> None:
    """Initialise the LangChain LLM and chains (idempotent)."""
    global _llm, _rfq_chain, _counter_chain

    if not LANGCHAIN_AVAILABLE or _llm is not None:
        return

    try:
        _llm = ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=0.2,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("Failed to initialise ChatOpenAI: %s", exc)
        return

    # ----- RFQ quote generation chain -----
    rfq_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a pricing analyst at Packaging & Ingredients Supply Co., "
                    "a European supplier of beverage supply chain components including "
                    "packaging materials, ingredients, and bottling equipment, based "
                    "in Brussels, Belgium.\n\n"
                    "Your job is to generate competitive price quotes for incoming "
                    "procurement requests based on inventory data provided below.\n\n"
                    "Always respond with ONLY a valid JSON object — no markdown "
                    "fences, no explanation, no extra text."
                ),
            ),
            (
                "human",
                (
                    "Generate a price quote for the following request:\n\n"
                    "Part: {part_name}\n"
                    "Description: {part_description}\n"
                    "Quantity Requested: {quantity}\n"
                    "Required By: {required_by}\n"
                    "Delivery Location: {delivery_location}\n"
                    "Compliance Requirements: {compliance}\n\n"
                    "Inventory Data:\n"
                    "  Base Price: EUR {base_price}/unit\n"
                    "  Stock Available: {stock_quantity} units\n"
                    "  Lead Time: {lead_time_days} days\n"
                    "  Floor Price: EUR {floor_price}/unit\n"
                    "  Volume Discount: {discount_pct}%\n"
                    "  Discounted Unit Price: EUR {discounted_price}/unit\n"
                    "  Shipping Origin: {shipping_origin}\n"
                    "  Certifications: {certifications}\n"
                    "  Specs: {specs}\n\n"
                    "Rules:\n"
                    "- Unit price should be at or above the discounted price.\n"
                    "- Available quantity is min(requested, stock).\n"
                    "- Be competitive but protect margins (stay above floor).\n"
                    "- Consider urgency and compliance requirements.\n\n"
                    "Respond with ONLY this JSON (no other text):\n"
                    '{{"unit_price": <number>, "qty_available": <integer>, '
                    '"lead_time_days": <integer>, "notes": "<brief justification>"}}'
                ),
            ),
        ]
    )

    _rfq_chain = rfq_prompt | _llm | StrOutputParser()

    # ----- Counter-offer evaluation chain -----
    counter_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a pricing analyst at Packaging & Ingredients Supply Co. "
                    "Your job is to evaluate counter-offers from procurement agents.\n\n"
                    "Always respond with ONLY a valid JSON object — no markdown "
                    "fences, no explanation, no extra text."
                ),
            ),
            (
                "human",
                (
                    "Evaluate this counter-offer:\n\n"
                    "Part: {part_name}\n"
                    "RFQ ID: {rfq_id}\n"
                    "Our Original Quote: EUR {original_price}/unit\n"
                    "Customer Target Price: EUR {target_price}/unit\n"
                    "Customer Flexible on Date: {flexible_date}\n"
                    "Customer Justification: {justification}\n"
                    "Our Floor Price: EUR {floor_price}/unit\n"
                    "Our Base Price: EUR {base_price}/unit\n\n"
                    "Rules:\n"
                    "- If target_price >= floor_price: ACCEPT. Set revised_price "
                    "to the target price.\n"
                    "- If target_price < floor_price: REJECT.\n"
                    "- If the customer is flexible on date and the target is close "
                    "to floor (within 5%), consider offering a slightly longer lead "
                    "time and accepting.\n\n"
                    "Respond with ONLY one of these JSON formats:\n\n"
                    "Accept:\n"
                    '{{"decision": "accept", "revised_price": <number>, '
                    '"revised_lead_time": <integer_or_null>, '
                    '"conditions": "<string>"}}\n\n'
                    "Reject:\n"
                    '{{"decision": "reject", "reason": "<explanation>"}}'
                ),
            ),
        ]
    )

    _counter_chain = counter_prompt | _llm | StrOutputParser()

    logger.info("LangChain chains initialised (model: %s)", OPENAI_MODEL)


# ═══════════════════════════════════════════════════════════════════════════
# LangChain invocation helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _langchain_quote(
    part: PartInfo,
    quantity: int,
    required_by: str,
    delivery_location: str,
    compliance: list[str],
) -> dict[str, Any] | None:
    """Generate a quote using the LangChain chain."""
    if _rfq_chain is None:
        return None

    discount = compute_volume_discount(quantity)
    discounted_price = round(part.base_price * (1 - discount), 2)

    inputs = {
        "part_name": part.part_name,
        "part_description": part.description,
        "quantity": quantity,
        "required_by": required_by or "not specified",
        "delivery_location": delivery_location or "not specified",
        "compliance": ", ".join(compliance) if compliance else "standard",
        "base_price": f"{part.base_price:.2f}",
        "stock_quantity": part.stock_quantity,
        "lead_time_days": part.lead_time_days,
        "floor_price": f"{part.floor_price:.2f}",
        "discount_pct": f"{discount * 100:.0f}",
        "discounted_price": f"{discounted_price:.2f}",
        "shipping_origin": part.shipping_origin,
        "certifications": ", ".join(part.certifications),
        "specs": json.dumps(part.specs),
    }

    try:
        raw_output: str = await asyncio.to_thread(_rfq_chain.invoke, inputs)
        logger.info("LangChain RFQ raw output: %s", raw_output[:500])
        parsed = _parse_json(raw_output)
        if parsed and "unit_price" in parsed:
            return parsed
        logger.warning("Could not parse JSON from LangChain RFQ output.")
    except Exception as exc:
        logger.warning("LangChain RFQ chain failed: %s", exc)

    return None


async def _langchain_counter(
    part: PartInfo,
    rfq_id: str,
    original_price: float,
    target_price: float,
    flexible_date: bool,
    justification: str,
) -> dict[str, Any] | None:
    """Evaluate a counter-offer using the LangChain chain."""
    if _counter_chain is None:
        return None

    inputs = {
        "part_name": part.part_name,
        "rfq_id": rfq_id,
        "original_price": f"{original_price:.2f}",
        "target_price": f"{target_price:.2f}",
        "flexible_date": str(flexible_date),
        "justification": justification or "No justification provided",
        "floor_price": f"{part.floor_price:.2f}",
        "base_price": f"{part.base_price:.2f}",
    }

    try:
        raw_output: str = await asyncio.to_thread(
            _counter_chain.invoke, inputs
        )
        logger.info("LangChain counter raw output: %s", raw_output[:500])
        parsed = _parse_json(raw_output)
        if parsed and "decision" in parsed:
            return parsed
        logger.warning(
            "Could not parse JSON from LangChain counter output."
        )
    except Exception as exc:
        logger.warning("LangChain counter chain failed: %s", exc)

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Deterministic fallback logic (used when LangChain / LLM is unavailable)
# ═══════════════════════════════════════════════════════════════════════════

def _deterministic_quote(part_name: str, quantity: int) -> dict[str, Any] | None:
    """Generate a quote using rule-based logic."""
    part = lookup_part("supplier_e", part_name)
    if part is None:
        return None

    discount = compute_volume_discount(quantity)
    unit_price = round(part.base_price * (1 - discount), 2)
    qty_available = min(quantity, part.stock_quantity)

    notes = "Deterministic pricing (LangChain fallback). "
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


def _deterministic_counter_eval(
    part_name: str,
    target_price: float,
) -> dict[str, Any]:
    """Evaluate a counter-offer deterministically."""
    result = evaluate_counter_offer("supplier_e", part_name, target_price)
    part = lookup_part("supplier_e", part_name)

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
# Parse JSON from LLM output
# ═══════════════════════════════════════════════════════════════════════════

def _parse_json(raw_output: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from an LLM output string."""
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
    label="Supplier E",
    description=(
        "Beverage supply chain specialist powered by LangChain. "
        "Provides packaging materials, ingredients (caffeine, taurine), "
        "bottling equipment, and distribution supplies for the beverage "
        "industry. Uses LangChain prompt-template → ChatOpenAI → output-parser "
        "chains for intelligent quote generation and counter-offer evaluation."
    ),
    version="1.0.0",
    framework="langchain",
    jurisdiction="EU",
    provider="Packaging & Ingredients Supply Co.",
    skills=[
        Skill(
            id="supply:labels_packaging",
            description=(
                "Waterproof product labels and packaging materials with food-safe adhesive"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=3,
        ),
        Skill(
            id="supply:caffeine_supply",
            description=(
                "Pharmaceutical grade caffeine powder, 99.9% purity, for beverage manufacturing"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=10,
        ),
        Skill(
            id="supply:taurine_supply",
            description=(
                "Pharmaceutical grade taurine powder, 99.5% purity, for energy drink formulations"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
            max_lead_time_days=10,
        ),
        Skill(
            id="supply:bottling_equipment",
            description=(
                "Automated bottling line equipment with capacity of 1000 bottles per hour"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=21,
        ),
        Skill(
            id="supply:distribution_supplies",
            description=(
                "Corrugated cardboard shipping boxes and pallets for product distribution"
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=2,
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
        Evaluation(evaluator="self", score=0.88, metric="reliability"),
        Evaluation(
            evaluator="industry_benchmark",
            score=0.85,
            metric="delivery_accuracy",
        ),
    ],
    certifications=[
        Certification(name="ISO 9001", issuer="TÜV Belgium"),
        Certification(name="FDA", issuer="FDA"),
        Certification(name="USP", issuer="USP"),
        Certification(name="ISO 22000", issuer="TÜV Belgium"),
        Certification(name="CE marking", issuer="EU Notified Body"),
    ],
    policies=[
        Policy(
            name="min_order_qty",
            description="Minimum order quantity varies by part",
            value={
                "labels_packaging": 5000,
                "caffeine_supply": 10,
                "taurine_supply": 10,
                "bottling_equipment": 1,
                "distribution_supplies": 50,
            },
        ),
        Policy(
            name="floor_price_policy",
            description=(
                "Floor prices: 85-90% of base price depending on part type"
            ),
            value={
                "labels_packaging": 0.90,
                "caffeine_supply": 0.85,
                "taurine_supply": 0.85,
                "bottling_equipment": 0.80,
                "distribution_supplies": 0.90,
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
                "LLM-powered: LangChain chain evaluates pricing context and "
                "generates nuanced responses. Falls back to deterministic "
                "rules if the LLM is unavailable."
            ),
            value="langchain_llm",
        ),
    ],
    reliability_score=0.88,
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
            "framework": "langchain",
            "port": PORT,
            "skills": [s.id for s in AGENT_FACTS.skills],
            "langchain_available": LANGCHAIN_AVAILABLE,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI application
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    logger.info("Supplier E (LangChain) starting on port %d …", PORT)
    _init_chains()
    await _register_with_index()
    await _emit_startup_event()
    logger.info(
        "Supplier E ready at %s  (LangChain: %s)",
        BASE_URL,
        "enabled" if LANGCHAIN_AVAILABLE and _llm is not None else "fallback-only",
    )
    yield
    logger.info("Supplier E shutting down.")


app = FastAPI(
    title="Supplier E — Packaging & Ingredients (LangChain)",
    description=(
        "LangChain-powered packaging and ingredients supplier agent with "
        "LLM-based quote generation and counter-offer evaluation."
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

    The LangChain chain generates a competitive quote using prompt-injected
    inventory context.  Falls back to rule-based logic if the LLM is
    unavailable.
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
    part_info = lookup_part("supplier_e", part_name)
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

    # --- Try LangChain chain ---
    quote_data: dict[str, Any] | None = None
    used_langchain = False

    if LANGCHAIN_AVAILABLE and _rfq_chain is not None:
        logger.info("Running LangChain quote chain for RFQ %s …", rfq_id)
        quote_data = await _langchain_quote(
            part_info, quantity, required_by, delivery_location, compliance
        )
        if quote_data is not None:
            used_langchain = True
            logger.info(
                "LangChain quote parsed: €%.2f/unit",
                quote_data["unit_price"],
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
            "method": "langchain" if used_langchain else "deterministic",
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
        "langchain" if used_langchain else "deterministic",
    )
    return response_env.model_dump(mode="json")


@app.post("/counter")
async def receive_counter_offer(envelope: Envelope):
    """Process a counter-offer → return REVISED_QUOTE or REJECT.

    The LangChain chain evaluates the target price against our floor and
    inventory context.  Falls back to deterministic floor-price rules if
    the LLM is unavailable.
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

    # --- Try LangChain ---
    decision: dict[str, Any] | None = None
    used_langchain = False

    part_info = lookup_part("supplier_e", part_name) if part_name else None

    if LANGCHAIN_AVAILABLE and _counter_chain is not None and part_info is not None:
        logger.info("Running LangChain counter-offer evaluation …")
        decision = await _langchain_counter(
            part_info,
            rfq_id,
            original_price,
            target_price,
            flexible_date,
            justification,
        )
        if decision is not None:
            used_langchain = True
            logger.info("LangChain decision: %s", decision.get("decision"))

    # --- Deterministic fallback ---
    if decision is None:
        if part_name:
            decision = _deterministic_counter_eval(part_name, target_price)
        else:
            decision = {
                "decision": "reject",
                "reason": f"Unknown RFQ {rfq_id} — no part on record.",
            }

    # If the date is flexible and we rejected, log that
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
            "decision": decision.get("decision", "reject"),
            "method": "langchain" if used_langchain else "deterministic",
        },
    )

    # --- Build response envelope ---
    if decision.get("decision") == "accept":
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
            "langchain" if used_langchain else "deterministic",
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
            "langchain" if used_langchain else "deterministic",
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
    part_info = lookup_part("supplier_e", part)
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
        "service": "supplier-e",
        "framework": "langchain",
        "agent_id": AGENT_ID,
        "langchain_available": LANGCHAIN_AVAILABLE,
        "llm_initialised": _llm is not None,
        "catalog_parts": list(SUPPLIER_E_CATALOG.keys()),
        "active_rfqs": len(_rfq_store),
        "confirmed_orders": len(_order_store),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "supplier_packaging:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
