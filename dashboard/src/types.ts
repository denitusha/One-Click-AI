/* ────────────────────────────────────────────────────────────
   Types matching the Python backend schemas / event bus events
   ──────────────────────────────────────────────────────────── */

/** Event coming from the WebSocket event bus. */
export interface AgentEvent {
  event_type: string;
  agent_id: string;
  timestamp: string;
  data: Record<string, unknown>;
  run_id?: string;
}

/** History payload sent on WS connect. */
export interface HistoryMessage {
  type: "HISTORY";
  events: AgentEvent[];
}

/** Keep-alive messages. */
export interface PingPong {
  type: "PING" | "PONG";
}

/** All possible WS messages. */
export type WSMessage = HistoryMessage | PingPong | AgentEvent;

/* ── Agent metadata ──────────────────────────────────────── */

export interface AgentAddr {
  agent_id: string;
  agent_name: string;
  facts_url: string;
  skills: string[];
  region: string | null;
  ttl: number;
  registered_at: string;
  signature: string | null;
}

export interface AgentFacts {
  id: string;
  agent_name: string;
  label: string;
  description: string;
  framework: string;
  jurisdiction: string;
  provider: string;
  skills: Skill[];
  reliability_score: number;
  esg_rating: string;
  base_url: string;
}

export interface Skill {
  id: string;
  description: string;
  supported_regions: string[];
  max_lead_time_days: number | null;
}

/* ── Graph types ─────────────────────────────────────────── */

export type AgentRole = "procurement" | "supplier" | "logistics" | "index";

export interface GraphNode {
  id: string;
  label: string;
  role: AgentRole;
  framework?: string;
  skills?: string[];
  reliabilityScore?: number;
  esgRating?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  edgeType: "discovery" | "rfq" | "quote" | "counter" | "accept" | "order" | "logistics" | "contract";
  animated?: boolean;
}

/* ── Graph view / drill-down types ───────────────────────── */

export type GraphViewMode = "overview" | "agent-detail" | "order-detail" | "logistics-detail";

export interface GraphSelection {
  mode: GraphViewMode;
  agentId?: string;       // for agent-detail
  partName?: string;      // for order-detail (filter edges by part)
  supplierId?: string;    // for order-detail
  shipPlanIndex?: number; // for logistics-detail
}

export interface AggregatedEdge {
  id: string;
  source: string;
  target: string;
  counts: Record<string, number>; // edgeType -> count
  totalMessages: number;
}

/* ── Message log ─────────────────────────────────────────── */

export interface MessageLogEntry {
  id: string;
  timestamp: string;
  event_type: string;
  agent_id: string;
  from?: string;
  to?: string;
  summary: string;
  color: string;
}

/* ── Timeline phase ──────────────────────────────────────── */

export type PhaseStatus = "pending" | "active" | "completed";

export interface TimelinePhase {
  id: string;
  label: string;
  status: PhaseStatus;
  startedAt?: string;
  completedAt?: string;
}

/* ── Execution plan ──────────────────────────────────────── */

export interface OrderDetail {
  orderId: string;
  supplier: string;
  supplierName: string;
  part: string;
  quantity: number;
  unitPrice: number;
  totalPrice: number;
  currency: string;
  leadTimeDays: number | null;
  timestamp: string;
}

export interface ShipPlanDetail {
  orderId: string;
  route: string[];
  transitTimeDays: number | null;
  cost: number | null;
  pickup: string;
  delivery: string;
  estimatedArrival: string;
  timestamp: string;
}

export interface NegotiationRound {
  part: string;
  supplier: string;
  supplierName: string;
  rfqPrice: number | null;
  quotedPrice: number | null;
  counterPrice: number | null;
  revisedPrice: number | null;
  accepted: boolean;
  rejected: boolean;
  rejectionReason?: string;
}

export interface ExecutionPlan {
  totalCost: number;
  currency: string;
  partsCount: number;
  suppliersEngaged: number;
  ordersPlaced: number;
  shippingPlans: number;
  estimatedDelivery: string;
  orders: OrderDetail[];
  shipPlans: ShipPlanDetail[];
  negotiations: NegotiationRound[];
  report?: Record<string, unknown>;
}

/* ── Analytics overlay modes ─────────────────────────────── */

export type AnalyticsMode = "none" | "risk" | "cost" | "bottleneck";

/* ── Message filter types ────────────────────────────────── */

export type MessageFilterCategory =
  | "all"
  | "registration"
  | "discovery"
  | "verification"
  | "negotiation"
  | "orders"
  | "logistics"
  | "system";

export const MESSAGE_FILTER_CATEGORIES: Record<MessageFilterCategory, { label: string; color: string; types: string[] }> = {
  all: { label: "All", color: "#94a3b8", types: [] },
  registration: { label: "Registration", color: "#f472b6", types: ["AGENT_REGISTERED"] },
  discovery: { label: "Discovery", color: "#a78bfa", types: ["INTENT_RECEIVED", "BOM_GENERATED", "DISCOVERY_QUERY", "DISCOVERY_RESULT"] },
  verification: { label: "Verification", color: "#e879f9", types: ["AGENTFACTS_FETCHED", "VERIFICATION_RESULT"] },
  negotiation: { label: "Negotiation", color: "#38bdf8", types: ["RFQ_SENT", "QUOTE_RECEIVED", "COUNTER_SENT", "REVISED_RECEIVED", "ACCEPT_SENT", "REJECT_SENT"] },
  orders: { label: "Orders", color: "#22d3ee", types: ["ORDER_PLACED"] },
  logistics: { label: "Logistics", color: "#fb923c", types: ["LOGISTICS_REQUESTED", "SHIP_PLAN_RECEIVED"] },
  system: { label: "System", color: "#a3e635", types: ["CASCADE_COMPLETE"] },
};
