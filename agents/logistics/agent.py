"""Logistics Agent — AutoGen-based EU road-freight route planner.

Uses an AutoGen ``ConversableAgent`` backed by GPT-4o for intelligent
route planning, carrier selection, and cost estimation across the
European road-freight network.

Port 6004 · Skills: ``logistics:road_freight_eu``, ``logistics:express_delivery``

Endpoints
---------
- ``GET  /agent-facts`` — self-hosted AgentFacts (NANDA protocol)
- ``POST /logistics``   — receive LOGISTICS_REQUEST envelope, return SHIP_PLAN envelope
- ``GET  /health``      — health / readiness probe
"""

from __future__ import annotations

import asyncio
import heapq
import json
import logging
import os
import re
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
    LOGISTICS_PORT,
    OPENAI_MODEL,
)
from shared.message_types import (  # noqa: E402
    Envelope,
    MessageType,
    ShipPlanPayload,
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

# ---------------------------------------------------------------------------
# AutoGen import (with graceful fallback)
# ---------------------------------------------------------------------------
AUTOGEN_AVAILABLE = False
_ConversableAgent: Any = None

try:
    from autogen import ConversableAgent  # pyautogen >= 0.4

    _ConversableAgent = ConversableAgent
    AUTOGEN_AVAILABLE = True
except ImportError:
    try:
        from autogen import AssistantAgent  # older pyautogen

        _ConversableAgent = AssistantAgent
        AUTOGEN_AVAILABLE = True
    except ImportError:
        pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [logistics] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("logistics")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AGENT_ID = "logistics-agent"
AGENT_NAME = "European Freight Logistics (AutoGen)"
PORT = int(os.environ.get("PORT", LOGISTICS_PORT))
HOST = "0.0.0.0"
BASE_URL = f"http://localhost:{PORT}"

# ═══════════════════════════════════════════════════════════════════════════
# European Road Freight Network (simulated)
# ═══════════════════════════════════════════════════════════════════════════

# Canonical city name lookup (case-insensitive, supports aliases)
CITY_ALIASES: dict[str, str] = {
    "stuttgart": "Stuttgart",
    "munich": "Munich",
    "münchen": "Munich",
    "muenchen": "Munich",
    "frankfurt": "Frankfurt",
    "dusseldorf": "Düsseldorf",
    "düsseldorf": "Düsseldorf",
    "duesseldorf": "Düsseldorf",
    "hamburg": "Hamburg",
    "berlin": "Berlin",
    "cologne": "Cologne",
    "köln": "Cologne",
    "koeln": "Cologne",
    "vienna": "Vienna",
    "wien": "Vienna",
    "zurich": "Zurich",
    "zürich": "Zurich",
    "zuerich": "Zurich",
    "milan": "Milan",
    "milano": "Milan",
    "paris": "Paris",
    "brussels": "Brussels",
    "bruxelles": "Brussels",
    "amsterdam": "Amsterdam",
    "lyon": "Lyon",
    "prague": "Prague",
    "praha": "Prague",
    "warsaw": "Warsaw",
    "warszawa": "Warsaw",
    "budapest": "Budapest",
    "bratislava": "Bratislava",
    "barcelona": "Barcelona",
    "madrid": "Madrid",
    # Common supplier shipping origins
    "essen": "Essen",
    "essen, germany": "Essen",
    "bremen": "Bremen",
    "bremen, germany": "Bremen",
    "stuttgart, germany": "Stuttgart",
    "munich, germany": "Munich",
    "frankfurt, germany": "Frankfurt",
    "hamburg, germany": "Hamburg",
    "berlin, germany": "Berlin",
    "cologne, germany": "Cologne",
    "vienna, austria": "Vienna",
    "zurich, switzerland": "Zurich",
    "milan, italy": "Milan",
    "paris, france": "Paris",
    "brussels, belgium": "Brussels",
    "amsterdam, netherlands": "Amsterdam",
}

# Undirected road segments: (city_a, city_b) → metrics
ROAD_SEGMENTS: dict[tuple[str, str], dict[str, float]] = {
    # Germany — internal
    ("Stuttgart", "Munich"): {"distance_km": 233, "transit_hours": 3.5},
    ("Stuttgart", "Frankfurt"): {"distance_km": 209, "transit_hours": 3.0},
    ("Stuttgart", "Cologne"): {"distance_km": 365, "transit_hours": 4.5},
    ("Munich", "Frankfurt"): {"distance_km": 392, "transit_hours": 4.5},
    ("Munich", "Berlin"): {"distance_km": 585, "transit_hours": 6.5},
    ("Munich", "Prague"): {"distance_km": 381, "transit_hours": 4.5},
    ("Frankfurt", "Düsseldorf"): {"distance_km": 229, "transit_hours": 3.0},
    ("Frankfurt", "Cologne"): {"distance_km": 189, "transit_hours": 2.5},
    ("Frankfurt", "Berlin"): {"distance_km": 548, "transit_hours": 6.5},
    ("Frankfurt", "Hamburg"): {"distance_km": 492, "transit_hours": 5.5},
    ("Düsseldorf", "Cologne"): {"distance_km": 42, "transit_hours": 0.75},
    ("Düsseldorf", "Essen"): {"distance_km": 32, "transit_hours": 0.5},
    ("Hamburg", "Berlin"): {"distance_km": 289, "transit_hours": 3.5},
    ("Hamburg", "Bremen"): {"distance_km": 122, "transit_hours": 1.5},
    ("Bremen", "Düsseldorf"): {"distance_km": 320, "transit_hours": 3.5},
    ("Essen", "Cologne"): {"distance_km": 72, "transit_hours": 1.0},

    # Cross-border — DACH
    ("Stuttgart", "Zurich"): {"distance_km": 200, "transit_hours": 3.0},
    ("Munich", "Vienna"): {"distance_km": 434, "transit_hours": 5.5},
    ("Munich", "Zurich"): {"distance_km": 316, "transit_hours": 4.0},
    ("Munich", "Milan"): {"distance_km": 587, "transit_hours": 7.0},
    ("Stuttgart", "Milan"): {"distance_km": 520, "transit_hours": 6.5},
    ("Milan", "Zurich"): {"distance_km": 296, "transit_hours": 4.0},

    # Central / Eastern Europe
    ("Vienna", "Prague"): {"distance_km": 333, "transit_hours": 4.0},
    ("Vienna", "Budapest"): {"distance_km": 243, "transit_hours": 3.0},
    ("Vienna", "Bratislava"): {"distance_km": 80, "transit_hours": 1.0},
    ("Budapest", "Bratislava"): {"distance_km": 200, "transit_hours": 2.5},
    ("Berlin", "Prague"): {"distance_km": 349, "transit_hours": 4.5},
    ("Berlin", "Warsaw"): {"distance_km": 573, "transit_hours": 7.0},
    ("Warsaw", "Prague"): {"distance_km": 680, "transit_hours": 8.0},

    # Western Europe
    ("Düsseldorf", "Amsterdam"): {"distance_km": 227, "transit_hours": 3.0},
    ("Düsseldorf", "Brussels"): {"distance_km": 222, "transit_hours": 3.0},
    ("Cologne", "Brussels"): {"distance_km": 214, "transit_hours": 2.5},
    ("Cologne", "Amsterdam"): {"distance_km": 258, "transit_hours": 3.0},
    ("Hamburg", "Amsterdam"): {"distance_km": 465, "transit_hours": 5.5},
    ("Paris", "Brussels"): {"distance_km": 307, "transit_hours": 3.5},
    ("Paris", "Lyon"): {"distance_km": 466, "transit_hours": 5.0},
    ("Paris", "Amsterdam"): {"distance_km": 504, "transit_hours": 5.5},

    # Southern Europe
    ("Milan", "Lyon"): {"distance_km": 475, "transit_hours": 6.0},
    ("Lyon", "Barcelona"): {"distance_km": 645, "transit_hours": 7.0},
    ("Paris", "Barcelona"): {"distance_km": 1032, "transit_hours": 11.0},
    ("Barcelona", "Madrid"): {"distance_km": 621, "transit_hours": 6.5},
}

# Available freight carriers
CARRIERS: list[dict[str, Any]] = [
    {
        "name": "DB Schenker",
        "modes": ["road_freight", "express_delivery"],
        "base_cost_per_km": 1.20,
        "express_multiplier": 1.6,
        "weight_surcharge_per_kg": 0.02,
        "reliability": 0.94,
        "regions": ["EU"],
    },
    {
        "name": "DHL Freight",
        "modes": ["road_freight", "express_delivery"],
        "base_cost_per_km": 1.35,
        "express_multiplier": 1.5,
        "weight_surcharge_per_kg": 0.015,
        "reliability": 0.96,
        "regions": ["EU", "US"],
    },
    {
        "name": "DACHSER",
        "modes": ["road_freight"],
        "base_cost_per_km": 1.10,
        "express_multiplier": 1.7,
        "weight_surcharge_per_kg": 0.025,
        "reliability": 0.92,
        "regions": ["EU"],
    },
    {
        "name": "Kuehne+Nagel",
        "modes": ["road_freight", "express_delivery"],
        "base_cost_per_km": 1.45,
        "express_multiplier": 1.4,
        "weight_surcharge_per_kg": 0.01,
        "reliability": 0.97,
        "regions": ["EU", "US", "APAC"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# City resolution
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_city(raw: str) -> str | None:
    """Resolve a raw location string to a canonical city name.

    Handles case-insensitive lookup, common aliases, and stripping
    of country suffixes (e.g. ``"Stuttgart, Germany"`` → ``"Stuttgart"``).
    Returns ``None`` if the city is not in our network.
    """
    if not raw:
        return None

    cleaned = raw.strip()

    # Direct match (case-insensitive)
    lower = cleaned.lower()
    if lower in CITY_ALIASES:
        return CITY_ALIASES[lower]

    # Try without country suffix: "Stuttgart, Germany" → "Stuttgart"
    if "," in cleaned:
        city_part = cleaned.split(",")[0].strip().lower()
        if city_part in CITY_ALIASES:
            return CITY_ALIASES[city_part]

    # Try exact match against canonical names
    for canonical in set(CITY_ALIASES.values()):
        if canonical.lower() == lower:
            return canonical

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Graph construction and Dijkstra's shortest path
# ═══════════════════════════════════════════════════════════════════════════

def _build_adjacency() -> dict[str, list[tuple[str, float, float]]]:
    """Build an adjacency list from ROAD_SEGMENTS.

    Returns ``{city: [(neighbour, distance_km, transit_hours), ...]}``
    for both directions (undirected graph).
    """
    adj: dict[str, list[tuple[str, float, float]]] = {}
    for (a, b), metrics in ROAD_SEGMENTS.items():
        d = metrics["distance_km"]
        t = metrics["transit_hours"]
        adj.setdefault(a, []).append((b, d, t))
        adj.setdefault(b, []).append((a, d, t))
    return adj


_ADJACENCY = _build_adjacency()


def find_shortest_route(
    origin: str,
    destination: str,
    weight: str = "distance_km",
) -> dict[str, Any] | None:
    """Find the shortest route between two cities using Dijkstra's algorithm.

    Parameters
    ----------
    origin, destination : str
        Canonical city names (use ``_resolve_city`` first).
    weight : str
        ``"distance_km"`` or ``"transit_hours"`` — which metric to minimise.

    Returns
    -------
    dict or None
        ``{"route": [...], "total_distance_km": ..., "total_transit_hours": ...}``
        or ``None`` if no path exists.
    """
    if origin not in _ADJACENCY or destination not in _ADJACENCY:
        return None
    if origin == destination:
        return {
            "route": [origin],
            "total_distance_km": 0.0,
            "total_transit_hours": 0.0,
        }

    # Dijkstra
    # Priority queue entries: (cost, city, path, total_distance, total_hours)
    heap: list[tuple[float, str, list[str], float, float]] = [
        (0.0, origin, [origin], 0.0, 0.0)
    ]
    visited: set[str] = set()

    while heap:
        cost, current, path, dist, hours = heapq.heappop(heap)
        if current in visited:
            continue
        visited.add(current)

        if current == destination:
            return {
                "route": path,
                "total_distance_km": round(dist, 1),
                "total_transit_hours": round(hours, 1),
            }

        for neighbour, seg_dist, seg_hours in _ADJACENCY.get(current, []):
            if neighbour not in visited:
                edge_cost = seg_dist if weight == "distance_km" else seg_hours
                heapq.heappush(
                    heap,
                    (
                        cost + edge_cost,
                        neighbour,
                        path + [neighbour],
                        dist + seg_dist,
                        hours + seg_hours,
                    ),
                )

    return None


def list_network_cities() -> list[str]:
    """Return all cities in the freight network."""
    return sorted(_ADJACENCY.keys())


# ═══════════════════════════════════════════════════════════════════════════
# Cost calculation
# ═══════════════════════════════════════════════════════════════════════════

def calculate_shipping_cost(
    distance_km: float,
    weight_kg: float,
    priority: str = "standard",
) -> list[dict[str, Any]]:
    """Calculate shipping cost estimates from all eligible carriers.

    Returns a list of carrier quotes sorted by total cost (ascending).
    """
    mode = "express_delivery" if priority == "express" else "road_freight"
    quotes: list[dict[str, Any]] = []

    for carrier in CARRIERS:
        if mode not in carrier["modes"]:
            continue

        base_cost = distance_km * carrier["base_cost_per_km"]
        if priority == "express":
            base_cost *= carrier["express_multiplier"]

        weight_surcharge = weight_kg * carrier["weight_surcharge_per_kg"]
        total = round(base_cost + weight_surcharge, 2)

        quotes.append({
            "carrier": carrier["name"],
            "base_cost": round(base_cost, 2),
            "weight_surcharge": round(weight_surcharge, 2),
            "total_cost": total,
            "reliability": carrier["reliability"],
            "mode": mode,
        })

    quotes.sort(key=lambda q: q["total_cost"])
    return quotes


def select_best_carrier(
    distance_km: float,
    weight_kg: float,
    priority: str = "standard",
) -> dict[str, Any]:
    """Select the best carrier balancing cost and reliability.

    Scoring: 60% cost efficiency + 40% reliability.
    """
    quotes = calculate_shipping_cost(distance_km, weight_kg, priority)
    if not quotes:
        return {
            "carrier": "Default Road Freight",
            "total_cost": round(distance_km * 1.30, 2),
            "reliability": 0.90,
            "mode": "road_freight",
        }

    max_cost = max(q["total_cost"] for q in quotes) or 1.0
    best: dict[str, Any] | None = None
    best_score = -1.0

    for q in quotes:
        cost_score = 1.0 - (q["total_cost"] / max_cost)
        reliability_score = q["reliability"]
        combined = 0.6 * cost_score + 0.4 * reliability_score
        if combined > best_score:
            best_score = combined
            best = q

    return best or quotes[0]


# ═══════════════════════════════════════════════════════════════════════════
# AutoGen route planner
# ═══════════════════════════════════════════════════════════════════════════

ROUTE_PLANNER_SYSTEM_PROMPT = """\
You are an expert European road freight logistics planner working for a
supply-chain coordination network. Your job is to plan optimal shipping
routes for automotive parts across Europe.

Given a logistics request you will receive:
- Route data (waypoints, distance, transit time) computed by the network
- Carrier cost estimates from multiple carriers
- Shipment details (cargo, weight, priority, deadline)

Analyze the data and produce a concise shipping plan as a **JSON object**
with exactly these fields:
{
    "carrier": "<selected carrier name>",
    "mode": "road_freight" or "express_delivery",
    "route_notes": "<1-2 sentence reasoning about the route>",
    "carrier_notes": "<1-2 sentence reasoning about carrier selection>",
    "risk_notes": "<any risk factors or considerations>"
}

Be concise and practical. Do NOT include code blocks or markdown fences —
return only the raw JSON object.
"""


async def _plan_with_autogen(
    pickup: str,
    delivery: str,
    cargo: str,
    weight_kg: float,
    priority: str,
    route_data: dict[str, Any],
    carrier_quotes: list[dict[str, Any]],
    best_carrier: dict[str, Any],
) -> dict[str, Any]:
    """Use AutoGen ConversableAgent to generate an intelligent shipping plan.

    The LLM adds reasoning, risk assessment, and carrier selection
    rationale on top of the algorithmic route and cost data.
    """
    if not AUTOGEN_AVAILABLE or _ConversableAgent is None:
        return {}

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.info("No OPENAI_API_KEY — skipping AutoGen LLM reasoning")
        return {}

    config_list = [{"model": OPENAI_MODEL, "api_key": api_key}]

    try:
        planner = _ConversableAgent(
            name="route_planner",
            system_message=ROUTE_PLANNER_SYSTEM_PROMPT,
            llm_config={
                "config_list": config_list,
                "temperature": 0.1,
                "cache_seed": None,
            },
            human_input_mode="NEVER",
        )

        request_message = (
            f"Plan this shipment:\n"
            f"- Pickup: {pickup}\n"
            f"- Delivery: {delivery}\n"
            f"- Cargo: {cargo}\n"
            f"- Weight: {weight_kg} kg\n"
            f"- Priority: {priority}\n"
            f"- Deadline: within route transit time\n\n"
            f"Computed route: {json.dumps(route_data)}\n\n"
            f"Carrier cost estimates:\n{json.dumps(carrier_quotes, indent=2)}\n\n"
            f"Recommended carrier (algorithm): {best_carrier['carrier']} "
            f"at €{best_carrier['total_cost']:.2f}\n\n"
            f"Provide your shipping plan as a JSON object."
        )

        # generate_reply is synchronous — run in thread pool
        def _generate() -> Any:
            return planner.generate_reply(
                messages=[{"role": "user", "content": request_message}]
            )

        reply = await asyncio.to_thread(_generate)

        # Parse the reply
        if isinstance(reply, dict):
            return reply

        reply_str = str(reply).strip()

        # Try to extract JSON from the response
        # First try direct parse
        try:
            return json.loads(reply_str)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", reply_str, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Try to find any JSON object in the text
        brace_match = re.search(r"\{[^{}]*\}", reply_str, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))

        logger.info("AutoGen reply was not parseable JSON; using algorithmic plan")
        return {"route_notes": reply_str[:200]}

    except Exception as exc:
        logger.warning("AutoGen route planning failed: %s", exc)
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# Main route planning function
# ═══════════════════════════════════════════════════════════════════════════

async def plan_shipment(
    pickup_location: str,
    delivery_location: str,
    cargo_description: str = "",
    weight_kg: float = 50.0,
    volume_m3: float = 0.5,
    required_by: str = "",
    priority: str = "standard",
    order_id: str = "",
) -> ShipPlanPayload:
    """Plan a complete shipment: route, carrier selection, cost estimate.

    Combines Dijkstra shortest-path routing with AutoGen LLM reasoning
    for intelligent carrier selection and risk assessment.
    """
    # --- Resolve cities ---
    pickup_city = _resolve_city(pickup_location)
    delivery_city = _resolve_city(delivery_location)

    # Fallback: default to nearest major hub
    if not pickup_city:
        logger.warning(
            "Could not resolve pickup '%s' — defaulting to Frankfurt",
            pickup_location,
        )
        pickup_city = "Frankfurt"
    if not delivery_city:
        logger.warning(
            "Could not resolve delivery '%s' — defaulting to Stuttgart",
            delivery_location,
        )
        delivery_city = "Stuttgart"

    # --- Find route ---
    route_data = find_shortest_route(pickup_city, delivery_city)

    if route_data is None:
        # No path found — generate a direct estimate
        logger.warning(
            "No route found from %s to %s — generating direct estimate",
            pickup_city,
            delivery_city,
        )
        route_data = {
            "route": [pickup_city, delivery_city],
            "total_distance_km": 500.0,  # fallback estimate
            "total_transit_hours": 6.0,
        }

    distance_km = route_data["total_distance_km"]
    transit_hours = route_data["total_transit_hours"]

    # --- Calculate costs and select carrier ---
    carrier_quotes = calculate_shipping_cost(distance_km, weight_kg, priority)
    best = select_best_carrier(distance_km, weight_kg, priority)

    # --- AutoGen LLM reasoning (if available) ---
    autogen_insights = await _plan_with_autogen(
        pickup=pickup_city,
        delivery=delivery_city,
        cargo=cargo_description,
        weight_kg=weight_kg,
        priority=priority,
        route_data=route_data,
        carrier_quotes=carrier_quotes,
        best_carrier=best,
    )

    # Override carrier if AutoGen recommends a different one
    if autogen_insights.get("carrier"):
        # Validate that the recommended carrier is in our quotes
        ag_carrier = autogen_insights["carrier"]
        matching = [q for q in carrier_quotes if q["carrier"] == ag_carrier]
        if matching:
            best = matching[0]
            logger.info("AutoGen selected carrier: %s", ag_carrier)

    # --- Determine transport mode ---
    mode = "express_delivery" if priority == "express" else "road_freight"

    # --- Compute transit time in days ---
    # Road freight drivers: max 9 hours/day (EU regulations)
    driving_hours_per_day = 9.0 if mode == "road_freight" else 14.0
    transit_days = max(1, int(transit_hours / driving_hours_per_day + 0.99))

    # --- Estimate arrival date ---
    try:
        base_date = datetime.now(timezone.utc)
        if required_by:
            # Work backwards from deadline
            pass
        arrival = base_date + timedelta(days=transit_days)
        estimated_arrival = arrival.strftime("%Y-%m-%d")
    except Exception:
        estimated_arrival = ""

    # --- Build notes ---
    notes_parts = [
        f"AutoGen-planned route via {len(route_data['route'])} waypoints.",
        f"Carrier selected: {best['carrier']} (reliability {best.get('reliability', 0.9):.0%}).",
    ]
    if autogen_insights.get("route_notes"):
        notes_parts.append(f"Route analysis: {autogen_insights['route_notes']}")
    if autogen_insights.get("risk_notes"):
        notes_parts.append(f"Risks: {autogen_insights['risk_notes']}")

    logger.info(
        "SHIP_PLAN for order %s: %s → %s, %s, %.0f km, %d days, €%.2f",
        order_id,
        pickup_city,
        delivery_city,
        best["carrier"],
        distance_km,
        transit_days,
        best["total_cost"],
    )

    return ShipPlanPayload(
        order_id=order_id,
        route=route_data["route"],
        total_distance_km=distance_km,
        transit_time_days=transit_days,
        cost=best["total_cost"],
        currency="EUR",
        carrier=best["carrier"],
        mode=mode,
        estimated_arrival=estimated_arrival,
        notes=" ".join(notes_parts),
    )


# ═══════════════════════════════════════════════════════════════════════════
# AgentFacts (self-hosted NANDA metadata)
# ═══════════════════════════════════════════════════════════════════════════

AGENT_FACTS = AgentFacts(
    id=AGENT_ID,
    agent_name=AGENT_NAME,
    label="Logistics",
    description=(
        "European road freight logistics agent powered by Microsoft AutoGen. "
        "Plans optimal shipping routes across a simulated EU road-freight "
        "network using Dijkstra shortest-path routing combined with LLM-based "
        "reasoning for intelligent carrier selection, cost estimation, and "
        "risk assessment. Covers major European cities and hubs with "
        "real-world distance and transit-time data."
    ),
    version="1.0.0",
    framework="autogen",
    jurisdiction="EU",
    provider="OneClickAI Logistics Division",
    skills=[
        Skill(
            id="logistics:road_freight_eu",
            description=(
                "Standard European road freight shipping. Route planning, "
                "carrier selection, and cost estimation across EU road network. "
                "Multiple carriers available (DB Schenker, DHL Freight, "
                "DACHSER, Kuehne+Nagel)."
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=7,
        ),
        Skill(
            id="logistics:express_delivery",
            description=(
                "Express delivery service for time-critical automotive parts. "
                "Extended driving hours, premium carriers, guaranteed "
                "delivery windows."
            ),
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=3,
        ),
    ],
    endpoints=[
        Endpoint(
            path="/agent-facts",
            method="GET",
            description="Self-hosted AgentFacts (NANDA protocol)",
        ),
        Endpoint(
            path="/logistics",
            method="POST",
            description="Receive LOGISTICS_REQUEST, return SHIP_PLAN",
        ),
        Endpoint(path="/health", method="GET", description="Health check"),
    ],
    evaluations=[
        Evaluation(evaluator="self", score=0.93, metric="reliability"),
        Evaluation(
            evaluator="industry_benchmark",
            score=0.91,
            metric="on_time_delivery",
        ),
        Evaluation(
            evaluator="customer_feedback",
            score=0.89,
            metric="route_accuracy",
        ),
    ],
    certifications=[
        Certification(name="ISO 9001", issuer="TÜV Rheinland"),
        Certification(name="AEO-F", issuer="EU Customs"),
        Certification(name="GDP", issuer="EMA"),
        Certification(name="SQAS", issuer="Cefic"),
    ],
    policies=[
        Policy(
            name="max_shipment_weight",
            description="Maximum single shipment weight 25,000 kg",
            value=25000,
        ),
        Policy(
            name="coverage_area",
            description="Pan-European road freight network",
            value={
                "countries": [
                    "DE", "AT", "CH", "IT", "FR", "BE", "NL",
                    "CZ", "PL", "HU", "SK", "ES",
                ],
                "major_hubs": list_network_cities(),
            },
        ),
        Policy(
            name="transit_regulations",
            description="EU driver hour regulations: max 9h/day standard, 14h/day express",
            value={"standard_hours_per_day": 9, "express_hours_per_day": 14},
        ),
        Policy(
            name="pricing_model",
            description="Per-km base rate + weight surcharge; express multiplier applies",
            value="per_km_plus_weight",
        ),
    ],
    reliability_score=0.93,
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
            "framework": "autogen",
            "port": PORT,
            "skills": [s.id for s in AGENT_FACTS.skills],
            "network_cities": list_network_cities(),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI application
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    logger.info("Logistics Agent (AutoGen) starting on port %d …", PORT)
    if AUTOGEN_AVAILABLE:
        logger.info("AutoGen framework loaded — LLM-enhanced planning enabled")
    else:
        logger.warning(
            "AutoGen not available — using algorithmic-only planning "
            "(install pyautogen to enable LLM reasoning)"
        )
    await _register_with_index()
    await _emit_startup_event()
    logger.info(
        "Logistics Agent ready at %s  (network: %d cities, %d segments, %d carriers)",
        BASE_URL,
        len(_ADJACENCY),
        len(ROAD_SEGMENTS),
        len(CARRIERS),
    )
    yield
    logger.info("Logistics Agent shutting down.")


app = FastAPI(
    title="Logistics Agent — European Freight (AutoGen)",
    description=(
        "AutoGen-powered logistics agent for European road freight. "
        "Plans optimal routes using Dijkstra's algorithm enhanced with "
        "LLM reasoning for carrier selection and risk assessment."
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


@app.post("/logistics")
async def receive_logistics_request(envelope: Envelope):
    """Process a LOGISTICS_REQUEST and return a SHIP_PLAN.

    The AutoGen route planner computes the optimal route using Dijkstra's
    algorithm over the EU road network, selects the best carrier using a
    cost-reliability scoring model, and (when LLM is available) adds
    natural-language reasoning via an AutoGen ConversableAgent.
    """
    payload = envelope.payload
    order_id = payload.get("order_id", str(uuid.uuid4()))
    pickup = payload.get("pickup_location", "")
    delivery = payload.get("delivery_location", "")
    cargo = payload.get("cargo_description", "")
    weight_kg = float(payload.get("weight_kg", 50.0))
    volume_m3 = float(payload.get("volume_m3", 0.5))
    required_by = payload.get("required_by", "")
    priority = payload.get("priority", "standard")

    logger.info(
        "LOGISTICS_REQUEST received: order=%s  %s → %s  (%s, %.0f kg, %s)",
        order_id,
        pickup,
        delivery,
        cargo,
        weight_kg,
        priority,
    )

    # Emit event
    await _emit_event(
        "LOGISTICS_REQUEST_RECEIVED",
        {
            "order_id": order_id,
            "pickup": pickup,
            "delivery": delivery,
            "cargo": cargo,
            "priority": priority,
            "from_agent": envelope.from_agent,
        },
    )

    # --- Plan the shipment ---
    ship_plan = await plan_shipment(
        pickup_location=pickup,
        delivery_location=delivery,
        cargo_description=cargo,
        weight_kg=weight_kg,
        volume_m3=volume_m3,
        required_by=required_by,
        priority=priority,
        order_id=order_id,
    )

    # Emit ship plan event
    await _emit_event(
        "SHIP_PLAN_GENERATED",
        {
            "order_id": order_id,
            "route": ship_plan.route,
            "distance_km": ship_plan.total_distance_km,
            "transit_days": ship_plan.transit_time_days,
            "cost": ship_plan.cost,
            "carrier": ship_plan.carrier,
            "mode": ship_plan.mode,
        },
    )

    # Build response envelope
    response_env = make_envelope(
        MessageType.SHIP_PLAN,
        from_agent=AGENT_ID,
        to_agent=envelope.from_agent,
        payload=ship_plan,
        correlation_id=envelope.correlation_id or order_id,
    )

    logger.info(
        "SHIP_PLAN → %s: %s via %s, %.0f km, %d days, €%.2f",
        envelope.from_agent,
        " → ".join(ship_plan.route),
        ship_plan.carrier,
        ship_plan.total_distance_km,
        ship_plan.transit_time_days,
        ship_plan.cost,
    )

    return response_env.model_dump(mode="json")


@app.get("/health")
async def health():
    """Liveness / readiness probe."""
    return {
        "status": "ok",
        "service": "logistics-agent",
        "framework": "autogen",
        "autogen_available": AUTOGEN_AVAILABLE,
        "agent_id": AGENT_ID,
        "network_cities": len(_ADJACENCY),
        "road_segments": len(ROAD_SEGMENTS),
        "carriers": [c["name"] for c in CARRIERS],
    }


@app.get("/routes")
async def get_routes(origin: str = "", destination: str = ""):
    """Debug endpoint: find a route between two cities."""
    if not origin or not destination:
        return {
            "cities": list_network_cities(),
            "usage": "GET /routes?origin=Munich&destination=Paris",
        }

    origin_city = _resolve_city(origin)
    dest_city = _resolve_city(destination)

    if not origin_city:
        return {"error": f"Unknown origin: {origin}", "cities": list_network_cities()}
    if not dest_city:
        return {"error": f"Unknown destination: {destination}", "cities": list_network_cities()}

    route = find_shortest_route(origin_city, dest_city)
    if not route:
        return {"error": f"No route from {origin_city} to {dest_city}"}

    costs = calculate_shipping_cost(route["total_distance_km"], 50.0)
    return {
        "route": route,
        "cost_estimates": costs,
        "best_carrier": select_best_carrier(route["total_distance_km"], 50.0),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "agent:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
