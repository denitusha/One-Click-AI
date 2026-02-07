import { useState } from "react";
import type { TimelinePhase } from "../types";

interface TimelineProps {
  phases: TimelinePhase[];
}

/* ── Phase icons ──────────────────────────────────────────── */

const PHASE_ICONS: Record<string, React.ReactNode> = {
  intent: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  bom: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
    </svg>
  ),
  discovery: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  ),
  verification: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  negotiation: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
    </svg>
  ),
  logistics: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
    </svg>
  ),
  plan: (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
    </svg>
  ),
};

const PHASE_DESCRIPTIONS: Record<string, string> = {
  intent: "User procurement intent received",
  bom: "Bill of materials decomposition",
  discovery: "Agent discovery via NANDA Index",
  verification: "Zero-trust agent authentication",
  negotiation: "RFQ, quote, counter-offer rounds",
  logistics: "Shipping route planning",
  plan: "Final coordination plan assembled",
};

const STATUS_STYLES = {
  completed: {
    bg: "bg-emerald-500/15",
    border: "border-emerald-500/50",
    iconBg: "bg-emerald-500",
    text: "text-emerald-300",
    descText: "text-emerald-400/60",
    line: "bg-emerald-500",
    glow: "shadow-emerald-500/20",
  },
  active: {
    bg: "bg-sky-500/15",
    border: "border-sky-500/50",
    iconBg: "bg-sky-500",
    text: "text-sky-300",
    descText: "text-sky-400/60",
    line: "bg-sky-500",
    glow: "shadow-sky-500/30",
  },
  pending: {
    bg: "bg-slate-800/30",
    border: "border-slate-600/30",
    iconBg: "bg-slate-600",
    text: "text-slate-500",
    descText: "text-slate-600",
    line: "bg-slate-700",
    glow: "",
  },
};

/** Horizontal timeline showing coordination cascade phases with duration tracking. */
export default function Timeline({ phases }: TimelineProps) {
  const [hoveredPhase, setHoveredPhase] = useState<string | null>(null);

  // Calculate overall progress
  const completedCount = phases.filter((p) => p.status === "completed").length;
  const totalCount = phases.length;
  const progressPct = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const hasStarted = phases.some((p) => p.status !== "pending");

  return (
    <div className="flex flex-col">
      {/* Progress bar */}
      {hasStarted && (
        <div className="flex items-center gap-2 px-4 pt-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-700/50">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-sky-500 transition-all duration-700 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-[0.6rem] font-medium tabular-nums text-slate-500">
            {completedCount}/{totalCount}
          </span>
        </div>
      )}

      {/* Phase blocks */}
      <div className="flex items-center gap-0 overflow-x-auto px-4 py-2.5">
        {phases.map((phase, i) => {
          const s = STATUS_STYLES[phase.status];
          const isHovered = hoveredPhase === phase.id;
          const duration = computeDuration(phase);
          const icon = PHASE_ICONS[phase.id];
          const description = PHASE_DESCRIPTIONS[phase.id];

          return (
            <div key={phase.id} className="flex items-center">
              {/* Phase block */}
              <div
                className={`relative flex flex-col items-center gap-1 rounded-lg border px-3 py-2 transition-all duration-300 ${s.bg} ${s.border} ${s.glow ? `shadow-md ${s.glow}` : ""} ${isHovered ? "scale-105" : ""}`}
                onMouseEnter={() => setHoveredPhase(phase.id)}
                onMouseLeave={() => setHoveredPhase(null)}
              >
                {/* Icon circle */}
                <div className="relative flex items-center justify-center">
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full ${s.iconBg} text-white`}
                  >
                    {phase.status === "completed" ? (
                      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    ) : (
                      icon
                    )}
                  </span>
                  {phase.status === "active" && (
                    <span
                      className={`pulse-ring absolute h-7 w-7 rounded-full ${s.iconBg}`}
                    />
                  )}
                </div>

                {/* Label */}
                <span className={`text-[0.65rem] font-semibold ${s.text}`}>
                  {phase.label}
                </span>

                {/* Duration badge */}
                {duration && (
                  <span className={`text-[0.5rem] font-mono tabular-nums ${s.descText}`}>
                    {duration}
                  </span>
                )}

                {/* Tooltip */}
                {isHovered && (
                  <div className="absolute -bottom-16 left-1/2 z-20 w-44 -translate-x-1/2 rounded-lg border border-slate-600/50 bg-slate-800 px-3 py-2 shadow-xl">
                    <p className="text-[0.6rem] font-medium text-slate-300">
                      {description}
                    </p>
                    {phase.startedAt && (
                      <p className="mt-1 text-[0.5rem] text-slate-500">
                        Started: {formatTimestamp(phase.startedAt)}
                      </p>
                    )}
                    {phase.completedAt && (
                      <p className="text-[0.5rem] text-slate-500">
                        Completed: {formatTimestamp(phase.completedAt)}
                      </p>
                    )}
                    {/* Tooltip arrow */}
                    <div className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-t border-l border-slate-600/50 bg-slate-800" />
                  </div>
                )}
              </div>

              {/* Connector */}
              {i < phases.length - 1 && (
                <div className="relative flex items-center">
                  <div className={`h-0.5 w-6 shrink-0 transition-colors duration-500 ${s.line}`} />
                  {/* Arrow head on connector */}
                  {phase.status === "completed" && (
                    <div
                      className="absolute right-0 h-0 w-0"
                      style={{
                        borderTop: "3px solid transparent",
                        borderBottom: "3px solid transparent",
                        borderLeft: `4px solid ${phase.status === "completed" ? "#10b981" : "#475569"}`,
                      }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Helpers ───────────────────────────────────────────────── */

function computeDuration(phase: TimelinePhase): string | null {
  if (!phase.startedAt) return null;
  const start = new Date(phase.startedAt).getTime();

  if (phase.completedAt) {
    const end = new Date(phase.completedAt).getTime();
    return formatMs(end - start);
  }

  if (phase.status === "active") {
    // Show elapsed time for active phase
    const elapsed = Date.now() - start;
    return `${formatMs(elapsed)}...`;
  }

  return null;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = Math.floor(seconds % 60);
  return `${minutes}m ${remainSeconds}s`;
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", { hour12: false });
  } catch {
    return iso;
  }
}
