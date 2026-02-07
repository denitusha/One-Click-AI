import type { WsEvent } from "../hooks/useWebSocket";
import { ArrowRight } from "lucide-react";

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
}

export default function MessageFlow({ events }: Props) {
  const agentMessages = events.filter((e) => e.type === "agent_message");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 shrink-0" style={{ borderBottom: "1px solid #1a2336" }}>
        <div className={`w-1.5 h-1.5 rounded-full ${agentMessages.length > 0 ? "bg-accent-green" : "bg-white/20"}`} />
        <h3 className="text-[10px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
          Message Flow
        </h3>
        <span className="ml-auto text-[10px] text-white/20 font-mono">
          {agentMessages.length}
        </span>
      </div>

      {/* Messages */}
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
    </div>
  );
}
