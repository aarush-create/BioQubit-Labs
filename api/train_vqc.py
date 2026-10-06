"""
Train the Q-VIRA VQC and benchmark it against classical baselines.

Run:
    python train_vqc.py --data data/single_mut_effects.csv
    python train_vqc.py --demo          # synthetic data, pipeline smoke-test only

Outputs:
    weights.npz     trained parameters, loaded by quantum_engine.py
    metrics.json    held-out metrics for the VQC AND the classical baselines

WHERE TO GET THE REAL DATA
--------------------------
Starr et al. (2020), deep mutational scanning of the SARS-CoV-2 RBD. Every
single amino-acid mutation was measured for ACE2 binding and expression.

    git lfs install
    git clone https://github.com/jbloomlab/SARS-CoV-2-RBD_DMS
    cp SARS-CoV-2-RBD_DMS/results/single_mut_effects/single_mut_effects.csv data/

The files are stored with Git LFS, so a plain download gives you a ~130-byte
pointer file instead of the CSV. This script checks for that and tells you.

WHAT THE MODEL ACTUALLY PREDICTS
--------------------------------
Given the 4 physicochemical descriptors of a mutant RBD sequence, predict
whether that mutant retains ACE2 binding (bind_avg above a threshold). That
is a real, measurable, falsifiable label.

Call this a "variant binding-retention score". It is NOT an outbreak
prediction, and it is NOT a claim that the mutation will spread. Say this
clearly -- overclaiming is what loses credibility in Q&A.

SPLIT POLICY
------------
We split by SITE, not by row. Mutations at the same position are highly
correlated; a random row split leaks information and inflates the score.
A judge who knows ML will ask about exactly this.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pennylane as qml
from pennylane import numpy as pnp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mutation_features import (  # noqa: E402
    raw_descriptors, RANGES, VALID, NAMES, SELECTED, N_ALL_FEATURES,
)

# One feature per qubit (angle encoding), so the circuit width follows the
# featuriser. Overridable with --qubits only for ablation experiments.
N_QUBITS = len(SELECTED)
N_LAYERS = 6   # defaults reproduce the SHIPPED model; see RESULTS.md ablations
HERE = os.path.dirname(os.path.abspath(__file__))

dev = qml.device("default.qubit", wires=N_QUBITS)


@qml.qnode(dev)
def circuit(features, weights):
    """Data re-uploading ansatz -- must stay identical to quantum_engine.py."""
    for layer in range(weights.shape[0]):
        qml.AngleEmbedding(features=features, wires=range(N_QUBITS), rotation="Y")
        qml.StronglyEntanglingLayers(weights[layer:layer + 1], wires=range(N_QUBITS))
    return qml.expval(qml.PauliZ(0))


def predict_proba(X, weights, readout):
    """p = sigmoid(scale * <Z> + bias). The calibration is trained too."""
    # X is passed as a WHOLE BATCH. PennyLane broadcasts it through the
    # circuit in one call, measured ~24x faster than looping sample by sample
    # (0.91s vs 21.96s for 3 optimiser steps at 8 qubits). Identical maths,
    # different evaluation strategy.
    z = circuit(X, weights)
    return 1.0 / (1.0 + pnp.exp(-(readout[0] * z + readout[1])))


def bce_loss(weights, readout, X, y):
    p = pnp.clip(predict_proba(X, weights, readout), 1e-7, 1 - 1e-7)
    return -pnp.mean(y * pnp.log(p) + (1 - y) * pnp.log(1 - p))


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def _scale_block(raw, cols=None):
    """Apply the same fixed clamp/scale used at inference time."""
    out = np.empty_like(raw, dtype=float)
    chosen = [RANGES[c] for c in cols] if cols else list(RANGES[:raw.shape[1]])
    for j, (lo, hi) in enumerate(chosen):
        v = np.clip(raw[:, j], lo, hi)
        out[:, j] = (v - lo) / (hi - lo) * np.pi
    return out


def load_dms(path: str):
    """Load the Starr et al. single-mutant CSV into (X_raw, y, sites)."""
    import pandas as pd

    with open(path, "rb") as fh:
        if fh.read(40).startswith(b"version https://git-lfs"):
            raise SystemExit(
                f"{path} is a Git LFS pointer, not the real CSV.\n"
                "Run `git lfs install && git lfs pull` in the cloned repo."
            )

    df = pd.read_csv(path)
    needed = {"site_SARS2", "wildtype", "mutant", "bind_avg"}
    missing = needed - set(df.columns)
    if missing:
        raise SystemExit(f"CSV is missing expected columns: {sorted(missing)}")

    df = df.dropna(subset=["bind_avg"])
    df = df[df["mutant"] != df["wildtype"]]
    df = df[df["mutant"].isin(VALID)]
    df = df[df["wildtype"].isin(VALID)]
    if df.empty:
        raise SystemExit("No usable rows after filtering.")

    # Reconstruct the wild-type RBD from the table itself: one row per site
    # carries its wildtype residue.
    wt_map = df.groupby("site_SARS2")["wildtype"].first().sort_index()
    sites_sorted = list(wt_map.index)
    wt_seq = "".join(wt_map.values)
    site_to_idx = {s: i for i, s in enumerate(sites_sorted)}

    n_sites = len(sites_sorted)
    X_raw, y, sites = [], [], []
    for row in df.itertuples(index=False):
        idx = site_to_idx[row.site_SARS2]
        # Mutation-level descriptors: how the SUBSTITUTION changes the residue.
        X_raw.append(raw_descriptors(row.wildtype, row.mutant, idx / n_sites,
                                     site=row.site_SARS2))
        # bind_avg is a log10 change vs wild type; >= -1 keeps meaningful
        # binding. This threshold is a modelling choice -- state it.
        y.append(1.0 if row.bind_avg >= -1.0 else 0.0)
        sites.append(row.site_SARS2)

    return np.array(X_raw), np.array(y), np.array(sites), wt_seq


def make_demo(n=600, seed=0):
    """Synthetic smoke-test data. NEVER report metrics from this as results."""
    rng = np.random.default_rng(seed)
    X_raw = np.column_stack([rng.uniform(lo, hi, n) for lo, hi in RANGES])
    logit = (-0.3 * X_raw[:, 0] - 1.5 * X_raw[:, 1]
             - 0.02 * X_raw[:, 2] + 2.0 * X_raw[:, 3])
    p = 1 / (1 + np.exp(-(logit - np.median(logit))))
    y = (rng.uniform(size=n) < p).astype(float)
    sites = rng.integers(0, 60, n)
    return X_raw, y, sites, None


# --------------------------------------------------------------------------
# Baselines
# --------------------------------------------------------------------------

def run_baselines(Xtr, ytr, Xte, yte):
    """Classical models on the EXACT SAME 4 features. This is the honest
    comparison -- without it, the VQC number means nothing."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC
    from sklearn.neural_network import MLPClassifier
    from sklearn.dummy import DummyClassifier
    from sklearn.metrics import roc_auc_score, accuracy_score

    models = {
        "majority_class": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": LogisticRegression(max_iter=2000),
        "svm_rbf": SVC(probability=True, random_state=0),
        "mlp": MLPClassifier(hidden_layer_sizes=(16,), max_iter=2000, random_state=0),
    }
    out = {}
    for name, m in models.items():
        m.fit(Xtr, ytr)
        proba = m.predict_proba(Xte)[:, 1]
        try:
            auc = float(roc_auc_score(yte, proba))
        except ValueError:
            auc = float("nan")
        out[name] = {
            "accuracy": round(float(accuracy_score(yte, m.predict(Xte))), 4),
            "roc_auc": round(auc, 4),
        }
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    global N_QUBITS, N_LAYERS, dev, circuit
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="path to single_mut_effects.csv")
    ap.add_argument("--demo", action="store_true", help="synthetic smoke test")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--layers", type=int, default=6, help="circuit depth (ablation)")
    ap.add_argument("--n-features", type=int, default=None,
                    help="use only the first N features (ablation vs v1)")
    ap.add_argument("--all-features", action="store_true",
                    help="use all 8 descriptors (ablation; measured worse)")
    ap.add_argument("--features", type=str, default=None,
                    help="comma-separated feature indices to use, e.g. 4,6,2,3")
    args = ap.parse_args()

    if not args.data and not args.demo:
        ap.error("pass --data <csv> for real training, or --demo to smoke-test")

    N_LAYERS = args.layers

    if args.demo:
        X_raw, y, sites, _ = make_demo()
        source = "SYNTHETIC DEMO DATA - NOT A RESULT"
    else:
        X_raw, y, sites, _ = load_dms(args.data)
        source = os.path.basename(args.data)

    # Default to the measured-best subset; --features / --all-features override.
    feature_cols = list(SELECTED)
    if args.all_features:
        feature_cols = list(range(N_ALL_FEATURES))
    elif args.features:
        feature_cols = [int(i) for i in args.features.split(",")]
    elif args.n_features:
        feature_cols = list(range(args.n_features))
    X_raw = X_raw[:, feature_cols]
    print(f"features: {[NAMES[c] for c in feature_cols]}")

    # Rebuild the device/QNode at the width this run actually needs.
    N_QUBITS = X_raw.shape[1]
    dev = qml.device("default.qubit", wires=N_QUBITS)

    @qml.qnode(dev)
    def circuit(features, weights):
        for layer in range(weights.shape[0]):
            qml.AngleEmbedding(features=features, wires=range(N_QUBITS), rotation="Y")
            qml.StronglyEntanglingLayers(weights[layer:layer + 1], wires=range(N_QUBITS))
        return qml.expval(qml.PauliZ(0))

    globals()["circuit"] = circuit
    print(f"circuit: {N_QUBITS} qubits x {N_LAYERS} layers")

    X = _scale_block(X_raw, feature_cols)

    # Group split by site to avoid leakage between correlated mutations.
    rng = np.random.default_rng(args.seed)
    uniq = np.unique(sites)
    rng.shuffle(uniq)
    n_test = max(1, int(0.25 * len(uniq)))
    test_sites = set(uniq[:n_test].tolist())
    te = np.array([s in test_sites for s in sites])
    tr = ~te

    Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
    print(f"source={source}")
    print(f"train={len(Xtr)} rows / {len(uniq)-n_test} sites | "
          f"test={len(Xte)} rows / {n_test} sites")
    print(f"positive rate: train={ytr.mean():.3f} test={yte.mean():.3f}")

    # --- train the VQC ---
    pnp.random.seed(args.seed)
    weights = pnp.array(
        pnp.random.uniform(0, 2 * np.pi, (N_LAYERS, N_QUBITS, 3)), requires_grad=True
    )
    readout = pnp.array([1.0, 0.0], requires_grad=True)
    opt = qml.AdamOptimizer(stepsize=args.lr)

    # Keep the DATA as plain numpy. Wrapping it in pennylane.numpy tensors
    # makes autograd's ArrayBox and PennyLane's tensor subclass fail to
    # interoperate inside the loss, raising a NotImplementedType TypeError.
    # Only the TRAINABLE parameters should be pennylane.numpy arrays.
    Xtr_p = np.asarray(Xtr, dtype=float)
    ytr_p = np.asarray(ytr, dtype=float)

    t0 = time.time()
    for epoch in range(args.epochs):
        perm = np.random.default_rng(epoch).permutation(len(Xtr_p))
        for start in range(0, len(perm), args.batch):
            idx = perm[start:start + args.batch]
            weights, readout = opt.step(
                lambda w, r: bce_loss(w, r, Xtr_p[idx], ytr_p[idx]), weights, readout
            )
        if epoch % 5 == 0 or epoch == args.epochs - 1:
            loss = float(bce_loss(weights, readout, Xtr_p, ytr_p))
            print(f"  epoch {epoch:3d}  train_loss={loss:.4f}")
    train_secs = round(time.time() - t0, 1)

    # --- evaluate ---
    from sklearn.metrics import roc_auc_score, accuracy_score

    w_fixed = pnp.array(weights, requires_grad=False)
    r_fixed = pnp.array(readout, requires_grad=False)
    z = np.asarray(circuit(Xte, w_fixed), dtype=float)
    proba = 1.0 / (1.0 + np.exp(-(float(r_fixed[0]) * z + float(r_fixed[1]))))
    try:
        vqc_auc = float(roc_auc_score(yte, proba))
    except ValueError:
        vqc_auc = float("nan")
    vqc_acc = float(accuracy_score(yte, (proba >= 0.5).astype(float)))

    metrics = {
        "data_source": source,
        "is_synthetic": bool(args.demo),
        "n_train": int(len(Xtr)),
        "n_test": int(len(Xte)),
        "split": "grouped by site (no site appears in both splits)",
        "label": "bind_avg >= -1.0 (retains ACE2 binding)",
        "features": f"mutation-delta-v2 cols={feature_cols} ({[NAMES[c] for c in feature_cols]})",
        "train_seconds": train_secs,
        "vqc": {
            "accuracy": round(vqc_acc, 4),
            "roc_auc": round(vqc_auc, 4),
            "n_qubits": N_QUBITS,
            "n_layers": N_LAYERS,
            "n_parameters": int(np.asarray(weights).size + 2),
            "ansatz": "data-reuploading-StronglyEntanglingLayers",
        },
        "classical_baselines_same_features": run_baselines(Xtr, ytr, Xte, yte),
    }

    np.savez(
        os.path.join(HERE, "weights.npz"),
        weights=np.array(weights, dtype=float),
        readout=np.array(readout, dtype=float),
        metadata=np.array(metrics, dtype=object),
    )
    with open(os.path.join(HERE, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    print("\n--- held-out results ---")
    print(f"VQC                  acc={metrics['vqc']['accuracy']}  "
          f"auc={metrics['vqc']['roc_auc']}")
    for name, m in metrics["classical_baselines_same_features"].items():
        print(f"{name:20s} acc={m['accuracy']}  auc={m['roc_auc']}")
    print("\nSaved weights.npz and metrics.json")
    N_LAYERS = args.layers

    if args.demo:
        print("\n*** SYNTHETIC DATA. Do not put these numbers in your deck. ***")


if __name__ == "__main__":
    main()
