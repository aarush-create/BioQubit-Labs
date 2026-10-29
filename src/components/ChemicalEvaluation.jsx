import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function ChemicalEvaluation() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadMetrics() {
      try {
        const response = await fetch('/api/v1/evaluation');
        const data = await response.json();
        setMetrics(data);
        setLoading(false);
      } catch (error) {
        console.error("Failed to load evaluation metrics", error);
        setLoading(false);
      }
    }
    loadMetrics();
  }, []);

  if (loading) return <div className="p-6 text-center text-gray-600">Loading Evaluation Models...</div>;

  return (
    <div className="evaluation-container p-6 bg-white rounded-lg shadow-md border border-gray-200">
      <h2 className="text-2xl font-bold mb-4 text-gray-800">Chemical Evaluation & Benchmarking</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="stat-card p-4 border rounded bg-gray-50">
          <h3 className="text-gray-500 text-sm uppercase tracking-wide">Target Sequence</h3>
          <p className="font-semibold text-lg">{metrics.model_target}</p>
        </div>
        <div className="stat-card p-4 border rounded bg-gray-50">
          <h3 className="text-gray-500 text-sm uppercase tracking-wide">Classical vs Quantum R²</h3>
          <p className="font-semibold text-lg">{metrics.classical_r2} → {metrics.quantum_r2}</p>
        </div>
        <div className="stat-card p-4 border rounded bg-gray-50">
          <h3 className="text-gray-500 text-sm uppercase tracking-wide">RMSE Improvement</h3>
          <p className="font-semibold text-lg text-emerald-600">-{metrics.rmse_improvement_pct}%</p>
        </div>
      </div>

      <div className="chart-container h-80 w-full mt-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-700">VQE Energy Convergence (H₂ Demonstration)</h3>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={metrics.vqe_data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="iteration" label={{ value: 'Optimizer Iterations', position: 'insideBottomRight', offset: -5 }} />
            <YAxis label={{ value: 'Energy (Hartree)', angle: -90, position: 'insideLeft' }} domain={['dataMin - 0.1', 'dataMax + 0.1']} />
            <Tooltip 
              contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
            />
            <Legend verticalAlign="top" height={36} />
            <Line 
              type="monotone" 
              dataKey="energy_hartree" 
              stroke="#6366f1" 
              strokeWidth={2}
              name="Quantum Ground State Energy" 
              dot={false}
              activeDot={{ r: 6 }} 
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
