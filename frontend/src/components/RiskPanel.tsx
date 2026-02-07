import { useMemo } from "react";
import { AlertTriangle, Shield, TrendingUp } from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

// ── Risk model per agent ──────────────────────────────────────────────
interface RiskEntry {
  agentId: string;
  label: string;
  risks: { name: string; score: number; color: string }[];
  totalScore: number;
}

const RISK_DEFINITIONS: {
  agentId: string;
  label: string;
  risks: { name: string; base: number; color: string }[];
}[] = [
  {
    agentId: "nanda:procurement-agent",
    label: "Procurement",
    risks: [
      { name: "Dependency",    base: 5, color: "#ffd700" },
      { name: "Single Source", base: 1, color: "#ff9800" },
      { name: "Lead Time",    base: 2, color: "#00bcd4" },
    ],
  },
  {
    agentId: "nanda:supplier-agent-1",
    label: "Supplier A",
    risks: [
      { name: "Dependency",    base: 3, color: "#ffd700" },
      { name: "Single Source", base: 2, color: "#ff9800" },
      { name: "Lead Time",    base: 4, color: "#00bcd4" },
    ],
  },
  {
    agentId: "nanda:supplier-agent-2",
    label: "Supplier B",
    risks: [
      { name: "Dependency",    base: 3, color: "#ffd700" },
      { name: "Single Source", base: 1, color: "#ff9800" },
      { name: "Lead Time",    base: 3, color: "#00bcd4" },
    ],
  },
  {
    agentId: "nanda:manufacturer-agent",
    label: "Manufacturer",
    risks: [
      { name: "Dependency",    base: 4, color: "#ffd700" },
      { name: "Single Source", base: 3, color: "#ff9800" },
      { name: "Lead Time",    base: 5, color: "#00bcd4" },
    ],
  },
  {
    agentId: "nanda:logistics-agent",
    label: "Logistics",
    risks: [
      { name: "Dependency",    base: 2, color: "#ffd700" },
      { name: "Single Source", base: 2, color: "#ff9800" },
      { name: "Lead Time",    base: 3, color: "#00bcd4" },
    ],
  },
  {
    agentId: "nanda:compliance-agent",
    label: "Compliance",
    risks: [
      { name: "Dependency",    base: 1, color: "#ffd700" },
      { name: "Single Source", base: 0, color: "#ff9800" },
      { name: "Lead Time",    base: 1, color: "#00bcd4" },
    ],
  },
];

function getRiskLevel(score: number): { label: string; color: string; bg: string; border: string } {
  if (score >= 10) return { label: "HIGH",   color: "text-red-400",    bg: "bg-red-500/10",    border: "border-red-500/30" };
  if (score >= 7)  return { label: "MEDIUM", color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/30" };
  return                   { label: "LOW",    color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/30" };
}

interface Props {
  events: WsEvent[];
}

export default function RiskPanel({ events }: Props) {
  // Compute dynamic risk scores: base + message volume factor
  const riskData: RiskEntry[] = useMemo(() => {
    // Count messages per agent
    const msgCounts: Record<string, number> = {};
    for (const evt of events) {
      if (evt.type === "agent_message" && evt.data) {
        const sender = evt.data.sender_id as string;
        const receiver = evt.data.receiver_id as string;
        if (sender) msgCounts[sender] = (msgCounts[sender] || 0) + 1;
        if (receiver) msgCounts[receiver] = (msgCounts[receiver] || 0) + 1;
      }
    }

    return RISK_DEFINITIONS.map((def) => {
      const activity = msgCounts[def.agentId] || msgCounts[def.agentId.replace("nanda:", "")] || 0;
      // Slight boost to risk if agent is very active (bottleneck indicator)
      const activityBonus = activity > 4 ? 2 : activity > 2 ? 1 : 0;

      const risks = def.risks.map((r) => ({
        name: r.name,
        score: Math.min(r.base + (r.name === "Dependency" ? activityBonus : 0), 6),
        color: r.color,
      }));

      const totalScore = risks.reduce((sum, r) => sum + r.score, 0);
      return { agentId: def.agentId, label: def.label, risks, totalScore };
    });
  }, [events]);

  const maxScore = Math.max(...riskData.map((d) => d.totalScore), 1);
  const sorted = [...riskData].sort((a, b) => b.totalScore - a.totalScore);
  const bottleneck = sorted[0];

  // Summary counts
  const highCount = riskData.filter((d) => d.totalScore >= 10).length;
  const medCount = riskData.filter((d) => d.totalScore >= 7 && d.totalScore < 10).length;
  const lowCount = riskData.filter((d) => d.totalScore < 7).length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b border-panel-border">
        <AlertTriangle size={12} className="text-accent-orange" />
        <h3 className="text-[10px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
          Risk & Bottleneck Analysis
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Risk summary badges */}
        <div className="grid grid-cols-3 gap-1.5 px-3 pt-3 pb-2">
          <div className="bg-red-500/10 border border-red-500/20 rounded-md px-2 py-1.5 text-center">
            <div className="text-red-400 text-sm font-bold font-mono">{highCount}</div>
            <div className="text-[8px] text-red-400/60 font-mono uppercase">High</div>
          </div>
          <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-md px-2 py-1.5 text-center">
            <div className="text-yellow-400 text-sm font-bold font-mono">{medCount}</div>
            <div className="text-[8px] text-yellow-400/60 font-mono uppercase">Medium</div>
          </div>
          <div className="bg-green-500/10 border border-green-500/20 rounded-md px-2 py-1.5 text-center">
            <div className="text-green-400 text-sm font-bold font-mono">{lowCount}</div>
            <div className="text-[8px] text-green-400/60 font-mono uppercase">Low</div>
          </div>
        </div>

        {/* Bottleneck callout */}
        {bottleneck && bottleneck.totalScore >= 7 && (
          <div className="mx-3 mb-2 px-3 py-2 rounded-lg bg-red-500/5 border border-red-500/20">
            <div className="flex items-center gap-1.5 mb-1">
              <TrendingUp size={10} className="text-red-400" />
              <span className="text-[9px] font-mono text-red-400/80 uppercase tracking-wider">
                Primary Bottleneck
              </span>
            </div>
            <div className="text-[11px] font-medium text-white/80">
              {bottleneck.label}
              <span className="text-white/30 font-mono text-[10px] ml-1.5">
                score {bottleneck.totalScore}
              </span>
            </div>
          </div>
        )}

        {/* Agent risk bars */}
        <div className="px-3 pb-3 space-y-1">
          {sorted.map((entry) => {
            const level = getRiskLevel(entry.totalScore);

            return (
              <div
                key={entry.agentId}
                className={`rounded-lg border px-3 py-2.5 ${level.bg} ${level.border} transition-all`}
              >
                {/* Agent name + score */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-medium text-white/75">{entry.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded ${level.bg} ${level.color}`}>
                      {level.label}
                    </span>
                    <span className="text-[10px] font-mono text-white/40">{entry.totalScore}</span>
                  </div>
                </div>

                {/* Composite bar */}
                <div className="h-2 rounded-full bg-white/[0.04] overflow-hidden flex">
                  {entry.risks.map((risk) => (
                    <div
                      key={risk.name}
                      className="h-full transition-all duration-500"
                      style={{
                        width: `${(risk.score / maxScore) * 100}%`,
                        background: `${risk.color}88`,
                      }}
                      title={`${risk.name}: ${risk.score}`}
                    />
                  ))}
                </div>

                {/* Risk breakdown */}
                <div className="flex gap-3 mt-1.5">
                  {entry.risks.map((risk) => (
                    <div key={risk.name} className="flex items-center gap-1">
                      <div
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: risk.color }}
                      />
                      <span className="text-[8px] font-mono text-white/30">
                        {risk.name.split(" ")[0]} {risk.score}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Legend */}
        <div className="px-3 pb-3">
          <div className="text-[9px] font-mono text-white/25 uppercase tracking-wider mb-2">
            Risk Factors
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <LegendDot color="#ffd700" label="Dependency" />
            <LegendDot color="#ff9800" label="Single Source" />
            <LegendDot color="#00bcd4" label="Lead Time" />
          </div>
          <div className="mt-2 text-[9px] text-white/20 font-mono leading-relaxed flex items-start gap-1">
            <Shield size={9} className="shrink-0 mt-0.5 text-white/15" />
            Scores adjust dynamically based on agent message volume — high-activity agents signal potential bottlenecks.
          </div>
        </div>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1">
      <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
      <span className="text-[9px] font-mono text-white/35">{label}</span>
    </div>
  );
}
