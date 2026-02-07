"""Logistics Agent logic — AutoGen-based route planning and cost estimation."""

from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI

from shared.config import LLM_MODEL, OPENAI_API_KEY

# ---------------------------------------------------------------------------
# Route database (simulated)
# ---------------------------------------------------------------------------

ROUTES: dict[str, dict[str, Any]] = {
    "Stuttgart-Maranello-road": {
        "route": ["Stuttgart", "Munich", "Brenner Pass", "Verona", "Maranello"],
        "transport_mode": "road",
        "estimated_days": 3,
        "cost_per_kg": 0.45,
        "carrier": "DHL Freight",
    },
    "Stuttgart-Maranello-rail": {
        "route": ["Stuttgart", "Basel", "Milan", "Bologna", "Maranello"],
        "transport_mode": "rail",
        "estimated_days": 5,
        "cost_per_kg": 0.30,
        "carrier": "DB Cargo / Trenitalia Freight",
    },
    "Stuttgart-Maranello-multimodal": {
        "route": ["Stuttgart", "Munich", "Innsbruck", "Verona", "Maranello"],
        "transport_mode": "multimodal",
        "estimated_days": 4,
        "cost_per_kg": 0.38,
        "carrier": "Kuehne+Nagel",
    },
}


def get_llm():
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0.3)


async def plan_route(request: dict) -> dict:
    """Plan optimal route for a shipping request."""
    weight_kg = request.get("weight_kg", 1000)
    origin = request.get("origin", "Stuttgart, Germany")
    destination = request.get("destination", "Maranello, Italy")
    required_date = request.get("required_delivery_date")

    # Calculate costs for each route option
    options = []
    for key, route_data in ROUTES.items():
        cost = round(weight_kg * route_data["cost_per_kg"], 2)
        options.append({
            **route_data,
            "total_cost": cost,
            "route_key": key,
        })

    # Use LLM to pick best route
    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are a logistics planner. Choose the best shipping route.\n"
        f"Origin: {origin}\nDestination: {destination}\n"
        f"Weight: {weight_kg}kg\nRequired by: {required_date}\n"
        f"Options:\n{json.dumps(options, indent=2)}\n\n"
        f"Consider speed, cost, and reliability. "
        f"Respond with ONLY JSON: {{\"chosen_route_key\": \"<key>\", \"reason\": \"<why>\"}}"
    )

    try:
        decision = json.loads(resp.content)
        chosen_key = decision.get("chosen_route_key", "Stuttgart-Maranello-road")
        reason = decision.get("reason", "Best balance of speed and cost")
    except Exception:
        chosen_key = "Stuttgart-Maranello-road"
        reason = "Fastest route selected (LLM fallback)"

    chosen = ROUTES.get(chosen_key, list(ROUTES.values())[0])
    total_cost = round(weight_kg * chosen["cost_per_kg"], 2)

    return {
        "order_id": request.get("order_id", ""),
        "route": chosen["route"],
        "transport_mode": chosen["transport_mode"],
        "estimated_days": chosen["estimated_days"],
        "cost": total_cost,
        "carrier": chosen["carrier"],
        "notes": reason,
    }
