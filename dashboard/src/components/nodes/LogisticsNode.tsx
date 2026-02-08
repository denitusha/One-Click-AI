import React from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

export interface LogisticsNodeData {
  label: string;
  framework?: string;
  skills?: string;
  reliabilityScore?: number;
  role: 'logistics';
}

const LogisticsNode = ({ data, isConnecting, selected }: NodeProps<Node<LogisticsNodeData>>) => {
  return (
    <div
      className={`rounded-lg border-2 flex items-center justify-center transition-all ${
        selected ? 'border-slate-100 shadow-lg' : 'border-orange-500/70'
      }`}
      style={{
        backgroundColor: '#1a2332',
        width: '50px',
        height: '50px',
        position: 'relative',
      }}
      title={`${data.label}${data.framework ? `\nFramework: ${data.framework}` : ''}`}
    >
      {/* Truck icon for logistics */}
      <svg
        className="w-8 h-8"
        viewBox="0 0 24 24"
        fill="none"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
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

export default LogisticsNode;
