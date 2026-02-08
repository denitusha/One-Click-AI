import type { WsEvent } from "../hooks/useWebSocket";
import { ArrowRight, X } from "lucide-react";
import { useState, useMemo } from "react";
import OrdersView from "./OrdersView";

const TYPE_DOT: Record<string, string> = {
  request_for_quote: "bg-accent-gold",
  quote_response: "bg-accent-gold",
  negotiation_proposal: "bg-accent-orange",
  order_placement: "bg-accent-red",
  order_confirmation: "bg-accent-green",
  shipping_request: "bg-accent-orange",
  route_confirmation: "bg-accent-green",
  compliance_check: "bg-accent-purple",
  compliance_result: "bg-accent-purple",
  discovery_request: "bg-accent-cyan",
  discovery_response: "bg-accent-cyan",
  intent: "bg-accent-green",
  status_update: "bg-white/30",
  error: "bg-red-500",
};

const MESSAGE_TYPES = [
  { key: "all", label: "All", color: "bg-white/20" },
  { key: "orders", label: "Orders", color: "bg-accent-red" },
  { key: "quotes", label: "Quotes", color: "bg-accent-gold" },
  { key: "negotiation", label: "Negotiation", color: "bg-accent-orange" },
  { key: "compliance", label: "Compliance", color: "bg-accent-purple" },
  { key: "logistics", label: "Logistics", color: "bg-accent-cyan" },
  { key: "verification", label: "Verification", color: "bg-accent-purple" },
];

interface Props {
  events: WsEvent[];
  selectedOrderId: string | null;
  onOrderSelect: (orderId: string | null) => void;
}

export default function MessageFlow({ events, selectedOrderId, onOrderSelect }: Props) {
  const [view, setView] = useState<"messages" | "orders">("messages");
  const [activeFilter, setActiveFilter] = useState<string>("all");

  const agentMessages = events.filter((e) => e.type === "agent_message");

  // Count messages by type
  const messageCounts = useMemo(() => {
    const counts: Record<string, number> = { all: agentMessages.length };
    
    for (const evt of agentMessages) {
      const msgType = (evt.data?.message_type as string) || "";
      
      if (["order_placement", "order_confirmation"].includes(msgType)) counts.orders = (counts.orders || 0) + 1;
      if (["quote_response", "request_for_quote"].includes(msgType)) counts.quotes = (counts.quotes || 0) + 1;
      if (msgType === "negotiation_proposal") counts.negotiation = (counts.negotiation || 0) + 1;
      if (["compliance_check", "compliance_result"].includes(msgType)) counts.compliance = (counts.compliance || 0) + 1;
      if (["shipping_request", "route_confirmation"].includes(msgType)) counts.logistics = (counts.logistics || 0) + 1;
      if (msgType === "discovery_request") counts.verification = (counts.verification || 0) + 1;
    }
    
    return counts;
  }, [agentMessages]);

  // Filter messages based on active filter
  const filteredMessages = useMemo(() => {
    if (activeFilter === "all") return agentMessages;
    
    return agentMessages.filter((evt) => {
      const msgType = (evt.data?.message_type as string) || "";
      
      switch (activeFilter) {
        case "orders":
          return ["order_placement", "order_confirmation"].includes(msgType);
        case "quotes":
          return ["quote_response", "request_for_quote"].includes(msgType);
        case "negotiation":
          return msgType === "negotiation_proposal";
        case "compliance":
          return ["compliance_check", "compliance_result"].includes(msgType);
        case "logistics":
          return ["shipping_request", "route_confirmation"].includes(msgType);
        case "verification":
          return msgType === "discovery_request";
        default:
          return true;
      }
    });
  }, [agentMessages, activeFilter]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header with toggle */}
      <div className="flex items-center justify-between px-4 py-2.5 shrink-0" style={{ borderBottom: "1px solid #1a2336" }}>
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${view === "messages" && agentMessages.length > 0 ? "bg-accent-green" : "bg-white/20"}`} />
          <h3 className="text-[10px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
            {view === "messages" ? "Message Flow" : "Orders"}
          </h3>
        </div>

        {/* Messages/Orders toggle */}
        <div className="flex items-center gap-1 bg-panel-dark/60 rounded p-0.5 border border-panel-border/50">
          <button
            onClick={() => setView("messages")}
            className={`px-2 py-1 text-[9px] font-mono font-semibold rounded transition-all ${
              view === "messages"
                ? "bg-accent-green/15 text-accent-green border border-accent-green/30"
                : "text-white/40 hover:text-white/60"
            }`}
          >
            Messages
          </button>
          <button
            onClick={() => setView("orders")}
            className={`px-2 py-1 text-[9px] font-mono font-semibold rounded transition-all ${
              view === "orders"
                ? "bg-accent-green/15 text-accent-green border border-accent-green/30"
                : "text-white/40 hover:text-white/60"
            }`}
          >
            Orders
          </button>
        </div>

        {/* Count */}
        <span className="ml-auto text-[10px] text-white/20 font-mono">
          {view === "messages" ? filteredMessages.length : "--"}
        </span>
      </div>

      {/* Messages view */}
      {view === "messages" && (
        <>
          {/* Message type filter tabs */}
          <div className="shrink-0 border-b border-panel-border/30 bg-panel-dark/20 px-2 py-2 overflow-x-auto hide-scrollbar">
            <div className="flex gap-2 min-w-max">
              {MESSAGE_TYPES.map((type) => (
                <button
                  key={type.key}
                  onClick={() => setActiveFilter(type.key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[9px] font-mono font-semibold whitespace-nowrap transition-all border ${
                    activeFilter === type.key
                      ? `${type.color} bg-opacity-20 border-current text-white`
                      : "border-panel-border/30 text-white/40 hover:text-white/60"
                  }`}
                >
                  <div className={`w-1.5 h-1.5 rounded-full ${type.color}`} />
                  <span>{type.label}</span>
                  <span className="text-[8px] text-white/50 font-mono">{messageCounts[type.key] || 0}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Filtered messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
            {filteredMessages.length === 0 ? (
              <div className="text-white/20 text-xs font-mono pt-8 text-center">
                {activeFilter === "all" ? "Awaiting cascade..." : "No messages of this type"}
              </div>
            ) : (
              <div className="space-y-1.5">
                {filteredMessages.map((evt, i) => {
                  const d = evt.data || {};
                  const msgType = (d.message_type as string) || "status_update";
                  const dotColor = TYPE_DOT[msgType] || "bg-white/20";
                  const sender = ((d.sender_id as string) || "?").replace("nanda:", "").replace("-agent", "");
                  const receiver = ((d.receiver_id as string) || "?").replace("nanda:", "").replace("-agent", "");

                  return (
                    <div
                      key={i}
                      className="msg-enter bg-panel-dark/40 rounded-md px-2.5 py-2 border border-panel-border/50 hover:border-panel-border transition-colors"
                    >
                      <div className="flex items-center gap-1.5 text-[10px]">
                        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
                        <span className="font-mono text-white/60 truncate">{sender}</span>
                        <ArrowRight size={8} className="text-white/20 shrink-0" />
                        <span className="font-mono text-white/60 truncate">{receiver}</span>
                        <span className="ml-auto text-[9px] text-white/25 font-mono whitespace-nowrap">
                          {msgType.replace(/_/g, " ")}
                        </span>
                      </div>
                      {d.explanation && (
                        <p className="text-[10px] text-white/35 mt-1 leading-relaxed line-clamp-2">
                          {d.explanation as string}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* Orders view */}
      {view === "orders" && (
        <OrdersView events={events} selectedOrderId={selectedOrderId} onOrderSelect={onOrderSelect} />
      )}
    </div>
  );
}
