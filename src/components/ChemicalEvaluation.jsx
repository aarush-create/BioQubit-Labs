import React, { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer, ScatterChart, Scatter, ZAxis, Cell } from 'recharts';

const DEFAULT_PALETTE = { ink: '#111', ink2: '#555', rule: '#ddd', paper: '#fff', sheet: '#f7f7f7', ok: '#2e7d32', alarm: '#c62828', assay: '#1565c0', flag: '#ef6c00' };

export default function ChemicalEvaluation({ palette, data }) {
  const p = { ...DEFAULT_PALETTE, ...(palette || {}) };
  const { feature_fitness_correlations: correlations = [], hydrophobicity_vs_burial: hydropathy = [], validation_checks: checks = [] } = data || {};
  const sortedCorrelations = useMemo(() => [...correlations].sort((a, b) => Math.abs(b.spearman) - Math.abs(a.spearman)), [correlations]);

  return (
    <div style={{ padding: '24px 0' }}>
      <h2 style={{ fontSize: 'var(--t-xl)', marginBottom: '0.5rem', color: p.ink }}>Chemical evaluation</h2>
      <p className="lede" style={{ color: p.ink2, maxWidth: '70ch', marginBottom: '2rem' }}>These checks ask a different question from the AUC tables: do the features the quantum circuit actually uses behave the way known physical chemistry says they should?</p>

      <section className="section" style={{ marginBottom: '3rem' }}>
        <h3>Feature vs experimental fitness</h3>
        <div style={{ height: Math.max(180, sortedCorrelations.length * 44) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sortedCorrelations} layout="vertical" margin={{ left: 180, right: 40, top: 8, bottom: 8 }}>
              <CartesianGrid stroke={p.rule} horizontal={false} />
              <XAxis type="number" domain={[-0.5, 0.5]} tick={{ fill: p.ink2, fontSize: 12 }} />
              <YAxis type="category" dataKey="label" width={170} tick={{ fill: p.ink2, fontSize: 12 }} />
              <RTooltip contentStyle={{ background: p.paper, border: `1px solid ${p.rule}`, fontSize: 13, fontFamily: 'IBM Plex Mono, monospace' }} formatter={(v, _, row) => [`rho = ${v.toFixed(2)} (p = ${row.payload.p_value})`, 'Spearman']} />
              <Bar dataKey="spearman" radius={[0, 4, 4, 0]}>
                {sortedCorrelations.map((entry, i) => <Cell key={i} fill={entry.spearman < 0 ? p.alarm : p.ok} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="section" style={{ marginBottom: '3rem' }}>
        <h3>Burial vs. hydrophobicity</h3>
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 30, bottom: 30, left: 10 }}>
              <CartesianGrid stroke={p.rule} />
              <XAxis type="number" dataKey="hydropathy" domain={[-5, 5]} tick={{ fill: p.ink2, fontSize: 12 }} label={{ value: 'Hydropathy', position: 'bottom', fill: p.ink2, fontSize: 12 }} />
              <YAxis type="number" dataKey="mean_burial" domain={[0, 1]} tick={{ fill: p.ink2, fontSize: 12 }} label={{ value: 'Mean burial', angle: -90, position: 'insideLeft', fill: p.ink2, fontSize: 12 }} />
              <ZAxis range={[60, 60]} />
              <RTooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ background: p.paper, border: `1px solid ${p.rule}`, fontSize: 13, fontFamily: 'IBM Plex Mono, monospace' }} formatter={(v, name, row) => [v, `${name} (${row.payload.residue})`]} />
              <Scatter data={hydropathy}>
                {hydropathy.map((entry, i) => <Cell key={i} fill={entry.hydropathy > 0 ? p.ok : p.alarm} />)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="section">
        <h3>Validation checklist</h3>
        <div style={{ display: 'grid', gap: 12 }}>
          {checks.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 16px', background: p.sheet, border: `1px solid ${p.rule}`, borderRadius: 6 }}>
              <span style={{ flexShrink: 0, width: 22, height: 22, borderRadius: '50%', background: c.result === 'Pass' ? p.ok : p.flag, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700 }}>{c.result === 'Pass' ? 'v' : '-'}</span>
              <div><div style={{ fontWeight: 600, color: p.ink, marginBottom: 2 }}>{c.check}</div><div style={{ fontSize: 13, color: p.ink2 }}>{c.detail}</div></div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}