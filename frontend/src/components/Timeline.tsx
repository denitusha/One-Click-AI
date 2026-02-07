import type { WsEvent } from "../hooks/useWebSocket";

const STEP_COLOURS: Record<string, string> = {
  intent: "bg-red-500",
  discovery_request: "bg-blue-500",
  request_for_quote: "bg-yellow-500",
  quote_response: "bg-yellow-400",
  negotiation_proposal: "bg-orange-500",
  order_placement: "bg-red-600",
  order_confirmation: "bg-green-500",
  shipping_request: "bg-emerald-500",
  route_confirmation: "bg-emerald-400",
  compliance_check: "bg-purple-500",
  compliance_result: "bg-purple-400",
  status_update: "bg-gray-500",
};

interface Props {
  events: WsEvent[];
}

export default function Timeline({ events }: Props) {
  const steps = events
    .filter((e) => e.type === "agent_message")
    .map((e, i) => ({
      index: i + 1,
      sender: (e.data?.sender_id as string) || "?",
      receiver: (e.data?.receiver_id as string) || "?",
      type: (e.data?.message_type as string) || "unknown",
      explanation: (e.data?.explanation as string) || "",
      time: (e.data?.timestamp as string) || "",
    }));

  return (
    <div className="h-full flex flex-col">
      <h3 className="text-sm font-semibold text-white/70 uppercase tracking-wider mb-3">
        Coordination Timeline
      </h3>

      <div className="flex-1 overflow-y-auto">
        {steps.length === 0 && (
          <div className="text-center text-white/30 py-10 text-sm">
            Waiting for cascade to start...
          </div>
        )}

        <div className="relative">
          {/* Vertical line */}
          {steps.length > 0 && (
            <div className="absolute left-4 top-2 bottom-2 w-px bg-white/10" />
          )}

          {steps.map((step) => {
            const dotColor =
              STEP_COLOURS[step.type] || "bg-gray-500";
            return (
              <div key={step.index} className="relative pl-10 pb-4">
                {/* Dot */}
                <div
                  className={`absolute left-[11px] top-1.5 w-[10px] h-[10px] rounded-full ${dotColor} ring-2 ring-ferrari-dark`}
                />
                {/* Content */}
                <div className="bg-white/5 rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-white/40 font-mono w-5">
                      #{step.index}
                    </span>
                    <span className="font-semibold text-white/90">
                      {step.type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="text-[10px] text-white/40 mt-0.5 font-mono">
                    {step.sender} → {step.receiver}
                  </div>
                  {step.explanation && (
                    <p className="text-[11px] text-white/50 mt-1">
                      {step.explanation}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
