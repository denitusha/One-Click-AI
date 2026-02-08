import { useState } from "react";
import type { TimelinePhase } from "../types";

interface TimelineProps {
  phases: TimelinePhase[];
  cascadeComplete?: boolean;
}

/* ── Pill styles by status ───────────────────────────────── */

const STATUS_STYLES = {
  completed: {
    pill: "border-emerald-500/50 bg-emerald-500/10 text-emerald-300",
    connector: "border-emerald-500/50",
  },
  active: {
    pill: "border-sky-500/50 bg-sky-500/10 text-sky-300",
    connector: "border-slate-600/40",
  },
  pending: {
    pill: "border-slate-600/30 bg-slate-800/30 text-slate-500",
    connector: "border-slate-600/30",
  },
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

/** Compact horizontal timeline matching the coordination cascade screenshot. */
export default function Timeline({ phases, cascadeComplete }: TimelineProps) {
  const [hoveredPhase, setHoveredPhase] = useState<string | null>(null);

  return (
    <div className="flex items-center gap-0 overflow-x-auto px-4 py-2">
      {/* Label */}
      <span className="mr-3 shrink-0 text-[0.6rem] font-bold uppercase tracking-widest text-slate-400">
        Coordination Timeline
      </span>

      {/* Phase pills */}
      {phases.map((phase, i) => {
        const s = STATUS_STYLES[phase.status];
        const isHovered = hoveredPhase === phase.id;
        const description = PHASE_DESCRIPTIONS[phase.id];

        return (
          <div key={phase.id} className="flex items-center">
            {/* Pill badge */}
            <div
              className={`relative shrink-0 rounded-full border px-3 py-1 text-[0.6rem] font-semibold transition-all duration-200 ${s.pill} ${isHovered ? "brightness-125" : ""} ${phase.status === "active" ? "shadow-sm shadow-sky-500/20" : ""}`}
              onMouseEnter={() => setHoveredPhase(phase.id)}
              onMouseLeave={() => setHoveredPhase(null)}
            >
              {phase.label}

              {/* Pulse dot for active phase */}
              {phase.status === "active" && (
                <span className="absolute -right-0.5 -top-0.5 flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-sky-500" />
                </span>
              )}

              {/* Tooltip */}
              {isHovered && description && (
                <div className="absolute -bottom-12 left-1/2 z-20 w-44 -translate-x-1/2 rounded-lg border border-slate-600/50 bg-slate-800 px-3 py-2 shadow-xl">
                  <p className="text-[0.6rem] font-medium text-slate-300">
                    {description}
                  </p>
                  {phase.startedAt && (
                    <p className="mt-0.5 text-[0.5rem] text-slate-500">
                      Started: {formatTimestamp(phase.startedAt)}
                    </p>
                  )}
                  {phase.completedAt && (
                    <p className="text-[0.5rem] text-slate-500">
                      Done: {formatTimestamp(phase.completedAt)}
                    </p>
                  )}
                  <div className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-t border-l border-slate-600/50 bg-slate-800" />
                </div>
              )}
            </div>

            {/* Dashed connector */}
            {i < phases.length - 1 && (
              <div className={`mx-0.5 h-0 w-5 shrink-0 border-t border-dashed ${s.connector} transition-colors duration-500`} />
            )}
          </div>
        );
      })}

      {/* Cascade Complete badge (after last connector) */}
      {phases.length > 0 && (
        <>
          <div className={`mx-0.5 h-0 w-5 shrink-0 border-t border-dashed ${cascadeComplete ? "border-emerald-500/50" : "border-slate-600/30"} transition-colors duration-500`} />
          <div
            className={`shrink-0 rounded-full border px-3 py-1 text-[0.6rem] font-semibold transition-all duration-300 ${
              cascadeComplete
                ? "border-emerald-400 bg-emerald-500/15 text-emerald-300 shadow-sm shadow-emerald-500/20"
                : "border-slate-600/30 bg-slate-800/30 text-slate-500"
            }`}
          >
            Cascade Complete
          </div>
        </>
      )}
    </div>
  );
}

/* ── Helpers ───────────────────────────────────────────────── */

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", { hour12: false });
  } catch {
    return iso;
  }
}
