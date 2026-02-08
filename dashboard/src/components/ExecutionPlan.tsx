import { useState, useCallback } from "react";
import type { ExecutionPlan } from "../types";

interface ExecutionPlanProps {
  plan: ExecutionPlan | null;
  cascadeComplete: boolean;
  onSelectOrder?: (partName: string, supplierId: string) => void;
  onSelectShipPlan?: (index: number) => void;
}

type Tab = "overview" | "orders" | "shipping" | "missing" | "report";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  {
    id: "overview",
    label: "Overview",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
    ),
  },
  {
    id: "orders",
    label: "Orders",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    id: "shipping",
    label: "Shipping",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
      </svg>
    ),
  },
  {
    id: "missing",
    label: "Missing",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
      </svg>
    ),
  },
  {
    id: "report",
    label: "Report",
    icon: (
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
      </svg>
    ),
  },
];

/** Renders the final execution summary with tabbed detail views. */
export default function ExecutionPlanPanel({
  plan,
  cascadeComplete,
  onSelectOrder,
  onSelectShipPlan,
}: ExecutionPlanProps) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  const handleDownload = useCallback(() => {
    if (!plan) return;
    const reportData = plan.report ?? {
      summary: {
        totalCost: plan.totalCost,
        currency: plan.currency,
        partsCount: plan.partsCount,
        suppliersEngaged: plan.suppliersEngaged,
        ordersPlaced: plan.ordersPlaced,
        shippingPlans: plan.shippingPlans,
        estimatedDelivery: plan.estimatedDelivery,
      },
      orders: plan.orders,
      shipPlans: plan.shipPlans,
      negotiations: plan.negotiations,
    };
    const blob = new Blob([JSON.stringify(reportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    a.download = `coordination_report_${ts}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [plan]);

  if (!cascadeComplete || !plan) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        <div className="text-center">
          <svg
            className="mx-auto mb-2 h-8 w-8 opacity-30"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p className="text-xs">Waiting for cascade to complete...</p>
          <p className="mt-1 text-[0.6rem] text-slate-600">
            Summary appears when all phases finish
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Success banner */}
      <div className="flex shrink-0 items-center gap-2 border-b border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
        </span>
        <span className="text-xs font-medium text-emerald-300">
          Cascade Complete
        </span>
        {/* Download in banner */}
        <button
          onClick={handleDownload}
          className="ml-auto flex items-center gap-1 rounded-md bg-emerald-600/30 px-2 py-0.5 text-[0.6rem] font-medium text-emerald-300 transition-colors hover:bg-emerald-600/50"
        >
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
          Download
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex shrink-0 border-b border-slate-700/40">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1 px-3 py-1.5 text-[0.6rem] font-medium transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-sky-500 text-sky-400"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {tab.icon}
            {tab.label}
            {tab.id === "orders" && plan.ordersPlaced > 0 && (
              <span className="ml-0.5 rounded-full bg-sky-500/20 px-1 py-px text-[0.5rem] text-sky-400">
                {plan.ordersPlaced}
              </span>
            )}
            {tab.id === "shipping" && plan.shippingPlans > 0 && (
              <span className="ml-0.5 rounded-full bg-orange-500/20 px-1 py-px text-[0.5rem] text-orange-400">
                {plan.shippingPlans}
              </span>
            )}
            {tab.id === "missing" && plan.missingParts.length > 0 && (
              <span className="ml-0.5 rounded-full bg-red-500/20 px-1 py-px text-[0.5rem] text-red-400">
                {plan.missingParts.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === "overview" && <OverviewTab plan={plan} />}
        {activeTab === "orders" && <OrdersTab plan={plan} onSelectOrder={onSelectOrder} />}
        {activeTab === "shipping" && <ShippingTab plan={plan} onSelectShipPlan={onSelectShipPlan} />}
        {activeTab === "missing" && <MissingPartsTab plan={plan} />}
        {activeTab === "report" && (
          <ReportTab plan={plan} onDownload={handleDownload} />
        )}
      </div>
    </div>
  );
}

/* ── Overview Tab ─────────────────────────────────────────── */

function OverviewTab({ plan }: { plan: ExecutionPlan }) {
  const metrics = [
    {
      label: "Total Cost",
      value: `${currencySymbol(plan.currency)}${plan.totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      sub: plan.currency,
      color: "text-emerald-400",
      bgColor: "bg-emerald-500/10",
    },
    {
      label: "Parts Sourced",
      value: String(plan.partsCount),
      sub: "unique parts",
      color: "text-sky-400",
      bgColor: "bg-sky-500/10",
    },
    {
      label: "Suppliers",
      value: String(plan.suppliersEngaged),
      sub: "engaged",
      color: "text-indigo-400",
      bgColor: "bg-indigo-500/10",
    },
    {
      label: "Orders",
      value: String(plan.ordersPlaced),
      sub: "placed",
      color: "text-cyan-400",
      bgColor: "bg-cyan-500/10",
    },
    {
      label: "Ship Plans",
      value: String(plan.shippingPlans),
      sub: "routes",
      color: "text-orange-400",
      bgColor: "bg-orange-500/10",
    },
    {
      label: "Missing Parts",
      value: String(plan.missingParts.length),
      sub: plan.missingParts.length > 0 ? "gaps" : "none",
      color: plan.missingParts.length > 0 ? "text-red-400" : "text-slate-400",
      bgColor: plan.missingParts.length > 0 ? "bg-red-500/10" : "bg-slate-500/10",
    },
    {
      label: "Est. Delivery",
      value: plan.estimatedDelivery
        ? formatDate(plan.estimatedDelivery)
        : "TBD",
      sub: plan.estimatedDelivery ? daysFromNow(plan.estimatedDelivery) : "",
      color: "text-purple-400",
      bgColor: "bg-purple-500/10",
    },
  ];

  // Cost breakdown by order
  const costBySupplier = new Map<string, number>();
  for (const o of plan.orders) {
    const prev = costBySupplier.get(o.supplierName) ?? 0;
    costBySupplier.set(o.supplierName, prev + o.totalPrice);
  }
  const costEntries = [...costBySupplier.entries()].sort((a, b) => b[1] - a[1]);
  const maxCost = costEntries.length > 0 ? costEntries[0][1] : 1;

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* Metrics grid */}
      <div className="grid grid-cols-3 gap-1.5">
        {metrics.map((m) => (
          <div
            key={m.label}
            className={`flex flex-col items-center rounded-lg ${m.bgColor} p-2.5 text-center`}
          >
            <span className={`text-sm font-bold ${m.color}`}>{m.value}</span>
            <span className="text-[0.55rem] uppercase tracking-wider text-slate-500">
              {m.label}
            </span>
            {m.sub && (
              <span className="mt-0.5 text-[0.5rem] text-slate-600">{m.sub}</span>
            )}
          </div>
        ))}
      </div>

      {/* Cost breakdown bar chart */}
      {costEntries.length > 0 && (
        <div className="rounded-lg border border-slate-700/30 bg-slate-800/30 p-2.5">
          <h3 className="mb-2 text-[0.6rem] font-semibold uppercase tracking-wider text-slate-400">
            Cost by Supplier
          </h3>
          <div className="flex flex-col gap-1.5">
            {costEntries.map(([name, cost]) => (
              <div key={name} className="flex items-center gap-2">
                <span className="w-20 truncate text-[0.6rem] text-slate-400">
                  {name}
                </span>
                <div className="relative h-3 flex-1 overflow-hidden rounded-full bg-slate-700/50">
                  <div
                    className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-500"
                    style={{
                      width: `${(cost / maxCost) * 100}%`,
                    }}
                  />
                </div>
                <span className="w-16 text-right font-mono text-[0.6rem] text-slate-300">
                  {currencySymbol(plan.currency)}{cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Negotiation summary */}
      {plan.negotiations.length > 0 && (
        <div className="rounded-lg border border-slate-700/30 bg-slate-800/30 p-2.5">
          <h3 className="mb-2 text-[0.6rem] font-semibold uppercase tracking-wider text-slate-400">
            Negotiation Results
          </h3>
          <div className="flex flex-col gap-1">
            {plan.negotiations
              .filter((n) => n.accepted || n.rejected)
              .map((n, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-md bg-slate-800/40 px-2 py-1 text-[0.6rem]"
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${n.accepted ? "bg-emerald-400" : "bg-red-400"}`}
                  />
                  <span className="flex-1 truncate text-slate-300">
                    {n.part}
                  </span>
                  <span className="text-slate-500">{n.supplierName}</span>
                  {n.quotedPrice != null && (
                    <span className="font-mono text-slate-400">
                      {currencySymbol(plan.currency)}{n.revisedPrice ?? n.quotedPrice}
                    </span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Orders Tab ───────────────────────────────────────────── */

function OrdersTab({ plan, onSelectOrder }: { plan: ExecutionPlan; onSelectOrder?: (partName: string, supplierId: string) => void }) {
  if (plan.orders.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-slate-500">
        <p className="text-xs">No individual order details available</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-3">
      {plan.orders.map((order, i) => (
        <div
          key={order.orderId}
          onClick={() => onSelectOrder?.(order.part, order.supplier)}
          className={`rounded-lg border border-slate-700/30 bg-slate-800/30 p-3 transition-colors ${onSelectOrder ? "cursor-pointer hover:border-cyan-500/40 hover:bg-slate-800/60" : ""}`}
        >
          {/* Order header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-md bg-cyan-500/20 text-[0.55rem] font-bold text-cyan-400">
                {i + 1}
              </span>
              <span className="text-xs font-medium text-slate-200">
                {order.part}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {onSelectOrder && (
                <span className="flex items-center gap-0.5 text-[0.5rem] text-cyan-400/60">
                  <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                  graph
                </span>
              )}
              <span className="rounded-md bg-slate-700/40 px-1.5 py-0.5 font-mono text-[0.55rem] text-slate-400">
                #{order.orderId.slice(0, 8)}
              </span>
            </div>
          </div>

          {/* Order details grid */}
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[0.6rem]">
            <div>
              <span className="text-slate-500">Supplier</span>
              <p className="font-medium text-slate-300">{order.supplierName}</p>
            </div>
            <div>
              <span className="text-slate-500">Quantity</span>
              <p className="font-medium text-slate-300">{order.quantity}</p>
            </div>
            <div>
              <span className="text-slate-500">Unit Price</span>
              <p className="font-medium text-slate-300">
                {currencySymbol(order.currency)}{order.unitPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            </div>
            <div>
              <span className="text-slate-500">Total</span>
              <p className="font-bold text-emerald-400">
                {currencySymbol(order.currency)}{order.totalPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            </div>
            {order.leadTimeDays != null && (
              <div>
                <span className="text-slate-500">Lead Time</span>
                <p className="font-medium text-slate-300">
                  {order.leadTimeDays} days
                </p>
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Total */}
      <div className="flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
        <span className="text-xs font-semibold text-emerald-300">
          Total Order Value
        </span>
        <span className="font-mono text-sm font-bold text-emerald-400">
          {currencySymbol(plan.currency)}
          {plan.totalCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </span>
      </div>
    </div>
  );
}

/* ── Shipping Tab ─────────────────────────────────────────── */

function ShippingTab({ plan, onSelectShipPlan }: { plan: ExecutionPlan; onSelectShipPlan?: (index: number) => void }) {
  if (plan.shipPlans.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-slate-500">
        <p className="text-xs">No shipping plan details available</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-3">
      {plan.shipPlans.map((sp, i) => (
        <div
          key={i}
          onClick={() => onSelectShipPlan?.(i)}
          className={`rounded-lg border border-slate-700/30 bg-slate-800/30 p-3 transition-colors ${onSelectShipPlan ? "cursor-pointer hover:border-orange-500/40 hover:bg-slate-800/60" : ""}`}
        >
          {/* Route visualization */}
          <div className="flex items-center gap-1.5 text-xs">
            {onSelectShipPlan && (
              <span className="flex items-center gap-0.5 mr-1 text-[0.5rem] text-orange-400/60">
                <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                </svg>
              </span>
            )}
            {/* Origin pin */}
            <svg className="h-3.5 w-3.5 shrink-0 text-orange-400" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z"
                clipRule="evenodd"
              />
            </svg>
            <span className="font-medium text-slate-200">{sp.pickup}</span>

            {/* Route waypoints */}
            {sp.route.length > 0 && (
              <div className="flex flex-1 items-center gap-1">
                <div className="h-px flex-1 border-t border-dashed border-slate-600" />
                {sp.route.length > 2 && (
                  <span className="rounded-full bg-slate-700/60 px-1.5 py-px text-[0.5rem] text-slate-400">
                    {sp.route.length - 2} stops
                  </span>
                )}
                <div className="h-px flex-1 border-t border-dashed border-slate-600" />
              </div>
            )}

            {/* Destination pin */}
            <svg className="h-3.5 w-3.5 shrink-0 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z"
                clipRule="evenodd"
              />
            </svg>
            <span className="font-medium text-slate-200">{sp.delivery}</span>
          </div>

          {/* Route details shown below */}
          {sp.route.length > 0 && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[0.55rem] text-slate-500">
              {sp.route.map((stop, j) => (
                <span key={j} className="flex items-center gap-1">
                  {j > 0 && <span className="text-slate-600">&rarr;</span>}
                  <span className="rounded bg-slate-700/40 px-1 py-px">
                    {stop}
                  </span>
                </span>
              ))}
            </div>
          )}

          {/* Metrics row */}
          <div className="mt-2 flex gap-3 text-[0.6rem]">
            {sp.transitTimeDays != null && (
              <div>
                <span className="text-slate-500">Transit</span>
                <p className="font-medium text-slate-300">
                  {sp.transitTimeDays}d
                </p>
              </div>
            )}
            {sp.cost != null && (
              <div>
                <span className="text-slate-500">Cost</span>
                <p className="font-medium text-slate-300">
                  {currencySymbol(plan.currency)}{sp.cost.toLocaleString()}
                </p>
              </div>
            )}
            {sp.estimatedArrival && (
              <div>
                <span className="text-slate-500">ETA</span>
                <p className="font-medium text-slate-300">
                  {formatDate(sp.estimatedArrival)}
                </p>
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Shipping total */}
      {(() => {
        const totalShipCost = plan.shipPlans.reduce(
          (s, sp) => s + (sp.cost ?? 0),
          0,
        );
        const maxTransit = Math.max(
          ...plan.shipPlans.map((sp) => sp.transitTimeDays ?? 0),
        );
        return (
          totalShipCost > 0 && (
            <div className="flex items-center justify-between rounded-lg border border-orange-500/20 bg-orange-500/5 px-3 py-2 text-xs">
              <div>
                <span className="font-semibold text-orange-300">
                  Total Shipping
                </span>
                {maxTransit > 0 && (
                  <span className="ml-2 text-[0.6rem] text-slate-500">
                    (max {maxTransit}d transit)
                  </span>
                )}
              </div>
              <span className="font-mono font-bold text-orange-400">
                {currencySymbol(plan.currency)}
                {totalShipCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </span>
            </div>
          )
        );
      })()}
    </div>
  );
}

/* ── Missing Parts Tab ────────────────────────────────────── */

function MissingPartsTab({ plan }: { plan: ExecutionPlan }) {
  if (plan.missingParts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-slate-500">
        <div className="text-center">
          <svg
            className="mx-auto mb-2 h-8 w-8 text-emerald-500/40"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-xs font-medium text-emerald-400">All parts sourced</p>
          <p className="mt-1 text-[0.6rem] text-slate-600">
            Every BOM part has at least one qualifying supplier
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-3">
      {/* Warning banner */}
      <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2">
        <svg className="h-4 w-4 shrink-0 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
        <div>
          <p className="text-xs font-medium text-red-300">
            {plan.missingParts.length} part{plan.missingParts.length > 1 ? "s" : ""} could not be sourced
          </p>
          <p className="text-[0.55rem] text-red-400/70">
            No suppliers met the relevance threshold for these parts
          </p>
        </div>
      </div>

      {/* Missing parts list */}
      {plan.missingParts.map((mp, i) => (
        <div
          key={mp.partId ?? i}
          className="rounded-lg border border-red-500/15 bg-slate-800/40 p-3"
        >
          {/* Part header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-md bg-red-500/20 text-[0.55rem] font-bold text-red-400">
                {i + 1}
              </span>
              <span className="text-xs font-medium text-slate-200">
                {mp.partName}
              </span>
            </div>
            {mp.system && (
              <span className="rounded-md bg-slate-700/40 px-1.5 py-0.5 text-[0.55rem] text-slate-400">
                {mp.system}
              </span>
            )}
          </div>

          {/* Part details grid */}
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[0.6rem]">
            <div>
              <span className="text-slate-500">Skill Query</span>
              <p className="font-mono font-medium text-amber-400/80">{mp.skillQuery}</p>
            </div>
            <div>
              <span className="text-slate-500">Quantity Needed</span>
              <p className="font-medium text-slate-300">{mp.quantity}</p>
            </div>
            <div className="col-span-2">
              <span className="text-slate-500">Reason</span>
              <p className="font-medium text-red-400/80">{mp.reason}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Report Tab ───────────────────────────────────────────── */

function ReportTab({
  plan,
  onDownload,
}: {
  plan: ExecutionPlan;
  onDownload: () => void;
}) {
  const [fetchStatus, setFetchStatus] = useState<
    "idle" | "loading" | "done" | "error"
  >("idle");
  const [fetchedReport, setFetchedReport] = useState<Record<string, unknown> | null>(null);

  const fetchFromServer = useCallback(async () => {
    setFetchStatus("loading");
    try {
      const res = await fetch("/api/procurement/report");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setFetchedReport(data);
      setFetchStatus("done");
    } catch {
      setFetchStatus("error");
    }
  }, []);

  const reportData = fetchedReport ?? plan.report ?? null;

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={onDownload}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-sky-600 px-3 py-2 text-[0.65rem] font-medium text-white transition-colors hover:bg-sky-500"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
          Download JSON
        </button>
        <button
          onClick={fetchFromServer}
          disabled={fetchStatus === "loading"}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-600 bg-slate-800/60 px-3 py-2 text-[0.65rem] font-medium text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          {fetchStatus === "loading" ? (
            <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          )}
          Fetch from Server
        </button>
      </div>

      {fetchStatus === "error" && (
        <p className="text-[0.6rem] text-red-400">
          Failed to fetch from server. Using local data.
        </p>
      )}

      {/* Report preview */}
      {reportData ? (
        <div className="overflow-hidden rounded-lg border border-slate-700/30 bg-slate-900/60">
          <div className="flex items-center justify-between border-b border-slate-700/30 px-3 py-1.5">
            <span className="text-[0.6rem] font-semibold uppercase tracking-wider text-slate-400">
              Network Coordination Report
            </span>
            <span className="text-[0.5rem] text-slate-600">
              {JSON.stringify(reportData).length.toLocaleString()} bytes
            </span>
          </div>
          <pre className="max-h-64 overflow-auto p-3 text-[0.55rem] leading-relaxed text-slate-400">
            {JSON.stringify(reportData, null, 2)}
          </pre>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-700/30 bg-slate-800/30 p-4 text-center">
          <p className="text-xs text-slate-500">
            No raw report data available
          </p>
          <p className="mt-1 text-[0.6rem] text-slate-600">
            Click "Fetch from Server" to retrieve the full report, or download
            the local summary data
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Helpers ───────────────────────────────────────────────── */

function currencySymbol(currency: string): string {
  switch (currency.toUpperCase()) {
    case "EUR":
      return "\u20AC";
    case "USD":
      return "$";
    case "GBP":
      return "\u00A3";
    default:
      return `${currency} `;
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function daysFromNow(iso: string): string {
  try {
    const diff = Math.ceil(
      (new Date(iso).getTime() - Date.now()) / (1000 * 60 * 60 * 24),
    );
    if (diff < 0) return `${Math.abs(diff)}d ago`;
    if (diff === 0) return "today";
    return `in ${diff}d`;
  } catch {
    return "";
  }
}
