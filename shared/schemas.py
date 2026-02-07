"""MCP-style message schemas for inter-agent coordination."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Base envelope
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    REQUEST_FOR_QUOTE = "request_for_quote"
    QUOTE_RESPONSE = "quote_response"
    NEGOTIATION_PROPOSAL = "negotiation_proposal"
    ORDER_PLACEMENT = "order_placement"
    ORDER_CONFIRMATION = "order_confirmation"
    SHIPPING_REQUEST = "shipping_request"
    ROUTE_CONFIRMATION = "route_confirmation"
    COMPLIANCE_CHECK = "compliance_check"
    COMPLIANCE_RESULT = "compliance_result"
    INTENT = "intent"
    DISCOVERY_REQUEST = "discovery_request"
    DISCOVERY_RESPONSE = "discovery_response"
    STATUS_UPDATE = "status_update"
    ERROR = "error"


class AgentMessage(BaseModel):
    """Universal envelope for all inter-agent messages."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sender_id: str
    receiver_id: str
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = Field(
        default=None,
        description="Links related messages in a conversation / cascade",
    )
    explanation: str = Field(
        default="",
        description="Human-readable reasoning behind this message",
    )


# ---------------------------------------------------------------------------
# Payload schemas
# ---------------------------------------------------------------------------

class ComponentSpec(BaseModel):
    """Single component in a Bill of Materials."""

    component_id: str
    name: str
    category: str
    quantity: int = 1
    specifications: dict[str, Any] = Field(default_factory=dict)


class RequestForQuote(BaseModel):
    """Payload for RFQ messages."""

    components: list[ComponentSpec]
    required_by: Optional[str] = None  # ISO date string
    max_budget: Optional[float] = None
    preferred_jurisdiction: Optional[str] = None


class QuoteResponse(BaseModel):
    """Payload returned by a supplier in response to an RFQ."""

    supplier_id: str
    components: list[ComponentSpec]
    unit_prices: dict[str, float]  # component_id -> price
    total_price: float
    lead_time_days: int
    available: bool = True
    notes: str = ""


class NegotiationProposal(BaseModel):
    """Counter-offer during price / lead-time negotiation."""

    proposed_price: Optional[float] = None
    proposed_lead_time_days: Optional[int] = None
    conditions: str = ""
    accepted: Optional[bool] = None  # None = still negotiating


class OrderPlacement(BaseModel):
    """Confirmed order after negotiation."""

    order_id: str = Field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8]}")
    supplier_id: str
    components: list[ComponentSpec]
    agreed_price: float
    agreed_lead_time_days: int
    delivery_address: str = "Maranello, Italy"


class OrderConfirmation(BaseModel):
    """Supplier / manufacturer acknowledges an order."""

    order_id: str
    confirmed: bool
    estimated_completion: Optional[str] = None
    notes: str = ""


class ShippingRequest(BaseModel):
    """Request from manufacturer to logistics provider."""

    order_id: str
    origin: str
    destination: str
    weight_kg: float = 0.0
    volume_cbm: float = 0.0
    required_delivery_date: Optional[str] = None
    cargo_description: str = ""


class RouteConfirmation(BaseModel):
    """Logistics agent confirms shipping route."""

    order_id: str
    route: list[str]  # list of waypoints
    transport_mode: str  # sea, air, road, rail, multimodal
    estimated_days: int
    cost: float
    carrier: str = ""
    notes: str = ""


class ComplianceCheck(BaseModel):
    """Request to validate regulatory / policy compliance."""

    order_id: str
    supplier_id: str
    origin_jurisdiction: str
    destination_jurisdiction: str
    components: list[ComponentSpec]
    policies_to_check: list[str] = Field(default_factory=list)


class ComplianceResult(BaseModel):
    """Result of a compliance check."""

    order_id: str
    compliant: bool
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    checked_policies: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Coordination report
# ---------------------------------------------------------------------------

class CoordinationStep(BaseModel):
    """Single step in the coordination cascade log."""

    step_number: int
    timestamp: str
    from_agent: str
    to_agent: str
    action: str
    message_type: MessageType
    explanation: str
    duration_ms: Optional[int] = None


class NetworkCoordinationReport(BaseModel):
    """Full report generated at the end of a coordination cascade."""

    report_id: str = Field(default_factory=lambda: f"RPT-{uuid.uuid4().hex[:8]}")
    intent: str
    started_at: str
    completed_at: Optional[str] = None
    cascade_steps: list[CoordinationStep] = Field(default_factory=list)
    discovery_paths: list[dict[str, Any]] = Field(default_factory=list)
    trust_verification: list[dict[str, Any]] = Field(default_factory=list)
    policy_enforcement: list[dict[str, Any]] = Field(default_factory=list)
    final_execution_plan: dict[str, Any] = Field(default_factory=dict)
    total_cost: float = 0.0
    total_lead_time_days: int = 0
    status: str = "pending"
