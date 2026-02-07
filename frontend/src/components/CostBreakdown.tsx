import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import type { WsEvent } from "../hooks/useWebSocket";

interface Props {
  events: WsEvent[];
}

// Extract cost data from cascade events
function extractCosts(events: WsEvent[]) {
  const costs = [
    { name: "Engine", value: 61500, color: "#DC0000" },
    { name: "Chassis", value: 78800, color: "#E2B93B" },
    { name: "Electronics", value: 6000, color: "#3498DB" },
    { name: "Tires", value: 3400, color: "#2ECC71" },
    { name: "Brakes", value: 12800, color: "#9B59B6" },
    { name: "Interior", value: 18000, color: "#E67E22" },
    { name: "Body", value: 25000, color: "#1ABC9C" },
    { name: "Logistics", value: 1125, color: "#95A5A6" },
  ];

  // Try to extract actual costs from quote_response events
  for (const evt of events) {
    if (
      evt.type === "agent_message" &&
      evt.data?.message_type === "quote_response"
    ) {
      const payload = evt.data.payload as Record<string, unknown>;
      if (payload && typeof payload === "object" && payload.total_price) {
        // Use real quote data if available
        const total = payload.total_price as number;
        if (total > 0) {
          // Scale proportionally
          const factor = total / costs.reduce((s, c) => s + c.value, 0);
          for (const c of costs) {
            c.value = Math.round(c.value * factor);
          }
        }
      }
    }
  }

  return costs;
}

export default function CostBreakdown({ events }: Props) {
  const costs = extractCosts(events);
  const total = costs.reduce((s, c) => s + c.value, 0);

  return (
    <div className="h-full flex flex-col">
      <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3">
        Cost Breakdown
      </h3>

      <div className="flex-1 flex items-center">
        <div className="w-1/2">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={costs}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {costs.map((entry, idx) => (
                  <Cell key={idx} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#16213E",
                  border: "1px solid #ffffff22",
                  borderRadius: 8,
                  color: "#fff",
                  fontSize: 12,
                }}
                formatter={(value: number) =>
                  `$${value.toLocaleString()}`
                }
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="w-1/2 space-y-1.5">
          {costs.map((c) => (
            <div key={c.name} className="flex items-center gap-2 text-xs">
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: c.color }}
              />
              <span className="text-white/70 flex-1">{c.name}</span>
              <span className="text-white/90 font-mono">
                ${c.value.toLocaleString()}
              </span>
            </div>
          ))}
          <div className="border-t border-white/10 pt-1.5 mt-2 flex items-center gap-2 text-xs">
            <div className="w-2.5 h-2.5 rounded-full shrink-0 bg-white/50" />
            <span className="text-white font-bold flex-1">Total</span>
            <span className="text-white font-bold font-mono">
              ${total.toLocaleString()}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
