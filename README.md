# Q-VIRA — which mutation should a lab test first?

**Team BioQubit Labs · Quantum Biotech & Chemistry · Q-Hack India 2026**

Labs deposit new viral sequences every day, and someone has to decide which
mutations are worth bench time — characterising one takes two to six weeks.
Q-VIRA scores each amino-acid substitution with a trained variational quantum
circuit and puts the results in order, so limited capacity goes to the right
change first. It produces a triage order, not a verdict.

There are **two trained models**, deliberately kept separate:

| Model | Scope | Circuit | Held-out AUC |
|---|---|---|---|
| **SARS-CoV-2 specialist** | RBD → ACE2 binding, spike sites 331–531 | 2 qubits · 6 layers · 41 params | **0.742 ± 0.002** |
| **Cross-virus generalist** | 17 proteins, 12 viral organisms | 3 qubits · 6 layers · 63 params | **0.681 ± 0.002** |

| | |
|---|---|
| Live app | https://bio-qubit-labs.vercel.app |
| API | https://q-vira-api.onrender.com |
| Source | https://github.com/aarush-create/BioQubit-Labs |

---

## What this is, and what it is not

**What it does**

- Pulls recently deposited SARS-CoV-2 spike proteins from NCBI, aligns them to
  Wuhan-Hu-1 (Smith–Waterman), scores their RBD substitutions, and ranks deposits
  by the mutations **unique** to each one
- Scores a chosen substitution with a trained data re-uploading VQC (PennyLane),
  reporting held-out AUC alongside logistic regression, SVM and an MLP **on
  identical features and an identical split**
- **Generalises across viruses:** a second model scores substitutions in 17
  proteins from 12 organisms (influenza, HIV-1, dengue, coxsackievirus and more)
  drawn from the ProteinGym deep-mutational-scanning benchmark
- Projects an SEIR epidemic **scenario** from the score (scipy `solve_ivp`)
- Runs a real VQE on H₂, served through **IBM Qiskit Aer** and benchmarked
  against two classical references at every bond length: **Hartree–Fock**
  (mean-field) and **exact diagonalization** (FCI). VQE matches exact to
  ≤1.9×10⁻⁷ Ha across the whole curve; classical Hartree–Fock misses up to
  **0.22 Ha (~139 kcal/mol)** at stretched bonds — a real
  quantum-beats-classical-mean-field result at this scale, with no claim of
  speedup

**What it does not do**

- It does **not** predict outbreaks. The SEIR curve is a scenario under stated
  assumptions, with R₀ mapped from the score across 0.8–4.0.
- It does **not** claim a theoretical quantum advantage (no proven speedup). On
  the near-linear SARS-CoV-2 task the model trails the classical baselines; on the
  harder cross-virus generalisation task it **beats logistic regression and matches
  the best classical baseline on 63 parameters**, with a restart ensemble ahead of
  all of them. What we defend is parameter/qubit efficiency, honest measurement,
  and a competitive result where it counts.
- It does **not** model epistasis. Training used single mutants only, so combined
  substitutions are scored independently and flagged when there are many.
- The SARS-CoV-2 model is **trained on the receptor-binding domain only** (spike
  sites 331–531). The cross-virus model scores **only** the 17 proteins whose
  AlphaFold structure numbering we verified against the assay wildtype; it does
  not score an arbitrary protein, because its structural feature has nowhere to
  come from.
- It does **not** simulate protein–ligand binding on a quantum computer. That is
  ~10⁵ qubits away; see `notebooks/vqe_h2.ipynb` §5.
- It is **not** a clinical or public-health tool.

---

## Results — two models

Every number below is produced by `train_vqc.py`, reported as the **mean ± sample
standard deviation across 3 random restarts** (not one lucky seed), and served
live from `GET /metrics` so the app can be checked against the API.

### 1. SARS-CoV-2 specialist

Real data: Starr et al. (2020) deep mutational scanning of the SARS-CoV-2 RBD.
**Task:** predict `bind_avg ≥ −1.0` (the mutant retains binding). **Split:**
grouped by site — no site in both halves (151 train sites / 2,856 rows,
50 held-out sites / 946 rows).

**2 qubits · 6 layers · 41 parameters · dense encoding · full-distribution readout**
Features: `blosum62`, `wt_volume`, `delta_volume`, `ace2_distance`

| Model | Held-out AUC |
|---|---|
| Logistic regression | 0.7796 |
| Neural network (MLP) | 0.7706 |
| Support vector machine (RBF) | 0.7576 |
| **VQC (ours)** | **0.7423 ± 0.0016** |
| Always answer yes (chance) | 0.5000 |

This replaces the Round 1 model (4 qubits, 74 parameters, 0.7468). The new model
reaches the same accuracy within noise on **half the qubits and 45% fewer
parameters** — the headline is resource efficiency, not a higher number. On raw
AUC it still trails the classical baselines; it matches logistic regression on
calibration (Brier 0.189 vs 0.173) and on top-of-list precision (precision@25 =
1.00; 97 correct calls before the first false positive, against LR's 104). A
10-restart ensemble lifts held-out AUC to **0.757**, level with the SVM, though
logistic regression stays ahead — on this near-linear task a linear model is hard
for any method to beat.

### 2. Cross-virus generalist

Real data: 17 viral proteins from the ProteinGym substitution benchmark (the
"Growth"/organismal-fitness assays — one coherent phenotype), 146,161 single
mutants across 12 organisms. **Split:** grouped **by protein** — no protein in
both halves, so the test asks whether the model works on a virus it has never
seen, which is the deployment condition for a novel pathogen.

**3 qubits · 6 layers · 63 parameters · dense encoding**
Features: `blosum62`, `wt_volume`, `delta_volume`, `wt_hydropathy`,
`delta_hydropathy`, **`burial`** (contacts within 10 Å, from AlphaFold structures)

| Model | Held-out AUC (protein-held-out) | Parameters |
|---|---|---|
| **VQC — 10-restart ensemble** | **0.6903** | 630 |
| MLP | 0.6840 | 129 |
| Support vector machine | 0.6833 | — |
| **VQC — shipped** | **0.6812 ± 0.0022** | **63** |
| Logistic regression | 0.6760 | 7 |

The shipped **63-parameter** circuit **beats logistic regression** and sits level
with SVM and the MLP — at **half the MLP's 129 parameters**. Averaging ten
restarts (every restart used, none chosen by its test score — an honest single
model) **beats every classical baseline outright at 0.6903**, though at 630
parameters and with slightly lower top-of-list precision, so the single model
stays the shipped one. Cross-protein prediction is a harder task than
within-protein, which is why the absolute number is lower than the SARS-CoV-2
model's — they answer different questions and are not directly comparable.

Every ablation, every measured null result, and the full per-protein breakdown
are in **[RESULTS.md](RESULTS.md)**.

---

## What the build sprint measured

Five results, each a measurement rather than an assertion. Several contradicted
our own first guess, which is why they are worth stating.

1. **A structural feature, generalised.** The SARS-CoV-2 model's single biggest
   feature was `ace2_distance` — but it is measured from one complex (PDB 6M0J)
   and means nothing for any other virus. Its protein-agnostic cousin, **residue
   burial** (how packed a residue is in its own fold, from AlphaFold), restores
   that positional signal for every protein. Adding it moved the cross-virus
   model **+0.0265 AUC** (0.655 → 0.681), with non-overlapping restart ranges,
   and improved **all four** held-out proteins. The join from structure to assay
   was verified residue-by-residue against the wildtype column; two proteins
   (Zika, HCV) whose AlphaFold numbering disagreed were detected and dropped
   rather than trained on as noise.

2. **The optimal feature count scales with the data.** Four descriptors are best
   for the SARS-CoV-2 model (2,856 rows); adding two makes it *overfit*
   (0.742 → 0.679, training loss falls while test AUC drops). On the 112k-row
   panel the same two descriptors *help*. A feature set cannot be chosen on a
   small dataset and assumed to transfer.

3. **More data makes the measurement trustworthy.** Restart-to-restart AUC
   variance fell from **±0.02** at 2,856 rows to **±0.002** at 112k rows — a
   tenfold tightening. Several Round 1 single-seed comparisons were, in
   retrospect, within their own noise; everything here is reported as a
   multi-seed spread for that reason.

4. **Expanding the database 38× does not, by itself, raise AUC.** A SARS-CoV-2
   genetic-background panel (8 backgrounds) added rows but almost no new *feature
   vectors* (90% were duplicates), because the descriptors are functions of
   `(site, wildtype, mutant)`. More proteins — not more backgrounds of one
   protein — is what added real information.

5. **Where measured data already exists, no model is needed.** Looking up how the
   same substitution behaved in a related genetic background scores 0.98 AUC — a
   lookup table, not a model. Our site-grouped / protein-grouped splits forbid
   that lookup on purpose, because the tool is for the case a novel pathogen
   presents: no measurements yet. That is why our honest numbers are 0.74 and
   0.68 rather than the 0.95 a leaky split would report.

---

## Field benchmarks — measured against the field, not just our own baselines

Everything above compares the VQC to classical baselines on *our* split. These are
the comparisons against published methods, and the metric a triage lab actually
acts on. Every number is read from `api/metrics_panel.json` (served at
`GET /panel/status`) or the public ProteinGym AUC file, so a judge can diff them.

### vs ESM — Meta's protein language models (zero-shot, same four held-out proteins)

Pulled from ProteinGym v1.3 (`DMS_substitutions_AUC_DMS_level.csv`): same proteins,
same mutants, same binarisation, same AUC metric — apples to apples.

| Model | Parameters | Mean AUC (4 held-out proteins) |
|---|---|---|
| **Q-VIRA VQC (ours)** | **63** | **0.690** |
| ESM-2 | 650 M | 0.635 |
| ESM-1v (ensemble) | 650 M × 5 | 0.591 |
| ESM-1b | 650 M | 0.569 |
| ESM-1v (single) | 650 M | 0.565 |

A **63-parameter** circuit beats every ESM variant on the alignment-free task
(**+0.125** mean AUC over ESM-1v, winning 3 of 4 proteins — against a 650-million-parameter
model). The honest caveat: MSA-based methods still lead (EVmutation 0.727, GEMME
0.762, TranceptEVE 0.766) — but they need the deep alignments a novel pathogen does
not have, which is the exact case this tool is built for.

### Triage depth — the number a lab acts on

**Clean prefix** is how many top-ranked predictions are correct in a row before the
first false positive — how deep into the ranked list a lab can act without
double-checking. It is driven by calibration (Brier score and calibration gap,
lower is better), measured on identical features and the identical protein-held-out split.

| Model | Clean prefix | Brier ↓ | Calibration gap ↓ |
|---|---|---|---|
| **Q-VIRA VQC** | **22** | 0.2284 | **0.0453** |
| MLP | 1 | 0.2283 | 0.0481 |
| SVM | 9 | 0.2287 | 0.0557 |
| Logistic regression | 1 | 0.2309 | 0.0574 |

The VQC owns the calibration-gap column outright — its probabilities sit closest to
the true frequencies — which is the mechanism behind a trustworthy top-of-list
**2.4× deeper** than any classical baseline. For a lab deciding which mutations to
characterise first, that is the single most meaningful result in the project.

---

### Why quantum, honestly

The case for a VQC here is expressivity per parameter, not speed. The shipped
models carry 41 and 63 parameters; at 2–3 qubits the state is 4–8 dimensional and
trivially classically simulable — that is the point of working at this scale:
everything is verifiable, and the circuit is small enough to run on today's real
hardware. The ansatz is data re-uploading (Pérez-Salinas et al. 2020). Encoding
is **dense** (two features per qubit, one per rotation axis), which is what lets
six descriptors ride on three qubits instead of six — our own ablation measured
that six qubits hits a barren plateau (0.558 AUC, loss stuck) where three do not.

### Backend

Inference and the VQE run on **IBM Qiskit Aer** (`QVIRA_BACKEND=qiskit.aer`),
served through the PennyLane–Qiskit plugin from the same `circuit.py` the
models were trained on. The weights are backend-agnostic — we did not retrain
for Qiskit; the port was validated instead. Aer is a sampling simulator (no
analytic mode), so we tested convergence rather than exact equality: the
residual between the two backends falls with shot count at a fitted exponent
of **−0.497** (pure shot noise predicts −0.500), and across 18
fixture-by-shot-level tests no residual exceeded 2σ. Both backends implement
the same quantum state. See `api/parity_check.py` and
`api/convergence_check.py` — the scripts and their outputs are the audit
trail.

At serving shot counts (2048 shots) a single prediction carries ±0.010 of
shot noise, which `quantum_engine.py` already reports as an error bar with
every score.

---

## The two models in the app

The dashboard carries both. The **Score a variant** tab drives the SARS-CoV-2
specialist; the **Cross-virus model** tab drives the generalist — pick a virus and
protein, a site (its wildtype is shown), and a new residue, and the model returns
a score and the measured quantum state. Either model's result then drives the
shared **circuit**, **epidemic scenario** and **quantum chemistry** tabs, and the
cross-virus result also renders the protein's **AlphaFold 3D fold** (served from
`public/structures/`, the same AF2 models the burial feature is computed from)
with the mutated residue highlighted. The model card at the top is rendered live
from `GET /metrics`, so the numbers on screen can always be checked against the
API. An **Experiments** tab lays out the full measured record — baselines, the
ablations that chose the features, and the reported nulls (pLDDT, balancing,
BLOSUM clamp, and circuit depth) that show the feature space — and the circuit
reading it — is saturated.

---

## Architecture

```
  NCBI deposits                     manual input           virus + protein + site
  (sentinel.py, self-refreshing)    (reference + N501Y)    (panel_catalog.json)
        │                                 │                       │
        ▼                                 │                       │
  Smith-Waterman alignment               │                       │
  vs Wuhan-Hu-1, RBD 331-531             │                       │
        └───────────────┬────────────────┘                       │
                        ▼                                         ▼
          mutation_features.py                         panel_engine.py
          4 descriptors (incl. ACE2 distance)          6 descriptors (incl. burial)
                        ▼                                         ▼
          quantum_engine.py                            weights_panel.npz
          weights.npz  (2 qubits)                      (3 qubits, 17 proteins)
                        ▼                                         ▼
                 score ∈ [0,1] + shot-noise error bar + measured quantum state
                  │                     │
                  ▼                     ▼
          epidemiology.py          ranked triage list
          SEIR scenario            (surveillance feed)

  Shared: circuit.py defines the ansatz, encoding and readout ONCE, imported by
  training and by both engines, so what is trained cannot drift from what is
  served. Separate track: vqe.py — a real VQE on H2 vs exact diagonalization.
```

### The copilot runs on a provider chain

`copilot.py` tries **Gemini** first and falls through to **Grok** (xAI) on any
failure. Both get the same system prompt and grounding context. The model
**explains**; it never computes — every figure it quotes is passed in from the
endpoints, and the system prompt forbids inventing numbers.

### The surveillance feed refreshes itself

The committed `sentinel_cache.json` is a **seed, not a ceiling**. A page load is
served from memory; when the feed passes `SENTINEL_MAX_AGE_HOURS` (12 by default)
a worker thread re-queries NCBI and swaps the fresh payload in.

---

## Setup

### Backend

```bash
cd api
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

# SARS-CoV-2 model: training data (Git LFS — a plain download gives a pointer)
git lfs install
git clone https://github.com/jbloomlab/SARS-CoV-2-RBD_DMS
mkdir -p data && cp SARS-CoV-2-RBD_DMS/results/single_mut_effects/single_mut_effects.csv data/
python build_structure_features.py 6M0J.pdb        # ace2_distance, from PDB 6M0J

# Train the shipped SARS-CoV-2 model (-> weights.npz, metrics.json)
python train_vqc.py --data data/single_mut_effects.csv \
    --features 4,6,2,8 --readout probs --encoding dense --axes Y,Z \
    --seeds 3 --epochs 120 --val-frac 0.0

# Serve
uvicorn main:app --reload
```

**Reproducing the cross-virus model** (optional; the trained `weights_panel.npz`
and `panel_catalog.json` are committed):

```bash
# 1. ProteinGym substitution benchmark (1 GB) + AlphaFold structures (84 MB)
python fetch_panel.py           # or download DMS_ProteinGym_substitutions.zip
#   + ProteinGym_AF2_structures.zip from marks.hms.harvard.edu/proteingym

# 2. Burial feature from the structures (verified against assay wildtype)
python build_burial_features.py --af2-dir ../af2 --index ../DMS_substitutions.csv \
    --taxon Virus --selection-type Growth --out burial.json

# 3. Build the panel, joining burial (drops proteins that fail verification)
python proteingym_loader.py --data-dir ../proteingym_data \
    --index ../DMS_substitutions.csv --taxon Virus --selection-type Growth \
    --burial burial.json --out data/pg_growth_burial.csv

# 4. Train (-> weights_panel.npz, metrics_panel.json)
python train_vqc.py --panel data/pg_growth_burial.csv --group-by protein \
    --features 4,6,2,5,0,9 --readout probs --encoding dense --axes Y,Z \
    --seeds 3 --epochs 20 --batch 512 --lr 0.08 --val-frac 0.0 --tag panel
```

The large ProteinGym downloads are **not** committed (regenerable from the two
scripts above); the trained model and its catalogue are. Without `weights.npz`,
`/predict` returns 503 — the API will not emit a score from untrained parameters.

### Frontend

```bash
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.local
npm run dev
```

The interface follows the OS light/dark preference and remembers the choice;
it is verified from a 320px phone to a 1920px desktop. Technical terms are
defined in place via `src/glossary.js` and the footer glossary.

### Deploy

| | |
|---|---|
| Frontend (Vercel) | auto-detects Vite. Set `VITE_API_URL` to the Render URL, then redeploy. **`.vercelignore` must be in the repo root with the leading dot** — without it Vercel bundles `api/` as a serverless function and fails at the 500 MB limit (the Qiskit install alone is ~650 MB). Windows File Explorer silently strips the leading dot; create or rename the file from the GitHub web UI if that happens. |
| Backend (Render) | `render.yaml` included. Set `ALLOWED_ORIGINS`, plus `GEMINI_API_KEY` and/or `XAI_API_KEY`. |

Render's free tier sleeps after ~15 min idle (~50 s cold start). The frontend
pings `/` on load and says what it is waiting for rather than erroring.

#### Backend simulator

Set in `render.yaml` and in the Render dashboard:

```
QVIRA_BACKEND=qiskit.aer   # IBM Qiskit Aer simulator (validated)
QVIRA_SHOTS=2048           # shots per prediction
```

If the free tier runs out of memory on Aer, set `QVIRA_BACKEND=default.qubit`
in the Render dashboard (overrides `render.yaml`) and redeploy. The Qiskit
dependencies stay installed but Aer is never imported, so RSS drops. Scores
are identical within shot noise (that's what `convergence_check.py` proves),
so the fallback is a pure resource trade-off, not a correctness one.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Status: model trained, panel size, copilot providers, feed age |
| `GET /metrics` | Held-out metrics for the SARS-CoV-2 model (3-seed spread, baselines, triage) |
| `GET /references` | Reference sequences for scoring |
| `POST /predict` | `{"reference_name","mutations":["N501Y"]}` → per-substitution scores |
| `GET /panel/status` | Is the cross-virus model loaded; its headline metrics |
| `GET /panel/catalog` | Viruses → proteins, for the dropdowns |
| `GET /panel/sites` | `?protein=…` → sites (with wildtype) for a protein |
| `POST /panel/predict` | `{"protein","site","mutant"}` → cross-virus score + quantum state |
| `POST /seir` | `{"r0":2.5}` → SEIR curve, peak day, attack rate |
| `GET /vqe/curve`, `POST /vqe` | VQE across / at one H₂ geometry |
| `GET /sentinel`, `POST /sentinel/refresh` | Surveillance feed + background re-query |
| `POST /copilot` | Explainer on the Gemini → Grok chain, grounded in real numbers |

The cross-virus endpoints fail safe: if `weights_panel.npz` or `panel_catalog.json`
is absent the panel reports `available: false` and the SARS-CoV-2 API keeps
working.

---

## Engineering notes

- **One circuit definition.** `circuit.py` holds the ansatz, encoding and readout;
  training and both serving engines import it, so the served circuit cannot drift
  from the trained one. It used to be written out twice with a hopeful comment.
- **Models carry their own identity.** `weights.npz` records which feature columns
  and which blosum clamp it was trained with; the engine refuses to serve a model
  whose featuriser disagrees. A 6-feature SARS-CoV-2 model and a 6-feature panel
  model are otherwise indistinguishable on disk — this guard is why the wrong one
  can't be served silently.
- **24× training speedup** by broadcasting the batch through PennyLane in one call
  instead of looping per sample.
- **Coordinate frames are explicit and verified.** The structure→assay join is
  checked residue-by-residue against the wildtype; a mismatched protein is dropped,
  not trained on. Getting this wrong is silently wrong, never a crash.
- **No single point of failure in the demo path.** The copilot has a fallback
  provider, the feed falls back to its committed cache, and both `/predict` paths
  return an explained error rather than a plausible-looking fabricated number.

---

## Repo layout

```
api/
  circuit.py              ansatz + encoding + readout, imported everywhere
  mutation_features.py    residue descriptors (BLOSUM62 from Biopython, burial)
  quantum_engine.py       SARS-CoV-2 VQC; loads weights.npz, reports shot noise
  panel_engine.py         cross-virus VQC; loads weights_panel.npz + burial.json
  panel_catalog.json      17 proteins, 12 organisms, sites + wildtypes (dropdowns)
  burial.json             per-residue burial from AlphaFold, verified
  train_vqc.py            training + classical baselines + 3-seed spreads
  build_burial_features.py   burial from AF2 structures, with wildtype verification
  proteingym_loader.py    builds the multi-virus panel (phenotype-filtered)
  bootstrap_gap.py        paired bootstrap: which gaps to classical are real?
  epistasis_ceiling.py    the lookup-oracle ceiling + transfer matrix
  specialist_vs_pooled.py  one model per background vs one pooled (a measured null)
  epidemiology.py         SEIR via scipy solve_ivp
  sentinel.py             NCBI ingestion, alignment, scoring, auto-refresh
  copilot.py              Gemini -> Grok provider chain
  vqe.py                  VQE endpoints (precomputed H2 results)
  main.py                 FastAPI (both models)
notebooks/vqe_h2.ipynb    real VQE vs exact diagonalization
RESULTS.md                every measured number, including the nulls
src/App.jsx               the dashboard (Score a variant + Other viruses tabs)
src/glossary.js           plain-English definitions and sources
```

---

## Known limitations

1. Residue descriptors are a coarse representation. ESM-2 embeddings are the
   natural upgrade; we have **not** switched that on, so we do not claim it.
2. Trained on single mutants only — epistasis is not modelled.
3. Substitutions only; insertions and deletions are out of scope.
4. The cross-virus model scores **only** the 17 structure-verified proteins, at
   sites present in the solved structure. It is not a universal protein scorer.
5. Cross-protein AUC (0.68) is lower than within-SARS-CoV-2 AUC (0.74) because it
   is a harder task; the two numbers are not directly comparable.
6. Raw-AUC honesty, per model: the SARS-CoV-2 model trails the classical
   baselines on what is a near-linear task (logistic regression is the strongest
   classical model there, so a quantum feature map has little to add). The
   cross-virus model **beats logistic regression and is level with the best
   classical baseline on 63 parameters**, and its 10-restart ensemble beats every
   classical baseline (0.6903). What we defend is parameter/qubit efficiency and
   honest measurement — and a real quantum-competitive result on the harder task.
7. The VQE panel serves a **precomputed** real VQE on H₂ only — small enough to
   diagonalize exactly and prove the answer right.
8. SEIR assumes homogeneous mixing, constant R₀ and no interventions.

## Responsible use

Q-VIRA scores **observed** variants to help prioritise surveillance. It does not
propose or design novel mutations, and it is not a clinical tool.

## Acknowledgements

Starr et al. (2020) for the SARS-CoV-2 DMS data; the ProteinGym benchmark (Notin
et al.) and the Bloom lab for the multi-virus DMS assays; AlphaFold (Jumper et
al.) for the structures behind the burial feature; Pérez-Salinas et al. (2020)
for data re-uploading; Lan et al. (2020) / PDB 6M0J for the RBD–ACE2 complex;
BLOSUM62 via Biopython; PennyLane, FastAPI, NCBI E-utilities.

Developed with AI assistance for code generation and review. All modelling,
ablation and validation decisions are the team's own.

## Licence

MIT — see LICENSE.
