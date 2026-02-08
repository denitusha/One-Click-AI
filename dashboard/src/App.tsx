import { useCallback, useState, useMemo, useEffect, useRef } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useDashboardState, filterDetailEdges } from "./hooks/useDashboardState";
import SupplyGraph from "./components/SupplyGraph";
import MessageFlow from "./components/MessageFlow";
import Timeline from "./components/Timeline";
import ExecutionPlanPanel from "./components/ExecutionPlan";
import IntentInput from "./components/IntentInput";
import StatusBar from "./components/StatusBar";
import GraphNavigator from "./components/GraphNavigator";
import RiskAnalysis from "./components/RiskAnalysis";
import type { GraphSelection, MessageLogEntry, AnalyticsMode } from "./types";

type SidebarTab = "navigator" | "messages" | "risks" | "report";

const PROCUREMENT_URL = "http://localhost:6010";

export default function App() {
  const { events, connected, stopped, reconnect, disconnect, fetchHistory } = useWebSocket();
  const [submitting, setSubmitting] = useState(false);
  const [runId, setRunId] = useState<string | null>(
    () => sessionStorage.getItem("runId")  // restore on refresh
  );
  const {
    nodes,
    edges,
    messages,
    timeline,
    executionPlan,
    cascadeComplete,
    overviewEdges,
    orders,
    shipPlans,
    negotiations,
  } = useDashboardState(events, runId);
  const [graphSelection, setGraphSelection] = useState<GraphSelection>({ mode: "overview" });
  const [analyticsMode, setAnalyticsMode] = useState<AnalyticsMode>("none");
  const [activeTab, setActiveTab] = useState<SidebarTab>("messages");

  // ── Horizontal sidebar width resize ──
  const [sidebarWidth, setSidebarWidth] = useState(380);
  const handleSidebarDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = sidebarWidth;
    const onMouseMove = (moveEvent: MouseEvent) => {
      // Sidebar is on the right, so dragging left increases width
      const delta = startX - moveEvent.clientX;
      setSidebarWidth(Math.max(280, Math.min(600, startWidth + delta)));
    };
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [sidebarWidth]);

  // ── Auto-disconnect WebSocket once cascade is complete ──
  // All data is already stored in React state; no need to keep the WS alive.
  const didDisconnect = useRef(false);
  useEffect(() => {
    if (cascadeComplete && !didDisconnect.current) {
      didDisconnect.current = true;
      // Small delay so the final events flush through rendering
      const timer = setTimeout(() => disconnect(), 500);
      return () => clearTimeout(timer);
    }
  }, [cascadeComplete, disconnect]);

  // ── On first mount, try HTTP fallback if WS doesn't connect quickly ──
  // This handles page refresh after cascade already completed.
  useEffect(() => {
    const timer = setTimeout(() => {
      // If we still have no events after 3s, try HTTP fetch
      if (events.length === 0) {
        fetchHistory();
      }
    }, 3000);
    return () => clearTimeout(timer);
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleIntent = useCallback(async (intent: string) => {
    setSubmitting(true);
    const newRunId = crypto.randomUUID();
    setRunId(newRunId);
    sessionStorage.setItem("runId", newRunId);
    try {
      await fetch(`${PROCUREMENT_URL}/intent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent, run_id: newRunId }),
      });
    } catch (err) {
      console.error("Failed to submit intent:", err);
    } finally {
      setSubmitting(false);
    }
  }, []);

  const handleReset = useCallback(() => {
    sessionStorage.removeItem("runId");
    setRunId(null);
  }, []);

  // ── Graph drill-down callbacks ──
  const handleSelectAgent = useCallback((agentId: string) => {
    setGraphSelection({ mode: "agent-detail", agentId });
  }, []);

  const handleBack = useCallback(() => {
    setGraphSelection({ mode: "overview" });
  }, []);

  const handleSelectOrder = useCallback((partName: string, supplierId: string) => {
    setGraphSelection({ mode: "order-detail", partName, supplierId });
  }, []);

  const handleSelectLogistics = useCallback((index?: number) => {
    setGraphSelection({ mode: "logistics-detail", shipPlanIndex: index });
  }, []);

  const handleSelectShipPlan = useCallback((index: number) => {
    setGraphSelection({ mode: "logistics-detail", shipPlanIndex: index });
  }, []);

  const handleSelectMessage = useCallback((msg: MessageLogEntry) => {
    // Determine the right detail mode based on event type
    const evtType = msg.event_type;

    if (["ORDER_PLACED"].includes(evtType)) {
      // Try to navigate to order detail
      if (msg.to) {
        setGraphSelection({ mode: "agent-detail", agentId: msg.to });
      }
    } else if (["LOGISTICS_REQUESTED", "SHIP_PLAN_RECEIVED"].includes(evtType)) {
      setGraphSelection({ mode: "logistics-detail" });
    } else if (msg.from || msg.to) {
      // Default: show agent detail for the "from" or "to" agent
      const agentId = msg.to ?? msg.from ?? msg.agent_id;
      setGraphSelection({ mode: "agent-detail", agentId });
    }
  }, []);

  // ── Compute detail edges based on current selection ──
  const detailEdges = useMemo(
    () => filterDetailEdges(edges, graphSelection),
    [edges, graphSelection],
  );

  return (
    <div className="flex h-screen flex-col bg-[#0f172a]">
      {/* ── Header ─────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700/60 bg-slate-900/70 px-5 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            1C
          </div>
          <div>
            <h1 className="text-base font-semibold text-slate-100">
              OneClickAI Supply Chain
            </h1>
            <p className="text-[0.65rem] text-slate-500">
              Multi-agent coordination dashboard
            </p>
          </div>
        </div>
        <StatusBar
          connected={connected}
          eventCount={messages.length}
          nodeCount={nodes.length}
          edgeCount={edges.length}
          onReconnect={reconnect}
        />
        {stopped && (
          <button
            onClick={handleReset}
            className="rounded-md bg-slate-700/50 px-2 py-1 text-[0.6rem] text-slate-400 transition-colors hover:bg-slate-600/50 hover:text-slate-200"
            title="Reset to start a new run"
          >
            Reset
          </button>
        )}
        {!connected && !stopped && events.length === 0 && (
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 rounded-md bg-sky-600/20 px-2.5 py-1 text-[0.65rem] font-medium text-sky-400 transition-colors hover:bg-sky-600/30"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Reset
          </button>
        )}
      </header>

      {/* ── Intent input bar ───────────────────────────────── */}
      <div className="shrink-0 border-b border-slate-700/40 bg-slate-900/40 px-5 py-3">
        <IntentInput onSubmit={handleIntent} disabled={submitting} />
      </div>

      {/* ── Timeline bar ───────────────────────────────────── */}
      <div className="shrink-0 border-b border-slate-700/40 bg-slate-900/30">
        <Timeline phases={timeline} cascadeComplete={cascadeComplete} />
      </div>

      {/* ── Main content area ──────────────────────────────── */}
      <div className="flex min-h-0 flex-1">
        {/* Left: Supply graph (main area) */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-slate-700/30 px-4 py-2">
            <svg className="h-4 w-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Supply Network Graph
            </h2>
            {graphSelection.mode !== "overview" && (
              <button
                onClick={handleBack}
                className="ml-auto flex items-center gap-1 rounded-md bg-slate-700/50 px-2 py-0.5 text-[0.6rem] font-medium text-slate-400 transition-colors hover:bg-slate-600/50 hover:text-slate-200"
              >
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                Overview
              </button>
            )}
          </div>
          <div className="flex-1">
            <SupplyGraph
              nodes={nodes}
              edges={edges}
              overviewEdges={overviewEdges}
              detailEdges={detailEdges}
              selection={graphSelection}
              shipPlans={shipPlans}
              negotiations={negotiations}
              analyticsMode={analyticsMode}
              onSelectAgent={handleSelectAgent}
              onBack={handleBack}
            />
          </div>
        </div>

        {/* ── Horizontal drag divider ── */}
        <div
          onMouseDown={handleSidebarDrag}
          className="w-1.5 shrink-0 cursor-col-resize bg-slate-700/40 transition-colors hover:bg-indigo-500/40"
        />

        {/* Right sidebar: Tabbed panels */}
        <div className="flex shrink-0 flex-col" style={{ width: sidebarWidth }}>
          {/* ── Tab bar ── */}
          <div className="flex shrink-0 border-b border-slate-700/50 bg-slate-900/60">
            <button
              onClick={() => setActiveTab("navigator")}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-[0.65rem] font-semibold uppercase tracking-wider transition-all ${
                activeTab === "navigator"
                  ? "border-b-2 border-purple-400 text-purple-300 bg-purple-500/10"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800/40"
              }`}
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
              Navigator
            </button>
            <button
              onClick={() => setActiveTab("messages")}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-[0.65rem] font-semibold uppercase tracking-wider transition-all ${
                activeTab === "messages"
                  ? "border-b-2 border-sky-400 text-sky-300 bg-sky-500/10"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800/40"
              }`}
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Messages
              {messages.length > 0 && (
                <span className="rounded-full bg-sky-500/20 px-1.5 py-px text-[0.5rem] font-mono text-sky-400">
                  {messages.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("risks")}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-[0.65rem] font-semibold uppercase tracking-wider transition-all ${
                activeTab === "risks"
                  ? "border-b-2 border-amber-400 text-amber-300 bg-amber-500/10"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800/40"
              }`}
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              Risks
            </button>
            <button
              onClick={() => setActiveTab("report")}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-[0.65rem] font-semibold uppercase tracking-wider transition-all ${
                activeTab === "report"
                  ? "border-b-2 border-emerald-400 text-emerald-300 bg-emerald-500/10"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800/40"
              }`}
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Report
            </button>
          </div>

          {/* ── Tab content ── */}
          <div className="min-h-0 flex-1 overflow-hidden">
            {activeTab === "navigator" && (
              <GraphNavigator
                selection={graphSelection}
                orders={orders}
                shipPlans={shipPlans}
                analyticsMode={analyticsMode}
                onOverview={handleBack}
                onSelectOrder={handleSelectOrder}
                onSelectLogistics={handleSelectLogistics}
                onAnalyticsChange={setAnalyticsMode}
              />
            )}
            {activeTab === "messages" && (
              <div className="flex h-full flex-col overflow-hidden">
                <div className="flex shrink-0 items-center gap-2 border-b border-slate-700/30 px-4 py-2">
                  <svg className="h-4 w-4 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Message Flow
                  </h2>
                  <span className="ml-auto rounded-full bg-slate-700/60 px-2 py-0.5 text-[0.6rem] font-mono text-slate-400">
                    {messages.length}
                  </span>
                </div>
                <div className="min-h-0 flex-1 overflow-hidden">
                  <MessageFlow messages={messages} onSelectMessage={handleSelectMessage} />
                </div>
              </div>
            )}
            {activeTab === "risks" && (
              <div className="flex h-full flex-col overflow-hidden">
                <div className="flex shrink-0 items-center gap-2 border-b border-slate-700/30 px-4 py-2">
                  <svg className="h-4 w-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Risk Analysis
                  </h2>
                </div>
                <div className="min-h-0 flex-1 overflow-hidden">
                  <RiskAnalysis
                    nodes={nodes}
                    orders={orders}
                    negotiations={negotiations}
                    shipPlans={shipPlans}
                  />
                </div>
              </div>
            )}
            {activeTab === "report" && (
              <div className="flex h-full flex-col overflow-hidden">
                <div className="flex shrink-0 items-center gap-2 border-b border-slate-700/30 px-4 py-2">
                  <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Execution Plan
                  </h2>
                </div>
                <div className="min-h-0 flex-1 overflow-hidden">
                  <ExecutionPlanPanel
                    plan={executionPlan}
                    cascadeComplete={cascadeComplete}
                    onSelectOrder={handleSelectOrder}
                    onSelectShipPlan={handleSelectShipPlan}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
