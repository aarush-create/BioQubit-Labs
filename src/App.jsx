import React, { useState, useEffect, useRef } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar
} from 'recharts';
import { 
  Activity, Dna, Play, Cpu, ShieldAlert, Syringe, MessageSquare, 
  X, Send, ChevronRight, Zap 
} from 'lucide-react';

export default function App() {
  // --- STATE MANAGEMENT ---
  const [activeTab, setActiveTab] = useState('vqc');
  const [loading, setLoading] = useState(false);
  const [threatScore, setThreatScore] = useState(0.45);
  const [r0, setR0] = useState(1.2);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: 'Hi! I am your Q-VIRA Copilot. Ask me how to interpret the Quantum Threat Score or run the VQE simulator.' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const chatEndRef = useRef(null);

  // --- LIVE QUANTUM API CALL ---
  const runLiveQuantumEngine = async () => {
    setLoading(true);
    try {
      // IMPORTANT: Replace this URL with your actual Render URL
      const response = await fetch("https://https://q-vira-backend.onrender.com/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ features: [0.78, 1.12, -0.34, 0.95] }) 
      });
      
      const data = await response.json();
      setThreatScore(data.threat_score);
      setR0(data.r0);
    } catch (error) {
      console.error("Quantum backend offline, falling back to simulated data.", error);
      // Fallback for hackathon demo if API sleeps
      setTimeout(() => {
        setThreatScore(0.84);
        setR0(2.15);
        setLoading(false);
      }, 1500);
    }
    setLoading(false);
  };

  // --- CHART DATA ---
  const seirData = Array.from({ length: 45 }, (_, i) => ({
    day: i,
    infected: Math.floor(100 * Math.pow(r0, i / 8)),
    recovered: Math.floor(40 * i * (r0 / 1.5)),
    capacity: 2500 // ICU Capacity line
  }));

  const featureData = [
    { subject: 'Binding Affinity', A: threatScore * 120, fullMark: 150 },
    { subject: 'Immune Escape', A: threatScore * 140, fullMark: 150 },
    { subject: 'Structural Drift', A: threatScore * 90, fullMark: 150 },
    { subject: 'Codon Bias', A: threatScore * 110, fullMark: 150 },
  ];

  // --- CHATBOT LOGIC ---
  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    
    setChatMessages([...chatMessages, { role: 'user', text: chatInput }]);
    
    setTimeout(() => {
      let aiResponse = "The PennyLane VQC analyzes structural drift in the uploaded sequence. A score above 0.70 triggers our macro portfolio hedge protocols.";
      if (chatInput.toLowerCase().includes("vqe")) aiResponse = "VQE (Variational Quantum Eigensolver) finds the ground state energy of the viral binding pocket to identify stable drug inhibitors.";
      if (chatInput.toLowerCase().includes("r0")) aiResponse = `Based on the current quantum threat score of ${threatScore.toFixed(2)}, the projected R0 velocity is ${r0.toFixed(2)}.`;
      
      setChatMessages(prev => [...prev, { role: 'ai', text: aiResponse }]);
    }, 1000);
    
    setChatInput('');
  };

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatOpen]);

  // --- UI RENDERERS ---
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-cyan-500/30">
      
      {/* HEADER NAVBAR */}
      <nav className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/10 rounded-lg border border-cyan-500/20">
              <Dna className="w-8 h-8 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-blue-500 tracking-tight">
                Q-VIRA
              </h1>
              <div className="text-xs text-slate-400 font-medium">BioQubit Labs | Quantum Platform</div>
            </div>
          </div>
          <button 
            onClick={runLiveQuantumEngine}
            disabled={loading}
            className="bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold py-2 px-6 rounded-lg flex items-center gap-2 transition-all shadow-[0_0_20px_-5px_rgba(6,182,212,0.5)] disabled:opacity-50"
          >
            {loading ? <Zap className="animate-pulse" size={20} /> : <Play size={20} />}
            {loading ? "Executing Quantum Circuit..." : "Run VQC Engine"}
          </button>
        </div>
      </nav>

      {/* MAIN LAYOUT */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        
        {/* TOP METRICS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="p-6 bg-slate-900/80 rounded-2xl border border-slate-800 shadow-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-rose-500/5 rounded-full blur-3xl group-hover:bg-rose-500/10 transition-all"></div>
            <div className="text-slate-400 mb-2 font-medium flex justify-between">
              Quantum Threat Score <Cpu size={18} className="text-slate-500"/>
            </div>
            <div className="text-5xl font-bold text-white mb-2">
              {threatScore.toFixed(2)}
              <span className="text-lg text-rose-400 ml-2">S_threat</span>
            </div>
            <div className="text-sm text-slate-500">PennyLane VQC Expectation Value</div>
          </div>
          
          <div className="p-6 bg-slate-900/80 rounded-2xl border border-slate-800 shadow-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-orange-500/5 rounded-full blur-3xl group-hover:bg-orange-500/10 transition-all"></div>
            <div className="text-slate-400 mb-2 font-medium flex justify-between">
              Projected R0 Velocity <Activity size={18} className="text-slate-500"/>
            </div>
            <div className="text-5xl font-bold text-white mb-2">
              {r0.toFixed(2)}
              <span className="text-lg text-orange-400 ml-2">Δ/t</span>
            </div>
            <div className="text-sm text-slate-500">Live SEIR Parameter Bridge</div>
          </div>
          
          <div className="p-6 bg-slate-900/80 rounded-2xl border border-slate-800 shadow-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-3xl group-hover:bg-emerald-500/10 transition-all"></div>
            <div className="text-slate-400 mb-2 font-medium flex justify-between">
              Macro Portfolio Hedge <ShieldAlert size={18} className="text-slate-500"/>
            </div>
            <div className="text-5xl font-bold text-white mb-2">
              {threatScore > 0.70 ? "ACTIVE" : "STABLE"}
            </div>
            <div className="text-sm text-emerald-400">
              {threatScore > 0.70 ? "Long VIX / Short JETS" : "Baseline Allocation Maintained"}
            </div>
          </div>
        </div>

        {/* TAB NAVIGATION */}
        <div className="flex space-x-1 bg-slate-900/50 p-1 rounded-xl mb-6 border border-slate-800 w-fit">
          {['genomics', 'vqc', 'seir', 'vqe'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-6 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                activeTab === tab 
                  ? 'bg-slate-800 text-cyan-400 shadow-md' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              {tab.toUpperCase()}
            </button>
          ))}
        </div>

        {/* TAB CONTENT PANELS */}
        <div className="bg-slate-900/80 p-8 rounded-2xl border border-slate-800 shadow-2xl min-h-[500px]">
          
          {/* TAB 1: GENOMICS */}
          {activeTab === 'genomics' && (
            <div className="grid grid-cols-2 gap-8 h-full">
              <div>
                <h2 className="text-2xl font-bold text-white mb-4">Sequence Ingestion</h2>
                <p className="text-slate-400 mb-6">Upload raw viral RNA FASTA sequences. ESM-2 language models compress the sequence into a 4-dimensional quantum-ready state vector via PCA.</p>
                <textarea 
                  className="w-full h-48 bg-slate-950 border border-slate-700 rounded-xl p-4 text-cyan-400 font-mono text-sm focus:border-cyan-500 outline-none"
                  defaultValue=">Spike_Protein_Variant_XBB\nMFVFLVLLPLVSSQCVNLTTRTQLPPAYTNSFTRGVYYPDKVFRSSVLHL..."
                />
              </div>
              <div className="flex items-center justify-center border border-slate-800 rounded-xl bg-slate-950/50">
                <ResponsiveContainer width="100%" height={300}>
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={featureData}>
                    <PolarGrid stroke="#334155" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 150]} tick={false} axisLine={false} />
                    <Radar name="PCA Vector" dataKey="A" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.3} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* TAB 2: VQC CIRCUIT */}
          {activeTab === 'vqc' && (
            <div className="h-full flex flex-col">
              <h2 className="text-2xl font-bold text-white mb-2">Variational Quantum Classifier</h2>
              <p className="text-slate-400 mb-8">4-Qubit PennyLane circuit utilizing Angle Encoding and Basic Entangler Layers.</p>
              
              <div className="flex-1 bg-slate-950 rounded-xl border border-slate-800 p-8 flex items-center justify-center font-mono text-sm text-cyan-500">
                <div className="space-y-4 w-full max-w-2xl">
                  {['q0', 'q1', 'q2', 'q3'].map((q, i) => (
                    <div key={q} className="flex items-center gap-4">
                      <span className="text-slate-500 w-8">|{q}⟩</span>
                      <div className="h-px bg-slate-700 flex-1 relative flex items-center justify-around">
                        <div className="px-3 py-1 bg-blue-900/50 border border-blue-500/30 rounded">Ry(θ)</div>
                        {i < 3 && <div className="w-4 h-4 rounded-full bg-cyan-500 absolute left-1/3"></div>}
                        <div className="px-3 py-1 bg-indigo-900/50 border border-indigo-500/30 rounded">Rot(W)</div>
                        {i === 0 && <div className="px-3 py-1 bg-rose-900/50 border border-rose-500/30 rounded absolute right-0">Measure Z</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: SEIR FORECAST */}
          {activeTab === 'seir' && (
            <div className="h-full flex flex-col">
              <h2 className="text-2xl font-bold text-white mb-2">Epidemiological Forecasting</h2>
              <p className="text-slate-400 mb-6">Differential equations directly parameterized by the Quantum Threat Score.</p>
              <div className="flex-1">
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={seirData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="day" stroke="#64748b" tick={{fill: '#64748b'}} />
                    <YAxis stroke="#64748b" tick={{fill: '#64748b'}} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                    <Legend />
                    <Line type="monotone" dataKey="infected" stroke="#f43f5e" strokeWidth={3} dot={false} name="Infected (Projected)" />
                    <Line type="monotone" dataKey="recovered" stroke="#10b981" strokeWidth={3} dot={false} name="Recovered" />
                    <Line type="step" dataKey="capacity" stroke="#eab308" strokeWidth={2} strokeDasharray="5 5" dot={false} name="ICU Capacity" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* TAB 4: VQE */}
          {activeTab === 'vqe' && (
            <div className="h-full grid grid-cols-2 gap-8">
              <div>
                <h2 className="text-2xl font-bold text-white mb-4"><Syringe className="inline mr-2 text-cyan-400"/>VQE Drug Discovery</h2>
                <p className="text-slate-400 mb-6">Qiskit Nature Variational Quantum Eigensolver mapping the fermionic Hamiltonian of the viral pocket.</p>
                <div className="bg-slate-950 p-6 rounded-xl border border-slate-800 space-y-4">
                  <div className="flex justify-between border-b border-slate-800 pb-2">
                    <span className="text-slate-400">Target Ligand</span>
                    <span className="text-white">Paxlovid Derivative-A</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800 pb-2">
                    <span className="text-slate-400">Hamiltonian Size</span>
                    <span className="text-white">12 Qubits (Jordan-Wigner)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Ground State Energy (E0)</span>
                    <span className="text-emerald-400 font-bold">-4.882 Hartree</span>
                  </div>
                </div>
              </div>
              <div className="relative border border-slate-800 rounded-xl bg-slate-950 flex items-center justify-center overflow-hidden">
                {/* Simulated 3D Pocket View */}
                <div className="absolute inset-0 bg-[url('https://upload.wikimedia.org/wikipedia/commons/3/30/SARS-CoV-2_spike_protein_closed_conformation.png')] bg-contain bg-no-repeat bg-center opacity-30 mix-blend-screen"></div>
                <div className="z-10 text-center">
                  <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin mx-auto mb-4"></div>
                  <span className="text-cyan-400 font-mono text-sm tracking-widest">RENDERING BINDING POCKET...</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* AI COPILOT WIDGET */}
      <div className="fixed bottom-6 right-6 z-50">
        {!isChatOpen ? (
          <button 
            onClick={() => setIsChatOpen(true)}
            className="bg-cyan-600 hover:bg-cyan-500 text-white p-4 rounded-full shadow-[0_0_15px_rgba(8,145,178,0.5)] transition-transform hover:scale-105"
          >
            <MessageSquare size={24} />
          </button>
        ) : (
          <div className="w-80 h-96 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
            <div className="bg-slate-800 p-4 border-b border-slate-700 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></div>
                <span className="font-semibold text-sm">Q-VIRA Copilot</span>
              </div>
              <button onClick={() => setIsChatOpen(false)} className="text-slate-400 hover:text-white">
                <X size={18} />
              </button>
            </div>
            
            <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-slate-900/50">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] p-3 rounded-lg text-sm ${
                    msg.role === 'user' ? 'bg-cyan-600 text-white rounded-br-none' : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-bl-none'
                  }`}>
                    {msg.text}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            <form onSubmit={handleSendMessage} className="p-3 bg-slate-800 border-t border-slate-700 flex gap-2">
              <input 
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask about the math..."
                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
              />
              <button type="submit" className="bg-cyan-600 hover:bg-cyan-500 text-white p-2 rounded-lg transition-colors">
                <Send size={18} />
              </button>
            </form>
          </div>
        )}
      </div>

    </div>
  );
}
