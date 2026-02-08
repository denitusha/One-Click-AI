import { useMemo, useCallback } from "react";
import type {
  AgentEvent,
  GraphNode,
  GraphEdge,
  MessageLogEntry,
  TimelinePhase,
  PhaseStatus,
  AgentRole,
  ExecutionPlan,
  OrderDetail,
  ShipPlanDetail,
  NegotiationRound,
  MissingPart,
  AggregatedEdge,
  GraphSelection,
} from "../types";

/* ── Colour palette for message log entries ──────────────── */
const EVENT_COLORS: Record<string, string> = {
  AGENT_REGISTERED: "#f472b6",
  INTENT_RECEIVED: "#818cf8",
  BOM_GENERATED: "#818cf8",
  DISCOVERY_QUERY: "#a78bfa",
  DISCOVERY_RESULT: "#a78bfa",
  AGENTFACTS_FETCHED: "#c084fc",
  VERIFICATION_RESULT: "#e879f9",
  RFQ_SENT: "#38bdf8",
  QUOTE_RECEIVED: "#34d399",
  COUNTER_SENT: "#fb923c",
  REVISED_RECEIVED: "#fbbf24",
  ACCEPT_SENT: "#4ade80",
  REJECT_SENT: "#f87171",
  PART_MISSING: "#ef4444",
  ORDER_PLACED: "#22d3ee",
  LOGISTICS_REQUESTED: "#fb923c",
  SHIP_PLAN_RECEIVED: "#f97316",
  CASCADE_COMPLETE: "#a3e635",
};

/* ── Timeline phases in cascade order ────────────────────── */
const PHASE_ORDER = [
  { id: "intent", label: "Intent" },
  { id: "bom", label: "BOM" },
  { id: "discovery", label: "Discovery" },
  { id: "verification", label: "Verification" },
  { id: "negotiation", label: "Negotiation" },
  { id: "logistics", label: "Logistics" },
  { id: "plan", label: "Plan" },
];

const PHASE_TRIGGERS: Record<string, { phase: string; action: "start" | "complete" }> = {
  INTENT_RECEIVED: { phase: "intent", action: "start" },
  BOM_GENERATED: { phase: "bom", action: "complete" },
  DISCOVERY_QUERY: { phase: "discovery", action: "start" },
  DISCOVERY_RESULT: { phase: "discovery", action: "start" },
  PART_MISSING: { phase: "discovery", action: "start" },
  AGENTFACTS_FETCHED: { phase: "discovery", action: "complete" },
  VERIFICATION_RESULT: { phase: "verification", action: "start" },
  RFQ_SENT: { phase: "verification", action: "complete" },
  QUOTE_RECEIVED: { phase: "negotiation", action: "start" },
  COUNTER_SENT: { phase: "negotiation", action: "start" },
  ACCEPT_SENT: { phase: "negotiation", action: "start" },
  ORDER_PLACED: { phase: "negotiation", action: "complete" },
  LOGISTICS_REQUESTED: { phase: "logistics", action: "start" },
  SHIP_PLAN_RECEIVED: { phase: "logistics", action: "complete" },
  CASCADE_COMPLETE: { phase: "plan", action: "complete" },
};

/* ── Helpers ─────────────────────────────────────────────── */

function inferRole(agentId: string, agentName: string): AgentRole {
  const lower = `${agentId} ${agentName}`.toLowerCase();
  if (lower.includes("procurement") || lower.includes("orchestr")) return "procurement";
  if (lower.includes("logistic") || lower.includes("route") || lower.includes("shipping")) return "logistics";
  if (lower.includes("index") || lower.includes("registry") || lower.includes("nanda")) return "index";
  return "supplier";
}

function summariseEvent(evt: AgentEvent): string {
  const d = evt.data;
  switch (evt.event_type) {
    case "AGENT_REGISTERED":
      return `${d.agent_name ?? evt.agent_id} registered`;
    case "INTENT_RECEIVED":
      return `Intent: "${(d.intent as string)?.slice(0, 60) ?? "…"}"`;
    case "BOM_GENERATED":
      return `BOM: ${(d.parts as string[])?.length ?? "?"} parts identified`;
    case "DISCOVERY_QUERY":
      return `Searching for skill: ${d.skill ?? d.query ?? "?"}`;
    case "DISCOVERY_RESULT":
      return `Found ${(d.agents as unknown[])?.length ?? (d.results as unknown[])?.length ?? "?"} agents`;
    case "PART_MISSING":
      return `Missing: ${d.part_name ?? d.part_id ?? "?"} — ${d.reason ?? "no suppliers found"}`;
    case "AGENTFACTS_FETCHED":
      return `Fetched facts for ${d.agent_name ?? d.agent_id ?? "?"}`;
        case "VERIFICATION_RESULT":
      return `${d.agent_name ?? d.agent_id ?? "?"}: ${d.passed ? "✓ verified" : "✗ failed"} (rel: ${d.reliability_score ?? "?"}, ESG: ${d.esg_rating ?? "?"})`;
    case "RFQ_SENT":
      return `RFQ → ${d.to_agent ?? d.supplier ?? "?"}: ${d.part ?? "?"} × ${d.quantity ?? "?"}`;
    case "QUOTE_RECEIVED":
      return `Quote ← ${d.from_agent ?? d.supplier ?? "?"}: ${d.currency ?? "€"}${d.unit_price ?? "?"}`;
    case "COUNTER_SENT":
      return `Counter → ${d.to_agent ?? d.supplier ?? "?"}: target ${d.currency ?? "€"}${d.target_price ?? "?"}`;
    case "REVISED_RECEIVED":
      return `Revised ← ${d.from_agent ?? d.supplier ?? "?"}: ${d.currency ?? "€"}${d.revised_price ?? "?"}`;
    case "ACCEPT_SENT":
      return `Accepted quote from ${d.to_agent ?? d.supplier ?? "?"}`;
    case "REJECT_SENT":
      return `Rejected: ${d.reason ?? d.rejection_reason ?? "—"}`;
    case "ORDER_PLACED":
      return `Order #${(d.order_id as string)?.slice(0, 8) ?? "?"} placed`;
    case "LOGISTICS_REQUESTED":
      return `Ship request: ${d.pickup ?? "?"} → ${d.delivery ?? "?"}`;
    case "SHIP_PLAN_RECEIVED":
      return `Ship plan: ${(d.route as string[])?.join(" → ") ?? "?"} (${d.transit_time_days ?? "?"}d)`;
    case "CASCADE_COMPLETE":
      return "Coordination cascade complete";
    default:
      return evt.event_type;
  }
}

/* ── Main derivation hook ────────────────────────────────── */

export function useDashboardState(events: AgentEvent[], runId: string | null = null) {
  // First pass: compute all derived state from filtered events
  const derivedState = useMemo(() => {
    // Pre-filter: AGENT_REGISTERED always passes through (agent metadata).
    // When runId is set, only show events matching that run.
    // When runId is null (no intent submitted yet), block all run-specific events.
    const filtered = events.filter((evt) => {
      if (evt.event_type === "AGENT_REGISTERED") return true;
      if (!runId) return false; // no run selected → show nothing run-specific
      const evtRunId = evt.run_id || (evt.data.run_id as string | undefined);
      return evtRunId === runId;
    });

    let edgeCounter = 0;           // reset every recomputation — stable edge IDs
    const nodesMap = new Map<string, GraphNode>();
    const edges: GraphEdge[] = [];
    const messages: MessageLogEntry[] = [];
    const phaseState: Record<string, { started: boolean; completed: boolean; startedAt?: string; completedAt?: string }> = {};

    // Track execution plan data
    let totalCost = 0;
    let ordersPlaced = 0;
    let shippingPlans = 0;
    const suppliersEngaged = new Set<string>();
    const partsSet = new Set<string>();
    let cascadeComplete = false;
    let cascadeReport: Record<string, unknown> | undefined;
    let lastDelivery = "";

    // Detailed tracking for execution plan
    const orders: OrderDetail[] = [];
    const shipPlans: ShipPlanDetail[] = [];
    const missingParts: MissingPart[] = [];
    const negotiationMap = new Map<string, NegotiationRound>(); // keyed by "part:supplier"

    for (const evt of filtered) {
      const { event_type, agent_id, data } = evt;

      /* ── Build message log ── */
      messages.push({
        id: `${evt.timestamp}-${agent_id}-${event_type}-${messages.length}`,
        timestamp: evt.timestamp,
        event_type,
        agent_id,
        from: (data.from_agent as string) ?? agent_id,
        to: data.to_agent as string | undefined,
        summary: summariseEvent(evt),
        color: EVENT_COLORS[event_type] ?? "#94a3b8",
      });

      /* ── Timeline phases ── */
      const trigger = PHASE_TRIGGERS[event_type];
      if (trigger) {
        if (!phaseState[trigger.phase]) {
          phaseState[trigger.phase] = { started: false, completed: false };
        }
        const ps = phaseState[trigger.phase];
        if (trigger.action === "start" && !ps.started) {
          ps.started = true;
          ps.startedAt = evt.timestamp;
        }
        if (trigger.action === "complete") {
          ps.started = true;
          ps.completed = true;
          ps.completedAt = evt.timestamp;
          if (!ps.startedAt) ps.startedAt = evt.timestamp;
        }
      }

      /* ── Build graph nodes & edges based on event type ── */
      switch (event_type) {
        case "AGENT_REGISTERED": {
          const name = (data.agent_name as string) ?? agent_id;
          const role = inferRole(agent_id, name);
          const framework = (data.framework as string) ?? undefined;
          const skills = (data.skills as string[]) ?? undefined;
          nodesMap.set(agent_id, { id: agent_id, label: name, role, framework, skills });
          break;
        }

        case "VERIFICATION_RESULT": {
          // Store reliability & ESG data on the verified agent node
          const verifiedId = (data.agent_id as string) ?? agent_id;
          const existing = nodesMap.get(verifiedId);
          if (existing) {
            existing.reliabilityScore = (data.reliability_score as number) ?? existing.reliabilityScore;
            existing.esgRating = (data.esg_rating as string) ?? existing.esgRating;
          }
          break;
        }

        case "DISCOVERY_QUERY": {
          // Edge from procurement → index (discovery query)
          const from = agent_id;
          if (!nodesMap.has("nanda-index")) {
            nodesMap.set("nanda-index", { id: "nanda-index", label: "NANDA Index", role: "index" });
          }
          edges.push({
            id: `edge-${edgeCounter++}`,
            source: from,
            target: "nanda-index",
            label: `search: ${data.skill ?? data.query ?? "?"}`,
            edgeType: "discovery",
          });
          break;
        }

        case "DISCOVERY_RESULT": {
          // Edges from index → discovered agents
          const agents = (data.agents ?? data.results) as Array<{ agent_id?: string; agent_name?: string }> | undefined;
          if (agents) {
            for (const a of agents) {
              const aId = a.agent_id ?? "unknown";
              if (!nodesMap.has(aId)) {
                nodesMap.set(aId, {
                  id: aId,
                  label: a.agent_name ?? aId,
                  role: "supplier",
                });
              }
              edges.push({
                id: `edge-${edgeCounter++}`,
                source: "nanda-index",
                target: aId,
                label: "discovered",
                edgeType: "discovery",
              });
            }
          }
          break;
        }

        case "PART_MISSING": {
          missingParts.push({
            partId: (data.part_id as string) ?? "unknown",
            partName: (data.part_name as string) ?? "Unknown",
            skillQuery: (data.skill_query as string) ?? "",
            quantity: (data.quantity as number) ?? 0,
            system: (data.system as string) ?? "",
            reason: (data.reason as string) ?? "No suppliers found",
            timestamp: evt.timestamp,
          });
          break;
        }

        case "RFQ_SENT": {
          const to = (data.to_agent ?? data.supplier_id ?? data.supplier) as string;
          if (to) {
            if (!nodesMap.has(to)) {
              nodesMap.set(to, { id: to, label: (data.supplier_name as string) ?? to, role: "supplier" });
            }
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: agent_id,
              target: to,
              label: `RFQ: ${data.part ?? "?"}`,
              edgeType: "rfq",
              animated: true,
            });
            if (data.part) partsSet.add(data.part as string);
            suppliersEngaged.add(to);

            // Track negotiation
            const part = data.part as string;
            const key = `${part}:${to}`;
            if (!negotiationMap.has(key)) {
              negotiationMap.set(key, {
                part,
                supplier: to,
                supplierName: (data.supplier_name as string) ?? to,
                rfqPrice: null,
                quotedPrice: null,
                counterPrice: null,
                revisedPrice: null,
                accepted: false,
                rejected: false,
              });
            }
          }
          break;
        }

        case "QUOTE_RECEIVED": {
          const from = (data.from_agent ?? data.supplier_id ?? data.supplier) as string;
          if (from) {
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: from,
              target: agent_id,
              label: `Quote: €${data.unit_price ?? "?"}`,
              edgeType: "quote",
              animated: true,
            });

            // Track negotiation
            const part = data.part as string;
            if (part) {
              const key = `${part}:${from}`;
              const neg = negotiationMap.get(key);
              if (neg) neg.quotedPrice = (data.unit_price as number) ?? null;
            }
          }
          break;
        }

        case "COUNTER_SENT": {
          const to = (data.to_agent ?? data.supplier_id ?? data.supplier) as string;
          if (to) {
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: agent_id,
              target: to,
              label: `Counter: €${data.target_price ?? "?"}`,
              edgeType: "counter",
              animated: true,
            });

            // Track negotiation
            const part = data.part as string;
            if (part) {
              const key = `${part}:${to}`;
              const neg = negotiationMap.get(key);
              if (neg) neg.counterPrice = (data.target_price as number) ?? null;
            }
          }
          break;
        }

        case "REVISED_RECEIVED": {
          const from = (data.from_agent ?? data.supplier_id ?? data.supplier) as string;
          if (from) {
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: from,
              target: agent_id,
              label: `Revised: €${data.revised_price ?? "?"}`,
              edgeType: "quote",
              animated: true,
            });

            // Track negotiation
            const part = data.part as string;
            if (part) {
              const key = `${part}:${from}`;
              const neg = negotiationMap.get(key);
              if (neg) neg.revisedPrice = (data.revised_price as number) ?? null;
            }
          }
          break;
        }

        case "ACCEPT_SENT": {
          const to = (data.to_agent ?? data.supplier_id ?? data.supplier) as string;
          if (to) {
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: agent_id,
              target: to,
              label: "Accepted",
              edgeType: "accept",
            });

            // Track negotiation
            const part = data.part as string;
            if (part) {
              const key = `${part}:${to}`;
              const neg = negotiationMap.get(key);
              if (neg) neg.accepted = true;
            }
          }
          break;
        }

        case "REJECT_SENT": {
          const to = (data.to_agent ?? data.supplier_id ?? data.supplier) as string;
          // Track negotiation
          const part = data.part as string;
          if (part && to) {
            const key = `${part}:${to}`;
            const neg = negotiationMap.get(key);
            if (neg) {
              neg.rejected = true;
              neg.rejectionReason = (data.reason ?? data.rejection_reason) as string | undefined;
            }
          }
          break;
        }

        case "ORDER_PLACED": {
          const supplierId = (data.supplier_id ?? data.supplier ?? data.to_agent) as string;
          if (supplierId) {
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: agent_id,
              target: supplierId,
              label: `Order #${(data.order_id as string)?.slice(0, 8) ?? "?"}`,
              edgeType: "order",
            });
          }
          ordersPlaced++;
          const orderTotal = (data.total_price as number) ?? 0;
          totalCost += orderTotal;
          if (data.part) partsSet.add(data.part as string);

          // Collect order detail
          orders.push({
            orderId: (data.order_id as string) ?? `ord-${orders.length}`,
            supplier: supplierId ?? "unknown",
            supplierName: (data.supplier_name as string) ?? supplierId ?? "Unknown",
            part: (data.part as string) ?? "Unknown",
            quantity: (data.quantity as number) ?? 0,
            unitPrice: (data.unit_price as number) ?? 0,
            totalPrice: orderTotal,
            currency: (data.currency as string) ?? "EUR",
            leadTimeDays: (data.lead_time_days as number) ?? null,
            timestamp: evt.timestamp,
          });
          break;
        }

        case "LOGISTICS_REQUESTED": {
          // Find or create logistics node
          const logAgents = [...nodesMap.values()].filter((n) => n.role === "logistics");
          const logTarget = logAgents.length > 0 ? logAgents[0].id : "logistics-agent";
          if (!nodesMap.has(logTarget)) {
            nodesMap.set(logTarget, { id: logTarget, label: "Logistics Agent", role: "logistics" });
          }
          edges.push({
            id: `edge-${edgeCounter++}`,
            source: agent_id,
            target: logTarget,
            label: "Ship request",
            edgeType: "logistics",
            animated: true,
          });
          break;
        }

        case "SHIP_PLAN_RECEIVED": {
          const from = (data.from_agent ?? data.logistics_agent) as string;
          if (from) {
            edges.push({
              id: `edge-${edgeCounter++}`,
              source: from,
              target: agent_id,
              label: `Ship plan: ${(data.route as string[])?.join("→") ?? ""}`,
              edgeType: "logistics",
            });
          }
          shippingPlans++;
          if (data.estimated_arrival) lastDelivery = data.estimated_arrival as string;

          // Collect shipping plan detail
          shipPlans.push({
            orderId: (data.order_id as string) ?? `ship-${shipPlans.length}`,
            route: (data.route as string[]) ?? [],
            transitTimeDays: (data.transit_time_days as number) ?? null,
            cost: (data.cost as number) ?? (data.shipping_cost as number) ?? null,
            pickup: (data.pickup as string) ?? (data.origin as string) ?? "Unknown",
            delivery: (data.delivery as string) ?? (data.destination as string) ?? "Unknown",
            estimatedArrival: (data.estimated_arrival as string) ?? "",
            timestamp: evt.timestamp,
          });
          break;
        }

        case "CASCADE_COMPLETE": {
          cascadeComplete = true;
          cascadeReport = data.report as Record<string, unknown> | undefined;
          break;
        }
      }
    }

    /* ── Deduplicate supplier nodes ──────────────────────────
     * Stale NANDA Index entries (from MongoDB persistence across restarts)
     * can cause the same physical supplier to appear under different IDs
     * (e.g. "supplier-a" vs "Supplier A" vs "Supplier_A").
     *
     * Strategy: normalise each supplier ID → lowercase, trim, replace
     * spaces/underscores with dashes.  If multiple nodes map to the same
     * canonical key, keep the one that came from AGENT_REGISTERED (it has
     * `framework` set) and discard the rest, rewriting edge references.
     */
    const supplierNodes = [...nodesMap.entries()].filter(
      ([, n]) => n.role === "supplier",
    );

    // Build canonical key → best node mapping
    const canonicalMap = new Map<string, { id: string; node: GraphNode }>();
    const idRewrites = new Map<string, string>(); // old ID → canonical ID

    for (const [id, node] of supplierNodes) {
      const canonical = id.toLowerCase().trim().replace(/[\s_]+/g, "-");
      const existing = canonicalMap.get(canonical);

      if (!existing) {
        canonicalMap.set(canonical, { id, node });
      } else {
        // Prefer the node that has `framework` (came from AGENT_REGISTERED)
        const existingHasFramework = !!existing.node.framework;
        const currentHasFramework = !!node.framework;

        if (currentHasFramework && !existingHasFramework) {
          // Current node is better — rewrite old → current
          idRewrites.set(existing.id, id);
          nodesMap.delete(existing.id);
          canonicalMap.set(canonical, { id, node });
        } else {
          // Existing node is better (or both equal) — discard current
          idRewrites.set(id, existing.id);
          nodesMap.delete(id);
        }
      }
    }

    // Rewrite edge source/target references for discarded IDs
    if (idRewrites.size > 0) {
      for (const e of edges) {
        const newSource = idRewrites.get(e.source);
        if (newSource) e.source = newSource;
        const newTarget = idRewrites.get(e.target);
        if (newTarget) e.target = newTarget;
      }
    }

    /* ── Build timeline ── */
    const completedPhases = new Set<string>();
    const activePhases = new Set<string>();
    for (const [id, ps] of Object.entries(phaseState)) {
      if (ps.completed) completedPhases.add(id);
      else if (ps.started) activePhases.add(id);
    }

    // Auto-complete phases before the first active one
    let foundActive = false;
    const timeline: TimelinePhase[] = PHASE_ORDER.map(({ id, label }) => {
      let status: PhaseStatus = "pending";
      if (completedPhases.has(id)) {
        status = "completed";
      } else if (activePhases.has(id)) {
        status = "active";
        foundActive = true;
      } else if (!foundActive && (completedPhases.size > 0 || activePhases.size > 0)) {
        // If this phase is before any active/completed phase, mark completed
        const thisIdx = PHASE_ORDER.findIndex((p) => p.id === id);
        const firstActiveIdx = PHASE_ORDER.findIndex((p) => activePhases.has(p.id) || completedPhases.has(p.id));
        if (firstActiveIdx >= 0 && thisIdx < firstActiveIdx) {
          status = "completed";
        }
      }
      return {
        id,
        label,
        status,
        startedAt: phaseState[id]?.startedAt,
        completedAt: phaseState[id]?.completedAt,
      };
    });

    /* ── Compute overview (aggregated) edges ── */
    const aggMap = new Map<string, AggregatedEdge>();
    for (const e of edges) {
      // Normalise direction so A->B and B->A are separate
      const key = `${e.source}::${e.target}`;
      let agg = aggMap.get(key);
      if (!agg) {
        agg = {
          id: `agg-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          counts: {},
          totalMessages: 0,
        };
        aggMap.set(key, agg);
      }
      agg.counts[e.edgeType] = (agg.counts[e.edgeType] ?? 0) + 1;
      agg.totalMessages += 1;
    }
    const overviewEdges = [...aggMap.values()];

    return {
      nodes: [...nodesMap.values()],
      edges,
      messages,
      timeline,
      cascadeComplete,
      overviewEdges,
      totalCost,
      ordersPlaced,
      shippingPlans,
      partsSetSize: partsSet.size,
      suppliersEngagedSize: suppliersEngaged.size,
      orders,
      shipPlans,
      missingParts,
      negotiations: [...negotiationMap.values()],
      cascadeReport,
      lastDelivery,
    };
  }, [events, runId]);

  // Second pass: memoize executionPlan separately with stable reference
  // Only depends on the actual plan data, not the entire events array
  const executionPlan = useMemo(() => {
    if (!derivedState.cascadeComplete) return null;
    
    return {
      totalCost: derivedState.totalCost,
      currency: "EUR",
      partsCount: derivedState.partsSetSize,
      suppliersEngaged: derivedState.suppliersEngagedSize,
      ordersPlaced: derivedState.ordersPlaced,
      shippingPlans: derivedState.shippingPlans,
      estimatedDelivery: derivedState.lastDelivery,
      orders: derivedState.orders,
      shipPlans: derivedState.shipPlans,
      missingParts: derivedState.missingParts,
      negotiations: derivedState.negotiations,
      report: derivedState.cascadeReport,
    };
  }, [
    derivedState.cascadeComplete,
    derivedState.totalCost,
    derivedState.ordersPlaced,
    derivedState.shippingPlans,
    derivedState.partsSetSize,
    derivedState.suppliersEngagedSize,
    derivedState.lastDelivery,
    derivedState.orders,
    derivedState.shipPlans,
    derivedState.missingParts,
    derivedState.negotiations,
    derivedState.cascadeReport,
  ]);

  return {
    nodes: derivedState.nodes,
    edges: derivedState.edges,
    messages: derivedState.messages,
    timeline: derivedState.timeline,
    executionPlan,
    cascadeComplete: derivedState.cascadeComplete,
    overviewEdges: derivedState.overviewEdges,
    orders: derivedState.orders,
    shipPlans: derivedState.shipPlans,
    negotiations: derivedState.negotiations,
  };
}

/* ── Detail edge filter (called outside the memo, pure function) ── */

export function filterDetailEdges(
  edges: GraphEdge[],
  selection: GraphSelection,
): GraphEdge[] {
  switch (selection.mode) {
    case "overview":
      return [];

    case "agent-detail": {
      const id = selection.agentId;
      if (!id) return [];
      return edges.filter((e) => e.source === id || e.target === id);
    }

    case "order-detail": {
      const { partName, supplierId } = selection;
      if (!partName || !supplierId) return [];
      // Show all edges between procurement<->supplier that mention this part
      return edges.filter((e) => {
        const involvesSupplier = e.source === supplierId || e.target === supplierId;
        const mentionsPart = e.label.toLowerCase().includes(partName.toLowerCase());
        return involvesSupplier && mentionsPart;
      });
    }

    case "logistics-detail": {
      // Show only logistics edges
      return edges.filter((e) => e.edgeType === "logistics");
    }

    default:
      return [];
  }
}
