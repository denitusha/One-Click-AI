import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { WsEvent } from "../hooks/useWebSocket";

interface Props {
  events: WsEvent[];
}

export default function RiskHeatmap({ events }: Props) {
  // Calculate risk scores per agent based on message activity
  const agentActivity: Record<string, number> = {};
  for (const evt of events) {
    if (evt.type === "agent_message" && evt.data) {
      const sender = evt.data.sender_id as string;
      const receiver = evt.data.receiver_id as string;
      agentActivity[sender] = (agentActivity[sender] || 0) + 1;
      agentActivity[receiver] = (agentActivity[receiver] || 0) + 1;
    }
  }

  // Static risk model for demo
  const riskData = [
    { agent: "Procurement", dependency: 5, single_source: 1, lead_time: 2, score: 8 },
    { agent: "Supplier 1", dependency: 3, single_source: 2, lead_time: 4, score: 9 },
    { agent: "Supplier 2", dependency: 3, single_source: 1, lead_time: 3, score: 7 },
    { agent: "Manufacturer", dependency: 4, single_source: 3, lead_time: 5, score: 12 },
    { agent: "Logistics", dependency: 2, single_source: 2, lead_time: 3, score: 7 },
    { agent: "Compliance", dependency: 1, single_source: 0, lead_time: 1, score: 2 },
  ];

  const getBarColor = (score: number) => {
    if (score >= 10) return "#DC0000";
    if (score >= 7) return "#E2B93B";
    return "#2ECC71";
  };

  return (
    <div className="h-full flex flex-col">
      <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3">
        Risk Assessment
      </h3>

      <div className="flex-1">
        <ResponsiveContainer width="100%" height="60%">
          <BarChart data={riskData} layout="vertical" margin={{ left: 80 }}>
            <XAxis type="number" stroke="#ffffff33" tick={{ fill: "#ffffff66", fontSize: 10 }} />
            <YAxis
              dataKey="agent"
              type="category"
              stroke="#ffffff33"
              tick={{ fill: "#ffffff99", fontSize: 11 }}
              width={75}
            />
            <Tooltip
              contentStyle={{
                background: "#16213E",
                border: "1px solid #ffffff22",
                borderRadius: 8,
                color: "#fff",
                fontSize: 12,
              }}
            />
            <Bar dataKey="score" name="Risk Score" radius={[0, 4, 4, 0]}>
              {riskData.map((entry, idx) => (
                <Cell key={idx} fill={getBarColor(entry.score)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div className="bg-green-500/10 rounded-lg p-2 border border-green-500/20">
            <div className="text-green-400 text-lg font-bold">Low</div>
            <div className="text-[10px] text-white/40">Score &lt; 7</div>
          </div>
          <div className="bg-yellow-500/10 rounded-lg p-2 border border-yellow-500/20">
            <div className="text-yellow-400 text-lg font-bold">Medium</div>
            <div className="text-[10px] text-white/40">Score 7-10</div>
          </div>
          <div className="bg-red-500/10 rounded-lg p-2 border border-red-500/20">
            <div className="text-red-400 text-lg font-bold">High</div>
            <div className="text-[10px] text-white/40">Score &gt; 10</div>
          </div>
        </div>
      </div>
    </div>
  );
}
