import { useMemo, useState } from "react";
import type { GraphNode, OrderDetail, NegotiationRound, ShipPlanDetail } from "../types";

/* ── Risk types ───────────────────────────────────────────── */

interface RiskFactor {
  name: string;
  score: number;     // 1-6
  maxScore: number;  // always 6
  why: string;
  impact: string;
  mitigation: string;
}

interface SupplierRisk {
  supplierId: string;
  supplierName: string;
  totalScore: number;
  maxScore: number;
  level: "HIGH" | "MEDIUM" | "LOW";
  factors: RiskFactor[];
  dependencyScore: number;
  singleSourceScore: number;
  leadTimeScore: number;
}

interface BottleneckInfo {
  name: string;
  score: number;
  type: string;
}

interface Props {
  nodes: GraphNode[];
  orders: OrderDetail[];
  negotiations: NegotiationRound[];
  shipPlans: ShipPlanDetail[];
}

/* ── Risk colour helpers ──────────────────────────────────── */

const LEVEL_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  HIGH:   { bg: "rgba(248,113,113,0.15)", text: "#f87171", border: "#f87171" },
  MEDIUM: { bg: "rgba(251,191,36,0.15)",  text: "#fbbf24", border: "#fbbf24" },
  LOW:    { bg: "rgba(74,222,128,0.15)",   text: "#4ade80", border: "#4ade80" },
};

const FACTOR_COLORS: Record<string, string> = {
  Dependency:    "#fbbf24",
  "Single Source": "#fb923c",
  "Lead Time":   "#38bdf8",
};

function riskLevel(score: number): "HIGH" | "MEDIUM" | "LOW" {
  if (score >= 12) return "HIGH";
  if (score >= 7) return "MEDIUM";
  return "LOW";
}

/* ── Bar segment component ────────────────────────────────── */

function ScoreBar({ factors, maxScore }: { factors: RiskFactor[]; maxScore: number }) {
  return (
    <div className="flex w-full gap-px overflow-hidden rounded-full" style={{ height: 6 }}>
      {factors.map((f) => (
        <div
          key={f.name}
          style={{
            width: `${(f.score / maxScore) * 100}%`,
            backgroundColor: FACTOR_COLORS[f.name] ?? "#94a3b8",
            minWidth: f.score > 0 ? 4 : 0,
          }}
        />
      ))}
      {/* remaining "empty" portion */}
      <div
        style={{
          flex: 1,
          backgroundColor: "rgba(148,163,184,0.15)",
        }}
      />
    </div>
  );
}

/* ── Legend dots ───────────────────────────────────────────── */

function Legend({ factors }: { factors: RiskFactor[] }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-[0.6rem] text-slate-400">
      {factors.map((f) => (
        <span key={f.name} className="flex items-center gap-1">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: FACTOR_COLORS[f.name] ?? "#94a3b8" }}
          />
          {f.name} {f.score}
        </span>
      ))}
    </div>
  );
}

/* ── Supplier risk card ───────────────────────────────────── */

function SupplierCard({ risk }: { risk: SupplierRisk }) {
  const [expanded, setExpanded] = useState(false);
  const lc = LEVEL_COLORS[risk.level];

  return (
    <div
      className="rounded-lg border transition-colors"
      style={{
        borderColor: `${lc.border}30`,
        backgroundColor: "rgba(15,23,42,0.6)",
      }}
    >
      {/* Header row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <span className="truncate text-sm font-semibold text-slate-200">
              {risk.supplierName}
            </span>
            <div className="flex items-center gap-2">
              <span
                className="rounded px-2 py-0.5 text-[0.6rem] font-bold uppercase"
                style={{ backgroundColor: lc.bg, color: lc.text }}
              >
                {risk.level}
              </span>
              <span className="text-sm font-mono font-bold" style={{ color: lc.text }}>
                {risk.totalScore}
              </span>
              <svg
                className={`h-3.5 w-3.5 text-slate-500 transition-transform ${expanded ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
          <div className="mt-2">
            <ScoreBar factors={risk.factors} maxScore={risk.maxScore} />
          </div>
          <div className="mt-1.5">
            <Legend factors={risk.factors} />
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-slate-700/40 px-4 pb-4 pt-3 space-y-4">
          {risk.factors.map((f) => (
            <div key={f.name}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: FACTOR_COLORS[f.name] ?? "#94a3b8" }}
                  />
                  <span className="text-xs font-semibold text-slate-200">{f.name}</span>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-[0.6rem] font-bold"
                  style={{ backgroundColor: `${FACTOR_COLORS[f.name]}20`, color: FACTOR_COLORS[f.name] }}
                >
                  {f.score}/{f.maxScore}
                </span>
              </div>
              <div className="mt-1.5 ml-4.5 space-y-0.5 text-[0.65rem] leading-relaxed text-slate-400">
                <p>
                  <span className="text-slate-500">Why: </span>
                  {f.why}
                </p>
                <p>
                  <span className="text-slate-500">Impact: </span>
                  {f.impact}
                </p>
                <p>
                  <span className="text-cyan-500">Mitigation: </span>
                  {f.mitigation}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Main component ───────────────────────────────────────── */

export default function RiskAnalysis({ nodes, orders, negotiations, shipPlans }: Props) {
  const analysis = useMemo(() => {
    // ── Gather supplier nodes ──
    const supplierNodes = nodes.filter((n) => n.role === "supplier");
    if (supplierNodes.length === 0 && orders.length === 0) return null;

    // ── Build maps for analysis ──
    const totalOrders = orders.length;
    const ordersBySupplier = new Map<string, OrderDetail[]>();
    const partSupplierMap = new Map<string, Set<string>>(); // part → set of supplier IDs that can supply it

    for (const order of orders) {
      const existing = ordersBySupplier.get(order.supplier) ?? [];
      existing.push(order);
      ordersBySupplier.set(order.supplier, existing);

      const parts = partSupplierMap.get(order.part) ?? new Set();
      parts.add(order.supplier);
      partSupplierMap.set(order.part, parts);
    }

    // Also count from negotiations (RFQs sent = suppliers that were considered)
    for (const neg of negotiations) {
      const parts = partSupplierMap.get(neg.part) ?? new Set();
      parts.add(neg.supplier);
      partSupplierMap.set(neg.part, parts);
    }

    // Average lead time across all orders (for comparison)
    const leadTimes = orders.filter((o) => o.leadTimeDays != null).map((o) => o.leadTimeDays!);
    const avgLeadTime = leadTimes.length > 0 ? leadTimes.reduce((a, b) => a + b, 0) / leadTimes.length : 7;

    // Ship plan lookup
    const shipPlanByOrder = new Map<string, ShipPlanDetail>();
    for (const sp of shipPlans) {
      shipPlanByOrder.set(sp.orderId, sp);
    }

    // ── Compute risk per supplier ──
    const supplierRisks: SupplierRisk[] = [];

    // Include all suppliers that have orders
    const suppliersToAnalyze = new Set<string>();
    for (const order of orders) suppliersToAnalyze.add(order.supplier);
    // Also include supplier nodes even without orders (from negotiations)
    for (const neg of negotiations) {
      if (neg.accepted) suppliersToAnalyze.add(neg.supplier);
    }

    for (const supplierId of suppliersToAnalyze) {
      const supplierOrders = ordersBySupplier.get(supplierId) ?? [];
      const node = nodes.find((n) => n.id === supplierId);
      const supplierName = node?.label ?? supplierOrders[0]?.supplierName ?? supplierId;

      // 1. Dependency Score (1-6)
      // How concentrated are orders with this supplier?
      const orderConcentration = totalOrders > 0 ? supplierOrders.length / totalOrders : 0;
      const totalValue = supplierOrders.reduce((sum, o) => sum + o.totalPrice, 0);
      const totalAllValue = orders.reduce((sum, o) => sum + o.totalPrice, 0);
      const valueConcentration = totalAllValue > 0 ? totalValue / totalAllValue : 0;
      const depRaw = Math.max(orderConcentration, valueConcentration);
      const dependencyScore = Math.min(6, Math.max(1, Math.round(depRaw * 6 + 1)));

      let depWhy: string;
      let depImpact: string;
      let depMitigation: string;

      if (dependencyScore >= 4) {
        depWhy = `High volume of orders concentrated with this supplier (${(depRaw * 100).toFixed(0)}% of total value)`;
        depImpact = "Supplier overwhelm may lead to quality issues";
        depMitigation = "Load balance orders across multiple suppliers";
      } else if (dependencyScore >= 2) {
        depWhy = `Moderate order concentration (${(depRaw * 100).toFixed(0)}% of total value)`;
        depImpact = "Some risk of capacity strain during peak periods";
        depMitigation = "Monitor supplier capacity and have contingency plans";
      } else {
        depWhy = "Orders well distributed across suppliers";
        depImpact = "Low risk of over-dependency";
        depMitigation = "Continue current balanced distribution strategy";
      }

      // 2. Single Source Score (1-6)
      // For parts this supplier provides, are there alternatives?
      const supplierParts = supplierOrders.map((o) => o.part);
      const uniqueParts = [...new Set(supplierParts)];
      let singleSourceCount = 0;
      for (const part of uniqueParts) {
        const alternativeSuppliers = partSupplierMap.get(part);
        if (!alternativeSuppliers || alternativeSuppliers.size <= 1) {
          singleSourceCount++;
        }
      }
      const singleSourceRatio = uniqueParts.length > 0 ? singleSourceCount / uniqueParts.length : 0;
      const singleSourceScore = Math.min(6, Math.max(1, Math.round(singleSourceRatio * 5 + 1)));

      let ssWhy: string;
      let ssImpact: string;
      let ssMitigation: string;

      if (singleSourceScore >= 4) {
        ssWhy = `Limited backup options if supplier capacity reduced (${singleSourceCount}/${uniqueParts.length} parts sole-sourced)`;
        ssImpact = "Cannot fulfill orders if supplier is unavailable";
        ssMitigation = "Establish relationships with alternative suppliers";
      } else if (singleSourceScore >= 2) {
        ssWhy = "Some parts have limited alternative suppliers";
        ssImpact = "Partial order fulfillment risk if supplier has issues";
        ssMitigation = "Qualify additional suppliers for critical parts";
      } else {
        ssWhy = "Multiple supplier options available for all parts";
        ssImpact = "Low risk — can switch suppliers if needed";
        ssMitigation = "Maintain existing supplier relationships";
      }

      // 3. Lead Time Score (1-6)
      // How does this supplier's lead time compare?
      const supplierLeadTimes = supplierOrders
        .filter((o) => o.leadTimeDays != null)
        .map((o) => o.leadTimeDays!);
      const supplierAvgLead = supplierLeadTimes.length > 0
        ? supplierLeadTimes.reduce((a, b) => a + b, 0) / supplierLeadTimes.length
        : avgLeadTime;

      // Also factor in transit time from ship plans
      const relevantShipPlans = shipPlans.filter((sp) =>
        supplierOrders.some((o) => o.orderId === sp.orderId)
      );
      const transitTimes = relevantShipPlans
        .filter((sp) => sp.transitTimeDays != null)
        .map((sp) => sp.transitTimeDays!);
      const avgTransit = transitTimes.length > 0
        ? transitTimes.reduce((a, b) => a + b, 0) / transitTimes.length
        : 0;

      const totalLeadTime = supplierAvgLead + avgTransit;
      const leadTimeRatio = avgLeadTime > 0 ? totalLeadTime / (avgLeadTime + avgTransit) : 1;
      const leadTimeScore = Math.min(6, Math.max(1, Math.round(leadTimeRatio * 3 + 1)));

      let ltWhy: string;
      let ltImpact: string;
      let ltMitigation: string;

      if (leadTimeScore >= 4) {
        ltWhy = `Supplier has longer production cycles than competitors (~${Math.round(supplierAvgLead)}d lead + ${Math.round(avgTransit)}d transit)`;
        ltImpact = "Increases project timeline and customer wait time";
        ltMitigation = "Pre-order or negotiate expedited fulfillment options";
      } else if (leadTimeScore >= 2) {
        ltWhy = `Lead time is around average (~${Math.round(supplierAvgLead)}d lead time)`;
        ltImpact = "Acceptable timeline but limited buffer for delays";
        ltMitigation = "Build buffer time into project planning";
      } else {
        ltWhy = "Supplier has competitive lead times";
        ltImpact = "Low risk of delivery delays";
        ltMitigation = "Leverage fast lead times for just-in-time ordering";
      }

      // Reliability adjustment: lower reliability → increase scores
      const reliability = node?.reliabilityScore;
      let reliabilityBoost = 0;
      if (reliability !== undefined) {
        if (reliability < 0.5) reliabilityBoost = 2;
        else if (reliability < 0.7) reliabilityBoost = 1;
      }

      const adjDep = Math.min(6, dependencyScore + reliabilityBoost);
      const adjSS = Math.min(6, singleSourceScore + reliabilityBoost);
      const adjLT = Math.min(6, leadTimeScore + reliabilityBoost);

      const totalScore = adjDep + adjSS + adjLT;
      const maxScore = 18;

      const factors: RiskFactor[] = [
        { name: "Dependency", score: adjDep, maxScore: 6, why: depWhy, impact: depImpact, mitigation: depMitigation },
        { name: "Single Source", score: adjSS, maxScore: 6, why: ssWhy, impact: ssImpact, mitigation: ssMitigation },
        { name: "Lead Time", score: adjLT, maxScore: 6, why: ltWhy, impact: ltImpact, mitigation: ltMitigation },
      ];

      supplierRisks.push({
        supplierId,
        supplierName,
        totalScore,
        maxScore,
        level: riskLevel(totalScore),
        factors,
        dependencyScore: adjDep,
        singleSourceScore: adjSS,
        leadTimeScore: adjLT,
      });
    }

    // Sort by total score descending
    supplierRisks.sort((a, b) => b.totalScore - a.totalScore);

    // ── Summary counts ──
    const highCount = supplierRisks.filter((r) => r.level === "HIGH").length;
    const mediumCount = supplierRisks.filter((r) => r.level === "MEDIUM").length;
    const lowCount = supplierRisks.filter((r) => r.level === "LOW").length;

    // ── Primary bottleneck ──
    let bottleneck: BottleneckInfo | null = null;

    // Check for bottleneck: the entity with the highest aggregated risk
    // Could be a supplier, or a structural issue like "Manufacturer" (procurement node)
    if (supplierRisks.length > 0) {
      const worst = supplierRisks[0];
      bottleneck = {
        name: worst.supplierName,
        score: worst.totalScore,
        type: worst.level === "HIGH" ? "Critical" : worst.level === "MEDIUM" ? "Moderate" : "Low",
      };
    }

    // Also check if procurement concentration itself is a risk
    const procNode = nodes.find((n) => n.role === "procurement");
    if (procNode && orders.length > 0) {
      // Procurement as single point of orchestration
      const procScore = Math.min(18, 4 + Math.floor(orders.length / 2) + Math.floor(negotiations.length / 3));
      if (!bottleneck || procScore > bottleneck.score) {
        bottleneck = {
          name: procNode.label,
          score: procScore,
          type: procScore >= 12 ? "Critical" : "Moderate",
        };
      }
    }

    return {
      supplierRisks,
      highCount,
      mediumCount,
      lowCount,
      bottleneck,
    };
  }, [nodes, orders, negotiations, shipPlans]);

  // ── Empty state ──
  if (!analysis || analysis.supplierRisks.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <svg className="h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
        <p className="text-sm text-slate-500">
          Risk analysis will appear once orders are placed.
        </p>
        <p className="text-[0.65rem] text-slate-600">
          Waiting for supply chain data...
        </p>
      </div>
    );
  }

  const { supplierRisks, highCount, mediumCount, lowCount, bottleneck } = analysis;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* ── Title ── */}
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-300" style={{ fontFamily: "monospace" }}>
            Risk &amp; Bottleneck Analysis
          </h2>
        </div>

        {/* ── Summary cards ── */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "HIGH", count: highCount, color: "#f87171", bg: "rgba(248,113,113,0.12)" },
            { label: "MEDIUM", count: mediumCount, color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
            { label: "LOW", count: lowCount, color: "#4ade80", bg: "rgba(74,222,128,0.12)" },
          ].map((item) => (
            <div
              key={item.label}
              className="flex flex-col items-center rounded-lg border py-3"
              style={{
                borderColor: `${item.color}30`,
                backgroundColor: item.bg,
              }}
            >
              <span className="text-2xl font-bold" style={{ color: item.color }}>
                {item.count}
              </span>
              <span className="mt-0.5 text-[0.55rem] font-bold uppercase tracking-wider text-slate-400">
                {item.label}
              </span>
            </div>
          ))}
        </div>

        {/* ── Primary bottleneck ── */}
        {bottleneck && (
          <div
            className="rounded-lg border px-4 py-3"
            style={{
              borderColor: "rgba(251,191,36,0.25)",
              backgroundColor: "rgba(251,191,36,0.06)",
            }}
          >
            <div className="flex items-center gap-2 text-[0.6rem] font-bold uppercase tracking-widest text-amber-400">
              <span>⚡</span>
              Primary Bottleneck
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <span className="text-sm font-bold text-slate-200" style={{ fontFamily: "monospace" }}>
                {bottleneck.name}
              </span>
              <span className="text-[0.6rem] font-mono text-slate-500">
                score {bottleneck.score}
              </span>
            </div>
          </div>
        )}

        {/* ── Supplier risk cards ── */}
        <div className="space-y-3">
          {supplierRisks.map((risk) => (
            <SupplierCard key={risk.supplierId} risk={risk} />
          ))}
        </div>

        {/* ── Footer note ── */}
        <p className="pb-2 text-center text-[0.55rem] text-slate-600">
          Scores computed from order concentration, sourcing alternatives, lead times, and reliability data.
        </p>
      </div>
    </div>
  );
}
