import React from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface ProcurementNodeData {
  label: string;
  framework?: string;
  skills?: string;
  reliabilityScore?: number;
  role: 'procurement';
}

const ProcurementNode = ({ data, isConnecting, selected }: NodeProps<Node<ProcurementNodeData>>) => {
  return (
    <div
      className={`rounded-lg border-2 flex items-center justify-center transition-all ${
        selected ? 'border-slate-100 shadow-lg' : 'border-indigo-500/70'
      }`}
      style={{
        backgroundColor: '#1a2332',
        width: '55px',
        height: '55px',
        position: 'relative',
      }}
      title={`${data.label}${data.framework ? `\nFramework: ${data.framework}` : ''}`}
    >
      {/* Shopping cart icon for procurement */}
      <svg
        className="w-8 h-8"
        viewBox="0 0 24 24"
        fill="none"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 100 4 2 2 0 000-4z" />
      </svg>

      {/* Node label */}
      <div
        className="absolute bottom-0 left-1/2 transform -translate-x-1/2 translate-y-full mt-2 bg-slate-800/90 px-2 py-1 rounded text-[0.6rem] text-slate-200 whitespace-nowrap"
        style={{ textAlign: 'center', fontSize: '10px' }}
      >
        {data.label}
      </div>

      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default ProcurementNode;
