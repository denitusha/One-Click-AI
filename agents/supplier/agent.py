"""Supplier Agent logic — AutoGen-based inventory management and quoting.

This demonstrates cross-framework interoperability: the Supplier (AutoGen)
receives HTTP/JSON requests from the Procurement Agent (LangGraph).
"""

from __future__ import annotations

import json
import random
from typing import Any

from langchain_openai import ChatOpenAI

from shared.config import LLM_MODEL, OPENAI_API_KEY

# ---------------------------------------------------------------------------
# Simulated inventory
# ---------------------------------------------------------------------------

INVENTORY: dict[str, dict[str, Any]] = {
    "ENG-001": {"name": "V12 Engine Block", "stock": 5, "unit_price": 45000, "lead_days": 21},
    "ENG-002": {"name": "Turbocharger Assembly", "stock": 12, "unit_price": 8500, "lead_days": 14},
    "CHS-001": {"name": "Carbon Fiber Monocoque Chassis", "stock": 3, "unit_price": 62000, "lead_days": 35},
    "CHS-002": {"name": "Suspension System", "stock": 20, "unit_price": 4200, "lead_days": 10},
    "ELC-001": {"name": "ECU (Engine Control Unit)", "stock": 15, "unit_price": 3800, "lead_days": 7},
    "ELC-002": {"name": "Infotainment Display", "stock": 10, "unit_price": 2200, "lead_days": 12},
    "TIR-001": {"name": "Pirelli P Zero Tires", "stock": 40, "unit_price": 850, "lead_days": 5},
    "BRK-001": {"name": "Carbon Ceramic Brake Discs", "stock": 16, "unit_price": 3200, "lead_days": 14},
    "INT-001": {"name": "Leather Interior Kit", "stock": 6, "unit_price": 18000, "lead_days": 28},
    "BDY-001": {"name": "Aluminum Body Panels", "stock": 4, "unit_price": 25000, "lead_days": 30},
}


def get_llm():
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0.3)


async def process_rfq(rfq: dict, supplier_id: str) -> dict:
    """Evaluate an RFQ and return a quote based on inventory."""
    components = rfq.get("components", [])
    unit_prices: dict[str, float] = {}
    total = 0.0
    max_lead = 0
    all_available = True

    for comp in components:
        cid = comp.get("component_id", "")
        qty = comp.get("quantity", 1)
        inv = INVENTORY.get(cid)
        if inv and inv["stock"] >= qty:
            price = inv["unit_price"] * qty
            unit_prices[cid] = inv["unit_price"]
            total += price
            max_lead = max(max_lead, inv["lead_days"])
        else:
            all_available = False
            # Offer with longer lead time (need to source)
            if inv:
                unit_prices[cid] = inv["unit_price"] * 1.15  # 15% premium
                total += inv["unit_price"] * 1.15 * qty
                max_lead = max(max_lead, inv["lead_days"] + 14)
            else:
                unit_prices[cid] = 0
                all_available = False

    # Use LLM to add reasoning
    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are supplier '{supplier_id}'. You received an RFQ for {len(components)} components. "
        f"Total quoted price: ${total:,.0f}. Lead time: {max_lead} days. All in stock: {all_available}. "
        f"Write a 1-sentence professional note about this quote."
    )
    notes = resp.content.strip()

    return {
        "supplier_id": supplier_id,
        "components": components,
        "unit_prices": unit_prices,
        "total_price": round(total, 2),
        "lead_time_days": max_lead,
        "available": all_available,
        "notes": notes,
    }


async def process_negotiation(proposal: dict, supplier_id: str) -> dict:
    """Evaluate a negotiation proposal and respond."""
    proposed_price = proposal.get("proposed_price", 0)
    conditions = proposal.get("conditions", "")

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are supplier '{supplier_id}'. A buyer proposes ${proposed_price:,.0f}. "
        f"Conditions: {conditions}. "
        f"You can accept if the discount is ≤ 8%, counter with 5% if they want more, "
        f"or reject if > 15%. Respond with ONLY JSON: "
        f'{{"accepted": <bool>, "proposed_price": <float>, "conditions": "<your response>"}}'
    )

    try:
        decision = json.loads(resp.content)
    except Exception:
        # Fallback: accept with 5% discount
        decision = {
            "accepted": True,
            "proposed_price": proposed_price * 1.05,
            "conditions": "Counter-offer: 5% discount from list price accepted.",
        }

    decision["supplier_id"] = supplier_id
    return decision
