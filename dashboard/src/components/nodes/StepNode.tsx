import React from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface StepNodeData {
  label: string;
  role: 'step';
}

const StepNode = ({ data, selected }: NodeProps<Node<StepNodeData>>) => {
  return (
    <div
      className={`rounded border-2 flex items-center justify-center transition-all text-[0.6rem] font-medium text-center ${
        selected ? 'border-slate-100' : 'border-slate-600'
      }`}
      style={{
        backgroundColor: '#334155',
        width: '55px',
        height: '35px',
        color: '#e2e8f0',
        padding: '4px',
      }}
      title={data.label}
    >
      {data.label}
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default StepNode;
