import type {
  GraphSelection,
  OrderDetail,
  ShipPlanDetail,
  AnalyticsMode,
} from "../types";

/* ── Props ───────────────────────────────────────────────── */

interface GraphNavigatorProps {
  selection: GraphSelection;
  orders: OrderDetail[];
  shipPlans: ShipPlanDetail[];
  analyticsMode: AnalyticsMode;
  onOverview: () => void;
  onSelectOrder: (partName: string, supplierId: string) => void;
  onSelectLogistics: (index?: number) => void;
  onAnalyticsChange: (mode: AnalyticsMode) => void;
}

/* ── Analytics buttons config ────────────────────────────── */

const ANALYTICS_MODES: { id: AnalyticsMode; label: string; icon: React.ReactNode; color: string }[] = [
  {
    id: "risk",
    label: "Risk",
    color: "#f87171",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
      </svg>
    ),
  },
  {
    id: "cost",
    label: "Cost",
    color: "#4ade80",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    id: "bottleneck",
    label: "Bottleneck",
    color: "#fb923c",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
];

/* ── Component ───────────────────────────────────────────── */

export default function GraphNavigator({
  selection,
  orders,
  shipPlans,
  analyticsMode,
  onOverview,
  onSelectOrder,
  onSelectLogistics,
  onAnalyticsChange,
}: GraphNavigatorProps) {
  const isOverview = selection.mode === "overview";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ── View selector ────────────────────────────────── */}
      <div className="flex items-center gap-2 border-b border-slate-700/30 px-3 py-2">
        <svg className="h-4 w-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
        </svg>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Graph Navigator
        </h2>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 py-2">
        {/* ── Overview button ────────────────────────────── */}
        <button
          onClick={onOverview}
          className={`mb-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-all ${
            isOverview
              ? "bg-indigo-500/20 text-indigo-300 ring-1 ring-indigo-500/40"
              : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
          }`}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
          Network Overview
          {isOverview && (
            <span className="ml-auto h-2 w-2 rounded-full bg-indigo-400" />
          )}
        </button>

        {/* ── Analytics overlay toggles ──────────────────── */}
        <div className="mb-3">
          <p className="mb-1.5 px-1 text-[0.6rem] font-semibold uppercase tracking-wider text-slate-500">
            Analytics Overlays
          </p>
          <div className="flex gap-1">
            {ANALYTICS_MODES.map((m) => {
              const active = analyticsMode === m.id;
              return (
                <button
                  key={m.id}
                  onClick={() => onAnalyticsChange(active ? "none" : m.id)}
                  className={`flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[0.6rem] font-medium transition-all ${
                    active
                      ? "ring-1 ring-inset"
                      : "text-slate-500 hover:bg-slate-800/60 hover:text-slate-300"
                  }`}
                  style={
                    active
                      ? {
                          color: m.color,
                          backgroundColor: `${m.color}15`,
                          outlineColor: `${m.color}40`,
                          outlineWidth: "1px",
                          outlineStyle: "solid",
                          outlineOffset: "-1px",
                        }
                      : undefined
                  }
                >
                  {m.icon}
                  {m.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Orders section ─────────────────────────────── */}
        <div className="mb-3">
          <p className="mb-1.5 flex items-center gap-1.5 px-1 text-[0.6rem] font-semibold uppercase tracking-wider text-slate-500">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
            Orders
            {orders.length > 0 && (
              <span className="rounded-full bg-cyan-500/20 px-1.5 py-px text-[0.5rem] text-cyan-400">
                {orders.length}
              </span>
            )}
          </p>

          {orders.length === 0 ? (
            <p className="px-1 text-[0.55rem] text-slate-600 italic">
              No orders yet...
            </p>
          ) : (
            <div className="flex flex-col gap-1">
              {orders.map((order, i) => {
                const isActive =
                  selection.mode === "order-detail" &&
                  selection.partName === order.part &&
                  selection.supplierId === order.supplier;

                return (
                  <button
                    key={order.orderId}
                    onClick={() => onSelectOrder(order.part, order.supplier)}
                    className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[0.65rem] transition-all ${
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-500/30"
                        : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                    }`}
                  >
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[0.55rem] font-bold ${
                      isActive ? "bg-cyan-500/30 text-cyan-300" : "bg-slate-700/60 text-slate-400"
                    }`}>
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{order.part}</p>
                      <p className="truncate text-[0.55rem] text-slate-500">
                        {order.supplierName} &middot; &euro;{order.totalPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                    </div>
                    {isActive && (
                      <span className="h-2 w-2 shrink-0 rounded-full bg-cyan-400" />
                    )}
                    {!isActive && (
                      <svg className="h-3 w-3 shrink-0 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Logistics section ──────────────────────────── */}
        <div className="mb-2">
          <p className="mb-1.5 flex items-center gap-1.5 px-1 text-[0.6rem] font-semibold uppercase tracking-wider text-slate-500">
            <span className="h-1.5 w-1.5 rounded-full bg-orange-400" />
            Logistics Routes
            {shipPlans.length > 0 && (
              <span className="rounded-full bg-orange-500/20 px-1.5 py-px text-[0.5rem] text-orange-400">
                {shipPlans.length}
              </span>
            )}
          </p>

          {shipPlans.length === 0 ? (
            <p className="px-1 text-[0.55rem] text-slate-600 italic">
              No ship plans yet...
            </p>
          ) : (
            <div className="flex flex-col gap-1">
              {/* All logistics overview button */}
              <button
                onClick={() => onSelectLogistics()}
                className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[0.65rem] transition-all ${
                  selection.mode === "logistics-detail" && selection.shipPlanIndex === undefined
                    ? "bg-orange-500/15 text-orange-300 ring-1 ring-orange-500/30"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`}
              >
                <svg className="h-4 w-4 shrink-0 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
                </svg>
                <span className="font-medium">All Routes Overview</span>
                {selection.mode === "logistics-detail" && selection.shipPlanIndex === undefined && (
                  <span className="ml-auto h-2 w-2 shrink-0 rounded-full bg-orange-400" />
                )}
              </button>

              {/* Individual ship plans */}
              {shipPlans.map((sp, i) => {
                const isActive =
                  selection.mode === "logistics-detail" &&
                  selection.shipPlanIndex === i;

                return (
                  <button
                    key={i}
                    onClick={() => onSelectLogistics(i)}
                    className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[0.65rem] transition-all ${
                      isActive
                        ? "bg-orange-500/15 text-orange-300 ring-1 ring-orange-500/30"
                        : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                    }`}
                  >
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[0.55rem] font-bold ${
                      isActive ? "bg-orange-500/30 text-orange-300" : "bg-slate-700/60 text-slate-400"
                    }`}>
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">
                        {sp.pickup} &rarr; {sp.delivery}
                      </p>
                      <p className="truncate text-[0.55rem] text-slate-500">
                        {sp.route.length > 0 ? `${sp.route.length} stops` : "direct"}
                        {sp.transitTimeDays != null && ` \u00b7 ${sp.transitTimeDays}d`}
                        {sp.cost != null && ` \u00b7 \u20AC${sp.cost.toLocaleString()}`}
                      </p>
                    </div>
                    {isActive && (
                      <span className="h-2 w-2 shrink-0 rounded-full bg-orange-400" />
                    )}
                    {!isActive && (
                      <svg className="h-3 w-3 shrink-0 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
