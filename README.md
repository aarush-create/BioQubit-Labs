# Q-VIRA — Quantum-Classical Viral Variant Scoring

**Team BioQubit Labs · Quantum Biotech & Chemistry (Track 01) · Q-Hack India 2026**

A hybrid quantum-classical pipeline that scores SARS-CoV-2 receptor-binding-domain
variants with a trained 4-qubit variational circuit, and projects epidemic
scenarios from that score.

🔗 Live demo: _add your Vercel URL_
🎥 3-minute video: _add your link_

---

## What this is, and what it is not

**What it does**
- Pulls recently deposited SARS-CoV-2 spike proteins from NCBI, aligns them to
  Wuhan-Hu-1 (Smith-Waterman), scores their RBD substitutions, and ranks deposits
  by the mutations **unique** to each one — the surveillance loop, cached
- Takes a reference protein and a list of substitutions (`N501Y E484K`)
- Describes each substitution with 4 residue-property descriptors, chosen by ablation
- Scores it with a trained 4-qubit data re-uploading VQC (PennyLane)
- Reports held-out AUC alongside logistic regression, SVM and MLP **on identical features**
- Projects an SEIR epidemic **scenario** from the score (scipy `solve_ivp`)
- Runs a **live** VQE on H₂ in the dashboard (`POST /vqe`), benchmarked against
  exact diagonalisation of the same Hamiltonian at every bond length

**What it does not do**
- It does **not** predict outbreaks. The SEIR curve is a scenario under stated assumptions.
- It does **not** claim quantum advantage. Our VQC (0.747 AUC) trails the classical
  baselines (0.701–0.740) on the same features, and we say so on the results slide.
- It does **not** model epistasis. Training used single mutants only, so combined
  mutations are scored independently.
- It is **trained on the receptor-binding domain only** — spike sites 331–531
  (201 residues). The `relative_position` feature is position *within that
  window*, so the API maps user-supplied spike coordinates back into it.
  Substitutions outside 331–531 are extrapolation and are flagged.
- It is **not validated outside SARS-CoV-2 / ACE2**. The features are generic
  protein chemistry, so the model returns a score for any protein — but other
  viruses use different receptors (influenza → sialic acid, Ebola → NPC1), and
  `relative_position` learned which RBD positions contact ACE2 specifically.
  The API flags these as out of distribution and the UI shows a warning.
- It does **not** simulate protein-ligand binding on a quantum computer.
  That is ~10⁵ qubits away. See `notebooks/vqe_h2.ipynb` §5.
- It is **not** a clinical or public-health tool.

---

## Results

Real data: Starr et al. (2020) deep mutational scanning of the SARS-CoV-2 RBD —
4,221 single mutants across 201 sites, every one measured for ACE2 binding.

**Task:** predict `bind_avg >= -1.0` (mutant retains binding).
**Split:** grouped **by site**. Mutations at one position are correlated, so a
random row split leaks information. No site appears in both halves.

| Model | Held-out AUC |
|---|---|
| majority_class | 0.5000 |
| **VQC — 4 qubits, 3 layers, 38 params** | **0.7468** |
| svm_rbf | 0.7504 |
| mlp | 0.7661 |
| logistic_regression | 0.7799 |

Read AUC, not accuracy: the dataset is 68% positive, so every model scores
~0.70 accuracy by mostly answering "yes".

Full ablations, including the configurations that lost, are in **[RESULTS.md](RESULTS.md)**.

---

## Architecture

```
  NCBI deposits                     manual input
  (cached, sentinel.py)             (reference + N501Y E484K)
        │                                   │
        ▼                                   │
  Smith-Waterman local alignment            │
  vs Wuhan-Hu-1, RBD sites 331-531          │
        │                                   │
        └──────────────┬────────────────────┘
                       ▼
          mutation_features.py
          4 descriptors per substitution:
          BLOSUM62 · WT volume · Δvolume · ACE2 interface distance
                       ▼
          quantum_engine.py
          4-qubit data re-uploading VQC (PennyLane)
          weights.npz — never random
                       ▼
                score ∈ [0,1] + shot-noise error bar
                  │                     │
                  ▼                     ▼
          epidemiology.py          ranked triage list
          SEIR scenario            (sentinel feed)
          scipy solve_ivp

  Separate track: vqe.py — real VQE on H2, benchmarked against
  exact diagonalisation. Precomputed by build_vqe_data.py.
```

Gemini 3.1 Pro powers the copilot (`/copilot`). It **explains** results and its
system prompt forbids inventing numbers; every figure it quotes is passed in
from the endpoints above.

---

## Why quantum, honestly

The case for a VQC here is expressivity per parameter, not speed. Ours carries
38 parameters. At 4 qubits the state is 16-dimensional and trivially classically
simulable — that is the point of working at this scale: you can verify everything.

What we can defend is that **three design decisions were driven by measurement,
and all three contradicted the intuitive answer:**

1. **Fewer features beat more.** 4 descriptors (VQC 0.747) beat all 8 (0.640).
2. **Shallower beat deeper.** 3 layers (0.640) beat 6 layers (0.558) at equal
   width — consistent with barren plateaus.
3. **Univariate importance misleads.** `relative_position` scores 0.602 alone yet
   is the costliest feature to remove.

We also measured our own ansatz choice: the original single-encoding circuit
scored 0.59 AUC on our benchmark; data re-uploading (Pérez-Salinas et al. 2020),
which re-encodes the input before every entangling layer, raised it to 0.87.

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
python build_vqe_data.py      # H2 Hamiltonians for the live VQE (needs pyscf)
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

# 4. Build the surveillance cache from NCBI (needs internet)
python sentinel.py

# 5. Serve
uvicorn main:app --reload
```

Without `weights.npz`, `/predict` returns **503**. The API will not emit a score
from untrained parameters.

**Reproduce the ablations:**
```bash
python train_vqc.py --data data/... --all-features    # all 8  → 0.640
python train_vqc.py --data data/... --layers 6        # deeper → 0.558
python train_vqc.py --data data/... --features 4      # BLOSUM only
```

### Frontend

```bash
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.local
npm run dev
```

### Deploy

| | |
|---|---|
| Frontend (Vercel) | auto-detects Vite. Set `VITE_API_URL` to the Render URL, then redeploy. |
| Backend (Render) | `render.yaml` included. Set `ALLOWED_ORIGINS` to the Vercel URL and `GEMINI_API_KEY`. |

Render's free tier sleeps; the frontend pings `/` on load to warm it.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Honest status: backend, whether the model is trained, panel size |
| `GET /metrics` | Held-out metrics from the last training run |
| `GET /references` | Reference sequences available for variant scoring |
| `POST /predict` | `{"reference_name": "...", "mutations": ["N501Y"]}` → per-substitution scores |
| `POST /seir` | `{"r0": 2.5}` → full SEIR curve, peak day, attack rate |
| `GET /vqe/geometries` | Bond lengths available, with exact reference energies |
| `POST /vqe` | VQE result at one geometry + convergence (precomputed; `live:true` re-runs it) |
| `GET /vqe/curve` | VQE across the full H₂ dissociation curve |
| `GET /sentinel` | Cached surveillance feed: deposited spikes, scored and ranked |
| `POST /sentinel/refresh` | Re-query NCBI (guarded by `ALLOW_SENTINEL_REFRESH=1`) |
| `POST /copilot` | Gemini explainer, grounded in the run's real numbers |

`/predict` also accepts `{"reference": "...", "variant": "..."}` for two
equal-length sequences. Every response carries a `model_card` block with its caveats.

---

## What the surveillance feed found

Running it against real NCBI deposits surfaced two problems that curated test
data would never have shown:

1. **Batch duplication.** 40 fetched records collapsed to 11 distinct RBD
   mutation sets — deposits arrive in submission batches. Listing all 40 would
   have implied 40 findings where there was a handful. Identical mutation sets
   are now collapsed with a count.

2. **A shared background that destroys ranking.** 22 RBD mutations were present
   in *every* deposit. Ranking by each record's highest-scoring mutation tied
   everything at 0.910 and conveyed nothing. The feed now sets aside the shared
   background and ranks by each deposit's **distinguishing** mutations, which
   produces real separation (0.871 L441I, 0.868 K444R, 0.849 K417N).

Both are visible in the UI: shared mutations are greyed out, unique ones
highlighted.

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
  records (partial sequences, indels). Smith-Waterman local alignment of the RBD
  fixed it, with an 80% coverage threshold.
- **Coordinate frames are explicit.** The DMS data indexes spike sites 331–531
  while NCBI references are full-length (1,273 aa). `relative_position` is
  position *within the trained window*, so the API maps spike coordinates back
  into it. A naive index would put N501Y at 0.393 instead of 0.846 — silently
  wrong, never a crash.
- **No long work inside a request.** The VQE optimisation and the NCBI fetch both
  run offline; endpoints serve stored results in milliseconds.
- **Width is enforced in code.** `quantum_engine.py` refuses to load weights whose
  qubit count disagrees with the featuriser, rather than scoring nonsense.

---

## Seeing the results in the app

The dashboard header has a **Results** button. It opens a model card rendered
live from `GET /metrics` — the held-out AUC for the VQC alongside every
classical baseline, on identical features and the identical split. Accuracy is
deliberately not shown: the dataset is 68% positive, so every model scores
~0.70 by mostly answering "yes".

## Repo layout

```
api/
  mutation_features.py  8 descriptors, 4 SELECTED (BLOSUM62 from Biopython)
  features.py           whole-sequence descriptors, used for the reference panel
  quantum_engine.py     VQC; loads trained weights, reports shot noise
  epidemiology.py       SEIR via scipy solve_ivp
  reference_panel.py    nearest neighbour; declines to match when nothing is close
  build_panel.py        builds the panel from real NCBI sequences
  sentinel.py           NCBI ingestion, alignment, scoring, ranking
  vqe.py                VQE endpoints (serves precomputed results)
  build_vqe_data.py     precomputes H2 Hamiltonians + VQE runs (needs pyscf)
  build_structure_features.py  per-residue distance to ACE2 from PDB 6M0J
  ace2_distance.json    the resulting structural feature (committed)
  train_vqc.py          training + classical baselines → weights.npz, metrics.json
  main.py               FastAPI
notebooks/vqe_h2.ipynb  real VQE vs exact diagonalisation + why it does not scale
docs/JURY_QA.md         Q&A preparation
RESULTS.md              every measured number, including the failures
src/App.jsx             dashboard
```

---

## Known limitations

1. Four residue-property descriptors are a coarse representation. ESM-2
   embeddings are the natural upgrade; we have **not** switched that on, so we
   do not claim it.
2. Trained on single mutants only — epistasis between combined mutations is not modelled.
3. Substitutions only. Insertions and deletions are out of scope.
4. Only SARS-CoV-2 is selectable for scoring. The other eight reference proteins
   are fetched and stored, but are deliberately **not** offered in the scoring
   dropdown, because the model has no validation for their receptors.
5. The surveillance feed is **cached, not live**. NCBI is rate-limited and the
   host disk is ephemeral, so `sentinel.py` builds the cache offline and it is
   committed. The fetch timestamp is shown in the UI.
6. Deposited sequences carry ~30 co-occurring Omicron-era RBD mutations. The
   model was trained on **single** mutants, so those scores ignore epistasis and
   are flagged as high-divergence, weak evidence. The model is most useful for
   newly-emerging single mutations on a current backbone; retraining on a
   contemporary DMS dataset is the clear next step.
7. The VQE panel serves a **precomputed** optimisation. It is a real VQE, run
   once by `build_vqe_data.py`; optimising inside a web request blocked the
   server. Reproduce any point with `notebooks/vqe_h2.ipynb`.
6. The VQE covers H₂/LiH only, by design.
7. SEIR assumes homogeneous mixing, constant R₀, no interventions.

## Responsible use

Q-VIRA scores **observed** variants to help prioritise surveillance. It does not
propose or design novel mutations, and it is not a clinical tool.

## Acknowledgements

Starr et al. (2020) for the DMS data. Pérez-Salinas et al. (2020) for data
re-uploading. BLOSUM62 via Biopython. PennyLane, FastAPI, NCBI E-utilities.

Developed with AI assistance (Gemini 3.1 Pro and Claude) for code generation and
review. All modelling, ablation and validation decisions are the team's own.

## Licence

MIT — see LICENSE.
