import { useMemo, useState } from "react";
import { Map, AlertTriangle, TrendingUp, Zap } from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

interface Order {
  orderId: string;
  supplierName: string;
  price: number;
  status: "placed" | "manufacturing" | "shipped" | "complete";
}

interface GraphNode {
  id: string;
  label: string;
  role: string;
  status: "active" | "idle";
}

interface Props {
  events: WsEvent[];
  onSelectNode?: (nodeId: string | null) => void;
  selectedNodeId?: string | null;
}

export default function GraphNavigator({ events, onSelectNode, selectedNodeId }: Props) {
  const [expandedSection, setExpandedSection] = useState<"orders" | "agents" | null>("orders");

  // Extract orders
  const orders: Order[] = useMemo(() => {
    const orderMap: Record<string, Order> = {};
    const agentMessages = events.filter((e) => e.type === "agent_message");

    for (const evt of agentMessages) {
      const data = evt.data || {};
      const msgType = data.message_type as string;
      const payload = data.payload as Record<string, unknown>;
      const orderId = (payload.order_id as string) || "";

      if (msgType === "order_placement" && orderId && !orderMap[orderId]) {
        const supplierId = (payload.supplier_id as string) || "";
        orderMap[orderId] = {
          orderId,
          supplierName: supplierId
            .replace("nanda:", "")
            .replace("-agent", "")
            .split("-")
            .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" "),
          price: (payload.agreed_price as number) || 0,
          status: "placed",
        };
      }

      if (orderId && orderMap[orderId]) {
        if (msgType === "order_confirmation") {
          orderMap[orderId].status = "complete";
        } else if (msgType === "route_confirmation") {
          orderMap[orderId].status = "shipped";
        } else if (msgType === "compliance_result" || msgType === "shipping_request") {
          orderMap[orderId].status = "manufacturing";
        }
      }
    }

    return Object.values(orderMap).sort((a, b) => {
      const statusOrder = { complete: 0, shipped: 1, manufacturing: 2, placed: 3 };
      return statusOrder[a.status] - statusOrder[b.status];
    });
  }, [events]);

  // Extract active agents
  const activeAgents: GraphNode[] = useMemo(() => {
    const activeIds = new Set<string>();
    const agents: Record<string, GraphNode> = {
      "nanda-index": { id: "nanda-index", label: "NANDA Index", role: "registry", status: "idle" },
      "nanda-resolver": { id: "nanda-resolver", label: "Adaptive Resolver", role: "resolver", status: "idle" },
      "nanda:procurement-agent": { id: "nanda:procurement-agent", label: "Procurement", role: "procurement", status: "idle" },
      "nanda:supplier-agent-1": { id: "nanda:supplier-agent-1", label: "Supplier A", role: "supplier", status: "idle" },
      "nanda:supplier-agent-2": { id: "nanda:supplier-agent-2", label: "Supplier B", role: "supplier", status: "idle" },
      "nanda:manufacturer-agent": { id: "nanda:manufacturer-agent", label: "Manufacturer", role: "manufacturer", status: "idle" },
      "nanda:logistics-agent": { id: "nanda:logistics-agent", label: "Logistics", role: "logistics", status: "idle" },
      "nanda:compliance-agent": { id: "nanda:compliance-agent", label: "Compliance", role: "compliance", status: "idle" },
    };

    for (const evt of events) {
      if (evt.type === "agent_message" && evt.data) {
        const sender = evt.data.sender_id as string;
        const receiver = evt.data.receiver_id as string;
        if (sender) activeIds.add(sender.startsWith("nanda:") ? sender : `nanda:${sender}`);
        if (receiver) activeIds.add(receiver.startsWith("nanda:") ? receiver : `nanda:${receiver}`);
      }
    }

    if (events.some((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "discovery_request")) {
      activeIds.add("nanda-index");
      activeIds.add("nanda-resolver");
    }

    const result: GraphNode[] = [];
    for (const id of activeIds) {
      if (agents[id]) {
        result.push({ ...agents[id], status: "active" });
      }
    }
    return result.sort((a, b) => a.label.localeCompare(b.label));
  }, [events]);

  const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    complete: { bg: "bg-accent-green/10", text: "text-accent-green", dot: "bg-accent-green" },
    shipped: { bg: "bg-accent-cyan/10", text: "text-accent-cyan", dot: "bg-accent-cyan" },
    manufacturing: { bg: "bg-accent-orange/10", text: "text-accent-orange", dot: "bg-accent-orange" },
    placed: { bg: "bg-accent-gold/10", text: "text-accent-gold", dot: "bg-accent-gold" },
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-panel-dark/20">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 shrink-0 border-b border-panel-border/30">
        <Map size={12} className="text-accent-cyan" />
        <h3 className="text-[9px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
          Navigator
        </h3>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* Orders Section */}
        {orders.length > 0 && (
          <div className="px-2 py-2 border-b border-panel-border/20">
            <button
              onClick={() => setExpandedSection(expandedSection === "orders" ? null : "orders")}
              className="flex items-center gap-2 w-full text-left hover:bg-white/[0.03] px-2 py-1 rounded transition-all"
            >
              <Zap size={10} className="text-accent-cyan shrink-0" />
              <span className="text-[9px] font-mono font-semibold text-white/60 flex-1">ORDERS</span>
              <span
                className="w-4 h-4 rounded-full bg-accent-cyan/20 flex items-center justify-center text-[8px] font-bold text-accent-cyan shrink-0"
              >
                {orders.length}
              </span>
            </button>

            {expandedSection === "orders" && (
              <div className="mt-1 space-y-1">
                {orders.map((order, idx) => {
                  const cfg = statusColors[order.status];
                  const isSelected = selectedNodeId === `order-${order.orderId}`;
                  return (
                    <button
                      key={order.orderId}
                      onClick={() => onSelectNode?.(isSelected ? null : `order-${order.orderId}`)}
                      className={`w-full flex items-start gap-2 px-2 py-1.5 rounded text-[8px] border transition-all cursor-pointer ${
                        isSelected
                          ? `${cfg.bg} border-current ring-1 ring-offset-1 ring-offset-panel-dark ring-current`
                          : `border-panel-border/30 bg-panel-dark/40 hover:border-panel-border hover:bg-panel-dark/60`
                      }`}
                    >
                      <div className="flex items-center justify-center w-4 h-4 rounded-full bg-white/10 shrink-0 font-mono font-bold text-[7px]">
                        {idx + 1}
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <div className={`font-mono font-semibold truncate text-[8px] ${isSelected ? cfg.text : "text-white/70"}`}>
                          {order.orderId}
                        </div>
                        <div className="text-white/40 truncate text-[7px]">{order.supplierName}</div>
                        <div className="text-white/30 mt-0.5 text-[7px]">€{(order.price / 1000).toFixed(1)}M</div>
                      </div>
                      {isSelected && (
                        <div className="text-[8px] font-mono font-bold px-1 py-0.5 rounded bg-white/10">
                          ✓
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Agents Section */}
        {activeAgents.length > 0 && (
          <div className="px-2 py-2">
            <button
              onClick={() => setExpandedSection(expandedSection === "agents" ? null : "agents")}
              className="flex items-center gap-2 w-full text-left hover:bg-white/[0.03] px-2 py-1 rounded transition-all"
            >
              <TrendingUp size={10} className="text-accent-orange shrink-0" />
              <span className="text-[9px] font-mono font-semibold text-white/60 flex-1">AGENTS</span>
              <span
                className="w-4 h-4 rounded-full bg-accent-green/20 flex items-center justify-center text-[8px] font-bold text-accent-green shrink-0"
              >
                {activeAgents.length}
              </span>
            </button>

            {expandedSection === "agents" && (
              <div className="mt-1 space-y-1">
                {activeAgents.map((agent) => {
                  const isSelected = selectedNodeId === agent.id;
                  return (
                    <button
                      key={agent.id}
                      onClick={() => onSelectNode?.(isSelected ? null : agent.id)}
                      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-[8px] border transition-all cursor-pointer ${
                        isSelected
                          ? "bg-accent-green/15 border-accent-green/50 ring-1 ring-offset-1 ring-offset-panel-dark ring-accent-green"
                          : "border-panel-border/30 bg-panel-dark/40 hover:border-panel-border hover:bg-panel-dark/60"
                      }`}
                    >
                      <div className={`w-1 h-1 rounded-full shrink-0 ${isSelected ? "bg-accent-green" : "bg-accent-green/50"} ${isSelected ? "" : "animate-pulse"}`} />
                      <div className="flex-1 min-w-0 text-left">
                        <div className={`font-mono font-semibold text-white/70 truncate text-[8px] ${isSelected ? "text-accent-green" : ""}`}>
                          {agent.label}
                        </div>
                        <div className="text-white/40 text-[7px]">{agent.role}</div>
                      </div>
                      {isSelected && (
                        <div className="text-[8px] font-mono font-bold px-1 py-0.5 rounded bg-white/10">
                          ✓
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {orders.length === 0 && activeAgents.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-3">
            <Map size={20} className="text-white/15 mb-2" />
            <p className="text-[8px] text-white/25 font-mono">
              Start cascade to see graph
            </p>
          </div>
        )}
      </div>

      {/* Stats Footer */}
      <div className="shrink-0 px-2 py-1.5 border-t border-panel-border/30 bg-panel-dark/50 text-[7px] text-white/30 font-mono space-y-0.5">
        <div>Orders: {orders.length}</div>
        <div>Agents: {activeAgents.length}</div>
      </div>
    </div>
  );
}
