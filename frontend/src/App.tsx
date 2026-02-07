import { useState, useCallback, useMemo } from "react";
import { Zap, RotateCcw, Loader2 } from "lucide-react";
import SupplyGraph from "./components/SupplyGraph";
import RightPanel from "./components/RightPanel";
import { useWebSocket } from "./hooks/useWebSocket";

// ── Cascade phase detection ────────────────────────────────────────────
const PHASES = [
  "Intent Received",
  "BOM Decomposition",
  "Agent Discovery",
  "RFQ & Quotes",
  "Negotiation",
  "Order Placed",
  "Manufacturing",
  "Compliance",
  "Logistics Planning",
  "Cascade Complete",
] as const;

function detectPhase(events: Array<Record<string, unknown>>, loading: boolean, result: unknown): { label: string; index: number } {
  if (!loading && events.length === 0) return { label: "Idle", index: -1 };

  const types = events
    .filter((e) => e.type === "agent_message")
    .map((e) => ((e.data as Record<string, unknown>)?.message_type as string) || "");

  if (types.some((t) => t === "order_confirmation") && !loading)
    return { label: "Cascade Complete", index: 9 };
  if (types.some((t) => t === "route_confirmation"))
    return { label: "Logistics Planning", index: 8 };
  if (types.some((t) => t === "compliance_result"))
    return { label: "Compliance", index: 7 };
  if (types.some((t) => t === "shipping_request" || t === "compliance_check"))
    return { label: "Manufacturing", index: 6 };
  if (types.some((t) => t === "order_placement"))
    return { label: "Order Placed", index: 5 };
  if (types.some((t) => t === "negotiation_proposal"))
    return { label: "Negotiation", index: 4 };
  if (types.some((t) => t === "quote_response" || t === "request_for_quote"))
    return { label: "RFQ & Quotes", index: 3 };
  if (types.some((t) => t === "discovery_request"))
    return { label: "Agent Discovery", index: 2 };
  if (types.some((t) => t === "status_update"))
    return { label: "BOM Decomposition", index: 1 };
  if (types.some((t) => t === "intent") || loading)
    return { label: "Intent Received", index: 0 };

  return { label: "Processing...", index: 0 };
}

// ── Execution summary extraction ──────────────────────────────────────
function extractSummary(events: Array<Record<string, unknown>>, result: Record<string, unknown> | null) {
  // Count quotes from WebSocket events (live)
  const quoteEvents = events.filter(
    (e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "quote_response"
  );

  // Extract from final result (available after cascade completes)
  const bestQuote = result?.best_quote as Record<string, unknown> | undefined;
  const order = result?.order as Record<string, unknown> | undefined;
  const mfg = result?.manufacturing_result as Record<string, unknown> | undefined;
  const quotesReceived = result?.quotes_received as number | undefined;

  // Total cost: prefer order agreed_price > best_quote total_price > quote event payloads
  let totalCost: number | null = null;
  if (order?.agreed_price != null) {
    totalCost = Number(order.agreed_price);
  } else if (bestQuote?.total_price != null) {
    totalCost = Number(bestQuote.total_price);
  } else if (quoteEvents.length > 0) {
    // Extract from the first quote event payload
    const firstPayload = (quoteEvents[0].data as Record<string, unknown>)?.payload as Record<string, unknown> | undefined;
    if (firstPayload?.total_price != null) totalCost = Number(firstPayload.total_price);
  }

  // Lead time: prefer bestQuote > quote event payloads
  let leadTime: number | null = null;
  if (bestQuote?.lead_time_days != null) {
    leadTime = Number(bestQuote.lead_time_days);
  } else if (quoteEvents.length > 0) {
    const firstPayload = (quoteEvents[0].data as Record<string, unknown>)?.payload as Record<string, unknown> | undefined;
    if (firstPayload?.lead_time_days != null) leadTime = Number(firstPayload.lead_time_days);
  }

  // Supplier count: from result or live events
  const supplierCount = quotesReceived ?? (quoteEvents.length > 0 ? quoteEvents.length : null);

  // Parts: show once we have any meaningful event
  const hasStarted = events.some((e) => e.type === "agent_message");
  const parts = hasStarted ? 10 : null; // Ferrari BOM has 10 categories

  return {
    totalCost: totalCost != null ? `$${totalCost.toLocaleString()}` : "--",
    parts: parts != null ? String(parts) : "--",
    suppliers: supplierCount != null ? String(supplierCount) : "--",
    leadTime: leadTime != null ? `${leadTime}d` : "--",
    mfgComplete: mfg?.confirmed === true,
  };
}

export default function App() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [intentInput, setIntentInput] = useState("Buy all the parts required to assemble a Ferrari");
  const [highlightedAgentId, setHighlightedAgentId] = useState<string | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  const { events, connected, clearEvents } = useWebSocket("ws://localhost:8001/ws");
  const phase = useMemo(
    () => detectPhase(events as Array<Record<string, unknown>>, loading, result),
    [events, loading, result]
  );
  const summary = useMemo(
    () => extractSummary(events as Array<Record<string, unknown>>, result),
    [events, result]
  );

  const triggerCascade = useCallback(async () => {
    if (!intentInput.trim()) return;
    setLoading(true);
    setResult(null);
    clearEvents();
    try {
      const res = await fetch("http://localhost:8010/intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: intentInput.trim() }),
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      console.error("Cascade failed:", err);
      setResult({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }, [clearEvents, intentInput]);

  const resetAll = useCallback(() => {
    setResult(null);
    clearEvents();
    setSelectedOrderId(null);
  }, [clearEvents]);

  return (
    <div className="h-screen flex flex-col bg-panel-dark text-white overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="shrink-0 flex flex-col bg-panel-card border-b border-panel-border">
        {/* Top row: branding + status + actions */}
        <div className="h-12 flex items-center justify-between px-5 gap-3 min-w-0">
          {/* Left: branding */}
          <div className="flex items-center gap-2.5 shrink-0">
            <Zap size={18} className="text-accent-green" />
            <span className="text-sm font-semibold tracking-wide">
              <span className="text-accent-green">OneClickAI</span>
              <span className="text-white/50 font-normal ml-1.5 hidden sm:inline">Supply Chain Agents</span>
            </span>
          </div>

          {/* Center: phase + events */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center gap-2 text-xs min-w-0">
              <span className="text-white/40 font-mono uppercase tracking-wider shrink-0">Phase:</span>
              <span className={`font-semibold font-mono truncate ${phase.index >= 0 ? "text-accent-green" : "text-white/50"}`}>
                {phase.label}
              </span>
            </div>
            <div className="w-px h-4 bg-panel-border shrink-0" />
            <span className="text-xs text-white/40 font-mono whitespace-nowrap shrink-0">
              {events.length} events
            </span>
            <div className="w-px h-4 bg-panel-border shrink-0" />
            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? "bg-accent-green" : "bg-red-500"}`} />
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={resetAll}
              className="flex items-center gap-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-white/60 px-3 py-1.5 rounded-md text-xs font-medium transition-all"
            >
              <RotateCcw size={12} />
              Reset
            </button>
          </div>
        </div>

        {/* Bottom row: intent input + Run button */}
        <div className="px-5 pb-3 flex items-center gap-3">
          <div className="flex-1 relative">
            <input
              type="text"
              value={intentInput}
              onChange={(e) => setIntentInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !loading) triggerCascade(); }}
              disabled={loading}
              placeholder="Describe what you want to procure..."
              className="w-full bg-panel-dark/80 border border-panel-border focus:border-accent-green/50 text-white text-sm px-4 py-2.5 rounded-lg outline-none placeholder:text-white/25 font-mono disabled:opacity-50 transition-colors"
            />
          </div>
          <button
            onClick={triggerCascade}
            disabled={loading || !intentInput.trim()}
            className="flex items-center gap-1.5 bg-accent-green/15 hover:bg-accent-green/25 border border-accent-green/30 text-accent-green disabled:opacity-40 disabled:cursor-not-allowed px-5 py-2.5 rounded-lg text-sm font-semibold transition-all whitespace-nowrap"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            {loading ? "Running..." : "Run Cascade"}
          </button>
        </div>
      </header>

      {/* ── Main content: Graph left, Sidebar right ─────────────── */}
      <main className="flex-1 min-h-0 flex">
        {/* Left: Supply Graph */}
        <div className="flex-1 min-w-0 p-3">
          <SupplyGraph events={events} highlightedAgentId={highlightedAgentId} selectedOrderId={selectedOrderId} />
        </div>

        {/* Right: Tabbed Panel (Messages / Agents / Summary) */}
        <RightPanel
          events={events}
          summary={summary}
          error={result?.error ? String(result.error) : null}
          highlightedAgentId={highlightedAgentId}
          onAgentClick={setHighlightedAgentId}
          selectedOrderId={selectedOrderId}
          onOrderSelect={setSelectedOrderId}
        />
      </main>

      {/* ── Coordination Timeline (bottom bar) ─────────────────── */}
      <footer className="shrink-0 border-t border-panel-border bg-panel-card px-5 py-2.5 overflow-x-auto hide-scrollbar">
        <div className="flex items-center gap-1 min-w-max">
          <span className="text-[10px] text-white/30 font-mono uppercase tracking-wider mr-3 shrink-0">
            Coordination Timeline
          </span>
          {PHASES.map((step, i) => {
            const isActive = i === phase.index;
            const isDone = phase.index > i;

            return (
              <div key={step} className="flex items-center shrink-0">
                {i > 0 && (
                  <div className={`w-3 h-px mx-0.5 ${isDone ? "bg-accent-green/40" : "bg-panel-border"}`} />
                )}
                <div
                  className={`
                    px-2 py-1 rounded text-[9px] font-mono whitespace-nowrap transition-all
                    ${isActive
                      ? "bg-accent-green/15 text-accent-green border border-accent-green/30 step-active"
                      : isDone
                        ? "bg-accent-green/5 text-accent-green/60 border border-accent-green/10"
                        : "bg-white/[0.02] text-white/25 border border-transparent"
                    }
                  `}
                >
                  {step}
                </div>
              </div>
            );
          })}
        </div>
      </footer>
    </div>
  );
}
