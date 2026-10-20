"""
build_panel_dataset.py -- unify multi-genotype RBD DMS data into one table.

Reads the Bloom lab `final_variant_scores.csv` files for several RBD genotypes
and emits ONE csv in the column layout train_vqc.py already understands, plus a
`genotype` column so the training script can hold a whole genotype out.

VERIFIED SCHEMAS (checked 2026-10-18)
-------------------------------------
Current dataset -- SARS-CoV-2-RBD_DMS/results/single_mut_effects/single_mut_effects.csv
    site_RBD, site_SARS2, wildtype, mutant, mutation, mutation_RBD,
    bind_lib1, bind_lib2, bind_avg, expr_lib1, expr_lib2, expr_avg
    -> bind_avg is a DELTA (dlog10 Ka vs that background's wildtype)

Panel datasets -- {SARS-CoV-2-RBD_DMS_variants, _Omicron, _Delta}
                  results/final_variant_scores/final_variant_scores.csv
    target, wildtype, position, mutant, mutation, bind, delta_bind,
    n_bc_bind, n_libs_bind, bind_rep1, bind_rep2, bind_rep3,
    expr, delta_expr, n_bc_expr, n_libs_expr, expr_rep1, expr_rep2
    -> `bind`       is ABSOLUTE log10 Ka   (approx 6-11)
    -> `delta_bind` is the DELTA           (comparable to bind_avg)

THE TRAP: your label is `bind_avg >= -1.0`, which is a threshold on a DELTA.
The column that corresponds to it is `delta_bind`, NOT `bind`. Using `bind`
puts every row above -1.0, every label becomes 1, and AUC becomes undefined or
meaningless. This script only ever reads delta_bind.

BOTH PANEL FILES ARE GIT LFS POINTERS. A plain download or `git clone` without
`git lfs pull` gives you a 3-line stub, not data. This script detects that and
fails loudly rather than parsing a stub into an empty frame.

Usage
-----
    python build_panel_dataset.py \
        --variants /path/SARS-CoV-2-RBD_DMS_variants/results/final_variant_scores/final_variant_scores.csv \
        --omicron  /path/SARS-CoV-2-RBD_DMS_Omicron/results/final_variant_scores/final_variant_scores.csv \
        --out data/panel.csv

Any subset of inputs is fine; pass what you have. --legacy adds your existing
single_mut_effects.csv as a separate genotype, but read the batch-effect warning
printed at the end before you use it for cross-genotype claims.
"""


from __future__ import annotations

import argparse
import os
import sys
import pandas as pd

# RBD construct window, spike numbering. Matches ace2_distance.json's keys
# (which run 333-526) plus the flanking sites that fall back to ACE2_FAR.
RBD_LO, RBD_HI = 331, 531
SITE_OFFSET = 330  # site_RBD = site_SARS2 - 330, so 331 -> 1

STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")

PANEL_REQUIRED = {"target", "wildtype", "position", "mutant", "delta_bind"}
LEGACY_REQUIRED = {"site_SARS2", "wildtype", "mutant", "bind_avg"}

OUT_COLS = ["genotype", "site_RBD", "site_SARS2", "wildtype", "mutant",
            "mutation", "bind_avg"]


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _check_not_lfs_pointer(path: str) -> None:
    """A Git LFS stub is ~130 bytes of text starting with a version line."""
    if os.path.getsize(path) < 4096:
        with open(path, "r", errors="replace") as fh:
            head = fh.read(200)
        if "git-lfs.github.com/spec" in head:
            _die(
                f"{path} is a Git LFS pointer, not the real csv.\n"
                f"       Run:  git lfs install && git lfs pull\n"
                f"       inside that repository, then re-run this script."
            )


def _clean(df: pd.DataFrame, label_col: str, site_col: str,
           source: str) -> pd.DataFrame:
    """Shared filtering. Returns rows that are actually featurisable."""
    n0 = len(df)
    rejected = {}

    df = df.dropna(subset=[label_col, site_col, "wildtype", "mutant"])
    rejected["missing label/site/residue"] = n0 - len(df)

    n = len(df)
    df = df[df["wildtype"].astype(str).str.upper().isin(STANDARD_AA)]
    df = df[df["mutant"].astype(str).str.upper().isin(STANDARD_AA)]
    # Catches stop codons ('*'), ambiguity codes and deletions, none of which
    # mutation_features.py can featurise -- it raises MutationError on them.
    rejected["non-standard residue (incl. stop '*')"] = n - len(df)

    n = len(df)
    df = df[df["wildtype"].astype(str).str.upper()
            != df["mutant"].astype(str).str.upper()]
    # Wildtype/synonymous rows sit at delta ~0, so they are trivially positive
    # and would inflate the positive class without carrying signal.
    rejected["wildtype == mutant"] = n - len(df)

    n = len(df)
    df[site_col] = pd.to_numeric(df[site_col], errors="coerce")
    df = df.dropna(subset=[site_col])
    df = df[(df[site_col] >= RBD_LO) & (df[site_col] <= RBD_HI)]
    rejected["outside RBD window 331-531"] = n - len(df)

    print(f"  {source}: kept {len(df)} of {n0} rows")
    for reason, count in rejected.items():
        if count:
            print(f"      dropped {count:>6} -- {reason}")
    return df


def load_panel(path: str) -> pd.DataFrame:
    _check_not_lfs_pointer(path)
    df = pd.read_csv(path)
    missing = PANEL_REQUIRED - set(df.columns)
    if missing:
        _die(
            f"{path} is missing expected column(s): {sorted(missing)}\n"
            f"       Columns present: {sorted(df.columns)}\n"
            f"       The Bloom lab changes schemas between papers. Check "
            f"whether `delta_bind` was renamed before editing this script."
        )
    if "bind" in df.columns:
        # Sanity check that we picked the right column, not a silent mix-up.
        med_abs, med_delta = df["bind"].median(), df["delta_bind"].median()
        print(f"  schema check: median bind={med_abs:.2f} (absolute log10 Ka), "
              f"median delta_bind={med_delta:.2f} (delta)")
        if abs(med_delta) > 3:
            print("      WARNING: delta_bind median is far from 0. Confirm "
                  "this column really is a delta before trusting labels.")

    df = _clean(df, "delta_bind", "position", os.path.basename(path))
    out = pd.DataFrame({
        "genotype": df["target"].astype(str),
        "site_SARS2": df["position"].astype(int),
        "wildtype": df["wildtype"].astype(str).str.upper(),
        "mutant": df["mutant"].astype(str).str.upper(),
        "bind_avg": df["delta_bind"].astype(float),
    })
    out["site_RBD"] = out["site_SARS2"] - SITE_OFFSET
    out["mutation"] = (out["wildtype"] + out["site_SARS2"].astype(str)
                       + out["mutant"])
    return out[OUT_COLS]


def load_legacy(path: str, name: str = "Wuhan-Hu-1-2020") -> pd.DataFrame:
    _check_not_lfs_pointer(path)
    df = pd.read_csv(path)
    missing = LEGACY_REQUIRED - set(df.columns)
    if missing:
        _die(f"{path} missing column(s): {sorted(missing)}")
    df = _clean(df, "bind_avg", "site_SARS2", os.path.basename(path))
    out = pd.DataFrame({
        "genotype": name,
        "site_SARS2": df["site_SARS2"].astype(int),
        "wildtype": df["wildtype"].astype(str).str.upper(),
        "mutant": df["mutant"].astype(str).str.upper(),
        "bind_avg": df["bind_avg"].astype(float),
    })
    out["site_RBD"] = out["site_SARS2"] - SITE_OFFSET
    out["mutation"] = (out["wildtype"] + out["site_SARS2"].astype(str)
                       + out["mutant"])
    return out[OUT_COLS]


def report(df: pd.DataFrame, threshold: float) -> None:
    """Per-genotype class balance. Read this before trusting any cross-genotype
    AUC: if the positive rate swings a lot between genotypes, the single
    threshold is not measuring the same thing in each one."""
    print("\n--- per-genotype summary -------------------------------------")
    print(f"{'genotype':<18} {'rows':>7} {'sites':>7} {'pos rate':>9} "
          f"{'median d':>9}")
    rows = []
    for g, sub in df.groupby("genotype"):
        pos = float((sub["bind_avg"] >= threshold).mean())
        rows.append((g, len(sub), sub["site_SARS2"].nunique(), pos,
                     float(sub["bind_avg"].median())))
    for g, n, s, pos, med in sorted(rows):
        print(f"{g:<18} {n:>7} {s:>7} {pos:>9.3f} {med:>9.2f}")

    pos_rates = [r[3] for r in rows]
    if len(pos_rates) > 1 and (max(pos_rates) - min(pos_rates)) > 0.15:
        print("\n  WARNING: positive-class rate varies by more than 15 points "
              "across\n  genotypes. A single threshold of "
              f"{threshold} is not comparable between them.\n  Consider a "
              "per-genotype quantile threshold, and report both.")

    # How much genuinely NEW feature information the panel adds. Your active
    # features are (blosum62, wt_volume, delta_volume, ace2_distance), all
    # determined by the (site, wildtype, mutant) triple -- so two genotypes
    # sharing a triple produce an IDENTICAL feature vector.
    triples = df[["site_SARS2", "wildtype", "mutant"]].drop_duplicates()
    print(f"\n  rows total:                    {len(df)}")
    print(f"  distinct (site,wt,mut) triples: {len(triples)}")
    print(f"  -> duplicate-feature rows:      {len(df) - len(triples)} "
          f"({100 * (1 - len(triples) / len(df)):.1f}%)")
    print("     Those rows share a feature vector with another row and differ\n"
          "     only in label. They add label noise, not new signal. See the\n"
          "     note in the chat about what this means for AUC.")
    print("--------------------------------------------------------------")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", help="RBD_DMS_variants final_variant_scores.csv")
    ap.add_argument("--omicron", help="RBD_DMS_Omicron final_variant_scores.csv")
    ap.add_argument("--delta", help="RBD_Delta final_variant_scores.csv")
    ap.add_argument("--legacy", help="your existing single_mut_effects.csv")
    ap.add_argument("--out", default="data/panel.csv")
    ap.add_argument("--threshold", type=float, default=-1.0,
                    help="label threshold on the delta, matching train_vqc.py")
    args = ap.parse_args()

    frames = []
    print("Loading:")
    for path in (args.variants, args.omicron, args.delta):
        if path:
            frames.append(load_panel(path))
    if args.legacy:
        frames.append(load_legacy(args.legacy))

    if not frames:
        _die("no input files given. Pass at least one of "
             "--variants/--omicron/--delta/--legacy.")

    df = pd.concat(frames, ignore_index=True)

    # Same genotype name appearing in two files would silently double rows.
    dupes = df.duplicated(subset=["genotype", "site_SARS2", "wildtype",
                                  "mutant"], keep=False)
    if dupes.any():
        print(f"\n  NOTE: {int(dupes.sum())} rows share "
              f"(genotype, site, wt, mut) with another row. Keeping the first "
              f"of each; check your inputs do not overlap.")
        df = df.drop_duplicates(subset=["genotype", "site_SARS2", "wildtype",
                                        "mutant"], keep="first")

    report(df, args.threshold)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"\nWrote {len(df)} rows, {df['genotype'].nunique()} genotypes "
          f"-> {args.out}")

    if args.legacy and (args.variants or args.omicron or args.delta):
        print(
            "\nBATCH-EFFECT WARNING\n"
            "  You mixed single_mut_effects.csv (2020 assay) with the later\n"
            "  final_variant_scores panel. Those are different experimental\n"
            "  batches, so a genotype-to-genotype AUC difference may be an\n"
            "  assay difference rather than biology. The variants file has its\n"
            "  OWN Wuhan-Hu-1 target -- use that as your baseline genotype for\n"
            "  cross-genotype comparisons, and keep the 2020 dataset only as\n"
            "  the continuity result you already published."
        )


if __name__ == "__main__":
    main()
