# Q-VIRA measured results

Every number here was produced by `train_vqc.py` on real deep-mutational-scanning
data. Nothing is estimated. Headline figures are reported as **mean ± sample
standard deviation across 3 random restarts**, not a single seed — a Round 2
discipline (see "Why multi-seed", below).

There are **two shipped models**:

| | SARS-CoV-2 specialist | Cross-virus generalist |
|---|---|---|
| Data | Starr et al. 2020 RBD DMS, 2,856/946 rows | ProteinGym, 146,161 rows, 17 proteins |
| Split | grouped by **site** | grouped by **protein** (held-out virus) |
| Circuit | 2 qubits · 6 layers · 41 params | 3 qubits · 6 layers · 63 params |
| Encoding / readout | dense (Y,Z) · full distribution | dense (Y,Z) · full distribution |
| Features | blosum62, wt_vol, Δvol, **ace2_distance** | blosum62, wt_vol, Δvol, wt_hydro, Δhydro, **burial** |
| **Held-out AUC** | **0.7423 ± 0.0016** | **0.6812 ± 0.0022** |

---

## Model 1 — SARS-CoV-2 specialist

**Task:** predict `bind_avg ≥ −1.0` (mutant retains ACE2 binding). **Split:**
grouped by site — 151 train sites (2,856 rows) / 50 test sites (946 rows). Test
positive rate 0.684.

| Model | Held-out AUC | Brier | precision@100 | clean prefix* |
|---|---|---|---|---|
| Logistic regression | 0.7796 | 0.1734 | 1.00 | 104 |
| Neural network (MLP) | 0.7706 | 0.1771 | 1.00 | 110 |
| Support vector machine | 0.7576 | 0.2017 | 0.97 | 78 |
| **VQC (ours)** | **0.7423 ± 0.0016** | **0.189** | **0.99** | **97** |
| chance | 0.5000 | — | 0.78 | 1 |

\* *clean prefix = how far down the ranking before the first false positive.*

**The honest claim.** On raw AUC the VQC trails all three classical baselines on
identical features and an identical split — we report the gap rather than hide
it. What changed in Round 2 is the **cost**: this model reaches the same accuracy
as the Round 1 model (0.7468, 4 qubits, 74 parameters) on **2 qubits and 41
parameters** — half the qubits, 45% fewer parameters — by switching to a dense
encoding and a full-distribution readout. On the metrics that matter for a triage
tool (calibration, top-of-list precision) it is level with logistic regression.

**Read AUC, not accuracy.** The dataset is 68% positive, so every model scores
~0.69–0.73 accuracy by mostly answering "yes". Accuracy is uninformative here.

---

## Model 2 — cross-virus generalist

**Data:** the 17 ProteinGym "Growth" (organismal-fitness) viral assays — one
coherent phenotype — 146,161 single mutants across **12 organisms** (influenza
×7 proteins, HIV-1 ×6, dengue, coxsackievirus, and more). **Split:** grouped by
**protein**: no protein appears in both halves, so test AUC measures
generalisation to a virus the model has never seen.

| Model | Held-out AUC (protein-held-out) |
|---|---|
| MLP | 0.6840 |
| Support vector machine | 0.6833 |
| **VQC (ours)** | **0.6812 ± 0.0022** |
| Logistic regression | 0.6760 |

Per held-out protein (VQC): influenza/Wu-2014 0.705, influenza/Soh-2019 0.703,
influenza-PA/Wu-2015 0.685, coxsackievirus-B3 0.667 (mean 0.690).

Here the circuit is **level with the classical baselines** — all four within
0.008. Cross-protein prediction is harder than within-protein, so 0.68 is not
comparable to Model 1's 0.74; they answer different questions.

---

## Round 2 measured results

### Burial: a structural feature that generalises across viruses

Model 1's strongest descriptor, `ace2_distance`, is measured from one complex
(PDB 6M0J) and is meaningless for any other virus. Its protein-agnostic cousin is
**residue burial** — contacts within 10 Å in the protein's own AlphaFold fold.
Adding it to the cross-virus model, identical split and architecture, 3 seeds:

| Cross-virus model | Held-out AUC |
|---|---|
| 5 features (no burial) | 0.6547 ± 0.0016 |
| **6 features (+ burial)** | **0.6812 ± 0.0022** |

**+0.0265 AUC, restart ranges disjoint ([0.653,0.656] vs [0.679,0.683]), and all
four held-out proteins improved.** Training loss also fell (0.636 → 0.611), so it
is a better fit, not a lucky draw.

The structure→assay join was verified residue-by-residue against the assay
wildtype. Two proteins (Zika, HCV) whose AlphaFold numbering disagreed with the
DMS positions (wildtype-match 5% and 0%) were detected automatically and dropped
— their burial values would have been noise dressed as structure.

### Dense encoding: six features on three qubits

Angle encoding puts one feature on one qubit, so six descriptors would need six
qubits — and our Round 1 ablation measured that eight qubits hits a barren
plateau (0.558 AUC, loss stuck at 0.556). **Dense encoding** places two features
per qubit (one per rotation axis, Y then Z), so six descriptors ride on three
qubits — narrower than naive angle encoding, more information. Verified by direct
state-vector simulation: with the full ansatz all six features are "live" and
per-feature sensitivity is higher than the angle encoding's; the Y-before-Z
ordering is load-bearing, because RZ on |0⟩ encodes nothing.

### The optimal feature count scales with the dataset

| Model | 4 features | 6 features |
|---|---|---|
| SARS-CoV-2 (2,856 rows) | **0.7423** | 0.6785 |
| Cross-virus (112k train rows) | 0.6547 (5 feat) | **0.6812** |

On the small SARS-CoV-2 set, adding two descriptors **overfits** — AUC drops 0.07
while training loss *improves* (0.455 → 0.424), the textbook signature. On the
112k-row panel the same two descriptors help. A paired test on logistic
regression (7 parameters, cannot overfit at this scale) had favoured six features
at p<1e-30 — and generalising that to a 41–63-parameter circuit was our mistake,
caught by measuring the circuit directly. Feature sets do not transfer across
dataset sizes.

### Why multi-seed: variance shrinks with data

Restart-to-restart AUC standard deviation:

| Dataset | rows | seed sd |
|---|---|---|
| SARS-CoV-2 | 2,856 | up to ±0.020 |
| Cross-virus panel | 111,859 | ±0.002 |

At 2,856 rows one restart of the 4-feature model hit 0.780 while its siblings sat
at 0.745 — a single seed could have "beaten" logistic regression by luck. At 112k
rows the spread is ±0.002 and effects of 0.005 are resolvable. Several Round 1
single-seed comparisons were, in hindsight, inside their own noise; every Round 2
headline is a 3-seed spread for that reason.

### Expanding the database 38× does not by itself raise AUC

A SARS-CoV-2 **genetic-background** panel (8 backgrounds, 41k rows) added rows but
almost no new information: because the descriptors are functions of
`(site, wildtype, mutant)`, **90% of the pooled rows were feature-vector
duplicates** of another row with a possibly-different label. Distinct feature
vectors went from 3,802 to ~4,200. More *proteins* (different residues at
different sites) is what added real signal — 3,802 → 105,894 distinct vectors,
~28×.

### Measured null results

Three things we expected to help and measured as doing nothing — reported because
a null is a result:

- **blosum62 clamp recalibration.** The BLOSUM score never exceeds +3 in the data
  (the matrix's +11 is for identical residues, which are filtered out), so the
  original (−4, 11) clamp used 47% of the angle range. Narrowing it to (−4, 3)
  doubled the resolution — and changed panel AUC by nothing: 0.6812 (−4,11) vs
  0.6796 (−4,3), overlapping ranges.
- **One model per genetic background vs one pooled model** (SARS-CoV-2 backgrounds):
  specialist mean 0.7644 vs pooled 0.7651 — a dead heat, specialists winning 4 of
  8. The backgrounds transfer to each other at 0.96–0.998, so pooling costs
  nothing and specialisation gains nothing. (Across genuinely different *proteins*
  the story differs — that is the generalist model above.)
- Both are in `specialist_vs_pooled.py` and the training logs.

### The lookup-oracle ceiling

Looking up how the same substitution behaved in a *related genetic background*
scores **0.9814 AUC** (leave-one-genotype-out) — but that is a lookup table, not
a model, and it needs measurements that a novel pathogen does not have. Our
site-grouped and protein-grouped splits forbid that lookup by construction, which
is exactly why the honest numbers are 0.74 and 0.68 and not the ~0.95 a random
split would report. The gap between them is the value of the deep-mutational-scan
data itself. See `epistasis_ceiling.py`.

### How precisely is the SARS-CoV-2 gap known?

`bootstrap_gap.py` resamples the 946 held-out rows 10,000 times, paired (both
models score identical rows on every draw). Each model's own 95% interval is
~0.06 wide on this many rows, so on **one** test set the models sit within
sampling noise of each other. Note: the committed `bootstrap_gap.json` was
produced for the Round 1 model; rerun `python bootstrap_gap.py` to regenerate it
against the shipped 2-qubit weights. The 3-seed spread above (±0.0016) is the
current headline evidence.

---

## Round 1 ablations (still valid)

These drove the original design and remain true; the shipped circuit has since
moved to a dense encoding, but the *feature* conclusions carry over.

### Structure beats more chemistry

Adding more residue descriptors *hurt* (8 features 0.640 vs 4 features 0.682 on
the pre-structure model). The missing information was spatial, not chemical.
Minimum heavy-atom distance from each RBD residue to ACE2, from PDB 6M0J
(validated: <4.5 Å reproduces all 17 literature ACE2-contact residues):

| Feature set (MLP, same split) | AUC |
|---|---|
| 4 features with `relative_position` | 0.7573 |
| **4 features with `ace2_distance`** | **0.7772** |
| 5 features (both) | 0.7329 |

`ace2_distance` alone scores 0.7143 — the strongest single feature. Adding it as
a 5th feature was worse than *replacing* `relative_position`, so it replaced it.
Effect on the VQC: **+0.065**, the largest single gain in the project, from one
number per site at zero runtime cost.

### Depth and width are not independent

6 layers *helped* at 4 qubits but *hurt badly* at 8 (0.558, loss never below
0.556) — a barren-plateau signature. Wider circuits hit trainability problems at
a depth narrower ones tolerate. This is the evidence for dense encoding in Round
2: keep the circuit narrow, carry more features per qubit.

### The failure worth presenting

The first training run plateaued at exactly the entropy of the class prior — a
model collapsed to the base rate. Cause: whole-sequence-average features, where
one substitution in a 201-residue protein shifts the average by <0.05 rad.
Switching to substitution-level descriptors fixed it. Diagnosing a silent failure
from the loss value alone is a stronger answer to "how do you know it works?"
than any single metric.

### 24× training speedup

Broadcasting the batch through PennyLane in one call versus a per-sample loop:
21.96 s → 0.91 s for 3 optimiser steps at 8 qubits. Identical mathematics.

### Surveillance-feed findings (live NCBI)

Running against real deposits surfaced problems curated data would not:
exact-length matching rejected 100% of records (fixed with Smith–Waterman local
alignment); deposits arrive in batches (40 records → ~11–14 distinct RBD sets);
and a shared Omicron-era background tied naive ranking at the top, fixed by
ranking on each deposit's *distinguishing* mutations.

---

## What to claim, and what not to

**Say:** "Two trained models. The SARS-CoV-2 specialist reaches 0.742 ± 0.002
AUC on **2 qubits and 41 parameters** — the Round 1 accuracy at half the qubits.
The cross-virus generalist reaches 0.681 ± 0.002 across 12 organisms,
protein-held-out, level with every classical baseline on identical features. A
structure-derived burial feature added +0.027 and improved all four held-out
proteins. Every headline is a 3-seed spread, and the design decisions — dense
encoding, feature count, the burial feature — were each driven by measurement,
several of them overturning our first guess."

**Do not say:** quantum advantage; outbreak prediction; any accuracy figure as
evidence of quality on imbalanced data; that the cross-virus 0.68 and the
SARS-CoV-2 0.74 are comparable (different tasks); or any number for the
single-encoding-vs-re-uploading ansatz choice — that ablation has not been run.
