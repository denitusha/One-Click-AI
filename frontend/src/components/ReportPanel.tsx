import {
  FileText, CheckCircle, XCircle, Clock, DollarSign, MapPin,
  Shield, Key, Globe, Fingerprint, Radar, Navigation, Handshake,
} from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

interface Props {
  events: WsEvent[];
}

export default function ReportPanel({ events }: Props) {
  const completeEvt = events.find((e) => e.type === "cascade_complete");
  const report = completeEvt?.report as Record<string, unknown> | undefined;

  // Extract NANDA resolution events
  const nandaResolutions = events.filter(
    (e) =>
      e.type === "agent_message" &&
      e.data?.message_type === "discovery_request"
  );

  // Extract adaptive resolution info from discovery payloads
  const adaptiveResolutions = nandaResolutions.filter((e) => {
    const payload = (e.data?.payload || {}) as Record<string, unknown>;
    return (payload.resolution_path as string || "").includes("Adaptive");
  });

  if (!report) {
    return (
      <div className="h-full flex flex-col">
        <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3">
          Network Coordination Report
        </h3>

        {/* Show NANDA resolution events even before cascade completes */}
        {nandaResolutions.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-semibold text-blue-400 mb-2 flex items-center gap-1.5">
              <Globe size={12} />
              NANDA Resolution Paths
            </h4>
            {nandaResolutions.map((evt, i) => {
              const d = evt.data || {};
              const payload = d.payload as Record<string, unknown>;
              const reqCtx = payload?.requester_context as Record<string, unknown> | undefined;
              const agents = payload?.agents_discovered as Array<Record<string, unknown>> | string[];
              return (
                <div key={i} className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-2 mb-2 text-[11px]">
                  <div className="text-blue-300 font-mono mb-1">
                    {(payload?.resolution_path as string) || "Index → AgentAddr → AgentFacts"}
                  </div>
                  <div className="text-white/50">
                    Discovered: {(payload?.results_count as number) || 0} agents
                  </div>
                  {reqCtx && (
                    <div className="mt-1 bg-cyan-500/10 border border-cyan-500/20 rounded px-1.5 py-1">
                      <div className="text-cyan-300 text-[10px] font-semibold flex items-center gap-1">
                        <Navigation size={9} />
                        Requester Context
                      </div>
                      <div className="text-white/40 text-[10px] mt-0.5 font-mono">
                        {reqCtx.geo_location && <span>loc: {reqCtx.geo_location as string} | </span>}
                        {reqCtx.security_level && <span>sec: {reqCtx.security_level as string} | </span>}
                        {reqCtx.session_type && <span>type: {reqCtx.session_type as string}</span>}
                      </div>
                    </div>
                  )}
                  {agents && (
                    <div className="text-white/40 mt-1 font-mono text-[10px]">
                      {agents.map((a, j) => {
                        const id = typeof a === "string" ? a : (a.id as string);
                        const method = typeof a === "object" ? (a.resolution as string) : undefined;
                        return (
                          <div key={j} className="flex items-center gap-1">
                            <span>{id}</span>
                            {method && (
                              <span className={`text-[9px] px-1 rounded ${
                                method === "adaptive_resolver" ? "bg-cyan-500/20 text-cyan-300" :
                                method === "two_step_facts" ? "bg-blue-500/20 text-blue-300" :
                                "bg-gray-500/20 text-gray-300"
                              }`}>
                                {method}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="flex-1 flex items-center justify-center text-white/30 text-sm">
          <div className="text-center">
            <FileText size={40} className="mx-auto mb-3 opacity-30" />
            <p>Report will appear when the coordination cascade completes.</p>
          </div>
        </div>
      </div>
    );
  }

  const steps = (report.cascade_steps as unknown[]) || [];
  const discovery = (report.discovery_paths as unknown[]) || [];
  const trust = (report.trust_verification as unknown[]) || [];
  const policy = (report.policy_enforcement as unknown[]) || [];

  return (
    <div className="h-full flex flex-col overflow-y-auto">
      <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3">
        Network Coordination Report
      </h3>

      {/* Status banner */}
      <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 mb-4 flex items-center gap-3">
        <CheckCircle size={20} className="text-green-400" />
        <div>
          <div className="text-sm font-bold text-green-400">Cascade Complete</div>
          <div className="text-[11px] text-white/50">{report.intent as string}</div>
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-white/5 rounded-lg p-2 text-center">
          <DollarSign size={16} className="text-ferrari-gold mx-auto mb-1" />
          <div className="text-lg font-bold text-white">
            ${((report.total_cost as number) || 0).toLocaleString()}
          </div>
          <div className="text-[10px] text-white/40">Total Cost</div>
        </div>
        <div className="bg-white/5 rounded-lg p-2 text-center">
          <Clock size={16} className="text-blue-400 mx-auto mb-1" />
          <div className="text-lg font-bold text-white">
            {(report.total_lead_time_days as number) || "N/A"}
          </div>
          <div className="text-[10px] text-white/40">Lead Time (days)</div>
        </div>
        <div className="bg-white/5 rounded-lg p-2 text-center">
          <MapPin size={16} className="text-emerald-400 mx-auto mb-1" />
          <div className="text-lg font-bold text-white">{steps.length}</div>
          <div className="text-[10px] text-white/40">Cascade Steps</div>
        </div>
      </div>

      {/* NANDA Resolution Paths */}
      {nandaResolutions.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-blue-400 mb-1 flex items-center gap-1.5">
            <Globe size={12} />
            NANDA Resolution Paths
          </h4>
          {nandaResolutions.map((evt, i) => {
            const payload = (evt.data?.payload || {}) as Record<string, unknown>;
            const reqCtx = payload?.requester_context as Record<string, unknown> | undefined;
            return (
              <div key={i} className="bg-blue-500/10 border border-blue-500/20 rounded px-2 py-1.5 text-[11px] text-blue-200 mb-1">
                <div className="font-mono">
                  {(payload?.resolution_path as string) || "Index → AgentAddr → AgentFacts"}
                </div>
                <div className="text-white/40 text-[10px] mt-0.5">
                  {(payload?.results_count as number) || 0} agents resolved
                  {reqCtx?.geo_location && <span className="ml-1 text-cyan-300/60">(from {reqCtx.geo_location as string})</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Adaptive Resolution Details */}
      {adaptiveResolutions.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-cyan-400 mb-1 flex items-center gap-1.5">
            <Radar size={12} />
            Adaptive Resolution (Context-Aware)
          </h4>
          <div className="bg-cyan-500/10 border border-cyan-500/20 rounded px-2 py-1.5 text-[11px] text-cyan-200">
            <div>{adaptiveResolutions.length} resolution(s) used context-aware adaptive routing</div>
            <div className="text-[10px] text-white/40 mt-0.5">
              Endpoints were tailored based on requester location, security level, and QoS requirements
            </div>
          </div>
        </div>
      )}

      {/* Discovery paths */}
      {discovery.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-white/50 mb-1 flex items-center gap-1.5">
            <Fingerprint size={12} />
            Discovery Paths
          </h4>
          {discovery.map((d: any, i: number) => (
            <div key={i} className="bg-white/5 rounded px-2 py-1 text-[11px] text-white/60 mb-1">
              Query: {JSON.stringify(d.query)} → {d.matched_agents?.length || 0} agents
            </div>
          ))}
        </div>
      )}

      {/* Trust verification */}
      {trust.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-white/50 mb-1 flex items-center gap-1.5">
            <Key size={12} />
            Trust Verification (W3C VC)
          </h4>
          {trust.map((t: any, i: number) => (
            <div key={i} className="flex items-center gap-2 text-[11px] text-white/60 mb-1">
              {t.verified ? (
                <CheckCircle size={12} className="text-green-400" />
              ) : (
                <XCircle size={12} className="text-red-400" />
              )}
              {t.agent_id} — score: {t.reputation_score}
              {t.certification_level && (
                <span className="text-white/40 ml-1">({t.certification_level})</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Policy enforcement */}
      {policy.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-white/50 mb-1 flex items-center gap-1.5">
            <Shield size={12} />
            Policy Enforcement
          </h4>
          {policy.map((p: any, i: number) => (
            <div key={i} className="flex items-center gap-2 text-[11px] text-white/60 mb-1">
              {p.compliant ? (
                <CheckCircle size={12} className="text-green-400" />
              ) : (
                <XCircle size={12} className="text-red-400" />
              )}
              Order {p.order_id}: {p.compliant ? "Compliant" : p.issues?.join(", ")}
            </div>
          ))}
        </div>
      )}

      {/* NANDA Architecture Info */}
      <div className="mt-auto pt-3 border-t border-white/5">
        <div className="text-[10px] text-white/20 space-y-0.5">
          <div>Report ID: {report.report_id as string}</div>
          <div>Architecture: NANDA Lean Index + Adaptive Resolver (Context-Aware Tailored Endpoints)</div>
          <div>Signatures: Ed25519 (AgentAddr) + W3C VC v2 (AgentFacts) | Negotiation + Deployment Records</div>
        </div>
      </div>
    </div>
  );
}
