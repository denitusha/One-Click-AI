import { useMemo } from "react";
import {
  Database,
  Cpu,
  Crosshair,
  Package,
  Factory,
  Truck,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

// Agent definitions matching the graph nodes
const AGENTS = [
  { id: "nanda-index",              label: "NANDA Index",       role: "registry",     framework: "FastAPI",        port: "6900" },
  { id: "nanda-resolver",           label: "Adaptive Resolver", role: "resolver",     framework: "FastAPI",        port: "6900" },
  { id: "nanda:procurement-agent",  label: "Procurement Agent", role: "procurement",  framework: "LangGraph",      port: "6010" },
  { id: "nanda:supplier-agent-1",   label: "Supplier A",        role: "supplier",     framework: "CrewAI",         port: "6001" },
  { id: "nanda:supplier-agent-2",   label: "Supplier B",        role: "supplier",     framework: "Custom Python",  port: "6002" },
  { id: "nanda:manufacturer-agent", label: "Manufacturer",      role: "manufacturer", framework: "LangGraph",      port: "6005" },
  { id: "nanda:logistics-agent",    label: "Logistics Agent",   role: "logistics",    framework: "AutoGen",        port: "6004" },
  { id: "nanda:compliance-agent",   label: "Compliance Agent",  role: "compliance",   framework: "LangGraph",      port: "6006" },
] as const;

const ROLE_CONFIG: Record<string, { bg: string; border: string; text: string; dot: string; Icon: LucideIcon }> = {
  procurement:  { bg: "bg-accent-green/10",  border: "border-accent-green/30",  text: "text-accent-green",  dot: "bg-accent-green",  Icon: Crosshair },
  supplier:     { bg: "bg-accent-green/10",  border: "border-accent-green/30",  text: "text-accent-green",  dot: "bg-accent-green",  Icon: Package },
  manufacturer: { bg: "bg-blue-500/10",      border: "border-blue-500/30",      text: "text-blue-400",      dot: "bg-blue-400",      Icon: Factory },
  logistics:    { bg: "bg-accent-orange/10", border: "border-accent-orange/30", text: "text-accent-orange", dot: "bg-accent-orange", Icon: Truck },
  compliance:   { bg: "bg-accent-purple/10", border: "border-accent-purple/30", text: "text-accent-purple", dot: "bg-accent-purple", Icon: ShieldCheck },
  registry:     { bg: "bg-accent-purple/10", border: "border-accent-purple/30", text: "text-accent-purple", dot: "bg-accent-purple", Icon: Database },
  resolver:     { bg: "bg-accent-cyan/10",   border: "border-accent-cyan/30",   text: "text-accent-cyan",   dot: "bg-accent-cyan",   Icon: Cpu },
};

interface Props {
  events: WsEvent[];
  highlightedAgentId: string | null;
  onAgentClick: (agentId: string | null) => void;
}

export default function AgentsList({ events, highlightedAgentId, onAgentClick }: Props) {
  // Determine which agents are active based on events
  const activeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const evt of events) {
      if (evt.type === "agent_message" && evt.data) {
        const sender = evt.data.sender_id as string;
        const receiver = evt.data.receiver_id as string;
        if (sender) {
          ids.add(sender);
          if (!sender.startsWith("nanda:")) ids.add(`nanda:${sender}`);
        }
        if (receiver) {
          ids.add(receiver);
          if (!receiver.startsWith("nanda:")) ids.add(`nanda:${receiver}`);
        }
      }
    }
    if (events.some((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "discovery_request")) {
      ids.add("nanda-index");
      ids.add("nanda-resolver");
    }
    return ids;
  }, [events]);

  // Count messages per agent
  const messageCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const evt of events) {
      if (evt.type === "agent_message" && evt.data) {
        const sender = evt.data.sender_id as string;
        const receiver = evt.data.receiver_id as string;
        if (sender) {
          const normalizedSender = sender.startsWith("nanda:") ? sender : `nanda:${sender}`;
          counts[normalizedSender] = (counts[normalizedSender] || 0) + 1;
          counts[sender] = (counts[sender] || 0) + 1;
        }
        if (receiver) {
          const normalizedReceiver = receiver.startsWith("nanda:") ? receiver : `nanda:${receiver}`;
          counts[normalizedReceiver] = (counts[normalizedReceiver] || 0) + 1;
          counts[receiver] = (counts[receiver] || 0) + 1;
        }
      }
    }
    return counts;
  }, [events]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b border-panel-border">
        <div className={`w-1.5 h-1.5 rounded-full ${activeIds.size > 0 ? "bg-accent-green" : "bg-white/20"}`} />
        <h3 className="text-[10px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
          Agent Network
        </h3>
        <span className="ml-auto text-[10px] text-white/20 font-mono">
          {activeIds.size > 0 ? `${activeIds.size} active` : `${AGENTS.length} agents`}
        </span>
      </div>

      {/* Agent List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {AGENTS.map((agent) => {
          const cfg = ROLE_CONFIG[agent.role] || ROLE_CONFIG.procurement;
          const RoleIcon = cfg.Icon;
          const isActive = activeIds.has(agent.id);
          const isHighlighted = highlightedAgentId === agent.id;
          const msgCount = messageCounts[agent.id] || 0;

          return (
            <button
              key={agent.id}
              onClick={() => onAgentClick(isHighlighted ? null : agent.id)}
              className={`
                w-full text-left rounded-lg px-3 py-2.5 border transition-all duration-200 group cursor-pointer
                ${isHighlighted
                  ? `${cfg.bg} ${cfg.border} ring-1 ring-white/10`
                  : "bg-panel-dark/40 border-panel-border/50 hover:border-panel-border hover:bg-panel-dark/60"
                }
              `}
            >
              <div className="flex items-center gap-2.5">
                {/* Role icon */}
                <div
                  className={`
                    w-8 h-8 rounded-md flex items-center justify-center border shrink-0
                    ${isHighlighted || isActive ? cfg.bg + " " + cfg.border + " " + cfg.text : "bg-white/[0.03] border-white/10 text-white/30"}
                  `}
                >
                  <RoleIcon size={15} />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[11px] font-medium truncate ${isHighlighted ? "text-white" : "text-white/70"}`}>
                      {agent.label}
                    </span>
                    {isActive && (
                      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot} animate-pulse`} />
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[9px] text-white/25 font-mono">{agent.framework} · :{agent.port}</span>
                    {msgCount > 0 && (
                      <span className="text-[9px] text-white/30 font-mono">
                        {msgCount} msg{msgCount !== 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                </div>

                {/* Status indicator */}
                <div className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                  isActive ? "bg-accent-green/10 text-accent-green/70" : "bg-white/[0.03] text-white/20"
                }`}>
                  {isActive ? "active" : "idle"}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
