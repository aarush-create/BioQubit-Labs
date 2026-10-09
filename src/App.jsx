import React, { useState, useEffect, useRef } from 'react';
import { GLOSSARY, glossaryByGroup } from './glossary';
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


/* The 20 residues, with the property class that actually drives binding.
   Colouring by class is standard in sequence viewers (Clustal and friends) —
   it is how a biologist reads a mutation at a glance, so it belongs here. */
const RESIDUES = {
  A: ['Alanine', 'hydrophobic'],    V: ['Valine', 'hydrophobic'],
  L: ['Leucine', 'hydrophobic'],    I: ['Isoleucine', 'hydrophobic'],
  M: ['Methionine', 'hydrophobic'], F: ['Phenylalanine', 'aromatic'],
  W: ['Tryptophan', 'aromatic'],    Y: ['Tyrosine', 'aromatic'],
  P: ['Proline', 'special'],        G: ['Glycine', 'special'],
  C: ['Cysteine', 'special'],       S: ['Serine', 'polar'],
  T: ['Threonine', 'polar'],        N: ['Asparagine', 'polar'],
  Q: ['Glutamine', 'polar'],        D: ['Aspartate', 'acidic'],
  E: ['Glutamate', 'acidic'],       K: ['Lysine', 'basic'],
  R: ['Arginine', 'basic'],         H: ['Histidine', 'basic'],
};

/* "N501Y" -> { wt: 'N', pos: 501, mut: 'Y' } */
function parseMutation(code) {
  const m = /^([A-Z])(\d+)([A-Z])$/.exec(String(code || '').trim());
  return m ? { wt: m[1], pos: parseInt(m[2], 10), mut: m[3] } : null;
}

const klass = (letter) => (RESIDUES[letter] || [null, 'polar'])[1];

/* The substitution, shown the way a sequence viewer shows it: both residues in
   their class colours, with what they actually are underneath. */
function ResidueSwap({ code }) {
  const p = parseMutation(code);
  if (!p) return null;
  const wtName = (RESIDUES[p.wt] || ['unknown'])[0];
  const mutName = (RESIDUES[p.mut] || ['unknown'])[0];
  return (
    <div className="swap">
      <div className={`swap-aa aa-${klass(p.wt)}`}>
        <span className="swap-letter">{p.wt}</span>
        <span className="swap-name">{wtName}</span>
      </div>
      <div className="swap-arrow" aria-hidden="true">
        <span className="swap-site">site {p.pos}</span>
      </div>
      <div className={`swap-aa aa-${klass(p.mut)}`}>
        <span className="swap-letter">{p.mut}</span>
        <span className="swap-name">{mutName}</span>
      </div>
    </div>
  );
}

/* A score that lands rather than appears. One orchestrated moment, not a page
   full of them. */
function CountUp({ value, decimals = 3 }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const a = from.current, b = value, ms = 520;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setShown(b); from.current = b; return;
    }
    const start = performance.now();
    let raf;
    const tick = (t) => {
      const k = Math.min(1, (t - start) / ms);
      setShown(a + (b - a) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = b;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <>{shown.toFixed(decimals)}</>;
}

/* Reveals its children once, the first time they scroll into view. One
   orchestrated moment per page, not an effect on every section. */
function Reveal({ children, delay = 0 }) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver !== 'function') { setShown(true); return; }
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setShown(true); io.disconnect(); }
    }, { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className={`reveal${shown ? ' is-in' : ''}`}
         style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------- a term */
/* Jargon the page cannot avoid, with its plain-English meaning one tap away.
   A `title` tooltip would have been a line of code, but it does not exist on a
   phone and cannot hold a link — so this is a real popover: hover opens it on a
   mouse, tap opens it on a touch screen, and either way it carries the sentence
   and a way out to the source. */
function Term({ id, children }) {
  const g = GLOSSARY[id];
  const ref = useRef(null);
  const [box, setBox] = useState(null);
  const open = box !== null;

  /* A term whose entry was deleted renders as ordinary text rather than as a
     control that explains nothing. */
  if (!g) return <>{children}</>;

  const place = () => {
    const r = ref.current.getBoundingClientRect();
    const w = Math.min(21 * 16, window.innerWidth - 24);
    const left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12));
    /* below the word unless the room is above it */
    const below = window.innerHeight - r.bottom > 190 || r.top < 190;
    setBox({ w, left, top: below ? r.bottom + 10 : null,
             bottom: below ? null : window.innerHeight - r.top + 10 });
  };
  const close = () => setBox(null);

  useEffect(() => {
    if (!open) return;
    const onKey = e => e.key === 'Escape' && close();
    window.addEventListener('keydown', onKey);
    /* the popover is positioned once, so it has to go away when the thing it
       points at moves */
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  const hoverable = typeof window !== 'undefined'
    && window.matchMedia?.('(hover: hover)').matches;

  return (
    <>
      <button type="button" ref={ref} className="term" aria-expanded={open}
              onClick={() => (open ? close() : place())}
              onMouseEnter={() => hoverable && place()}
              onMouseLeave={() => hoverable && close()}>
        {children ?? g.term}
      </button>
      {open && (
        <span className="term-pop" role="tooltip"
              style={{ left: box.left, width: box.w,
                       top: box.top ?? undefined, bottom: box.bottom ?? undefined }}>
          <b className="term-pop-h">{g.term}</b>
          <span className="term-pop-b">{g.plain}</span>
          <a className="term-pop-a" href={g.href} target="_blank" rel="noopener noreferrer">
            {g.source} &#8599;
          </a>
        </span>
      )}
    </>
  );
}

/* ------------------------------------------------------------- glossary */
/* Everything the Term popovers say, in one place. A popover is for the word
   you tripped over; this is for reading before you start, or on a phone where
   chasing twenty popovers is no way to learn anything. */
function Glossary() {
  return (
    <details className="glossary">
      <summary>Plain-English glossary — every technical term on this page</summary>
      <div className="glossary-body">
        {glossaryByGroup().map(([label, entries]) => (
          <section key={label}>
            <h4>{label}</h4>
            <dl>
              {entries.map(([id, g]) => (
                <div key={id}>
                  <dt>
                    <a href={g.href} target="_blank" rel="noopener noreferrer">{g.term} &#8599;</a>
                  </dt>
                  <dd>{g.plain}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </details>
  );
}

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

  /* The masthead is sticky, so anything we scroll to has to stop below it.
     Its height depends on how the row wraps, which depends on the width and on
     how long the backend's status string happens to be — so it is measured
     rather than guessed, and published as --header-h for the CSS to use. */
  const mastheadRef = useRef(null);
  useEffect(() => {
    const el = mastheadRef.current;
    if (!el) return;
    const publish = () => document.documentElement.style.setProperty(
      '--header-h', `${Math.round(el.getBoundingClientRect().height)}px`);
    publish();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', publish);
      return () => window.removeEventListener('resize', publish);
    }
    const ro = new ResizeObserver(publish);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

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

  /* A dialog that floats over a page which is still scrolling is a phone
     problem specifically: you flick to reach the dialog's button and the page
     behind it moves instead. */
  const overlayOpen = showWelcome || showMetrics || structureFullscreen;
  useEffect(() => {
    document.body.classList.toggle('has-overlay', overlayOpen);
    return () => document.body.classList.remove('has-overlay');
  }, [overlayOpen]);
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
    { subject: 'How odd the swap is', A: ((d.blosum62 + 4) / 15) * 100, fullMark: 100 },
    { subject: 'Original size', A: ((d.wt_volume - 60) / 168) * 100, fullMark: 100 },
    { subject: 'Change in size', A: ((d.delta_volume + 170) / 340) * 100, fullMark: 100 },
    { subject: 'Closeness to ACE2', A: Math.max(0, (1 - d.ace2_distance / 45) * 100), fullMark: 100 },
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
              Every method below got the same four numbers per mutation and the same training data,
              then was tested on {metrics.n_test} mutations <Term id="heldout">none of them had ever
              seen</Term>. The score is <Term id="rocauc">ROC-AUC</Term>: the chance a method ranks a
              real binder above a real non-binder. 0.5 is a coin flip; 1.0 is perfect.
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

            <p className="small" style={{ marginTop: '0.9rem' }}>
              The non-quantum methods are <Term id="logistic">logistic regression</Term>, a small{' '}
              <Term id="mlp">neural network</Term> and a{' '}
              <Term id="svm">support vector machine</Term>. Ours is a{' '}
              <Term id="vqc">variational quantum circuit</Term>.
            </p>

            <p className="note" style={{ marginTop: '1.25rem' }}>
              <b>Why we quote this and not accuracy.</b> 68% of the mutations in this data still
              bind, so a model that simply answered "yes, it binds" every single time would already
              look 68% accurate while being completely useless. ROC-AUC cannot be gamed that way. On
              it, our quantum model comes fourth of five. We print that gap rather than bury it.
            </p>

            <dl className="facts" style={{ marginTop: '1rem' }}>
              <div>
                <dt>Circuit</dt>
                <dd>{metrics.vqc?.n_qubits} qubits · {metrics.vqc?.n_layers} layers ·{' '}
                    {metrics.vqc?.n_parameters} tunable dials</dd>
              </div>
              <div>
                <dt>Circuit design</dt>
                <dd>{metrics.vqc?.ansatz}</dd>
              </div>
            </dl>
            <p className="small" style={{ marginTop: '0.75rem' }}>
              How the data was split for testing: {metrics.split}<br />
              What the model reads: {metrics.features}
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
              Labs around the world upload new coronavirus sequences every day. Each one carries a
              handful of small changes, and somebody has to decide which of those changes are worth
              testing. Testing a single one at a lab bench takes two to six weeks.
            </p>
            <p>
              Q-VIRA looks at each change and predicts one thing: can the virus still grab{' '}
              <Term id="ace2">ACE2</Term>, the protein on a human cell it has to hold on to in order
              to get in? It then puts the changes in order, so the most suspicious are tested first.
              It gives a to-do list, not a diagnosis.
            </p>
            <p className="note is-flag" style={{ margin: '1.25rem 0' }}>
              <b>What this is not.</b> A research project, not a medical or public-health tool. We
              are not claiming that quantum computers do this better — three ordinary, non-quantum
              methods beat our quantum one on the same data, and the model card shows those numbers.
            </p>
            <button className="btn" onClick={() => setShowWelcome(false)}>Open the dashboard</button>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------- masthead */}
      <header className="masthead print-hidden" ref={mastheadRef}>
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
                <span className="hide-sm">Held-out </span>AUC {metrics.vqc.roc_auc.toFixed(3)}
                <span className="hide-sm"> · model card</span>
              </button>
            )}
            {/* The same fact at two lengths. A phone gets the dot and one word;
                there is no width at which a truncated sentence is better. */}
            <span className="small mono status-line">
              <span className="status-dot" aria-hidden="true"
                    data-state={waking ? 'waking' : health ? 'up' : 'down'} />
              <span className="status-full">
                {waking ? `waking backend · ${wakeSeconds}s`
                  : health ? `backend online${health.model_trained ? ' · model loaded' : ' · untrained'}`
                  : 'backend unreachable'}
              </span>
              <span className="status-short">
                {waking ? `waking ${wakeSeconds}s` : health ? 'online' : 'offline'}
              </span>
            </span>
          </div>
        </div>
      </header>

      <main>
        {/* ------------------------------------------------------------ hero */}
        <section className="stage">
          <div className="shell">
            <p className="eyebrow">A 4-qubit quantum model that puts virus mutations in test-me-first order</p>
            <h1 className="stage-h1">Which mutation<br />should a lab test first?</h1>
            <p className="stage-sub">
              Labs upload new coronavirus sequences every day, and testing one mutation at the bench
              takes two to six weeks. Q-VIRA predicts, for every mutation, whether the virus can
              still grab <Term id="ace2">ACE2</Term> — the door handle it uses to get into a human
              cell — and ranks them, so the lab time goes to the right mutation first.
            </p>
            <div className="stage-cta">
              <button className="pill pill-solid" onClick={() => {
                setActiveTab('genomics');
                document.getElementById('instrument')?.scrollIntoView({ behavior: 'smooth' });
              }}>Score a variant</button>
              <button className="pill" onClick={() => {
                setActiveTab('sentinel');
                document.getElementById('instrument')?.scrollIntoView({ behavior: 'smooth' });
              }}>See today's deposits</button>
            </div>

            <div className="figures">
              {[
                ['4,221', 'real mutations', 'Each one made and measured in a laboratory, not predicted'],
                ['4', 'qubits', 'Four facts per mutation, one per qubit. We tried eight and kept these'],
                [metrics?.vqc?.roc_auc ? metrics.vqc.roc_auc.toFixed(3) : '0.747', 'ranking score',
                 'How well it orders mutations it never saw. Fourth of five methods — we publish the gap'],
                ['201', 'positions', 'The stretch of the spike that touches ACE2, spike 331 to 531'],
              ].map(([n, label, note], i) => (
                <Reveal key={label} delay={i * 70}>
                  <div className="figure-stat">
                    <div className="figure-n">{n}</div>
                    <div className="figure-l">{label}</div>
                    <div className="figure-note">{note}</div>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="shell hero" id="instrument">

          <div className="readout">
            <div className="readout-top">
              {result ? (
                <>
                  <div>
                    <div className="readout-label">
                      How well it still grabs ACE2 · {result.driver_mutation}
                    </div>
                    <div className="readout-value">
                      <CountUp value={result.threat_score} />
                      <span className="readout-err" title="How much the score wobbles between repeated quantum measurements">± {result.threat_score_stderr.toFixed(3)}</span>
                    </div>
                  </div>
                  <ResidueSwap code={result.driver_mutation} />
                  <div className="readout-meta">
                    {result.quantum.shots} quantum measurements · R₀ scenario {r0.toFixed(2)}
                    {seir && <> · peak day {seir.indicators.peak_day}</>}
                  </div>
                </>
              ) : (
                <div>
                  <div className="readout-label">Nothing scored yet</div>
                  <p className="muted" style={{ maxWidth: '58ch', marginTop: '0.15rem', marginBottom: '0.75rem' }}>
                    The ruler below is the stretch of the virus this model was trained on — the
                    201 positions that touch human cells. Pick a mutation you may have heard of and
                    see where it sits:
                  </p>
                  <div className="try-row">
                    {['N501Y', 'E484K', 'K417N', 'L452R'].map(code => (
                      <button key={code} type="button" className="try"
                              onClick={() => { setMutationInput(code); setActiveTab('genomics'); }}>
                        <span className={`try-dot aa-${klass(parseMutation(code).mut)}`} />
                        {code}
                      </button>
                    ))}
                  </div>
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
                <b>Outside what the model was taught.</b> {result.distribution.note}
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
                <span className="small">
                  each scored on its own — the model does not account for mutations changing
                  one another's effect (<Term id="epistasis">epistasis</Term>)
                </span>
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
                  New coronavirus <Term id="spike">spike proteins</Term> uploaded by labs to{' '}
                  <Term id="ncbi">NCBI</Term>, the public sequence database. We compare each one
                  against the original Wuhan virus to find what changed, score the changes that fall
                  in the region that touches human cells (spike positions 331–531), and rank them.
                </p>
                <p className="small" style={{ marginTop: '0.5rem', maxWidth: '70ch' }}>
                  Method: local <Term id="alignment">sequence alignment</Term> by{' '}
                  <Term id="smithwaterman">Smith–Waterman</Term> with the{' '}
                  <Term id="blosum">BLOSUM62</Term> substitution matrix.
                </p>
              </div>

              <section className="section">
                <h3>How to read this</h3>
                <p className="note">
                  Almost every coronavirus circulating today already carries the same ~30 changes it
                  inherited from Omicron. Everything has them, so they say nothing about which sample
                  is new. Each row below is therefore ranked by the changes that are{' '}
                  <b>unique to that upload</b> — shown in colour; the shared ones stay grey.{' '}
                  <b>Read it as a to-do list, not a verdict.</b> A high score means a lab should look
                  at it sooner, not that the variant is dangerous or that it will spread.
                </p>
              </section>

              {sentinelError && (
                <section className="section">
                  <p className="note is-alarm"><b>No list to show.</b> {sentinelError}</p>
                </section>
              )}

              {sentinel && (
                <>
                  <section className="section">
                  <h3>This fetch</h3>
                  <dl className="facts">
                    <div>
                      <dt>Last asked NCBI</dt>
                      <dd>
                        {new Date(sentinel.fetched_at).toLocaleString()}
                        {feedStatus?.age_hours != null && (
                          <span className="small"> · {feedStatus.age_hours.toFixed(1)}h ago</span>
                        )}
                      </dd>
                    </div>
                    <div><dt>Sequences read</dt><dd>{sentinel.n_analysed}</dd></div>
                    <div><dt>Actually different from each other</dt><dd>{sentinel.n_distinct_variants}</dd></div>
                    <div><dt>Could not be used</dt><dd>{sentinel.n_skipped}</dd></div>
                    <div><dt>Region scored</dt><dd>spike {sentinel.rbd_window}</dd></div>
                    <div><dt>Changes every sample shares</dt><dd>{sentinel.n_shared_mutations}</dd></div>
                  </dl>

                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', flexWrap: 'wrap',
                                margin: '1rem 0 1.75rem' }}>
                    <button className="btn btn-ghost btn-sm" onClick={refreshSentinel}
                            disabled={sentinelBusy || feedStatus?.refreshing}>
                      {sentinelBusy || feedStatus?.refreshing ? 'Asking NCBI…' : 'Get the newest uploads'}
                    </button>
                    <span className="small" style={{ maxWidth: '62ch' }}>
                      {feedStatus?.auto_refresh
                        ? `This list updates itself once it is more than ${feedStatus.max_age_hours}h old. NCBI limits how often anyone may query it, so the update runs quietly in the background and the page shows the last saved copy. The time above is when we actually asked NCBI — never when you opened the page.`
                        : 'NCBI limits how often anyone may query it, so uploads are fetched ahead of time. The time above is when we actually asked.'}
                    </span>
                  </div>

                  {feedStatus?.last_error && (
                    <p className="note is-flag">
                      <b>The last update failed.</b> {feedStatus.last_error} — showing the previous list.
                    </p>
                  )}
                  </section>

                  <section className="section">
                  <h3>Uploads, ranked</h3>
                  <p className="section-lede">
                    Each row is one sequence deposited by a lab. The code on the left is its{' '}
                    <Term id="accession">accession</Term> — the permanent ID it was given in the
                    public database.
                  </p>
                  <p className="note is-flag" style={{ marginBottom: '1.25rem' }}>
                    <b>Why some rows are flagged.</b> The model learned from viruses carrying exactly{' '}
                    <i>one</i> change at a time. A real upload often carries dozens at once, and we
                    still score them one at a time. That ignores the fact that mutations can amplify
                    or cancel each other (<Term id="epistasis">epistasis</Term>), which is known to be
                    a large effect in this protein. Those rows are marked, and their scores are weaker
                    evidence.
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
                                        ? 'This position is missing from the 6M0J structure, so its distance to ACE2 is an estimate rather than a measurement'
                                        : undefined}
                                      className={`chip${unique ? ' is-unique' : ''}${m.has_structure === false ? ' no-structure' : ''}`}>
                                  <span className={`chip-dot aa-${klass((parseMutation(m.mutation) || {}).mut)}`} />
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
                            {r.n_distinguishing} unique to this upload ·{' '}
                            {r.n_without_structure > 0 && <>{r.n_without_structure} marked * are missing from the measured structure, so they are not ranked · </>}
                            {r.rbd_substitutions} change{r.rbd_substitutions === 1 ? '' : 's'} scored in the region ·
                            {' '}{(r.rbd_coverage * 100).toFixed(0)}% of that region readable · {r.sequence_length} positions long
                          </div>
                          {r.high_divergence && (
                            <div className="small" style={{ color: 'var(--flag)' }}>
                              Many changes at once — {r.rbd_substitutions} of them in the scored
                              region, so these numbers are weaker evidence than a single change would be.
                            </div>
                          )}
                        </div>

                        <div className="lane-score">
                          <div className="v">
                            {r.top_distinguishing_score !== null ? r.top_distinguishing_score.toFixed(3) : '—'}
                          </div>
                          <div className="k">
                            {r.top_distinguishing ? `highest unique change · ${r.top_distinguishing}` : 'nothing unique to this upload'}
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
                      {sentinel.records.filter(r => r.max_score === null).length} more sequences had no
                      changes at all in the region we score. That is a normal result, shown rather
                      than quietly dropped.
                    </p>
                  )}

                  </section>

                  <section className="section">
                    <h3>Caveats</h3>
                    <p className="section-lede">
                      Everything we know to be uncertain or wrong about this run, written down rather
                      than left out.
                    </p>
                    <ul className="caveats">
                      {sentinel.caveats.map((c, i) => <li key={i}>{c}</li>)}
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
                  Pick a reference virus, then type the changes you want scored. The standard way to
                  write one is <b>N501Y</b>: the original{' '}
                  <Term id="residue">amino acid</Term> (N), its position along the chain (501), and
                  what it changed into (Y). We check that the first letter really is what sits at
                  that position, so a typo is rejected instead of being scored in the wrong place.
                </p>
              </div>

              <div className="cols cols-2">
                <div>
                  <section className="section">
                  <h3>Input</h3>
                  <div className="stack">
                  <div>
                    <label className="field" htmlFor="ref">Which virus to start from</label>
                    <select id="ref" value={refName} onChange={e => setRefName(e.target.value)}>
                      {refList.length === 0 && <option value="">No references loaded</option>}
                      {refList.filter(r => r.in_distribution).map(r => (
                        <option key={r.name} value={r.name}>{r.name} ({r.length} aa)</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="field" htmlFor="muts">Changes to score</label>
                    <input id="muts" type="text" className="mono" value={mutationInput}
                           onChange={e => setMutationInput(e.target.value)} placeholder="N501Y E484K" />
                    <p className="small" style={{ marginTop: '0.4rem' }}>
                      Separate them with spaces or commas. The model only learned the{' '}
                      <Term id="rbd">region that touches human cells</Term> — spike positions 331 to
                      531. Anything outside that is flagged rather than hidden.
                    </p>
                  </div>

                  <button className="btn" onClick={runLiveQuantumEngine} disabled={loading || !refName}>
                    {loading ? 'Scoring…' : 'Score these changes'}
                  </button>

                  {apiError && (
                    <p className={`note ${apiErrorKind === 'input' ? 'is-flag' : 'is-alarm'}`}>
                      <b>{apiErrorKind === 'input' ? 'Rejected.' : 'Cannot reach the server.'}</b> {apiError}
                    </p>
                  )}

                  {refList.some(r => !r.in_distribution) && (
                    <p className="note">
                      {refList.filter(r => !r.in_distribution).length} other viruses are loaded —
                      MERS, Ebola, Nipah, influenza and others — but you <b>cannot pick them</b>. This
                      model only ever learned SARS-CoV-2 grabbing human <Term id="ace2">ACE2</Term>.
                      Those viruses get into cells through completely different proteins, so a score
                      for them would mean nothing — and offering one would suggest we had checked. We
                      have not.
                    </p>
                  )}

                  <p className="note">
                    <b>Why there is nowhere to paste a sequence.</b> The model scores{' '}
                    <i>changes</i>, not whole sequences — it needs to know which positions differ from
                    the original. A pasted <Term id="fasta">FASTA</Term> file is just a run of
                    letters and would not tell it that on its own. The reference sequences come
                    from <Term id="ncbi">NCBI</Term>.
                  </p>
                  </div>
                  </section>
                </div>

                <div style={{ minWidth: 0 }}>
                  <section className="section">
                  <h3>What the model actually looks at</h3>
                  <p className="section-lede">
                    Every mutation is boiled down to four numbers — one per{' '}
                    <Term id="qubit">qubit</Term>. We started with eight and removed them one at a
                    time (<Term id="ablation">an ablation</Term>); these four were the ones doing
                    the work.
                  </p>
                  <div className="figure">
                    {featureData.length === 0 ? (
                      /* an empty radar draws nothing at all, which reads as a broken panel
                         rather than as "no input yet" */
                      <div style={{ height: 'clamp(185px, 48vw, 230px)', display: 'grid',
                                    placeItems: 'center', textAlign: 'center', padding: '1rem' }}>
                        <span className="muted">
                          Score a mutation to see the four numbers it is reduced to.
                        </span>
                      </div>
                    ) : (
                    <div style={{ width: '100%', height: 'clamp(185px, 48vw, 230px)', minWidth: 0 }}>
                      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                        <RadarChart cx="50%" cy="50%" outerRadius="72%" data={featureData}>
                          <PolarGrid stroke={C.rule} />
                          <PolarAngleAxis dataKey="subject" tick={{ fill: C.ink2, fontSize: 11 }} />
                          <PolarRadiusAxis angle={30} domain={[0, 120]} tick={false} axisLine={false} />
                          <Radar dataKey="A" stroke={C.assay} fill={C.assay} fillOpacity={0.22} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </div>
                    )}
                    <dl className="feature-key">
                      <div>
                        <dt>How odd the swap is</dt>
                        <dd>
                          Whether this is a swap that shows up often between related real proteins,
                          or a drastic one. Scored with <Term id="blosum">BLOSUM62</Term>.
                        </dd>
                      </div>
                      <div>
                        <dt>Original size</dt>
                        <dd>
                          How bulky the <Term id="wildtype">original</Term>{' '}
                          <Term id="residue">amino acid</Term> was.
                        </dd>
                      </div>
                      <div>
                        <dt>Change in size</dt>
                        <dd>
                          How much bulkier or smaller the new one is. A big jump can push the
                          surrounding protein out of shape.
                        </dd>
                      </div>
                      <div>
                        <dt>Closeness to ACE2</dt>
                        <dd>
                          How near this position sits to the point where the virus actually touches
                          ACE2, measured from the{' '}
                          <Term id="structure">solved 6M0J structure</Term>. It is the single most
                          important of the four.
                        </dd>
                      </div>
                    </dl>
                  </div>
                  </section>

                  <section className="section">
                  <h3>The real structure it measures from</h3>
                  <div className="figure viewer-shell" style={{ padding: 0, overflow: 'hidden' }}>
                    {isFolding ? (
                      <div style={{ height: 'clamp(220px, 60vw, 280px)', display: 'grid', placeItems: 'center', textAlign: 'center', padding: '1rem' }}>
                        <div>
                          <div className="mono" style={{ fontSize: 'var(--t-sm)' }}>Loading the structure</div>
                          <div className="small" style={{ marginTop: '0.3rem' }}>
                            Fetching a structure that was solved in a laboratory. Nothing here is
                            predicted by software.
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ position: 'relative', height: 'clamp(220px, 60vw, 280px)', overflow: 'hidden' }}>
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
                      <span className="mono">{(pdbInput || '6m0j').toUpperCase()}</span> — a{' '}
                      <Term id="structure">structure solved in a laboratory</Term>, showing the virus
                      spike tip locked onto human ACE2: exactly the event this model scores. One of
                      the four numbers the model reads — how far each position sits from the point of
                      contact — was measured from this. Measured, not predicted.
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
                  Four <Term id="qubit">qubits</Term> can be in 16 different settings at once. The
                  chart shows how much of the quantum state is sitting in each of those{' '}
                  <Term id="basisstate">16 settings</Term> — taken from the same circuit that
                  produced the score above, not drawn for show.
                </p>
                <p className="small" style={{ marginTop: '0.5rem', maxWidth: '70ch' }}>
                  Method: a <Term id="reupload">data re-uploading</Term> circuit; the score is the{' '}
                  <Term id="expval">expectation value</Term> of <Term id="pauliz">Pauli-Z</Term> on
                  the first qubit.
                </p>
              </div>

              <div className="figure">
                {quantumWaveformData.length === 0 ? (
                  <div style={{ height: 'clamp(230px, 62vw, 320px)', display: 'grid', placeItems: 'center' }}>
                    <span className="muted">Score a mutation to see the quantum state.</span>
                  </div>
                ) : (
                  <div style={{ width: '100%', height: 'clamp(250px, 64vw, 340px)', minWidth: 0 }}>
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
                  Computed on the server by the real circuit, not drawn in your browser.
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
                  A textbook <Term id="seir">SEIR model</Term>: it sorts a population into
                  Susceptible, Exposed, Infected and Recovered, and works out how fast people move
                  between those four groups. It assumes everyone mixes with everyone evenly, that{' '}
                  <Term id="r0">R₀</Term> never changes, and that nobody does anything to stop the
                  spread — none of which is true of a real outbreak. We turn the binding score into
                  an R₀ between 0.8 and 4.0 by a fixed rule you can check.{' '}
                  <b>This is a what-if, not a forecast.</b>
                </p>
              </div>

              {seir ? (
                <>
                  <section className="section">
                  <h3>Parameters</h3>
                  <dl className="facts">
                    <div><dt>β · infections caused per day</dt><dd>{seir.parameters.beta}</dd></div>
                    <div><dt>σ · rate of turning infectious</dt><dd>{seir.parameters.sigma}</dd></div>
                    <div><dt>γ · recovery rate</dt><dd>{seir.parameters.gamma}</dd></div>
                    <div><dt><Term id="r0">R₀</Term></dt><dd>{r0.toFixed(2)}</dd></div>
                    <div><dt>Busiest day</dt><dd>{seir.indicators.peak_day}</dd></div>
                    <div><dt>Share who catch it (<Term id="attackrate">attack rate</Term>)</dt><dd>{seir.indicators.attack_rate_percent}%</dd></div>
                    <div><dt><Term id="herd">Herd-immunity threshold</Term></dt><dd>{seir.indicators.herd_immunity_threshold_percent}%</dd></div>
                    <div><dt>Day hospitals overflow</dt><dd>{seir.indicators.capacity_breach_day ?? 'never'}</dd></div>
                  </dl>
                  </section>

                  <section className="section">
                  <h3>Curve</h3>
                  <div className="figure">
                    <div style={{ width: '100%', height: 'clamp(265px, 68vw, 360px)', minWidth: 0 }}>
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
                <p className="muted">Score a mutation to run the scenario.</p>
              )}
            </section>
          )}

          {/* =============================================== 5. CHEMISTRY */}
          {activeTab === 'vqe' && (
            <section className="panel">
              <div className="panel-head">
                <h2>Quantum chemistry</h2>
                <p className="lede">
                  A real quantum algorithm — <Term id="vqe">VQE</Term> — working out the lowest
                  energy a hydrogen molecule (H₂, just two atoms) can have. Because the molecule is
                  so small, we can also{' '}
                  <Term id="diagonalization">solve it exactly by brute force</Term>, so you can see
                  for yourself how close the quantum answer gets.
                </p>
                <p className="small" style={{ marginTop: '0.5rem', maxWidth: '70ch' }}>
                  Method: <Term id="sto3g">STO-3G</Term> basis,{' '}
                  <Term id="jordanwigner">Jordan–Wigner</Term> mapping, checked against exact
                  diagonalization of the same <Term id="hamiltonian">Hamiltonian</Term>.
                </p>
              </div>

              <div className="cols cols-2">
                <div style={{ minWidth: 0 }}>
                  <section className="section">
                  <h3>Run it yourself</h3>
                  <div className="stack">
                  <div className="sheet stack">
                    <div>
                      <label className="field" htmlFor="bond">
                        How far apart the two atoms are <span className="mono">{vqeBond.toFixed(4)} <Term id="angstrom">Å</Term></span>
                      </label>
                      <input id="bond" type="range" min="0.3" max="2.4" step="0.01" value={vqeBond}
                             onChange={e => setVqeBond(parseFloat(e.target.value))} />
                      <div className="small" style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>0.3 Å</span><span>they settle at ≈ 0.74 Å</span><span>2.4 Å</span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className="btn btn-ghost" style={{ flex: 1 }} aria-pressed={vqeView === 'single'}
                              onClick={() => runVqe('single')} disabled={vqeBusy}>
                        {vqeBusy && vqeView === 'single' ? 'Loading…' : 'This distance'}
                      </button>
                      <button className="btn btn-ghost" style={{ flex: 1 }} aria-pressed={vqeView === 'curve'}
                              onClick={() => runVqe('curve')} disabled={vqeBusy}>
                        {vqeBusy && vqeView === 'curve' ? 'Loading…' : 'Every distance'}
                      </button>
                    </div>

                    {vqeError && <p className="note is-alarm"><b>Failed.</b> {vqeError}</p>}

                    {vqeView === 'single' && vqeResult && (
                      <div className="stack-sm">
                        <dl className="facts">
                          <div><dt>Quantum answer</dt><dd>{Number(vqeResult.vqe_energy ?? 0).toFixed(6)} <Term id="hartree">Ha</Term></dd></div>
                          <div><dt>Exact answer</dt><dd>{Number(vqeResult.exact_energy ?? 0).toFixed(6)} Ha</dd></div>
                        </dl>
                        <p className={`note ${vqeResult.within_chemical_accuracy ? '' : 'is-flag'}`}>
                          <b>Off by {Number(vqeResult.absolute_error ?? 0).toExponential(2)} Ha</b> —{' '}
                          {vqeResult.within_chemical_accuracy ? 'inside' : 'outside'}{' '}
                          <Term id="chemacc">chemical accuracy</Term>, the 1.6×10⁻³ Ha mark below
                          which a computed energy is good enough to predict real chemistry.
                        </p>
                        <div className="small">
                          {vqeResult.n_qubits} qubits · {vqeResult.n_parameters} tunable dials ·{' '}
                          {vqeResult.n_pauli_terms} terms in the energy
                          {vqeResult.runtime_seconds ? ` · ${vqeResult.runtime_seconds}s` : ''} ·
                          recovers {vqeResult.correlation_energy?.toFixed(6)} Ha of{' '}
                          <Term id="correlation">correlation energy</Term>, the part the simplest
                          method (<Term id="hartreefock">Hartree–Fock</Term>) misses
                        </div>
                        <div style={{ width: '100%', height: 'clamp(150px, 38vw, 170px)', minWidth: 0 }}>
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
                        <div className="figure-cap">The optimiser walking downhill to the lowest energy, one step at a time.</div>
                      </div>
                    )}

                    {vqeView === 'curve' && vqeCurve && (
                      <div className="stack-sm">
                        <div className="small">
                          Pulling the two atoms apart — largest error anywhere on the curve{' '}
                          <span className="mono">{Number(vqeCurve.max_absolute_error ?? 0).toExponential(2)} Ha</span>
                          {vqeCurve.all_within_chemical_accuracy && ', every point inside chemical accuracy'}
                        </div>
                        <div style={{ width: '100%', height: 'clamp(170px, 44vw, 200px)', minWidth: 0 }}>
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
                          The atoms settle {vqeCurve.equilibrium_bond_length} Å apart; measured in
                          the real world, it is {vqeCurve.experimental_bond_length} Å.
                        </div>
                      </div>
                    )}
                  </div>

                  <p className="note">
                    <b>Computed earlier, not right now.</b> The optimisation is real, but we ran it
                    ahead of time with <code>build_vqe_data.py</code> and serve the answer instantly —
                    a 60-step optimisation inside a web request tied the server up. You can reproduce
                    any point here with <code>notebooks/vqe_h2.ipynb</code>.
                  </p>
                  </div>
                  </section>
                </div>

                <div style={{ minWidth: 0 }}>
                  <section className="section">
                  <h3>What is really being simulated here</h3>
                  <p className="section-lede">
                    This panel runs on H₂ — two atoms. The protein the rest of the site scores is a
                    different problem entirely, and not one a quantum computer can touch. Being clear
                    about that is the whole point of this panel.
                  </p>
                  <div className="stack">

                  <div className="sheet">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem' }}>
                      <b>H₂ — what runs here</b>
                      <span className="mono" style={{ color: C.assay, fontSize: 'var(--t-md)' }}>4 qubits</span>
                    </div>
                    <p className="small" style={{ marginTop: '0.4rem' }}>
                      Two electrons in four slots. Small enough that we can also solve it exactly
                      and prove the quantum answer is right, which is exactly why it is worth doing.
                    </p>
                  </div>

                  <div className="divide"><span>~25,000× more qubits</span></div>

                  <div className="sheet">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem' }}>
                      <b>A drug inside a protein — what would be needed</b>
                      <span className="mono" style={{ color: C.flag, fontSize: 'var(--t-md)' }}>~10⁵ qubits</span>
                    </div>
                    <p className="small" style={{ marginTop: '0.4rem' }}>
                      Thousands of atoms, and that is before the error correction a real machine
                      would need. No quantum computer will do this for many years. If a demo claims it
                      computed a drug binding to a protein on a quantum computer, it did something
                      else and called it that.
                    </p>
                  </div>

                  <p className="note">
                    <b>What would come next, in order.</b> H₂ and LiH checked against the exact
                    answer — that part is done. Then a small, carefully chosen piece of a drug
                    molecule (<Term id="activespace">an active space</Term>) checked against the best
                    classical method. Then that quantum piece embedded inside an ordinary classical
                    simulation of the whole protein (<Term id="qmmm">QM/MM</Term>). Even then, the
                    number a drug designer actually wants — how tightly the drug binds — stays out of
                    reach.
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
              BioQubit Labs · Q-Hack India 2026, Quantum Biotech &amp; Chemistry. Trained on{' '}
              <Term id="starr">Starr et al. (2020)</Term>, a{' '}
              <Term id="dms">deep mutational scanning</Term> study of the part of the SARS-CoV-2
              spike that touches human cells; distances measured from{' '}
              <Term id="pdb">PDB</Term> entry 6M0J. A research prototype, not a clinical or
              public-health tool.
            </p>
            <Glossary />
          </div>
        </footer>
      </main>

      {/* ------------------------------------------------------------ copilot */}
      <div className="print-hidden">
        {!isChatOpen ? (
          <button className="btn copilot-fab" aria-label="Ask about this run"
                  onClick={() => setIsChatOpen(true)}>
            Ask<span className="hide-sm"> about this run</span>
          </button>
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
