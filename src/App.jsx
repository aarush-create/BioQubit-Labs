import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Activity, Dna } from 'lucide-react';

export default function App() {
  const [r0, setR0] = useState(1.5);

  // Simulated SEIR curve data based on Quantum Threat Score
  const data = Array.from({ length: 30 }, (_, i) => ({
    day: i,
    infected: Math.floor(100 * Math.pow(r0, i / 5)),
    recovered: Math.floor(20 * i)
  }));

  return (
    <div className="p-8 font-sans max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <Dna className="w-10 h-10 text-cyan-400" />
        <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-blue-500">
          Q-VIRA Dashboard
        </h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="p-6 bg-slate-800 rounded-xl border border-slate-700 shadow-lg">
          <div className="text-slate-400 mb-2 font-semibold">Quantum Threat Score</div>
          <div className="text-5xl font-bold text-rose-400">0.84</div>
          <div className="text-sm text-slate-500 mt-2">PennyLane VQC Output</div>
        </div>
        
        <div className="p-6 bg-slate-800 rounded-xl border border-slate-700 shadow-lg">
          <div className="text-slate-400 mb-2 font-semibold">Projected R0 Velocity</div>
          <div className="text-5xl font-bold text-orange-400">{r0.toFixed(2)}</div>
          <div className="text-sm text-slate-500 mt-2">SEIR Parameter Updated</div>
        </div>
        
        <div className="p-6 bg-slate-800 rounded-xl border border-slate-700 shadow-lg">
          <div className="text-slate-400 mb-2 font-semibold">Macro Portfolio Hedge</div>
          <div className="text-5xl font-bold text-green-400">Active</div>
          <div className="text-sm text-slate-500 mt-2">VIX Calls / Travel Short</div>
        </div>
      </div>

      <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg h-[450px]">
        <h2 className="text-xl mb-6 flex items-center gap-2 font-semibold text-cyan-300">
          <Activity /> SEIR Outbreak Projection vs CDC Data
        </h2>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="day" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }} />
            <Legend />
            <Line type="monotone" dataKey="infected" stroke="#f43f5e" strokeWidth={3} name="Predicted Infected" />
            <Line type="monotone" dataKey="recovered" stroke="#10b981" strokeWidth={3} name="Predicted Recovered" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
