import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, ResponsiveContainer } from 'recharts';

const COLORS = { VQC: '#7c4dff', LogReg: '#1565c0', MLP: '#ef6c00', SVM: '#2e7d32' };
const DEFAULT_PALETTE = { ink: '#111', ink2: '#555', rule: '#ddd', paper: '#fff' };

export default function FewShotCurve({ palette, data }) {
  const p = { ...DEFAULT_PALETTE, ...(palette || {}) };
  if (!data || !data.curves) return null;
  const rows = data.sample_sizes.map((n, i) => {
    const row = { n };
    for (const [model, c] of Object.entries(data.curves)) { row[model] = c.mean_auc[i]; }
    return row;
  });

  return (
    <div style={{ padding: '24px 0' }}>
      <h2 style={{ fontSize: 'var(--t-xl)', marginBottom: '0.5rem', color: p.ink }}>Few-shot learning curve</h2>
      <p className="lede" style={{ color: p.ink2, maxWidth: '70ch', marginBottom: '2rem' }}>All models retrained from scratch on identical random draws of the training sites. If the quantum model closes the gap faster as training data shrinks, that is the data-efficiency argument for QML.</p>
      <div className="figure" style={{ height: 400 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 10, right: 30, bottom: 40, left: 10 }}>
            <CartesianGrid stroke={p.rule} />
            <XAxis dataKey="n" type="number" scale="log" domain={['dataMin', 'dataMax']} tick={{ fill: p.ink2, fontSize: 12 }} label={{ value: 'Training examples (log scale)', position: 'bottom', fill: p.ink2, fontSize: 12 }} />
            <YAxis domain={[0.5, 0.85]} tick={{ fill: p.ink2, fontSize: 12 }} label={{ value: 'Held-out AUC', angle: -90, position: 'insideLeft', fill: p.ink2, fontSize: 12 }} />
            <RTooltip contentStyle={{ background: p.paper, border: `1px solid ${p.rule}`, fontSize: 13, fontFamily: 'IBM Plex Mono, monospace' }} formatter={(v) => v == null ? '-' : v.toFixed(3)} labelFormatter={(n) => `n = ${n}`} />
            <Legend wrapperStyle={{ fontSize: 13, color: p.ink2 }} />
            {Object.keys(data.curves).map((model) => <Line key={model} type="monotone" dataKey={model} stroke={COLORS[model] || p.ink} strokeWidth={2} dot={{ r: 3 }} connectNulls />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}