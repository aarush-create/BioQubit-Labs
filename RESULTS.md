# Q-VIRA measured results

Every number here was produced by `train_vqc.py` on the real Starr et al. (2020)
SARS-CoV-2 RBD deep mutational scanning dataset. Nothing is estimated.

- **Data:** 4,221 single mutants across 201 sites
- **Task:** predict `bind_avg >= -1.0` (mutant retains ACE2 binding)
- **Split:** grouped BY SITE — 151 train sites (2,856 rows) / 50 test sites (946 rows)
- **Test positive rate:** 0.684, so majority-class accuracy is 0.684

## Final model

**4 qubits · 6 layers · 74 parameters · data re-uploading ansatz**
Features: `blosum62`, `wt_volume`, `delta_volume`, **`ace2_distance`**

| Model | Held-out AUC |
|---|---|
| majority_class | 0.5000 |
| **VQC (quantum)** | **0.7468** |
| svm_rbf | 0.7504 |
| mlp | 0.7661 |
| logistic_regression | 0.7799 |

The VQC lands within **0.004 AUC of the SVM** — statistically indistinguishable
on 946 test rows — and trails logistic regression by 0.033. The gain came
entirely from replacing a sequence-position feature with a structural one, not
from a bigger circuit.

Note on reproducibility: this run scored 0.7468 on Windows and 0.7506 on Linux
with the identical seed and command. Mini-batch accumulation order differs in
floating point across platforms. We report the run that produced the shipped
`weights.npz`.

**Read AUC, not accuracy.** All models score ~0.69–0.73 accuracy because they
mostly answer "yes" on a 68%-positive dataset. Accuracy is uninformative here.

**The honest claim:** the VQC reaches 0.747, clearly above chance but below all
three classical baselines on identical features. We report the gap rather than
hide it.

## How precisely is any of this known?

The headline table is read off **one** held-out set of 946 rows, so before
treating "fourth of five" as a fact about the models, it is worth asking how
precisely 946 rows pin an AUC down at all.

`bootstrap_gap.py` answers that. It loads the committed `weights.npz` — so it
describes the deployed model, not a fresh run — reproduces the shipped split,
and resamples the held-out rows 10,000 times. The comparison is **paired**: on
every draw both models score the identical resampled rows, which is the correct
test for a difference measured on one shared test set, and is tighter than
comparing two independent confidence intervals.

Each model's own 95% interval is about 0.06 wide:

| Model | AUC | 95% CI | width |
|---|---|---|---|
| Logistic regression | 0.7799 | [0.7496, 0.8085] | 0.059 |
| Neural network (MLP) | 0.7661 | [0.7357, 0.7955] | 0.060 |
| Support vector machine | 0.7504 | [0.7174, 0.7823] | 0.065 |
| **VQC (ours)** | **0.7468** | **[0.7139, 0.7786]** | **0.065** |

And the paired differences against our circuit:

| Gap vs VQC | mean | 95% CI | VQC wins | resolved at 95%? |
|---|---|---|---|---|
| Logistic regression | +0.0330 | [+0.0080, +0.0592] | 0.7% of resamples | **yes** |
| Neural network (MLP) | +0.0193 | [−0.0018, +0.0405] | 3.5% | no |
| Support vector machine | +0.0034 | [−0.0177, +0.0246] | 37.8% | no |

**Two of the three gaps include zero.** The SVM result in particular is pure
sampling noise — resample the test rows and our circuit comes out ahead more
than a third of the time. Only logistic regression is ahead by a margin this
test set can actually resolve.

This does not rescue the VQC into a win, and it is not meant to. It says the
ranking is a weaker statement than a league table implies: the honest summary is
*"logistic regression beats our circuit; the SVM and the MLP are not separable
from it on this much data."*

Reproduce:

```bash
cd api && python bootstrap_gap.py     # ~30 s, writes bootstrap_gap.json
```

## How we got there — three ablations

### 1. Feature count: fewer is better

Measured **before** ablation 5 replaced `relative_position` with `ace2_distance`,
so the VQC column here is the pre-structure model. The ordering is what matters:
adding descriptors past four made every model worse.

| Feature set | k | MLP AUC | VQC AUC |
|---|---|---|---|
| blosum62 only | 1 | 0.6548 | — |
| + wt_volume | 2 | 0.7046 | — |
| + relative_position | 3 | 0.7544 | — |
| **+ delta_volume (shipped)** | **4** | **0.7573** | **0.6816** |
| + wt_hydropathy | 5 | 0.7078 | — |
| all eight | 8 | 0.7136 | 0.6404 |

Halving the feature set improved **every** model. The four dropped descriptors
(delta_hydropathy 0.504 AUC alone, delta_charge 0.518, wt_hydropathy,
pro_gly_flag) are close to noise, and each costs a qubit and more parameters.

### 2. Univariate importance is misleading

Each feature's AUC on its own:

| Feature | AUC alone | Shipped? |
|---|---|---|
| blosum62 | 0.6548 | yes |
| wt_volume | 0.6315 | yes |
| delta_volume | 0.6053 | yes |
| relative_position | 0.6016 | yes |
| wt_hydropathy | 0.5769 | no |
| pro_gly_flag | 0.5395 | no |
| delta_charge | 0.5175 | no |
| delta_hydropathy | 0.5042 | no |

BLOSUM62 alone beats the entire original 4-feature model. But BLOSUM62 **by
itself** only reaches 0.655 — it needs the others. And `relative_position`
scores a mediocre 0.602 alone yet is the most costly feature to remove
(-0.040 AUC in drop-one-out). Features matter in combination, not isolation.

### 3. Circuit depth: deeper is worse

8 qubits, 40 epochs:

| Layers | Params | Final train loss | Held-out AUC |
|---|---|---|---|
| **3** | 74 | **0.4994** | **0.6404** |
| 6 | 146 | 0.5710 | 0.5581 |

Doubling depth made it substantially worse, and the deeper circuit never trained
below 0.556 loss. Consistent with barren plateaus — gradients shrink with depth
and the optimiser stalls. This is the evidence for keeping the circuit shallow
and matching width to feature count, instead of assuming more qubits help.

## Engineering: 24x training speedup

Evaluating the circuit once per sample in a Python loop, versus broadcasting the
whole batch through PennyLane in one call. Measured at 8 qubits on PennyLane
0.39, 3 optimiser steps:

| Strategy | Time |
|---|---|
| per-sample loop | 21.96 s |
| broadcast batch | 0.91 s |

Identical mathematics. Full 40-epoch training went from roughly 6 hours to
141 seconds for the final 4-qubit configuration.

## The failure worth presenting

The first training run plateaued at 0.5866 loss and never moved. That is exactly
the entropy of the class prior (0.5862) — the signature of a model collapsed to
predicting the base rate.

Cause: the original featuriser used whole-sequence averages. One substitution in
a 201-residue protein shifts those averages by under 0.05 rad out of a pi range,
so every variant looked like the same input. Switching to substitution-level
descriptors fixed it.

"We diagnosed a silent failure from the loss value alone" is a stronger answer to
"how do you know your model works?" than any single metric.

## Ablation 4 — can more capacity close the gap to classical?

A fair question: is the VQC behind because variational circuits are weaker here,
or because we under-trained it? We measured rather than assumed.

| Config | Params | Final train loss | Held-out AUC |
|---|---|---|---|
| 4 qubits, 3 layers, 40 epochs | 38 | 0.4994 | 0.6716 |
| **4 qubits, 6 layers, 120 epochs, lr 0.05 (shipped)** | **74** | **0.4635** | **0.6816** |
| 8 qubits, 3 layers, 40 epochs | 74 | 0.5434 | 0.6404 |
| 8 qubits, 6 layers, 40 epochs | 146 | 0.5710 | 0.5581 |

Doubling the depth and tripling the epochs at 4 qubits improved the held-out AUC
by +0.010, while the training loss fell much further (0.499 -> 0.464). The model
is fitting the training set better without generalising much better, which is the
signature of approaching the ceiling of this representation rather than of
under-training.

Note the interaction: 6 layers HELPED at 4 qubits and HURT badly at 8 qubits
(0.5581). Depth and width are not independent — wider circuits hit trainability
problems at a depth that narrower ones tolerate.

**Conclusion.** The gap to the classical baselines is not an artefact of
under-training. These runs predate ablation 5; after it the shipped VQC reaches
0.7468 against 0.7504 SVM, 0.7661 MLP and 0.7799 logistic regression — the same
ordering, a much smaller gap. With only four residue descriptors there is a
ceiling near 0.78, and the single Pauli-Z readout of a 4-qubit circuit does not
quite reach it. Closing it needs a richer representation (ESM-2 embeddings)
rather than a bigger circuit.

## Ablation 5 — structure beats more chemistry

Asked whether to add more residue descriptors, we had already measured that more
chemistry HURT (8 features: 0.640 vs 4 features: 0.682). The missing information
was not chemical but spatial: none of our descriptors knew WHERE in the folded
protein a mutation sits, and for ACE2 binding that dominates.

We computed the minimum heavy-atom distance from every RBD residue to ACE2 using
the experimental complex **PDB 6M0J** (`build_structure_features.py`). Validation:
residues at <4.5 A reproduce all 17 ACE2-contact residues reported in the
literature (417, 453, 455, 456, 486, 493, 501, 505 ...).

| Feature set (MLP, same split) | AUC |
|---|---|
| 4 features with `relative_position` | 0.7573 |
| **4 features with `ace2_distance`** | **0.7772** |
| 5 features (both) | 0.7329 |
| `blosum62` + `ace2_distance` only | 0.7713 |

Univariate: `ace2_distance` alone scores **0.7143**, versus 0.6016 for
`relative_position` and 0.6548 for `blosum62`. It is our strongest single feature.

Adding it as a 5th feature was WORSE than replacing — consistent with ablation 1.
So `relative_position` was replaced, and the circuit stayed at 4 qubits.

**Effect on the VQC: 0.6816 -> 0.7468 (+0.065).** The largest single gain in the project,
from one number per site looked up at zero runtime cost.

Sanity check on the learned behaviour: A380V (21.4 A from the interface) scores
0.92 — likely to retain binding — while N501Y (3.4 A) scores 0.41. The model
learned that interface mutations are the ones that risk breaking binding. Note
N501Y in reality *enhances* ACE2 affinity, so the model is wrong on that specific
famous case; it has learned the population tendency, not per-residue biology.

## What we did NOT measure: the ansatz

We use data re-uploading (Pérez-Salinas et al. 2020) because the literature
argues a single encoding followed by entangling layers is limited in the
functions it can express. We did **not** run a controlled single-encoding versus
re-uploading comparison on this dataset, so there is no number here for what the
choice bought us, and we do not quote one anywhere else.

Earlier drafts of this repo cited a 0.59 → 0.87 figure for that comparison. It
was not reproducible from any committed script, and 0.87 is above the shipped
model's own held-out AUC, so it has been withdrawn from every document. A
controlled ablation with the `--single-encoding` flag is the right way to settle
it, and it is on the Round 2 list.

## Caveat found in production: unresolved sites

The crystal structure 6M0J covers RBD residues 333-526. Sites outside it
(331-332, 527-531) receive a far-field fallback distance of 45 A, which the
model reads as "maximally far from the interface" and therefore scores highly.

This surfaced on a real NCBI batch: the top-ranked drivers were L335F, L517F,
K529T, K529N and I332V — and 332 and 529 are precisely the unresolved sites.
The ranking was being driven by MISSING DATA rather than by signal.

Fix: sites without structural coverage are flagged (`has_structure: false`),
shown with a dashed border and an asterisk, and EXCLUDED from ranking. They are
still displayed, because hiding them would be its own distortion.

## Real-world findings from the surveillance feed

Running the pipeline against live NCBI deposits (40 records, Oct 2026) produced
three findings that curated test data would not have surfaced.

**1. Exact-length matching rejects everything.** The first implementation
required deposited sequences to match the 1,273-residue reference exactly.
Result: 0 analysed, 40 skipped. Real deposits are frequently partial or carry
indels elsewhere in the spike. Smith-Waterman local alignment of the RBD, with
an 80% coverage threshold, analysed 40/40 at 100% coverage.

**2. Deposits arrive in batches.** 40 records collapsed to 11 distinct RBD
mutation sets, one group containing 13 identical deposits. Listing them
separately would overstate the number of findings.

**3. A shared background destroys naive ranking.** In that batch, 22 RBD
mutations were present in *every* deposit — the Omicron-era inheritance. Ranking
by each record's highest-scoring mutation tied all 11 variants at exactly 0.910
(R403K). Ranking by each deposit's *distinguishing* mutations instead produced
real separation:

| Deposit | Top distinguishing mutation | Score | Distinguishing / total RBD |
|---|---|---|---|
| YGY72459.1 | L441I | 0.871 | 10 / 32 |
| YGY72649.1 | K444R | 0.868 | 10 / 32 |
| YGY72613.1 | K417N | 0.849 | 7 / 29 |

**4. Current lineages are outside the model's training assumptions.** Deposits
carry 29-32 co-occurring RBD substitutions. The model was trained on SINGLE
mutants, so scoring these independently ignores epistasis, which is large in the
RBD. Records with >= 5 RBD substitutions are flagged as high-divergence, weak
evidence. The model is most useful for newly-emerging single mutations on a
current backbone; retraining on an Omicron-era DMS dataset is the clear next step.

## What to claim, and what not to

**Say:** "Our 4-qubit VQC reaches 0.747 AUC against a 0.5 chance baseline,
placing fourth of five — within 0.004 of the SVM and 0.033 behind logistic
regression on identical features and an identical split. Three ablations drove
the design: structure versus more chemistry, feature count, and the interaction
between depth and width. All three contradicted the intuitive answer."

**Do not say:** quantum advantage, outbreak prediction, any accuracy figure as
evidence of quality on this imbalanced dataset, or any number for the ansatz
choice — that ablation has not been run.
