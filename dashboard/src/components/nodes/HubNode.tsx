import React from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface HubNodeData {
  label: string;
  role: 'hub';
  isOrigin?: boolean;
  isDest?: boolean;
}

const HubNode = ({ data, selected }: NodeProps<Node<HubNodeData>>) => {
  const isOrigin = data.isOrigin;
  const isDest = data.isDest;

  return (
    <div
      className={`rounded border-2 flex items-center justify-center transition-all font-medium text-xs ${
        isOrigin ? 'bg-orange-400 border-orange-600' : isDest ? 'bg-emerald-400 border-emerald-600' : 'bg-slate-500 border-slate-600'
      }`}
      style={{
        width: '40px',
        height: '30px',
        color: '#fff',
      }}
      title={data.label}
    >
      {data.label.split(' ')[0]}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
};

export default HubNode;
