import { useMemo, useState } from "react";
import { ChevronDown, Package, DollarSign, Clock, Truck, CheckCircle, AlertCircle, FileText } from "lucide-react";
import type { WsEvent } from "../hooks/useWebSocket";

interface Order {
  orderId: string;
  supplierId: string;
  supplierName: string;
  agreedPrice: number;
  leadTimeDays: number;
  componentsCount: number;
  status: "placed" | "manufacturing" | "shipped" | "complete";
  events: Array<{
    timestamp: string;
    messageType: string;
    sender: string;
    receiver: string;
    payload: Record<string, unknown>;
  }>;
}

function getSupplierName(supplierId: string): string {
  return supplierId
    .replace("nanda:", "")
    .replace("-agent", "")
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function synthesizeOrders(events: WsEvent[]): Order[] {
  const orders: Record<string, Order> = {};
  const agentMessages = events.filter((e) => e.type === "agent_message");

  // First pass: find all order placements
  for (const evt of agentMessages) {
    const data = evt.data || {};
    const msgType = data.message_type as string;

    if (msgType === "order_placement") {
      const payload = data.payload as Record<string, unknown>;
      const orderId = (payload.order_id as string) || "";
      const supplierId = (payload.supplier_id as string) || "";

      if (orderId && !orders[orderId]) {
        orders[orderId] = {
          orderId,
          supplierId,
          supplierName: getSupplierName(supplierId),
          agreedPrice: (payload.agreed_price as number) || 0,
          leadTimeDays: (payload.agreed_lead_time_days as number) || 0,
          componentsCount: ((payload.components as unknown[]) || []).length || 0,
          status: "placed",
          events: [],
        };
      }
    }
  }

  // Second pass: collect all events for each order and determine status
  for (const evt of agentMessages) {
    const data = evt.data || {};
    const msgType = data.message_type as string;
    const payload = data.payload as Record<string, unknown>;
    const orderId = (payload.order_id as string) || "";

    if (orderId && orders[orderId]) {
      const sender = ((data.sender_id as string) || "").replace("nanda:", "").replace("-agent", "");
      const receiver = ((data.receiver_id as string) || "").replace("nanda:", "").replace("-agent", "");

      orders[orderId].events.push({
        timestamp: (data.timestamp as string) || "",
        messageType: msgType,
        sender,
        receiver,
        payload,
      });

      // Update status based on latest event
      if (msgType === "order_confirmation") {
        orders[orderId].status = "complete";
      } else if (msgType === "route_confirmation") {
        orders[orderId].status = "shipped";
      } else if (msgType === "compliance_result" || msgType === "shipping_request") {
        orders[orderId].status = "manufacturing";
      }
    }
  }

  return Object.values(orders).sort(
    (a, b) =>
      new Date(b.events[b.events.length - 1]?.timestamp || 0).getTime() -
      new Date(a.events[a.events.length - 1]?.timestamp || 0).getTime()
  );
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: typeof CheckCircle }> = {
  placed: { label: "Placed", color: "text-accent-gold", bg: "bg-accent-gold/10", icon: FileText },
  manufacturing: { label: "Manufacturing", color: "text-accent-orange", bg: "bg-accent-orange/10", icon: Package },
  shipped: { label: "Shipped", color: "text-accent-cyan", bg: "bg-accent-cyan/10", icon: Truck },
  complete: { label: "Complete", color: "text-accent-green", bg: "bg-accent-green/10", icon: CheckCircle },
};

const MESSAGE_TYPE_COLORS: Record<string, string> = {
  request_for_quote: "bg-accent-gold",
  quote_response: "bg-accent-gold",
  negotiation_proposal: "bg-accent-orange",
  order_placement: "bg-accent-red",
  order_confirmation: "bg-accent-green",
  shipping_request: "bg-accent-orange",
  route_confirmation: "bg-accent-green",
  compliance_check: "bg-accent-purple",
  compliance_result: "bg-accent-purple",
};

function OrderCard({
  order,
  isSelected,
  onSelect,
}: {
  order: Order;
  isSelected: boolean;
  onSelect: (orderId: string) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const statusCfg = STATUS_CONFIG[order.status];
  const StatusIcon = statusCfg.icon;

  const handleClick = () => {
    const newExpanded = !isExpanded;
    setIsExpanded(newExpanded);
    if (newExpanded) {
      onSelect(order.orderId);
    } else {
      onSelect("");
    }
  };

  return (
    <div
      className={`rounded-lg border transition-all ${
        isSelected
          ? "bg-panel-dark/60 border-accent-green/30 ring-1 ring-accent-green/20"
          : "bg-panel-dark/40 border-panel-border/50 hover:border-panel-border hover:bg-panel-dark/50"
      }`}
    >
      {/* Order header - always visible */}
      <button
        onClick={handleClick}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left cursor-pointer"
      >
        {/* Left: Order ID + Supplier */}
        <div className="flex-1 min-w-0">
          <div className="font-mono text-[10px] font-semibold text-white/80">{order.orderId}</div>
          <div className="text-[9px] text-white/50 font-mono mt-0.5">{order.supplierName}</div>
        </div>

        {/* Middle: Price + Lead Time */}
        <div className="flex items-center gap-3 text-[9px] text-white/40 font-mono shrink-0">
          <div className="flex items-center gap-1">
            <DollarSign size={11} />
            <span>{(order.agreedPrice / 1000).toFixed(1)}M</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock size={11} />
            <span>{order.leadTimeDays}d</span>
          </div>
        </div>

        {/* Right: Status badge + Chevron */}
        <div className="flex items-center gap-2 shrink-0">
          <div className={`flex items-center gap-1 px-2 py-1 rounded text-[8px] font-mono font-semibold ${statusCfg.bg} ${statusCfg.color}`}>
            <StatusIcon size={9} />
            {statusCfg.label}
          </div>
          <ChevronDown
            size={12}
            className={`text-white/30 transition-transform ${isExpanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {/* Expanded content - order flow timeline */}
      {isExpanded && (
        <div className="px-3 pb-3 border-t border-panel-border/30">
          <div className="mt-2 space-y-0">
            {order.events.map((evt, i) => {
              const dotColor = MESSAGE_TYPE_COLORS[evt.messageType] || "bg-white/20";
              const isLast = i === order.events.length - 1;
              const timeStr = new Date(evt.timestamp).toLocaleTimeString("en-US", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              });

              let stepLabel = evt.messageType.replace(/_/g, " ").toUpperCase();
              let stepValue = "";

              // Extract key info from payload
              if (evt.messageType === "quote_response") {
                const payload = evt.payload as Record<string, unknown>;
                stepValue = `$${((payload.total_price as number) / 1000).toFixed(1)}M, ${payload.lead_time_days}d`;
              } else if (evt.messageType === "negotiation_proposal") {
                const payload = evt.payload as Record<string, unknown>;
                if (payload.proposed_price) stepValue = `$${((payload.proposed_price as number) / 1000).toFixed(1)}M`;
                if (payload.proposed_lead_time_days) stepValue += `, ${payload.proposed_lead_time_days}d`;
              } else if (evt.messageType === "route_confirmation") {
                const payload = evt.payload as Record<string, unknown>;
                stepValue = `${payload.transport_mode}, ${payload.estimated_days}d, $${((payload.cost as number) / 1000).toFixed(1)}M`;
              } else if (evt.messageType === "compliance_result") {
                const payload = evt.payload as Record<string, unknown>;
                stepValue = payload.compliant === true ? "Compliant" : "Issues found";
              }

              return (
                <div key={i} className="relative flex gap-2">
                  {/* Timeline line */}
                  {!isLast && (
                    <div className="absolute left-[5px] top-5 w-0.5 h-8 bg-panel-border/40" />
                  )}

                  {/* Timeline dot */}
                  <div className={`w-2.5 h-2.5 rounded-full shrink-0 mt-1 ${dotColor}`} />

                  {/* Step content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-[9px] font-mono font-semibold text-white/70">{stepLabel}</span>
                      <span className="text-[8px] text-white/25 font-mono">{timeStr}</span>
                    </div>
                    {stepValue && (
                      <div className="text-[8px] text-white/40 font-mono mt-0.5">{stepValue}</div>
                    )}
                    <div className="text-[8px] text-white/35 font-mono mt-0.5">
                      {evt.sender} → {evt.receiver}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

interface Props {
  events: WsEvent[];
  selectedOrderId: string | null;
  onOrderSelect: (orderId: string | null) => void;
}

export default function OrdersView({ events, selectedOrderId, onOrderSelect }: Props) {
  const orders = useMemo(() => synthesizeOrders(events), [events]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b border-panel-border">
        <div className={`w-1.5 h-1.5 rounded-full ${orders.length > 0 ? "bg-accent-green" : "bg-white/20"}`} />
        <h3 className="text-[10px] font-semibold text-white/40 uppercase tracking-[0.15em] font-mono">
          Orders
        </h3>
        <span className="ml-auto text-[10px] text-white/20 font-mono">
          {orders.length}
        </span>
      </div>

      {/* Orders list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {orders.length === 0 ? (
          <div className="text-white/20 text-xs font-mono pt-8 text-center">
            No orders yet. Run cascade to place orders.
          </div>
        ) : (
          orders.map((order) => (
            <OrderCard
              key={order.orderId}
              order={order}
              isSelected={selectedOrderId === order.orderId}
              onSelect={onOrderSelect}
            />
          ))
        )}
      </div>
    </div>
  );
}
