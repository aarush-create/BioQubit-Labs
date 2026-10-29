import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer, Legend } from 'recharts';

const DEFAULT_PALETTE = { ink: '#111', ink2: '#555', rule: '#ddd', paper: '#fff', sheet: '#f7f7f7', ok: '#2e7d32', alarm: '#c62828', assay: '#1565c0' };

export default function HardwareTab({ palette, data }) {
  const p = { ...DEFAULT_PALETTE, ...(palette || {}) };
  if (!data) return null;
  const labels = data.probabilities.ideal[0].map((_, i) => i.toString(2).padStart(Math.log2(data.probabilities.ideal[0].length), '0'));
  const rows = labels.map((bitstr, i) => ({ bitstr, ideal: data.probabilities.ideal[0][i], raw: data.probabilities.raw[0][i], mitigated: data.probabilities.mitigated[0][i] }));

  return (
    <div style={{ padding: '24px 0' }}>
      <h2 style={{ fontSize: 'var(--t-xl)', marginBottom: '0.5rem', color: p.ink }}>Real IBM hardware execution</h2>
      <p className="lede" style={{ color: p.ink2, maxWidth: '70ch', marginBottom: '2rem' }}>The shipped circuit executed on <strong>{data.backend}</strong>, compared against an ideal simulator. Mitigated output uses TREX readout mitigation + ZNE + dynamical decoupling.</p>
      <div className="lanes" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        <div style={{ padding: 16, background: p.sheet, border: `1px solid ${p.rule}`, borderRadius: 8 }}><div style={{ fontSize: 12, color: p.ink2, marginBottom: 4 }}>Ideal simulator</div><div className="mono" style={{ fontSize: 24, fontWeight: 700, color: p.ink }}>-</div></div>
        <div style={{ padding: 16, background: p.sheet, border: `1px solid ${p.rule}`, borderRadius: 8 }}><div style={{ fontSize: 12, color: p.ink2, marginBottom: 4 }}>Raw QPU TVD</div><div className="mono" style={{ fontSize: 24, fontWeight: 700, color: p.alarm }}>{data.fidelity_proxy.raw_tvd}</div></div>
        <div style={{ padding: 16, background: p.sheet, border: `1px solid ${p.rule}`, borderRadius: 8 }}><div style={{ fontSize: 12, color: p.ink2, marginBottom: 4 }}>Mitigated QPU TVD</div><div className="mono" style={{ fontSize: 24, fontWeight: 700, color: p.ok }}>{data.fidelity_proxy.mitigated_tvd}</div></div>
      </div>
      <div className="figure" style={{ height: 360 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 10, right: 30, bottom: 30, left: 10 }}>
            <CartesianGrid stroke={p.rule} />
            <XAxis dataKey="bitstr" tick={{ fill: p.ink2, fontSize: 12 }} />
            <YAxis tick={{ fill: p.ink2, fontSize: 12 }} />
            <RTooltip contentStyle={{ background: p.paper, border: `1px solid ${p.rule}`, fontSize: 13, fontFamily: 'IBM Plex Mono, monospace' }} formatter={(v) => v.toFixed(4)} />
            <Legend wrapperStyle={{ fontSize: 13, color: p.ink2 }} />
            <Bar dataKey="ideal" fill={p.ink2} name="Ideal" />
            <Bar dataKey="raw" fill={p.alarm} name="Raw QPU" />
            <Bar dataKey="mitigated" fill={p.ok} name="Mitigated QPU" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ marginTop: 24, padding: '12px 16px', background: p.sheet, border: `1px solid ${p.rule}`, borderRadius: 6, fontSize: 13, color: p.ink2 }}>
        <div><strong>Job IDs</strong></div>
        <div>Raw: <code>{data.jobs.raw.id}</code></div>
        <div>Mitigated: <code>{data.jobs.mitigated.id}</code></div>
      </div>
    </div>
  );
}