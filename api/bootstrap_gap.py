"""Is the VQC-to-classical gap bigger than the noise on the test set?

An AUC ordering read off ONE held-out set of 946 rows invites the obvious
question: given only 946 rows, how precisely is any of these AUCs known, and is
the gap larger than that precision?

Method: the shipped weights and the shipped split, so this describes the model
that is actually deployed. Then a PAIRED bootstrap -- the same resampled rows
scored by both models on every draw, which is the correct test for a difference
measured on one shared test set. An unpaired comparison would overstate the
uncertainty by ignoring that both models see identical rows.

WHAT CHANGED, AND WHY IT MATTERED
---------------------------------
This script used to hardcode two things that silently went stale:

1. The ansatz and the readout were written out again here, as
   `sigmoid(r[0] * <Z_0> + r[1])`. With the current `probs` readout the
   parameter vector has 2^n + 1 entries, so r[0] and r[1] are just the first
   two basis weights. It would have produced a number with no error and no
   meaning. The circuit now comes from circuit.py, the one definition both
   training and serving use, and the readout kind is read from weights.npz.

2. The split was reproduced by hand as a TWO-way train/test split. Training now
   holds out validation sites as well, so fitting the baselines here on
   everything-but-test gave them ~25% more data than the VQC ever saw -- an
   unfair comparison that favoured the baselines. The split now comes from
   train_vqc.site_split, with the seed and val_frac read back out of
   metrics.json so this reproduces the run that produced weights.npz.

Baselines are fitted on the TRAIN rows only, matching what the VQC's gradients
saw and matching run_baselines() in train_vqc.py.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
from sklearn.metrics import roc_auc_score

API = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, API)

import train_vqc as T  # noqa: E402
from mutation_features import SELECTED  # noqa: E402
from circuit import make_qnode, predict_proba, n_readout_params  # noqa: E402
from pennylane import numpy as pnp  # noqa: E402

DATA = os.path.join(API, "data", "single_mut_effects.csv")
B = 10_000

# --- reproduce the run that produced weights.npz --------------------------
metrics_path = os.path.join(API, "metrics.json")
if os.path.exists(metrics_path):
    with open(metrics_path) as fh:
        meta = json.load(fh)
    seed = int(meta.get("split_seed", 0))
    val_frac = float(meta.get("split_val_frac", 0.2))
    if "split_seed" not in meta:
        print("NOTE: metrics.json predates split_seed/split_val_frac. "
              "Assuming seed=0, val_frac=0.2 -- if the shipped model was "
              "trained with other values this comparison is not valid.")
else:
    seed, val_frac = 0, 0.2
    print("NOTE: no metrics.json found; assuming seed=0, val_frac=0.2")

print(f"split: seed={seed} val_frac={val_frac}")

X_raw, y, sites, _ = T.load_dms(DATA)
cols = list(SELECTED)
X = T._scale_block(X_raw[:, cols], cols)

tr, va, te = T.site_split(sites, seed, val_frac)
Xtr, ytr = X[tr], y[tr]
Xte, yte = X[te], y[te]
print(f"train {tr.sum()} rows / {len(np.unique(sites[tr]))} sites | "
      f"val {va.sum()} rows | "
      f"test {te.sum()} rows / {len(np.unique(sites[te]))} sites")

# --- the shipped VQC, loaded not retrained --------------------------------
d = np.load(os.path.join(API, "weights.npz"), allow_pickle=True)
w = np.asarray(d["weights"], dtype=float)
r = np.asarray(d["readout"], dtype=float).ravel()

if "readout_kind" in d:
    rk = d["readout_kind"]
    kind = str(rk.item() if hasattr(rk, "item") else rk)
else:
    kind = "single_z"
    print("NOTE: weights.npz has no readout_kind; treating it as single_z")

n_q = Xtr.shape[1]
expected = n_readout_params(n_q, kind)
if r.size != expected:
    raise SystemExit(
        f"weights.npz has {r.size} readout parameters but readout_kind="
        f"{kind!r} at {n_q} qubits needs {expected}. Refusing to bootstrap a "
        f"mismatched model -- retrain, then re-run this."
    )
print(f"model: {n_q} qubits x {w.shape[0]} layers, readout={kind} "
      f"({r.size} readout params)")

qnode = make_qnode(n_q, kind)
raw = qnode(np.asarray(Xte, dtype=float), pnp.array(w, requires_grad=False))
p_vqc = np.asarray(
    predict_proba(raw, pnp.array(r, requires_grad=False), kind), dtype=float
)

# --- the classical baselines, same features, same TRAIN rows --------------
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.svm import SVC  # noqa: E402
from sklearn.neural_network import MLPClassifier  # noqa: E402

models = {
    "logistic regression": LogisticRegression(max_iter=2000),
    "neural network (MLP)": MLPClassifier(hidden_layer_sizes=(16,),
                                          max_iter=2000, random_state=0),
    "support vector machine": SVC(probability=True, random_state=0),
}
preds = {"VQC (ours)": p_vqc}
for name, mdl in models.items():
    mdl.fit(Xtr, ytr)
    preds[name] = mdl.predict_proba(Xte)[:, 1]

print("\npoint estimates (this is the deck table):")
for n, p in sorted(preds.items(), key=lambda kv: -roc_auc_score(yte, kv[1])):
    print(f"  {n:24} {roc_auc_score(yte, p):.4f}")

# --- paired bootstrap over the held-out rows ------------------------------
rs = np.random.default_rng(12345)
idx = np.arange(len(yte))
boot = {n: [] for n in preds}
diff = {n: [] for n in preds if n != "VQC (ours)"}
for _ in range(B):
    s = rs.choice(idx, len(idx), replace=True)
    if len(np.unique(yte[s])) < 2:
        continue
    a = {n: roc_auc_score(yte[s], p[s]) for n, p in preds.items()}
    for n, v in a.items():
        boot[n].append(v)
    for n in diff:
        diff[n].append(a[n] - a["VQC (ours)"])

print(f"\n95% CI per model, {B} paired bootstrap resamples of the "
      f"{len(yte)} held-out rows:")
for n in preds:
    v = np.array(boot[n])
    lo, hi = np.percentile(v, [2.5, 97.5])
    print(f"  {n:24} {roc_auc_score(yte, preds[n]):.4f}  "
          f"[{lo:.4f}, {hi:.4f}]  width {hi - lo:.4f}")

print("\nPAIRED difference vs our VQC (the question that matters):")
out = {"readout": kind, "split_seed": seed, "split_val_frac": val_frac,
       "n_test": int(len(yte)), "gaps": {}}
for n in diff:
    v = np.array(diff[n])
    lo, hi = np.percentile(v, [2.5, 97.5])
    p_over = float((v <= 0).mean())
    sig = ("RESOLVED (CI excludes 0)" if lo > 0
           else "NOT RESOLVED (CI includes 0)")
    print(f"  {n:24} {v.mean():+.4f}  [{lo:+.4f}, {hi:+.4f}]  "
          f"VQC wins in {p_over * 100:.1f}% of resamples  -> {sig}")
    out["gaps"][n] = dict(mean=round(float(v.mean()), 4),
                          lo=round(float(lo), 4), hi=round(float(hi), 4),
                          vqc_wins_pct=round(p_over * 100, 1),
                          resolved=bool(lo > 0))

with open(os.path.join(API, "bootstrap_gap.json"), "w") as fh:
    json.dump(out, fh, indent=2)
print("\nwrote bootstrap_gap.json")
