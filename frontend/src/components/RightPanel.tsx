import { useState } from "react";
import { MessageSquare, Users, BarChart3, AlertTriangle, FileText, Map } from "lucide-react";
import MessageFlow from "./MessageFlow";
import AgentsList from "./AgentsList";
import RiskPanel from "./RiskPanel";
import ReportPanel from "./ReportPanel";
import GraphNavigator from "./GraphNavigator";
import type { WsEvent } from "../hooks/useWebSocket";

type TabId = "messages" | "agents" | "risks" | "report" | "summary" | "graph";

const TABS: { id: TabId; label: string; icon: typeof MessageSquare }[] = [
  { id: "messages", label: "Messages", icon: MessageSquare },
  { id: "agents", label: "Agents", icon: Users },
  { id: "risks", label: "Risks", icon: AlertTriangle },
  { id: "report", label: "Report", icon: FileText },
  { id: "summary", label: "Summary", icon: BarChart3 },
  { id: "graph", label: "Navigator", icon: Map },
];

interface SummaryData {
  totalCost: string;
  parts: string;
  suppliers: string;
  leadTime: string;
  mfgComplete: boolean;
}

interface Props {
  events: WsEvent[];
  summary: SummaryData;
  error: string | null;
  highlightedAgentId: string | null;
  onAgentClick: (agentId: string | null) => void;
  selectedOrderId: string | null;
  onOrderSelect: (orderId: string | null) => void;
  selectedGraphNode: string | null;
  onGraphNodeSelect: (nodeId: string | null) => void;
}

export default function RightPanel({ events, summary, error, highlightedAgentId, onAgentClick, selectedOrderId, onOrderSelect, selectedGraphNode, onGraphNodeSelect }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("messages");

  return (
    <aside className="w-full h-full shrink-0 border-l border-panel-border flex flex-col bg-panel-card/50 overflow-hidden">
      {/* Tab Bar */}
      <div className="shrink-0 flex border-b border-panel-border bg-panel-card/80 overflow-x-auto hide-scrollbar">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex-1 min-w-0 flex items-center justify-center gap-0.5 px-2 py-2 text-[8px] font-medium font-mono
                transition-all duration-200 relative cursor-pointer whitespace-nowrap
                ${isActive
                  ? "text-accent-green"
                  : "text-white/35 hover:text-white/55"
                }
              `}
            >
              <Icon size={10} className="shrink-0" />
              <span className="truncate">{tab.label}</span>

              {/* Active indicator line */}
              {isActive && (
                <div className="absolute bottom-0 left-1 right-1 h-[2px] bg-accent-green rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === "messages" && (
          <MessageFlow events={events} selectedOrderId={selectedOrderId} onOrderSelect={onOrderSelect} />
        )}

        {activeTab === "agents" && (
          <AgentsList
            events={events}
            highlightedAgentId={highlightedAgentId}
            onAgentClick={onAgentClick}
          />
        )}

        {activeTab === "risks" && (
          <RiskPanel events={events} />
        )}

        {activeTab === "report" && (
          <ReportPanel events={events} />
        )}

        {activeTab === "summary" && (
          <div className="h-full flex flex-col overflow-y-auto">
            {/* Error display */}
            {error && (
              <div className="shrink-0 mx-2 mt-2 px-2 py-1.5 rounded-md bg-red-500/10 border border-red-500/30 text-red-400 text-[8px] font-mono">
                {error}
              </div>
            )}

            {/* Execution Summary */}
            <div className="p-3">
              <h3 className="text-[9px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono mb-2">
                Summary
              </h3>
              <div className="grid grid-cols-2 gap-1.5">
                <SummaryCard icon="$" label="Cost" value={summary.totalCost} color="text-accent-green" />
                <SummaryCard icon="◈" label="Parts" value={summary.parts} color="text-accent-cyan" />
                <SummaryCard icon="⟐" label="Suppliers" value={summary.suppliers} color="text-accent-gold" />
                <SummaryCard icon="◷" label="Lead Time" value={summary.leadTime} color="text-accent-orange" />
              </div>
            </div>

            {/* Manufacturing status */}
            {summary.mfgComplete && (
              <div className="mx-3 mb-2 px-2 py-1.5 rounded-lg bg-accent-green/5 border border-accent-green/20">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-accent-green animate-pulse" />
                  <span className="text-[9px] font-medium text-accent-green/80 font-mono">
                    Manufacturing OK
                  </span>
                </div>
              </div>
            )}

            {/* Cascade metrics */}
            <div className="px-3 pb-3">
              <h3 className="text-[9px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono mb-2">
                Metrics
              </h3>
              <div className="space-y-1">
                <MetricRow label="Events" value={String(events.length)} />
                <MetricRow
                  label="Messages"
                  value={String(events.filter((e) => e.type === "agent_message").length)}
                />
                <MetricRow
                  label="Quotes"
                  value={String(
                    events.filter(
                      (e) =>
                        e.type === "agent_message" &&
                        (e.data as Record<string, unknown>)?.message_type === "quote_response"
                    ).length
                  )}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === "graph" && (
          <GraphNavigator events={events} selectedNodeId={selectedGraphNode} onSelectNode={onGraphNodeSelect} />
        )}
      </div>
    </aside>
  );
}

// ── Summary Card ────────────────────────────────────────────────────────
function SummaryCard({ icon, label, value, color }: { icon: string; label: string; value: string; color: string }) {
  return (
    <div className="bg-panel-dark/60 border border-panel-border rounded-lg p-2 text-center">
      <div className={`text-base mb-0.5 ${color}`}>{icon}</div>
      <div className={`text-sm font-semibold font-mono ${value === "--" ? "text-white/20" : "text-white"}`}>
        {value}
      </div>
      <div className="text-[8px] text-white/30 font-mono uppercase tracking-wider mt-0.5">{label}</div>
    </div>
  );
}

// ── Metric Row ──────────────────────────────────────────────────────────
function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1 px-2 rounded-md bg-panel-dark/40 border border-panel-border/50">
      <span className="text-[9px] text-white/40 font-mono">{label}</span>
      <span className="text-[9px] text-white/70 font-mono font-medium">{value}</span>
    </div>
  );
}
