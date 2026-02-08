import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';

export const getLayoutedElements = (
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB'
) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 100, height: 100 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 50,
        y: nodeWithPosition.y - 50,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

export const concentricLayout = (
  nodes: Node[],
  edges: Edge[]
) => {
  // Simple concentric layout: place procurement in center, others around it
  const procurementNode = nodes.find((n) => n.data?.role === 'procurement');
  const otherNodes = nodes.filter((n) => n.data?.role !== 'procurement');

  const layoutedNodes = nodes.map((node) => {
    if (node === procurementNode) {
      return {
        ...node,
        position: { x: 0, y: 0 },
      };
    }

    // Distribute other nodes in a circle
    const nodeIndex = otherNodes.indexOf(node);
    const angleSlice = (2 * Math.PI) / Math.max(otherNodes.length, 1);
    const radius = 200;
    const angle = angleSlice * nodeIndex;

    return {
      ...node,
      position: {
        x: radius * Math.cos(angle),
        y: radius * Math.sin(angle),
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};
