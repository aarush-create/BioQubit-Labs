import React, { useState, useEffect, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  AreaChart, Area
} from 'recharts';

/* Chart colours. Recharts needs literal values, not CSS vars, so the two
   themes are mirrored here from index.css and picked at render time. */
const PALETTES = {
  light: {
    ink: '#121617', ink2: '#4d5652', ink3: '#727b76',
    rule: '#bcc3b7', sheet: '#f6f7f3', paper: '#e8ebe4',
    assay: '#194955', flag: '#7e510e', alarm: '#8a2d28', ok: '#2a6340',
  },
  dark: {
    ink: '#e7ece9', ink2: '#9eaaa6', ink3: '#76827e',
    rule: '#2d373c', sheet: '#192026', paper: '#11161a',
    assay: '#74c6d8', flag: '#dca94c', alarm: '#e8786d', ok: '#67bd87',
  },
};

/* Honour the operating system on a first visit, remember the choice after.
   A judge opening this on a dark laptop should not get a white flash. */
const THEME_KEY = 'qvira-theme';
function initialTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* private mode, or storage blocked */ }
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark' : 'light';
}

/* Backend base URL. Set VITE_API_URL in Vercel (Project > Settings >
   Environment Variables) to the Render URL. Never hardcode it: an early build
   shipped a dead URL and silently fabricated numbers when it failed. */
const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const DOMAIN = { start: 331, end: 531 };

/* iCn3D renders on a white canvas. In dark mode we ask IT for a dark canvas
   rather than filtering the iframe: a CSS filter would also recolour the
   molecule, and iCn3D colours chains and residues to mean something. */
const viewerSrc = (pdb, theme, full) =>
  `https://www.ncbi.nlm.nih.gov/Structure/icn3d/full.html?pdbid=${pdb || '6m0j'}`
  + `&showcommand=0${full ? '' : '&showmenu=0'}&showtitle=0`
  + (theme === 'dark' ? '&bkgdcolor=black' : '');

/* The backend's keys are snake_case identifiers; these are what a reader
   should see on the model card. */
const BASELINE_NAME = {
  logistic_regression: 'Logistic regression',
  mlp: 'Neural network (MLP)',
  svm_rbf: 'Support vector machine (RBF)',
  majority_class: 'Always answer yes (chance)',
};

/* SEIR populations run to eight figures; raw ticks overflow the axis. */
const compact = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(n % 1e6 === 0 ? 0 : 1)}M`;
  if (Math.abs(n) >= 1e3) return `${Math.round(n / 1e3)}k`;
  return String(Math.round(n));
};

/* The trained domain drawn as a position ruler, with each scored substitution
   marked where it actually sits. This is what a virologist reads first: where
   in the receptor-binding domain the change landed. */
function DomainRuler({ mutations }) {
  const span = DOMAIN.end - DOMAIN.start;
  const at = (pos) => Math.min(100, Math.max(0, ((pos - DOMAIN.start) / span) * 100));
  const ticks = [350, 375, 400, 425, 450, 475, 500, 525];

  return (
    <div className="ruler" aria-hidden="true">
      <div className="ruler-line" />
      {ticks.map(t => <div key={t} className="ruler-tick" style={{ left: `${at(t)}%` }} />)}
      <div className="ruler-end" style={{ left: 0 }}>spike {DOMAIN.start}</div>
      <div className="ruler-end" style={{ right: 0 }}>{DOMAIN.end}</div>
      {mutations.map(m => {
        const pos = parseInt(String(m.mutation).slice(1, -1), 10);
        if (!Number.isFinite(pos)) return null;
        const out = m.in_trained_domain === false;
        const left = at(pos);
        const shift = left > 85 ? 'translateX(-90%)' : left < 6 ? 'translateX(-10%)' : 'translateX(-50%)';
        return (
          <React.Fragment key={m.mutation}>
            <div className={`ruler-mark${out ? ' is-out' : ''}`} style={{ left: `${left}%` }} />
            <div className={`ruler-flag${out ? ' is-out' : ''}`} style={{ left: `${left}%`, transform: shift }}>
              {m.mutation}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

const SunIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2v2.6M12 19.4V22M22 12h-2.6M4.6 12H2M19.07 4.93l-1.84 1.84M6.77 17.23l-1.84 1.84M19.07 19.07l-1.84-1.84M6.77 6.77L4.93 4.93" />
  </svg>
);

const MoonIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20.5 14.3A8.5 8.5 0 0 1 9.7 3.5a8.5 8.5 0 1 0 10.8 10.8z" />
  </svg>
);

function Bar({ value, flagged }) {
  const pct = Math.max(0, Math.min(1, Number(value) || 0)) * 100;
  return (
    <div className="bar">
      <div className={`bar-fill${flagged ? ' is-flagged' : ''}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const C = PALETTES[theme];
  const axis = { stroke: C.rule, tick: { fill: C.ink2, fontSize: 12 } };
  const tipStyle = {
    background: C.paper, border: `1px solid ${C.ink}`, borderRadius: 2,
    fontSize: 12, color: C.ink, fontFamily: 'IBM Plex Mono, monospace',
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* storage blocked */ }
  }, [theme]);

  const [activeTab, setActiveTab] = useState('sentinel');
  const [loading, setLoading] = useState(false);
  const [threatScore, setThreatScore] = useState(0.45);
  const [r0, setR0] = useState(1.2);
  const [showWelcome, setShowWelcome] = useState(true);
  const [apiError, setApiError] = useState(null);
  const [apiErrorKind, setApiErrorKind] = useState('offline');
  const [refList, setRefList] = useState([]);
  const [refName, setRefName] = useState('');
  const [mutationInput, setMutationInput] = useState('N501Y');
  const [result, setResult] = useState(null);
  const [seir, setSeir] = useState(null);
  const [health, setHealth] = useState(null);
  const [vqeResult, setVqeResult] = useState(null);
  const [vqeCurve, setVqeCurve] = useState(null);
  const [vqeBond, setVqeBond] = useState(0.7414);
  const [vqeBusy, setVqeBusy] = useState(false);
  const [vqeError, setVqeError] = useState(null);
  const [vqeView, setVqeView] = useState('single');
  const [sentinel, setSentinel] = useState(null);
  const [sentinelError, setSentinelError] = useState(null);
  const [sentinelBusy, setSentinelBusy] = useState(false);
  const [metrics, setMetrics] = useState(null);
  const [showMetrics, setShowMetrics] = useState(false);
  const [structureFullscreen, setStructureFullscreen] = useState(false);
  /* Render's free tier sleeps after ~15 min idle and takes ~50s to wake. A
     first-time visitor would otherwise see "backend unavailable" and conclude
     the site is broken. We retry, and say what is happening while we wait. */
  const [waking, setWaking] = useState(true);
  const [wakeSeconds, setWakeSeconds] = useState(0);

  const [pdbInput, setPdbInput] = useState('6m0j');
  const [isFolding, setIsFolding] = useState(false);

  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: 'I explain this dashboard using only the numbers the backend actually computed. Score a variant first, then ask me about the result, the circuit, or the SEIR assumptions.' }
  ]);
  const chatEndRef = useRef(null);

  /* The 16-state distribution comes from the BACKEND, computed by the same
     circuit that produces the score. An early build generated this curve with
     a sin/cos formula in JavaScript and labelled it the quantum state. */
  const quantumWaveformData = result?.state_distribution ?? [];

  const runLiveQuantumEngine = async () => {
    setLoading(true);
    setApiError(null);

    {
      /* Pick a reference structure for the 3D viewer. This is a LOOKUP, not a
         structure prediction — the interface says so. */
      setIsFolding(true);
      const known = { '6m0j': 1, '1rzc': 1, '5ire': 1, '6bp2': 1, '5kqv': 1, '7t9l': 1, '4kr0': 1 };
      setTimeout(() => {
        setPdbInput(known[pdbInput] ? pdbInput : '6m0j');
        setIsFolding(false);
      }, 400);
    }

    try {
      /* Send the SUBSTITUTIONS. The backend featurises them with real
         physicochemical descriptors; an early build sent a character-sum hash
         computed in the browser. */
      const res = await fetch(`${API}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reference_name: refName,
          mutations: mutationInput.split(/[\s,]+/).filter(Boolean)
        })
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        const err = new Error(detail.detail || `Backend returned ${res.status}`);
        /* 4xx means the backend answered and rejected the INPUT. Calling that
           "backend unavailable" blames the wrong thing. */
        err.isValidation = res.status >= 400 && res.status < 500;
        throw err;
      }

      const data = await res.json();
      setResult(data);
      setThreatScore(data.threat_score);

      /* R0 is a SCENARIO parameter chosen from the score, not a prediction.
         Range 0.8–4.0, stated so the mapping is auditable. */
      const scenarioR0 = 0.8 + data.threat_score * 3.2;
      setR0(scenarioR0);

      const seirRes = await fetch(`${API}/seir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ r0: scenarioR0, days: 180 })
      });
      if (seirRes.ok) setSeir(await seirRes.json());
    } catch (err) {
      setApiError(err.message || 'Could not reach the Q-VIRA backend.');
      setApiErrorKind(err.isValidation ? 'input' : 'offline');
      setResult(null);
      setSeir(null);
    } finally {
      setLoading(false);
      setIsFolding(false);
    }
  };

  const runVqe = async (mode) => {
    if (vqeBusy) return;
    setVqeView(mode === 'curve' ? 'curve' : 'single');
    setVqeBusy(true); setVqeError(null);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 20000);
    try {
      if (mode === 'curve') {
        const r = await fetch(`${API}/vqe/curve`, { signal: ctrl.signal });
        if (!r.ok) throw new Error((await r.json()).detail || `Error ${r.status}`);
        setVqeCurve(await r.json());
      } else {
        const r = await fetch(`${API}/vqe`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ bond_length: vqeBond, steps: 60 }),
          signal: ctrl.signal
        });
        if (!r.ok) throw new Error((await r.json()).detail || `Error ${r.status}`);
        setVqeResult(await r.json());
      }
    } catch (err) {
      setVqeError(err.name === 'AbortError'
        ? 'The VQE request timed out after 20 seconds.'
        : err.message);
    } finally {
      clearTimeout(timer);
      setVqeBusy(false);
    }
  };

  /* The backend refreshes the feed on a worker thread, so ask and then poll
     rather than holding a request open for an NCBI round trip. */
  const refreshSentinel = async () => {
    if (sentinelBusy) return;
    setSentinelBusy(true);
    try {
      await fetch(`${API}/sentinel/refresh`, { method: 'POST' });
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 3000));
        const r = await fetch(`${API}/sentinel`);
        if (!r.ok) break;
        const data = await r.json();
        setSentinel(data);
        if (!data.feed_status?.refreshing) break;
      }
    } catch {
      /* leave the current feed on screen; it is still the best data we have */
    } finally {
      setSentinelBusy(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    const q = chatInput.trim();
    if (!q || chatBusy) return;

    setChatMessages(prev => [...prev, { role: 'user', text: q }]);
    setChatInput('');
    setChatBusy(true);

    try {
      /* The model EXPLAINS; it never computes. We pass the current run's real
         numbers as context and the backend system prompt forbids inventing
         figures. An early version returned two hardcoded strings. */
      const res = await fetch(`${API}/copilot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          context: {
            prediction: result,
            seir_indicators: seir?.indicators ?? null,
            seir_parameters: seir?.parameters ?? null,
            backend_status: health
          }
        })
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Copilot error ${res.status}`);
      }
      const data = await res.json();
      setChatMessages(prev => [...prev, {
        role: 'ai', text: data.answer,
        meta: data.provider ? `${data.provider}${data.fell_back ? ', after the primary failed' : ''}` : null
      }]);
    } catch (err) {
      setChatMessages(prev => [...prev, {
        role: 'ai',
        text: `I could not reach the copilot (${err.message}). I won't guess at an answer.`
      }]);
    } finally {
      setChatBusy(false);
    }
  };

  useEffect(() => {
    if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatOpen]);

  /* Warm the backend on load, retrying until it answers. */
  useEffect(() => {
    let cancelled = false;
    let ticker = null;

    const loadEverything = (h) => {
      setHealth(h);
      setWaking(false);
      fetch(`${API}/metrics`).then(r => r.ok ? r.json() : null).then(setMetrics).catch(() => {});
      fetch(`${API}/references`)
        .then(r => r.json())
        .then(d => {
          setRefList(d.references || []);
          if (d.references?.length) {
            const firstValid = d.references.find(r => r.in_distribution) || d.references[0];
            setRefName(firstValid.name);
          }
        })
        .catch(() => setRefList([]));
      fetch(`${API}/sentinel`)
        .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(new Error(d.detail))))
        .then(setSentinel)
        .catch(e => setSentinelError(e.message));
    };

    const attempt = (n) => {
      if (cancelled) return;
      fetch(`${API}/`)
        .then(r => r.ok ? r.json() : Promise.reject(new Error(`status ${r.status}`)))
        .then(h => { if (!cancelled) loadEverything(h); })
        .catch(() => {
          if (!cancelled && n < 24) setTimeout(() => attempt(n + 1), 5000);
          else if (!cancelled) { setWaking(false); setHealth(null); }
        });
    };

    ticker = setInterval(() => setWakeSeconds(s => s + 1), 1000);
    attempt(0);
    return () => { cancelled = true; if (ticker) clearInterval(ticker); };
  }, []);

  /* Real SEIR curve from scipy on the backend. An early version was
     100 * R0^(day/8): a bare exponential that never peaks. */
  const seirData = seir?.curve ?? [];

  /* The four descriptors the model ACTUALLY uses, normalised to the fixed
     clamp ranges in mutation_features.py. Chosen by ablation, not intuition.
     ACE2 distance is inverted so "closer to the interface" reads as a longer
     spoke. */
  const d = result?.features?.descriptors;
  const featureData = d ? [
    { subject: 'BLOSUM62', A: ((d.blosum62 + 4) / 15) * 100, fullMark: 100 },
    { subject: 'WT volume', A: ((d.wt_volume - 60) / 168) * 100, fullMark: 100 },
    { subject: 'Δ volume', A: ((d.delta_volume + 170) / 340) * 100, fullMark: 100 },
    { subject: 'ACE2 proximity', A: Math.max(0, (1 - d.ace2_distance / 45) * 100), fullMark: 100 },
  ] : [];

  const feedStatus = sentinel?.feed_status;
  const outOfDomain = result?.distribution && !result.distribution.in_distribution;

  const TABS = [
    { id: 'sentinel', label: 'Surveillance feed' },
    { id: 'genomics', label: 'Score a variant' },
    { id: 'vqc', label: 'The circuit' },
    { id: 'seir', label: 'Epidemic scenario' },
    { id: 'vqe', label: 'Quantum chemistry' },
  ];

  return (
    <>
      {/* ------------------------------------------- structure, full screen */}
      {structureFullscreen && (
        <div className="overlay print-hidden" style={{ padding: 0, background: C.ink }}>
          <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
                          gap: '1rem', padding: '0.75rem 1.25rem', borderBottom: `1px solid ${C.ink2}`, color: C.paper }}>
              <div>
                <div className="mono" style={{ fontWeight: 600 }}>{(pdbInput || '6m0j').toUpperCase()}</div>
                <div className="small" style={{ color: C.ink3, maxWidth: '70ch' }}>
                  Experimentally solved structure from the RCSB PDB. Drag to rotate, scroll to zoom.
                  The ACE2 interface distances the model reads were measured from this complex.
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ color: C.paper, borderColor: C.ink2 }}
                      onClick={() => setStructureFullscreen(false)}>Close</button>
            </div>
            <iframe
              key={`fs-${pdbInput}-${theme}`}
              src={viewerSrc(pdbInput, theme, true)}
              style={{ flex: 1, width: '100%', border: 0 }}
              title="Protein structure, full screen"
            />
          </div>
        </div>
      )}

      {/* -------------------------------------------------------- model card */}
      {showMetrics && metrics && (
        <div className="overlay print-hidden" onClick={() => setShowMetrics(false)}>
          <div className="dialog custom-scrollbar" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
              <h2 style={{ fontSize: 'var(--t-lg)' }}>Model card</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowMetrics(false)}>Close</button>
            </div>
            <p className="small" style={{ marginTop: '0.4rem' }}>
              Held-out ROC-AUC on {metrics.n_test} rows the model never saw. Every model below was
              trained on identical features and an identical split.
            </p>

            <div className="lanes" style={{ marginTop: '1.25rem' }}>
              {Object.entries({
                'VQC (ours, 4 qubits)': metrics.vqc?.roc_auc,
                ...Object.fromEntries(Object.entries(metrics.classical_baselines_same_features || {})
                  .map(([k, v]) => [BASELINE_NAME[k] || k.replace(/_/g, ' '), v.roc_auc]))
              })
                .filter(([, v]) => typeof v === 'number')
                .sort((a, b) => b[1] - a[1])
                .map(([name, auc]) => (
                  <div key={name} className="lane" style={{ gridTemplateColumns: '1fr 6rem', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 'var(--t-sm)', marginBottom: '0.35rem' }}>{name}</div>
                      <Bar value={(auc - 0.5) / 0.5} />
                    </div>
                    <div className="mono" style={{ textAlign: 'right', color: C.assay }}>{auc.toFixed(4)}</div>
                  </div>
                ))}
            </div>

            <p className="note" style={{ marginTop: '1.25rem' }}>
              <b>Read AUC, not accuracy.</b> The dataset is 68% positive, so every model scores
              roughly 0.69–0.73 accuracy by mostly answering yes. Our quantum model places fourth of
              five. We report the gap rather than hide it.
            </p>

            <dl className="facts" style={{ marginTop: '1rem' }}>
              <div><dt>Circuit</dt><dd>{metrics.vqc?.n_qubits} qubits · {metrics.vqc?.n_layers} layers · {metrics.vqc?.n_parameters} parameters</dd></div>
              <div><dt>Ansatz</dt><dd>{metrics.vqc?.ansatz}</dd></div>
            </dl>
            <p className="small" style={{ marginTop: '0.75rem' }}>
              Split: {metrics.split}<br />Features: {metrics.features}
            </p>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------- welcome */}
      {showWelcome && (
        <div className="overlay print-hidden">
          <div className="dialog">
            <div className="small">BioQubit Labs · Q-Hack India 2026</div>
            <h2 style={{ fontSize: 'var(--t-xl)', letterSpacing: '-0.03em', margin: '0.4rem 0 1rem' }}>
              Which mutation should a lab test first?
            </h2>
            <p>
              Labs deposit new coronavirus sequences every day, and someone has to decide which
              mutations are worth bench time. Characterising one takes two to six weeks.
            </p>
            <p>
              Q-VIRA scores each substitution with a 4-qubit quantum classifier trained on laboratory
              measurements of 4,221 real mutations, and ranks them so the most promising are looked
              at first. It produces a triage order, not a verdict.
            </p>
            <p className="note is-flag" style={{ margin: '1.25rem 0' }}>
              <b>What this is not.</b> A research prototype, not a clinical or public-health tool. We
              claim no quantum advantage — the model card shows three classical baselines beating our
              circuit on identical features.
            </p>
            <button className="btn" onClick={() => setShowWelcome(false)}>Open the dashboard</button>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------- masthead */}
      <header className="masthead print-hidden">
        <div className="shell masthead-in">
          <div className="wordmark">Q<span>·</span>VIRA</div>
          <div className="masthead-sub">BioQubit Labs</div>
          <div className="masthead-right">
            <div className="theme-toggle" role="group" aria-label="Colour theme">
              <button type="button" aria-pressed={theme === 'light'} title="Light theme"
                      onClick={() => setTheme('light')}><SunIcon /><span>Light</span></button>
              <button type="button" aria-pressed={theme === 'dark'} title="Dark theme"
                      onClick={() => setTheme('dark')}><MoonIcon /><span>Dark</span></button>
            </div>

            {metrics?.vqc?.roc_auc && (
              <button className="btn btn-ghost btn-sm" onClick={() => setShowMetrics(true)}>
                Held-out AUC {metrics.vqc.roc_auc.toFixed(3)} · model card
              </button>
            )}
            <span className="small mono">
              {waking ? `waking backend · ${wakeSeconds}s`
                : health ? `backend online${health.model_trained ? ' · model loaded' : ' · untrained'}`
                : 'backend unreachable'}
            </span>
          </div>
        </div>
      </header>

      <main>
        {/* ------------------------------------------------------------ hero */}
        <section className="shell hero">
          <h1 className="hero-q">Which mutation should a lab test first?</h1>
          <p className="hero-sub">
            Q-VIRA scores one amino-acid substitution for whether the virus still binds human ACE2,
            and puts the results in order so limited bench capacity goes to the right change first.
          </p>

          <div className="readout">
            <div className="readout-top">
              {result ? (
                <>
                  <div>
                    <div className="readout-label">Binding score · {result.driver_mutation}</div>
                    <div className="readout-value">
                      {result.threat_score.toFixed(3)}
                      <span className="readout-err">± {result.threat_score_stderr.toFixed(3)}</span>
                    </div>
                  </div>
                  <div className="readout-meta">
                    {result.quantum.shots} shots · R₀ scenario {r0.toFixed(2)}
                    {seir && <> · peak day {seir.indicators.peak_day}</>}
                  </div>
                </>
              ) : (
                <div>
                  <div className="readout-label">Nothing scored yet</div>
                  <p className="muted" style={{ maxWidth: '62ch', marginTop: '0.15rem', marginBottom: 0 }}>
                    The ruler below is the window this model was trained on — 201 residues of the
                    receptor-binding domain. Score a substitution and it appears at its real
                    position, or read the ranked feed of today's deposits.
                  </p>
                </div>
              )}
            </div>

            <DomainRuler mutations={result?.mutations ?? []} />

            {result && (
              <div style={{ marginTop: '0.35rem' }}>
                <Bar value={result.threat_score} flagged={outOfDomain} />
              </div>
            )}

            {outOfDomain && (
              <p className="note is-flag" style={{ marginTop: '0.9rem' }}>
                <b>Outside the trained domain.</b> {result.distribution.note}
              </p>
            )}

            {result?.mutations?.length > 1 && (
              <div className="chips" style={{ marginTop: '0.9rem', alignItems: 'center' }}>
                {result.mutations.map(m => (
                  <span key={m.mutation}
                        className={`chip${m.in_trained_domain === false ? ' no-structure' : ' is-unique'}`}>
                    {m.mutation}<span className="s">{m.score.toFixed(3)}</span>
                  </span>
                ))}
                <span className="small">scored independently — epistasis is not modelled</span>
              </div>
            )}
          </div>
        </section>

        {/* ------------------------------------------------------------ tabs */}
        <div className="shell print-hidden" style={{ marginTop: '2.25rem' }}>
          <div className="rail" role="tablist">
            {TABS.map(t => (
              <button key={t.id} role="tab" aria-selected={activeTab === t.id}
                      onClick={() => setActiveTab(t.id)}>{t.label}</button>
            ))}
          </div>
        </div>

        <div className="shell">

          {/* ============================================= 1. SURVEILLANCE */}
          {activeTab === 'sentinel' && (
            <section className="panel">
              <div className="panel-head">
                <h2>Surveillance feed</h2>
                <p className="lede">
                  Recently deposited SARS-CoV-2 spike proteins from NCBI, aligned to the Wuhan-Hu-1
                  reference by local alignment (Smith–Waterman, BLOSUM62). Substitutions inside the
                  receptor-binding domain, spike sites 331–531, are scored by the trained circuit and
                  ranked.
                </p>
              </div>

              <section className="section">
                <h3>How to read this</h3>
                <p className="note">
                  Nearly every circulating virus already carries the same ~30 changes inherited from
                  Omicron, so those say nothing about which sample is new. Lanes are ranked by the
                  substitutions <b>unique to each deposit</b>, shown in colour below; shared ones stay
                  grey. <b>Read it as a worklist, not a verdict</b> — a high score means a lab should
                  look sooner, not that a variant is dangerous or will spread.
                </p>
              </section>

              {sentinelError && (
                <section className="section">
                  <p className="note is-alarm"><b>No feed.</b> {sentinelError}</p>
                </section>
              )}

              {sentinel && (
                <>
                  <section className="section">
                  <h3>This fetch</h3>
                  <dl className="facts">
                    <div>
                      <dt>Fetched</dt>
                      <dd>
                        {new Date(sentinel.fetched_at).toLocaleString()}
                        {feedStatus?.age_hours != null && (
                          <span className="small"> · {feedStatus.age_hours.toFixed(1)}h ago</span>
                        )}
                      </dd>
                    </div>
                    <div><dt>Sequences analysed</dt><dd>{sentinel.n_analysed}</dd></div>
                    <div><dt>Genuinely distinct</dt><dd>{sentinel.n_distinct_variants}</dd></div>
                    <div><dt>Unusable</dt><dd>{sentinel.n_skipped}</dd></div>
                    <div><dt>Region examined</dt><dd>spike {sentinel.rbd_window}</dd></div>
                    <div><dt>Shared by all</dt><dd>{sentinel.n_shared_mutations} mutations</dd></div>
                  </dl>

                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', flexWrap: 'wrap',
                                margin: '1rem 0 1.75rem' }}>
                    <button className="btn btn-ghost btn-sm" onClick={refreshSentinel}
                            disabled={sentinelBusy || feedStatus?.refreshing}>
                      {sentinelBusy || feedStatus?.refreshing ? 'Querying NCBI…' : 'Fetch the latest deposits'}
                    </button>
                    <span className="small" style={{ maxWidth: '62ch' }}>
                      {feedStatus?.auto_refresh
                        ? `The feed refreshes itself once it passes ${feedStatus.max_age_hours}h old. NCBI rate-limits queries, so a fetch runs in the background and the page is served from memory — the timestamp is the real fetch time, never a page-load time.`
                        : 'NCBI rate-limits queries, so deposits are fetched ahead of time. The timestamp is the real fetch time.'}
                    </span>
                  </div>

                  {feedStatus?.last_error && (
                    <p className="note is-flag">
                      <b>The last refresh failed.</b> {feedStatus.last_error} — showing the previous feed.
                    </p>
                  )}
                  </section>

                  <section className="section">
                  <h3>Ranked deposits</h3>
                  <p className="note is-flag" style={{ marginBottom: '1.25rem' }}>
                    <b>Why some lanes are flagged.</b> The model was trained on <i>single</i> mutants
                    of Wuhan-Hu-1. A deposit carrying tens of co-occurring RBD substitutions is scored
                    one substitution at a time, which ignores epistasis — and epistasis is large in
                    this domain. Those lanes are marked below and their scores are weaker evidence.
                  </p>

                  <div className="lanes">
                    {sentinel.records.filter(r => r.max_score !== null).map(r => (
                      <article key={r.accession} className="lane">
                        <div>
                          <div className="lane-acc">{r.accession}</div>
                          {r.identical_count > 1 && (
                            <div className="small">×{r.identical_count} identical deposits</div>
                          )}
                        </div>

                        <div className="stack-sm">
                          <div className="lane-desc" title={r.description}>{r.description}</div>
                          <div className="chips">
                            {[...r.distinguishing_mutations,
                              ...r.mutations.filter(m => !r.distinguishing_mutations.some(x => x.mutation === m.mutation))
                             ].slice(0, 12).map(m => {
                              const unique = r.distinguishing_mutations.some(x => x.mutation === m.mutation);
                              return (
                                <span key={m.mutation}
                                      title={m.has_structure === false
                                        ? 'Outside the 6M0J crystal structure — the distance is a far-field fallback, not a measurement'
                                        : undefined}
                                      className={`chip${unique ? ' is-unique' : ''}${m.has_structure === false ? ' no-structure' : ''}`}>
                                  {m.mutation}{m.has_structure === false && '*'}
                                  <span className="s">{m.score.toFixed(2)}</span>
                                </span>
                              );
                            })}
                            {r.mutations.length > 12 && (
                              <span className="small">+{r.mutations.length - 12} more</span>
                            )}
                          </div>
                          <div className="small">
                            {r.n_distinguishing} unique to this deposit ·{' '}
                            {r.n_without_structure > 0 && <>{r.n_without_structure} marked * sit outside the crystal structure and are excluded from ranking · </>}
                            {r.rbd_substitutions} RBD substitution{r.rbd_substitutions === 1 ? '' : 's'} scored ·
                            RBD coverage {(r.rbd_coverage * 100).toFixed(0)}% · {r.sequence_length} residues
                          </div>
                          {r.high_divergence && (
                            <div className="small" style={{ color: 'var(--flag)' }}>
                              High divergence — {r.rbd_substitutions} co-occurring RBD substitutions,
                              so these scores are weaker evidence than a single-substitution score.
                            </div>
                          )}
                        </div>

                        <div className="lane-score">
                          <div className="v">
                            {r.top_distinguishing_score !== null ? r.top_distinguishing_score.toFixed(3) : '—'}
                          </div>
                          <div className="k">
                            {r.top_distinguishing ? `top unique · ${r.top_distinguishing}` : 'nothing unique'}
                          </div>
                          <div style={{ marginTop: '0.45rem' }}>
                            <Bar value={r.top_distinguishing_score ?? 0} flagged={r.high_divergence} />
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>

                  {sentinel.records.filter(r => r.max_score === null).length > 0 && (
                    <p className="small" style={{ marginTop: '1rem' }}>
                      {sentinel.records.filter(r => r.max_score === null).length} further sequences had
                      no substitutions inside the RBD — a normal result, shown for completeness rather
                      than filtered away.
                    </p>
                  )}

                  </section>

                  <section className="section">
                    <h3>Caveats</h3>
                    <p className="section-lede">
                      Every limit the pipeline knows about, surfaced rather than filtered away.
                    </p>
                    <ul className="small" style={{ paddingLeft: '1.1rem', maxWidth: '72ch', margin: 0 }}>
                      {sentinel.caveats.map((c, i) => <li key={i} style={{ marginBottom: '0.45rem' }}>{c}</li>)}
                    </ul>
                  </section>
                </>
              )}
            </section>
          )}

          {/* =================================================== 2. SCORE */}
          {activeTab === 'genomics' && (
            <section className="panel">
              <div className="panel-head">
                <h2>Score a variant</h2>
                <p className="lede">
                  Pick a reference, then list substitutions in standard notation — wild-type residue,
                  position, mutant residue, as in N501Y. The wild-type letter is checked against the
                  reference, so a wrong one is rejected rather than scored at the wrong position.
                </p>
              </div>

              <div className="cols cols-2">
                <div>
                  <section className="section">
                  <h3>Input</h3>
                  <div className="stack">
                  <div>
                    <label className="field" htmlFor="ref">Reference sequence</label>
                    <select id="ref" value={refName} onChange={e => setRefName(e.target.value)}>
                      {refList.length === 0 && <option value="">No references loaded</option>}
                      {refList.filter(r => r.in_distribution).map(r => (
                        <option key={r.name} value={r.name}>{r.name} ({r.length} aa)</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="field" htmlFor="muts">Substitutions</label>
                    <input id="muts" type="text" className="mono" value={mutationInput}
                           onChange={e => setMutationInput(e.target.value)} placeholder="N501Y E484K" />
                    <p className="small" style={{ marginTop: '0.4rem' }}>
                      Space or comma separated. The model is trained on the receptor-binding domain
                      only — spike sites 331–531. Positions outside that window are flagged, not hidden.
                    </p>
                  </div>

                  <button className="btn" onClick={runLiveQuantumEngine} disabled={loading || !refName}>
                    {loading ? 'Scoring…' : 'Score these substitutions'}
                  </button>

                  {apiError && (
                    <p className={`note ${apiErrorKind === 'input' ? 'is-flag' : 'is-alarm'}`}>
                      <b>{apiErrorKind === 'input' ? 'Rejected.' : 'Backend unreachable.'}</b> {apiError}
                    </p>
                  )}

                  {refList.some(r => !r.in_distribution) && (
                    <p className="note">
                      {refList.filter(r => !r.in_distribution).length} other reference proteins are
                      loaded — MERS, Ebola, Nipah, influenza and others — but are <b>not selectable</b>.
                      The model is trained only on SARS-CoV-2 RBD binding to human ACE2, and those
                      viruses use different receptors. Offering them would imply a validity we have
                      not measured.
                    </p>
                  )}

                  <p className="note">
                    <b>Why there is no sequence box.</b> The model scores <i>substitutions</i>, not
                    whole sequences: it takes a reference protein and the residue changes applied to
                    it. Pasting a raw FASTA would not tell it which positions changed. The reference
                    sequences are fetched from NCBI by the backend.
                  </p>
                  </div>
                  </section>
                </div>

                <div style={{ minWidth: 0 }}>
                  <section className="section">
                  <h3>What the circuit reads</h3>
                  <p className="section-lede">
                    One descriptor per qubit, normalised to the clamp ranges in the featuriser.
                    Chosen by ablation: eight descriptors scored worse than these four.
                  </p>
                  <div className="figure">
                    <div style={{ width: '100%', height: 230, minWidth: 0 }}>
                      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                        <RadarChart cx="50%" cy="50%" outerRadius="72%" data={featureData}>
                          <PolarGrid stroke={C.rule} />
                          <PolarAngleAxis dataKey="subject" tick={{ fill: C.ink2, fontSize: 11 }} />
                          <PolarRadiusAxis angle={30} domain={[0, 120]} tick={false} axisLine={false} />
                          <Radar dataKey="A" stroke={C.assay} fill={C.assay} fillOpacity={0.22} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  </section>

                  <section className="section">
                  <h3>Reference structure</h3>
                  <div className="figure viewer-shell" style={{ padding: 0, overflow: 'hidden' }}>
                    {isFolding ? (
                      <div style={{ height: 280, display: 'grid', placeItems: 'center', textAlign: 'center', padding: '1rem' }}>
                        <div>
                          <div className="mono" style={{ fontSize: 'var(--t-sm)' }}>Loading reference structure</div>
                          <div className="small" style={{ marginTop: '0.3rem' }}>
                            Fetching a solved PDB entry. No structure prediction is performed.
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ position: 'relative', height: 280, overflow: 'hidden' }}>
                        <iframe
                          key={`${pdbInput}-${theme}`}
                          src={viewerSrc(pdbInput, theme, false)}
                          title="Protein structure"
                          style={{
                            /* Render the frame LARGER and crop it rather than
                               transform: scale(), which stretches the finished
                               bitmap. iCn3D fits the molecule to its canvas, so
                               a bigger canvas draws it at more pixels. */
                            position: 'absolute', border: 0,
                            width: '165%', height: '165%', left: '-32.5%', top: '-32.5%',
                          }}
                        />
                        <button className="btn btn-ghost btn-sm"
                                style={{ position: 'absolute', top: 8, right: 8, background: C.paper }}
                                onClick={() => setStructureFullscreen(true)}>Expand</button>
                      </div>
                    )}
                    <div className="figure-cap" style={{ padding: '0.75rem 1rem', marginTop: 0 }}>
                      <span className="mono">{(pdbInput || '6m0j').toUpperCase()}</span> — the solved
                      SARS-CoV-2 RBD bound to human ACE2, the exact interaction this model scores. The
                      interface distances the circuit reads were measured from this complex. Solved
                      structures, not predictions.
                    </div>
                  </div>
                  </section>
                </div>
              </div>
            </section>
          )}

          {/* ================================================= 3. CIRCUIT */}
          {activeTab === 'vqc' && (
            <section className="panel">
              <div className="panel-head">
                <h2>The circuit</h2>
                <p className="lede">
                  |ψ|² across the 16 basis states of the 4-qubit register, returned by the same
                  circuit that produces the score. Data re-uploading ansatz; the score is the
                  expectation value of Pauli-Z on the first qubit.
                </p>
              </div>

              <div className="figure">
                {quantumWaveformData.length === 0 ? (
                  <div style={{ height: 320, display: 'grid', placeItems: 'center' }}>
                    <span className="muted">Score a variant to compute the state distribution.</span>
                  </div>
                ) : (
                  <div style={{ width: '100%', height: 340, minWidth: 0 }}>
                    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                      <AreaChart data={quantumWaveformData} margin={{ top: 8, right: 8, bottom: 28, left: 0 }}>
                        <defs>
                          <linearGradient id="prob" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={C.assay} stopOpacity={0.35} />
                            <stop offset="100%" stopColor={C.assay} stopOpacity={0.03} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={C.rule} strokeDasharray="2 4" vertical={false} />
                        <XAxis dataKey="state" stroke={C.rule}
                               tick={{ fill: C.ink2, fontSize: 10, fontFamily: 'IBM Plex Mono, monospace' }}
                               interval={0} angle={-45} textAnchor="end" />
                        <YAxis {...axis} tickFormatter={v => `${v}%`} />
                        <RTooltip contentStyle={tipStyle} formatter={v => [`${v}%`, '|ψ|²']} />
                        <Area type="monotone" dataKey="probability" stroke={C.assay} strokeWidth={2}
                              fill="url(#prob)" animationDuration={300} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <div className="figure-cap">
                  Measured on the backend, not generated in the browser.
                </div>
              </div>
            </section>
          )}

          {/* ================================================ 4. SCENARIO */}
          {activeTab === 'seir' && (
            <section className="panel">
              <div className="panel-head">
                <h2>Epidemic scenario</h2>
                <p className="lede">
                  Deterministic SEIR, integrated with scipy <code>solve_ivp</code>. Homogeneous
                  mixing, constant R₀, no interventions. R₀ is mapped from the binding score across
                  0.8–4.0, so the scenario is auditable — it is not a forecast.
                </p>
              </div>

              {seir ? (
                <>
                  <section className="section">
                  <h3>Parameters</h3>
                  <dl className="facts">
                    <div><dt>β</dt><dd>{seir.parameters.beta}</dd></div>
                    <div><dt>σ</dt><dd>{seir.parameters.sigma}</dd></div>
                    <div><dt>γ</dt><dd>{seir.parameters.gamma}</dd></div>
                    <div><dt>R₀</dt><dd>{r0.toFixed(2)}</dd></div>
                    <div><dt>Peak day</dt><dd>{seir.indicators.peak_day}</dd></div>
                    <div><dt>Attack rate</dt><dd>{seir.indicators.attack_rate_percent}%</dd></div>
                    <div><dt>Herd-immunity threshold</dt><dd>{seir.indicators.herd_immunity_threshold_percent}%</dd></div>
                    <div><dt>Capacity breach</dt><dd>{seir.indicators.capacity_breach_day ?? 'none'}</dd></div>
                  </dl>
                  </section>

                  <section className="section">
                  <h3>Curve</h3>
                  <div className="figure">
                    <div style={{ width: '100%', height: 360, minWidth: 0 }}>
                      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                        <LineChart data={seirData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                          <CartesianGrid stroke={C.rule} strokeDasharray="2 4" />
                          <XAxis dataKey="day" {...axis}
                                 label={{ value: 'day', position: 'insideBottomRight', offset: -2, fill: C.ink2, fontSize: 11 }} />
                          <YAxis {...axis} width={48} tickFormatter={compact} />
                          <RTooltip contentStyle={tipStyle} formatter={v => compact(v)} />
                          <Legend wrapperStyle={{ fontSize: 12 }} />
                          <Line type="monotone" dataKey="susceptible" stroke={C.ink3} strokeWidth={1.5} dot={false} name="Susceptible" />
                          <Line type="monotone" dataKey="exposed" stroke={C.flag} strokeWidth={1.5} dot={false} name="Exposed" />
                          <Line type="monotone" dataKey="infected" stroke={C.alarm} strokeWidth={2.5} dot={false} name="Infected" />
                          <Line type="monotone" dataKey="recovered" stroke={C.ok} strokeWidth={1.5} dot={false} name="Recovered" />
                          <Line type="step" dataKey="capacity" stroke={C.ink} strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="Hospital capacity" />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  </section>
                </>
              ) : (
                <p className="muted">Score a variant to run the scenario.</p>
              )}
            </section>
          )}

          {/* =============================================== 5. CHEMISTRY */}
          {activeTab === 'vqe' && (
            <section className="panel">
              <div className="panel-head">
                <h2>Quantum chemistry</h2>
                <p className="lede">
                  A real variational quantum eigensolver on H₂ (STO-3G, Jordan–Wigner), checked
                  against exact diagonalization of the same Hamiltonian.
                </p>
              </div>

              <div className="cols cols-2">
                <div style={{ minWidth: 0 }}>
                  <section className="section">
                  <h3>Run the eigensolver</h3>
                  <div className="stack">
                  <div className="sheet stack">
                    <div>
                      <label className="field" htmlFor="bond">
                        Bond length <span className="mono">{vqeBond.toFixed(4)} Å</span>
                      </label>
                      <input id="bond" type="range" min="0.3" max="2.4" step="0.01" value={vqeBond}
                             onChange={e => setVqeBond(parseFloat(e.target.value))} />
                      <div className="small" style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>0.3 Å</span><span>equilibrium ≈ 0.74 Å</span><span>2.4 Å</span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className="btn btn-ghost" style={{ flex: 1 }} aria-pressed={vqeView === 'single'}
                              onClick={() => runVqe('single')} disabled={vqeBusy}>
                        {vqeBusy && vqeView === 'single' ? 'Loading…' : 'This bond length'}
                      </button>
                      <button className="btn btn-ghost" style={{ flex: 1 }} aria-pressed={vqeView === 'curve'}
                              onClick={() => runVqe('curve')} disabled={vqeBusy}>
                        {vqeBusy && vqeView === 'curve' ? 'Loading…' : 'Full curve'}
                      </button>
                    </div>

                    {vqeError && <p className="note is-alarm"><b>Failed.</b> {vqeError}</p>}

                    {vqeView === 'single' && vqeResult && (
                      <div className="stack-sm">
                        <dl className="facts">
                          <div><dt>Eigensolver energy</dt><dd>{Number(vqeResult.vqe_energy ?? 0).toFixed(6)} Ha</dd></div>
                          <div><dt>Exact, diagonalized</dt><dd>{Number(vqeResult.exact_energy ?? 0).toFixed(6)} Ha</dd></div>
                        </dl>
                        <p className={`note ${vqeResult.within_chemical_accuracy ? '' : 'is-flag'}`}>
                          <b>Error {Number(vqeResult.absolute_error ?? 0).toExponential(2)} Ha</b> —{' '}
                          {vqeResult.within_chemical_accuracy ? 'within' : 'outside'} chemical accuracy (1.6e-3).
                        </p>
                        <div className="small">
                          {vqeResult.n_qubits} qubits · {vqeResult.n_parameters} parameters ·{' '}
                          {vqeResult.n_pauli_terms} Pauli terms
                          {vqeResult.runtime_seconds ? ` · ${vqeResult.runtime_seconds}s` : ''} ·
                          correlation energy {vqeResult.correlation_energy?.toFixed(6)} Ha recovered
                          beyond Hartree–Fock
                        </div>
                        <div style={{ width: '100%', height: 170, minWidth: 0 }}>
                          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                            <LineChart data={vqeResult.convergence || []}>
                              <CartesianGrid stroke={C.rule} strokeDasharray="2 4" />
                              <XAxis dataKey="step" stroke={C.rule} tick={{ fill: C.ink2, fontSize: 10 }} />
                              <YAxis stroke={C.rule} tick={{ fill: C.ink2, fontSize: 10 }} domain={['auto', 'auto']} />
                              <RTooltip contentStyle={tipStyle} />
                              <Line type="monotone" dataKey="energy" stroke={C.assay} strokeWidth={2} dot={false} name="Energy" />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <div className="figure-cap">Optimiser convergence, Ha against step.</div>
                      </div>
                    )}

                    {vqeView === 'curve' && vqeCurve && (
                      <div className="stack-sm">
                        <div className="small">
                          Dissociation curve — maximum error{' '}
                          <span className="mono">{Number(vqeCurve.max_absolute_error ?? 0).toExponential(2)} Ha</span>
                          {vqeCurve.all_within_chemical_accuracy && ', all within chemical accuracy'}
                        </div>
                        <div style={{ width: '100%', height: 200, minWidth: 0 }}>
                          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                            <LineChart data={vqeCurve.points || []}>
                              <CartesianGrid stroke={C.rule} strokeDasharray="2 4" />
                              <XAxis dataKey="bond_length" stroke={C.rule} tick={{ fill: C.ink2, fontSize: 10 }} />
                              <YAxis stroke={C.rule} tick={{ fill: C.ink2, fontSize: 10 }} domain={['auto', 'auto']} />
                              <RTooltip contentStyle={tipStyle} />
                              <Legend wrapperStyle={{ fontSize: 11 }} />
                              <Line type="monotone" dataKey="exact_energy" stroke={C.ok} strokeWidth={2.5} dot={false} name="Exact" />
                              <Line type="monotone" dataKey="vqe_energy" stroke={C.assay} strokeWidth={1.5} strokeDasharray="4 3" dot={{ r: 2 }} name="Eigensolver" />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <div className="small">
                          Equilibrium at {vqeCurve.equilibrium_bond_length} Å; experimental value{' '}
                          {vqeCurve.experimental_bond_length} Å.
                        </div>
                      </div>
                    )}
                  </div>

                  <p className="note">
                    <b>Served from a stored run.</b> The optimisation is real but was performed ahead
                    of time with <code>build_vqe_data.py</code> and is served instantly — running a
                    60-step optimisation inside a web request tied up the server. Reproduce any point
                    with <code>notebooks/vqe_h2.ipynb</code>.
                  </p>
                  </div>
                  </section>
                </div>

                <div style={{ minWidth: 0 }}>
                  <section className="section">
                  <h3>What is actually simulated</h3>
                  <p className="section-lede">
                    The eigensolver runs on H₂ — two atoms. The protein this project scores is
                    elsewhere in the app. Keeping those apart is the point of this panel.
                  </p>
                  <div className="stack">

                  <div className="sheet">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem' }}>
                      <b>H₂, simulated here</b>
                      <span className="mono" style={{ color: C.assay, fontSize: 'var(--t-md)' }}>4 qubits</span>
                    </div>
                    <p className="small" style={{ marginTop: '0.4rem' }}>
                      Two electrons, four spin-orbitals, STO-3G. Small enough that we can diagonalize
                      the Hamiltonian exactly and prove the eigensolver's answer is right.
                    </p>
                  </div>

                  <div className="divide"><span>~25,000× more qubits</span></div>

                  <div className="sheet">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem' }}>
                      <b>A protein–drug binding pocket</b>
                      <span className="mono" style={{ color: C.flag, fontSize: 'var(--t-md)' }}>~10⁵ qubits</span>
                    </div>
                    <p className="small" style={{ marginTop: '0.4rem' }}>
                      Thousands of atoms, before error correction. Not a near-term quantum target.
                      Any demo claiming a quantum-computed protein–ligand binding energy is doing
                      something else.
                    </p>
                  </div>

                  <p className="note">
                    <b>Roadmap, in order.</b> H₂ and LiH against exact diagonalization, which is done
                    → small active spaces of a ligand fragment against CASCI → a quantum active space
                    embedded in a classical DFT/MM calculation. Binding free energies stay out of reach.
                  </p>
                  </div>
                  </section>
                </div>
              </div>
            </section>
          )}
        </div>

        <footer className="print-hidden" style={{ borderTop: `1px solid ${C.rule}` }}>
          <div className="shell" style={{ padding: '1.5rem var(--gut) 3rem' }}>
            <p className="small" style={{ maxWidth: '72ch' }}>
              BioQubit Labs · Q-Hack India 2026, Quantum Biotech &amp; Chemistry. Trained on Starr et
              al. (2020) deep mutational scanning of the SARS-CoV-2 receptor-binding domain;
              interface distances from PDB 6M0J. A research prototype, not a clinical or
              public-health tool.
            </p>
          </div>
        </footer>
      </main>

      {/* ------------------------------------------------------------ copilot */}
      <div className="print-hidden">
        {!isChatOpen ? (
          <button className="btn" style={{ position: 'fixed', right: '1.25rem', bottom: '1.25rem', zIndex: 50 }}
                  onClick={() => setIsChatOpen(true)}>Ask about this run</button>
        ) : (
          <div className="copilot">
            <div className="copilot-head">
              <div>
                <b style={{ fontSize: 'var(--t-sm)' }}>Copilot</b>
                <div className="small">
                  {health?.copilot_providers?.length
                    ? `grounded in this run · ${health.copilot_providers.join(' → ')}`
                    : 'grounded in this run'}
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setIsChatOpen(false)}>Close</button>
            </div>
            <div className="copilot-log custom-scrollbar">
              {chatMessages.map((m, i) => (
                <div key={i} className={`msg ${m.role === 'user' ? 'msg-you' : 'msg-ai'}`}>
                  {m.text}
                  {m.meta && <div className="msg-meta">answered by {m.meta}</div>}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <form className="copilot-form" onSubmit={handleSendMessage}>
              <input type="text" value={chatInput} onChange={e => setChatInput(e.target.value)}
                     placeholder={health && health.copilot_enabled === false
                       ? 'Copilot is not configured'
                       : (chatBusy ? 'Thinking…' : 'Ask about the score, the circuit, the scenario…')}
                     disabled={chatBusy || (health && health.copilot_enabled === false)} />
              <button className="btn btn-sm" type="submit" disabled={chatBusy}>Send</button>
            </form>
          </div>
        )}
      </div>
    </>
  );
}
