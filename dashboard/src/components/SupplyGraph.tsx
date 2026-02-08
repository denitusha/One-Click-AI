import { useRef, useEffect, useMemo } from "react";
import type { Core, ElementDefinition } from "cytoscape";
import cytoscape from "cytoscape";
import type {
  GraphNode,
  GraphEdge,
  AggregatedEdge,
  GraphSelection,
  ShipPlanDetail,
  NegotiationRound,
  AnalyticsMode,
} from "../types";

/* ── Colour palette by role ──────────────────────────────── */
const ROLE_COLORS: Record<string, string> = {
  procurement: "#818cf8",
  supplier: "#34d399",
  logistics: "#fb923c",
  index: "#f472b6",
  hub: "#94a3b8",        // logistics hub cities
  step: "#64748b",       // negotiation step node
};

/* ── SVG data URI icons per role ──────────────────────────── */
// Each icon is a 64x64 compound SVG: a colored rounded-rect chip + white icon on top
const NODE_ICONS: Record<string, string> = {
  // Shopping cart icon for procurement (purple chip)
  procurement: `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="10" y="10" width="44" height="44" rx="10" fill="#818cf8" fill-opacity="0.3" stroke="#818cf8" stroke-opacity="0.6" stroke-width="2"/><g transform="translate(16,16) scale(1.33)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 100 4 2 2 0 000-4z"/></g></svg>')}`,
  // Factory / box icon for supplier (green chip)
  supplier: `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="10" y="10" width="44" height="44" rx="10" fill="#34d399" fill-opacity="0.3" stroke="#34d399" stroke-opacity="0.6" stroke-width="2"/><g transform="translate(16,16) scale(1.33)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></g></svg>')}`,
  // Truck icon for logistics (orange chip)
  logistics: `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="10" y="10" width="44" height="44" rx="10" fill="#fb923c" fill-opacity="0.3" stroke="#fb923c" stroke-opacity="0.6" stroke-width="2"/><g transform="translate(16,16) scale(1.33)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0"/></g></svg>')}`,
  // Search icon for index (pink chip)
  index: `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="10" y="10" width="44" height="44" rx="10" fill="#f472b6" fill-opacity="0.3" stroke="#f472b6" stroke-opacity="0.6" stroke-width="2"/><g transform="translate(16,16) scale(1.33)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></g></svg>')}`,
};

/* ── Edge style by type ──────────────────────────────────── */
const EDGE_STYLES: Record<string, { color: string; style: string; width: number }> = {
  discovery: { color: "#a78bfa", style: "dashed", width: 1.5 },
  rfq: { color: "#38bdf8", style: "solid", width: 2 },
  quote: { color: "#34d399", style: "solid", width: 2 },
  counter: { color: "#fb923c", style: "dashed", width: 2 },
  accept: { color: "#4ade80", style: "solid", width: 3 },
  order: { color: "#22d3ee", style: "solid", width: 3 },
  logistics: { color: "#f97316", style: "solid", width: 2.5 },
  contract: { color: "#e2e8f0", style: "solid", width: 3 },
  route: { color: "#f97316", style: "solid", width: 3 },
  "route-express": { color: "#ef4444", style: "solid", width: 3.5 },
};

/* ── Type-friendly label for aggregated edge badges ─────── */
const EDGE_TYPE_LABELS: Record<string, string> = {
  discovery: "disc",
  rfq: "RFQ",
  quote: "quote",
  counter: "ctr",
  accept: "acc",
  order: "order",
  logistics: "log",
  contract: "ctr",
};

function aggregatedLabel(counts: Record<string, number>): string {
  const parts: string[] = [];
  for (const [type, count] of Object.entries(counts)) {
    if (count > 0) {
      parts.push(`${count} ${EDGE_TYPE_LABELS[type] ?? type}`);
    }
  }
  return parts.join(", ");
}

function dominantEdgeType(counts: Record<string, number>): string {
  const priority = ["order", "accept", "logistics", "rfq", "quote", "counter", "discovery"];
  for (const t of priority) {
    if ((counts[t] ?? 0) > 0) return t;
  }
  let best = "discovery";
  let bestCount = 0;
  for (const [t, c] of Object.entries(counts)) {
    if (c > bestCount) {
      best = t;
      bestCount = c;
    }
  }
  return best;
}

/* ── Shared stylesheet base ──────────────────────────────── */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildStylesheet(mode: GraphSelection["mode"], analyticsMode: AnalyticsMode): Array<{ selector: string; style: Record<string, any> }> {
  const isOverview = mode === "overview";
  const isLogistics = mode === "logistics-detail";
  const isOrder = mode === "order-detail";
  const nodeSize = isOverview ? 50 : isLogistics ? 45 : 50;
  const procSize = isOverview ? 60 : 55;
  const fontSize = isOverview ? "11px" : "10px";

  const styles: Array<{ selector: string; style: Record<string, any> }> = [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "text-valign": "bottom",
        "text-halign": "center",
        "font-size": fontSize,
        color: "#e2e8f0",
        "text-margin-y": 10,
        "background-color": "#1a2332",
        "background-opacity": 1,
        "border-width": 3,
        "border-opacity": 0.7,
        shape: "round-rectangle" as any,
        width: nodeSize,
        height: nodeSize,
        "text-wrap": "wrap",
        "text-max-width": isOverview ? "100px" : "90px",
        "text-background-opacity": 0.7,
        "text-background-color": "#1e293b",
        "text-background-padding": "4px",
        "text-background-shape": "roundrectangle",
        "corner-radius": 10,
      },
    },
    {
      selector: 'node[role = "procurement"]',
      style: {
        "background-color": "#1a2332",
        "border-color": "#6366f1",
        shape: "round-rectangle" as any,
        width: isOverview ? 55 : 50,
        height: isOverview ? 55 : 50,
        "background-image": NODE_ICONS.procurement,
        "background-fit": "contain" as any,
        "background-width": "75%",
        "background-height": "75%",
        "background-clip": "none" as any,
        "background-image-smoothing": "yes" as any,
      },
    },
    {
      selector: 'node[role = "supplier"]',
      style: {
        "background-color": "#1a2332",
        "border-color": "#10b981",
        shape: "round-rectangle" as any,
        width: isOverview ? 50 : 45,
        height: isOverview ? 50 : 45,
        "background-image": NODE_ICONS.supplier,
        "background-fit": "contain" as any,
        "background-width": "75%",
        "background-height": "75%",
        "background-clip": "none" as any,
        "background-image-smoothing": "yes" as any,
      },
    },
    {
      selector: 'node[role = "logistics"]',
      style: {
        "background-color": "#1a2332",
        "border-color": "#ea580c",
        shape: "round-rectangle" as any,
        width: isOverview ? 50 : 45,
        height: isOverview ? 50 : 45,
        "background-image": NODE_ICONS.logistics,
        "background-fit": "contain" as any,
        "background-width": "75%",
        "background-height": "75%",
        "background-clip": "none" as any,
        "background-image-smoothing": "yes" as any,
      },
    },
    {
      selector: 'node[role = "index"]',
      style: {
        "background-color": "#1a2332",
        "border-color": "#ec4899",
        shape: "round-rectangle" as any,
        width: isOverview ? 50 : 45,
        height: isOverview ? 50 : 45,
        "background-image": NODE_ICONS.index,
        "background-fit": "contain" as any,
        "background-width": "75%",
        "background-height": "75%",
        "background-clip": "none" as any,
        "background-image-smoothing": "yes" as any,
      },
    },
    // Hub nodes (logistics routing cities)
    {
      selector: 'node[role = "hub"]',
      style: {
        "background-color": "#475569",
        "border-color": "#64748b",
        shape: "round-rectangle" as any,
        width: 40,
        height: 30,
        "font-size": "10px",
        "text-margin-y": 6,
      },
    },
    // Origin hub
    {
      selector: "node.hub-origin",
      style: {
        "background-color": "#fb923c",
        "border-color": "#ea580c",
        width: 50,
        height: 35,
      },
    },
    // Destination hub
    {
      selector: "node.hub-dest",
      style: {
        "background-color": "#4ade80",
        "border-color": "#16a34a",
        width: 50,
        height: 35,
      },
    },
    // Negotiation step nodes
    {
      selector: 'node[role = "step"]',
      style: {
        "background-color": "#334155",
        "border-color": "#475569",
        shape: "round-rectangle" as any,
        width: 55,
        height: 35,
        "font-size": "9px",
        "text-valign": "center",
        "text-halign": "center",
        "text-margin-y": 0,
      },
    },
    // Highlighted / selected agent in detail mode
    {
      selector: "node.highlighted",
      style: {
        "border-width": 4,
        "border-color": "#f1f5f9",
        width: procSize + 10,
        height: procSize + 10,
        "font-size": "14px",
        "font-weight": "bold" as any,
      },
    },
    // Dimmed nodes (not involved in current detail)
    {
      selector: "node.dimmed",
      style: {
        opacity: 0.3,
      },
    },
    // Overview node hover
    {
      selector: "node.hovered",
      style: {
        "border-width": 4,
        "border-color": "#f1f5f9",
        "border-opacity": 1,
      },
    },
    {
      selector: "edge",
      style: {
        width: 2,
        "line-color": "#475569",
        "target-arrow-color": "#475569",
        "target-arrow-shape": "triangle",
        "curve-style": isOrder ? "taxi" : "bezier",
        "arrow-scale": 0.8,
        label: "data(label)",
        "font-size": isOverview ? "10px" : "9px",
        color: "#94a3b8",
        "text-rotation": "autorotate",
        "text-margin-y": -10,
        "text-background-opacity": 0.8,
        "text-background-color": "#0f172a",
        "text-background-padding": "3px",
        opacity: 0.85,
      },
    },
    // Edge type-specific styles
    {
      selector: 'edge[edgeType = "discovery"]',
      style: {
        "line-color": EDGE_STYLES.discovery.color,
        "target-arrow-color": EDGE_STYLES.discovery.color,
        "line-style": "dashed" as any,
        width: 1.5,
      },
    },
    {
      selector: 'edge[edgeType = "rfq"]',
      style: {
        "line-color": EDGE_STYLES.rfq.color,
        "target-arrow-color": EDGE_STYLES.rfq.color,
        width: 2,
      },
    },
    {
      selector: 'edge[edgeType = "quote"]',
      style: {
        "line-color": EDGE_STYLES.quote.color,
        "target-arrow-color": EDGE_STYLES.quote.color,
        width: 2,
      },
    },
    {
      selector: 'edge[edgeType = "counter"]',
      style: {
        "line-color": EDGE_STYLES.counter.color,
        "target-arrow-color": EDGE_STYLES.counter.color,
        "line-style": "dashed" as any,
        width: 2,
      },
    },
    {
      selector: 'edge[edgeType = "accept"]',
      style: {
        "line-color": EDGE_STYLES.accept.color,
        "target-arrow-color": EDGE_STYLES.accept.color,
        width: 3,
      },
    },
    {
      selector: 'edge[edgeType = "order"]',
      style: {
        "line-color": EDGE_STYLES.order.color,
        "target-arrow-color": EDGE_STYLES.order.color,
        width: 3,
      },
    },
    {
      selector: 'edge[edgeType = "logistics"]',
      style: {
        "line-color": EDGE_STYLES.logistics.color,
        "target-arrow-color": EDGE_STYLES.logistics.color,
        width: 2.5,
      },
    },
    // Route edges for logistics detail
    {
      selector: 'edge[edgeType = "route"]',
      style: {
        "line-color": "#f97316",
        "target-arrow-color": "#f97316",
        width: 3,
        "curve-style": "bezier",
      },
    },
    {
      selector: 'edge[edgeType = "route-express"]',
      style: {
        "line-color": "#ef4444",
        "target-arrow-color": "#ef4444",
        width: 3.5,
        "line-style": "solid" as any,
        "curve-style": "bezier",
      },
    },
    // Aggregated edges scale width by total messages
    {
      selector: "edge.agg-sm",
      style: { width: 2 },
    },
    {
      selector: "edge.agg-md",
      style: { width: 4 },
    },
    {
      selector: "edge.agg-lg",
      style: { width: 6 },
    },
    {
      selector: "edge.dimmed",
      style: { opacity: 0.15 },
    },
    {
      selector: "edge.hovered-edge",
      style: { opacity: 1, width: 4 },
    },
    {
      selector: "node:selected",
      style: {
        "border-width": 4,
        "border-color": "#f1f5f9",
      },
    },
  ];

  /* ── Analytics overlay styles ── */
  if (analyticsMode === "risk") {
    styles.push(
      {
        selector: "node.risk-high",
        style: { "background-color": "#4ade80", "border-color": "#16a34a", "border-width": 3 },
      },
      {
        selector: "node.risk-med",
        style: { "background-color": "#fbbf24", "border-color": "#d97706", "border-width": 3 },
      },
      {
        selector: "node.risk-low",
        style: { "background-color": "#f87171", "border-color": "#dc2626", "border-width": 3 },
      },
      {
        selector: "node.risk-unknown",
        style: { "background-color": "#475569", "border-color": "#334155", "border-width": 2, opacity: 0.5 },
      },
    );
  }

  if (analyticsMode === "bottleneck") {
    styles.push(
      {
        selector: "node.bottleneck-critical",
        style: {
          "border-width": 6,
          "border-color": "#ef4444",
          "border-opacity": 1,
          "background-color": "#fca5a5",
          width: 80,
          height: 80,
        },
      },
      {
        selector: "node.bottleneck-high",
        style: {
          "border-width": 4,
          "border-color": "#fb923c",
          "border-opacity": 1,
          width: 70,
          height: 70,
        },
      },
      {
        selector: "node.bottleneck-normal",
        style: {
          opacity: 0.5,
        },
      },
    );
  }

  if (analyticsMode === "cost") {
    styles.push(
      {
        selector: "edge.cost-high",
        style: { width: 6, "line-color": "#ef4444", "target-arrow-color": "#ef4444" },
      },
      {
        selector: "edge.cost-med",
        style: { width: 4, "line-color": "#fbbf24", "target-arrow-color": "#fbbf24" },
      },
      {
        selector: "edge.cost-low",
        style: { width: 2, "line-color": "#4ade80", "target-arrow-color": "#4ade80" },
      },
    );
  }

  return styles;
}

/* ── Build logistics routing sub-graph ───────────────────── */

function buildLogisticsElements(
  shipPlans: ShipPlanDetail[],
  selectedIndex?: number,
): ElementDefinition[] {
  const elements: ElementDefinition[] = [];
  const nodeIds = new Set<string>();

  const plans = selectedIndex !== undefined ? [shipPlans[selectedIndex]] : shipPlans;

  for (let pi = 0; pi < plans.length; pi++) {
    const sp = plans[pi];
    if (!sp) continue;

    const route = sp.route.length > 0 ? sp.route : [sp.pickup, sp.delivery];
    const isExpress = (sp.cost ?? 0) > 500;

    for (let i = 0; i < route.length; i++) {
      const city = route[i];
      const nodeId = `hub-${city.replace(/\s+/g, "_").toLowerCase()}`;

      if (!nodeIds.has(nodeId)) {
        nodeIds.add(nodeId);
        const isOrigin = i === 0;
        const isDest = i === route.length - 1;
        const classes = isOrigin ? "hub-origin" : isDest ? "hub-dest" : "";

        elements.push({
          data: {
            id: nodeId,
            label: city,
            role: "hub",
          },
          classes,
        });
      }

      // Edge to next city
      if (i < route.length - 1) {
        const nextCity = route[i + 1];
        const nextId = `hub-${nextCity.replace(/\s+/g, "_").toLowerCase()}`;
        const edgeId = `route-${pi}-${i}`;
        const edgeType = isExpress ? "route-express" : "route";

        // Cost per segment (approximate)
        const segmentCost = sp.cost != null ? Math.round(sp.cost / Math.max(route.length - 1, 1)) : null;
        const label = segmentCost != null ? `\u20AC${segmentCost}` : "";

        elements.push({
          data: {
            id: edgeId,
            source: nodeId,
            target: nextId,
            label,
            edgeType,
          },
        });
      }
    }
  }

  // Add summary info node if showing all routes
  if (selectedIndex === undefined && shipPlans.length > 0) {
    const totalCost = shipPlans.reduce((s, sp) => s + (sp.cost ?? 0), 0);
    const maxTransit = Math.max(...shipPlans.map((sp) => sp.transitTimeDays ?? 0));
    elements.push({
      data: {
        id: "logistics-summary",
        label: `${shipPlans.length} routes\n\u20AC${totalCost.toLocaleString()}\nMax ${maxTransit}d`,
        role: "logistics",
      },
      classes: "highlighted",
    });
  }

  return elements;
}

/* ── Build order negotiation flow ────────────────────────── */

function buildOrderElements(
  negotiations: NegotiationRound[],
  partName?: string,
  supplierId?: string,
): ElementDefinition[] {
  const elements: ElementDefinition[] = [];

  // Find the matching negotiation
  const neg = negotiations.find(
    (n) =>
      (partName ? n.part.toLowerCase() === partName.toLowerCase() : true) &&
      (supplierId ? n.supplier === supplierId : true),
  );

  if (!neg) return elements;

  // Build sequential flow: Procurement -> RFQ -> Supplier -> Quote -> ... -> Order
  const steps: { id: string; label: string; role: string; classes?: string }[] = [];
  const edges: { source: string; target: string; label: string; edgeType: string }[] = [];

  // Step 1: Procurement node
  steps.push({ id: "proc", label: "Procurement\nAgent", role: "procurement", classes: "highlighted" });

  // Step 2: RFQ sent
  steps.push({ id: "step-rfq", label: "RFQ", role: "step" });
  edges.push({ source: "proc", target: "step-rfq", label: `Request for ${neg.part}`, edgeType: "rfq" });

  // Step 3: Supplier node
  steps.push({ id: "supplier", label: neg.supplierName, role: "supplier" });
  edges.push({ source: "step-rfq", target: "supplier", label: "", edgeType: "rfq" });

  // Step 4: Quote received
  if (neg.quotedPrice != null) {
    steps.push({ id: "step-quote", label: `Quote\n\u20AC${neg.quotedPrice}`, role: "step" });
    edges.push({ source: "supplier", target: "step-quote", label: `\u20AC${neg.quotedPrice}/unit`, edgeType: "quote" });

    // Step 5: Counter offer (if sent)
    if (neg.counterPrice != null) {
      steps.push({ id: "step-counter", label: `Counter\n\u20AC${neg.counterPrice}`, role: "step" });
      edges.push({ source: "step-quote", target: "step-counter", label: `Target: \u20AC${neg.counterPrice}`, edgeType: "counter" });

      // Step 6: Revised quote (if received)
      if (neg.revisedPrice != null) {
        steps.push({ id: "step-revised", label: `Revised\n\u20AC${neg.revisedPrice}`, role: "step" });
        edges.push({ source: "step-counter", target: "step-revised", label: `Revised: \u20AC${neg.revisedPrice}`, edgeType: "quote" });
      }
    }
  }

  // Final step: Accept/Reject
  if (neg.accepted) {
    const lastStep = steps[steps.length - 1].id;
    steps.push({ id: "step-accept", label: "Accepted", role: "step" });
    edges.push({ source: lastStep, target: "step-accept", label: "Deal accepted", edgeType: "accept" });

    // Order placed
    steps.push({ id: "step-order", label: "Order\nPlaced", role: "step" });
    edges.push({ source: "step-accept", target: "step-order", label: "PO issued", edgeType: "order" });
  } else if (neg.rejected) {
    const lastStep = steps[steps.length - 1].id;
    steps.push({ id: "step-reject", label: "Rejected", role: "step" });
    edges.push({ source: lastStep, target: "step-reject", label: neg.rejectionReason ?? "Rejected", edgeType: "counter" });
  }

  // Convert to Cytoscape elements
  for (const s of steps) {
    elements.push({
      data: { id: s.id, label: s.label, role: s.role },
      classes: s.classes ?? "",
    });
  }
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i];
    elements.push({
      data: {
        id: `neg-edge-${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        edgeType: e.edgeType,
      },
    });
  }

  return elements;
}

/* ── Component ───────────────────────────────────────────── */

interface SupplyGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  overviewEdges: AggregatedEdge[];
  detailEdges: GraphEdge[];
  selection: GraphSelection;
  shipPlans: ShipPlanDetail[];
  negotiations: NegotiationRound[];
  analyticsMode: AnalyticsMode;
  onSelectAgent: (agentId: string) => void;
  onBack: () => void;
}

export default function SupplyGraph({
  nodes,
  edges,
  overviewEdges,
  detailEdges,
  selection,
  shipPlans,
  negotiations,
  analyticsMode,
  onSelectAgent,
  onBack,
}: SupplyGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const prevElementKey = useRef("");

  const isOverview = selection.mode === "overview";
  const isLogistics = selection.mode === "logistics-detail";
  const isOrder = selection.mode === "order-detail";

  // ── Determine which nodes are relevant in detail mode ──
  const detailNodeIds = useMemo(() => {
    if (isOverview || isLogistics || isOrder) return new Set<string>();
    const ids = new Set<string>();
    for (const e of detailEdges) {
      ids.add(e.source);
      ids.add(e.target);
    }
    if (selection.agentId) ids.add(selection.agentId);
    return ids;
  }, [isOverview, isLogistics, isOrder, detailEdges, selection.agentId]);

  // ── Build Cytoscape elements ──
  const elements = useMemo((): ElementDefinition[] => {
    /* ── Logistics detail: routing sub-graph ── */
    if (isLogistics) {
      return buildLogisticsElements(shipPlans, selection.shipPlanIndex);
    }

    /* ── Order detail: negotiation flow ── */
    if (isOrder) {
      return buildOrderElements(negotiations, selection.partName, selection.supplierId);
    }

    /* ── Overview mode ── */
    if (isOverview) {
      const nodeIds = new Set(nodes.map((n) => n.id));

      const nodeEls: ElementDefinition[] = nodes.map((n) => {
        // Analytics classes
        let analyticsClass = "";
        if (analyticsMode === "risk") {
          const score = n.reliabilityScore;
          if (score === undefined) analyticsClass = "risk-unknown";
          else if (score >= 0.7) analyticsClass = "risk-high";
          else if (score >= 0.4) analyticsClass = "risk-med";
          else analyticsClass = "risk-low";
        }
        if (analyticsMode === "bottleneck") {
          // Compute degree (edges connected to this node)
          const degree = overviewEdges.reduce((count, ae) => {
            if (ae.source === n.id || ae.target === n.id) return count + ae.totalMessages;
            return count;
          }, 0);
          if (degree >= 10) analyticsClass = "bottleneck-critical";
          else if (degree >= 5) analyticsClass = "bottleneck-high";
          else analyticsClass = "bottleneck-normal";
        }

        return {
          data: {
            id: n.id,
            label: analyticsMode === "risk" && n.reliabilityScore !== undefined
              ? `${n.label}\n${(n.reliabilityScore * 100).toFixed(0)}% / ESG: ${n.esgRating ?? "?"}`
              : n.label,
            role: n.role,
            framework: n.framework ?? "",
            skills: (n.skills ?? []).join(", "),
            reliabilityScore: n.reliabilityScore ?? 0,
          },
          classes: analyticsClass,
        };
      });

      // Filter out edges whose source or target node doesn't exist yet
      const safeEdges = overviewEdges.filter(
        (ae) => nodeIds.has(ae.source) && nodeIds.has(ae.target),
      );

      const edgeEls: ElementDefinition[] = safeEdges.map((ae) => {
        const dominant = dominantEdgeType(ae.counts);
        let sizeClass = ae.totalMessages > 15 ? "agg-lg" : ae.totalMessages > 5 ? "agg-md" : "agg-sm";

        // Cost analytics: classify edges by total message volume as cost proxy
        if (analyticsMode === "cost") {
          if (ae.totalMessages >= 10) sizeClass += " cost-high";
          else if (ae.totalMessages >= 4) sizeClass += " cost-med";
          else sizeClass += " cost-low";
        }

        return {
          data: {
            id: ae.id,
            source: ae.source,
            target: ae.target,
            label: aggregatedLabel(ae.counts),
            edgeType: dominant,
          },
          classes: sizeClass,
        };
      });

      return [...nodeEls, ...edgeEls];
    }

    /* ── Agent detail mode (default) ── */
    const agentNodeIds = new Set(nodes.map((n) => n.id));

    const nodeEls: ElementDefinition[] = nodes.map((n) => {
      const classes: string[] = [];
      if (selection.agentId && n.id === selection.agentId) {
        classes.push("highlighted");
      } else if (detailNodeIds.size > 0 && !detailNodeIds.has(n.id)) {
        classes.push("dimmed");
      }
      return {
        data: {
          id: n.id,
          label: n.label,
          role: n.role,
          framework: n.framework ?? "",
          skills: (n.skills ?? []).join(", "),
        },
        classes: classes.join(" "),
      };
    });

    // Filter out edges whose source or target node doesn't exist
    const safeDetailEdges = detailEdges.filter(
      (e) => agentNodeIds.has(e.source) && agentNodeIds.has(e.target),
    );

    const edgeEls: ElementDefinition[] = safeDetailEdges.map((e) => ({
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        edgeType: e.edgeType,
        animated: e.animated ?? false,
      },
    }));

    return [...nodeEls, ...edgeEls];
  }, [isOverview, isLogistics, isOrder, nodes, overviewEdges, detailEdges, selection, detailNodeIds, shipPlans, negotiations, analyticsMode]);

  // ── Compute a key to detect when we need to rebuild the graph ──
  const elementKey = useMemo(() => {
    const mode = selection.mode;
    const ids = elements.map((el) => el.data?.id ?? "").join(",");
    return `${mode}::${analyticsMode}::${ids}`;
  }, [selection.mode, analyticsMode, elements]);

  // ── Build / rebuild Cytoscape ──
  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy previous instance if the element set changed fundamentally
    if (cyRef.current && prevElementKey.current !== elementKey) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    if (cyRef.current) {
      // Just update elements incrementally
      const cy = cyRef.current;
      const existingIds = new Set<string>();
      cy.elements().forEach((el: any) => { existingIds.add(el.id()); });

      const newIds = new Set(elements.map((el) => el.data?.id as string).filter(Boolean));

      // Remove elements no longer present
      cy.elements().forEach((el: any) => {
        if (!newIds.has(el.id())) cy.remove(el);
      });

      // Add new elements — nodes first, then edges (to avoid referencing missing nodes)
      const newNodes = elements.filter((el) => !el.data?.source && el.data?.id && !existingIds.has(el.data.id as string));
      const newEdges = elements.filter((el) => el.data?.source && el.data?.id && !existingIds.has(el.data.id as string));
      for (const el of newNodes) cy.add(el);
      // Re-read existing IDs after adding nodes
      const updatedIds = new Set<string>();
      cy.elements().forEach((e: any) => { updatedIds.add(e.id()); });
      for (const el of newEdges) {
        const src = el.data?.source as string;
        const tgt = el.data?.target as string;
        if (updatedIds.has(src) && updatedIds.has(tgt)) {
          cy.add(el);
        }
      }

      return;
    }

    // ── Fresh Cytoscape instance ──
    const stylesheet = buildStylesheet(selection.mode, analyticsMode);

    // Choose layout based on mode
    let layoutOpts: any;
    if (isOverview) {
      layoutOpts = {
        name: "concentric",
        concentric: (node: any) => {
          const role = node.data("role");
          if (role === "procurement") return 10;
          if (role === "index") return 5;
          return 1;
        },
        levelWidth: () => 1,
        animate: true,
        animationDuration: 500,
        padding: 50,
        minNodeSpacing: 60,
      };
    } else if (isLogistics) {
      layoutOpts = {
        name: "breadthfirst",
        directed: true,
        animate: true,
        animationDuration: 500,
        padding: 50,
        spacingFactor: 1.5,
        avoidOverlap: true,
      };
    } else if (isOrder) {
      layoutOpts = {
        name: "breadthfirst",
        directed: true,
        animate: true,
        animationDuration: 500,
        padding: 60,
        spacingFactor: 1.8,
        avoidOverlap: true,
      };
    } else {
      layoutOpts = {
        name: "cose",
        animate: true,
        animationDuration: 500,
        nodeRepulsion: () => 6000,
        idealEdgeLength: () => 100,
        gravity: 0.4,
        padding: 40,
        randomize: false,
        componentSpacing: 60,
        nodeOverlap: 20,
      };
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: stylesheet,
      layout: layoutOpts,
      minZoom: 0.3,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    });

    cyRef.current = cy;
    prevElementKey.current = elementKey;

    // ── Tooltip on hover ──
    cy.on("mouseover", "node", (evt) => {
      const node = evt.target;
      const role = node.data("role");
      const tooltipParts = [node.data("label")];

      if (role && role !== "hub" && role !== "step") {
        tooltipParts.push(`Role: ${role}`);
        if (node.data("framework")) tooltipParts.push(`Framework: ${node.data("framework")}`);
        if (node.data("skills")) tooltipParts.push(`Skills: ${node.data("skills")}`);
        if (analyticsMode === "risk" && node.data("reliabilityScore")) {
          tooltipParts.push(`Reliability: ${(node.data("reliabilityScore") * 100).toFixed(0)}%`);
        }
      }

      containerRef.current!.title = tooltipParts.filter(Boolean).join("\n");

      // In overview, highlight connected edges
      if (isOverview) {
        node.addClass("hovered");
        node.connectedEdges().addClass("hovered-edge");
        cy.elements().not(node).not(node.connectedEdges()).not(node.connectedEdges().connectedNodes()).addClass("dimmed");
      }
    });

    cy.on("mouseout", "node", () => {
      containerRef.current!.title = "";
      if (isOverview) {
        cy.elements().removeClass("dimmed hovered hovered-edge");
      }
    });

    // ── Click to drill down (overview mode only) ──
    cy.on("tap", "node", (evt) => {
      if (isOverview) {
        const nodeId = evt.target.id();
        onSelectAgent(nodeId);
      }
    });

    // Cursor style for overview nodes
    if (isOverview) {
      cy.on("mouseover", "node", () => {
        if (containerRef.current) containerRef.current.style.cursor = "pointer";
      });
      cy.on("mouseout", "node", () => {
        if (containerRef.current) containerRef.current.style.cursor = "default";
      });
    }

    // ── Fit after layout — start a bit more zoomed out ──
    setTimeout(() => {
      cy.fit(undefined, 80);

      // ── Dynamic node scaling on zoom (semantic zoom) ──
      // Keeps nodes at a readable screen size regardless of zoom level.
      const initialZoom = cy.zoom();
      const roleBaseSizes: Record<string, number> = {
        procurement: isOverview ? 55 : 50,
        supplier: isOverview ? 50 : 45,
        logistics: isOverview ? 50 : 45,
        index: isOverview ? 50 : 45,
      };
      const defaultBase = isOverview ? 50 : isLogistics ? 45 : 50;

      let rafPending = false;
      cy.on("zoom", () => {
        if (rafPending) return;
        rafPending = true;
        requestAnimationFrame(() => {
          rafPending = false;
          const zoom = cy.zoom();
          // Ratio > 1 when zoomed in past initial, < 1 when zoomed out
          const ratio = initialZoom / zoom;
          // Gentle scaling: nodes shrink slightly when zoomed in, grow when zoomed out
          const scale = Math.max(0.5, Math.min(2.0, Math.pow(ratio, 0.35)));

          cy.batch(() => {
            cy.nodes().forEach((node: any) => {
              const role = node.data("role");
              if (role === "hub" || role === "step") return;
              const isHighlighted = node.hasClass("highlighted");
              const base = roleBaseSizes[role] ?? defaultBase;
              const sz = Math.round(base * scale);
              node.style({
                width: isHighlighted ? sz + 10 : sz,
                height: isHighlighted ? sz + 10 : sz,
              });
            });
          });
        });
      });
    }, 600);

    return () => {
      // Don't destroy on cleanup -- we manage lifecycle via elementKey
    };
  }, [elementKey, elements, isOverview, isLogistics, isOrder, onSelectAgent, selection.mode, analyticsMode]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, []);

  // ── Build detail title ──
  const detailTitle = useMemo(() => {
    if (isOverview) return null;
    if (selection.mode === "agent-detail") {
      const agent = nodes.find((n) => n.id === selection.agentId);
      return agent ? `${agent.label} \u2014 ${detailEdges.length} interactions` : "Agent Detail";
    }
    if (selection.mode === "order-detail") {
      const neg = negotiations.find(
        (n) => n.part.toLowerCase() === (selection.partName ?? "").toLowerCase() && n.supplier === selection.supplierId,
      );
      const status = neg ? (neg.accepted ? "\u2705 Accepted" : neg.rejected ? "\u274C Rejected" : "\u23F3 Pending") : "";
      return `Order: ${selection.partName} \u2014 ${neg?.supplierName ?? selection.supplierId ?? ""} ${status}`;
    }
    if (selection.mode === "logistics-detail") {
      if (selection.shipPlanIndex !== undefined) {
        const sp = shipPlans[selection.shipPlanIndex];
        return sp
          ? `Route: ${sp.pickup} \u2192 ${sp.delivery} \u2014 ${sp.route.length} stops, ${sp.transitTimeDays ?? "?"}d`
          : "Route Detail";
      }
      return `Logistics Network \u2014 ${shipPlans.length} routes`;
    }
    return "Detail View";
  }, [isOverview, selection, nodes, detailEdges, shipPlans, negotiations]);

  // ── Analytics badge ──
  const analyticsBadge = useMemo(() => {
    if (analyticsMode === "none" || !isOverview) return null;
    const labels: Record<AnalyticsMode, string> = {
      none: "",
      risk: "Risk Heatmap \u2014 node color = reliability score",
      cost: "Cost Flow \u2014 edge thickness = message volume",
      bottleneck: "Bottleneck Detection \u2014 node size = connection degree",
    };
    return labels[analyticsMode];
  }, [analyticsMode, isOverview]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {/* ── Back button (detail mode only) ── */}
      {!isOverview && (
        <button
          onClick={onBack}
          className="absolute top-3 left-3 z-10 flex items-center gap-1.5 rounded-lg bg-slate-800/90 px-3 py-1.5 text-xs font-medium text-slate-300 shadow-lg backdrop-blur-sm transition-colors hover:bg-slate-700 hover:text-white"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to Overview
        </button>
      )}

      {/* ── Detail title badge ── */}
      {!isOverview && detailTitle && (
        <div className="absolute top-3 left-1/2 z-10 -translate-x-1/2 rounded-lg bg-slate-800/90 px-4 py-1.5 text-xs font-medium text-slate-200 shadow-lg backdrop-blur-sm">
          {detailTitle}
        </div>
      )}

      {/* ── Analytics overlay badge ── */}
      {analyticsBadge && (
        <div className="absolute top-3 left-1/2 z-10 -translate-x-1/2 rounded-lg bg-slate-800/90 px-4 py-1.5 text-xs font-medium text-amber-300 shadow-lg backdrop-blur-sm">
          {analyticsBadge}
        </div>
      )}

      {/* ── Overview hint ── */}
      {isOverview && nodes.length > 0 && !analyticsBadge && (
        <div className="absolute top-3 right-3 z-10 rounded-lg bg-slate-800/80 px-3 py-1.5 text-[0.6rem] text-slate-400 backdrop-blur-sm">
          Click a node to drill down
        </div>
      )}

      {/* ── Logistics detail legend ── */}
      {isLogistics && (
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg bg-slate-900/80 px-3 py-2 text-xs backdrop-blur-sm">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-orange-400" />
            <span className="text-slate-300">Origin</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-slate-500" />
            <span className="text-slate-300">Transit Hub</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-emerald-400" />
            <span className="text-slate-300">Destination</span>
          </span>
          <span className="ml-2 border-l border-slate-600 pl-2 flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-3 border-orange-400" />
            <span className="text-slate-300">Standard</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-3 border-red-400" />
            <span className="text-slate-300">Express</span>
          </span>
        </div>
      )}

      {/* ── Order detail legend ── */}
      {isOrder && (
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg bg-slate-900/80 px-3 py-2 text-xs backdrop-blur-sm">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-sky-400" />
            <span className="text-slate-300">RFQ</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-emerald-400" />
            <span className="text-slate-300">Quote</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-dashed border-orange-400" />
            <span className="text-slate-300">Counter</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-green-400" />
            <span className="text-slate-300">Accept</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-cyan-400" />
            <span className="text-slate-300">Order</span>
          </span>
        </div>
      )}

      {/* ── Default overview legend ── */}
      {isOverview && (
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg bg-slate-900/80 px-3 py-2 text-xs backdrop-blur-sm">
          {Object.entries(ROLE_COLORS)
            .filter(([role]) => role !== "hub" && role !== "step")
            .map(([role, color]) => (
              <span key={role} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{
                    backgroundColor: color,
                    clipPath: role === "procurement" ? "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" : role === "logistics" ? "polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)" : undefined,
                    borderRadius: role === "supplier" ? "50%" : role === "index" ? "3px" : undefined,
                  }}
                />
                <span className="capitalize text-slate-300">{role}</span>
              </span>
            ))}
          <span className="ml-2 border-l border-slate-600 pl-2 flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-dashed border-purple-400" />
            <span className="text-slate-300">Discovery</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-sky-400" />
            <span className="text-slate-300">RFQ/Quote</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-emerald-400" />
            <span className="text-slate-300">Contract</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-orange-400" />
            <span className="text-slate-300">Logistics</span>
          </span>
        </div>
      )}

      {/* Empty state */}
      {nodes.length === 0 && isOverview && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <svg className="mx-auto mb-3 h-12 w-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            <p className="text-sm">Waiting for agents to register...</p>
            <p className="mt-1 text-xs text-slate-600">Nodes appear as agents join the network</p>
          </div>
        </div>
      )}

      {/* Empty logistics state */}
      {isLogistics && shipPlans.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <svg className="mx-auto mb-3 h-12 w-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
            </svg>
            <p className="text-sm">No shipping plans yet</p>
            <p className="mt-1 text-xs text-slate-600">Routes appear when logistics plans are received</p>
          </div>
        </div>
      )}

      {/* Empty order state */}
      {isOrder && elements.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <svg className="mx-auto mb-3 h-12 w-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
            <p className="text-sm">No negotiation data for this order</p>
            <p className="mt-1 text-xs text-slate-600">Negotiation flow appears after RFQ/Quote exchange</p>
          </div>
        </div>
      )}
    </div>
  );
}
