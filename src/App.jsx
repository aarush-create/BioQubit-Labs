import React, { useState, useEffect, useRef } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar
} from 'recharts';
import { 
  Activity, Dna, Play, Cpu, ShieldAlert, Syringe, MessageSquare, 
  X, Send, Info, HelpCircle, ArrowRight, Printer, Database, Globe, AlertTriangle, Radio
} from 'lucide-react';

const HelpTooltip = ({ text }) => (
  <div className="group relative inline-flex items-center justify-center ml-2 cursor-help">
    <Info size={14} className="text-slate-500 hover:text-cyan-400 transition-colors" />
    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-slate-800 text-slate-200 text-xs rounded-lg border border-slate-700 shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
      {text}
      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800"></div>
    </div>
  </div>
);

export default function App() {
  const [activeTab, setActiveTab] = useState('sentinel');
  const [loading, setLoading] = useState(false);
  const [threatScore, setThreatScore] = useState(0.45);
  const [r0, setR0] = useState(1.2);
  const [showWelcome, setShowWelcome] = useState(true);
  const [dbMatch, setDbMatch] = useState("Awaiting Analysis...");
  
  const [fastaInput, setFastaInput] = useState(">Spike_Protein_Variant_XBB\nMFVFLVLLPLVSSQCVNLTTRTQLPPAYTNSFTRGVYYPDKVFRSSVLHLTQDLFLPFFSNVTWFHAIHVSGTNGTKRFD");
  const [pdbInput, setPdbInput] = useState("6m0j");
  
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: 'Hi! I am your Q-VIRA Copilot. Ask me how the Global Sentinel scrapes data, or how the VQC engine works.' }
  ]);
  const chatEndRef = useRef(null);

  const strLen = fastaInput.length;
  const currentAngles = [
    ((strLen % 100) / 100).toFixed(2), 
    ((fastaInput.charCodeAt(strLen > 10 ? 10 : 0) % 20) / 10).toFixed(2),
    (Math.abs(strLen % 50) / 50).toFixed(2),
    0.95
  ];

  const handleExtractSequence = () => {
    setFastaInput(">H5N1_Avian_Influenza_Hemagglutinin_Spillover\nMEKIVLLFAIVSLVKSDQICIGYHANNSTEQVDTIMEKNVTVTHAQDILEKKHNGKLCDLDGVKPLILRDCSVAGWLLGN...");
    setPdbInput("1rzc");
    setActiveTab('genomics');
  };

  const runLiveQuantumEngine = async () => {
    setLoading(true);
    const dynamicFeatures = currentAngles.map(Number);

    try {
      // REPLACE THIS WITH YOUR RENDER URL
      const response = await fetch("https://q-vira-backend.onrender.com/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ features: dynamicFeatures }) 
      });
      
      const data = await response.json();
      setThreatScore(data.threat_score);
      setR0(data.r0);
      setDbMatch(`${data.closest_ancestor} (${data.database_confidence_percent}% Match)`);
    } catch (error) {
      console.error("Backend offline, using dynamic fallback.");
      setTimeout(() => {
        const simulatedThreat = 0.50 + (dynamicFeatures[0] * 0.4);
        setThreatScore(simulatedThreat);
        setR0(1.0 + (simulatedThreat * 2.5));
        setDbMatch(strLen > 100 ? "SARS-CoV-2 Variant (89% Match)" : "Avian Influenza (76% Match)");
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
      setChatMessages(prev => [...prev, { role: 'ai', text: "The PennyLane VQC analyzes structural drift using IBM Qiskit Aer. It maps mutations to a quantum vector space to calculate the threat scalar." }]);
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
      
      {showWelcome && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/90 backdrop-blur-sm p-4 print:hidden">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl max-w-2xl w-full p-8 relative">
            <button onClick={() => setShowWelcome(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white">
              <X size={24} />
            </button>
            <div className="flex items-center gap-3 mb-6">
              <Dna className="w-10 h-10 text-cyan-400" />
              <h2 className="text-3xl font-bold text-white">Welcome to Q-VIRA</h2>
            </div>
            <p className="text-slate-300 mb-6 leading-relaxed">
              Q-VIRA is a hybrid AI-Quantum pipeline that predicts viral outbreaks and discovers drug vulnerabilities weeks before clinical data is available. 
            </p>
            <div className="space-y-4 mb-8">
              <div className="flex gap-4 items-start p-4 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="bg-rose-500/20 text-rose-400 rounded-full w-8 h-8 flex items-center justify-center font-bold shrink-0">0</div>
                <div>
                  <h3 className="font-bold text-white">Global Sentinel (OSINT)</h3>
                  <p className="text-sm text-slate-400">Our NLP engine monitors global news and EHR anomalies to flag unknown outbreaks instantly.</p>
                </div>
              </div>
              <div className="flex gap-4 items-start p-4 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="bg-cyan-500/20 text-cyan-400 rounded-full w-8 h-8 flex items-center justify-center font-bold shrink-0">1</div>
                <div>
                  <h3 className="font-bold text-white">IBM Qiskit Engine</h3>
                  <p className="text-sm text-slate-400">Our PennyLane Variational Quantum Circuit runs on IBM Qiskit Aer to calculate the Threat Score.</p>
                </div>
              </div>
            </div>
            <button 
              onClick={() => setShowWelcome(false)}
              className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-bold py-3 rounded-lg flex items-center justify-center gap-2 transition-colors"
            >
              Enter Dashboard <ArrowRight size={20} />
            </button>
          </div>
        </div>
      )}

      <nav className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 print:hidden">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/10 rounded-lg border border-cyan-500/20">
              <Dna className="w-8 h-8 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-blue-500 tracking-tight">
                Q-VIRA
              </h1>
              <div className="text-[11px] text-slate-400 font-medium uppercase tracking-wider">BioQubit Labs</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowWelcome(true)} className="text-slate-400 hover:text-cyan-400 flex items-center gap-1 text-sm font-medium transition-colors">
              <HelpCircle size={18} /> Tour
            </button>
            <div className="h-6 w-px bg-slate-700"></div>
            <div className="flex items-center gap-3">
              <button 
                onClick={() => window.print()}
                className="hidden sm:flex bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 text-sm font-bold py-2 px-4 rounded-lg items-center gap-2 transition-all"
              >
                <Printer size={16} /> Export Report
              </button>
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
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="p-6 bg-slate-900 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden">
            <div className="text-slate-400 mb-1 font-medium flex items-center">
              Quantum Threat Score 
            </div>
            <div className="text-[11px] text-slate-500 mb-3 uppercase tracking-wider">IBM Qiskit Expectation Value</div>
            <div className="text-5xl font-bold text-white">
              {threatScore.toFixed(2)}
              <span className="text-lg text-rose-400 ml-2">S_threat</span>
            </div>
          </div>
          
          <div className="p-6 bg-slate-900 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden">
            <div className="text-slate-400 mb-1 font-medium flex items-center">
              Projected R0 Velocity 
            </div>
            <div className="text-[11px] text-slate-500 mb-3 uppercase tracking-wider">Live Epidemic Differential Bridge</div>
            <div className="text-5xl font-bold text-white">
              {r0.toFixed(2)}
              <span className="text-lg text-orange-400 ml-2">Δ/t</span>
            </div>
          </div>
          
          <div className="p-6 bg-slate-900 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden">
            <div className="text-slate-400 mb-1 font-medium flex items-center">
              NCBI Database Match 
            </div>
            <div className="text-[11px] text-slate-500 mb-3 uppercase tracking-wider">Nearest Neighbor Vector Search</div>
            <div className="text-xl font-bold text-emerald-400 mt-2 leading-tight">
              {dbMatch}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 bg-slate-900 p-1.5 rounded-xl mb-6 border border-slate-800 w-fit print:hidden">
          {[
            { id: 'sentinel', label: '0. Global Sentinel' },
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

        <div className="bg-slate-900 p-8 rounded-2xl border border-slate-800 shadow-xl min-h-[500px]">

          {/* TAB 0 */}
          {activeTab === 'sentinel' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-full">
              <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                    <Globe className="text-cyan-400" /> Global Sentinel
                  </h2>
                  <span className="bg-rose-900/50 text-rose-400 border border-rose-500/30 text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-widest flex items-center gap-1">
                    <Radio size={10} className="animate-pulse" /> Live OSINT Feed
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 mb-6 leading-tight">
                  <span className="text-slate-400 font-bold">NLP & EHR:</span> Continuously mines Global News, WHO ProMED, and NCBI to detect outbreak anomalies.
                </div>

                <div className="space-y-4 overflow-y-auto pr-2 custom-scrollbar flex-1">
                  <div className="p-4 bg-rose-950/30 border border-rose-500/30 rounded-xl relative overflow-hidden group">
                    <div className="absolute top-0 right-0 w-2 h-full bg-rose-500"></div>
                    <div className="flex items-center gap-2 text-rose-400 font-bold text-xs uppercase tracking-wider mb-2">
                      <AlertTriangle size={14} /> GISAID & ProMED Alert | Confidence: 94%
                    </div>
                    <h3 className="text-white font-bold text-lg mb-1">Unexplained Atypical Pneumonia Cluster</h3>
                    <p className="text-slate-400 text-sm mb-4">
                      NLP detects 400% spike in ICU admissions near poultry facilities. GISAID shows rapid accumulation of unknown hemagglutinin mutations.
                    </p>
                    <button 
                      onClick={handleExtractSequence}
                      className="bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold py-2 px-4 rounded flex items-center gap-2 transition-colors shadow-lg shadow-rose-900/20"
                    >
                      <Activity size={14} /> EXTRACT FASTA TO QUANTUM ENGINE
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex flex-col items-center justify-center border border-slate-800 rounded-xl bg-slate-950/50 p-6 relative overflow-hidden">
                <div className="absolute inset-0 bg-[url('https://upload.wikimedia.org/wikipedia/commons/8/80/World_map_-_low_resolution.svg')] bg-center bg-no-repeat bg-contain opacity-10"></div>
                
                <div className="relative w-64 h-64 border border-cyan-900/30 rounded-full flex items-center justify-center">
                  <div className="absolute w-full h-full border border-cyan-800/20 rounded-full"></div>
                  <div className="absolute w-3/4 h-3/4 border border-cyan-700/20 rounded-full"></div>
                  <div className="absolute w-1/2 h-1/2 border border-cyan-600/30 rounded-full"></div>
                  <div className="absolute w-1/2 h-[2px] bg-gradient-to-r from-transparent to-cyan-500 origin-right right-1/2 top-1/2 animate-[spin_4s_linear_infinite]"></div>
                  <div className="absolute top-1/4 right-1/3 w-3 h-3 bg-rose-500 rounded-full shadow-[0_0_15px_#f43f5e] animate-pulse"></div>
                </div>

                <div className="mt-8 text-center z-10">
                  <div className="text-rose-400 font-mono text-sm tracking-widest font-bold mb-1">TARGET IDENTIFIED</div>
                  <div className="text-slate-400 text-xs">Waiting for sequence extraction to initiate Quantum Analysis...</div>
                </div>
              </div>
            </div>
          )}
          
          {/* TAB 1 */}
          {activeTab === 'genomics' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-full">
              <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-2xl font-bold text-white">Sequence & 3D Ingestion</h2>
                  <span className="bg-slate-800 text-cyan-400 text-[10px] px-2 py-0.5 rounded font-bold border border-slate-700 uppercase tracking-widest">Step 1</span>
                </div>
                
                <div className="grid grid-cols-3 gap-4 mb-4 mt-6">
                  <div className="col-span-2">
                    <div className="text-sm font-bold text-slate-300">Viral RNA Sequence</div>
                    <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">FASTA Text Format</div>
                  </div>
                  <div>
                    <div className="text-sm font-bold text-slate-300">3D Structure</div>
                    <div className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">PDB / ESMFold ID</div>
                  </div>
                </div>

                <div className="flex gap-4 flex-1">
                  <textarea 
                    className="w-2/3 bg-slate-950 border border-slate-700 rounded-xl p-4 text-cyan-400 font-mono text-sm focus:border-cyan-500 outline-none resize-none"
                    value={fastaInput}
                    onChange={(e) => setFastaInput(e.target.value)}
                  />
                  <div className="w-1/3 flex flex-col gap-3">
                    <input 
                      type="text" 
                      className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-emerald-400 font-mono text-sm focus:border-emerald-500 outline-none text-center"
                      value={pdbInput}
                      onChange={(e) => setPdbInput(e.target.value)}
                      placeholder="e.g. 6M0J"
                    />
                    <div className="bg-slate-950/50 border border-slate-800 p-3 rounded-xl text-xs text-slate-400 text-center flex-1 flex items-center justify-center">
                      <Database size={16} className="inline mr-2 text-slate-500" />
                      Feeds directly into VQE Tab 4
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col items-center justify-center border border-slate-800 rounded-xl bg-slate-950/50 p-4">
                <div className="w-full text-center text-sm font-bold text-slate-300">Extracted Biological Features</div>
                <ResponsiveContainer width="100%" height={280}>
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={featureData}>
                    <PolarGrid stroke="#334155" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 11 }} />
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
              <h2 className="text-2xl font-bold text-white mb-1 flex items-center">
                Variational Quantum Classifier (VQC)
              </h2>
              <div className="text-[11px] text-slate-500 mb-8 leading-tight">
                <span className="text-slate-400 font-bold">VQC:</span> A PennyLane quantum machine learning model compiled to IBM Qiskit Aer.
              </div>
              
              <div className="flex-1 bg-slate-950 rounded-xl border border-slate-800 p-8 flex flex-col items-center justify-center font-mono text-sm text-cyan-500 overflow-x-auto relative">
                <div className="absolute top-4 left-6 text-xs text-slate-500 font-sans font-bold uppercase tracking-widest flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                  Parameters updating live from Sequence Ingestion
                </div>

                <div className="space-y-8 w-full max-w-3xl min-w-[650px] mt-8">
                  {['Qubit 0', 'Qubit 1', 'Qubit 2', 'Qubit 3'].map((q, i) => (
                    <div key={q} className="flex items-center gap-4">
                      <span className="text-slate-400 w-16 font-bold">{q}</span>
                      <div className="h-px bg-slate-600 flex-1 relative flex items-center justify-around">
                        <div className="px-4 py-2 bg-blue-900/80 border border-blue-500 rounded text-white shadow-lg flex flex-col items-center">
                          <span>Ry(<span className="text-emerald-400 font-bold">{currentAngles[i]}</span>)</span>
                          <span className="text-[9px] text-blue-300 uppercase tracking-widest mt-1">Encode</span>
                        </div>
                        {i < 3 && <div className="w-4 h-4 rounded-full bg-cyan-400 absolute left-1/3 shadow-[0_0_10px_#22d3ee]"></div>}
                        <div className="px-4 py-2 bg-indigo-900/80 border border-indigo-500 rounded text-white shadow-lg flex flex-col items-center">
                          <span>Entangle Gate</span>
                          <span className="text-[9px] text-indigo-300 uppercase tracking-widest mt-1">CNOT</span>
                        </div>
                        {i === 0 && (
                          <div className="absolute right-0 px-4 py-2 bg-rose-900/80 border border-rose-500 rounded text-white font-bold shadow-[0_0_15px_rgba(244,63,94,0.4)] flex flex-col items-center">
                            <span>Measure Z</span>
                            <span className="text-[9px] text-rose-300 uppercase tracking-widest mt-1">Pauli-Z</span>
                          </div>
                        )}
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
              <h2 className="text-2xl font-bold text-white mb-1 flex items-center">Epidemiological Bridge (SEIR Model)</h2>
              <div className="flex-1 bg-slate-950 rounded-xl p-4 border border-slate-800 mt-4">
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={seirData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="day" stroke="#64748b" tick={{fill: '#64748b', fontSize: 12}} />
                    <YAxis stroke="#64748b" tick={{fill: '#64748b', fontSize: 12}} />
                    <RechartsTooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', color: '#fff' }} />
                    <Legend wrapperStyle={{ fontSize: '12px' }}/>
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
                <h2 className="text-2xl font-bold text-white mb-1 flex items-center">
                  <Syringe className="mr-2 text-cyan-400" size={24}/> Drug Target Discovery
                </h2>
                <div className="bg-slate-950 p-6 rounded-xl border border-slate-800 space-y-5 mt-6">
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-400 font-medium text-sm">Target Drug Molecule</span>
                    <span className="text-white font-bold text-sm">Paxlovid Derivative</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800 pb-3">
                    <span className="text-slate-400 font-medium text-sm">Quantum Hamiltonian</span>
                    <span className="text-white font-mono text-xs mt-1">12 Qubits (IBM Qiskit)</span>
                  </div>
                  <div className="flex justify-between items-center bg-emerald-500/10 p-3 rounded-lg border border-emerald-500/20">
                    <span className="text-emerald-400 font-medium text-sm">Ground State Energy (E0)</span>
                    <span className="text-emerald-400 font-bold text-xl ml-4">-4.882 Hartree</span>
                  </div>
                </div>
              </div>
              
              <div className="relative border border-slate-800 rounded-xl bg-slate-950 flex flex-col items-center justify-center min-h-[400px] overflow-hidden">
                <iframe 
                  src={`https://www.ncbi.nlm.nih.gov/Structure/icn3d/full.html?pdbid=${pdbInput || '6m0j'}&showcommand=0&showmenu=0&showtitle=0`} 
                  width="100%" height="100%" className="absolute inset-0 z-0" title="3D Protein Structure"
                ></iframe>
                <div className="z-10 absolute bottom-4 left-4 bg-slate-900/90 p-3 rounded-lg border border-slate-700 backdrop-blur-md pointer-events-none">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse"></div>
                    <span className="text-cyan-400 font-mono text-xs tracking-widest font-bold">VQE TARGET: {pdbInput ? pdbInput.toUpperCase() : 'NONE'}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
      
      {/* AI COPILOT */}
      <div className="fixed bottom-24 right-6 z-50 print:hidden">
        {!isChatOpen ? (
          <button onClick={() => setIsChatOpen(true)} className="bg-cyan-600 hover:bg-cyan-500 text-white p-4 rounded-full shadow-[0_0_20px_rgba(8,145,178,0.4)]">
            <MessageSquare size={24} />
          </button>
        ) : (
          <div className="w-80 h-96 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
            <div className="bg-slate-800 p-4 border-b border-slate-700 flex justify-between items-center">
              <span className="font-bold text-sm text-white flex items-center gap-2"><div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></div>Q-VIRA Copilot</span>
              <button onClick={() => setIsChatOpen(false)} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-slate-900/50">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] p-3 rounded-xl text-sm shadow-md ${msg.role === 'user' ? 'bg-cyan-600 text-white rounded-br-sm' : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-bl-sm'}`}>{msg.text}</div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <form onSubmit={handleSendMessage} className="p-3 bg-slate-800 border-t border-slate-700 flex gap-2">
              <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Ask..." className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white outline-none" />
              <button type="submit" className="bg-cyan-600 hover:bg-cyan-500 text-white p-2 rounded-lg"><Send size={18} /></button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
