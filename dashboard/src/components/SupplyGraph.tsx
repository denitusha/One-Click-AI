import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
} from '@xyflow/react';
import {
  ProcurementNode,
  SupplierNode,
  LogisticsNode,
  IndexNode,
  HubNode,
  StepNode,
} from './nodes';
import { getLayoutedElements, concentricLayout } from '../utils/layout';
import type {
  GraphNode,
  GraphEdge,
  AggregatedEdge,
  GraphSelection,
  ShipPlanDetail,
  NegotiationRound,
  AnalyticsMode,
} from '../types';

const nodeTypes = {
  procurement: ProcurementNode,
  supplier: SupplierNode,
  logistics: LogisticsNode,
  index: IndexNode,
  hub: HubNode,
  step: StepNode,
};

const EDGE_COLORS: Record<string, string> = {
  discovery: '#a78bfa',
  rfq: '#38bdf8',
  quote: '#34d399',
  counter: '#fb923c',
  accept: '#4ade80',
  order: '#22d3ee',
  logistics: '#f97316',
  contract: '#e2e8f0',
  route: '#f97316',
  'route-express': '#ef4444',
};

interface SupplyGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  overviewEdges: AggregatedEdge[];
  detailEdges: GraphEdge[];
  selection: GraphSelection;
  shipPlans: ShipPlanDetail[];
  negotiations: NegotiationRound[];
  analyticsMode: AnalyticsMode;
  onSelectAgent: (agentId: string) => void;
  onBack: () => void;
}

function buildReactFlowNodes(
  nodes: GraphNode[],
  mode: GraphSelection['mode'],
  analyticsMode: AnalyticsMode,
  overviewEdges: AggregatedEdge[],
  agentId?: string,
  shipPlans: ShipPlanDetail[] = [],
  selectedIndex?: number
): Node[] {
  if (mode === 'overview' || mode === 'agent-detail') {
    return nodes.map((node) => {
      let nodeType: keyof typeof nodeTypes = 'supplier';
      if (node.role === 'procurement') nodeType = 'procurement';
      else if (node.role === 'logistics') nodeType = 'logistics';
      else if (node.role === 'index') nodeType = 'index';

      let analyticsClass = '';
      if (analyticsMode === 'risk') {
        const score = node.reliabilityScore;
        if (score === undefined) analyticsClass = 'risk-unknown';
        else if (score >= 0.7) analyticsClass = 'risk-high';
        else if (score >= 0.4) analyticsClass = 'risk-med';
        else analyticsClass = 'risk-low';
      }

      if (analyticsMode === 'bottleneck') {
        const degree = overviewEdges.reduce((count, ae) => {
          if (ae.source === node.id || ae.target === node.id) return count + ae.totalMessages;
          return count;
        }, 0);
        if (degree >= 10) analyticsClass = 'bottleneck-critical';
        else if (degree >= 5) analyticsClass = 'bottleneck-high';
        else analyticsClass = 'bottleneck-normal';
      }

      return {
        id: node.id,
        type: nodeType,
        data: {
          label: analyticsMode === 'risk' && node.reliabilityScore !== undefined
            ? `${node.label}\n${(node.reliabilityScore * 100).toFixed(0)}% / ESG: ${node.esgRating ?? '?'}`
            : node.label,
          role: node.role,
          framework: node.framework,
          skills: node.skills?.join(', '),
          reliabilityScore: node.reliabilityScore,
        },
        position: { x: 0, y: 0 },
        className: analyticsClass,
        selected: mode === 'agent-detail' && node.id === agentId,
      };
    });
  }

  if (mode === 'logistics-detail') {
    // Render hub nodes for routing
    const plans = selectedIndex !== undefined ? [shipPlans[selectedIndex]] : shipPlans;
    const hubIds = new Set<string>();
    const hubNodesList: Node[] = [];

    for (const sp of plans) {
      const route = sp.route.length > 0 ? sp.route : [sp.pickup, sp.delivery];
      let yOffset = 0;

      for (let i = 0; i < route.length; i++) {
        const city = route[i];
        const nodeId = `hub-${city.replace(/\s+/g, '_').toLowerCase()}`;

        if (!hubIds.has(nodeId)) {
          hubIds.add(nodeId);
          const isOrigin = i === 0;
          const isDest = i === route.length - 1;

          hubNodesList.push({
            id: nodeId,
            type: 'hub',
            data: {
              label: city,
              role: 'hub',
              isOrigin,
              isDest,
            },
            position: { x: i * 150, y: yOffset },
          });
        }
      }
      yOffset += 100;
    }

    return hubNodesList;
  }

  if (mode === 'order-detail') {
    // Render negotiation step nodes
    // TODO: Implement order detail view
    return [];
  }

  return [];
}

function buildReactFlowEdges(
  edges: GraphEdge[],
  mode: GraphSelection['mode'],
  overviewEdges: AggregatedEdge[],
  analyticsMode: AnalyticsMode,
  shipPlans: ShipPlanDetail[] = [],
  selectedIndex?: number
): Edge[] {
  if (mode === 'overview') {
    return overviewEdges.map((ae) => {
      const counts = ae.counts as Record<string, number>;
      const dominant = Object.entries(counts)
        .filter(([_, count]) => count > 0)
        .sort((a, b) => b[1] - a[1])[0]?.[0] as string;

      let edgeClass = '';
      if (analyticsMode === 'cost') {
        if (ae.totalMessages >= 10) edgeClass = 'cost-high';
        else if (ae.totalMessages >= 4) edgeClass = 'cost-med';
        else edgeClass = 'cost-low';
      }

      return {
        id: ae.id,
        source: ae.source,
        target: ae.target,
        label: Object.entries(counts)
          .filter(([_, count]) => count > 0)
          .map(([type, count]) => `${count} ${type}`)
          .join(', '),
        animated: false,
        className: edgeClass,
        style: {
          stroke: EDGE_COLORS[dominant] || '#a78bfa',
          strokeWidth: ae.totalMessages > 15 ? 6 : ae.totalMessages > 5 ? 4 : 2,
        },
      };
    });
  }

  if (mode === 'agent-detail') {
    return edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      animated: edge.animated || false,
      style: {
        stroke: EDGE_COLORS[edge.edgeType] || '#94a3b8',
        strokeDasharray: ['discovery', 'counter'].includes(edge.edgeType) ? '5,5' : 'none',
        strokeWidth: 2,
      },
    }));
  }

  if (mode === 'logistics-detail') {
    // Render route edges
    const rfEdges: Edge[] = [];
    const plans = selectedIndex !== undefined ? [shipPlans[selectedIndex]] : shipPlans;

    for (let pi = 0; pi < plans.length; pi++) {
      const sp = plans[pi];
      if (!sp) continue;

      const route = sp.route.length > 0 ? sp.route : [sp.pickup, sp.delivery];
      const isExpress = (sp.cost ?? 0) > 500;

      for (let i = 0; i < route.length - 1; i++) {
        const city = route[i];
        const nextCity = route[i + 1];
        const sourceId = `hub-${city.replace(/\s+/g, '_').toLowerCase()}`;
        const targetId = `hub-${nextCity.replace(/\s+/g, '_').toLowerCase()}`;

        rfEdges.push({
          id: `route-${pi}-${i}`,
          source: sourceId,
          target: targetId,
          label: sp.cost != null ? `€${Math.round(sp.cost / Math.max(route.length - 1, 1))}` : '',
          animated: false,
          style: {
            stroke: isExpress ? '#ef4444' : '#f97316',
            strokeWidth: isExpress ? 3.5 : 3,
            strokeDasharray: isExpress ? 'none' : 'none',
          },
        });
      }
    }
    return rfEdges;
  }

  return [];
}

export default function SupplyGraph({
  nodes: graphNodes,
  edges: graphEdges,
  overviewEdges,
  detailEdges,
  selection,
  shipPlans,
  negotiations,
  analyticsMode,
  onSelectAgent,
  onBack,
}: SupplyGraphProps) {
  const { fitView } = useReactFlow();
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const initialNodes = useMemo(
    () => buildReactFlowNodes(
      graphNodes,
      selection.mode,
      analyticsMode,
      overviewEdges,
      selection.agentId,
      shipPlans,
      selection.shipPlanIndex
    ),
    [graphNodes, selection.mode, analyticsMode, overviewEdges, selection.agentId, shipPlans, selection.shipPlanIndex]
  );

  const initialEdges = useMemo(
    () => buildReactFlowEdges(
      selection.mode === 'agent-detail' ? detailEdges : graphEdges,
      selection.mode,
      overviewEdges,
      analyticsMode,
      shipPlans,
      selection.shipPlanIndex
    ),
    [selection.mode, graphEdges, detailEdges, overviewEdges, analyticsMode, shipPlans, selection.shipPlanIndex]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when initial nodes change
  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  // Update edges when initial edges change
  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  // Apply layout when mode changes
  useEffect(() => {
    if (nodes.length === 0) return;

    let layoutedNodes: Node[];

    if (selection.mode === 'overview') {
      const result = concentricLayout(nodes, edges);
      layoutedNodes = result.nodes;
    } else if (selection.mode === 'agent-detail') {
      const result = getLayoutedElements(nodes, edges, 'TB');
      layoutedNodes = result.nodes;
    } else if (selection.mode === 'logistics-detail' || selection.mode === 'order-detail') {
      const result = getLayoutedElements(nodes, edges, 'LR');
      layoutedNodes = result.nodes;
    } else {
      layoutedNodes = nodes;
    }

    setNodes(layoutedNodes);

    // Fit view after layout
    setTimeout(() => {
      fitView({ padding: 0.2, duration: 300 });
    }, 50);
  }, [selection.mode, nodes.length, setNodes, edges, fitView]);

  const onNodeClick = useCallback(
    (_: any, node: Node) => {
      if (selection.mode === 'overview') {
        onSelectAgent(node.id);
      }
    },
    [selection.mode, onSelectAgent]
  );

  const onNodeMouseEnter = useCallback(
    (_: any, node: Node) => {
      if (selection.mode === 'overview') {
        setHoveredNode(node.id);
        setNodes((nds) =>
          nds.map((n) => ({
            ...n,
            className: n.id === node.id ? 'hovered' : n.id === selection.agentId ? 'highlighted' : n.className,
          }))
        );
      }
    },
    [selection.mode, selection.agentId, setNodes]
  );

  const onNodeMouseLeave = useCallback(() => {
    if (selection.mode === 'overview') {
      setHoveredNode(null);
      setNodes((nds) =>
        nds.map((n) => ({
          ...n,
          className: n.id === selection.agentId ? 'highlighted' : '',
        }))
      );
    }
  }, [selection.mode, selection.agentId, setNodes]);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        nodeTypes={nodeTypes}
        fitView
        colorMode="dark"
      >
        <Background color="#334155" gap={16} size={0.5} />
        <Controls position="bottom-right" />
        {selection.mode === 'overview' && graphNodes.length > 5 && <MiniMap position="bottom-left" />}
      </ReactFlow>

      {/* Back button (detail mode only) */}
      {selection.mode !== 'overview' && (
        <button
          onClick={onBack}
          className="absolute top-3 left-3 z-10 flex items-center gap-1.5 rounded-lg bg-slate-800/90 px-3 py-1.5 text-xs font-medium text-slate-300 shadow-lg backdrop-blur-sm transition-colors hover:bg-slate-700 hover:text-white"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to Overview
        </button>
      )}

      {/* Detail title badge */}
      {selection.mode !== 'overview' && (
        <div className="absolute top-3 left-1/2 z-10 -translate-x-1/2 rounded-lg bg-slate-800/90 px-4 py-1.5 text-xs font-medium text-slate-200 shadow-lg backdrop-blur-sm">
          {selection.mode === 'agent-detail' && `Agent Detail — ${detailEdges.length} interactions`}
          {selection.mode === 'order-detail' && `Order: ${selection.partName}`}
          {selection.mode === 'logistics-detail' && (
            selection.shipPlanIndex !== undefined
              ? `Route: ${shipPlans[selection.shipPlanIndex]?.pickup} → ${shipPlans[selection.shipPlanIndex]?.delivery}`
              : `Logistics Network — ${shipPlans.length} routes`
          )}
        </div>
      )}

      {/* Analytics overlay badge */}
      {analyticsMode !== 'none' && selection.mode === 'overview' && (
        <div className="absolute top-3 left-1/2 z-10 -translate-x-1/2 rounded-lg bg-slate-800/90 px-4 py-1.5 text-xs font-medium text-amber-300 shadow-lg backdrop-blur-sm">
          {analyticsMode === 'risk' && 'Risk Heatmap — node color = reliability score'}
          {analyticsMode === 'cost' && 'Cost Flow — edge thickness = message volume'}
          {analyticsMode === 'bottleneck' && 'Bottleneck Detection — node size = connection degree'}
        </div>
      )}

      {/* Overview hint */}
      {selection.mode === 'overview' && graphNodes.length > 0 && analyticsMode === 'none' && (
        <div className="absolute top-3 right-3 z-10 rounded-lg bg-slate-800/80 px-3 py-1.5 text-[0.6rem] text-slate-400 backdrop-blur-sm">
          Click a node to drill down
        </div>
      )}

      {/* Logistics detail legend */}
      {selection.mode === 'logistics-detail' && (
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg bg-slate-900/80 px-3 py-2 text-xs backdrop-blur-sm">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-orange-400" />
            <span className="text-slate-300">Origin</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-slate-500" />
            <span className="text-slate-300">Transit Hub</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-emerald-400" />
            <span className="text-slate-300">Destination</span>
          </span>
        </div>
      )}

      {/* Empty state */}
      {graphNodes.length === 0 && selection.mode === 'overview' && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <svg className="mx-auto mb-3 h-12 w-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            <p className="text-sm">Waiting for agents to register...</p>
            <p className="mt-1 text-xs text-slate-600">Nodes appear as agents join the network</p>
          </div>
        </div>
      )}

      {/* Empty logistics state */}
      {selection.mode === 'logistics-detail' && shipPlans.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <svg className="mx-auto mb-3 h-12 w-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
            </svg>
            <p className="text-sm">No shipping plans yet</p>
            <p className="mt-1 text-xs text-slate-600">Routes appear when logistics plans are received</p>
          </div>
        </div>
      )}
    </div>
  );
}
