interface StatusBarProps {
  connected: boolean;
  eventCount: number;
  nodeCount: number;
  edgeCount: number;
}

/** Top-right status indicator showing connection state and counters. */
export default function StatusBar({
  connected,
  eventCount,
  nodeCount,
  edgeCount,
}: StatusBarProps) {
  return (
    <div className="flex items-center gap-4 text-xs">
      {/* Connection status */}
      <div
        className="flex items-center gap-1.5 rounded-full px-2.5 py-1"
        title={connected ? "Connected to Event Bus" : "Disconnected from Event Bus"}
      >
        <span className="relative flex h-2 w-2">
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${connected ? "bg-emerald-400 animate-ping opacity-75" : "bg-red-400"}`}
          />
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`}
          />
        </span>
        <span className={connected ? "text-emerald-400" : "text-red-400"}>
          {connected ? "Live" : "Disconnected"}
        </span>
      </div>

      {/* Counters */}
      <div className="flex items-center gap-3 text-slate-400">
        <span title="Events received">
          <span className="font-mono font-bold text-slate-300">{eventCount}</span> events
        </span>
        <span title="Agent nodes">
          <span className="font-mono font-bold text-slate-300">{nodeCount}</span> nodes
        </span>
        <span title="Message edges">
          <span className="font-mono font-bold text-slate-300">{edgeCount}</span> edges
        </span>
      </div>
    </div>
  );
}
