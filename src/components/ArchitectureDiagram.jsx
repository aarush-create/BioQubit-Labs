import React from 'react';

const DEFAULT_PALETTE = { ink: '#111', ink2: '#555', rule: '#ddd', sheet: '#f7f7f7', quantum: '#7c4dff' };
const STAGES = [
  { id: 'input', label: 'NCBI FASTA', sub: 'novel variant sequence', color: 'ink2' },
  { id: 'align', label: 'Classical alignment', sub: 'Smith-Waterman - filtering', color: 'ink2' },
  { id: 'features', label: 'Biophysical features', sub: 'burial - BLOSUM62 - dVolume', color: 'ink2' },
  { id: 'quantum', label: 'IBM QPU (VQC)', sub: 'epistatic coupling - 2-3 qubits', color: 'quantum' },
  { id: 'output', label: 'Triage output', sub: 'ranked mutations - confidence', color: 'ok' },
];

export default function ArchitectureDiagram({ palette }) {
  const p = { ...DEFAULT_PALETTE, ...(palette || {}) };
  const boxW = 170, gap = 28, h = 90, y = 40;
  const totalW = STAGES.length * boxW + (STAGES.length - 1) * gap;
  return (
    <div style={{ padding: '24px 0', overflowX: 'auto' }}>
      <h3 style={{ marginBottom: '1rem' }}>End-to-end architecture</h3>
      <svg viewBox={`0 0 ${totalW} ${h + y + 20}`} width="100%" style={{ maxWidth: totalW, display: 'block' }}>
        {STAGES.map((s, i) => {
          const x = i * (boxW + gap);
          const isQuantum = s.color === 'quantum';
          return (
            <g key={s.id}>
              <rect x={x} y={y} width={boxW} height={h} rx={8} fill={isQuantum ? p.sheet : p.paper} stroke={isQuantum ? p.quantum : p.rule} strokeWidth={isQuantum ? 2 : 1} />
              <text x={x + boxW / 2} y={y + 34} textAnchor="middle" fontSize={13} fontWeight={600} fill={p.ink}>{s.label}</text>
              <text x={x + boxW / 2} y={y + 56} textAnchor="middle" fontSize={11} fill={p.ink2}>{s.sub}</text>
              {i < STAGES.length - 1 && <path d={`M ${x + boxW} ${y + h / 2} L ${x + boxW + gap} ${y + h / 2}`} stroke={p.ink2} strokeWidth={1.5} markerEnd="url(#arrow)" />}
            </g>
          );
        })}
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={p.ink2} />
          </marker>
        </defs>
      </svg>
    </div>
  );
}