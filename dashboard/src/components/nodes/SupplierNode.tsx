import React from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface SupplierNodeData {
  label: string;
  framework?: string;
  skills?: string;
  reliabilityScore?: number;
  role: 'supplier';
}

const SupplierNode = ({ data, isConnecting, selected }: NodeProps<Node<SupplierNodeData>>) => {
  return (
    <div
      className={`rounded-lg border-2 flex items-center justify-center transition-all ${
        selected ? 'border-slate-100 shadow-lg' : 'border-emerald-500/70'
      }`}
      style={{
        backgroundColor: '#1a2332',
        width: '50px',
        height: '50px',
        position: 'relative',
      }}
      title={`${data.label}${data.framework ? `\nFramework: ${data.framework}` : ''}`}
    >
      {/* Factory/box icon for supplier */}
      <svg
        className="w-8 h-8"
        viewBox="0 0 24 24"
        fill="none"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
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

export default SupplierNode;
