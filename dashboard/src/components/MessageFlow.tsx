import { useEffect, useRef, useState, useCallback } from "react";
import type { MessageLogEntry, MessageFilterCategory } from "../types";
import { MESSAGE_FILTER_CATEGORIES } from "../types";

interface MessageFlowProps {
  messages: MessageLogEntry[];
  onSelectMessage?: (msg: MessageLogEntry) => void;
}

/* ── Direction icons ──────────────────────────────────────── */

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <path d="M1 8a.5.5 0 01.5-.5h11.793l-3.147-3.146a.5.5 0 01.708-.708l4 4a.5.5 0 010 .708l-4 4a.5.5 0 01-.708-.708L13.293 8.5H1.5A.5.5 0 011 8z" />
    </svg>
  );
}

function ArrowLeft({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <path d="M15 8a.5.5 0 00-.5-.5H2.707l3.147-3.146a.5.5 0 10-.708-.708l-4 4a.5.5 0 000 .708l4 4a.5.5 0 00.708-.708L2.707 8.5H14.5A.5.5 0 0015 8z" />
    </svg>
  );
}

/* ── Expand/collapse icon ─────────────────────────────────── */

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-3 w-3 text-slate-500 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
      viewBox="0 0 16 16"
      fill="currentColor"
    >
      <path d="M6.22 4.22a.75.75 0 011.06 0l3.25 3.25a.75.75 0 010 1.06l-3.25 3.25a.75.75 0 01-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 010-1.06z" />
    </svg>
  );
}

/* ── Incoming vs outgoing event classification ────────────── */

const OUTGOING_TYPES = new Set([
  "RFQ_SENT",
  "COUNTER_SENT",
  "ACCEPT_SENT",
  "REJECT_SENT",
  "ORDER_PLACED",
  "LOGISTICS_REQUESTED",
  "DISCOVERY_QUERY",
]);

const INCOMING_TYPES = new Set([
  "QUOTE_RECEIVED",
  "REVISED_RECEIVED",
  "SHIP_PLAN_RECEIVED",
  "DISCOVERY_RESULT",
  "AGENTFACTS_FETCHED",
]);

/** Events that have meaningful graph representation */
const GRAPH_RELEVANT_TYPES = new Set([
  "RFQ_SENT", "QUOTE_RECEIVED", "COUNTER_SENT", "REVISED_RECEIVED",
  "ACCEPT_SENT", "REJECT_SENT", "ORDER_PLACED",
  "LOGISTICS_REQUESTED", "SHIP_PLAN_RECEIVED",
  "DISCOVERY_QUERY", "DISCOVERY_RESULT",
]);

/** Scrolling log of A2A messages, colour-coded by event type with filtering. */
export default function MessageFlow({ messages, onSelectMessage }: MessageFlowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [activeFilter, setActiveFilter] = useState<MessageFilterCategory>("all");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const [searchText, setSearchText] = useState("");

  // Detect manual scroll to pause auto-scroll
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 40;
    setAutoScroll(isAtBottom);
  }, []);

  // Auto-scroll to bottom on new messages (if not manually scrolled)
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, autoScroll]);

  // Toggle expanded state
  const toggleExpanded = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // Filter messages
  const filteredMessages = messages.filter((msg) => {
    // Apply category filter
    if (activeFilter !== "all") {
      const category = MESSAGE_FILTER_CATEGORIES[activeFilter];
      if (!category.types.includes(msg.event_type)) return false;
    }
    // Apply search text
    if (searchText) {
      const lower = searchText.toLowerCase();
      return (
        msg.summary.toLowerCase().includes(lower) ||
        msg.event_type.toLowerCase().includes(lower) ||
        (msg.from?.toLowerCase().includes(lower) ?? false) ||
        (msg.to?.toLowerCase().includes(lower) ?? false)
      );
    }
    return true;
  });

  // Count by category for badges
  const categoryCounts: Record<string, number> = {};
  for (const cat of Object.keys(MESSAGE_FILTER_CATEGORIES) as MessageFilterCategory[]) {
    if (cat === "all") {
      categoryCounts[cat] = messages.length;
    } else {
      const types = MESSAGE_FILTER_CATEGORIES[cat].types;
      categoryCounts[cat] = messages.filter((m) => types.includes(m.event_type)).length;
    }
  }

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col">
        {/* Filter bar even when empty */}
        <FilterBar
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
          categoryCounts={categoryCounts}
          searchText={searchText}
          onSearchChange={setSearchText}
        />
        <div className="flex flex-1 items-center justify-center text-slate-500">
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
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
            <p className="text-xs">No messages yet</p>
            <p className="mt-1 text-[0.6rem] text-slate-600">
              Messages appear as the cascade runs
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Filter bar */}
      <FilterBar
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        categoryCounts={categoryCounts}
        searchText={searchText}
        onSearchChange={setSearchText}
      />

      {/* Auto-scroll paused indicator */}
      {!autoScroll && (
        <button
          onClick={() => {
            setAutoScroll(true);
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
          }}
          className="shrink-0 border-b border-slate-700/30 bg-sky-500/10 px-3 py-1 text-center text-[0.6rem] text-sky-400 transition-colors hover:bg-sky-500/20"
        >
          Scroll paused -- click to resume auto-scroll ({filteredMessages.length}{" "}
          messages)
        </button>
      )}

      {/* Message list */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 py-1.5 text-xs"
      >
        {filteredMessages.map((msg) => {
          const isExpanded = expandedIds.has(msg.id);
          const isOutgoing = OUTGOING_TYPES.has(msg.event_type);
          const isIncoming = INCOMING_TYPES.has(msg.event_type);

          return (
            <div key={msg.id} className="mb-1">
              {/* Main message row */}
              <button
                onClick={() => toggleExpanded(msg.id)}
                className="flex w-full items-start gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-slate-800/60"
              >
                {/* Expand chevron */}
                <span className="mt-0.5 shrink-0">
                  <ChevronIcon expanded={isExpanded} />
                </span>

                {/* Colour indicator dot */}
                <span
                  className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: msg.color }}
                />

                {/* Content column */}
                <div className="min-w-0 flex-1">
                  {/* Top row: timestamp + badge */}
                  <div className="flex items-center gap-1.5">
                    <span className="shrink-0 font-mono text-[0.6rem] text-slate-500">
                      {formatTime(msg.timestamp)}
                    </span>
                    <span
                      className="shrink-0 rounded-sm px-1 py-px font-semibold uppercase tracking-wide"
                      style={{
                        color: msg.color,
                        backgroundColor: `${msg.color}18`,
                        fontSize: "0.55rem",
                      }}
                    >
                      {msg.event_type.replace(/_/g, " ")}
                    </span>
                  </div>

                  {/* From/To routing */}
                  {(msg.from || msg.to) && (
                    <div className="mt-0.5 flex items-center gap-1 text-[0.6rem] text-slate-500">
                      {msg.from && (
                        <span className="max-w-[100px] truncate font-medium text-slate-400">
                          {formatAgentName(msg.from)}
                        </span>
                      )}
                      {isOutgoing && msg.to && (
                        <>
                          <ArrowRight className="h-2.5 w-2.5 shrink-0 text-sky-400/70" />
                          <span className="max-w-[100px] truncate font-medium text-slate-400">
                            {formatAgentName(msg.to)}
                          </span>
                        </>
                      )}
                      {isIncoming && msg.from && msg.to && (
                        <>
                          <ArrowLeft className="h-2.5 w-2.5 shrink-0 text-emerald-400/70" />
                          <span className="max-w-[100px] truncate font-medium text-slate-400">
                            {formatAgentName(msg.to)}
                          </span>
                        </>
                      )}
                    </div>
                  )}

                  {/* Summary */}
                  <p className="mt-0.5 leading-snug text-slate-300">
                    {msg.summary}
                  </p>
                </div>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="ml-7 mr-2 mt-0.5 mb-1 rounded-md border border-slate-700/40 bg-slate-800/40 p-2">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[0.6rem]">
                    <DetailRow label="Event" value={msg.event_type} />
                    <DetailRow label="Agent" value={msg.agent_id} />
                    {msg.from && <DetailRow label="From" value={msg.from} />}
                    {msg.to && <DetailRow label="To" value={msg.to} />}
                    <DetailRow label="Time" value={msg.timestamp} />
                  </div>
                  {/* Show in graph button */}
                  {onSelectMessage && GRAPH_RELEVANT_TYPES.has(msg.event_type) && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectMessage(msg);
                      }}
                      className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md bg-indigo-500/15 px-2 py-1 text-[0.6rem] font-medium text-indigo-400 transition-colors hover:bg-indigo-500/25"
                    >
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                      </svg>
                      Show in graph
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

/* ── Filter Bar sub-component ─────────────────────────────── */

interface FilterBarProps {
  activeFilter: MessageFilterCategory;
  onFilterChange: (f: MessageFilterCategory) => void;
  categoryCounts: Record<string, number>;
  searchText: string;
  onSearchChange: (s: string) => void;
}

function FilterBar({
  activeFilter,
  onFilterChange,
  categoryCounts,
  searchText,
  onSearchChange,
}: FilterBarProps) {
  const [showSearch, setShowSearch] = useState(false);

  return (
    <div className="shrink-0 border-b border-slate-700/30 px-2 py-1.5">
      {/* Filter chips row */}
      <div className="flex items-center gap-1 overflow-x-auto">
        {(Object.keys(MESSAGE_FILTER_CATEGORIES) as MessageFilterCategory[]).map(
          (cat) => {
            const { label, color } = MESSAGE_FILTER_CATEGORIES[cat];
            const count = categoryCounts[cat] ?? 0;
            const isActive = activeFilter === cat;

            return (
              <button
                key={cat}
                onClick={() => onFilterChange(cat)}
                className={`flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[0.6rem] font-medium transition-all ${
                  isActive
                    ? "ring-1 ring-inset"
                    : "opacity-60 hover:opacity-100"
                }`}
                style={{
                  color: isActive ? color : "#94a3b8",
                  backgroundColor: isActive ? `${color}15` : "transparent",
                  outlineColor: isActive ? `${color}40` : undefined,
                  outlineWidth: isActive ? "1px" : undefined,
                  outlineStyle: isActive ? "solid" : undefined,
                  outlineOffset: "-1px",
                }}
              >
                {cat !== "all" && (
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                )}
                {label}
                {count > 0 && (
                  <span className="font-mono text-[0.5rem] opacity-70">
                    {count}
                  </span>
                )}
              </button>
            );
          },
        )}

        {/* Search toggle */}
        <button
          onClick={() => setShowSearch((s) => !s)}
          className="ml-auto shrink-0 rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-700/40 hover:text-slate-300"
          title="Search messages"
        >
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </button>
      </div>

      {/* Search input */}
      {showSearch && (
        <div className="mt-1.5">
          <input
            type="text"
            value={searchText}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search messages..."
            className="w-full rounded-md border border-slate-600/50 bg-slate-800/60 px-2 py-1 text-[0.65rem] text-slate-200 placeholder-slate-500 outline-none focus:border-sky-500/50"
            autoFocus
          />
        </div>
      )}
    </div>
  );
}

/* ── Detail row sub-component ─────────────────────────────── */

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1 overflow-hidden">
      <span className="shrink-0 font-medium uppercase tracking-wider text-slate-500">
        {label}:
      </span>
      <span className="truncate font-mono text-slate-300">{value}</span>
    </div>
  );
}

/* ── Helpers ───────────────────────────────────────────────── */

function formatTime(iso: string): string {
  if (!iso) return "--:--:--";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-GB", { hour12: false });
  } catch {
    return iso.slice(11, 19);
  }
}

function formatAgentName(id: string): string {
  // Shorten common prefixes for display
  return id
    .replace(/^agent[-_]/, "")
    .replace(/_/g, " ")
    .replace(/^([a-z])/, (_, c) => c.toUpperCase());
}
