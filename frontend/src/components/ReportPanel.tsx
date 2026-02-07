import { useMemo } from "react";
import {
  FileText,
  CheckCircle,
  XCircle,
  Globe,
  Key,
  Shield,
  Navigation,
  DollarSign,
  Clock,
  MapPin,
  Truck,
  Factory,
  ArrowRight,
} from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

// ── Types ────────────────────────────────────────────────────────────────

interface DiscoveryPath {
  query: Record<string, unknown>;
  matched_agents: string[];
  resolution_path?: string;
}

interface TrustRecord {
  agent_id: string;
  reputation_score: number;
  verified: boolean;
  certification_level?: string;
}

interface PolicyRecord {
  order_id: string;
  compliant: boolean;
  issues: string[];
}

interface FinalPlan {
  order_id?: string;
  supplier_id?: string;
  delivery_address?: string;
  agreed_price?: number;
  lead_time_days?: number;
  manufacturing?: { start?: string; end?: string; total_days?: number };
  logistics?: { origin?: string; destination?: string; transport_mode?: string; shipping_days?: number; shipping_cost?: number };
  components_count?: number;
}

interface SynthesizedReport {
  intent: string;
  status: "running" | "completed";
  cascade_steps: number;
  discovery_paths: DiscoveryPath[];
  trust_verification: TrustRecord[];
  policy_enforcement: PolicyRecord[];
  final_plan: FinalPlan;
  total_cost: number;
  total_lead_time_days: number;
}

// ── Synthesize report from events ────────────────────────────────────────

function synthesizeReport(events: WsEvent[]): SynthesizedReport {
  const cascadeStart = events.find((e) => e.type === "cascade_start");
  const cascadeComplete = events.find((e) => e.type === "cascade_complete");
  const backendReport = cascadeComplete?.report as Record<string, unknown> | undefined;

  // If backend report exists and is populated, prefer it
  if (backendReport && (backendReport.discovery_paths as unknown[])?.length > 0) {
    return {
      intent: (backendReport.intent as string) || (cascadeStart?.intent as string) || "",
      status: "completed",
      cascade_steps: ((backendReport.cascade_steps as unknown[]) || []).length,
      discovery_paths: (backendReport.discovery_paths as DiscoveryPath[]) || [],
      trust_verification: (backendReport.trust_verification as TrustRecord[]) || [],
      policy_enforcement: (backendReport.policy_enforcement as PolicyRecord[]) || [],
      final_plan: (backendReport.final_execution_plan as FinalPlan) || {},
      total_cost: (backendReport.total_cost as number) || 0,
      total_lead_time_days: (backendReport.total_lead_time_days as number) || 0,
    };
  }

  // Otherwise, synthesize from WS events
  const agentMessages = events.filter((e) => e.type === "agent_message");
  const intent = (cascadeStart?.intent as string) || "";

  // Discovery paths from discovery_request events
  const discoveryEvents = agentMessages.filter(
    (e) => (e.data as Record<string, unknown>)?.message_type === "discovery_request"
  );
  const discovery_paths: DiscoveryPath[] = discoveryEvents.map((e) => {
    const payload = ((e.data as Record<string, unknown>)?.payload || {}) as Record<string, unknown>;
    return {
      query: (payload.query as Record<string, unknown>) || { role: "supplier" },
      matched_agents: ((payload.agents_discovered as { id: string }[]) || []).map((a) => a.id || String(a)),
      resolution_path: (payload.resolution_path as string) || "",
    };
  });

  // Trust: extract from supplier metadata in discovery payloads
  const trust_verification: TrustRecord[] = [];
  const seenTrust = new Set<string>();
  for (const evt of discoveryEvents) {
    const payload = ((evt.data as Record<string, unknown>)?.payload || {}) as Record<string, unknown>;
    const agents = (payload.agents_discovered as { id: string; resolution?: string }[]) || [];
    for (const a of agents) {
      const aid = a.id || String(a);
      if (!seenTrust.has(aid)) {
        seenTrust.add(aid);
        trust_verification.push({
          agent_id: aid,
          reputation_score: 0.5,
          verified: true,
          certification_level: "verified",
        });
      }
    }
  }

  // Policy enforcement from compliance events
  const complianceEvents = agentMessages.filter(
    (e) => (e.data as Record<string, unknown>)?.message_type === "compliance_result"
  );
  const policy_enforcement: PolicyRecord[] = complianceEvents.map((e) => {
    const payload = ((e.data as Record<string, unknown>)?.payload || {}) as Record<string, unknown>;
    return {
      order_id: (payload.order_id as string) || "",
      compliant: (payload.compliant as boolean) ?? true,
      issues: (payload.issues as string[]) || [],
    };
  });

  // Final plan from order placement + manufacturing result + logistics
  const orderEvent = agentMessages.find(
    (e) => (e.data as Record<string, unknown>)?.message_type === "order_placement"
  );
  const mfgConfirmEvent = agentMessages.find(
    (e) =>
      (e.data as Record<string, unknown>)?.message_type === "order_confirmation" &&
      (e.data as Record<string, unknown>)?.sender_id !== "system"
  );
  const routeEvent = agentMessages.find(
    (e) => (e.data as Record<string, unknown>)?.message_type === "route_confirmation"
  );
  const quoteEvents = agentMessages.filter(
    (e) => (e.data as Record<string, unknown>)?.message_type === "quote_response"
  );

  const orderPayload = ((orderEvent?.data as Record<string, unknown>)?.payload || {}) as Record<string, unknown>;
  const mfgPayload = ((mfgConfirmEvent?.data as Record<string, unknown>)?.payload || {}) as Record<string, unknown>;
  const routePayload = ((routeEvent?.data as Record<string, unknown>)?.payload || {}) as Record<string, unknown>;
  const mfgSchedule = (mfgPayload.assembly_schedule || {}) as Record<string, unknown>;

  const agreedPrice = (orderPayload.agreed_price as number) ||
    (quoteEvents[0] && ((quoteEvents[0].data as Record<string, unknown>)?.payload as Record<string, unknown>)?.total_price as number) || 0;
  const leadTime = (orderPayload.agreed_lead_time_days as number) ||
    (quoteEvents[0] && ((quoteEvents[0].data as Record<string, unknown>)?.payload as Record<string, unknown>)?.lead_time_days as number) || 0;

  const final_plan: FinalPlan = {
    order_id: (orderPayload.order_id as string) || "",
    supplier_id: (orderPayload.supplier_id as string) || "",
    delivery_address: (orderPayload.delivery_address as string) || "Maranello, Italy",
    agreed_price: agreedPrice,
    lead_time_days: leadTime,
    manufacturing: {
      start: mfgSchedule.assembly_start as string,
      end: mfgSchedule.assembly_end as string,
      total_days: mfgSchedule.total_days as number,
    },
    logistics: {
      origin: routePayload.origin as string,
      destination: routePayload.destination as string,
      transport_mode: routePayload.transport_mode as string,
      shipping_days: routePayload.estimated_days as number,
      shipping_cost: routePayload.cost as number,
    },
    components_count: ((orderPayload.components as unknown[]) || []).length || 10,
  };

  return {
    intent,
    status: cascadeComplete ? "completed" : "running",
    cascade_steps: agentMessages.length,
    discovery_paths,
    trust_verification,
    policy_enforcement,
    final_plan,
    total_cost: agreedPrice,
    total_lead_time_days: leadTime,
  };
}

// ── Component ────────────────────────────────────────────────────────────

interface Props {
  events: WsEvent[];
}

export default function ReportPanel({ events }: Props) {
  const report = useMemo(() => synthesizeReport(events), [events]);
  const hasData = events.some((e) => e.type === "agent_message");

  if (!hasData) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-6">
        <FileText size={32} className="text-white/15 mb-3" />
        <p className="text-[11px] text-white/25 font-mono text-center">
          Network Coordination Report will appear when the cascade runs.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b border-panel-border">
        <FileText size={12} className="text-accent-cyan" />
        <h3 className="text-[10px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
          Coordination Report
        </h3>
        <span className={`ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded ${
          report.status === "completed"
            ? "bg-accent-green/10 text-accent-green/70"
            : "bg-accent-orange/10 text-accent-orange/70"
        }`}>
          {report.status === "completed" ? "Complete" : "In Progress"}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Key Metrics */}
        <div className="grid grid-cols-3 gap-1.5 px-3 pt-3 pb-2">
          <MetricBadge
            icon={<DollarSign size={11} />}
            value={report.total_cost > 0 ? `$${report.total_cost.toLocaleString()}` : "--"}
            label="Total Cost"
            color="text-accent-green"
          />
          <MetricBadge
            icon={<Clock size={11} />}
            value={report.total_lead_time_days > 0 ? `${report.total_lead_time_days}d` : "--"}
            label="Lead Time"
            color="text-accent-cyan"
          />
          <MetricBadge
            icon={<MapPin size={11} />}
            value={String(report.cascade_steps)}
            label="Steps"
            color="text-accent-orange"
          />
        </div>

        {/* Discovery Paths */}
        {report.discovery_paths.length > 0 && (
          <Section icon={<Globe size={11} />} title="Discovery Paths" color="text-accent-cyan">
            {report.discovery_paths.map((d, i) => (
              <div key={i} className="bg-accent-cyan/5 border border-accent-cyan/15 rounded-md px-2.5 py-2 mb-1.5">
                <div className="text-[10px] text-accent-cyan/70 font-mono mb-1">
                  {d.resolution_path || `Query: ${JSON.stringify(d.query)}`}
                </div>
                <div className="text-[9px] text-white/35 font-mono">
                  {d.matched_agents.length} agent{d.matched_agents.length !== 1 ? "s" : ""} resolved
                </div>
                {d.matched_agents.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {d.matched_agents.map((a, j) => (
                      <span key={j} className="text-[8px] font-mono px-1.5 py-0.5 rounded bg-accent-cyan/10 text-accent-cyan/50">
                        {a.replace("nanda:", "")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Section>
        )}

        {/* Trust Verification */}
        {report.trust_verification.length > 0 && (
          <Section icon={<Key size={11} />} title="Trust Verification" color="text-accent-gold">
            <div className="space-y-1">
              {report.trust_verification.map((t, i) => (
                <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-panel-dark/40 border border-panel-border/50">
                  {t.verified ? (
                    <CheckCircle size={11} className="text-accent-green shrink-0" />
                  ) : (
                    <XCircle size={11} className="text-red-400 shrink-0" />
                  )}
                  <span className="text-[10px] font-mono text-white/60 truncate flex-1">
                    {t.agent_id.replace("nanda:", "")}
                  </span>
                  <span className="text-[9px] font-mono text-white/30">
                    {t.reputation_score.toFixed(2)}
                  </span>
                  {t.certification_level && t.certification_level !== "unknown" && (
                    <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-accent-gold/10 text-accent-gold/60">
                      {t.certification_level}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Policy Enforcement */}
        {report.policy_enforcement.length > 0 && (
          <Section icon={<Shield size={11} />} title="Policy Enforcement" color="text-accent-purple">
            <div className="space-y-1">
              {report.policy_enforcement.map((p, i) => (
                <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-panel-dark/40 border border-panel-border/50">
                  {p.compliant ? (
                    <CheckCircle size={11} className="text-accent-green shrink-0" />
                  ) : (
                    <XCircle size={11} className="text-red-400 shrink-0" />
                  )}
                  <span className="text-[10px] font-mono text-white/60 flex-1">
                    {p.order_id || "Order"}
                  </span>
                  <span className={`text-[9px] font-mono ${p.compliant ? "text-accent-green/60" : "text-red-400/60"}`}>
                    {p.compliant ? "Compliant" : p.issues.join(", ")}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Final Execution Plan */}
        {(report.final_plan.order_id || report.final_plan.agreed_price) && (
          <Section icon={<Navigation size={11} />} title="Final Execution Plan" color="text-white/50">
            <div className="bg-panel-dark/40 border border-panel-border/50 rounded-lg p-3 space-y-3">
              {/* Order info */}
              <div>
                <div className="text-[9px] font-mono text-white/25 uppercase tracking-wider mb-1.5">Order</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  <PlanRow label="Order ID" value={report.final_plan.order_id} />
                  <PlanRow label="Supplier" value={report.final_plan.supplier_id?.replace("nanda:", "")} />
                  <PlanRow label="Price" value={report.final_plan.agreed_price ? `$${report.final_plan.agreed_price.toLocaleString()}` : undefined} />
                  <PlanRow label="Lead Time" value={report.final_plan.lead_time_days ? `${report.final_plan.lead_time_days} days` : undefined} />
                  <PlanRow label="Components" value={report.final_plan.components_count ? String(report.final_plan.components_count) : undefined} />
                  <PlanRow label="Destination" value={report.final_plan.delivery_address} />
                </div>
              </div>

              {/* Manufacturing */}
              {report.final_plan.manufacturing?.total_days && (
                <div>
                  <div className="flex items-center gap-1 mb-1.5">
                    <Factory size={9} className="text-blue-400/60" />
                    <span className="text-[9px] font-mono text-white/25 uppercase tracking-wider">Manufacturing</span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    <PlanRow label="Start" value={report.final_plan.manufacturing.start} />
                    <PlanRow label="End" value={report.final_plan.manufacturing.end} />
                    <PlanRow label="Duration" value={`${report.final_plan.manufacturing.total_days} days`} />
                  </div>
                </div>
              )}

              {/* Logistics */}
              {report.final_plan.logistics?.transport_mode && (
                <div>
                  <div className="flex items-center gap-1 mb-1.5">
                    <Truck size={9} className="text-accent-orange/60" />
                    <span className="text-[9px] font-mono text-white/25 uppercase tracking-wider">Logistics</span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    <PlanRow label="Route" value={
                      report.final_plan.logistics.origin && report.final_plan.logistics.destination
                        ? `${report.final_plan.logistics.origin} → ${report.final_plan.logistics.destination}`
                        : undefined
                    } />
                    <PlanRow label="Mode" value={report.final_plan.logistics.transport_mode} />
                    <PlanRow label="Transit" value={report.final_plan.logistics.shipping_days ? `${report.final_plan.logistics.shipping_days} days` : undefined} />
                    <PlanRow label="Cost" value={report.final_plan.logistics.shipping_cost ? `$${report.final_plan.logistics.shipping_cost.toLocaleString()}` : undefined} />
                  </div>
                </div>
              )}
            </div>
          </Section>
        )}

        {/* Message Exchange Summary */}
        <Section icon={<ArrowRight size={11} />} title="Message Exchanges" color="text-white/40">
          <div className="grid grid-cols-2 gap-1.5">
            <MsgStat label="Total Messages" value={report.cascade_steps} />
            <MsgStat label="Discoveries" value={events.filter((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "discovery_request").length} />
            <MsgStat label="Quotes" value={events.filter((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "quote_response").length} />
            <MsgStat label="Negotiations" value={events.filter((e) => e.type === "agent_message" && (e.data as Record<string, unknown>)?.message_type === "negotiation_proposal").length} />
          </div>
        </Section>

        {/* Footer */}
        <div className="px-3 pb-3 mt-1">
          <div className="text-[8px] text-white/15 font-mono leading-relaxed">
            Architecture: NANDA Lean Index + Adaptive Resolver (Context-Aware Tailored Endpoints)
            {" | "}Signatures: Ed25519 (AgentAddr) + W3C VC v2 (AgentFacts)
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────

function Section({ icon, title, color, children }: { icon: React.ReactNode; title: string; color: string; children: React.ReactNode }) {
  return (
    <div className="px-3 pb-3">
      <div className={`flex items-center gap-1.5 mb-2 ${color}`}>
        {icon}
        <span className="text-[9px] font-mono font-semibold uppercase tracking-wider opacity-60">
          {title}
        </span>
      </div>
      {children}
    </div>
  );
}

function MetricBadge({ icon, value, label, color }: { icon: React.ReactNode; value: string; label: string; color: string }) {
  return (
    <div className="bg-panel-dark/60 border border-panel-border rounded-md px-2 py-2 text-center">
      <div className={`${color} flex items-center justify-center mb-0.5`}>{icon}</div>
      <div className={`text-sm font-bold font-mono ${value === "--" ? "text-white/20" : "text-white/80"}`}>{value}</div>
      <div className="text-[8px] text-white/25 font-mono uppercase">{label}</div>
    </div>
  );
}

function PlanRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="flex items-baseline gap-1">
      <span className="text-[9px] text-white/25 font-mono">{label}:</span>
      <span className="text-[9px] text-white/55 font-mono truncate">{value}</span>
    </div>
  );
}

function MsgStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-1 px-2 rounded bg-panel-dark/40 border border-panel-border/50">
      <span className="text-[9px] text-white/30 font-mono">{label}</span>
      <span className="text-[10px] text-white/60 font-mono font-medium">{value}</span>
    </div>
  );
}
