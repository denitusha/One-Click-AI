"""Core data models for the NANDA agent network (Pydantic v2).

Models
------
- **AgentAddr** – ~120-byte lean record stored in the NANDA Index.
- **Skill** – A capability an agent advertises (e.g. ``supply:carbon_fiber_panels``).
- **Evaluation** – Trust / quality evaluation result.
- **Certification** – Industry or compliance certification.
- **Policy** – Agent-level policy declaration.
- **AgentFacts** – Full rich metadata per the NANDA paper, self-hosted at ``/agent-facts``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# AgentAddr – lean pointer stored in the NANDA Index
# ---------------------------------------------------------------------------

class AgentAddr(BaseModel):
    """Minimal record kept in the NANDA Lean Index (~120 bytes).

    Contains just enough to *find* an agent and fetch its full AgentFacts.
    """

    agent_id: str = Field(..., description="Unique agent identifier (UUID or slug)")
    agent_name: str = Field(..., description="Human-readable agent name")
    facts_url: str = Field(
        ...,
        description="URL where the agent self-hosts its full AgentFacts (GET /agent-facts)",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Compact skill IDs for index-level search (e.g. 'supply:titanium_alloy')",
    )
    region: str | None = Field(
        default=None,
        description="ISO region tag for geographic filtering (e.g. 'EU', 'US')",
    )
    ttl: int = Field(
        default=3600,
        description="Time-to-live in seconds before the record is considered stale",
    )
    registered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of last registration / heartbeat",
    )
    signature: str | None = Field(
        default=None,
        description="Optional cryptographic signature for ZTAA verification",
    )


# ---------------------------------------------------------------------------
# Sub-models used inside AgentFacts
# ---------------------------------------------------------------------------

class Skill(BaseModel):
    """A single advertised capability of an agent."""

    id: str = Field(..., description="Namespaced skill ID, e.g. 'supply:carbon_fiber_panels'")
    description: str = Field(default="", description="Human-readable description of the skill")
    input_modes: list[str] = Field(
        default_factory=list,
        description="Accepted input modes/formats (e.g. 'application/json')",
    )
    output_modes: list[str] = Field(
        default_factory=list,
        description="Produced output modes/formats",
    )
    supported_regions: list[str] = Field(
        default_factory=list,
        description="Regions where this skill is available (e.g. ['EU', 'US'])",
    )
    max_lead_time_days: int | None = Field(
        default=None,
        description="Maximum lead time in days for this skill, if applicable",
    )


class Evaluation(BaseModel):
    """Trust or quality evaluation record."""

    evaluator: str = Field(..., description="Who performed the evaluation")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalised score 0-1")
    metric: str = Field(default="overall", description="What was evaluated (e.g. 'reliability')")
    evaluated_at: datetime | None = Field(default=None, description="When the evaluation happened")
    details: dict[str, Any] = Field(default_factory=dict, description="Extra evaluation metadata")


class Certification(BaseModel):
    """Industry / compliance certification."""

    name: str = Field(..., description="Certification name (e.g. 'ISO 9001', 'IATF 16949')")
    issuer: str = Field(default="", description="Issuing body")
    valid_until: datetime | None = Field(default=None, description="Expiry date")
    document_url: str | None = Field(default=None, description="Link to certificate document")


class Policy(BaseModel):
    """Agent-level policy declaration (pricing, data handling, etc.)."""

    name: str = Field(..., description="Policy name (e.g. 'min_order_qty')")
    description: str = Field(default="", description="Human-readable policy description")
    value: Any = Field(default=None, description="Policy value (type depends on policy)")


class Endpoint(BaseModel):
    """A single endpoint the agent exposes."""

    path: str = Field(..., description="URL path (e.g. '/rfq')")
    method: str = Field(default="POST", description="HTTP method")
    description: str = Field(default="", description="What this endpoint does")


# ---------------------------------------------------------------------------
# AgentFacts – full rich metadata, self-hosted by each agent
# ---------------------------------------------------------------------------

class AgentFacts(BaseModel):
    """Full agent metadata per the NANDA paper.

    Each agent self-hosts this at ``GET /agent-facts``.  The procurement
    agent fetches it after discovering an ``AgentAddr`` via the Index.
    """

    id: str = Field(..., description="Same as AgentAddr.agent_id")
    agent_name: str = Field(..., description="Human-readable agent name")
    label: str = Field(default="", description="Short label for UI display")
    description: str = Field(default="", description="Detailed description of agent purpose")
    version: str = Field(default="1.0.0", description="Agent software version")
    framework: str = Field(
        default="custom",
        description="AI framework powering this agent (e.g. 'crewai', 'langchain', 'autogen', 'langgraph', 'custom')",
    )
    jurisdiction: str = Field(default="EU", description="Legal jurisdiction the agent operates under")
    provider: str = Field(default="", description="Organisation / team that runs the agent")

    # Capabilities
    skills: list[Skill] = Field(default_factory=list, description="List of advertised skills")
    endpoints: list[Endpoint] = Field(default_factory=list, description="HTTP endpoints the agent exposes")

    # Trust & compliance
    evaluations: list[Evaluation] = Field(default_factory=list, description="Trust / quality evaluations")
    certifications: list[Certification] = Field(default_factory=list, description="Industry certifications")
    policies: list[Policy] = Field(default_factory=list, description="Agent-level policies")

    # Operational
    reliability_score: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Self-reported reliability score (0-1)",
    )
    esg_rating: str = Field(default="A", description="ESG rating (A-F or custom scale)")
    base_url: str = Field(default="", description="Root URL of the agent's HTTP server")

    # Metadata
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra metadata")
