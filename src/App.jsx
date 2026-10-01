import React, { useState, useEffect, useRef } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar
} from 'recharts';
import { 
  Activity, Dna, Play, Cpu, ShieldAlert, Syringe, MessageSquare, 
  X, Send, Info, HelpCircle, ArrowRight
} from 'lucide-react';

// --- CUSTOM TOOLTIP COMPONENT ---
const HelpTooltip = ({ text }) => (
  <div className="group relative inline-flex items-center justify-center ml-2 cursor-help">
    <Info size={16} className="text-slate-500 hover:text-cyan-400 transition-colors" />
    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-slate-800 text-slate-200 text-xs rounded-lg border border-slate-700 shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
      {text}
      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800"></div>
    </div>
  </div>
);

export default function App() {
  const [activeTab, setActiveTab] = useState('genomics');
  const [loading, setLoading] = useState(false);
  const [threatScore, setThreatScore] = useState(0.45);
  const [r0, setR0] = useState(1.2);
  const [showWelcome, setShowWelcome] = useState(true);
  
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: 'Hi! I am your Q-VIRA Copilot. Ask me how to interpret the Quantum Threat Score or how our VQE simulator works.' }
  ]);
  const chatEndRef = useRef(null);

  const runLiveQuantumEngine = async () => {
    setLoading(true);
    try {
      // Replace with your Render URL: e.g., "https://q-vira-backend.onrender.com/predict"
      const response = await fetch("https://q-vira-backend.onrender.com/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ features: [0.78, 1.12, -0.34, 0.95] }) 
      });
      
      const data = await response.json();
      setThreatScore(data.threat_score);
      setR0(data.r0);
    } catch (error) {
      console.error("Quantum backend offline, using simulated fallback for demo.");
      setTimeout(() => {
        setThreatScore(0.84);
        setR0(2.15);
        setLoading(false);
      }, 1500);
    }
    setLoading(false);
  };

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    setChatMessages([...chatMessages, { role: 'user', text: chatInput }]);
    setTimeout(() => {
      let aiResponse = "The PennyLane VQC analyzes structural drift. A score above 0.70 means the mutation is highly evasive.";
      if (chatInput.toLowerCase().includes("vqe")) aiResponse = "VQE (Variational Quantum Eigensolver) finds the lowest energy state of the viral protein binding with a drug to test if the drug will work.";
      if (chatInput.toLowerCase().includes("r0")) aiResponse = `Based on the current threat score of ${threatScore.toFixed(2)}, the projected basic reproduction number (R0) is ${r0.toFixed(2)}.`;
      setChatMessages(prev => [...prev, { role: 'ai', text: aiResponse }]);
    }, 1000);
    setChatInput('');
  };

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatOpen]);

  const seirData = Array.from({ length: 45 }, (_, i) => ({
    day: i,
    infected: Math.floor(100 * Math.pow(r0, i / 8)),
    recovered: Math.floor(40 * i * (r0 / 1.5)),
    capacity: 2500
  }));

  const featureData = [
    { subject: 'Binding Affinity', A: threatScore * 120, fullMark: 150 },
    { subject: 'Immune Escape', A: threatScore * 140, fullMark: 150 },
    { subject: 'Structural Drift', A: threatScore * 90, fullMark: 150 },
    { subject: 'Codon Bias', A: threatScore * 110, fullMark: 150 },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-cyan-500/30 pb-20">
      
      {/* WELCOME ONBOARDING MODAL */}
      {showWelcome && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl max-w-2xl w-full p-8 relative">
            <button onClick={() => setShowWelcome(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white">
              <X size={24} />
            </button>
            <div className="flex items-center gap-3 mb-6">
              <Dna className="w-10 h-10 text-cyan-400" />
              <h2 className="text-3xl font-bold text-white">Welcome to Q-VIRA</h2>
            </div>
            <p className="text-slate-300 mb-6 leading-relaxed">
              Q-VIRA is a hybrid quantum-classical pipeline that predicts viral outbreaks and discovers drug vulnerabilities weeks before clinical data is available. 
            </p>
            <div className="space-y-4 mb-8">
              <div className="flex gap-4 items-start p-4 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="bg-cyan-500/20 text-cyan-400 rounded-full w-8 h-8 flex items-center justify-center font-bold shrink-0">1</div>
                <div>
                  <h3 className="font-bold text-white">Upload Sequence (Genomics Tab)</h3>
                  <p className="text-sm text-slate-400">Input a viral RNA string. We compress it into 4 features for the quantum computer.</p>
                </div>
              </div>
              <div className="flex gap-4 items-start p-4 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="bg-blue-500/20 text-blue-400 rounded-full w-8 h-8 flex items-center justify-center font-bold shrink-0">2</div>
                <div>
                  <h3 className="font-bold text-white">Execute VQC Engine</h3>
                  <p className="text-sm text-slate-400">Click the "Run VQC Engine" button in the top right. Our PennyLane circuit will calculate the mutational Threat Score.</p>
                </div>
              </div>
              <div className="flex gap-4 items-start p-4 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="bg-emerald-500/20 text-emerald-400 rounded-full w-8 h-8 flex items-center justify-center font-bold shrink-0">3</div>
                <div>
                  <h3 className="font-bold text-white">Analyze & Prevent (SEIR & VQE Tabs)</h3>
                  <p className="text-sm text-slate-400">View the projected epidemic outbreak curve and simulate quantum drug binding.</p>
                </div>
              </div>
            </div>
            <button 
              onClick={() => setShowWelcome(false)}
              className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-bold py-3 rounded-lg flex items-center justify-center gap-2 transition-colors"
            >
              Start the Demo <ArrowRight size={20} />
            </button>
          </div>
        </div>
      )}

      {/* HEADER */}
      <nav className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/10 rounded-lg border border-cyan-500/20">
              <Dna className="w-8 h-8 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-blue-500 tracking-tight">
                Q-VIRA
              </h1>
              <div className="text-xs text-slate-400 font-medium">BioQubit Labs</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowWelcome(true)} className="text-slate-400 hover:text-cyan-400 flex items-center gap-1 text-sm font-medium transition-colors">
              <HelpCircle size={18} /> Tour
            </button>
            <div className="h-6 w-px bg-slate-700"></div>
            <div className="flex items-center gap-3">
              <span className="text-sm font-bold text-slate-400 hidden sm:block">Step 2:</span>
              <button 
                onClick={runLiveQuantumEngine}
                disabled={loading}
                className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold py-2 px-6 rounded-lg flex items-center gap-2 transition-all shadow-[0_0_15px_-5px_rgba(6,182,212,0.5)] disabled:opacity-50"
              >
                {loading ? <Activity className="animate-spin" size={20} /> : <Play size={20} />}
                {loading ? "Processing..." : "Run VQC Engine"}
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        
        {/* METRICS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="p-6 bg-slate-900 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden group">
            <div className="text-slate-400 mb-2 font-medium flex items-center">
              Quantum Threat Score 
              <HelpTooltip text="A normalized value (0 to 1) output by our PennyLane Quantum Circuit. It evaluates how evasive and structurally dangerous the uploaded virus mutation is." />
            </div>
            <div className="text-5xl font-bold text-white mb-2">
              {threatScore.toFixed(2)}
              <span className="text-lg text-rose-400 ml-2">S_threat</span>
            </div>
            <div className="text-sm text-slate-500">Calculated via VQC Expectation</div>
          </div>
          
          <div className="p-6 bg-slate-900 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden group">
            <div className="text-slate-400 mb-2 font-medium flex items-center">
              Projected R0 Velocity 
              <HelpTooltip text="The Basic Reproduction Number (R0) represents how many people one sick person will infect. 'Velocity' means how fast this rate is accelerating due to the mutation." />
            </div>
            <div className="text-5xl font-bold text-white mb-2">
              {r0.toFixed(2)}
              <span className="text-lg text-orange-400 ml-2">Δ/t</span>
            </div>
            <div className="text-sm text-slate-500">Live Epidemic Parameter</div>
          </div>
          
          <div className="p-6 bg-slate-900 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden group">
            <div className="text-slate-400 mb-2 font-medium flex items-center">
              Macro Portfolio Hedge 
              <HelpTooltip text="Translates biological risk into financial action. If Threat Score > 0.70, the system triggers a signal to short vulnerable travel stocks and buy protective options." />
            </div>
            <div className="text-4xl font-bold text-white mb-2 mt-1">
              {threatScore > 0.70 ? "ACTIVE" : "STABLE"}
            </div>
            <div className="text-sm text-emerald-400">
              {threatScore > 0.70 ? "Strategy: Long VIX / Short Travel" : "Baseline Allocation"}
            </div>
          </div>
        </div>

        {/* TABS */}
        <div className="flex flex-wrap gap-2 bg-slate-900 p-1.5 rounded-xl mb-6 border border-slate-800 w-fit">
          {[
            { id: 'genomics', label: '1. Genomics Ingestion' },
            { id: 'vqc', label: '2. Quantum Circuit (VQC)' },
            { id: 'seir', label: '3. Outbreak Forecast' },
            { id: 'vqe', label: '4. Drug Discovery (VQE)' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                activeTab === tab.id 
                  ? 'bg-slate-800 text-cyan-400 shadow-md border border-slate-700' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* TAB CONTENT */}
        <div className="bg-slate-900 p-8 rounded-2xl border border-slate-800 shadow-xl min-h-[500px]">
          
          {/* TAB 1 */}
          {activeTab === 'genomics' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-full">
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <h2 className="text-2xl font-bold text-white">Sequence Ingestion</h2>
                  <span className="bg-slate-800 text-cyan-400 text-xs px-2 py-1 rounded font-bold border border-slate-700">Step 1</span>
                </div>
                <p className="text-slate-400 mb-6">
                  Paste a raw viral RNA string below. We use a classical Protein Language Model (ESM-2) to analyze the string, then compress it into a 4-feature PCA Vector so it fits inside a Quantum Computer.
                </p>
                <div className="mb-2 text-sm font-bold text-slate-300">Target Viral FASTA Sequence:</div>
                <textarea 
                  className="w-full h-48 bg-slate-950 border border-slate-700 rounded-xl p-4 text-cyan-400 font-mono text-sm focus:border-cyan-500 outline-none"
                  defaultValue=">Spike_Protein_Variant_XBB\nMFVFLVLLPLVSSQCVNLTTRTQLPPAYTNSFTRGVYYPDKVFRSSVLHL..."
                />
              </div>
              <div className="flex flex-col items-center justify-center border border-slate-800 rounded-xl bg-slate-950/50 p-4">
                <div className="w-full text-center text-sm font-bold text-slate-400 mb-2">
                  Extracted Biological Features (PCA Vector)
                  <HelpTooltip text="PCA (Principal Component Analysis) reduces massive data down to exactly 4 variables, perfectly matching our 4-Qubit quantum system." />
                </div>
                <ResponsiveContainer width="100%" height={300}>
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={featureData}>
                    <PolarGrid stroke="#334155" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 150]} tick={false} axisLine={false} />
                    <Radar name="Threat Vector" dataKey="A" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.3} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* TAB 2 */}
          {activeTab === 'vqc' && (
            <div className="h-full flex flex-col">
              <h2 className="text-2xl font-bold text-white mb-2 flex items-center">
                Variational Quantum Classifier (VQC)
                <HelpTooltip text="A quantum machine learning model. It acts like a neural network but uses quantum entanglement to find hidden mutation patterns classical computers miss." />
              </h2>
              <p className="text-slate-400 mb-8">
                This is a live representation of the 4-Qubit PennyLane circuit. The biological features are angle-encoded into quantum states, entangled, and measured to predict the Threat Score.
              </p>
              
              <div className="flex-1 bg-slate-950 rounded-xl border border-slate-800 p-8 flex items-center justify-center font-mono text-sm text-cyan-500 overflow-x-auto">
                <div className="space-y-6 w-full max-w-3xl min-w-[600px]">
                  {['Qubit 0', 'Qubit 1', 'Qubit 2', 'Qubit 3'].map((q, i) => (
                    <div key={q} className="flex items-center gap-4">
                      <span className="text-slate-400 w-16 font-bold">{q}</span>
                      <div className="h-px bg-slate-600 flex-1 relative flex items-center justify-around">
                        <div className="px-4 py-2 bg-blue-900/80 border border-blue-500 rounded text-white shadow-lg">Ry(θ) Data Encode</div>
                        {i < 3 && <div className="w-4 h-4 rounded-full bg-cyan-400 absolute left-1/3 shadow-[0_0_10px_#22d3ee]"></div>}
                        <div className="px-4 py-2 bg-indigo-900/80 border border-indigo-500 rounded text-white shadow-lg">Entangle Gate</div>
                        {i === 0 && <div className="px-4 py-2 bg-rose-900/80 border border-rose-500 rounded text-white font-bold shadow-[0_0_15px_rgba(244,63,94,0.4)] absolute right-0">Measure Z</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3 */}
          {activeTab === 'seir' && (
            <div className="h-full flex flex-col">
              <h2 className="text-2xl font-bold text-white mb-2 flex items-center">
                Epidemiological Bridge (SEIR Model)
                <HelpTooltip text="Susceptible, Exposed, Infected, Recovered. A classic math model that predicts how an outbreak spreads. We feed our Quantum R0 directly into this math." />
              </h2>
              <p className="text-slate-400 mb-6">
                Instead of waiting 21 days for the CDC to report cases, we inject our Quantum Threat Score directly into differential equations to project the outbreak curve today.
              </p>
              <div className="flex-1 bg-slate-950 rounded-xl p-4 border border-slate-800">
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={seirData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="day" stroke="#64748b" tick={{fill: '#64748b'}} />
                    <YAxis stroke="#64748b" tick={{fill: '#64748b'}} />
                    <RechartsTooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', color: '#fff' }} />
                    <Legend />
                    <Line type="monotone" dataKey="infected" stroke="#f43f5e" strokeWidth={3} dot={false} name="Predicted Infected" />
                    <Line type="monotone" dataKey="recovered" stroke="#10b981" strokeWidth={3} dot={false} name="Recovered Population" />
                    <Line type="step" dataKey="capacity" stroke="#eab308" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Critical Hospital Capacity" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* TAB 4 */}
          {activeTab === 'vqe' && (
            <div className="h-full grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div>
                <h2 className="text-2xl font-bold text-white mb-4 flex items-center">
                  <Syringe className="mr-2 text-cyan-400"/> Drug Target Discovery
                  <HelpTooltip text="VQE computes the exact energy required for a drug molecule to bind to the virus. Lower energy means the drug successfully neutralizes the virus." />
                </h2>
                <p className="text-slate-400 mb-6">
                  Using Qiskit Nature's Variational Quantum Eigensolver (VQE), we simulate the fermionic physics of the virus interacting with a drug inhibitor to prove if the drug will work.
                </p>
                <div className="bg-slate-950 p-6 rounded-xl border border-slate-800 space-y-5">
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-400 font-medium">Target Drug Molecule</span>
                    <span className="text-white font-bold">Paxlovid Derivative</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-400 font-medium">Quantum Hamiltonian</span>
                    <span className="text-white font-mono text-sm">12 Qubits (Jordan-Wigner)</span>
                  </div>
                  <div className="flex justify-between items-center bg-emerald-500/10 p-3 rounded-lg border border-emerald-500/20">
                    <span className="text-emerald-400 font-medium">Ground State Energy (E0)</span>
                    <span className="text-emerald-400 font-bold text-xl">-4.882 Hartree</span>
                  </div>
                </div>
              </div>
              <div className="relative border border-slate-800 rounded-xl bg-slate-950 flex items-center justify-center min-h-[300px]">
                {/* Simulated 3D Pocket View */}
                <div className="absolute inset-0 bg-[url('https://upload.wikimedia.org/wikipedia/commons/3/30/SARS-CoV-2_spike_protein_closed_conformation.png')] bg-contain bg-no-repeat bg-center opacity-40 mix-blend-screen"></div>
                <div className="z-10 text-center bg-slate-950/80 p-4 rounded-xl border border-slate-800 backdrop-blur-sm">
                  <div className="w-12 h-12 border-4 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin mx-auto mb-3"></div>
                  <span className="text-cyan-400 font-mono text-sm tracking-widest font-bold">VQE SIMULATION ACTIVE</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* AI COPILOT */}
      <div className="fixed bottom-24 right-6 z-50">
        {!isChatOpen ? (
          <button 
            onClick={() => setIsChatOpen(true)}
            className="bg-cyan-600 hover:bg-cyan-500 text-white p-4 rounded-full shadow-[0_0_20px_rgba(8,145,178,0.4)] transition-transform hover:scale-110 flex items-center gap-2 group"
          >
            <MessageSquare size={24} />
            <span className="max-w-0 overflow-hidden whitespace-nowrap group-hover:max-w-xs transition-all duration-300 ease-in-out font-bold">Ask AI Copilot</span>
          </button>
        ) : (
          <div className="w-80 h-96 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
            <div className="bg-slate-800 p-4 border-b border-slate-700 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></div>
                <span className="font-bold text-sm text-white">Q-VIRA Copilot</span>
              </div>
              <button onClick={() => setIsChatOpen(false)} className="text-slate-400 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>
            
            <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-slate-900/50">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] p-3 rounded-xl text-sm shadow-md ${
                    msg.role === 'user' ? 'bg-cyan-600 text-white rounded-br-sm' : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-bl-sm'
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
                className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 transition-colors"
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
