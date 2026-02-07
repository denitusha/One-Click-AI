"""NANDA-compliant AgentAddr and AgentFacts models.

Architecture follows the NANDA paper's three-level design:
  1. AgentAddr  — lean index record (~120 bytes), stored in the registry
  2. AgentFacts — rich metadata document (1-3 KB), self-hosted by each agent
  3. Resolution — two-step: registry returns AgentAddr → client fetches AgentFacts
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    PROCUREMENT = "procurement"
    SUPPLIER = "supplier"
    MANUFACTURER = "manufacturer"
    LOGISTICS = "logistics"
    COMPLIANCE = "compliance"


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: AgentAddr — Lean Index Record (stored in registry)
# Analogous to a DNS record; ~120 bytes per entry
# Fields: agent_id, agent_name (URN), primary_facts_url, private_facts_url,
#         adaptive_resolver_url, ttl, signature
# ═══════════════════════════════════════════════════════════════════════════

class AgentAddr(BaseModel):
    """Lean index record returned by the NANDA registry.

    This is the ONLY object the registry stores per agent. It contains
    pointers to the agent's AgentFacts (rich metadata), NOT the facts themselves.
    """

    agent_id: str = Field(
        ..., description="Globally unique agent identifier (e.g. nanda:550e8400-...)"
    )
    agent_name: str = Field(
        ...,
        description="Human-readable URN (e.g. urn:agent:salesforce:TranslationAssistant)",
    )
    primary_facts_url: str = Field(
        ...,
        description="URL where the agent hosts its own AgentFacts (e.g. https://host/.well-known/agent-facts)",
    )
    private_facts_url: Optional[str] = Field(
        default=None,
        description="Privacy-preserving AgentFacts URL hosted by a third party",
    )
    adaptive_resolver_url: Optional[str] = Field(
        default=None,
        description="Optional dynamic routing endpoint for load balancing / geo-dispatch",
    )
    ttl: int = Field(
        default=3600,
        description="Cache time-to-live in seconds before re-resolution",
    )
    signature: str = Field(
        default="",
        description="Ed25519 signature binding all fields of this AgentAddr",
    )
    registered_at: Optional[str] = Field(default=None)
    # Hierarchical resolution: which authoritative name server owns this agent
    authoritative_ns: Optional[str] = Field(
        default=None,
        description="URL of the authoritative name server for this agent's zone",
    )
    zone: Optional[str] = Field(
        default=None,
        description="Name-space zone this agent belongs to (e.g. 'oneclickai:supplier')",
    )


# ═══════════════════════════════════════════════════════════════════════════
# REQUESTER CONTEXT — sent alongside resolution queries per Adaptive Resolver paper
# ═══════════════════════════════════════════════════════════════════════════

class RequesterContext(BaseModel):
    """Context metadata a requester sends during adaptive resolution.

    Per the Adaptive Resolver paper, the resolver uses this to return
    *tailored* endpoints — different requesters may get different URLs.
    """

    requester_id: Optional[str] = Field(default=None, description="ID of the requesting agent")
    geo_location: Optional[str] = Field(default=None, description="Geographic location (e.g. 'Maranello, Italy')")
    geo_lat: Optional[float] = Field(default=None, description="Latitude")
    geo_lon: Optional[float] = Field(default=None, description="Longitude")
    network_cidr: Optional[str] = Field(default=None, description="Requester's topological address (CIDR)")
    qos_requirements: Optional[dict[str, Any]] = Field(
        default=None,
        description="QoS needs: max_latency_ms, min_bandwidth_mbps, priority",
    )
    security_level: Optional[str] = Field(
        default=None, description="Required security tier: public, authenticated, encrypted, zero-trust",
    )
    cost_budget: Optional[float] = Field(default=None, description="Max cost constraint for this session")
    session_type: Optional[str] = Field(
        default=None, description="Expected interaction pattern: request-response, streaming, long-session, batch",
    )


class TailoredResponse(BaseModel):
    """Tailored resolution response — the endpoint may differ per requester context."""

    agent_id: str
    agent_name: str
    endpoint: str = Field(..., description="Tailored endpoint URL for this specific requester")
    transport: str = Field(default="https", description="Protocol: https, wss, grpc, mqtt")
    ttl: int = Field(default=300, description="TTL for this tailored endpoint")
    context_used: dict[str, Any] = Field(default_factory=dict, description="Which context influenced the tailoring")
    negotiation_required: bool = Field(default=False, description="Whether further negotiation is needed")
    negotiation_url: Optional[str] = Field(default=None, description="URL to begin negotiation if required")
    comms_spec: Optional[dict[str, Any]] = Field(default=None, description="Agreed communication specification")
    signature: str = Field(default="")


class NegotiationInvitation(BaseModel):
    """Returned by authoritative NS when trust or QoS negotiation is required."""

    agent_id: str
    negotiation_url: str = Field(..., description="URL to begin the negotiation process")
    reason: str = Field(default="", description="Why negotiation is required")
    required_context: list[str] = Field(
        default_factory=list,
        description="Additional context fields the target needs (e.g. 'geo_location', 'security_level')",
    )
    trust_requirements: dict[str, Any] = Field(default_factory=dict)
    ttl: int = Field(default=60)


# ═══════════════════════════════════════════════════════════════════════════
# AGENT DEPLOYMENT RECORD — physical resource metadata per Adaptive Resolver paper
# ═══════════════════════════════════════════════════════════════════════════

class DeploymentResource(BaseModel):
    """A physical resource where agent components are deployed."""

    resource_id: str
    resource_type: str = Field(description="datacenter, edge, mobile, embedded")
    geo_location: str = ""
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    hardware: list[str] = Field(default_factory=list, description="e.g. gpu, high-memory, ssd")
    bandwidth_mbps: Optional[float] = None
    region: str = ""


class AgentDeploymentRecord(BaseModel):
    """Describes how an agent instance is physically deployed.

    Per the paper: 'metadata about how its instance is deployed and what
    physical resources it owns and where the resources are located.'
    This is stored at the authoritative name server level.
    """

    agent_id: str
    resources: list[DeploymentResource] = Field(default_factory=list)
    deployment_mode: str = Field(
        default="single-origin",
        description="single-origin, multi-region, edge-distributed, serverless",
    )
    mobility: bool = Field(default=False, description="Whether agent state can migrate")
    max_concurrent_sessions: int = Field(default=100)
    current_load: float = Field(default=0.0, ge=0.0, le=1.0, description="Current load 0.0-1.0")


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2: AgentFacts — Rich Metadata Document (self-hosted by agent)
# Matches the NANDA paper's Appendix schema with all fields marked 🔵 and 🟢
# ═══════════════════════════════════════════════════════════════════════════

class ProviderInfo(BaseModel):
    """Provider / organisation details."""
    name: str
    url: Optional[str] = None
    did: Optional[str] = None  # Optional DID for provider verification


class EndpointConfig(BaseModel):
    """Multi-endpoint configuration per NANDA spec."""
    static: list[str] = Field(default_factory=list, description="Stable endpoint URIs")
    rotating: list[str] = Field(default_factory=list, description="Short-TTL dynamic URIs")
    adaptive_resolver: Optional[str] = Field(
        default=None, description="Programmable routing microservice URL"
    )
    adaptive_resolver_policies: list[str] = Field(
        default_factory=list, description="Routing policies (e.g. geo, load, threat-shield)"
    )


class AgentSkill(BaseModel):
    """Structured skill definition per NANDA/A2A schema."""
    id: str
    description: str = ""
    input_modes: list[str] = Field(default_factory=list)
    output_modes: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    latency_budget_ms: Optional[int] = None
    max_tokens: Optional[int] = None


class AgentCapabilities(BaseModel):
    """Technical capabilities block."""
    modalities: list[str] = Field(default_factory=list, description="e.g. text, audio, structured_data")
    streaming: bool = False
    batch: bool = False
    authentication: dict[str, Any] = Field(
        default_factory=lambda: {"methods": ["api_key"], "required_scopes": []},
    )


class AgentEvaluations(BaseModel):
    """Quality metrics and audit trail."""
    performance_score: Optional[float] = Field(default=None, ge=0, le=5)
    availability_90d: Optional[str] = None  # e.g. "99.93%"
    last_audited: Optional[str] = None  # ISO datetime
    audit_trail: Optional[str] = None  # e.g. IPFS CID
    auditor_id: Optional[str] = None


class AgentTelemetry(BaseModel):
    """Observability configuration."""
    enabled: bool = False
    retention: str = "7d"
    sampling: float = 0.1
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentCertification(BaseModel):
    """Certification and trust framework per NANDA spec."""
    level: str = "self-declared"  # self-declared | verified | audited
    issuer: str = ""
    issuance_date: Optional[str] = None
    expiration_date: Optional[str] = None
    credential_type: str = "W3C-VC-v2"  # Per paper: W3C Verifiable Credential v2
    policies: list[str] = Field(default_factory=list)
    revocation_url: Optional[str] = None  # VC-Status-List endpoint


class AgentFacts(BaseModel):
    """NANDA-compliant AgentFacts — the rich metadata document self-hosted by each agent.

    This matches the paper's Appendix schema. It is served at each agent's
    /.well-known/agent-facts endpoint and signed as a W3C Verifiable Credential.
    """

    # ── Identity & Basic Info ─────────────────────────────────────────────
    id: str = Field(..., description="Unique machine-readable ID (e.g. nanda:550e8400-...)")
    agent_name: str = Field(..., description="URN identifier (e.g. urn:agent:company:AgentName)")
    label: str = Field(..., description="Human-readable display name")
    description: str = Field(default="", description="Agent description")
    version: str = Field(default="1.0.0", description="Agent version")
    documentation_url: Optional[str] = Field(default=None)
    jurisdiction: str = Field(default="global", description="Compliance jurisdiction (EU, US, global)")

    # ── Provider ──────────────────────────────────────────────────────────
    provider: ProviderInfo

    # ── Network Endpoints ─────────────────────────────────────────────────
    endpoints: EndpointConfig

    # ── Role & Framework (supply-chain specific extensions) ───────────────
    role: AgentRole = Field(..., description="Supply-chain role")
    framework: str = Field(default="custom", description="Agent framework (langgraph, autogen, custom)")

    # ── Technical Capabilities ────────────────────────────────────────────
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)

    # ── Functional Skills ─────────────────────────────────────────────────
    skills: list[AgentSkill] = Field(default_factory=list)

    # ── Quality Metrics ───────────────────────────────────────────────────
    evaluations: AgentEvaluations = Field(default_factory=AgentEvaluations)

    # ── Observability ─────────────────────────────────────────────────────
    telemetry: AgentTelemetry = Field(default_factory=AgentTelemetry)

    # ── Trust & Certification ─────────────────────────────────────────────
    certification: AgentCertification = Field(default_factory=AgentCertification)

    # ── Context Requirements (Adaptive Resolver paper) ──────────────────
    context_requirements: list[str] = Field(
        default_factory=list,
        description="Context fields this agent requires from requesters for resolution "
                    "(e.g. 'geo_location', 'security_level', 'network_cidr')",
    )
    deployment: Optional[AgentDeploymentRecord] = Field(
        default=None,
        description="Physical deployment metadata for adaptive routing",
    )

    # ── Signature (signed by agent's key) ─────────────────────────────────
    signature: str = Field(default="", description="Cryptographic signature over the AgentFacts document")
    facts_ttl: int = Field(default=3600, description="TTL in seconds for caching this AgentFacts")

    # ── Legacy compat helpers ─────────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        """Backwards-compat alias for id."""
        return self.id

    @property
    def name(self) -> str:
        """Backwards-compat alias for label."""
        return self.label

    @property
    def endpoint(self) -> str:
        """Return the first static endpoint (backwards compat)."""
        return self.endpoints.static[0] if self.endpoints.static else ""

    @property
    def reputation_score(self) -> float:
        """Derive reputation from evaluations."""
        score = self.evaluations.performance_score
        return (score / 5.0) if score else 1.0
