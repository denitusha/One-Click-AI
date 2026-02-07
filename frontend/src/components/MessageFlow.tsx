import type { WsEvent } from "../hooks/useWebSocket";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
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

interface Props {
  events: WsEvent[];
  selectedOrderId: string | null;
  onOrderSelect: (orderId: string | null) => void;
}

export default function MessageFlow({ events, selectedOrderId, onOrderSelect }: Props) {
  const [view, setView] = useState<"messages" | "orders">("messages");
  const agentMessages = events.filter((e) => e.type === "agent_message");

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
          {view === "messages" ? agentMessages.length : "--"}
        </span>
      </div>

      {/* Messages view */}
      {view === "messages" && (
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
          {agentMessages.length === 0 ? (
            <div className="text-white/20 text-xs font-mono pt-8 text-center">
              Awaiting cascade...
            </div>
          ) : (
            <div className="space-y-1.5">
              {agentMessages.map((evt, i) => {
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
      )}

      {/* Orders view */}
      {view === "orders" && (
        <OrdersView events={events} selectedOrderId={selectedOrderId} onOrderSelect={onOrderSelect} />
      )}
    </div>
  );
}
