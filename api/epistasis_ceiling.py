"""
epistasis_ceiling.py -- how much of our AUC gap is model, and how much is data?

NO TRAINING HAPPENS HERE. Everything below is measured from labels alone, so
nothing depends on the circuit, the optimiser or a random seed.

THE QUESTION
------------
build_panel_dataset.py found that 89.8% of panel rows share a (site, wildtype,
mutant) triple with another row. Our four active features -- blosum62,
wt_volume, delta_volume, ace2_distance -- are all pure functions of that
triple. So two rows with the same triple get a BYTE-IDENTICAL feature vector,
and the model is obliged to give them the same score.

But their measured labels differ, because the genetic background differs. That
is epistasis, and it puts a hard ceiling on ANY model built on these features,
ours and every classical baseline alike.

This script measures that ceiling three ways:

  1. ORACLE CEILING (optimistic)
     Score each row by the empirical positive-rate of its triple across all
     genotypes. That is the Bayes-optimal context-free ranking. It is an UPPER
     bound and it is optimistically biased, because the rate is estimated from
     the same labels being scored. Reported for completeness, not for quoting.

  2. LEAVE-ONE-GENOTYPE-OUT CEILING (honest)
     Score each row of genotype g by the positive-rate of its triple among the
     OTHER genotypes only. No row contributes to its own score. This is the
     number to quote.

  3. PAIRWISE TRANSFER MATRIX (model-free)
     For each ordered pair (A, B), use A's measured binding as the score and
     B's binary label as the truth. Measures directly how well one background's
     measurements predict another's outcome, with no model in the loop at all.

CAVEATS, STATED UP FRONT
------------------------
* The ceiling applies to the ACTIVE four-feature set. Add a feature that
  carries background context and the ceiling moves. That is the point.
* Alias genotypes are detected and collapsed before anything is computed.
  Alpha and N501Y are the same RBD construct; so are Eta and E484K. Left
  separate they would report a fake transfer AUC of 1.0.
* Per-genotype class balance varies, so pooled AUC mixes base rates. Both
  pooled and per-genotype numbers are printed; prefer per-genotype.

Usage
-----
    python epistasis_ceiling.py --panel data/panel.csv --out epistasis.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

TRIPLE = ["site_SARS2", "wildtype", "mutant"]


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. alias detection -- verify, do not assume
# ---------------------------------------------------------------------------
def find_aliases(df: pd.DataFrame, tol: float = 1e-6,
                 min_overlap: float = 0.90) -> dict[str, str]:
    """Two genotype labels are aliases if, on the triples they share, every
    measured value agrees to within `tol`. We require them to share at least
    `min_overlap` of their triples as well, so a small accidental overlap
    cannot merge two genuinely different backgrounds.

    Returns {genotype: canonical_name}.
    """
    genos = sorted(df["genotype"].unique())
    tables = {
        g: sub.set_index(TRIPLE)["bind_avg"]
        for g, sub in df.groupby("genotype")
    }

    print("\n--- alias detection ------------------------------------------")
    edges: list[tuple[str, str]] = []
    for a, b in itertools.combinations(genos, 2):
        ta, tb = tables[a], tables[b]
        shared = ta.index.intersection(tb.index)
        if len(shared) == 0:
            continue
        frac = len(shared) / min(len(ta), len(tb))
        diff = float(np.nanmax(np.abs(
            ta.loc[shared].to_numpy() - tb.loc[shared].to_numpy())))
        if frac >= min_overlap and diff <= tol:
            print(f"  ALIAS  {a} == {b}   "
                  f"({len(shared)} shared triples, max |diff| = {diff:.2e})")
            edges.append((a, b))

    # union-find over the alias edges
    parent = {g: g for g in genos}

    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # deterministic canonical pick

    mapping = {g: root(g) for g in genos}
    groups: dict[str, list[str]] = {}
    for g, c in mapping.items():
        groups.setdefault(c, []).append(g)

    collapsed = {c: v for c, v in groups.items() if len(v) > 1}
    if not collapsed:
        print("  none found -- all genotype labels are distinct measurements")
    else:
        print("\n  collapsing:")
        for c, members in sorted(collapsed.items()):
            print(f"    {c}  <-  {sorted(members)}")
    print(f"  {len(genos)} labels -> {len(groups)} distinct backgrounds")
    print("--------------------------------------------------------------")
    return mapping


# ---------------------------------------------------------------------------
# 2. the ceilings
# ---------------------------------------------------------------------------
def safe_auc(y: np.ndarray, s: np.ndarray) -> float:
    """roc_auc_score, but NaN instead of an exception on a single-class y."""
    y = np.asarray(y)
    if len(np.unique(y)) < 2 or len(y) < 2:
        return float("nan")
    return float(roc_auc_score(y, np.asarray(s)))


def oracle_ceiling(df: pd.DataFrame) -> dict:
    """Score every row by its triple's positive rate over ALL genotypes.
    Optimistically biased upper bound."""
    rate = df.groupby(TRIPLE)["label"].transform("mean")
    return {
        "pooled_auc": safe_auc(df["label"].to_numpy(), rate.to_numpy()),
        "per_genotype": {
            g: safe_auc(sub["label"].to_numpy(), rate.loc[sub.index].to_numpy())
            for g, sub in df.groupby("genotype")
        },
    }


def logo_ceiling(df: pd.DataFrame) -> dict:
    """Leave-one-genotype-out. Each row is scored by the positive rate of its
    triple among the OTHER backgrounds, so no row informs its own score.

    Rows whose triple appears in only one background get no score and are
    excluded; the count is reported rather than hidden."""
    grp = df.groupby(TRIPLE)["label"]
    tot = grp.transform("sum")
    cnt = grp.transform("count")

    others_sum = tot - df["label"]
    others_cnt = cnt - 1
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(others_cnt > 0, others_sum / others_cnt, np.nan)

    work = df.assign(_score=score)
    n_excluded = int(work["_score"].isna().sum())
    work = work.dropna(subset=["_score"])

    per_geno = {}
    for g, sub in work.groupby("genotype"):
        per_geno[g] = {
            "auc": safe_auc(sub["label"].to_numpy(), sub["_score"].to_numpy()),
            "n": int(len(sub)),
            "pos_rate": float(sub["label"].mean()),
        }

    aucs = [v["auc"] for v in per_geno.values() if not np.isnan(v["auc"])]
    return {
        "pooled_auc": safe_auc(work["label"].to_numpy(),
                               work["_score"].to_numpy()),
        "mean_per_genotype_auc": float(np.mean(aucs)) if aucs else float("nan"),
        "per_genotype": per_geno,
        "rows_excluded_singleton_triple": n_excluded,
    }


def disagreement(df: pd.DataFrame) -> dict:
    """How often do backgrounds disagree on the binary outcome for an
    identical feature vector? This is the raw size of the problem."""
    g = df.groupby(TRIPLE)["label"].agg(["mean", "count"])
    multi = g[g["count"] > 1]
    mixed = multi[(multi["mean"] > 0) & (multi["mean"] < 1)]
    return {
        "distinct_triples": int(len(g)),
        "triples_in_more_than_one_background": int(len(multi)),
        "triples_with_disagreeing_labels": int(len(mixed)),
        "disagreement_rate": (float(len(mixed) / len(multi))
                              if len(multi) else float("nan")),
        "mean_minority_fraction_when_mixed": (
            float(np.minimum(mixed["mean"], 1 - mixed["mean"]).mean())
            if len(mixed) else float("nan")),
    }


def transfer_matrix(df: pd.DataFrame) -> dict:
    """Model-free. Score = background A's measured bind_avg (continuous, so
    more resolution than its binary label). Truth = background B's label.

    The diagonal is trivially 1.0 by construction -- A's measurement perfectly
    ranks A's own thresholded label -- so it is reported as NaN, not 1.0, to
    stop anyone reading it as a result."""
    tables = {g: sub.set_index(TRIPLE) for g, sub in df.groupby("genotype")}
    genos = sorted(tables)
    out: dict[str, dict[str, float]] = {}
    off_diag: list[float] = []

    for a in genos:
        out[a] = {}
        for b in genos:
            if a == b:
                out[a][b] = float("nan")
                continue
            ta, tb = tables[a], tables[b]
            shared = ta.index.intersection(tb.index)
            if len(shared) < 50:
                out[a][b] = float("nan")
                continue
            auc = safe_auc(tb.loc[shared, "label"].to_numpy(),
                           ta.loc[shared, "bind_avg"].to_numpy())
            out[a][b] = auc
            if not np.isnan(auc):
                off_diag.append(auc)

    return {
        "matrix": out,
        "genotypes": genos,
        "mean_off_diagonal": float(np.mean(off_diag)) if off_diag else float("nan"),
        "min_off_diagonal": float(np.min(off_diag)) if off_diag else float("nan"),
        "note": "diagonal is NaN by construction, not a measurement",
    }


def print_matrix(tm: dict) -> None:
    genos = tm["genotypes"]
    w = max(len(g) for g in genos) + 1
    print("\n--- pairwise transfer AUC (row = score source, col = truth) --")
    print(" " * w + "".join(f"{g[:7]:>8}" for g in genos))
    for a in genos:
        cells = []
        for b in genos:
            v = tm["matrix"][a][b]
            cells.append("     -- " if np.isnan(v) else f"{v:>8.3f}")
        print(f"{a:<{w}}" + "".join(cells))
    print(f"\n  mean off-diagonal: {tm['mean_off_diagonal']:.4f}")
    print(f"  worst pair:        {tm['min_off_diagonal']:.4f}")
    print("--------------------------------------------------------------")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default="data/panel.csv")
    ap.add_argument("--threshold", type=float, default=-1.0,
                    help="label threshold on the delta; must match train_vqc.py")
    ap.add_argument("--out", default="epistasis.json")
    ap.add_argument("--matrix-csv", default="transfer_matrix.csv",
                    help="wide csv of the transfer matrix, for plotting")
    args = ap.parse_args()

    if not os.path.exists(args.panel):
        die(f"{args.panel} not found. Run build_panel_dataset.py first.")

    df = pd.read_csv(args.panel)
    need = set(TRIPLE) | {"genotype", "bind_avg"}
    missing = need - set(df.columns)
    if missing:
        die(f"{args.panel} missing column(s): {sorted(missing)}")

    df["label"] = (df["bind_avg"] >= args.threshold).astype(int)
    print(f"Loaded {len(df)} rows, {df['genotype'].nunique()} genotype labels")
    print(f"Label: bind_avg >= {args.threshold}   "
          f"overall positive rate {df['label'].mean():.3f}")

    # collapse aliases BEFORE any statistic is computed
    mapping = find_aliases(df)
    df["genotype"] = df["genotype"].map(mapping)
    # one row per (background, triple) after collapsing
    before = len(df)
    df = df.drop_duplicates(subset=["genotype"] + TRIPLE, keep="first")
    if len(df) != before:
        print(f"  dropped {before - len(df)} duplicate rows created by "
              f"collapsing aliases")
    df = df.reset_index(drop=True)

    dis = disagreement(df)
    print("\n--- label disagreement ---------------------------------------")
    print(f"  distinct (site,wt,mut) triples:        "
          f"{dis['distinct_triples']}")
    print(f"  measured in >1 background:             "
          f"{dis['triples_in_more_than_one_background']}")
    print(f"  backgrounds DISAGREE on the label:     "
          f"{dis['triples_with_disagreeing_labels']}")
    print(f"  disagreement rate:                     "
          f"{dis['disagreement_rate']:.4f}")
    print(f"  mean minority fraction when mixed:     "
          f"{dis['mean_minority_fraction_when_mixed']:.4f}")
    print("  -> every disagreeing triple is a feature vector the model must\n"
          "     score once, against two different truths. This is the source\n"
          "     of the ceiling below.")
    print("--------------------------------------------------------------")

    orc = oracle_ceiling(df)
    logo = logo_ceiling(df)

    print("\n--- context-free ceiling -------------------------------------")
    print(f"  oracle (optimistic, do not quote):  "
          f"{orc['pooled_auc']:.4f}")
    print(f"  leave-one-genotype-out, pooled:     "
          f"{logo['pooled_auc']:.4f}")
    print(f"  leave-one-genotype-out, mean/geno:  "
          f"{logo['mean_per_genotype_auc']:.4f}   <-- QUOTE THIS")
    if logo["rows_excluded_singleton_triple"]:
        print(f"  rows excluded (triple in 1 background only): "
              f"{logo['rows_excluded_singleton_triple']}")
    print("\n  per background:")
    print(f"    {'background':<18}{'AUC':>8}{'n':>8}{'pos rate':>10}")
    for g, v in sorted(logo["per_genotype"].items()):
        a = "    nan" if np.isnan(v["auc"]) else f"{v['auc']:>8.3f}"
        print(f"    {g:<18}{a}{v['n']:>8}{v['pos_rate']:>10.3f}")
    print("--------------------------------------------------------------")

    tm = transfer_matrix(df)
    print_matrix(tm)

    payload = {
        "panel": os.path.basename(args.panel),
        "threshold": args.threshold,
        "n_rows": int(len(df)),
        "n_backgrounds": int(df["genotype"].nunique()),
        "alias_mapping": mapping,
        "disagreement": dis,
        "ceiling_oracle_optimistic": orc,
        "ceiling_leave_one_genotype_out": logo,
        "transfer": tm,
        "interpretation": (
            "The leave-one-genotype-out AUC is the best any model using only "
            "(site, wildtype, mutant)-derived features could achieve on this "
            "data. Compare it against the VQC and the classical baselines in "
            "metrics.json: a gap to the ceiling is model capacity, the ceiling "
            "itself is missing genetic context."
        ),
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2, default=float)
    print(f"\nWrote {args.out}")

    wide = pd.DataFrame(tm["matrix"]).T.loc[tm["genotypes"], tm["genotypes"]]
    wide.to_csv(args.matrix_csv)
    print(f"Wrote {args.matrix_csv}")

    print("\nNEXT: compare the quoted ceiling against metrics.json --")
    print("  VQC 0.7468 | LR 0.7799 | MLP 0.7661 | SVM 0.7504")
    print("  Those were measured on the 2020 single-genotype dataset, so this")
    print("  ceiling is indicative, not a like-for-like bound. To make it")
    print("  like-for-like, re-run those four on ONE background from this")
    print("  panel with the same site-grouped split.")


if __name__ == "__main__":
    main()
