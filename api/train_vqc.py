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

Sites are now split THREE ways: train / validation / test. Validation is used
for early stopping and for choosing between random restarts. The test sites are
scored exactly once, at the end. Previously there was no validation set and a
single seed, which meant the reported number was also the selection number.

READOUT (new)
-------------
    --readout probs      trained linear map over all 2^n basis probabilities
    --readout single_z    the original <Z_0>, one qubit of four

Same circuit either way, so this flag isolates the readout. Run both at the
same --seed and --val-frac to get a clean ablation. See circuit.py.

REPRODUCING THE PREVIOUS SHIPPED MODEL
--------------------------------------
    python train_vqc.py --data ... --readout single_z --val-frac 0.0 --seeds 1
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
    N_BASE_FEATURES, BURIAL_INDEX,
)
from circuit import (  # noqa: E402
    make_qnode, predict_proba, init_readout, n_readout_params, READOUT_KINDS,
    qubits_needed, ENCODINGS, DEFAULT_AXES,
)

HERE = os.path.dirname(os.path.abspath(__file__))


def bce_loss(weights, readout, X, y, qnode, kind):
    # X is passed as a WHOLE BATCH. PennyLane broadcasts it through the circuit
    # in one call, measured ~24x faster than looping sample by sample.
    raw = qnode(X, weights)
    p = pnp.clip(predict_proba(raw, readout, kind), 1e-7, 1 - 1e-7)
    return -pnp.mean(y * pnp.log(p) + (1 - y) * pnp.log(1 - p))


def score(X, weights, readout, qnode, kind) -> np.ndarray:
    """Probabilities as plain numpy, for metrics."""
    w = pnp.array(weights, requires_grad=False)
    r = pnp.array(readout, requires_grad=False)
    raw = qnode(np.asarray(X, dtype=float), w)
    return np.asarray(predict_proba(raw, r, kind), dtype=float)


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


def site_split(sites, seed: int, val_frac: float):
    """Three-way split by SITE. Returns boolean masks (train, val, test).

    Lives in a function, not inline in main(), because bootstrap_gap.py has to
    reproduce the EXACT same split to compare the deployed VQC against freshly
    fitted baselines. When this logic was duplicated there, the two drifted:
    bootstrap trained its baselines on train+val while the VQC had only seen
    train, which quietly handed the baselines ~25% more data.
    """
    rng = np.random.default_rng(seed)
    uniq = np.unique(sites)
    rng.shuffle(uniq)
    n_test = max(1, int(0.25 * len(uniq)))
    test_sites = set(uniq[:n_test].tolist())
    rest = uniq[n_test:]
    n_val = int(val_frac * len(rest))
    val_sites = set(rest[:n_val].tolist())
    assert not (test_sites & val_sites), "val and test sites overlap"

    te = np.array([s in test_sites for s in sites])
    va = np.array([s in val_sites for s in sites])
    tr = ~(te | va)
    return tr, va, te


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

    wt_map = df.groupby("site_SARS2")["wildtype"].first().sort_index()
    sites_sorted = list(wt_map.index)
    wt_seq = "".join(wt_map.values)
    site_to_idx = {s: i for i, s in enumerate(sites_sorted)}

    n_sites = len(sites_sorted)
    X_raw, y, sites = [], [], []
    for row in df.itertuples(index=False):
        idx = site_to_idx[row.site_SARS2]
        X_raw.append(raw_descriptors(row.wildtype, row.mutant, idx / n_sites,
                                     site=row.site_SARS2))
        y.append(1.0 if row.bind_avg >= -1.0 else 0.0)
        sites.append(row.site_SARS2)

    return np.array(X_raw), np.array(y), np.array(sites), wt_seq


def load_panel(path: str, group_by: str = "protein"):
    """Load a multi-protein table from proteingym_loader.py.

    Returns (X_raw, y, groups). `groups` is what the split holds out:

      protein  no protein appears in both train and test. This is the honest
               generalisation test for a multi-protein model -- it asks whether
               the model works on a protein it has never seen, which is the
               deployment condition for a novel target.
      site     groups by (protein, site), the within-protein analogue of the
               single-assay split. Easier, and NOT a cross-protein claim.

    ace2_distance (feature index 8) is measured from one SARS-CoV-2 complex and
    is meaningless for other proteins. It is still COMPUTED here (the featuriser
    returns all 9 descriptors) but it falls back to ACE2_FAR for every site of
    every other protein, so including it in --features on a multi-protein run
    would feed the model a constant. Use --features 4,6,2,5,0.
    """
    import pandas as pd

    df = pd.read_csv(path)
    need = {"protein", "site_SARS2", "wildtype", "mutant", "label"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"{path} missing columns: {sorted(missing)}. "
                         f"Build it with proteingym_loader.py.")

    df = df.dropna(subset=["site_SARS2", "wildtype", "mutant", "label"])
    df = df[df["wildtype"].isin(VALID) & df["mutant"].isin(VALID)]
    df = df[df["wildtype"] != df["mutant"]]
    if df.empty:
        raise SystemExit("No usable rows after filtering.")

    has_burial = "burial" in df.columns
    if has_burial:
        df = df.dropna(subset=["burial"])
        print(f"panel carries a burial column -> descriptor index "
              f"{BURIAL_INDEX} is available. Include it with "
              f"--features ...,{BURIAL_INDEX}")

    X_raw, y, groups = [], [], []
    for prot, sub in df.groupby("protein", sort=False):
        # relative_position is per protein, so it is computed within each
        # protein's own site range rather than across the pooled table.
        sites_sorted = sorted(sub["site_SARS2"].unique())
        pos = {s: i for i, s in enumerate(sites_sorted)}
        n_sites = max(1, len(sites_sorted))
        for row in sub.itertuples(index=False):
            d = raw_descriptors(row.wildtype, row.mutant,
                                pos[row.site_SARS2] / n_sites,
                                site=int(row.site_SARS2))
            if has_burial:
                # Appended as descriptor index N_ALL_FEATURES (9). Index 8
                # (ace2_distance) stays in the vector but is a constant outside
                # SARS-CoV-2, so do not select it on a multi-protein run.
                d = d + [float(row.burial)]
            X_raw.append(d)
            y.append(float(row.label))
            groups.append(prot if group_by == "protein"
                          else f"{prot}:{int(row.site_SARS2)}")

    print(f"panel: {len(y)} rows | {df['protein'].nunique()} proteins | "
          f"grouping held-out by {group_by} "
          f"({len(set(groups))} distinct groups)")
    return np.array(X_raw), np.array(y), np.array(groups, dtype=object)


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
# Metrics
# --------------------------------------------------------------------------

def triage_metrics(y, proba, ks=(25, 100, 250)) -> dict:
    """AUC answers "how good is the whole ranking". This tool answers "which
    mutation should a lab test FIRST", so the top of the ranking is what
    actually matters. precision@k is that question; enrichment compares it to
    the base rate, so 1.0 means the ranking added nothing.

    Brier score and the calibration gap are included because a triage score
    that is read as a probability should be calibrated, not just ordered."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(proba, dtype=float)
    order = np.argsort(-p)
    base = float(y.mean())
    out = {"base_rate": round(base, 4)}
    for k in ks:
        k_eff = min(k, len(y))
        if k_eff == 0:
            continue
        prec = float(y[order[:k_eff]].mean())
        out[f"precision_at_{k}"] = round(prec, 4)
        out[f"enrichment_at_{k}"] = round(prec / base, 4) if base > 0 else None
    # How far down the ranking you can read before hitting the first negative.
    # precision@k saturates at 1.0 for small k when the base rate is high
    # (0.68 here), so it stops discriminating; this does not saturate.
    neg = np.where(y[order] == 0)[0]
    out["clean_prefix"] = int(neg[0]) if len(neg) else int(len(y))
    out["brier"] = round(float(np.mean((p - y) ** 2)), 4)
    # 10-bin reliability gap: mean |predicted - observed| per populated bin.
    bins = np.clip((p * 10).astype(int), 0, 9)
    gaps, weights = [], []
    for b in range(10):
        m = bins == b
        if m.sum() == 0:
            continue
        gaps.append(abs(p[m].mean() - y[m].mean()))
        weights.append(m.sum())
    out["calibration_gap"] = (round(float(np.average(gaps, weights=weights)), 4)
                              if gaps else None)
    return out


SVM_MAX_ROWS = 20_000


def run_baselines(Xtr, ytr, Xte, yte, svm_max_rows: int = SVM_MAX_ROWS):
    """Classical models on the EXACT SAME features. This is the honest
    comparison -- without it, the VQC number means nothing.

    SVC IS SUBSAMPLED ABOVE svm_max_rows. Kernel SVM training is O(n^2)-O(n^3)
    in the number of rows, and probability=True adds an internal 5-fold
    calibration on top. On the ~117k-row multi-protein panel that does not
    finish in any useful time -- it looks like a hang. A stratified subsample
    keeps the baseline honest and finite, and the row count actually used is
    recorded in metrics.json so the comparison is never quietly unequal.

    Logistic regression and the MLP scale fine and get all the rows.
    """
    import numpy as _np
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC
    from sklearn.neural_network import MLPClassifier
    from sklearn.dummy import DummyClassifier
    from sklearn.metrics import roc_auc_score, accuracy_score

    models = {
        "majority_class": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": LogisticRegression(max_iter=2000),
        "svm_rbf": SVC(probability=True, random_state=0),
        "mlp": MLPClassifier(hidden_layer_sizes=(16,), max_iter=2000,
                             random_state=0),
    }
    out = {}
    for name, m in models.items():
        Xf, yf = Xtr, ytr
        if name == "svm_rbf" and len(Xtr) > svm_max_rows:
            rs = _np.random.default_rng(0)
            idx = rs.choice(len(Xtr), svm_max_rows, replace=False)
            Xf, yf = Xtr[idx], ytr[idx]
            print(f"  note: svm_rbf trained on a {svm_max_rows}-row "
                  f"subsample of {len(Xtr)} (O(n^2) kernel fit)")
        m.fit(Xf, yf)
        proba = m.predict_proba(Xte)[:, 1]
        try:
            auc = float(roc_auc_score(yte, proba))
        except ValueError:
            auc = float("nan")
        out[name] = {
            "accuracy": round(float(accuracy_score(yte, m.predict(Xte))), 4),
            "roc_auc": round(auc, 4),
            "n_train_used": int(len(Xf)),
            "triage": triage_metrics(yte, proba),
        }
    return out


def per_group_auc(groups_te, yte, proba) -> dict:
    """Test AUC broken down by held-out group.

    A pooled multi-protein AUC hides everything that matters: it can look
    mediocre because two proteins are unpredictable while the rest are fine, or
    look fine because one large easy protein dominates the row count. The
    per-protein numbers are what tell you whether a single pooled model is the
    right architecture or whether specialists are needed.
    """
    from sklearn.metrics import roc_auc_score
    rows = {}
    for g in np.unique(groups_te):
        m = groups_te == g
        yy, pp = yte[m], proba[m]
        try:
            a = float(roc_auc_score(yy, pp))
        except ValueError:
            a = float("nan")
        rows[str(g)] = {"n": int(m.sum()),
                        "pos_rate": round(float(yy.mean()), 4),
                        "auc": None if np.isnan(a) else round(a, 4)}
    return rows


# --------------------------------------------------------------------------
# One training run
# --------------------------------------------------------------------------

def train_one(Xtr, ytr, Xva, yva, qnode, n_qubits, n_layers, kind, args, seed):
    """Train a single restart. Returns (best, history).

    The qnode is built once in main() and reused across restarts: it holds no
    state apart from the device, and rebuilding it per seed would silently make
    an encoding/width mismatch possible between restarts.
    """
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(seed)
    pnp.random.seed(seed)
    weights = pnp.array(
        pnp.random.uniform(0, 2 * np.pi, (n_layers, n_qubits, 3)),
        requires_grad=True,
    )
    readout = init_readout(n_qubits, kind, rng=rng)

    # Keep the DATA as plain numpy. Wrapping it in pennylane.numpy tensors
    # makes autograd's ArrayBox and PennyLane's tensor subclass fail to
    # interoperate inside the loss, raising a NotImplementedType TypeError.
    # Only the TRAINABLE parameters should be pennylane.numpy arrays.
    Xtr_p = np.asarray(Xtr, dtype=float)
    ytr_p = np.asarray(ytr, dtype=float)

    best = {"val_auc": -np.inf, "weights": None, "readout": None, "epoch": -1}
    history = []
    stale = 0

    # ONE optimiser for the whole run. Rebuilding it per epoch would reset
    # Adam's first- and second-moment estimates every epoch, throwing away the
    # momentum that makes Adam worth using.
    opt = qml.AdamOptimizer(stepsize=float(args.lr))

    for epoch in range(args.epochs):
        # Cosine decay: Adam at a constant 0.05 converges fast but then
        # oscillates around the optimum instead of settling into it.
        lr = args.lr * 0.5 * (1 + np.cos(np.pi * epoch / max(1, args.epochs)))
        opt.stepsize = float(lr)

        perm = np.random.default_rng(seed * 10_000 + epoch).permutation(len(Xtr_p))
        for start in range(0, len(perm), args.batch):
            idx = perm[start:start + args.batch]
            weights, readout = opt.step(
                lambda w, r: bce_loss(w, r, Xtr_p[idx], ytr_p[idx], qnode, kind),
                weights, readout,
            )

        if len(Xva) > 0:
            pv = score(Xva, weights, readout, qnode, kind)
            try:
                va = float(roc_auc_score(yva, pv))
            except ValueError:
                va = float("nan")
        else:
            va = float("nan")

        if epoch % 5 == 0 or epoch == args.epochs - 1:
            tl = float(bce_loss(weights, readout, Xtr_p, ytr_p, qnode, kind))
            history.append({"epoch": epoch, "train_loss": round(tl, 4),
                            "val_auc": None if np.isnan(va) else round(va, 4)})
            print(f"  seed {seed} epoch {epoch:3d} lr={lr:.4f} "
                  f"train_loss={tl:.4f}"
                  + ("" if np.isnan(va) else f"  val_auc={va:.4f}"))

        if not np.isnan(va):
            if va > best["val_auc"] + 1e-5:
                best = {"val_auc": va,
                        "weights": np.array(weights, dtype=float),
                        "readout": np.array(readout, dtype=float),
                        "epoch": epoch}
                stale = 0
            else:
                stale += 1
                if args.patience and stale >= args.patience:
                    print(f"  seed {seed}: early stop at epoch {epoch} "
                          f"(best val_auc={best['val_auc']:.4f} "
                          f"@ epoch {best['epoch']})")
                    break

    if best["weights"] is None:  # no validation set -> keep the final state
        best = {"val_auc": float("nan"),
                "weights": np.array(weights, dtype=float),
                "readout": np.array(readout, dtype=float),
                "epoch": args.epochs - 1}
    return best, history


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="path to single_mut_effects.csv")
    ap.add_argument("--panel", help="multi-protein table from proteingym_loader.py")
    ap.add_argument("--group-by", choices=["protein", "site"], default="protein",
                    help="--panel only: what the split holds out. 'protein' is "
                         "the cross-protein generalisation test; 'site' is the "
                         "easier within-protein split and is NOT a "
                         "cross-protein claim.")
    ap.add_argument("--demo", action="store_true", help="synthetic smoke test")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0, help="split seed, and base for restarts")
    ap.add_argument("--seeds", type=int, default=1,
                    help="number of random restarts; best VALIDATION auc wins")
    ap.add_argument("--layers", type=int, default=6, help="circuit depth (ablation)")
    ap.add_argument("--readout", choices=READOUT_KINDS, default="probs",
                    help="probs = full basis distribution (new); single_z = original")
    ap.add_argument("--encoding", choices=ENCODINGS, default="angle",
                    help="angle = 1 feature/qubit (original); dense = several "
                         "features per qubit, one per rotation axis")
    ap.add_argument("--axes", type=str, default="Y,Z",
                    help="dense only: rotation axes, in order. Y must come "
                         "first -- RZ on |0> encodes nothing. Try Y,X too.")
    ap.add_argument("--tag", default=None,
                    help="suffix for the output files, e.g. --tag panel writes "
                         "weights_panel.npz and metrics_panel.json. Without it "
                         "the run overwrites weights.npz/metrics.json, which is "
                         "what the live API serves -- so use a tag for every "
                         "experiment and leave the bare names for the model you "
                         "actually intend to deploy.")
    ap.add_argument("--legacy-blosum-range", action="store_true",
                    help="restore the old blosum62 clamp of (-4, 11) instead of "
                         "the corrected (-4, 3). Only for the A/B comparison: "
                         "+11 occurs solely for identical residues, which are "
                         "filtered out, so the old range wasted 53%% of the "
                         "angle range on values that never occur.")
    ap.add_argument("--qubits", type=int, default=None,
                    help="override circuit width; defaults to the minimum the "
                         "encoding needs. Fewer than that is an error, never a "
                         "silent drop of features.")
    ap.add_argument("--val-frac", type=float, default=0.2,
                    help="fraction of TRAIN sites held out for early stopping "
                         "and restart selection; 0.0 reproduces the old setup")
    ap.add_argument("--patience", type=int, default=20,
                    help="epochs without validation improvement before stopping; 0 disables")
    ap.add_argument("--n-features", type=int, default=None,
                    help="use only the first N features (ablation vs v1)")
    ap.add_argument("--all-features", action="store_true",
                    help="use all 8 descriptors (ablation; measured worse)")
    ap.add_argument("--features", type=str, default=None,
                    help="comma-separated feature indices to use, e.g. 4,6,2,3")
    args = ap.parse_args()

    if not any([args.data, args.panel, args.demo]):
        ap.error("pass --data <csv>, --panel <csv>, or --demo to smoke-test")
    if args.data and args.panel:
        ap.error("--data and --panel are mutually exclusive")

    if args.legacy_blosum_range:
        # Rebind BOTH references: mutation_features owns the tuple, but this
        # module imported its own name for it and _scale_block reads that one.
        import mutation_features as _mf
        _r = list(_mf.RANGES); _r[4] = (-4.0, 11.0)
        _mf.RANGES = tuple(_r)
        globals()["RANGES"] = tuple(_r)
        print("NOTE: using the LEGACY blosum62 clamp (-4, 11) for comparison")

    if args.demo:
        X_raw, y, groups, _ = make_demo()
        source = "SYNTHETIC DEMO DATA - NOT A RESULT"
        group_kind = "site"
    elif args.panel:
        X_raw, y, groups = load_panel(args.panel, args.group_by)
        source = os.path.basename(args.panel)
        group_kind = args.group_by
    else:
        X_raw, y, groups, _ = load_dms(args.data)
        source = os.path.basename(args.data)
        group_kind = "site"

    feature_cols = list(SELECTED)
    if args.all_features:
        # Size this from the data, not from N_ALL_FEATURES: the single-assay
        # path has no burial column, so index 9 does not exist there.
        feature_cols = list(range(X_raw.shape[1]))
    elif args.features:
        feature_cols = [int(i) for i in args.features.split(",")]
    elif args.n_features:
        feature_cols = list(range(args.n_features))
    X_raw = X_raw[:, feature_cols]
    print(f"features: {[NAMES[c] for c in feature_cols]}")

    n_features = X_raw.shape[1]
    n_layers = args.layers
    kind = args.readout
    encoding = args.encoding
    axes = tuple(a.strip().upper() for a in args.axes.split(",")) if args.axes \
        else DEFAULT_AXES

    need = qubits_needed(n_features, encoding, axes)
    n_qubits = args.qubits if args.qubits else need
    if n_qubits < need:
        raise SystemExit(
            f"--qubits {n_qubits} is too few: {n_features} features need "
            f"{need} under encoding={encoding} axes={axes}."
        )

    print(f"features: {n_features} | encoding: {encoding}"
          + (f" axes={axes}" if encoding == "dense" else ""))
    print(f"circuit:  {n_qubits} qubits x {n_layers} layers"
          + (f"   ({n_features} features on {n_qubits} wires)"
             if encoding == "dense" else ""))
    print(f"readout:  {kind} "
          f"({n_readout_params(n_qubits, kind)} readout parameters)")
    if encoding == "dense" and n_layers < 3:
        print("  WARNING: dense encoding puts some features on a phase axis, "
              "and phase\n  only becomes measurable through the RY inside each "
              "entangling layer.\n  At this depth those features are nearly "
              "invisible. Use more layers.")

    X = _scale_block(X_raw, feature_cols)

    # ---- three-way site split: train / val / test -------------------------
    tr, va, te = site_split(groups, args.seed, args.val_frac)

    Xtr, ytr = X[tr], y[tr]
    Xva, yva = X[va], y[va]
    Xte, yte = X[te], y[te]

    print(f"source={source}")
    print(f"train={len(Xtr)} rows / {len(np.unique(groups[tr]))} {group_kind}s | "
          f"val={len(Xva)} rows / {len(np.unique(groups[va])) if va.any() else 0} {group_kind}s | "
          f"test={len(Xte)} rows / {len(np.unique(groups[te]))} {group_kind}s")
    msg = f"positive rate: train={ytr.mean():.3f}"
    if len(yva):
        msg += f" val={yva.mean():.3f}"
    msg += f" test={yte.mean():.3f}"
    print(msg)

    # ---- train, possibly several restarts ---------------------------------
    qnode = make_qnode(n_features, n_qubits, kind, encoding, axes)
    t0 = time.time()
    runs = []
    for k in range(args.seeds):
        best, hist = train_one(Xtr, ytr, Xva, yva, qnode, n_qubits, n_layers,
                               kind, args, seed=args.seed + k)
        runs.append((best, hist))
    train_secs = round(time.time() - t0, 1)

    if len(Xva) > 0 and args.seeds > 1:
        vals = [r[0]["val_auc"] for r in runs]
        pick = int(np.nanargmax(vals))
        print(f"\nrestart val_aucs: "
              f"{[None if np.isnan(v) else round(v, 4) for v in vals]} "
              f"-> picked seed {args.seed + pick}")
    else:
        pick = 0
    best, history = runs[pick]
    weights, readout = best["weights"], best["readout"]

    # ---- evaluate ONCE on test -------------------------------------------
    from sklearn.metrics import roc_auc_score, accuracy_score

    proba = score(Xte, weights, readout, qnode, kind)

    # ---- test AUC for EVERY restart --------------------------------------
    # This is NOT selection. We never pick a model by its test score -- the
    # shipped model is still the one validation chose, above. We score all the
    # restarts to characterise the TRAINING PROCEDURE's variance, because one
    # test number from one seed is not a measurement of anything.
    #
    # It matters here: a 562-row / 30-site validation set has noise around
    # +/-0.03 AUC, and taking a max over (restarts x epoch checkpoints) selects
    # that noise rather than genuine quality. Measured directly: the restart
    # with the HIGHEST validation AUC of a run has repeatedly produced a
    # mediocre test AUC. So the honest headline is mean +/- std across seeds,
    # with the spread quoted, not the single number the selector happened to
    # land on.
    #
    # Quote the mean and the spread. Never quote max(test).
    seed_aucs = []
    for k, (b, _h) in enumerate(runs):
        p_k = score(Xte, b["weights"], b["readout"], qnode, kind)
        try:
            a_k = float(roc_auc_score(yte, p_k))
        except ValueError:
            a_k = float("nan")
        seed_aucs.append({
            "seed": int(args.seed + k),
            "val_auc": (None if np.isnan(b["val_auc"])
                        else round(b["val_auc"], 4)),
            "test_auc": round(a_k, 4),
            "best_epoch": int(b["epoch"]),
        })

    arr = np.array([s["test_auc"] for s in seed_aucs], dtype=float)
    spread = {
        "n_restarts": int(len(arr)),
        "test_auc_mean": round(float(np.nanmean(arr)), 4),
        "test_auc_std": round(float(np.nanstd(arr, ddof=1)), 4) if len(arr) > 1 else None,
        "test_auc_min": round(float(np.nanmin(arr)), 4),
        "test_auc_max": round(float(np.nanmax(arr)), 4),
        "per_seed": seed_aucs,
    }

    # Is validation telling us anything at all? If this correlation is near
    # zero or negative, early stopping and restart choice are selecting noise
    # and the validation split is too small to be worth its cost.
    v = np.array([s["val_auc"] if s["val_auc"] is not None else np.nan
                  for s in seed_aucs], dtype=float)
    if len(arr) > 2 and not np.isnan(v).any() and np.nanstd(v) > 0:
        spread["val_test_correlation"] = round(
            float(np.corrcoef(v, arr)[0, 1]), 3)
    else:
        spread["val_test_correlation"] = None
    try:
        vqc_auc = float(roc_auc_score(yte, proba))
    except ValueError:
        vqc_auc = float("nan")
    vqc_acc = float(accuracy_score(yte, (proba >= 0.5).astype(float)))

    metrics = {
        "data_source": source,
        "is_synthetic": bool(args.demo),
        "n_train": int(len(Xtr)),
        "n_val": int(len(Xva)),
        "n_test": int(len(Xte)),
        "split": (f"grouped by {group_kind}, three-way (train/val/test); no "
                  f"{group_kind} appears in more than one split"),
        "group_kind": group_kind,
        "selection": ("early stopping and restart choice on VALIDATION auc; "
                      "test scored once"),
        # Saved so bootstrap_gap.py can reproduce this exact split.
        "split_seed": int(args.seed),
        "split_val_frac": float(args.val_frac),
        "label": "bind_avg >= -1.0 (retains ACE2 binding)",
        "features": f"mutation-delta-v2 cols={feature_cols} ({[NAMES[c] for c in feature_cols]})",
        "blosum62_clamp": list(RANGES[4]),
        "feature_cols": list(feature_cols),
        "train_seconds": train_secs,
        "vqc": {
            "accuracy": round(vqc_acc, 4),
            "roc_auc": round(vqc_auc, 4),
            "n_features": n_features,
            "n_qubits": n_qubits,
            "n_layers": n_layers,
            "readout": kind,
            "encoding": encoding,
            "axes": list(axes) if encoding == "dense" else None,
            "n_circuit_parameters": int(np.asarray(weights).size),
            "n_readout_parameters": int(np.asarray(readout).size),
            "n_parameters": int(np.asarray(weights).size
                                + np.asarray(readout).size),
            "ansatz": "data-reuploading-StronglyEntanglingLayers",
            "restarts": int(args.seeds),
            "selected_seed": int(args.seed + pick),
            "val_auc_of_selected": (None if np.isnan(best["val_auc"])
                                    else round(best["val_auc"], 4)),
            "best_epoch": int(best["epoch"]),
            "triage": triage_metrics(yte, proba),
            "restart_spread": spread,
            "per_group": per_group_auc(groups[te], yte, proba),
        },
        "classical_baselines_same_features": run_baselines(Xtr, ytr, Xte, yte),
        "history": history,
    }

    suffix = f"_{args.tag}" if args.tag else ""
    np.savez(
        os.path.join(HERE, f"weights{suffix}.npz"),
        weights=np.array(weights, dtype=float),
        readout=np.array(readout, dtype=float),
        readout_kind=np.array(kind),
        encoding=np.array(encoding),
        axes=np.array(",".join(axes)),
        n_features=np.array(int(n_features)),
        # WHICH descriptors, not just how many. The engine compares this
        # against SELECTED and refuses a mismatch. Without it, a 6-feature
        # panel model (…,burial) and a 6-feature SARS-CoV-2 model
        # (…,ace2_distance) are indistinguishable on disk: same count, same
        # width, same encoding -- and the engine would serve one while the
        # featuriser computed the other, silently.
        feature_cols=np.array(list(feature_cols), dtype=int),
        metadata=np.array(metrics, dtype=object),
    )
    with open(os.path.join(HERE, f"metrics{suffix}.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    if args.seeds > 1:
        print(f"\n--- restart spread ({kind}) -- QUOTE THIS, NOT ONE SEED ---")
        print(f"    {'seed':>5} {'val_auc':>9} {'test_auc':>9} {'best_ep':>8}")
        for s in seed_aucs:
            vv = "      nan" if s["val_auc"] is None else f"{s['val_auc']:>9.4f}"
            print(f"    {s['seed']:>5}{vv}{s['test_auc']:>10.4f}"
                  f"{s['best_epoch']:>8}")
        sd = spread["test_auc_std"]
        print(f"\n    test AUC = {spread['test_auc_mean']:.4f}"
              + (f" +/- {sd:.4f} (sd)" if sd is not None else "")
              + f"   range [{spread['test_auc_min']:.4f}, "
                f"{spread['test_auc_max']:.4f}]")
        c = spread["val_test_correlation"]
        if c is not None:
            print(f"    val-test correlation across restarts: {c:+.3f}", end="")
            if c < 0.3:
                print("  <-- validation is NOT predicting test.")
                print("        Early stopping and restart choice are "
                      "selecting noise, not quality.")
            else:
                print()
        print(f"\n    The shipped model is the VALIDATION pick (seed "
              f"{args.seed + pick}), scored below.")
        print("    Test scores for the other restarts are reported for "
              "variance only;")
        print("    no model was ever chosen by its test score.")

    pg = metrics["vqc"]["per_group"]
    if len(pg) > 1:
        print(f"\n--- per-{group_kind} test AUC (pooled AUC hides this) ---")
        print(f"    {'group':<34}{'n':>7}{'pos':>7}{'AUC':>8}")
        for g, v in sorted(pg.items(), key=lambda kv: -(kv[1]['auc'] or 0)):
            aa = "   nan" if v['auc'] is None else f"{v['auc']:>8.4f}"
            print(f"    {g[:33]:<34}{v['n']:>7}{v['pos_rate']:>7.3f}{aa}")
        vals = [v['auc'] for v in pg.values() if v['auc'] is not None]
        if vals:
            print(f"    mean across {group_kind}s: {np.mean(vals):.4f}"
                  f"  spread [{min(vals):.4f}, {max(vals):.4f}]")

    print("\n--- held-out results ---")
    print(f"VQC ({kind:8s})      acc={metrics['vqc']['accuracy']}  "
          f"auc={metrics['vqc']['roc_auc']}")
    for name, m in metrics["classical_baselines_same_features"].items():
        print(f"{name:20s} acc={m['accuracy']}  auc={m['roc_auc']}")

    t = metrics["vqc"]["triage"]
    print(f"\n--- triage view (base rate {t['base_rate']}) ---")
    for k in (25, 100, 250):
        key = f"precision_at_{k}"
        if key in t:
            print(f"  precision@{k:<4d} = {t[key]:.3f}   "
                  f"enrichment = {t[f'enrichment_at_{k}']:.3f}")
    print(f"  clean prefix   = {t['clean_prefix']} "
          f"(ranked correct before the first false positive)")
    print(f"  brier = {t['brier']}   calibration_gap = {t['calibration_gap']}")
    print("\n  baselines, same view:")
    for name, m in metrics["classical_baselines_same_features"].items():
        bt = m["triage"]
        print(f"    {name:20s} p@100={bt.get('precision_at_100')}  "
              f"clean_prefix={bt['clean_prefix']}  brier={bt['brier']}")

    print(f"\nSaved weights{suffix}.npz and metrics{suffix}.json")
    if not args.tag:
        print("  (no --tag: this overwrote the files the live API serves)")
    if args.demo:
        print("\n*** SYNTHETIC DATA. Do not put these numbers in your deck. ***")


if __name__ == "__main__":
    main()
