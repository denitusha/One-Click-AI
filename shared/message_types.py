"""A2A (Agent-to-Agent) message protocol for the supply-chain network.

Every inter-agent message uses a common **Envelope** wrapper that carries
a typed payload.  Ten message types cover the full coordination cascade:

    RFQ -> QUOTE -> COUNTER_OFFER -> REVISED_QUOTE -> ACCEPT / REJECT -> ORDER
    LOGISTICS_REQUEST -> SHIP_PLAN

Plus a generic EVENT type used for dashboard/event-bus notifications.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Message type enum
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    """Discriminator for the payload carried inside an Envelope."""

    RFQ = "RFQ"
    QUOTE = "QUOTE"
    COUNTER_OFFER = "COUNTER_OFFER"
    REVISED_QUOTE = "REVISED_QUOTE"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ORDER = "ORDER"
    LOGISTICS_REQUEST = "LOGISTICS_REQUEST"
    SHIP_PLAN = "SHIP_PLAN"
    EVENT = "EVENT"  # generic event for the dashboard / event bus


# ---------------------------------------------------------------------------
# Common envelope
# ---------------------------------------------------------------------------

class Envelope(BaseModel):
    """Standard wrapper for every agent-to-agent message.

    ``correlation_id`` ties all messages in a single negotiation together
    (typically the original RFQ id).
    """

    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique message ID",
    )
    type: MessageType = Field(..., description="Payload type discriminator")
    from_agent: str = Field(..., description="Sender agent_id")
    to_agent: str = Field(..., description="Recipient agent_id")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Message creation time (UTC)",
    )
    correlation_id: str = Field(
        default="",
        description="Shared ID linking all messages in a negotiation (usually the RFQ id)",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific payload (see typed payload models below)",
    )


# ---------------------------------------------------------------------------
# Typed payload models
# ---------------------------------------------------------------------------

class RFQPayload(BaseModel):
    """Request For Quotation – sent by Procurement to Suppliers."""

    rfq_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique RFQ identifier",
    )
    part: str = Field(..., description="Part name / identifier being requested")
    quantity: int = Field(..., gt=0, description="Number of units required")
    required_by: str = Field(
        default="",
        description="Deadline date (ISO-8601 string, e.g. '2026-04-01')",
    )
    delivery_location: str = Field(default="", description="Delivery address or region")
    compliance_requirements: list[str] = Field(
        default_factory=list,
        description="Required certifications / standards (e.g. ['ISO 9001', 'REACH'])",
    )
    specs: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional technical specifications",
    )


class QuotePayload(BaseModel):
    """Supplier's price quote in response to an RFQ."""

    rfq_id: str = Field(..., description="The RFQ this quote responds to")
    unit_price: float = Field(..., gt=0, description="Price per unit")
    currency: str = Field(default="EUR", description="ISO 4217 currency code")
    qty_available: int = Field(..., ge=0, description="Units available in inventory")
    lead_time_days: int = Field(..., ge=0, description="Estimated lead time in days")
    shipping_origin: str = Field(default="", description="Where the goods ship from")
    certifications: list[str] = Field(
        default_factory=list,
        description="Certifications applicable to this part",
    )
    valid_until: str = Field(
        default="",
        description="Quote expiry (ISO-8601 string)",
    )
    notes: str = Field(default="", description="Free-text notes from the supplier")


class CounterOfferPayload(BaseModel):
    """Counter-offer from Procurement to a Supplier after reviewing a Quote."""

    rfq_id: str = Field(..., description="Original RFQ identifier")
    target_price: float = Field(..., gt=0, description="Desired unit price")
    flexible_date: bool = Field(
        default=False,
        description="Whether the delivery date is negotiable",
    )
    justification: str = Field(
        default="",
        description="Reason for the counter-offer (e.g. 'market benchmark is 10% lower')",
    )


class RevisedQuotePayload(BaseModel):
    """Supplier's revised quote after a counter-offer."""

    rfq_id: str = Field(..., description="Original RFQ identifier")
    revised_price: float = Field(..., gt=0, description="New unit price offered")
    revised_lead_time: int | None = Field(
        default=None,
        description="Optionally revised lead time in days",
    )
    conditions: str = Field(
        default="",
        description="Any conditions attached to the revised quote",
    )


class AcceptPayload(BaseModel):
    """Procurement accepts a quote and creates an order reference."""

    rfq_id: str = Field(..., description="Original RFQ identifier")
    order_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Generated order ID",
    )
    accepted_price: float = Field(..., gt=0, description="Agreed unit price")
    quantity: int = Field(..., gt=0, description="Agreed quantity")


class RejectPayload(BaseModel):
    """Procurement rejects a quote (or supplier rejects a counter-offer)."""

    rfq_id: str = Field(..., description="Original RFQ identifier")
    rejection_reason: str = Field(default="", description="Why the quote/counter was rejected")


class OrderPayload(BaseModel):
    """Confirmed order details sent to the winning supplier."""

    order_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique order ID",
    )
    rfq_id: str = Field(..., description="Original RFQ identifier")
    supplier_id: str = Field(..., description="Winning supplier agent_id")
    part: str = Field(..., description="Part being ordered")
    quantity: int = Field(..., gt=0, description="Units ordered")
    unit_price: float = Field(..., gt=0, description="Agreed unit price")
    currency: str = Field(default="EUR", description="ISO 4217 currency code")
    total_price: float = Field(default=0.0, description="quantity * unit_price")
    delivery_location: str = Field(default="", description="Delivery destination")
    required_by: str = Field(default="", description="Delivery deadline (ISO-8601)")
    shipping_origin: str = Field(default="", description="Where goods ship from")
    certifications: list[str] = Field(default_factory=list, description="Applicable certifications")
    notes: str = Field(default="", description="Additional order notes")


class LogisticsRequestPayload(BaseModel):
    """Request to the Logistics agent to plan a shipment."""

    order_id: str = Field(..., description="Order this shipment is for")
    pickup_location: str = Field(..., description="Pickup address / region")
    delivery_location: str = Field(..., description="Delivery address / region")
    cargo_description: str = Field(default="", description="What is being shipped")
    weight_kg: float = Field(default=0.0, description="Cargo weight in kilograms")
    volume_m3: float = Field(default=0.0, description="Cargo volume in cubic metres")
    required_by: str = Field(default="", description="Delivery deadline (ISO-8601)")
    priority: str = Field(
        default="standard",
        description="Shipping priority: 'standard' or 'express'",
    )


class ShipPlanPayload(BaseModel):
    """Shipping plan returned by the Logistics agent."""

    order_id: str = Field(..., description="Order this plan covers")
    route: list[str] = Field(
        default_factory=list,
        description="Ordered list of waypoints (e.g. ['Stuttgart', 'Munich', 'Vienna'])",
    )
    total_distance_km: float = Field(default=0.0, description="Total route distance in km")
    transit_time_days: int = Field(default=0, description="Estimated transit time in days")
    cost: float = Field(default=0.0, description="Shipping cost estimate")
    currency: str = Field(default="EUR", description="ISO 4217 currency code")
    carrier: str = Field(default="", description="Assigned carrier / logistics provider")
    mode: str = Field(
        default="road_freight",
        description="Transport mode (e.g. 'road_freight', 'express_delivery')",
    )
    estimated_arrival: str = Field(default="", description="Estimated arrival date (ISO-8601)")
    notes: str = Field(default="", description="Additional logistics notes")


# ---------------------------------------------------------------------------
# Event Bus event (dashboard-facing)
# ---------------------------------------------------------------------------

class EventPayload(BaseModel):
    """Generic event emitted to the Event Bus for dashboard consumption."""

    event_type: str = Field(
        ...,
        description=(
            "Event discriminator, e.g. 'AGENT_REGISTERED', 'RFQ_SENT', "
            "'QUOTE_RECEIVED', 'CASCADE_COMPLETE', etc."
        ),
    )
    agent_id: str = Field(..., description="Agent that generated this event")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event-specific data",
    )


# ---------------------------------------------------------------------------
# Helper: build an envelope
# ---------------------------------------------------------------------------

def make_envelope(
    msg_type: MessageType,
    from_agent: str,
    to_agent: str,
    payload: BaseModel | dict[str, Any],
    correlation_id: str = "",
) -> Envelope:
    """Convenience factory to create a properly populated Envelope."""
    payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
    return Envelope(
        type=msg_type,
        from_agent=from_agent,
        to_agent=to_agent,
        correlation_id=correlation_id,
        payload=payload_dict,
    )
