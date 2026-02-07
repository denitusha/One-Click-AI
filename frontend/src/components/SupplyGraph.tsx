import { useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  MarkerType,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Eye,
  EyeOff,
  Database,
  Cpu,
  Crosshair,
  Package,
  Factory,
  Truck,
  ShieldCheck,
  FileText,
} from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

// ── Edge type definitions ─────────────────────────────────────────────
type EdgeCategory = "material_flow" | "contractual" | "routing" | "information";

const EDGE_CATEGORIES: Record<EdgeCategory, { label: string; color: string; activeColor: string; dash: string; icon: string }> = {
  material_flow: { label: "Material Flow",   color: "#00e676", activeColor: "#00e676cc", dash: "",         icon: "◈" },
  contractual:   { label: "Contractual",      color: "#ffd700", activeColor: "#ffd700cc", dash: "8 4",     icon: "◇" },
  routing:       { label: "Routing Path",     color: "#ff9800", activeColor: "#ff9800cc", dash: "4 4",     icon: "→" },
  information:   { label: "Info Exchange",    color: "#00bcd4", activeColor: "#00bcd4cc", dash: "2 3 6 3", icon: "◎" },
};

// ── Custom labeled edge ───────────────────────────────────────────────
function CategoryEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const category = (data?.category as EdgeCategory) || "material_flow";
  const edgeLabel = data?.edgeLabel as string | undefined;
  const catConfig = EDGE_CATEGORIES[category];

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
      {edgeLabel && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="edge-label-tag"
          >
            <span
              className="px-1.5 py-0.5 rounded text-[8px] font-mono font-medium whitespace-nowrap"
              style={{
                background: `${catConfig.color}18`,
                color: `${catConfig.color}bb`,
                border: `1px solid ${catConfig.color}30`,
              }}
            >
              {edgeLabel}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const edgeTypes = { category: CategoryEdge };

// ── Node styling ───────────────────────────────────────────────────────
const ROLE_CONFIG: Record<string, { badge: string; color: string; badgeBg: string; Icon: typeof Database }> = {
  procurement:  { badge: "PROC", color: "#00e676", badgeBg: "#00e676",  Icon: Crosshair },
  supplier:     { badge: "SUPP", color: "#00e676", badgeBg: "#00e676",  Icon: Package },
  manufacturer: { badge: "MFGR", color: "#60a5fa", badgeBg: "#60a5fa",  Icon: Factory },
  logistics:    { badge: "LOGI", color: "#ff9800", badgeBg: "#ff9800",  Icon: Truck },
  compliance:   { badge: "COMP", color: "#a855f7", badgeBg: "#a855f7",  Icon: ShieldCheck },
  registry:     { badge: "INDEX", color: "#a855f7", badgeBg: "#a855f7", Icon: Database },
  resolver:     { badge: "RSLV", color: "#00bcd4", badgeBg: "#00bcd4",  Icon: Cpu },
};

function AgentNode({ data }: { data: Record<string, unknown> }) {
  const role = (data.role as string) || "procurement";
  const cfg = ROLE_CONFIG[role] || ROLE_CONFIG.procurement;
  const active = data.active as boolean;
  const highlighted = data.highlighted as boolean;
  const port = data.port as string | undefined;
  const framework = data.framework as string;
  const Icon = cfg.Icon;

  return (
    <div className={`relative ${active ? "agent-active" : ""} ${highlighted ? "agent-highlighted" : ""}`}>
      <Handle type="target" position={Position.Left} className="!bg-white/20 !w-1.5 !h-1.5 !border-0" />

      {/* Role badge floating on top */}
      <div
        className="absolute -top-3 left-1/2 -translate-x-1/2 z-10 px-2 py-0.5 rounded text-[8px] font-bold font-mono tracking-wider whitespace-nowrap"
        style={{
          background: cfg.badgeBg,
          color: "#0a0f1a",
        }}
      >
        {cfg.badge}
      </div>

      {/* Card */}
      <div
        className={`flex flex-col items-center px-5 pt-5 pb-3 rounded-xl border transition-all duration-300 ${
          highlighted
            ? "ring-2 ring-white/30 bg-white/[0.06] border-white/20"
            : active
              ? "bg-panel-card/80 border-white/15"
              : "bg-panel-card/60 border-white/[0.08]"
        }`}
        style={{ minWidth: 130 }}
      >
        {/* Icon box */}
        <div
          className={`w-12 h-12 rounded-lg flex items-center justify-center border-2 mb-2.5 transition-all duration-300 ${
            highlighted ? "scale-110" : ""
          }`}
          style={{
            background: `${cfg.color}15`,
            borderColor: active || highlighted ? cfg.color : `${cfg.color}44`,
            boxShadow: highlighted ? `0 0 20px ${cfg.color}44` : "none",
          }}
        >
          <Icon size={22} style={{ color: cfg.color }} />
        </div>

        {/* Label */}
        <div className={`text-[12px] font-semibold text-center leading-tight max-w-[130px] mb-1 transition-colors duration-300 ${
          highlighted ? "text-white" : "text-white/85"
        }`}>
          {data.label as string}
        </div>

        {/* Framework · Port */}
        <div className="text-[9px] text-white/35 font-mono mb-2">
          {framework}{port ? ` · :${port}` : ""}
        </div>

        {/* Status */}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-1.5 h-1.5 rounded-full ${active ? "bg-accent-green animate-pulse" : "bg-white/20"}`}
          />
          <span className={`text-[9px] font-mono uppercase tracking-wider ${active ? "text-accent-green/80" : "text-white/25"}`}>
            {active ? "Active" : "Idle"}
          </span>
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-white/20 !w-1.5 !h-1.5 !border-0" />
    </div>
  );
}

// ── Order Node ───────────────────────────────────────────────────────────
function OrderNode({ data }: { data: Record<string, unknown> }) {
  const orderId = data.label as string;
  const price = data.price as number;
  const status = data.status as string;
  const highlighted = data.highlighted as boolean;

  const statusConfig: Record<string, { color: string; label: string }> = {
    placed: { color: "#ffd700", label: "Placed" },
    manufacturing: { color: "#ff9800", label: "Mfg" },
    shipped: { color: "#00bcd4", label: "Shipped" },
    complete: { color: "#00e676", label: "✓" },
  };

  const statusCfg = statusConfig[status] || statusConfig.placed;

  return (
    <div className={`relative ${highlighted ? "agent-highlighted" : ""}`}>
      <Handle type="target" position={Position.Left} className="!bg-white/20 !w-1.5 !h-1.5 !border-0" />

      <div
        className={`flex flex-col items-center px-4 pt-4 pb-3 rounded-xl border transition-all duration-300 ${
          highlighted
            ? "ring-2 ring-white/30 bg-white/[0.06] border-white/20"
            : "bg-panel-card/60 border-white/[0.08]"
        }`}
        style={{ minWidth: 120 }}
      >
        {/* Icon box */}
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center border-2 mb-2 transition-all duration-300 ${
            highlighted ? "scale-110" : ""
          }`}
          style={{
            background: `${statusCfg.color}15`,
            borderColor: highlighted ? statusCfg.color : `${statusCfg.color}44`,
            boxShadow: highlighted ? `0 0 20px ${statusCfg.color}44` : "none",
          }}
        >
          <FileText size={18} style={{ color: statusCfg.color }} />
        </div>

        {/* Order ID */}
        <div className="text-[11px] font-mono font-semibold text-white/85 text-center leading-tight">
          {orderId}
        </div>

        {/* Price */}
        <div className="text-[9px] text-white/40 font-mono mt-1">
          ${(price / 1000).toFixed(1)}M
        </div>

        {/* Status badge */}
        <div
          className="text-[8px] font-mono font-semibold px-1.5 py-0.5 rounded mt-1.5 whitespace-nowrap"
          style={{
            background: `${statusCfg.color}20`,
            color: statusCfg.color,
          }}
        >
          {statusCfg.label}
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-white/20 !w-1.5 !h-1.5 !border-0" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode, order: OrderNode };

// ── Graph layout ──────────────────────────────────────────────────────
const DEFAULT_NODES: Node[] = [
  {
    id: "nanda-index",
    type: "agent",
    position: { x: 350, y: 10 },
    data: { label: "NANDA Index", role: "registry", framework: "FastAPI", port: "6900", active: false },
  },
  {
    id: "nanda-resolver",
    type: "agent",
    position: { x: 620, y: 10 },
    data: { label: "Adaptive Resolver", role: "resolver", framework: "FastAPI", port: "6900", active: false },
  },
  {
    id: "nanda:procurement-agent",
    type: "agent",
    position: { x: 20, y: 230 },
    data: { label: "Procurement Agent", role: "procurement", framework: "LangGraph", port: "6010", active: false },
  },
  {
    id: "nanda:supplier-agent-1",
    type: "agent",
    position: { x: 300, y: 140 },
    data: { label: "Supplier A", role: "supplier", framework: "CrewAI", port: "6001", active: false },
  },
  {
    id: "nanda:supplier-agent-2",
    type: "agent",
    position: { x: 300, y: 360 },
    data: { label: "Supplier B", role: "supplier", framework: "Custom Python", port: "6002", active: false },
  },
  {
    id: "nanda:manufacturer-agent",
    type: "agent",
    position: { x: 600, y: 240 },
    data: { label: "Manufacturer", role: "manufacturer", framework: "LangGraph", port: "6005", active: false },
  },
  {
    id: "nanda:logistics-agent",
    type: "agent",
    position: { x: 600, y: 440 },
    data: { label: "Logistics Agent", role: "logistics", framework: "AutoGen", port: "6004", active: false },
  },
  {
    id: "nanda:compliance-agent",
    type: "agent",
    position: { x: 880, y: 240 },
    data: { label: "Compliance Agent", role: "compliance", framework: "LangGraph", port: "6006", active: false },
  },
];

function makeEdge(
  id: string,
  source: string,
  target: string,
  category: EdgeCategory,
  edgeLabel: string
): Edge {
  const cat = EDGE_CATEGORIES[category];
  return {
    id,
    source,
    target,
    type: "category",
    animated: false,
    data: { category, edgeLabel },
    style: {
      stroke: `${cat.color}22`,
      strokeWidth: 1,
      strokeDasharray: cat.dash,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: `${cat.color}44` },
  };
}

const DEFAULT_EDGES: Edge[] = [
  // Information Exchange
  makeEdge("e1",  "nanda:procurement-agent", "nanda-index",              "information",   "Discovery"),
  makeEdge("e1b", "nanda-index",             "nanda-resolver",           "information",   "Resolution"),
  // Material Flow
  makeEdge("e2",  "nanda:procurement-agent", "nanda:supplier-agent-1",   "material_flow", "RFQ / Quotes"),
  makeEdge("e3",  "nanda:procurement-agent", "nanda:supplier-agent-2",   "material_flow", "RFQ / Quotes"),
  // Contractual
  makeEdge("e4",  "nanda:procurement-agent", "nanda:manufacturer-agent", "contractual",   "Order"),
  // Routing Path
  makeEdge("e5",  "nanda:manufacturer-agent","nanda:logistics-agent",    "routing",       "Shipping"),
  // Information Exchange
  makeEdge("e6",  "nanda:manufacturer-agent","nanda:compliance-agent",   "information",   "Compliance"),
];

// ── Component ─────────────────────────────────────────────────────────
interface Props {
  events: WsEvent[];
  highlightedAgentId?: string | null;
  selectedOrderId?: string | null;
}

export default function SupplyGraph({ events, highlightedAgentId, selectedOrderId }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState(DEFAULT_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState(DEFAULT_EDGES);
  const [showLegend, setShowLegend] = useState(true);

  useEffect(() => {
    const activeIds = new Set<string>();
    const activeEdgePairs = new Set<string>();

    // Extract orders from events
    const orders: Record<string, { orderId: string; price: number; status: string; agents: Set<string> }> = {};
    const orderAgents: Record<string, Set<string>> = {};

    for (const evt of events) {
      if (evt.type === "agent_message" && evt.data) {
        const sender = evt.data.sender_id as string;
        const receiver = evt.data.receiver_id as string;
        const msgType = evt.data.message_type as string;
        const payload = evt.data.payload as Record<string, unknown>;
        const orderId = (payload?.order_id as string) || "";

        activeIds.add(sender);
        activeIds.add(receiver);
        if (!sender.startsWith("nanda:")) activeIds.add(`nanda:${sender}`);
        if (!receiver.startsWith("nanda:")) activeIds.add(`nanda:${receiver}`);
        activeEdgePairs.add(`${sender}->${receiver}`);
        activeEdgePairs.add(`nanda:${sender}->nanda:${receiver}`);

        // Track orders
        if (msgType === "order_placement" && orderId) {
          if (!orders[orderId]) {
            orders[orderId] = {
              orderId,
              price: (payload.agreed_price as number) || 0,
              status: "placed",
              agents: new Set(),
            };
            orderAgents[orderId] = new Set();
          }
          // Normalize sender/receiver for agent set
          const normalizedSender = sender.startsWith("nanda:") ? sender : `nanda:${sender}`;
          const normalizedReceiver = receiver.startsWith("nanda:") ? receiver : `nanda:${receiver}`;
          orderAgents[orderId].add(normalizedSender);
          orderAgents[orderId].add(normalizedReceiver);
        }

        // Update order status based on message type
        if (orderId && orders[orderId]) {
          if (msgType === "order_confirmation") {
            orders[orderId].status = "complete";
          } else if (msgType === "route_confirmation") {
            orders[orderId].status = "shipped";
          } else if (msgType === "compliance_result" || msgType === "shipping_request") {
            orders[orderId].status = "manufacturing";
          }
          // Track all agents involved in the order
          const normalizedSender = sender.startsWith("nanda:") ? sender : `nanda:${sender}`;
          const normalizedReceiver = receiver.startsWith("nanda:") ? receiver : `nanda:${receiver}`;
          orderAgents[orderId].add(normalizedSender);
          orderAgents[orderId].add(normalizedReceiver);
        }
      }
    }

    // Also light up index/resolver whenever discovery happens
    if (events.some((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "discovery_request")) {
      activeIds.add("nanda-index");
      activeIds.add("nanda-resolver");
    }

    // Build node list with dynamic order nodes
    const nodesList: Node[] = DEFAULT_NODES.map((n) => ({ ...n }));

    if (Object.keys(orders).length > 0) {
      const firstOrder = Object.values(orders)[0];
      nodesList.push({
        id: `order-${firstOrder.orderId}`,
        type: "order",
        position: { x: 450, y: 240 },
        data: {
          label: firstOrder.orderId,
          price: firstOrder.price,
          status: firstOrder.status,
          highlighted: selectedOrderId === firstOrder.orderId,
        },
      });
    }

    setNodes((nds) => {
      // Update existing agent nodes
      const updated = nds.map((n) => {
        if (n.type === "order") {
          // Update order node
          const firstOrder = Object.values(orders)[0];
          return {
            ...n,
            data: {
              ...n.data,
              highlighted: selectedOrderId === firstOrder?.orderId,
            },
          };
        }
        return {
          ...n,
          data: {
            ...n.data,
            active: activeIds.has(n.id),
            highlighted: highlightedAgentId === n.id,
          },
        };
      });

      // Add new order node if it doesn't exist
      if (Object.keys(orders).length > 0 && !updated.some((n) => n.type === "order")) {
        const firstOrder = Object.values(orders)[0];
        updated.push({
          id: `order-${firstOrder.orderId}`,
          type: "order",
          position: { x: 450, y: 240 },
          data: {
            label: firstOrder.orderId,
            price: firstOrder.price,
            status: firstOrder.status,
            highlighted: selectedOrderId === firstOrder.orderId,
          },
        });
      }

      return updated;
    });

    // Build edges with order connections
    const edgesList: Edge[] = DEFAULT_EDGES.map((e) => ({ ...e }));

    // Add order edges
    if (Object.keys(orders).length > 0) {
      const firstOrder = Object.values(orders)[0];
      const agentsInOrder = orderAgents[firstOrder.orderId] || new Set();

      // Create edges from order to each agent involved
      const agentConnections = [
        "nanda:procurement-agent",
        "nanda:supplier-agent-1",
        "nanda:manufacturer-agent",
        "nanda:compliance-agent",
        "nanda:logistics-agent",
      ];

      for (const agent of agentConnections) {
        if (agentsInOrder.has(agent)) {
          edgesList.push({
            id: `order-edge-${agent}`,
            source: `order-${firstOrder.orderId}`,
            target: agent,
            type: "category",
            animated: false,
            data: { category: "contractual", edgeLabel: "Order Flow" },
            style: {
              stroke: "#ffd70022",
              strokeWidth: 1,
              strokeDasharray: "8 4",
            },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#ffd70044" },
          });
        }
      }
    }

    setEdges((eds) => {
      return edgesList.map((e) => {
        const pair = `${e.source}->${e.target}`;
        const isActive = activeEdgePairs.has(pair);
        const isOrderRelated = e.source?.startsWith("order-") || e.target?.startsWith("order-");
        const isOrderSelected = selectedOrderId && (e.source?.includes(selectedOrderId) || e.target?.includes(selectedOrderId));
        const isHighlightEdge =
          highlightedAgentId != null && (e.source === highlightedAgentId || e.target === highlightedAgentId);
        const category = (e.data?.category as EdgeCategory) || "material_flow";
        const cat = EDGE_CATEGORIES[category];

        return {
          ...e,
          animated: false,
          style: {
            ...e.style,
            stroke: isOrderSelected
              ? cat.activeColor
              : isHighlightEdge
                ? cat.activeColor
                : isActive || isOrderRelated
                  ? `${cat.color}bb`
                  : `${cat.color}22`,
            strokeWidth: isOrderSelected || isHighlightEdge ? 3 : isActive || isOrderRelated ? 2 : 1,
            strokeDasharray: cat.dash,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: isOrderSelected
              ? cat.activeColor
              : isHighlightEdge
                ? cat.activeColor
                : isActive || isOrderRelated
                  ? `${cat.color}bb`
                  : `${cat.color}44`,
          },
        };
      });
    });
  }, [events, highlightedAgentId, selectedOrderId, setNodes, setEdges]);

  return (
    <div className="h-full w-full rounded-lg overflow-hidden border border-panel-border bg-panel-dark relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#ffffff08" gap={24} />
        <Controls
          className="!bg-panel-card !border-panel-border !text-white/50 [&>button]:!bg-panel-card [&>button]:!border-panel-border [&>button]:!text-white/50 [&>button:hover]:!bg-panel-hover"
        />
      </ReactFlow>

      {/* ── Edge Legend ──────────────────────────────────────────── */}
      <div className="absolute bottom-3 right-3 z-10">
        <button
          onClick={() => setShowLegend((v) => !v)}
          className="mb-1.5 ml-auto flex items-center gap-1 px-2 py-1 rounded text-[9px] font-mono text-white/40 hover:text-white/60 bg-panel-card/80 border border-panel-border hover:border-white/20 transition-all cursor-pointer"
        >
          {showLegend ? <EyeOff size={10} /> : <Eye size={10} />}
          {showLegend ? "Hide" : "Legend"}
        </button>

        {showLegend && (
          <div className="bg-panel-card/90 backdrop-blur-sm border border-panel-border rounded-lg p-2.5 space-y-1.5">
            <div className="text-[9px] font-mono text-white/30 uppercase tracking-wider mb-1">
              Edge Types
            </div>
            {(Object.entries(EDGE_CATEGORIES) as [EdgeCategory, typeof EDGE_CATEGORIES[EdgeCategory]][]).map(
              ([key, cat]) => (
                <div key={key} className="flex items-center gap-2">
                  <svg width="28" height="8" className="shrink-0">
                    <line
                      x1="0" y1="4" x2="28" y2="4"
                      stroke={cat.color}
                      strokeWidth="2"
                      strokeDasharray={cat.dash || "none"}
                      opacity={0.7}
                    />
                  </svg>
                  <span className="text-[9px] font-mono" style={{ color: `${cat.color}aa` }}>
                    {cat.label}
                  </span>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}
