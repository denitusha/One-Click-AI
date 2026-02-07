import { useEffect } from "react";
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
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { WsEvent } from "../hooks/useWebSocket";

// ── Node styling ───────────────────────────────────────────────────────
const ROLE_STYLES: Record<string, { bg: string; border: string; letter: string }> = {
  procurement:  { bg: "#00e67620", border: "#00e676",  letter: "P" },
  supplier:     { bg: "#00e67620", border: "#00e676",  letter: "S" },
  manufacturer: { bg: "#0f346040", border: "#0f3460",  letter: "M" },
  logistics:    { bg: "#ff980020", border: "#ff9800",  letter: "L" },
  compliance:   { bg: "#a855f720", border: "#a855f7",  letter: "C" },
  registry:     { bg: "#a855f720", border: "#a855f7",  letter: "◆" },
  resolver:     { bg: "#00bcd420", border: "#00bcd4",  letter: "R" },
};

function AgentNode({ data }: { data: Record<string, unknown> }) {
  const role = (data.role as string) || "procurement";
  const style = ROLE_STYLES[role] || ROLE_STYLES.procurement;
  const active = data.active as boolean;

  return (
    <div className={`relative ${active ? "agent-active" : ""}`}>
      <Handle type="target" position={Position.Left} className="!bg-white/20 !w-1.5 !h-1.5 !border-0" />

      <div
        className="flex flex-col items-center gap-1.5 px-3 py-2.5"
        style={{ minWidth: 100 }}
      >
        {/* Icon circle */}
        <div
          className="w-12 h-12 rounded-lg flex items-center justify-center text-lg font-bold border-2"
          style={{
            background: style.bg,
            borderColor: active ? style.border : `${style.border}66`,
            color: style.border,
          }}
        >
          {style.letter}
        </div>

        {/* Label */}
        <div className="text-[11px] font-medium text-white/80 text-center leading-tight max-w-[120px]">
          {data.label as string}
        </div>

        {/* Framework tag */}
        <div className="text-[9px] text-white/30 font-mono">
          {data.framework as string}
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-white/20 !w-1.5 !h-1.5 !border-0" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

// ── Graph layout ──────────────────────────────────────────────────────
const DEFAULT_NODES: Node[] = [
  {
    id: "nanda-index",
    type: "agent",
    position: { x: 280, y: 10 },
    data: { label: "NANDA Index", role: "registry", framework: "FastAPI", active: false },
  },
  {
    id: "nanda-resolver",
    type: "agent",
    position: { x: 480, y: 10 },
    data: { label: "Adaptive Resolver", role: "resolver", framework: "FastAPI", active: false },
  },
  {
    id: "nanda:procurement-agent",
    type: "agent",
    position: { x: 20, y: 180 },
    data: { label: "Procurement Agent", role: "procurement", framework: "LangGraph", active: false },
  },
  {
    id: "nanda:supplier-agent-1",
    type: "agent",
    position: { x: 250, y: 140 },
    data: { label: "Supplier A", role: "supplier", framework: "AutoGen", active: false },
  },
  {
    id: "nanda:supplier-agent-2",
    type: "agent",
    position: { x: 250, y: 270 },
    data: { label: "Supplier B", role: "supplier", framework: "AutoGen", active: false },
  },
  {
    id: "nanda:manufacturer-agent",
    type: "agent",
    position: { x: 480, y: 200 },
    data: { label: "Manufacturer", role: "manufacturer", framework: "LangGraph", active: false },
  },
  {
    id: "nanda:logistics-agent",
    type: "agent",
    position: { x: 480, y: 340 },
    data: { label: "Logistics Agent", role: "logistics", framework: "AutoGen", active: false },
  },
  {
    id: "nanda:compliance-agent",
    type: "agent",
    position: { x: 680, y: 200 },
    data: { label: "Compliance Agent", role: "compliance", framework: "LangGraph", active: false },
  },
];

const edgeDefaults = { animated: false, style: { strokeWidth: 1 } };

const DEFAULT_EDGES: Edge[] = [
  { id: "e1", source: "nanda:procurement-agent", target: "nanda-index", ...edgeDefaults, style: { stroke: "#ffffff22" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#ffffff44" } },
  { id: "e1b", source: "nanda-index", target: "nanda-resolver", ...edgeDefaults, style: { stroke: "#00bcd422" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#00bcd444" } },
  { id: "e2", source: "nanda:procurement-agent", target: "nanda:supplier-agent-1", ...edgeDefaults, style: { stroke: "#00e67622" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#00e67644" } },
  { id: "e3", source: "nanda:procurement-agent", target: "nanda:supplier-agent-2", ...edgeDefaults, style: { stroke: "#00e67622" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#00e67644" } },
  { id: "e4", source: "nanda:procurement-agent", target: "nanda:manufacturer-agent", ...edgeDefaults, style: { stroke: "#0f346022" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#0f346044" } },
  { id: "e5", source: "nanda:manufacturer-agent", target: "nanda:logistics-agent", ...edgeDefaults, style: { stroke: "#ff980022" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#ff980044" } },
  { id: "e6", source: "nanda:manufacturer-agent", target: "nanda:compliance-agent", ...edgeDefaults, style: { stroke: "#a855f722" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#a855f744" } },
];

// ── Component ─────────────────────────────────────────────────────────
interface Props {
  events: WsEvent[];
}

export default function SupplyGraph({ events }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState(DEFAULT_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState(DEFAULT_EDGES);

  useEffect(() => {
    const activeIds = new Set<string>();
    const activeEdgePairs = new Set<string>();

    for (const evt of events) {
      if (evt.type === "agent_message" && evt.data) {
        const sender = evt.data.sender_id as string;
        const receiver = evt.data.receiver_id as string;
        activeIds.add(sender);
        activeIds.add(receiver);
        if (!sender.startsWith("nanda:")) activeIds.add(`nanda:${sender}`);
        if (!receiver.startsWith("nanda:")) activeIds.add(`nanda:${receiver}`);
        activeEdgePairs.add(`${sender}->${receiver}`);
        activeEdgePairs.add(`nanda:${sender}->nanda:${receiver}`);
      }
    }

    // Also light up index/resolver whenever discovery happens
    if (events.some((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "discovery_request")) {
      activeIds.add("nanda-index");
      activeIds.add("nanda-resolver");
    }

    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, active: activeIds.has(n.id) },
      }))
    );

    setEdges((eds) =>
      eds.map((e) => {
        const pair = `${e.source}->${e.target}`;
        const isActive = activeEdgePairs.has(pair);
        const baseStroke = (e.style?.stroke as string) || "#ffffff22";
        return {
          ...e,
          animated: isActive,
          style: {
            ...e.style,
            stroke: isActive ? baseStroke.replace("22", "bb").replace("44", "ff") : baseStroke,
            strokeWidth: isActive ? 2 : 1,
          },
        };
      })
    );
  }, [events, setNodes, setEdges]);

  return (
    <div className="h-full w-full rounded-lg overflow-hidden border border-panel-border bg-panel-dark">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#ffffff08" gap={24} />
        <Controls
          showMinimap={false}
          className="!bg-panel-card !border-panel-border !text-white/50 [&>button]:!bg-panel-card [&>button]:!border-panel-border [&>button]:!text-white/50 [&>button:hover]:!bg-panel-hover"
        />
      </ReactFlow>
    </div>
  );
}
