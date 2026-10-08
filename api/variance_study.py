"""
How big is the number, and how big is the error bar on it?

WHY THIS EXISTS
---------------
`train_vqc.py` reports one AUC from one site-grouped split with one random
initialisation. Three measurements say that single number cannot carry the
weight we were putting on it:

  1. A bootstrap over the 946 held-out rows gives a 95% CI roughly 0.06 wide.
     The 0.004 that separates our VQC from the SVM is a tenth of that.
  2. Re-drawing the site-grouped split moves logistic regression by up to 0.13
     AUC. Which sites land in the test half matters more than which model runs.
  3. Changing only the weight initialisation — same data, same split, same
     hyperparameters — moves the VQC by about 0.03.

So "we place fourth of five" was a statement about one split, not about the
models. This script produces the statement we can actually defend: mean and
standard deviation across folds and seeds, for every model, on identical
features.

It does NOT touch weights.npz or metrics.json. Training stays where it was;
this only measures.

USAGE
-----
    python variance_study.py --data data/single_mut_effects.csv            # full
    python variance_study.py --data ... --folds 2 --seeds 2 --epochs 40    # quick

Expect roughly (folds x seeds x epochs/120) x 30 minutes for the quantum part.
The classical part takes seconds, so --skip-vqc gives the split-variance
picture immediately.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import sys

import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)      # so this runs from any working directory

from mutation_features import NAMES, SELECTED   # noqa: E402
import train_vqc as T                           # noqa: E402


# --------------------------------------------------------------- splitting
def site_folds(sites, n_folds, seed=0):
    """Partition SITES (never rows) into n_folds disjoint test sets."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(sites)
    rng.shuffle(uniq)
    size = max(1, len(uniq) // n_folds)
    for f in range(n_folds):
        test_sites = set(uniq[f * size:(f + 1) * size].tolist())
        te = np.array([s in test_sites for s in sites])
        yield f, ~te, te


# ------------------------------------------------------------------ bootstrap
def bootstrap_ci(y, p, n=2000, seed=0):
    """95% CI on AUC by resampling the held-out rows. This is the resolution
    limit of any comparison made on this test set."""
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed)
    idx = np.arange(len(y))
    aucs = []
    for _ in range(n):
        s = rng.choice(idx, len(idx), replace=True)
        if len(np.unique(y[s])) > 1:
            aucs.append(roc_auc_score(y[s], p[s]))
    a = np.asarray(aucs)
    return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))


# ------------------------------------------------------------------- the VQC
def train_one(Xtr, ytr, Xte, n_layers, epochs, lr, batch, init_seed):
    """One VQC, one initialisation. Returns held-out probabilities."""
    n_q = Xtr.shape[1]
    dev = qml.device("default.qubit", wires=n_q)

    @qml.qnode(dev)
    def circuit(features, weights):
        for layer in range(weights.shape[0]):
            qml.AngleEmbedding(features=features, wires=range(n_q), rotation="Y")
            qml.StronglyEntanglingLayers(weights[layer:layer + 1], wires=range(n_q))
        return qml.expval(qml.PauliZ(0))

    def proba(X, w, r):
        return 1.0 / (1.0 + pnp.exp(-(r[0] * circuit(X, w) + r[1])))

    def loss(w, r, X, y):
        p = pnp.clip(proba(X, w, r), 1e-7, 1 - 1e-7)
        return -pnp.mean(y * pnp.log(p) + (1 - y) * pnp.log(1 - p))

    pnp.random.seed(init_seed)
    w = pnp.array(pnp.random.uniform(0, 2 * np.pi, (n_layers, n_q, 3)), requires_grad=True)
    r = pnp.array([1.0, 0.0], requires_grad=True)
    opt = qml.AdamOptimizer(stepsize=lr)

    Xp, yp = np.asarray(Xtr, float), np.asarray(ytr, float)
    for ep in range(epochs):
        perm = np.random.default_rng(ep).permutation(len(Xp))
        for s in range(0, len(perm), batch):
            i = perm[s:s + batch]
            w, r = opt.step(lambda ww, rr: loss(ww, rr, Xp[i], yp[i]), w, r)

    wf = pnp.array(w, requires_grad=False)
    rf = pnp.array(r, requires_grad=False)
    z = np.asarray(circuit(np.asarray(Xte, float), wf), dtype=float)
    return 1.0 / (1.0 + np.exp(-(float(rf[0]) * z + float(rf[1]))))


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=3, help="weight initialisations per fold")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--layers", type=int, default=6)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--skip-vqc", action="store_true",
                    help="classical models only — seconds instead of hours")
    a = ap.parse_args()

    from sklearn.metrics import roc_auc_score

    X_raw, y, sites, _ = T.load_dms(a.data)
    cols = list(SELECTED)
    X = T._scale_block(X_raw[:, cols], cols)
    print(f"features: {[NAMES[c] for c in cols]}")
    print(f"{len(y)} rows across {len(np.unique(sites))} sites\n")

    results: dict[str, list[float]] = {}
    ci_note = None

    for fold, tr, te in site_folds(sites, a.folds):
        Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
        print(f"fold {fold}: train {tr.sum()} rows / test {te.sum()} rows")

        for name, m in T.run_baselines(Xtr, ytr, Xte, yte).items():
            results.setdefault(name, []).append(m["roc_auc"])

        if a.skip_vqc:
            continue

        # every initialisation on this fold, then the ensemble of them
        probs = []
        for s in range(a.seeds):
            t0 = time.time()
            p = train_one(Xtr, ytr, Xte, a.layers, a.epochs, a.lr, a.batch, s)
            probs.append(p)
            auc = float(roc_auc_score(yte, p))
            results.setdefault("vqc_single_init", []).append(auc)
            print(f"   vqc init {s}: auc={auc:.4f}  ({time.time()-t0:.0f}s)")
            if fold == 0 and s == 0:
                lo, hi = bootstrap_ci(yte, p)
                ci_note = (auc, lo, hi)

        ens = float(roc_auc_score(yte, np.mean(probs, axis=0)))
        results.setdefault("vqc_ensemble", []).append(ens)
        print(f"   vqc {a.seeds}-init ensemble: auc={ens:.4f}")

    # ------------------------------------------------------------- report
    print("\n" + "=" * 70)
    print(f"ACROSS {a.folds} SITE-GROUPED FOLDS" +
          ("" if a.skip_vqc else f" x {a.seeds} INITIALISATIONS"))
    print("=" * 70)
    summary = {}
    for name, vals in sorted(results.items(), key=lambda kv: -float(np.mean(kv[1]))):
        v = np.asarray(vals, dtype=float)
        summary[name] = {"mean": round(float(v.mean()), 4),
                         "std": round(float(v.std()), 4),
                         "n": int(v.size),
                         "values": [round(float(x), 4) for x in v]}
        print(f"  {name:22} {v.mean():.4f} ± {v.std():.4f}   (n={v.size})")

    if ci_note:
        auc, lo, hi = ci_note
        print(f"\n  Bootstrap 95% CI on fold 0, one model: "
              f"{auc:.4f}  [{lo:.4f}, {hi:.4f}]  width {hi-lo:.4f}")
        print("  Any difference smaller than that width is not measurable here.")

    out = os.path.join(HERE, "variance_study.json")
    with open(out, "w") as fh:
        json.dump({"folds": a.folds, "seeds": a.seeds, "epochs": a.epochs,
                   "features": [NAMES[c] for c in cols], "results": summary}, fh, indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
