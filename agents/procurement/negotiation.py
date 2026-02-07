"""Negotiation logic for the Procurement Agent.

Handles supplier scoring, counter-offer generation, and winner selection.

Scoring weights (per the plan):
    price         30%
    lead_time     25%
    reliability   20%
    ESG           15%
    proximity     10%
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("procurement.negotiation")

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

WEIGHTS = {
    "price": 0.30,
    "lead_time": 0.25,
    "reliability": 0.20,
    "esg": 0.15,
    "proximity": 0.10,
}

# ---------------------------------------------------------------------------
# ESG mapping  (letter → 0-1 score)
# ---------------------------------------------------------------------------

ESG_SCORES: dict[str, float] = {
    "A+": 1.0,
    "A": 0.9,
    "A-": 0.85,
    "B+": 0.8,
    "B": 0.7,
    "B-": 0.65,
    "C+": 0.6,
    "C": 0.5,
    "D": 0.3,
    "F": 0.1,
}

# Proximity score based on same-region match
PROXIMITY_SAME_REGION = 1.0
PROXIMITY_DIFF_REGION = 0.4

# Counter-offer discount percentage
COUNTER_OFFER_DISCOUNT = 0.10  # 10% below quoted price


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SupplierQuote:
    """Parsed supplier quote with associated metadata from AgentFacts."""

    supplier_id: str
    supplier_name: str
    framework: str = ""
    rfq_id: str = ""
    part: str = ""
    unit_price: float = 0.0
    currency: str = "EUR"
    qty_available: int = 0
    lead_time_days: int = 0
    shipping_origin: str = ""
    certifications: list[str] = field(default_factory=list)
    # From AgentFacts
    reliability_score: float = 0.9
    esg_rating: str = "A"
    region: str = "EU"
    # Computed
    score: float = 0.0


@dataclass
class NegotiationResult:
    """Result of negotiation for a single part."""

    part: str
    rfq_id: str
    quotes: list[SupplierQuote] = field(default_factory=list)
    counter_offer_sent: bool = False
    counter_offer_to: str = ""
    revised_quote: SupplierQuote | None = None
    winner: SupplierQuote | None = None
    accepted: bool = False
    order_id: str = ""


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_quote(
    quote: SupplierQuote,
    max_price: float,
    max_lead_time: int,
    delivery_region: str = "EU",
) -> float:
    """Compute a normalised 0-1 score for a supplier quote.

    Higher is better. Each dimension is normalised so that the *best*
    value in the comparison set maps to 1.0.

    Parameters
    ----------
    quote : SupplierQuote
        The quote to score.
    max_price : float
        Maximum price across all quotes for this part (for normalisation).
    max_lead_time : int
        Maximum lead time across all quotes (for normalisation).
    delivery_region : str
        Region where delivery is needed (for proximity scoring).
    """
    # Price: lower is better → invert
    price_score = 1.0 - (quote.unit_price / max_price) if max_price > 0 else 0.5

    # Lead time: lower is better → invert
    lt_score = 1.0 - (quote.lead_time_days / max_lead_time) if max_lead_time > 0 else 0.5

    # Reliability: direct
    rel_score = quote.reliability_score

    # ESG: map letter to number
    esg_score = ESG_SCORES.get(quote.esg_rating, 0.5)

    # Proximity: binary same-region check
    prox_score = (
        PROXIMITY_SAME_REGION
        if quote.region.upper() == delivery_region.upper()
        else PROXIMITY_DIFF_REGION
    )

    total = (
        WEIGHTS["price"] * price_score
        + WEIGHTS["lead_time"] * lt_score
        + WEIGHTS["reliability"] * rel_score
        + WEIGHTS["esg"] * esg_score
        + WEIGHTS["proximity"] * prox_score
    )

    logger.debug(
        "Score %s: price=%.2f lt=%.2f rel=%.2f esg=%.2f prox=%.2f → %.3f",
        quote.supplier_id,
        price_score,
        lt_score,
        rel_score,
        esg_score,
        prox_score,
        total,
    )
    return round(total, 4)


def rank_quotes(
    quotes: list[SupplierQuote],
    delivery_region: str = "EU",
) -> list[SupplierQuote]:
    """Score and rank a list of quotes for the same part. Returns sorted (best first)."""
    if not quotes:
        return []

    max_price = max(q.unit_price for q in quotes) if quotes else 1.0
    max_lead = max(q.lead_time_days for q in quotes) if quotes else 1

    for q in quotes:
        q.score = score_quote(q, max_price, max_lead, delivery_region)

    ranked = sorted(quotes, key=lambda q: q.score, reverse=True)
    logger.info(
        "Ranked %d quotes for part '%s': %s",
        len(ranked),
        ranked[0].part if ranked else "?",
        [(q.supplier_id, f"{q.score:.3f}") for q in ranked],
    )
    return ranked


# ---------------------------------------------------------------------------
# Counter-offer logic
# ---------------------------------------------------------------------------

def generate_counter_offer(
    top_quote: SupplierQuote,
    discount: float = COUNTER_OFFER_DISCOUNT,
) -> dict[str, Any]:
    """Generate a counter-offer payload for the best-ranked supplier.

    Offers a price ``discount`` (default 10%) below the quoted price.
    """
    target_price = max(0.01, round(top_quote.unit_price * (1.0 - discount), 2))
    counter = {
        "rfq_id": top_quote.rfq_id,
        "target_price": target_price,
        "flexible_date": True,
        "justification": (
            f"Market benchmark analysis suggests {discount*100:.0f}% below your quoted "
            f"€{top_quote.unit_price:.2f}. We propose €{target_price:.2f}/unit "
            f"for a confirmed order of {top_quote.qty_available}+ units."
        ),
    }
    logger.info(
        "Counter-offer for %s: €%.2f → €%.2f (-%s%%)",
        top_quote.supplier_id,
        top_quote.unit_price,
        target_price,
        f"{discount*100:.0f}",
    )
    return counter


# ---------------------------------------------------------------------------
# Winner selection
# ---------------------------------------------------------------------------

def select_winner(result: NegotiationResult) -> SupplierQuote | None:
    """Select the winning supplier for a part negotiation.

    If a revised quote was received (from counter-offer), compare it against
    the original top quote's score. Otherwise, use the top-ranked quote.
    """
    ranked = rank_quotes(result.quotes)
    if not ranked:
        logger.warning("No quotes to select winner for part '%s'", result.part)
        return None

    top = ranked[0]

    # If we have a revised quote from counter-offer negotiation, check if it's better
    if result.revised_quote is not None:
        revised = result.revised_quote
        # Re-score the revised quote with updated price
        max_price = max(q.unit_price for q in ranked)
        max_lead = max(q.lead_time_days for q in ranked)
        revised.score = score_quote(revised, max_price, max_lead)

        if revised.score >= top.score or revised.unit_price < top.unit_price:
            logger.info(
                "Winner for '%s': %s (revised quote, €%.2f, score=%.3f)",
                result.part,
                revised.supplier_id,
                revised.unit_price,
                revised.score,
            )
            return revised

    logger.info(
        "Winner for '%s': %s (€%.2f, score=%.3f)",
        result.part,
        top.supplier_id,
        top.unit_price,
        top.score,
    )
    return top


def build_execution_summary(
    results: list[NegotiationResult],
) -> dict[str, Any]:
    """Build a summary of all negotiation results for the execution report."""
    total_cost = 0.0
    suppliers_engaged: set[str] = set()
    parts_ordered = 0

    orders: list[dict[str, Any]] = []
    for r in results:
        for q in r.quotes:
            suppliers_engaged.add(q.supplier_id)
        if r.winner and r.accepted:
            parts_ordered += 1
            order_cost = r.winner.unit_price * r.winner.qty_available
            total_cost += order_cost
            orders.append({
                "part": r.part,
                "supplier": r.winner.supplier_id,
                "supplier_name": r.winner.supplier_name,
                "framework": r.winner.framework,
                "unit_price": r.winner.unit_price,
                "quantity": r.winner.qty_available,
                "total": round(order_cost, 2),
                "lead_time_days": r.winner.lead_time_days,
                "score": r.winner.score,
                "order_id": r.order_id,
            })

    return {
        "total_cost": round(total_cost, 2),
        "currency": "EUR",
        "parts_ordered": parts_ordered,
        "suppliers_engaged": len(suppliers_engaged),
        "supplier_list": sorted(suppliers_engaged),
        "orders": orders,
    }
