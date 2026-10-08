# Q-VIRA — which mutation should a lab test first?

**Team BioQubit Labs · Quantum Biotech & Chemistry · Q-Hack India 2026**

Labs deposit new coronavirus sequences every day, and someone has to decide which
mutations are worth bench time — characterising one takes two to six weeks.
Q-VIRA scores each amino-acid substitution with a trained 4-qubit variational
circuit and puts the results in order, so limited capacity goes to the right
change first. It produces a triage order, not a verdict.

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
- Takes a reference protein and a list of substitutions (`N501Y E484K`)
- Describes each substitution with four residue descriptors, chosen by ablation
- Scores it with a trained 4-qubit data re-uploading VQC (PennyLane)
- Reports held-out AUC alongside logistic regression, SVM and an MLP **on
  identical features and an identical split**
- Projects an SEIR epidemic **scenario** from the score (scipy `solve_ivp`)
- Runs a real VQE on H₂, benchmarked against exact diagonalization of the same
  Hamiltonian at every bond length

**What it does not do**

- It does **not** predict outbreaks. The SEIR curve is a scenario under stated
  assumptions, with R₀ mapped from the score across 0.8–4.0.
- It does **not** claim quantum advantage. Our VQC reaches 0.7468 AUC and trails
  all three classical baselines (0.7504–0.7799) on the same features. That
  comparison is in the app, on the results slide, and in the table below.
- It does **not** model epistasis. Training used single mutants only, so combined
  substitutions are scored independently and flagged when there are many.
- It is **trained on the receptor-binding domain only** — spike sites 331–531,
  201 residues. Substitutions outside that window are extrapolation and are
  flagged rather than hidden.
- It is **not validated outside SARS-CoV-2 / ACE2**. The descriptors are generic
  protein chemistry, so the model will return a score for any protein, but other
  viruses use different receptors (influenza → sialic acid, Ebola → NPC1) and the
  `ace2_distance` feature is measured from one specific complex. Those references
  are loaded but deliberately not selectable for scoring.
- It does **not** simulate protein–ligand binding on a quantum computer. That is
  ~10⁵ qubits away; see `notebooks/vqe_h2.ipynb` §5.
- It is **not** a clinical or public-health tool.

---

## Results

Real data: Starr et al. (2020) deep mutational scanning of the SARS-CoV-2 RBD —
4,221 single mutants across 201 sites, every one measured for ACE2 binding.

**Task:** predict `bind_avg >= -1.0` (the mutant retains binding).
**Split:** grouped **by site**. Mutations at one position are correlated, so a
random row split leaks. No site appears in both halves: 151 train sites (2,856
rows) / 50 held-out sites (946 rows).

| Model | Held-out AUC |
|---|---|
| Logistic regression | 0.7799 |
| Neural network (MLP) | 0.7661 |
| Support vector machine (RBF) | 0.7504 |
| **VQC — 4 qubits, 6 layers, 74 parameters** | **0.7468** |
| Always answer yes (chance) | 0.5000 |

We place fourth of five. The VQC lands within 0.004 AUC of the SVM —
indistinguishable on 946 rows — and trails logistic regression by 0.033.

Read AUC, not accuracy: the dataset is 68% positive, so every model scores
~0.69–0.73 accuracy by mostly answering "yes".

Every ablation, including the configurations that lost, is in
**[RESULTS.md](RESULTS.md)**. The same table is served live from `GET /metrics`
and rendered in the app's model card, so the numbers on screen can be checked
against the API.

---

## Architecture

```
  NCBI deposits                     manual input
  (sentinel.py, self-refreshing)    (reference + N501Y E484K)
        │                                   │
        ▼                                   │
  Smith-Waterman local alignment            │
  vs Wuhan-Hu-1, RBD sites 331-531          │
        │                                   │
        └──────────────┬────────────────────┘
                       ▼
          mutation_features.py
          4 descriptors per substitution:
          BLOSUM62 · WT volume · Δ volume · ACE2 interface distance
                       ▼
          quantum_engine.py
          4-qubit data re-uploading VQC (PennyLane)
          weights.npz — never random
                       ▼
                score ∈ [0,1] + shot-noise error bar
                  │                     │
                  ▼                     ▼
          epidemiology.py          ranked triage list
          SEIR scenario            (surveillance feed)
          scipy solve_ivp

  Separate track: vqe.py — a real VQE on H2, benchmarked against exact
  diagonalization. Precomputed by build_vqe_data.py.
```

### The copilot runs on a provider chain

`copilot.py` tries **Gemini** first and falls through to **Grok** (xAI) on any
failure — a quota reset, a 429, a timeout, an outage, a renamed model. Both
providers get the same system prompt and the same grounding context, so an answer
does not change character when the chain falls through, and the reply says which
provider served it.

The model **explains**; it never computes. Every figure it quotes is passed in
from the endpoints above, and the system prompt forbids inventing numbers. Either
`GEMINI_API_KEY` or `XAI_API_KEY` alone is enough; with both, a demo survives one
provider going down mid-question.

If xAI renames a model (`grok-3-mini` → `grok-4` → `grok-4.7` …), the chain asks
`/v1/models` what the key can actually use and retries once, rather than 404ing
on a name hard-coded months earlier.

### The surveillance feed refreshes itself

The committed `sentinel_cache.json` is a **seed, not a ceiling**. A page load is
always served from memory — nothing ever waits on NCBI — and when the feed passes
`SENTINEL_MAX_AGE_HOURS` (12 by default) a worker thread re-queries NCBI and
swaps the fresh payload in. The app shows the real fetch time and its age, and a
button fires the background job on demand.

The host's disk is ephemeral, so the fresh payload lives in memory; a restart
falls back to the committed cache and triggers another refresh. Counts in this
README are from one such fetch and move as the feed updates.

---

## Why quantum, honestly

The case for a VQC here is expressivity per parameter, not speed. Ours carries 74
parameters. At 4 qubits the state is 16-dimensional and trivially classically
simulable — that is the point of working at this scale: everything is verifiable.

What we can defend is that **three design decisions were driven by measurement,
and all three contradicted the intuitive answer:**

1. **Structure beat more chemistry.** Replacing a sequence-position feature with
   ACE2 interface distance, measured from PDB 6M0J, took the VQC from 0.682 to
   0.747 — **+0.065, the largest single gain in the project** — from one number
   per site, looked up at zero runtime cost.
2. **Fewer features beat more.** Four descriptors (0.747) beat all eight (0.640).
   The four we dropped score 0.504–0.577 alone, close to noise, and each one
   costs a qubit and more parameters.
3. **Depth and width are not independent.** Six layers *helped* at 4 qubits
   (0.672 → 0.682) and *hurt badly* at 8 (0.640 → 0.558), where the deeper
   circuit never trained below 0.556 loss. Consistent with barren plateaus: a
   wider circuit hits trainability problems at a depth a narrower one tolerates.
   This is why the shipped model is narrow and six layers deep, rather than
   either "deeper is better" or "shallower is better".

Our ansatz is data re-uploading (Pérez-Salinas et al. 2020), which re-encodes the
input before every entangling layer. We chose it from the literature; we have
**not** run a controlled single-encoding-versus-re-uploading ablation on this
dataset, so we make no numerical claim about what it bought us.

---

## Deploying

Step-by-step checklist in **[DEPLOY.md](DEPLOY.md)**.

## Setup

### Backend

```bash
cd api
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

# 1. Reference panel, built from real NCBI sequences
python build_panel.py
python build_vqe_data.py      # H2 Hamiltonians for the VQE panel (needs pyscf)
# structural feature, from the experimental RBD/ACE2 complex:
#   download https://files.rcsb.org/download/6M0J.pdb
python build_structure_features.py 6M0J.pdb

# 2. Training data (Git LFS — a plain download gives a pointer file)
git lfs install
git clone https://github.com/jbloomlab/SARS-CoV-2-RBD_DMS
mkdir -p data && cp SARS-CoV-2-RBD_DMS/results/single_mut_effects/single_mut_effects.csv data/

# 3. Train (~12 min). Writes weights.npz and metrics.json.
#    Defaults (6 layers, 120 epochs, lr 0.05) reproduce the shipped model.
python train_vqc.py --data data/single_mut_effects.csv

# 4. Seed the surveillance cache from NCBI (needs internet)
python sentinel.py

# 5. Serve
uvicorn main:app --reload
```

Without `weights.npz`, `/predict` returns **503**. The API will not emit a score
from untrained parameters.

**Reproduce the ablations:**

```bash
python train_vqc.py --data data/... --all-features           # all 8 -> 0.640
python train_vqc.py --data data/... --qubits 8               # wider -> 0.640
python train_vqc.py --data data/... --qubits 8 --layers 6    # wider + deeper -> 0.558
```

### Frontend

```bash
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.local
npm run dev
```

The interface follows the operating system's light/dark preference on a first
visit and remembers the choice afterwards; a toggle in the masthead switches it.

### Deploy

| | |
|---|---|
| Frontend (Vercel) | auto-detects Vite. Set `VITE_API_URL` to the Render URL, then redeploy. |
| Backend (Render) | `render.yaml` included. Set `ALLOWED_ORIGINS` to the Vercel URL, plus `GEMINI_API_KEY` and/or `XAI_API_KEY`. |

Render's free tier sleeps after ~15 minutes idle and takes ~50 s to wake. The
frontend pings `/` on load, retries for about two minutes, and says what it is
waiting for rather than showing an error for a working system.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Honest status: model trained or not, panel size, copilot providers, feed age |
| `GET /metrics` | Held-out metrics from the last training run |
| `GET /references` | Reference sequences available for scoring |
| `POST /predict` | `{"reference_name": "...", "mutations": ["N501Y"]}` → per-substitution scores |
| `POST /seir` | `{"r0": 2.5}` → full SEIR curve, peak day, attack rate |
| `GET /vqe/geometries` | Bond lengths available, with exact reference energies |
| `POST /vqe` | VQE result at one geometry, with its convergence trace |
| `GET /vqe/curve` | VQE across the full H₂ dissociation curve |
| `GET /sentinel` | Surveillance feed, plus `feed_status` (fetch time, age, refreshing) |
| `POST /sentinel/refresh` | Starts a background NCBI re-query and returns immediately |
| `POST /copilot` | Explainer on the Gemini → Grok chain, grounded in the run's real numbers |

`/predict` also accepts `{"reference": "...", "variant": "..."}` for two
equal-length sequences. Every response carries a `model_card` block with its
caveats.

---

## What the surveillance feed found

Running against real NCBI deposits surfaced two problems that curated test data
would never have shown. (Counts below are from one fetch; they move as the feed
refreshes.)

1. **Batch duplication.** 40 fetched records collapsed to 14 distinct RBD
   mutation sets — deposits arrive in submission batches. Listing all 40 would
   have implied 40 findings where there was a handful. Identical mutation sets
   are now collapsed with a count.

2. **A shared background that destroys ranking.** 11 RBD mutations were present
   in *every* deposit. Ranking each record by its highest-scoring mutation tied
   everything near the top and conveyed nothing. The feed now sets aside the
   shared background and ranks by each deposit's **distinguishing** mutations,
   which produces real separation (0.871 L441I, 0.868 K444R, 0.849 K417N).

Both are visible in the app: shared mutations stay grey, unique ones are
highlighted, and each lane's score is drawn as a bar.

## Engineering notes

- **24× training speedup** by broadcasting the batch through PennyLane in one
  call instead of looping per sample (0.91 s vs 21.96 s for 3 optimiser steps at
  8 qubits). Full training went from ~6 hours to 141 seconds.
- **Dependencies are pinned, including transitive ones.** `autoray` ≥0.8 removed
  `NumpyMimic`, which PennyLane 0.39 calls at import; Qiskit 1.0 removed
  `qiskit.algorithms`. Unpinned installs are how a demo works on Monday and
  breaks on Friday.
- **Alignment, not index arithmetic.** The first sentinel required deposited
  sequences to match the reference length exactly and rejected 100% of real
  records (partial sequences, indels). Smith–Waterman local alignment of the RBD
  fixed it, with an 80% coverage threshold.
- **Coordinate frames are explicit.** The DMS data indexes spike sites 331–531
  while NCBI references are full-length (1,273 aa), so the API maps spike
  coordinates back into the trained window. Getting this wrong is silently wrong,
  never a crash.
- **No long work inside a request.** The VQE optimisation runs offline and the
  NCBI fetch runs on a worker thread. Endpoints answer in milliseconds.
- **No single point of failure in the demo path.** The copilot has a fallback
  provider, the feed falls back to its committed cache, and `/predict` returns 503
  with an explanation rather than a plausible-looking number.
- **Width is enforced in code.** `quantum_engine.py` refuses to load weights whose
  qubit count disagrees with the featuriser, rather than scoring nonsense.

---

## Seeing the results in the app

The masthead shows the held-out AUC and opens a **model card** rendered live from
`GET /metrics` — every model's AUC on identical features and the identical split,
drawn as a ranked bar chart with ours fourth of five. Accuracy is deliberately not
shown: the dataset is 68% positive, so every model scores ~0.70 by mostly
answering "yes".

## Repo layout

```
api/
  mutation_features.py  8 descriptors, 4 SELECTED (BLOSUM62 from Biopython)
  features.py           whole-sequence descriptors, used for the reference panel
  quantum_engine.py     VQC; loads trained weights, reports shot noise
  epidemiology.py       SEIR via scipy solve_ivp
  reference_panel.py    nearest neighbour; declines to match when nothing is close
  build_panel.py        builds the panel from real NCBI sequences
  sentinel.py           NCBI ingestion, alignment, scoring, ranking, auto-refresh
  copilot.py            Gemini -> Grok provider chain for /copilot
  vqe.py                VQE endpoints (serves precomputed results)
  build_vqe_data.py     precomputes H2 Hamiltonians + VQE runs (needs pyscf)
  build_structure_features.py  per-residue distance to ACE2 from PDB 6M0J
  ace2_distance.json    the resulting structural feature (committed)
  train_vqc.py          training + classical baselines -> weights.npz, metrics.json
  main.py               FastAPI
notebooks/vqe_h2.ipynb  real VQE vs exact diagonalization + why it does not scale
docs/JURY_QA.md         Q&A preparation
RESULTS.md              every measured number, including the failures
src/App.jsx             the dashboard
src/index.css           the design system, light and dark
```

---

## Known limitations

1. Four residue descriptors are a coarse representation. ESM-2 embeddings are the
   natural upgrade; we have **not** switched that on, so we do not claim it.
2. Trained on single mutants only — epistasis between combined mutations is not
   modelled.
3. Substitutions only. Insertions and deletions are out of scope.
4. Only SARS-CoV-2 is selectable for scoring. The other reference proteins are
   fetched and stored but deliberately not offered, because the model has no
   validation for their receptors.
5. The feed refreshes on a 12-hour cycle, not per page load. NCBI rate-limits
   queries, so a fetch runs in the background and the page is served from memory.
   The timestamp shown is the real fetch time, never a page-load time.
6. Deposited sequences carry ~30 co-occurring Omicron-era RBD mutations. The model
   was trained on **single** mutants, so those scores ignore epistasis and are
   flagged as weak evidence. The model is most useful for newly emerging single
   mutations on a current backbone; retraining on a contemporary DMS dataset is
   the clear next step.
7. The VQE panel serves a **precomputed** optimisation. It is a real VQE, run once
   by `build_vqe_data.py`; optimising inside a web request blocked the server.
   Reproduce any point with `notebooks/vqe_h2.ipynb`.
8. The VQE covers H₂ only, by design — small enough to diagonalize exactly and
   prove the answer right.
9. SEIR assumes homogeneous mixing, constant R₀ and no interventions.

## Responsible use

Q-VIRA scores **observed** variants to help prioritise surveillance. It does not
propose or design novel mutations, and it is not a clinical tool.

## Acknowledgements

Starr et al. (2020) for the DMS data. Pérez-Salinas et al. (2020) for data
re-uploading. Lan et al. (2020) / PDB 6M0J for the RBD–ACE2 complex. BLOSUM62 via
Biopython. PennyLane, FastAPI, NCBI E-utilities.

Developed with AI assistance (Gemini and Claude) for code generation and review.
All modelling, ablation and validation decisions are the team's own.

## Licence

MIT — see LICENSE.
